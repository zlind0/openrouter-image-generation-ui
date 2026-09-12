"""EXIF 抽取：Pillow 主力，HEIC/AVIF 插件兜底，失败返回 {} 不阻断上传。"""
from __future__ import annotations

from PIL import Image
from PIL.ExifTags import TAGS


def extract_exif(path: str) -> dict:
    try:
        with Image.open(path) as im:
            info: dict = {
                "format": im.format,
                "width": im.width,
                "height": im.height,
                "mode": im.mode,
            }
            try:
                raw = im.getexif() or {}
                for k, v in raw.items():
                    name = TAGS.get(k, str(k))
                    if name in ("Make", "Model", "LensModel", "ISOSpeedRatings",
                                "FNumber", "FocalLength", "ExposureTime", "DateTimeOriginal",
                                "DateTime", "GPSInfo"):
                        info[name] = str(v)
            except Exception:
                pass
            return info
    except Exception:
        return {}
