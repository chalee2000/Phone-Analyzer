"""Connection self-checks shown in the "connection diagnostics" window."""

from __future__ import annotations

import subprocess
import sys
from typing import Any

from .android.adb import AdbManager

_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def _run(cmd: list[str], timeout: float = 8) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, creationflags=_NO_WINDOW).stdout
    except Exception:
        return ""


def check(id_: str, status: str, detail: str = "") -> dict[str, Any]:
    return {"id": id_, "status": status, "detail": detail}


def android_checks(adb: AdbManager) -> list[dict[str, Any]]:
    out = []
    running = adb.ensure_server()
    st = adb.status()
    out.append(check("adb_server", "ok" if running else "fail", f"adb {st.get('version') or ''} · {st.get('path') or '-'}"))
    devices = adb.list_devices() if running else []
    states = {d["state"] for d in devices}
    if "ready" in states:
        out.append(check("device_seen", "ok", ", ".join(d["model"] or d["serial"] for d in devices if d["state"] == "ready")))
    elif "unauthorized" in states:
        out.append(check("device_unauthorized", "warn"))
    elif "offline" in states:
        out.append(check("device_offline", "warn"))
    else:
        out.append(check("device_seen", "fail"))
    if sys.platform == "win32" and "ready" not in states:
        listing = _run(["pnputil", "/enum-devices", "/connected", "/class", "AndroidUsbDeviceClass"])
        out.append(check("usb_driver", "ok" if "Instance ID" in listing else "warn"))
    return out


def ios_checks() -> list[dict[str, Any]]:
    from .ios import device

    out = []
    if sys.platform == "win32":
        svc = _run(["sc", "query", "Apple Mobile Device Service"])
        out.append(check("apple_service", "ok" if "RUNNING" in svc else "fail"))
    reachable = device.usbmux_available()
    out.append(check("usbmux", "ok" if reachable else "fail"))
    devices = device.list_devices() if reachable else []
    states = {d["state"] for d in devices}
    if "ready" in states:
        out.append(check("device_seen", "ok", ", ".join(d["model"] for d in devices if d["state"] == "ready")))
    elif "not_trusted" in states:
        out.append(check("device_not_trusted", "warn"))
    elif "locked" in states:
        out.append(check("device_locked", "warn"))
    elif "error" in states:
        out.append(check("device_error", "fail", "; ".join(d.get("detail", "") for d in devices if d["state"] == "error")))
    else:
        out.append(check("device_seen", "fail"))
    return out
