from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .core.config import ensure_jwt_secret
from .core.security import decode_access_token, decode_file_token
from .db.session import get_db
from .models import User

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if not creds:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    try:
        payload = decode_access_token(creds.credentials, ensure_jwt_secret())
        uid = payload.get("sub", "")
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已过期")
    user = db.get(User, uid)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号不可用")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="仅管理员可操作")
    return user


def get_file_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    token: str | None = Query(None, description="文件读取专用 token（供 <img> 携带）"),
    db: Session = Depends(get_db),
) -> User:
    """图片 serving 专用鉴权：<img> 发不出 Authorization 头，故额外接受 ?token= 文件令牌。

    - Authorization Bearer：复用 access token（无 aud）
    - ?token=：必须是 aud=files 的文件令牌，只能读图，调其他接口无效
    """
    uid = ""
    if creds:
        try:
            uid = decode_access_token(creds.credentials, ensure_jwt_secret()).get("sub", "")
        except Exception:
            pass
    if not uid and token:
        try:
            uid = decode_file_token(token, ensure_jwt_secret()).get("sub", "")
        except Exception:
            pass
    if not uid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    user = db.get(User, uid)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号不可用")
    return user


def can_manage_asset(user: User, owner_id: str) -> bool:
    return user.is_admin or user.id == owner_id
