import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ..core.config import settings
from ..models import Base


def _url() -> str:
    url = settings.database_url
    if url.startswith("sqlite"):
        os.makedirs("data", exist_ok=True)
    return url


connect_args = {"check_same_thread": False} if _url().startswith("sqlite") else {}
engine = create_engine(_url(), connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
