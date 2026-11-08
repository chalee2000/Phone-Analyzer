"""ADB access: server management, device listing and a small transport API.

The extractors only talk to :class:`Transport`, so they can be tested with a
fake device that replays recorded output.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Callable, Protocol

ADB_HOST = "127.0.0.1"
ADB_PORT = 5037

_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW


class Transport(Protocol):
    serial: str

    def shell(self, cmd: str, timeout: float = 120) -> str: ...

    def pull(self, remote: str, local: Path) -> None: ...

    def push(self, local: Path, remote: str) -> None: ...


class AdbutilsTransport:
    """Transport backed by the adbutils client (talks to the local adb server)."""

    def __init__(self, device) -> None:  # device: adbutils.AdbDevice
        self.device = device
        self.serial = device.serial

    def shell(self, cmd: str, timeout: float = 120) -> str:
        return self.device.shell(cmd, timeout=timeout, encoding="utf-8")

    def pull(self, remote: str, local: Path) -> None:
        local.parent.mkdir(parents=True, exist_ok=True)
        self.device.sync.pull(remote, str(local))

    def push(self, local: Path, remote: str) -> None:
        self.device.sync.push(str(local), remote)


class AuditedTransport:
    """Wraps a transport and writes every command to the case audit log."""

    def __init__(self, inner: Transport, audit: Callable[[str, str], None]) -> None:
        self.inner = inner
        self.serial = inner.serial
        self._audit = audit

    def shell(self, cmd: str, timeout: float = 120) -> str:
        try:
            out = self.inner.shell(cmd, timeout=timeout)
        except Exception as exc:
            self._audit("adb.shell", f"{cmd}  → error: {exc}")
            raise
        self._audit("adb.shell", f"{cmd}  → {len(out)} chars")
        return out

    def pull(self, remote: str, local: Path) -> None:
        self.inner.pull(remote, local)
        self._audit("adb.pull", remote)

    def push(self, local: Path, remote: str) -> None:
        self.inner.push(local, remote)
        self._audit("adb.push", f"{local.name} → {remote}")


def adb_executable() -> str | None:
    """Path of the adb binary (bundled with adbutils, or on PATH)."""
    bundled = Path(getattr(sys, "_MEIPASS", "")) / "platform-tools" / ("adb.exe" if os.name == "nt" else "adb")
    if bundled.is_file():
        return str(bundled)
    try:
        from adbutils._utils import adb_path

        return adb_path()
    except Exception:
        return None


def _run_adb(*args: str, timeout: float = 20) -> subprocess.CompletedProcess | None:
    exe = adb_executable()
    if not exe:
        return None
    try:
        return subprocess.run(
            [exe, *args], capture_output=True, text=True, timeout=timeout, creationflags=_NO_WINDOW
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


class AdbManager:
    def __init__(self) -> None:
        self._client = None

    def client(self):
        if self._client is None:
            import adbutils

            self._client = adbutils.AdbClient(host=ADB_HOST, port=ADB_PORT, socket_timeout=15)
        return self._client

    def server_running(self) -> bool:
        try:
            self.client().server_version()
            return True
        except Exception:
            return False

    def ensure_server(self) -> bool:
        if self.server_running():
            return True
        _run_adb("start-server", timeout=30)
        return self.server_running()

    def restart_server(self) -> bool:
        try:
            self.client().server_kill()
        except Exception:
            _run_adb("kill-server")
        self._client = None
        _run_adb("start-server", timeout=30)
        return self.server_running()

    def status(self) -> dict:
        running = self.server_running()
        version = None
        if running:
            try:
                version = self.client().server_version()
            except Exception:
                pass
        return {"running": running, "version": version, "path": adb_executable()}

    def list_devices(self) -> list[dict]:
        """All devices known to the adb server, including unauthorized ones."""
        if not self.ensure_server():
            return []
        out = []
        try:
            infos = self.client().list(extended=True)
        except Exception:
            return []
        for info in infos:
            entry = {
                "id": f"android:{info.serial}",
                "platform": "android",
                "serial": info.serial,
                "state": {"device": "ready"}.get(info.state, info.state),
                "brand": "",
                "model": info.tags.get("model", "").replace("_", " "),
                "name": info.tags.get("device", ""),
            }
            if info.state == "device":
                try:
                    dev = self.client().device(info.serial)
                    entry["brand"] = dev.shell("getprop ro.product.brand", timeout=5).strip()
                    market = dev.shell("getprop ro.product.marketname", timeout=5).strip()
                    if market:
                        entry["model"] = market
                except Exception:
                    pass
            out.append(entry)
        return out

    def transport(self, serial: str) -> AdbutilsTransport:
        return AdbutilsTransport(self.client().device(serial))
