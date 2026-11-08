"""SPNI helper app ("agent") for Android 10+ devices.

When the system providers refuse ``content query`` for the shell user, the
examiner may allow a temporary helper app. The flow is fully logged:

1. push ``spni-agent.apk`` to ``/data/local/tmp`` and ``pm install -r -g``
   (``-g`` grants the runtime permissions declared in the manifest)
2. ``pm grant`` each permission again (some ROMs ignore ``-g``)
3. start ``ExportActivity``; it writes JSON files and ``done.json`` into the
   app's external files folder. If a permission is still missing, the phone
   shows Android's own permission prompt for the examiner to accept.
4. pull the JSON files, then ``pm uninstall`` the helper app, which also
   deletes its exported files from the device.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from ..extract import ExtractionContext
from ..models import CallRecord, Contact, SmsMessage
from ..util import normalize_phone, unix_to_ms
from .adb import Transport

PACKAGE = "th.spni.agent"
ACTIVITY = f"{PACKAGE}/.ExportActivity"
REMOTE_APK = "/data/local/tmp/spni-agent.apk"
EXPORT_DIR = f"/sdcard/Android/data/{PACKAGE}/files/export"
PERMISSIONS = [
    "android.permission.READ_CONTACTS",
    "android.permission.READ_CALL_LOG",
    "android.permission.READ_SMS",
    "android.permission.READ_PHONE_STATE",
]
FILES = {"contacts": "contacts.json", "calls": "calls.json", "sms": "sms.json"}
CALL_TYPES = {1: "incoming", 2: "outgoing", 3: "missed", 4: "voicemail", 5: "rejected", 6: "blocked", 7: "incoming"}


class AgentError(Exception):
    pass


def _explain_install_error(output: str) -> str:
    if "INSTALL_FAILED_USER_RESTRICTED" in output:
        return "install_blocked_xiaomi"  # MIUI/HyperOS: enable "Install via USB"
    if "INSTALL_FAILED_VERIFICATION_FAILURE" in output or "Auto Blocker" in output:
        return "install_blocked_auto_blocker"  # Samsung Auto Blocker
    return output.strip()[:200] or "install_failed"


def run_agent(t: Transport, apk: Path, ctx: ExtractionContext, kinds: list[str], timeout: float = 180) -> dict[str, Any]:
    ctx.stage("agent_install")
    ctx.audit("agent.install", f"{apk.name} → {PACKAGE} (examiner approved)")
    t.push(apk, REMOTE_APK)
    out = t.shell(f"pm install -r -g {REMOTE_APK}", timeout=120)
    t.shell(f"rm -f {REMOTE_APK}")
    if "Success" not in out:
        raise AgentError(_explain_install_error(out))
    try:
        for perm in PERMISSIONS:
            t.shell(f"pm grant {PACKAGE} {perm} 2>/dev/null")
        t.shell(f"appops set {PACKAGE} READ_SMS allow 2>/dev/null")
        t.shell(f"rm -rf {EXPORT_DIR}")
        ctx.stage("agent_waiting")
        t.shell(f"am start -W -n {ACTIVITY} --es kinds {','.join(kinds)}", timeout=60)
        deadline = time.monotonic() + timeout
        while True:
            ctx.check_cancel()
            if "done.json" in t.shell(f"ls {EXPORT_DIR} 2>/dev/null", timeout=10):
                break
            if time.monotonic() > deadline:
                raise AgentError("agent_timeout")
            time.sleep(1.5)
        data: dict[str, Any] = {}
        raw_dir = ctx.extraction.raw_dir / "agent"
        for kind in [*kinds, "done"]:
            name = FILES.get(kind, f"{kind}.json")
            local = raw_dir / name
            try:
                t.pull(f"{EXPORT_DIR}/{name}", local)
            except Exception:
                continue
            ctx.register(local, f"{EXPORT_DIR}/{name}")
            try:
                payload = json.loads(local.read_text(encoding="utf-8"))
            except ValueError:
                continue
            if kind == "done":
                ctx.audit("agent.done", json.dumps(payload, ensure_ascii=False)[:500])
                continue
            if isinstance(payload, dict) and payload.get("error"):
                ctx.audit(f"agent.{kind}", f"error: {payload['error']}")
                continue
            data[kind] = payload
        return data
    finally:
        t.shell(f"pm uninstall {PACKAGE}", timeout=60)
        ctx.audit("agent.uninstall", PACKAGE)


def contacts_from_agent(items: list[dict[str, Any]]) -> list[Contact]:
    out = []
    for c in items:
        out.append(
            Contact(
                name=c.get("name") or "",
                phones=[p for p in c.get("phones", []) if p],
                emails=[e for e in c.get("emails", []) if e],
                organization=c.get("organization") or "",
                note=c.get("note") or "",
                account=c.get("account") or "",
                starred=bool(c.get("starred")),
            )
        )
    out.sort(key=lambda c: c.name)
    return out


def calls_from_agent(items: list[dict[str, Any]], names: dict[str, str]) -> list[CallRecord]:
    out = []
    for c in items:
        number = normalize_phone(c.get("number"))
        out.append(
            CallRecord(
                number=number,
                name=c.get("name") or names.get(number, ""),
                direction=CALL_TYPES.get(int(c.get("type") or 0), "unknown"),
                timestamp=unix_to_ms(c.get("date")),
                duration=int(c.get("duration") or 0),
                sim=f"SIM {c['subscription_id']}" if c.get("subscription_id") not in (None, "", "-1") else "",
                location=c.get("location") or "",
            )
        )
    out.sort(key=lambda c: c.timestamp or 0, reverse=True)
    return out


def sms_from_agent(items: list[dict[str, Any]], names: dict[str, str]) -> list[SmsMessage]:
    out = []
    for m in items:
        address = normalize_phone(m.get("address"))
        out.append(
            SmsMessage(
                address=address,
                body=m.get("body") or "",
                direction="out" if int(m.get("type") or 1) in (2, 4, 5, 6) else "in",
                timestamp=unix_to_ms(m.get("date")),
                thread=str(m.get("thread_id") or address),
                contact_name=names.get(address, ""),
                read=bool(m.get("read", 1)),
            )
        )
    out.sort(key=lambda m: m.timestamp or 0, reverse=True)
    return out
