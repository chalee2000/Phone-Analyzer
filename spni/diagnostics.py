"""Connection self-checks shown in the "connection diagnostics" window."""

from __future__ import annotations

import re
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


def check(id_: str, status: str, detail: str = "", fix: str = "") -> dict[str, Any]:
    out = {"id": id_, "status": status, "detail": detail}
    if fix:
        out["fix"] = fix  # an action the dialog offers as a button
    return out


# The service of iTunes / the Apple Devices app; the Store package may register the short name.
APPLE_SERVICES = ("Apple Mobile Device Service", "AppleMobileDeviceService")
APPLE_VID = "VID_05AC"  # Apple's USB vendor id
APPLE_DEVICES_MIN_BUILD = 19045  # the Store's Apple Devices app needs Windows 10 22H2 or later
ITUNES_URL = "https://www.apple.com/itunes/download/win64"  # iTunes from Apple: also for older Windows 10


def windows_build() -> int:
    try:
        return int(sys.getwindowsversion().build)  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        return 0


def apple_service_state(sc_output: str) -> str:
    """``sc query`` output → running | stopped | missing | unknown (numbers only: Windows may be in Thai)."""
    if re.search(r"\b1060\b", sc_output):
        return "missing"
    # The label ("STATE") is translated on some Windows languages; the state names are not.
    m = re.search(r"\b(\d)\s+(STOPPED|START_PENDING|STOP_PENDING|RUNNING|CONTINUE_PENDING|PAUSE_PENDING|PAUSED)\b", sc_output)
    if not m:
        return "unknown"
    return {"RUNNING": "running", "START_PENDING": "starting", "CONTINUE_PENDING": "starting"}.get(m.group(2), "stopped")


def query_apple_service() -> tuple[str, str]:
    """(state, service name) of the first Apple service name Windows knows."""
    state = "unknown"
    for name in APPLE_SERVICES:
        state = apple_service_state(_run(["sc", "query", name]))
        if state != "missing":
            return state, name
    return state, APPLE_SERVICES[0]


def apple_usb_seen(pnputil_output: str) -> bool | None:
    """Does Windows list an Apple USB device? None when pnputil gave no device list (old Windows)."""
    if "VID_" not in pnputil_output.upper() and "USB\\" not in pnputil_output.upper():
        return None
    return APPLE_VID in pnputil_output.upper()


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
        seen = apple_usb_seen(_run(["pnputil", "/enum-devices", "/connected"], timeout=15))
        if seen is not None:  # first: does Windows see the iPhone on the cable at all?
            out.append(check("apple_usb", "ok") if seen else check("apple_usb_missing", "fail"))
        state, name = query_apple_service()
        if state in ("running", "starting"):
            out.append(check("apple_service", "ok", name))
        elif state == "missing":
            build = windows_build()
            if build and build < APPLE_DEVICES_MIN_BUILD:  # the Store refuses Apple Devices here: iTunes from apple.com
                out.append(check("apple_service_missing", "fail", f"Windows build {build}", fix="install_itunes"))
            else:
                out.append(check("apple_service_missing", "fail", fix="install_apple_devices"))
        elif state == "stopped":
            out.append(check("apple_service_stopped", "warn", name, fix="start_apple_service"))
        else:
            out.append(check("apple_service", "fail"))
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
