import hashlib
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.config import ensure_jwt_secret, settings
from ..core.security import (
    create_access_token,
    new_refresh_token,
    verify_password,
)
from ..db.session import get_db
from ..deps import get_current_user
from ..models import RefreshToken, User

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str
    password: str


def _set_refresh_cookie(resp: Response, raw: str) -> None:
    resp.set_cookie(
        "refresh_token",
        raw,
        max_age=settings.refresh_token_days * 86400,
        httponly=True,
        secure=False,
        samesite="lax",
        path="/api/auth",
    )


@router.post("/login")
def login(body: LoginIn, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == body.username).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="账号已停用")
    access = create_access_token(user.id, user.is_admin, ensure_jwt_secret(), settings.access_token_minutes)
    raw = new_refresh_token()
    jti = hashlib.sha256(raw.encode()).hexdigest()
    db.add(
        RefreshToken(
            jti=jti,
            user_id=user.id,
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_days),
        )
    )
    db.commit()
    _set_refresh_cookie(response, raw)
    return {"access_token": access, "user": {"id": user.id, "username": user.username, "is_admin": user.is_admin}}


@router.post("/refresh")
def refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    raw = request.cookies.get("refresh_token", "")
    if not raw:
        raise HTTPException(status_code=401, detail="无 refresh 会话")
    jti = hashlib.sha256(raw.encode()).hexdigest()
    rec = db.get(RefreshToken, jti)
    now = datetime.now(timezone.utc)
    exp = rec.expires_at.replace(tzinfo=timezone.utc) if rec and rec.expires_at.tzinfo is None else (rec.expires_at if rec else now)
    if not rec or rec.revoked or exp < now:
        raise HTTPException(status_code=401, detail="会话已过期，请重新登录")
    user = db.get(User, rec.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="账号不可用")
    # 旋转：旧 jti 作废，发新 refresh
    rec.revoked = True
    access = create_access_token(user.id, user.is_admin, ensure_jwt_secret(), settings.access_token_minutes)
    raw2 = new_refresh_token()
    db.add(
        RefreshToken(
            jti=hashlib.sha256(raw2.encode()).hexdigest(),
            user_id=user.id,
            expires_at=now + timedelta(days=settings.refresh_token_days),
        )
    )
    db.commit()
    _set_refresh_cookie(response, raw2)
    return {"access_token": access}


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    raw = request.cookies.get("refresh_token", "")
    if raw:
        rec = db.get(RefreshToken, hashlib.sha256(raw.encode()).hexdigest())
        if rec:
            rec.revoked = True
            db.commit()
    response.delete_cookie("refresh_token", path="/api/auth")
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return {"id": user.id, "username": user.username, "is_admin": user.is_admin}


@router.get("/file-token")
def file_token(user: User = Depends(get_current_user)):
    """签发 30 分钟文件读取令牌，前端拼到 <img src>?token= 上。"""
    from ..core.security import create_file_token

    return {"token": create_file_token(user.id, ensure_jwt_secret()), "expires_in": 1800}
