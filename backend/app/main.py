import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .core.config import settings
from .db.session import SessionLocal, init_db
from .models import AuditLog, User
from .core.security import hash_password
from .routers import admin, assets, auth, openrouter, shares

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(openrouter.router)
app.include_router(assets.router)
app.include_router(shares.router)


@app.on_event("startup")
def startup():
    init_db()
    os.makedirs(settings.data_dir, exist_ok=True)
    # seed 单管理员（仅首次）
    db = SessionLocal()
    try:
        # 预置默认库「上传素材」，上传/入库无文件夹时归入此处
        try:
            from .routers.assets import ensure_default_folder

            ensure_default_folder(db)
        except Exception as e:
            print(f"[WARN] 默认文件夹预置失败: {e}")
        if not db.query(User).filter(User.is_admin.is_(True)).first():
            if not settings.admin_password:
                print("[WARN] 无管理员且 ADMIN_PASSWORD 未设置，暂不建号（设置后重启生效）")
            else:
                db.add(User(username=settings.admin_username, password_hash=hash_password(settings.admin_password), is_admin=True))
                db.add(AuditLog(actor="system", action="admin.seed", detail=f"username={settings.admin_username}"))
                db.commit()
                print(f"[OK] 已创建管理员 {settings.admin_username}")
    finally:
        db.close()


@app.get("/api/health")
def health():
    return {"ok": True}


# 生产：同源托管前端 dist（compose 构建时已拷入 /app/dist）
if os.path.isdir("/app/dist") or os.path.isdir("dist"):
    _d = "/app/dist" if os.path.isdir("/app/dist") else "dist"
    app.mount("/", StaticFiles(directory=_d, html=True), name="frontend")
