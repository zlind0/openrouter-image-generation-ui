"""Argon2id 密码哈希 + JWT(access) + 不透明 refresh(token jti 存库可吊销)。"""
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher

_ph = PasswordHasher()  # 默认即 Argon2id，OWASP 推荐参数


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, pw)
    except Exception:
        return False


def create_access_token(user_id: str, is_admin: bool, secret: str, minutes: int = 15) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": user_id, "admin": is_admin, "aud": "api", "iat": now, "exp": now + timedelta(minutes=minutes)},
        secret,
        algorithm="HS256",
    )


def decode_access_token(token: str, secret: str) -> dict:
    return jwt.decode(token, secret, algorithms=["HS256"], audience="api")


def create_file_token(user_id: str, secret: str, minutes: int = 30) -> str:
    """文件读取专用 token：作用域仅限 /file /thumb（aud=files），供 <img> URL 携带。"""
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": user_id, "aud": "files", "iat": now, "exp": now + timedelta(minutes=minutes)},
        secret,
        algorithm="HS256",
    )


def decode_file_token(token: str, secret: str) -> dict:
    return jwt.decode(token, secret, algorithms=["HS256"], audience="files")


def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)
