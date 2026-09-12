import os
import secrets
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "OR Image WebApp"
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./data/app.db")
    # 必须经环境变量注入，绝不进 git
    app_master_key_b64: str = os.getenv("APP_MASTER_KEY", "")
    jwt_secret: str = os.getenv("JWT_SECRET", "")
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    admin_username: str = os.getenv("ADMIN_USERNAME", "admin")
    admin_password: str = os.getenv("ADMIN_PASSWORD", "")
    data_dir: str = os.getenv("DATA_DIR", "./data/uploads")
    max_upload_mb: int = 50
    # OpenRouter 透传
    openrouter_base: str = os.getenv("OPENROUTER_BASE", "https://openrouter.ai/api/v1")

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()


def ensure_master_key() -> bytes:
    """APP_MASTER_KEY 必须是 32 字节 base64。缺失则拒绝启动，避免明文回退。"""
    if not settings.app_master_key_b64:
        raise RuntimeError("APP_MASTER_KEY 未设置：请执行 openssl rand -base64 32 写入 .env")
    import base64

    raw = base64.b64decode(settings.app_master_key_b64)
    if len(raw) != 32:
        raise RuntimeError("APP_MASTER_KEY 必须解码为 32 字节")
    return raw


def ensure_jwt_secret() -> str:
    if not settings.jwt_secret or len(settings.jwt_secret) < 32:
        raise RuntimeError("JWT_SECRET 未设置或太短（>=32字符），请用 openssl rand -hex 32 生成")
    return settings.jwt_secret
