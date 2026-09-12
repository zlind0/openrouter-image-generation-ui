"""管理员：用户管理 + OpenRouter Key 加密存储。"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.crypto import decrypt_api_key, encrypt_api_key, fingerprint, masked
from ..core.security import hash_password
from ..db.session import get_db
from ..deps import require_admin
from ..models import AppSetting, AuditLog, ServerCache, User

router = APIRouter(prefix="/api/admin", tags=["admin"])


class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=6, max_length=128)


class UserPatch(BaseModel):
    password: str | None = None
    is_active: bool | None = None


@router.get("/users")
def list_users(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [
        {"id": u.id, "username": u.username, "is_admin": u.is_admin, "is_active": u.is_active,
         "created_at": u.created_at.isoformat() if u.created_at else None}
        for u in db.query(User).order_by(User.created_at).all()
    ]


@router.post("/users")
def create_user(body: UserCreate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(status_code=400, detail="用户名已存在")
    u = User(username=body.username.strip(), password_hash=hash_password(body.password))
    db.add(u)
    db.add(AuditLog(actor=admin.username, action="user.create", detail=f"username={u.username}"))
    db.commit()
    return {"id": u.id, "username": u.username}


@router.patch("/users/{uid}")
def patch_user(uid: str, body: UserPatch, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    u = db.get(User, uid)
    if not u:
        raise HTTPException(status_code=404, detail="用户不存在")
    if u.is_admin:
        raise HTTPException(status_code=400, detail="管理员账号不可修改/停用（保持单管理员）")
    if body.password:
        u.password_hash = hash_password(body.password)
    if body.is_active is not None:
        u.is_active = body.is_active
    db.add(AuditLog(actor=admin.username, action="user.patch", detail=f"username={u.username}"))
    db.commit()
    return {"ok": True}


@router.delete("/users/{uid}")
def delete_user(uid: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    u = db.get(User, uid)
    if not u:
        raise HTTPException(status_code=404, detail="用户不存在")
    if u.is_admin:
        raise HTTPException(status_code=400, detail="不可删除管理员")
    db.delete(u)
    db.add(AuditLog(actor=admin.username, action="user.delete", detail=f"username={u.username}"))
    db.commit()
    return {"ok": True}


class KeyIn(BaseModel):
    api_key: str = Field(min_length=10)


def _get_setting(db: Session) -> AppSetting:
    s = db.get(AppSetting, 1)
    if not s:
        s = AppSetting(id=1)
        db.add(s)
        db.commit()
        db.refresh(s)
    return s


@router.get("/settings/openrouter-key")
def get_key_status(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    s = _get_setting(db)
    return {
        "configured": bool(s.or_key_ciphertext),
        "masked": s.or_key_masked,
        "fingerprint": s.or_key_fingerprint,
        "updated_by": s.updated_by,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


@router.put("/settings/openrouter-key")
def set_key(body: KeyIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    key = body.api_key.strip()
    ct, nonce = encrypt_api_key(key)
    s = _get_setting(db)
    s.or_key_ciphertext = ct
    s.or_key_nonce = nonce
    s.or_key_fingerprint = fingerprint(key)
    s.or_key_masked = masked(key)
    s.updated_by = admin.username
    from datetime import datetime, timezone

    s.updated_at = datetime.now(timezone.utc)
    db.add(AuditLog(actor=admin.username, action="key.rotate", detail=f"fp={s.or_key_fingerprint}"))
    # Key 已换：模型/余额/端点缓存全部失效，下次访问自动回源重刷
    #（直接删 server_cache 行，避免与 openrouter 路由模块循环引用）
    for rec in db.query(ServerCache).filter(ServerCache.key.startswith("openrouter.")).all():
        db.delete(rec)
    db.commit()
    return {"ok": True, "masked": s.or_key_masked, "fingerprint": s.or_key_fingerprint}


def load_openrouter_key_plaintext(db: Session) -> str:
    """仅服务端内存解密，绝不返回给前端。"""
    s = db.get(AppSetting, 1)
    if not s or not s.or_key_ciphertext:
        raise HTTPException(status_code=400, detail="管理员尚未配置 OpenRouter Key")
    assert s.or_key_nonce
    return decrypt_api_key(s.or_key_ciphertext, s.or_key_nonce)
