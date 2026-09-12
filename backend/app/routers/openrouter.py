"""OpenRouter 代理：前端不再接触 Key，全部经服务端注入解密后的 Key 转发。"""
import json

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.config import settings
from ..db.session import get_db
from ..deps import get_current_user
from ..models import Generation, User
from .admin import load_openrouter_key_plaintext

router = APIRouter(prefix="/api/openrouter", tags=["openrouter"])

HEADERS = {"HTTP-Referer": "https://localhost/or-webapp", "X-Title": "OR Image WebApp"}


def _h(key: str) -> dict:
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json", **HEADERS}


@router.get("/models")
def proxy_models(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    key = load_openrouter_key_plaintext(db)
    try:
        r = httpx.get(f"{settings.openrouter_base}/images/models", headers=_h(key), timeout=30)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"上游连接失败: {e}")
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text[:500])
    return r.json()


@router.get("/models/{author}/{slug}/endpoints")
def proxy_endpoints(author: str, slug: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    key = load_openrouter_key_plaintext(db)
    try:
        r = httpx.get(f"{settings.openrouter_base}/images/models/{author}/{slug}/endpoints", headers=_h(key), timeout=30)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"上游连接失败: {e}")
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text[:500])
    return r.json()


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
    try:
        r = httpx.get(f"{settings.openrouter_base}/key", headers=_h(key), timeout=15)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"上游连接失败: {e}")
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text[:500])
    return r.json()
