import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    JSON,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def uid() -> str:
    return uuid.uuid4().hex


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    jti: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class AppSetting(Base):
    """单行表 id=1：只存 OpenRouter Key 的密文+nonce+指纹，绝不明文。"""
    __tablename__ = "app_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    or_key_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    or_key_nonce: Mapped[str | None] = mapped_column(String(64), nullable=True)
    or_key_fingerprint: Mapped[str | None] = mapped_column(String(32), nullable=True)
    or_key_masked: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now())


class Folder(Base):
    __tablename__ = "folders"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(255))
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("folders.id", ondelete="CASCADE"), nullable=True, index=True)
    # 冗余全路径 "旅拍/京都"，方便筛选与展示
    path: Mapped[str] = mapped_column(String(1024), default="", index=True)
    created_by: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Asset(Base):
    __tablename__ = "assets"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    folder_id: Mapped[str | None] = mapped_column(ForeignKey("folders.id", ondelete="SET NULL"), nullable=True, index=True)
    filename: Mapped[str] = mapped_column(String(512))
    # 相对 data_dir 的路径，UUID 文件名防穿越
    stored_path: Mapped[str] = mapped_column(String(1024))
    thumb_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # AVIF/HEIC 向后兼容：预生成的 JPEG 兜底
    fallback_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    mime: Mapped[str] = mapped_column(String(128), index=True)
    size_bytes: Mapped[int] = mapped_column(Integer)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    exif: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="upload")  # upload|generate
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # 注：EXIF 筛选在 Python 侧过滤（小团队量级），故不在 JSON 列上建索引。
    # 之前这里的普通 btree 索引会导致 Postgres 启动建表直接失败，已删除。


class Tag(Base):
    __tablename__ = "tags"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)


class AssetTag(Base):
    __tablename__ = "asset_tags"
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True)
    tag_id: Mapped[str] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)


class AssetPin(Base):
    """素材置顶：独立表（免迁移），置顶者在任何排序下永远排最前，按置顶时间倒序。"""
    __tablename__ = "asset_pins"
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True)
    pinned_by: Mapped[str] = mapped_column(String(32))
    pinned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Generation(Base):
    """每次生成记账：共享 Key 下区分用户成本。"""
    __tablename__ = "generations"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    model: Mapped[str] = mapped_column(String(255))
    prompt: Mapped[str] = mapped_column(Text)
    cost: Mapped[float | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ShareLink(Base):
    """图床公开链接：token 即路径，revoke 即失效。"""
    __tablename__ = "share_links"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), index=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ShareView(Base):
    __tablename__ = "share_views"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    share_id: Mapped[str] = mapped_column(ForeignKey("share_links.id", ondelete="CASCADE"), index=True)
    ip: Mapped[str] = mapped_column(String(64))
    ua: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64), index=True)
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ServerCache(Base):
    """服务端缓存：OpenRouter 模型列表/余额/端点，24h TTL。
    GET 接口只读缓存（超期才回源，相当于每天最多自动刷一次），
    POST /refresh 接口强制回源。换 Key 时整组失效。"""
    __tablename__ = "server_cache"
    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value_json: Mapped[str] = mapped_column(Text, default="{}")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GenerationHistory(Base):
    """生成历史（服务端持久化，每用户最新 100 条）：
    点选还原 prompt/参数/provider/参考图；原图与缩略图落盘存放。"""
    __tablename__ = "generation_history"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    model: Mapped[str] = mapped_column(String(255))
    prompt: Mapped[str] = mapped_column(Text)
    params_json: Mapped[str] = mapped_column(Text, default="{}")
    provider_choice: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # 参考图：素材 asset id 列表（上传即自动入库，从库选择的本就是 asset）
    reference_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    # 生成图：相对 DATA_DIR 的原图路径列表，与 image_mimes_json 一一对应
    image_paths_json: Mapped[str] = mapped_column(Text, default="[]")
    image_mimes_json: Mapped[str] = mapped_column(Text, default="[]")
    usage_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    cost: Mapped[float | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
