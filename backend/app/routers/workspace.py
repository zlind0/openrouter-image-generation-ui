"""工作区草稿：每用户一行 JSON（生成页 prompt/模型/参数/参考图 + 素材库筛选滚动），
前端防抖自动 PUT，刷新/换机不丢失。点历史还原前工作区会先快照成一条历史。"""
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..deps import get_current_user
from ..models import User, WorkspaceDraft

router = APIRouter(prefix="/api/workspace", tags=["workspace"])


class DraftPut(BaseModel):
    generate: dict | None = None
    library: dict | None = None


def _load(db: Session, user_id: str) -> dict:
    rec = db.get(WorkspaceDraft, user_id)
    if not rec or not rec.data_json:
        return {}
    try:
        d = json.loads(rec.data_json)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


@router.get("/draft")
def get_draft(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    d = _load(db, user.id)
    return {"generate": d.get("generate"), "library": d.get("library")}


@router.put("/draft")
def put_draft(body: DraftPut, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    d = _load(db, user.id)
    if body.generate is not None:
        d["generate"] = body.generate
    if body.library is not None:
        d["library"] = body.library
    # 单行兜底：超大 dataUrl（如未入库粘贴图）截断，防止行无限膨胀
    try:
        raw = json.dumps(d)
    except Exception:
        d = {}
        raw = "{}"
    if len(raw) > 2_000_000:
        g = d.get("generate")
        if isinstance(g, dict) and isinstance(g.get("references"), list):
            for r in g["references"]:
                if isinstance(r, dict) and isinstance(r.get("dataUrl"), str) and len(r["dataUrl"]) > 200_000:
                    r["dataUrl"] = ""
        raw = json.dumps(d)
    rec = db.get(WorkspaceDraft, user.id)
    now = datetime.now(timezone.utc)
    if rec:
        rec.data_json = raw
        rec.updated_at = now
    else:
        rec = WorkspaceDraft(user_id=user.id, data_json=raw, updated_at=now)
    db.add(rec)
    db.commit()
    return {"ok": True}
