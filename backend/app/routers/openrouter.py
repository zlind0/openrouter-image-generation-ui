"""OpenRouter 代理：前端不再接触 Key，全部经服务端注入解密后的 Key 转发。

模型列表 / 余额 / 端点走服务端缓存（server_cache，TTL 24h）：
- GET 接口只读缓存，超期才回源（每天最多自动刷一次）；
- POST /refresh 接口强制回源，供前端手动刷新按钮调用；
- 管理员轮换 Key 时整组缓存失效。
"""
import json
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.config import settings
from ..db.session import get_db
from ..deps import get_current_user
from ..models import Generation, ServerCache, User
from .admin import load_openrouter_key_plaintext

router = APIRouter(prefix="/api/openrouter", tags=["openrouter"])

HEADERS = {"HTTP-Referer": "https://localhost/or-webapp", "X-Title": "OR Image WebApp"}

CACHE_TTL = 86400  # 24h：每天最多自动回源一次
MODELS_KEY = "openrouter.models"
KEYINFO_KEY = "openrouter.keyinfo"
EP_KEY_PREFIX = "openrouter.endpoints:"


def _h(key: str) -> dict:
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json", **HEADERS}


def _age_seconds(updated_at) -> float:
    if not updated_at:
        return float("inf")
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - updated_at).total_seconds()


def _cache_get(db: Session, key: str):
    """返回 (value, fresh, cached_at_iso)。无缓存返回 (None, False, None)。"""
    rec = db.get(ServerCache, key)
    if not rec or not rec.value_json:
        return None, False, None
    try:
        value = json.loads(rec.value_json)
    except Exception:
        return None, False, None
    fresh = _age_seconds(rec.updated_at) < CACHE_TTL
    try:
        cached_at = rec.updated_at.isoformat() if rec.updated_at else None
    except Exception:
        cached_at = None
    return value, fresh, cached_at


def _cache_set(db: Session, key: str, value: dict) -> None:
    rec = db.get(ServerCache, key)
    now = datetime.now(timezone.utc)
    if rec:
        rec.value_json = json.dumps(value)
        rec.updated_at = now
    else:
        rec = ServerCache(key=key, value_json=json.dumps(value), updated_at=now)
    db.add(rec)
    db.commit()


def invalidate_openrouter_cache(db: Session) -> None:
    for rec in db.query(ServerCache).filter(ServerCache.key.startswith("openrouter.")).all():
        db.delete(rec)
    db.commit()


def _fetch_json(api_key: str, path: str, timeout: int = 30) -> dict:
    try:
        r = httpx.get(f"{settings.openrouter_base}{path}", headers=_h(api_key), timeout=timeout)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"上游连接失败: {e}")
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text[:500])
    return r.json()


def _cached_or_fetch(db: Session, cache_key: str, api_key: str, path: str, timeout: int = 30, force: bool = False) -> dict:
    value, fresh, cached_at = _cache_get(db, cache_key)
    if not force and fresh and value is not None:
        data = dict(value)
        data["cached_at"] = cached_at
        data["cached"] = True
        return data
    data = _fetch_json(api_key, path, timeout)
    _cache_set(db, cache_key, data)
    data = dict(data)
    data["cached"] = False
    return data


@router.get("/models")
def proxy_models(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    key = load_openrouter_key_plaintext(db)
    return _cached_or_fetch(db, MODELS_KEY, key, "/images/models")


@router.post("/models/refresh")
def refresh_models(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    key = load_openrouter_key_plaintext(db)
    return _cached_or_fetch(db, MODELS_KEY, key, "/images/models", force=True)


@router.get("/models/{author}/{slug}/endpoints")
def proxy_endpoints(author: str, slug: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    key = load_openrouter_key_plaintext(db)
    return _cached_or_fetch(db, f"{EP_KEY_PREFIX}{author}/{slug}", key, f"/images/models/{author}/{slug}/endpoints")


@router.post("/models/{author}/{slug}/endpoints/refresh")
def refresh_endpoints(author: str, slug: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    key = load_openrouter_key_plaintext(db)
    return _cached_or_fetch(db, f"{EP_KEY_PREFIX}{author}/{slug}", key, f"/images/models/{author}/{slug}/endpoints", force=True)


class GenIn(BaseModel):
    model: str
    prompt: str
    save_to_library: bool = False
    folder_id: str | None = None
    params: dict = {}


@router.post("/images")
def proxy_generate(body: GenIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    key = load_openrouter_key_plaintext(db)
    payload = {"model": body.model, "prompt": body.prompt, "user": user.id, **(body.params or {})}
    try:
        r = httpx.post(f"{settings.openrouter_base}/images", headers=_h(key), json=payload, timeout=300)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"上游连接失败: {e}")
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text[:1000])
    data = r.json()
    try:
        usage = data.get("usage") or {}
        db.add(Generation(user_id=user.id, model=body.model, prompt=body.prompt[:2000], cost=usage.get("cost")))
        db.commit()
    except Exception:
        pass
    # save_to_library 由前端随后调 /api/assets/from-generation，或此处直接存：
    # 为保持简单，此处只返回；前端拿到 b64 后若勾选则 POST /api/assets/from-generation
    return data


@router.post("/images/stream")
def proxy_generate_stream(body: GenIn, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    key = load_openrouter_key_plaintext(db)
    payload = {"model": body.model, "prompt": body.prompt, "user": user.id, "stream": True, **(body.params or {})}

    def gen():
        try:
            with httpx.stream("POST", f"{settings.openrouter_base}/images", headers=_h(key), json=payload, timeout=300) as r:
                if r.status_code != 200:
                    yield f"data: {json.dumps({'type': 'error', 'error': {'message': r.read().decode()[:500]}})}\n\n"
                    return
                for line in r.iter_lines():
                    if line is None:
                        continue
                    t = line.strip() if isinstance(line, str) else line.decode().strip()
                    if not t:
                        continue
                    if t.startswith(":"):
                        continue
                    if t.startswith("data:"):
                        yield t + "\n\n"
                    else:
                        yield f"data: {t}\n\n"
                yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': {'message': str(e)}})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.get("/key")
def proxy_key_info(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    key = load_openrouter_key_plaintext(db)
    return _cached_or_fetch(db, KEYINFO_KEY, key, "/key", timeout=15)


@router.post("/key/refresh")
def refresh_key_info(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    key = load_openrouter_key_plaintext(db)
    return _cached_or_fetch(db, KEYINFO_KEY, key, "/key", timeout=15, force=True)
