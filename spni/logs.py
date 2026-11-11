"""Application log file (for support: what failed on the examiner's machine)."""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from . import APP_NAME, __version__

_path: Path | None = None


def default_dir() -> Path:
    return Path(os.environ.get("APPDATA") or Path.home()) / APP_NAME / "logs"


def setup(folder: Path | None = None) -> Path | None:
    """Write warnings and errors (and a start line) to ``app.log``; 3 × 1 MB."""
    global _path
    folder = folder or default_dir()
    try:
        folder.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(folder / "app.log", maxBytes=1 << 20, backupCount=3, encoding="utf-8")
    except OSError:
        return None
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger("spni")
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    _path = folder / "app.log"
    root.info("%s v%s started", APP_NAME, __version__)
    return _path


def path() -> Path | None:
    return _path
