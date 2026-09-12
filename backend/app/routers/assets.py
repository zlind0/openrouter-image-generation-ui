"""素材库：文件夹树 + 按文件夹上传 + tag + EXIF/尺寸筛选 + AVIF 兼容。"""
import base64
import os
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..core.config import settings
from ..db.session import get_db
from ..deps import can_manage_asset, get_current_user, get_file_user
from ..models import Asset, AssetTag, Folder, Tag, User
from ..services.exif_util import extract_exif
from ..services.image_util import (
    ALLOWED_EXTS,
    guess_mime,
    is_modern_lossless_avif_needed,
    make_jpeg_fallback,
    make_thumb,
    needs_compat_fallback,
    resolve_image_ext,
    sniff_mime,
)

router = APIRouter(prefix="/api/assets", tags=["assets"])

# 默认库：未指定文件夹的上传/入库一律归入此处
DEFAULT_UPLOAD_FOLDER = "上传素材"


def ensure_default_folder(db: Session) -> Folder:
    """获取或创建顶级「上传素材」文件夹（供启动预置与上传兜底）"""
    f = db.query(Folder).filter(Folder.parent_id.is_(None), Folder.name == DEFAULT_UPLOAD_FOLDER).first()
    if not f:
        f = Folder(name=DEFAULT_UPLOAD_FOLDER, parent_id=None, path=DEFAULT_UPLOAD_FOLDER, created_by="system")
        db.add(f)
        db.commit()
        db.refresh(f)
    return f


def _data_dir() -> str:
    d = settings.data_dir
    os.makedirs(d, exist_ok=True)
    return d


def _norm_tag(name: str) -> str:
    return name.strip().lower().replace(" ", "")[:64]


def _ensure_folder(db: Session, path: str, owner: User) -> str | None:
    """'旅拍/京都' -> 逐级建文件夹，返回叶子 id。空路径返回 None。"""
    parts = [p.strip() for p in (path or "").split("/") if p.strip()]
    if not parts:
        return None
    parent = None
    full = ""
    for p in parts:
        full = f"{full}/{p}" if full else p
        q = db.query(Folder).filter(Folder.path == full)
        if parent:
            q = q.filter(Folder.parent_id == parent)
        f = q.first()
        if not f:
            f = Folder(name=p, parent_id=parent, path=full, created_by=owner.id)
            db.add(f)
            db.flush()
        parent = f.id
    db.commit()
    return parent


@router.get("/folders")
def list_folders(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Folder).order_by(Folder.path).all()
    return [{"id": f.id, "name": f.name, "parent_id": f.parent_id, "path": f.path} for f in rows]


