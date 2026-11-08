"""Locate bundled resources both from source and inside a PyInstaller build."""

from __future__ import annotations

import sys
from pathlib import Path


def base_dir() -> Path:
    frozen = getattr(sys, "_MEIPASS", None)
    if frozen:
        return Path(frozen)
    return Path(__file__).resolve().parent.parent


def resource(*parts: str) -> Path:
    return base_dir().joinpath("resources", *parts)


def frontend_dist() -> Path:
    return base_dir() / "frontend" / "dist"


def agent_apk() -> Path:
    return resource("agent", "spni-agent.apk")


def font(name: str) -> Path:
    return resource("fonts", name)
