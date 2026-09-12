"""图片处理：AVIF/HEIC 注册解码 + 缩略图 + Firefox 等旧客户端兜底图。

向后兼容策略（服务端转换）：
- 上传时原图原样保存；若为 AVIF/HEIC（4:4:4 等高压缩），额外预生成
  fallback JPEG（4:2:0，最高兼容）与 thumb WebP（列表用）。
- 对外服务时按请求头协商：Accept 不含 image/avif，或 UA 命中
  Firefox/旧 Safari，或显式 ?compat=1，则返回 fallback JPEG。
  这样 <img src> 在任何浏览器都可显示，无需前端转码。
"""
from __future__ import annotations

import io
import os

try:
    import pillow_avif  # noqa: F401  # 注册 AVIF 编解码
except Exception:
    pass
try:
    from pillow_heif import register_heif_opener  # type: ignore

    register_heif_opener()
except Exception:
    pass

from PIL import Image

ALLOWED_EXTS = {".png", ".jpg", ".jpeg", ".jpe", ".jfif", ".webp", ".gif", ".bmp",
                ".tif", ".tiff", ".svg", ".avif", ".heic", ".heif"}
MIME_BY_EXT = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".jpe": "image/jpeg", ".jfif": "image/jpeg",
    ".webp": "image/webp", ".gif": "image/gif", ".bmp": "image/bmp",
    ".tif": "image/tiff", ".tiff": "image/tiff",
    ".svg": "image/svg+xml", ".avif": "image/avif",
    ".heic": "image/heic", ".heif": "image/heif",
}
# Pillow 能解码且我们接受的格式（用于无后缀/错后缀时按内容识别）
SUPPORTED_PIL_FORMATS = {"PNG", "JPEG", "JPG", "MPO", "WEBP", "GIF", "BMP",
                         "TIFF", "AVIF", "HEIC", "HEIF"}
EXT_BY_PIL_FORMAT = {
    "PNG": ".png", "JPEG": ".jpg", "JPG": ".jpg", "MPO": ".jpg",
    "WEBP": ".webp", "GIF": ".gif", "BMP": ".bmp", "TIFF": ".tiff",
    "AVIF": ".avif", "HEIC": ".heic", "HEIF": ".heif",
}

# UA 命中即视为“可能不支持 4:4:4 AVIF”，服务端降级
LEGACY_UA_MARKERS = ("Firefox/", "MSIE", "Trident/")


def guess_mime(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    return MIME_BY_EXT.get(ext, "application/octet-stream")


def is_modern_lossless_avif_needed(mime: str) -> bool:
    return mime in ("image/avif", "image/heic", "image/heif")


def needs_compat_fallback(accept: str, ua: str, force: bool = False) -> bool:
    if force:
        return True
    if accept and "image/avif" not in accept and "image/*" not in accept and "*/*" not in accept:
        # 某些旧 UA 的 Accept 明确不含 avif
        return True
    return any(m in ua for m in LEGACY_UA_MARKERS)


def make_thumb(src: str, dst: str, size: int = 512) -> None:
    if src.lower().endswith(".svg"):
        return
    with Image.open(src) as im:
        im.thumbnail((size, size))
        if im.mode in ("RGBA", "LA"):
            bg = Image.new("RGB", im.size, (255, 255, 255))
            bg.paste(im, mask=im.split()[-1])
            im = bg
        elif im.mode != "RGB":
            im = im.convert("RGB")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        im.save(dst, "WEBP", quality=80)


def make_jpeg_fallback(src: str, dst: str, quality: int = 88) -> None:
    """AVIF(4:4:4) -> JPEG(4:2:0)：最大兼容，Firefox/旧浏览器可用。"""
    with Image.open(src) as im:
        if im.mode in ("RGBA", "LA"):
            bg = Image.new("RGB", im.size, (255, 255, 255))
            bg.paste(im, mask=im.split()[-1])
            im = bg
        elif im.mode != "RGB":
            im = im.convert("RGB")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        im.save(dst, "JPEG", quality=quality, subsampling=1)  # 4:2:0


def sniff_mime(path: str, filename: str) -> str:
    try:
        with Image.open(path) as im:
            fmt = (im.format or "").upper()
            if fmt == "AVIF":
                return "image/avif"
            if fmt in ("HEIC", "HEIF"):
                return "image/heic"
            if fmt == "PNG":
                return "image/png"
            if fmt in ("JPEG", "JPG", "MPO"):
                return "image/jpeg"
            if fmt == "WEBP":
                return "image/webp"
            if fmt == "GIF":
                return "image/gif"
            if fmt == "BMP":
                return "image/bmp"
            if fmt == "TIFF":
                return "image/tiff"
    except Exception:
        pass
    if path.lower().endswith(".svg") or filename.lower().endswith(".svg"):
        return "image/svg+xml"
    return guess_mime(filename)


def resolve_image_ext(path: str, filename: str) -> str | None:
    """按“后缀优先、内容兜底”确定文件后缀。

    返回合法后缀（如 .jpg），无法识别为受支持图片时返回 None。
    覆盖场景：无后缀、错后缀（.jfif 已在白名单）、.DS_Store 之类杂文件。
    """
    ext = os.path.splitext(filename)[1].lower()
    if ext in ALLOWED_EXTS:
        return ext
    if filename.lower().endswith(".svg") or ext == ".svg":
        return ".svg"
    try:
        with Image.open(path) as im:
            fmt = (im.format or "").upper()
            if fmt in SUPPORTED_PIL_FORMATS:
                return EXT_BY_PIL_FORMAT[fmt]
    except Exception:
        pass
    return None