@router.post("/folders")
def create_folder(body: dict, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    name = str(body.get("name", "")).strip()
    parent_id = body.get("parent_id")
    if not name:
        raise HTTPException(400, "文件夹名不能为空")
    parent_path = ""
    if parent_id:
        p = db.get(Folder, parent_id)
        if not p:
            raise HTTPException(404, "父文件夹不存在")
        parent_path = p.path
    path = f"{parent_path}/{name}" if parent_path else name
    if db.query(Folder).filter(Folder.path == path).first():
        raise HTTPException(400, "同路径文件夹已存在")
    f = Folder(name=name, parent_id=parent_id, path=path, created_by=user.id)
    db.add(f)
    db.commit()
    return {"id": f.id, "path": f.path}


class SkippedFile(Exception):
    """批量上传中单个文件的可跳过问题（杂文件/不支持的格式），不影响整批。"""
    pass


def _save_asset_file(db: Session, owner: User, filename: str, raw: bytes, folder_id: str | None,
                     tags: list[str], source: str = "upload", prompt: str | None = None) -> Asset:
    if len(raw) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(400, f"文件过大（限 {settings.max_upload_mb}MB）：{filename}")
    # 先落暂存文件，再按“后缀优先、内容兜底”识别，避免错后缀/无后缀/杂文件误杀
    tmp_rel = f"tmp/{uuid.uuid4().hex}.bin"
    tmp_abs = os.path.join(_data_dir(), tmp_rel)
    os.makedirs(os.path.dirname(tmp_abs), exist_ok=True)
    with open(tmp_abs, "wb") as fh:
        fh.write(raw)
    try:
        ext = resolve_image_ext(tmp_abs, filename)
        if not ext:
            raise SkippedFile(f"非受支持的图片格式（png/jpg/webp/gif/bmp/tiff/svg/avif/heic）：{filename}")
        rel = f"{uuid.uuid4().hex[:2]}/{uuid.uuid4().hex[:2]}/{uuid.uuid4().hex}{ext}"
        abs_path = os.path.join(_data_dir(), rel)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        os.rename(tmp_abs, abs_path)
    except SkippedFile:
        try:
            os.remove(tmp_abs)
        except OSError:
            pass
        raise
    except Exception as e:
        try:
            os.remove(tmp_abs)
        except OSError:
            pass
        raise HTTPException(400, f"图片读取失败：{filename}（{e}）")
    mime = sniff_mime(abs_path, filename)
    exif = extract_exif(abs_path)
    width, height = exif.pop("width", None), exif.pop("height", None)
    # 缩略图（svg 跳过）
    thumb_rel = None
    try:
        thumb_rel = rel + ".thumb.webp"
        make_thumb(abs_path, os.path.join(_data_dir(), thumb_rel))
    except Exception:
        thumb_rel = None
    # AVIF/HEIC 预生成 JPEG 兜底，供 Firefox 等不支持 4:4:4 的浏览器
    fallback_rel = None
    try:
        if is_modern_lossless_avif_needed(mime):
            fallback_rel = rel + ".fallback.jpg"
            make_jpeg_fallback(abs_path, os.path.join(_data_dir(), fallback_rel))
    except Exception:
        fallback_rel = None
    a = Asset(owner_id=owner.id, folder_id=folder_id, filename=filename[:255],
              stored_path=rel, thumb_path=thumb_rel, fallback_path=fallback_rel,
              mime=mime, size_bytes=len(raw), width=width, height=height,
              exif=exif, source=source, prompt=prompt)
    db.add(a)
    db.flush()
    for t in tags:
        n = _norm_tag(t)
        if not n:
            continue
        tag = db.query(Tag).filter(Tag.name == n).first() or Tag(name=n)
        db.add(tag)
        db.flush()
        db.add(AssetTag(asset_id=a.id, tag_id=tag.id))
    db.commit()
    db.refresh(a)
    return a


def _asset_out(db: Session, a: Asset) -> dict:
    tag_ids = [r.tag_id for r in db.query(AssetTag).filter(AssetTag.asset_id == a.id).all()]
    tags = [t.name for t in db.query(Tag).filter(Tag.id.in_(tag_ids)).all()] if tag_ids else []
    owner = db.get(User, a.owner_id)
    return {
        "id": a.id, "filename": a.filename, "mime": a.mime, "size_bytes": a.size_bytes,
        "width": a.width, "height": a.height, "exif": a.exif or {}, "tags": tags,
        "folder_id": a.folder_id, "owner": owner.username if owner else "?",
        "owner_id": a.owner_id, "source": a.source,
        "file_url": f"/api/assets/{a.id}/file",
        "thumb_url": f"/api/assets/{a.id}/thumb" if a.thumb_path else f"/api/assets/{a.id}/file",
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


@router.post("/upload")
async def upload(
    files: list[UploadFile] = File(...),
    folder_id: str | None = Form(None),
    folder_path: str | None = Form(None),
    tags: str = Form(""),
    request: Request = None,  # noqa
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # 按文件夹上传：前端传 webkitRelativePath 拼出的 folder_path，自动建树；
    # 两者都未指定时默认归入「上传素材」库
    fid = folder_id or None
    if folder_path:
        fid = _ensure_folder(db, folder_path, user)
    if not fid:
        fid = ensure_default_folder(db).id
    tag_list = [t for t in (tags or "").split(",") if t.strip()]
    saved, skipped = [], []
    for f in files:
        raw = await f.read()
        name = f.filename or "unnamed"
        try:
            a = _save_asset_file(db, user, name, raw, fid, tag_list)
            saved.append(_asset_out(db, a))
        except SkippedFile as e:
            # 单文件上传：直接报错让用户知道；批量上传：跳过该文件继续
            if len(files) == 1:
                raise HTTPException(400, str(e))
            skipped.append({"filename": name, "reason": str(e)})
        except HTTPException:
            if len(files) == 1:
                raise
            skipped.append({"filename": name, "reason": "文件过大或读取失败"})
    return {"assets": saved, "skipped": skipped}


class FromGenIn(BaseModel):
    b64: str
    filename: str = "generated.png"
    mime: str = "image/png"
    folder_id: str | None = None
    tags: list[str] = []
    prompt: str | None = None


@router.post("/from-generation")
def from_generation(body: FromGenIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        raw = base64.b64decode(body.b64.split(",")[-1])
    except Exception:
        raise HTTPException(400, "b64 非法")
    # 点击入库才调到这里；未选文件夹则默认进入「上传素材」库
    fid = body.folder_id or ensure_default_folder(db).id
    a = _save_asset_file(db, user, body.filename, raw, fid, body.tags, source="generate", prompt=body.prompt)
    return _asset_out(db, a)


@router.get("")
def list_assets(
    folder_id: str | None = None,
    tags: str = Query("", description="逗号分隔"),
    match: str = Query("all", pattern="^(all|any)$"),
    q: str = "",
    mime: str = "",
    make: str = Query("", description="EXIF Make/Model 模糊匹配，如 Canon"),
    iso_min: int | None = None,
    iso_max: int | None = None,
    uploader: str = "",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Asset)
    if folder_id:
        query = query.filter(Asset.folder_id == folder_id)
    if mime:
        query = query.filter(Asset.mime == mime)
    if q:
        query = query.filter(Asset.filename.ilike(f"%{q}%"))
    if uploader:
        u = db.query(User).filter(User.username == uploader).first()
        query = query.filter(Asset.owner_id == u.id) if u else query.filter(False)
    rows = query.order_by(Asset.created_at.desc()).limit(500).all()
    # tag + exif 在 Python 侧过滤（量<20人可接受；大了再改 SQL JSONB 查询）
    tag_list = [_norm_tag(t) for t in tags.split(",") if t.strip()]
    res = []
    for a in rows:
        tids = [r.tag_id for r in db.query(AssetTag).filter(AssetTag.asset_id == a.id).all()]
        tnames = {t.name for t in db.query(Tag).filter(Tag.id.in_(tids)).all()} if tids else set()
        if tag_list:
            hit = [t in tnames for t in tag_list]
            if match == "all" and not all(hit):
                continue
            if match == "any" and not any(hit):
                continue
        ex = a.exif or {}
        if make and make.lower() not in f"{ex.get('Make', '')} {ex.get('Model', '')}".lower():
            continue
        try:
            iso = int(str(ex.get("ISOSpeedRatings", "0")).strip().split()[0])
        except Exception:
            iso = None
        if iso_min is not None and (iso is None or iso < iso_min):
            continue
        if iso_max is not None and (iso is None or iso > iso_max):
            continue
        res.append(_asset_out(db, a) | {"tags": sorted(tnames)})
    return res


class AssetPatch(BaseModel):
    tags: list[str] | None = None
    folder_id: str | None = None


@router.patch("/{aid}")
def patch_asset(aid: str, body: AssetPatch, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    a = db.get(Asset, aid)
    if not a:
        raise HTTPException(404, "素材不存在")
    if not can_manage_asset(user, a.owner_id):
        raise HTTPException(403, "仅上传者/管理员可管理")
    if body.folder_id is not None:
        a.folder_id = body.folder_id or None
    if body.tags is not None:
        db.query(AssetTag).filter(AssetTag.asset_id == aid).delete()
        for t in body.tags:
            n = _norm_tag(t)
            if not n:
                continue
            tag = db.query(Tag).filter(Tag.name == n).first() or Tag(name=n)
            db.add(tag)
            db.flush()
            db.add(AssetTag(asset_id=aid, tag_id=tag.id))
    db.commit()
    return _asset_out(db, db.get(Asset, aid))


@router.delete("/{aid}")
def delete_asset(aid: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    a = db.get(Asset, aid)
    if not a:
        raise HTTPException(404, "素材不存在")
    if not can_manage_asset(user, a.owner_id):
        raise HTTPException(403, "仅上传者/管理员可删除")
    for rel in (a.stored_path, a.thumb_path, a.fallback_path):
        if rel:
            try:
                os.remove(os.path.join(_data_dir(), rel))
            except OSError:
                pass
    db.delete(a)
    db.commit()
    return {"ok": True}


def _serve_file(asset: Asset, request: Request, thumb: bool = False):
    rel = asset.stored_path
    mime = asset.mime
    fallback_used = False
    if thumb and asset.thumb_path:
        rel = asset.thumb_path
        mime = "image/webp"
    elif not thumb and is_modern_lossless_avif_needed(asset.mime) and asset.fallback_path:
        accept = request.headers.get("accept", "")
        ua = request.headers.get("user-agent", "")
        compat = request.query_params.get("compat") == "1"
        if needs_compat_fallback(accept, ua, compat):
            rel = asset.fallback_path
            mime = "image/jpeg"
            fallback_used = True
    headers = {}
    if fallback_used:
        headers["X-Served-Fallback"] = "avif-to-jpeg"
    return FileResponse(os.path.join(_data_dir(), rel), media_type=mime, headers=headers)


@router.get("/{aid}/file")
def serve_file(aid: str, request: Request, user: User = Depends(get_file_user), db: Session = Depends(get_db)):
    a = db.get(Asset, aid)
    if not a:
        raise HTTPException(404, "素材不存在")
    return _serve_file(a, request)


@router.get("/{aid}/thumb")
def serve_thumb(aid: str, request: Request, user: User = Depends(get_file_user), db: Session = Depends(get_db)):
    a = db.get(Asset, aid)
    if not a:
        raise HTTPException(404, "素材不存在")
    # 兜底：老数据可能没有 thumb_path，访问时按需生成一次并回写
    if not a.thumb_path or not os.path.exists(os.path.join(_data_dir(), a.thumb_path)):
        try:
            rel = f"{a.stored_path}.thumb.webp"
            make_thumb(os.path.join(_data_dir(), a.stored_path), os.path.join(_data_dir(), rel))
            a.thumb_path = rel
            db.commit()
        except Exception:
            # svg 等无法生成缩略图时直接回退原图
            return _serve_file(a, request)
    return _serve_file(a, request, thumb=True)
