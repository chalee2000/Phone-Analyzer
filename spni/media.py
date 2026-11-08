"""Image helpers: thumbnails and EXIF metadata (date, camera, GPS)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import ExifTags, Image, ImageOps

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".gif", ".bmp", ".dng"}
VIDEO_EXTS = {".mp4", ".mov", ".3gp", ".mkv", ".avi", ".m4v"}
AUDIO_EXTS = {".m4a", ".mp3", ".aac", ".amr", ".wav", ".ogg", ".opus", ".3ga"}

_GPS_TAG = next(k for k, v in ExifTags.TAGS.items() if v == "GPSInfo")

try:  # HEIC support is optional (pillow-heif)
    from pillow_heif import register_heif_opener  # type: ignore

    register_heif_opener()
except Exception:  # pragma: no cover - optional dependency
    pass


def _ratio(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError, ZeroDivisionError):
        try:
            num, den = value
            return float(num) / float(den)
        except Exception:
            return 0.0


def _dms_to_deg(dms: Any, ref: str) -> float | None:
    try:
        deg = _ratio(dms[0]) + _ratio(dms[1]) / 60 + _ratio(dms[2]) / 3600
    except Exception:
        return None
    if ref in ("S", "W"):
        deg = -deg
    return round(deg, 6)


def read_exif(path: Path) -> dict[str, Any]:
    """Return width/height, capture time (ms, device-local), camera and GPS."""
    out: dict[str, Any] = {}
    try:
        with Image.open(path) as img:
            out["width"], out["height"] = img.size
            exif = img.getexif()
            if not exif:
                return out
            tags = {ExifTags.TAGS.get(k, k): v for k, v in exif.items()}
            try:
                sub = exif.get_ifd(0x8769)  # Exif IFD (DateTimeOriginal lives here)
                tags.update({ExifTags.TAGS.get(k, k): v for k, v in sub.items()})
            except Exception:
                pass
            out["make"] = str(tags.get("Make", "") or "").strip("\x00 ")
            out["camera_model"] = str(tags.get("Model", "") or "").strip("\x00 ")
            stamp = tags.get("DateTimeOriginal") or tags.get("DateTime")
            if stamp:
                try:
                    dt = datetime.strptime(str(stamp).strip("\x00 "), "%Y:%m:%d %H:%M:%S")
                    out["taken"] = int(dt.timestamp() * 1000)
                except ValueError:
                    pass
            try:
                gps = exif.get_ifd(_GPS_TAG)
            except Exception:
                gps = None
            if gps:
                lat = _dms_to_deg(gps.get(2), str(gps.get(1, "N")))
                lon = _dms_to_deg(gps.get(4), str(gps.get(3, "E")))
                if lat is not None and lon is not None and (lat or lon):
                    out["lat"], out["lon"] = lat, lon
    except Exception:
        pass
    return out


def make_thumbnail(src: Path, dst: Path, size: int = 360) -> bool:
    try:
        with Image.open(src) as img:
            img = ImageOps.exif_transpose(img)
            img.thumbnail((size, size))
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            dst.parent.mkdir(parents=True, exist_ok=True)
            img.save(dst, "JPEG", quality=82)
        return True
    except Exception:
        return False
