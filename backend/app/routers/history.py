"""生成历史：服务端持久化（每用户最新 100 条），点选还原 prompt/参数/参考图。"""
import base64
import json
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.config import settings
from ..db.session import get_db
from ..deps import get_current_user, get_file_user
from ..models import Asset, GenerationHistory, User
from ..services.image_util import make_thumb

router = APIRouter(prefix="/api/history", tags=["history"])

HISTORY_KEEP = 100  # 每用户最多保留条数，超出的连文件一起裁掉

MIME_TO_EXT = {
    "image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp",
    "image/gif": ".gif", "image/bmp": ".bmp", "image/avif": ".avif",
    "image/svg+xml": ".svg",
}


def _hist_dir() -> str:
    d = os.path.join(settings.data_dir, "history")
    os.makedirs(d, exist_ok=True)
    return d


class HistoryImage(BaseModel):
    b64: str
    mime: str = "image/png"


class HistoryIn(BaseModel):
    model: str
    prompt: str
    params: dict = Field(default_factory=dict)
    provider_choice: str | None = None
    reference_ids: list[str] = Field(default_factory=list)
    images: list[HistoryImage] = Field(default_factory=list)
    usage: dict | None = None
    error: str | None = None


def _item_out(db: Session, h: GenerationHistory) -> dict:
    try:
        params = json.loads(h.params_json or "{}")
    except Exception:
        params = {}
    try:
        ref_ids = json.loads(h.reference_ids_json or "[]")
    except Exception:
        ref_ids = []
    try:
        paths = json.loads(h.image_paths_json or "[]")
    except Exception:
        paths = []
    try:
        usage = json.loads(h.usage_json) if h.usage_json else None
    except Exception:
        usage = None
    refs = []
    for rid in ref_ids:
        a = db.get(Asset, rid)
        if a:
            refs.append({"id": a.id, "filename": a.filename,
                         "file_url": f"/api/assets/{a.id}/file",
                         "thumb_url": f"/api/assets/{a.id}/thumb" if a.thumb_path else f"/api/assets/{a.id}/file"})
    return {
        "id": h.id,
        "time": h.created_at.isoformat() if h.created_at else None,
        "model": h.model,
        "prompt": h.prompt,
        "params": params,
        "providerChoice": h.provider_choice or "",
        "references": refs,
        "image_count": len(paths),
        "thumbs": [f"/api/history/{h.id}/thumb/{i}" for i in range(len(paths))],
        "images": [f"/api/history/{h.id}/image/{i}" for i in range(len(paths))],
        "usage": usage,
        "error": h.error,
    }


@router.post("")
def save_history(body: HistoryIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    hid = uuid.uuid4().hex
    paths, mimes = [], []
    for i, img in enumerate(body.images):
        try:
            raw = base64.b64decode(img.b64.split(",")[-1])
        except Exception:
            raise HTTPException(400, "图片 b64 非法")
        mime = (img.mime or "image/png").split(";")[0]
        ext = MIME_TO_EXT.get(mime, ".png")
        rel = os.path.join("history", f"{hid}_{i}{ext}")
        abs_path = os.path.join(settings.data_dir, rel)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "wb") as f:
            f.write(raw)
        try:
            make_thumb(abs_path, os.path.join(settings.data_dir, "history", f"{hid}_{i}.thumb.webp"))
        except Exception:
            pass
        paths.append(rel)
        mimes.append(mime)
    cost = None
    try:
        cost = (body.usage or {}).get("cost")
    except Exception:
        pass
    h = GenerationHistory(
        id=hid, user_id=user.id, model=body.model, prompt=body.prompt[:4000],
        params_json=json.dumps(body.params or {}), provider_choice=body.provider_choice,
        reference_ids_json=json.dumps(body.reference_ids or []),
        image_paths_json=json.dumps(paths), image_mimes_json=json.dumps(mimes),
        usage_json=json.dumps(body.usage) if body.usage else None,
        error=body.error, cost=cost,
    )
    db.add(h)
    db.commit()
    # 裁剪：只留最新 HISTORY_KEEP 条（含文件）
    olds = db.query(GenerationHistory).filter(GenerationHistory.user_id == user.id)\
        .order_by(GenerationHistory.created_at.desc()).offset(HISTORY_KEEP).all()
    for o in olds:
        _delete_files(o)
        db.delete(o)
    db.commit()
    db.refresh(h)
    return _item_out(db, h)


def _delete_files(h: GenerationHistory) -> None:
    try:
        paths = json.loads(h.image_paths_json or "[]")
    except Exception:
        paths = []
    for rel in paths:
        for p in (os.path.join(settings.data_dir, rel),
                  os.path.join(settings.data_dir, "history", os.path.basename(rel).rsplit(".", 1)[0] + ".thumb.webp")):
            try:
                os.remove(p)
            except OSError:
                pass


@router.get("")
def list_history(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(GenerationHistory).filter(GenerationHistory.user_id == user.id)\
        .order_by(GenerationHistory.created_at.desc()).limit(HISTORY_KEEP).all()
    return [_item_out(db, h) for h in rows]


@router.delete("")
def clear_history(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(GenerationHistory).filter(GenerationHistory.user_id == user.id).all()
    for h in rows:
        _delete_files(h)
        db.delete(h)
    db.commit()
    return {"ok": True}


@router.delete("/{hid}")
def delete_history(hid: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    h = db.get(GenerationHistory, hid)
    if not h or h.user_id != user.id:
        raise HTTPException(404, "记录不存在")
    _delete_files(h)
    db.delete(h)
    db.commit()
    return {"ok": True}


def _serve(hid: str, idx: int, thumb: bool, request: Request, db: Session):
    h = db.get(GenerationHistory, hid)
    if not h:
        raise HTTPException(404, "记录不存在")
    try:
        paths = json.loads(h.image_paths_json or "[]")
        mimes = json.loads(h.image_mimes_json or "[]")
    except Exception:
        raise HTTPException(404, "记录不存在")
    if idx < 0 or idx >= len(paths):
        raise HTTPException(404, "记录不存在")
    if thumb:
        base = os.path.basename(paths[idx]).rsplit(".", 1)[0]
        p = os.path.join(settings.data_dir, "history", base + ".thumb.webp")
        if os.path.exists(p):
            return FileResponse(p, media_type="image/webp")
    mime = mimes[idx] if idx < len(mimes) else "image/png"
    return FileResponse(os.path.join(settings.data_dir, paths[idx]), media_type=mime)


@router.get("/{hid}/image/{idx}")
def serve_history_image(hid: str, idx: int, request: Request,
                        user: User = Depends(get_file_user), db: Session = Depends(get_db)):
    h = db.get(GenerationHistory, hid)
    if not h or (h.user_id != user.id and not user.is_admin):
        raise HTTPException(404, "记录不存在")
    return _serve(hid, idx, False, request, db)


@router.get("/{hid}/thumb/{idx}")
def serve_history_thumb(hid: str, idx: int, request: Request,
                        user: User = Depends(get_file_user), db: Session = Depends(get_db)):
    h = db.get(GenerationHistory, hid)
    if not h or (h.user_id != user.id and not user.is_admin):
        raise HTTPException(404, "记录不存在")
    return _serve(hid, idx, True, request, db)
