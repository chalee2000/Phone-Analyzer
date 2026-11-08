"""Small helpers shared by the Android and iOS extractors."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

# Seconds between the Unix epoch (1970) and the Apple/Cocoa epoch (2001-01-01).
COCOA_EPOCH_OFFSET = 978_307_200


def now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def iso_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def cocoa_to_ms(value: float | int | None) -> int | None:
    """Convert an Apple timestamp to Unix milliseconds.

    iOS stores some dates as seconds since 2001 (CallHistory, Safari) and, since
    iOS 11, others as *nanoseconds* since 2001 (sms.db). Both are handled.
    """
    if value is None or value == 0:
        return None
    value = float(value)
    if abs(value) > 1e14:  # nanoseconds
        value /= 1e9
    return int((value + COCOA_EPOCH_OFFSET) * 1000)


def unix_to_ms(value: float | int | str | None) -> int | None:
    """Accept seconds or milliseconds since 1970 and return milliseconds."""
    if value in (None, "", "NULL"):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    if value < 1e11:  # seconds
        value *= 1000
    return int(value)


_PHONE_STRIP = re.compile(r"[\s\-().]")


def normalize_phone(raw: str | None) -> str:
    """Normalise a phone number to the Thai domestic format where possible.

    ``+66 81-234-5678`` → ``0812345678``. Values that are not phone numbers
    (short codes, sender names such as ``AIS``) are returned trimmed but
    otherwise untouched so no evidence is lost.
    """
    if not raw:
        return ""
    value = str(raw).strip()
    compact = _PHONE_STRIP.sub("", value)
    if compact.startswith("tel:"):
        compact = compact[4:]
    if re.fullmatch(r"\+?66\d{8,9}", compact):
        return "0" + compact.lstrip("+")[2:]
    if re.fullmatch(r"\+?\d{6,15}", compact):
        return compact
    return value


def sha256_file(path: str | Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def safe_name(text: str, fallback: str = "item") -> str:
    """Make a string safe to use as a file or folder name on Windows."""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", text).strip(" .")
    return cleaned[:80] or fallback


def human_size(num: int | float | None) -> str:
    if num is None:
        return "-"
    num = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num < 1024 or unit == "TB":
            return f"{num:.0f} {unit}" if unit == "B" else f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} TB"
