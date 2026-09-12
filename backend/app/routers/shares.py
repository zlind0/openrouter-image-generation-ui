"""图床：公开查看链接（<img src> 可引用）+ 访问统计 + revoke。"""
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..deps import get_current_user
from ..models import Asset, ShareLink, ShareView, User
from ..services.image_util import is_modern_lossless_avif_needed, needs_compat_fallback
from fastapi.responses import FileResponse
from ..core.config import settings
import os

router = APIRouter(tags=["shares"])


class ShareCreate(BaseModel):
    expires_at: str | None = None


@router.post("/api/assets/{aid}/shares")
def create_share(aid: str, body: ShareCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    a = db.get(Asset, aid)
    if not a:
        raise HTTPException(404, "素材不存在")
    # 仅上传者/管理员可开公开链接（普通用户可看但不可公开别人的图）
    if not (user.is_admin or a.owner_id == user.id):
        raise HTTPException(403, "仅上传者/管理员可创建公开链接")
    token = secrets.token_urlsafe(32)
    exp = None
    if body.expires_at:
        try:
            exp = datetime.fromisoformat(body.expires_at)
        except Exception:
            raise HTTPException(400, "expires_at 须为 ISO 时间")
    s = ShareLink(token=token, asset_id=aid, created_by=user.id, expires_at=exp)
    db.add(s)
    db.commit()
    return {"token": token, "url": f"/s/{token}", "id": s.id}


@router.get("/api/shares")
def list_shares(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(ShareLink)
    if not user.is_admin:
        q = q.filter(ShareLink.created_by == user.id)
    out = []
    for s in q.order_by(ShareLink.created_at.desc()).limit(500).all():
        a = db.get(Asset, s.asset_id)
        out.append({
            "id": s.id, "token": s.token, "url": f"/s/{s.token}",
            "asset_id": s.asset_id, "filename": a.filename if a else "?",
            "revoked": s.revoked, "view_count": s.view_count,
            "expires_at": s.expires_at.isoformat() if s.expires_at else None,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        })
    return out


@router.get("/api/shares/{sid}/stats")
def share_stats(sid: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = db.get(ShareLink, sid)
    if not s:
        raise HTTPException(404, "链接不存在")
    if not (user.is_admin or s.created_by == user.id):
        raise HTTPException(403, "无权查看")
    views = db.query(ShareView).filter(ShareView.share_id == sid).order_by(ShareView.created_at.desc()).limit(200).all()
    # 按 IP 聚合
    by_ip: dict[str, int] = {}
    for v in db.query(ShareView).filter(ShareView.share_id == sid).all():
        by_ip[v.ip] = by_ip.get(v.ip, 0) + 1
    return {
        "view_count": s.view_count, "revoked": s.revoked,
        "by_ip": by_ip,
        "recent": [{"ip": v.ip, "ua": v.ua[:200], "at": v.created_at.isoformat() if v.created_at else None} for v in views],
    }


@router.delete("/api/shares/{sid}")
def revoke_share(sid: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = db.get(ShareLink, sid)
    if not s:
        raise HTTPException(404, "链接不存在")
    if not (user.is_admin or s.created_by == user.id):
        raise HTTPException(403, "无权撤销")
    s.revoked = True
    db.commit()
    return {"ok": True}


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()[:64]
    return (request.client.host if request.client else "?")[:64]


@router.get("/s/{token}")
def public_view(token: str, request: Request, db: Session = Depends(get_db)):
    """公开图片：直接返回 image/*，可被 <img src> 引用；每次访问记 IP/UA。"""
    s = db.query(ShareLink).filter(ShareLink.token == token).first()
    if not s or s.revoked:
        raise HTTPException(404, "链接不存在或已撤销")
    if s.expires_at:
        exp = s.expires_at.replace(tzinfo=timezone.utc) if s.expires_at.tzinfo is None else s.expires_at
        if exp < datetime.now(timezone.utc):
            raise HTTPException(410, "链接已过期")
    a = db.get(Asset, s.asset_id)
    if not a:
        raise HTTPException(404, "原图已删除")
    # 统计（失败不影响 serving）
    try:
        s.view_count += 1
        db.add(ShareView(share_id=s.id, ip=_client_ip(request), ua=request.headers.get("user-agent", "")[:512]))
        db.commit()
    except Exception:
        pass
    # AVIF 协商：与私有 file 接口同逻辑
    rel, mime, headers = a.stored_path, a.mime, {}
    if is_modern_lossless_avif_needed(a.mime) and a.fallback_path:
        accept = request.headers.get("accept", "")
        ua = request.headers.get("user-agent", "")
        if needs_compat_fallback(accept, ua, request.query_params.get("compat") == "1"):
            rel, mime = a.fallback_path, "image/jpeg"
            headers["X-Served-Fallback"] = "avif-to-jpeg"
    headers["Cache-Control"] = "public, max-age=86400"
    return FileResponse(os.path.join(settings.data_dir, rel), media_type=mime, headers=headers)
