"""Logical extraction from Android over ADB (no root required).

Strategy per category:

* calls / contacts / SMS — ``content query`` against the system providers.
  Android 10+ (and MIUI/HyperOS in particular) often refuses this for the
  shell user; those categories then fall back to the SPNI helper app
  (:mod:`spni.android.agent`) when the examiner allowed it.
* apps — ``dumpsys package packages``
* Wi-Fi — ``cmd wifi list-networks`` (Android 11+) or ``dumpsys wifi``
* SIM — ``content://telephony/siminfo`` (every SIM ever inserted) or getprop
* photos / voice recordings — ``find`` + ``adb pull`` with SHA-256 hashing
* chats / browser history / notes live in app-private storage and need root.
"""

from __future__ import annotations

import os
import re
import shlex
from pathlib import Path, PurePosixPath
from typing import Any

from ..extract import BaseExtractor, ExtractionContext
from ..media import AUDIO_EXTS, IMAGE_EXTS
from ..models import App, CallRecord, Contact, DeviceInfo, SimCard, SmsMessage, Unavailable, VoiceMemo, WifiNetwork
from ..util import normalize_phone, unix_to_ms
from . import agent as agent_mod
from .adb import AuditedTransport, Transport
from .content import ContentQueryError, as_int, build_query, parse_rows
from .info import parse_getprop, read_device_info

CALL_TYPES = {1: "incoming", 2: "outgoing", 3: "missed", 4: "voicemail", 5: "rejected", 6: "blocked", 7: "incoming"}
SMS_OUT_TYPES = {2, 4, 5, 6}

PHOTO_DIRS = ["/sdcard/DCIM", "/sdcard/Pictures"]
VOICE_DIRS = [
    "/sdcard/MIUI/sound_recorder",
    "/sdcard/Recordings",
    "/sdcard/Music/Recordings",
    "/sdcard/Sounds",
    "/sdcard/Recorder",
    "/sdcard/Call",
    "/sdcard/Record",
]

KNOWN_LABELS = {
    "jp.naver.line.android": "LINE",
    "com.facebook.katana": "Facebook",
    "com.facebook.orca": "Messenger",
    "com.whatsapp": "WhatsApp",
    "org.telegram.messenger": "Telegram",
    "com.zhiliaoapp.musically": "TikTok",
    "com.ss.android.ugc.trill": "TikTok",
    "com.instagram.android": "Instagram",
    "com.shopee.th": "Shopee",
    "com.lazada.android": "Lazada",
    "com.kasikorn.retail.mbanking.wap": "K PLUS",
    "com.scb.phone": "SCB EASY",
    "ktbcs.netbank": "Krungthai NEXT",
    "com.bbl.mobilebanking": "Bangkok Bank",
    "com.krungsri.kma": "KMA",
    "th.co.truemoney.wallet": "TrueMoney",
    "com.grabtaxi.passenger": "Grab",
    "com.linecorp.linemanth": "LINE MAN",
    "com.android.chrome": "Chrome",
    "com.google.android.youtube": "YouTube",
    "com.google.android.apps.maps": "Google Maps",
    "com.google.android.gm": "Gmail",
    "com.discord": "Discord",
    "com.viber.voip": "Viber",
    "com.tencent.mm": "WeChat",
    "com.bitkub": "Bitkub",
    "com.binance.dev": "Binance",
}


def find_files(t: Transport, dirs: list[str], exts: set[str]) -> list[tuple[str, int, int]]:
    """List files under ``dirs`` with the given extensions → (path, size, mtime seconds)."""
    names = " -o ".join(f"-iname '*{e}'" for e in sorted(exts))
    existing = " ".join(shlex.quote(d) for d in dirs)
    cmd = f"find {existing} -type f \\( {names} \\) -exec stat -c '%s|%Y|%n' {{}} + 2>/dev/null"
    out = t.shell(cmd, timeout=300)
    files = []
    for line in out.splitlines():
        parts = line.strip().split("|", 2)
        if len(parts) == 3 and parts[0].isdigit():
            files.append((parts[2], int(parts[0]), int(parts[1]) if parts[1].isdigit() else 0))
    return files


def parse_list_networks(output: str) -> list[WifiNetwork]:
    """``cmd wifi list-networks``: ``Network Id  SSID  Security type`` table."""
    nets = []
    lines = [ln for ln in output.splitlines() if ln.strip()]
    if not lines or not lines[0].lower().startswith("network id"):
        return nets
    for line in lines[1:]:
        m = re.match(r"^\s*(\d+)\s+(.*?)\s{2,}(\S+)\s*$", line)
        if m:
            nets.append(WifiNetwork(ssid=m[2].strip(), security=m[3].upper(), source="cmd wifi"))
        else:
            m = re.match(r"^\s*(\d+)\s+(.+?)\s*$", line)
            if m:
                nets.append(WifiNetwork(ssid=m[2], source="cmd wifi"))
    return nets


def parse_dumpsys_wifi(output: str) -> list[WifiNetwork]:
    seen: dict[str, WifiNetwork] = {}
    for m in re.finditer(r'SSID: "([^"]+)".*?(?:KeyMgmt: ([\w\- ]+?)(?: Protocols|\n|$))?', output):
        ssid = m[1]
        if ssid not in seen:
            seen[ssid] = WifiNetwork(ssid=ssid, security=(m[2] or "").strip(), source="dumpsys wifi")
    return list(seen.values())


def parse_dumpsys_packages(output: str) -> list[App]:
    apps: list[App] = []
    current: App | None = None
    for line in output.splitlines():
        m = re.match(r"^\s*Package \[([^\]]+)\]", line)
        if m:
            current = App(package=m[1], name=KNOWN_LABELS.get(m[1], ""))
            apps.append(current)
            continue
        if current is None:
            continue
        s = line.strip()
        if s.startswith("versionName="):
            current.version = s.split("=", 1)[1]
        elif s.startswith("firstInstallTime="):
            current.installed = _parse_pkg_time(s.split("=", 1)[1])
        elif s.startswith("lastUpdateTime="):
            current.updated = _parse_pkg_time(s.split("=", 1)[1])
        elif s.startswith("installerPackageName="):
            current.installer = s.split("=", 1)[1]
        elif s.startswith("pkgFlags=[") and " SYSTEM " in s + " ":
            current.system = True
    # dumpsys may list a package twice (hidden system + update); keep the first.
    unique: dict[str, App] = {}
    for app in apps:
        unique.setdefault(app.package, app)
    return list(unique.values())


def _parse_pkg_time(value: str) -> int | None:
    from datetime import datetime

    try:
        return int(datetime.strptime(value.strip(), "%Y-%m-%d %H:%M:%S").timestamp() * 1000)
    except ValueError:
        return None


class AndroidExtractor(BaseExtractor):
    platform = "android"
    method = "adb-logical"

    def __init__(self, transport: Transport, agent_apk: Path | None = None) -> None:
        self.raw = transport
        self.t: Transport = transport
        self.agent_apk = agent_apk
        self._contacts_by_number: dict[str, str] = {}

    def device_info(self) -> DeviceInfo:
        return read_device_info(self.raw)

    # ── main ─────────────────────────────────────────────────────────────
    def run(self, ctx: ExtractionContext) -> DeviceInfo | None:
        self.t = AuditedTransport(self.raw, ctx.audit)
        info = read_device_info(self.t)
        need_agent: list[str] = []

        for kind, fn in (("contacts", self.contacts), ("calls", self.calls), ("sms", self.sms)):
            if not ctx.wants(kind):
                continue
            ctx.begin(kind)
            try:
                ctx.save(kind, fn())
            except ContentQueryError as exc:
                ctx.audit(f"provider.{kind}", f"denied: {exc}")
                need_agent.append(kind)
                ctx.progress(kind, 0.1, message="provider_denied")

        if need_agent:
            self._run_agent(ctx, need_agent)

        for kind in ("chats", "web"):
            if ctx.wants(kind):
                ctx.begin(kind)
                ctx.unavailable(kind, Unavailable.REQUIRES_ROOT.value, "app-private storage (/data/data)")
        if ctx.wants("notes"):
            ctx.begin("notes")
            ctx.unavailable("notes", Unavailable.NOT_SUPPORTED.value, "no system notes provider on Android")

        for kind, fn in (("wifi", self.wifi), ("sim", self.sims), ("apps", self.apps)):
            if not ctx.wants(kind):
                continue
            ctx.begin(kind)
            try:
                ctx.save(kind, fn())
            except Exception as exc:  # keep going with the other categories
                ctx.error(kind, exc)

        if ctx.wants("voice"):
            ctx.begin("voice")
            try:
                ctx.save("voice", self.voice(ctx))
            except Exception as exc:
                ctx.error("voice", exc)
        if ctx.wants("photos"):
            ctx.begin("photos")
            try:
                ctx.save("photos", self.photos(ctx))
            except Exception as exc:
                ctx.error("photos", exc)
        return info

    def _run_agent(self, ctx: ExtractionContext, kinds: list[str]) -> None:
        if not ctx.options.get("android_allow_agent"):
            for kind in kinds:
                ctx.unavailable(kind, Unavailable.AGENT_DECLINED.value, "content provider denied; helper app not allowed")
            return
        if not self.agent_apk or not self.agent_apk.is_file():
            for kind in kinds:
                ctx.unavailable(kind, Unavailable.AGENT_MISSING.value, "spni-agent.apk not bundled")
            return
        try:
            data = agent_mod.run_agent(self.t, self.agent_apk, ctx, kinds)
        except agent_mod.AgentError as exc:
            for kind in kinds:
                ctx.unavailable(kind, Unavailable.PERMISSION_DENIED.value, str(exc))
            return
        if "contacts" in kinds and "contacts" in data:
            contacts = agent_mod.contacts_from_agent(data["contacts"])
            self._index_contacts(contacts)
            ctx.save("contacts", contacts)
        if "calls" in kinds and "calls" in data:
            ctx.save("calls", agent_mod.calls_from_agent(data["calls"], self._contacts_by_number))
        if "sms" in kinds and "sms" in data:
            ctx.save("sms", agent_mod.sms_from_agent(data["sms"], self._contacts_by_number))
        for kind in kinds:
            if kind not in data:
                ctx.unavailable(kind, Unavailable.PERMISSION_DENIED.value, "helper app could not read this category")

    # ── providers ─────────────────────────────────────────────────────────
    def _query(self, uri: str, columns: list[str], fallback: list[str] | None = None) -> list[dict[str, Any]]:
        try:
            return parse_rows(self.t.shell(build_query(uri, columns), timeout=300), columns)
        except ContentQueryError as exc:
            if exc.denied or not fallback:
                raise
            return parse_rows(self.t.shell(build_query(uri, fallback), timeout=300), fallback)

    def _index_contacts(self, contacts: list[Contact]) -> None:
        for c in contacts:
            for p in c.phones:
                self._contacts_by_number.setdefault(normalize_phone(p), c.name)

    def contacts(self) -> list[Contact]:
        cols = ["contact_id", "mimetype", "account_type", "starred", "data2", "display_name", "data1"]
        rows = self._query("content://com.android.contacts/data", cols)
        by_id: dict[str, Contact] = {}
        for r in rows:
            cid = r.get("contact_id") or ""
            c = by_id.get(cid)
            if c is None:
                c = by_id[cid] = Contact(
                    name=r.get("display_name") or "",
                    account=r.get("account_type") or "",
                    starred=r.get("starred") == "1",
                )
            mime = r.get("mimetype") or ""
            value = (r.get("data1") or "").strip()
            if not value:
                continue
            if mime.endswith("/phone_v2"):
                if value not in c.phones:
                    c.phones.append(value)
            elif mime.endswith("/email_v2"):
                c.emails.append(value)
            elif mime.endswith("/organization"):
                c.organization = value
            elif mime.endswith("/note"):
                c.note = value
        contacts = sorted(by_id.values(), key=lambda c: c.name)
        self._index_contacts(contacts)
        return contacts

    def calls(self) -> list[CallRecord]:
        cols = ["_id", "number", "date", "duration", "type", "subscription_id", "geocoded_location", "name"]
        rows = self._query("content://call_log/calls", cols, ["_id", "number", "date", "duration", "type", "name"])
        out = []
        for r in rows:
            number = normalize_phone(r.get("number"))
            out.append(
                CallRecord(
                    number=number,
                    name=r.get("name") or self._contacts_by_number.get(number, ""),
                    direction=CALL_TYPES.get(as_int(r.get("type")), "unknown"),
                    timestamp=unix_to_ms(r.get("date")),
                    duration=as_int(r.get("duration")),
                    sim=(f"SIM {r['subscription_id']}" if r.get("subscription_id") not in (None, "", "-1") else ""),
                    location=r.get("geocoded_location") or "",
                )
            )
        out.sort(key=lambda c: c.timestamp or 0, reverse=True)
        return out

    def sms(self) -> list[SmsMessage]:
        cols = ["_id", "thread_id", "address", "date", "type", "read", "body"]
        rows = self._query("content://sms", cols)
        out = []
        for r in rows:
            address = normalize_phone(r.get("address"))
            out.append(
                SmsMessage(
                    address=address,
                    body=r.get("body") or "",
                    direction="out" if as_int(r.get("type")) in SMS_OUT_TYPES else "in",
                    timestamp=unix_to_ms(r.get("date")),
                    thread=r.get("thread_id") or address,
                    contact_name=self._contacts_by_number.get(address, ""),
                    read=r.get("read") != "0",
                )
            )
        out.sort(key=lambda m: m.timestamp or 0, reverse=True)
        return out

    # ── system ────────────────────────────────────────────────────────────
    def wifi(self) -> list[WifiNetwork]:
        nets = parse_list_networks(self.t.shell("cmd wifi list-networks", timeout=30))
        if not nets:
            nets = parse_dumpsys_wifi(self.t.shell("dumpsys wifi", timeout=60))
        return nets

    def sims(self) -> list[SimCard]:
        cols = ["_id", "icc_id", "sim_id", "number", "mcc_string", "mnc_string", "carrier_name", "display_name"]
        try:
            rows = self._query("content://telephony/siminfo", cols)
        except ContentQueryError:
            rows = []
        sims = []
        for r in rows:
            slot = as_int(r.get("sim_id"), -1)
            mcc, mnc = r.get("mcc_string") or "", r.get("mnc_string") or ""
            sims.append(
                SimCard(
                    slot=f"SIM {slot + 1}" if slot >= 0 else "",
                    iccid=r.get("icc_id") or "",
                    number=normalize_phone(r.get("number")),
                    carrier=r.get("carrier_name") or "",
                    display_name=r.get("display_name") or "",
                    country="TH" if mcc == "520" else mcc,
                    active=slot >= 0,
                )
            )
        if sims:
            return sims
        props = parse_getprop(self.t.shell("getprop", timeout=20))
        names = props.get("gsm.sim.operator.alpha", "").split(",")
        states = props.get("gsm.sim.state", "").split(",")
        for i, name in enumerate(names):
            state = states[i] if i < len(states) else ""
            if name or state in ("READY", "LOADED"):
                sims.append(SimCard(slot=f"SIM {i + 1}", carrier=name, display_name=name, active=state in ("READY", "LOADED")))
        return sims

    def apps(self) -> list[App]:
        apps = parse_dumpsys_packages(self.t.shell("dumpsys package packages", timeout=180))
        apps.sort(key=lambda a: (a.system, (a.name or a.package).lower()))
        return apps

    # ── files ─────────────────────────────────────────────────────────────
    def _pull(self, ctx: ExtractionContext, remote: str, mtime: int, sub: str) -> Path:
        rel = PurePosixPath(remote.lstrip("/"))
        local = ctx.extraction.media_dir / sub / Path(*rel.parts[-3:])
        self.t.pull(remote, local)
        if mtime:
            os.utime(local, (mtime, mtime))
        return local

    def photos(self, ctx: ExtractionContext):
        files = find_files(self.t, PHOTO_DIRS, IMAGE_EXTS)
        limit = int(ctx.options.get("max_photos") or 0)
        files.sort(key=lambda f: f[2], reverse=True)
        if limit:
            files = files[:limit]
        photos = []
        for i, (remote, size, mtime) in enumerate(files):
            ctx.progress("photos", i / max(1, len(files)), count=i)
            try:
                local = self._pull(ctx, remote, mtime, "photos")
            except Exception as exc:
                ctx.audit("adb.pull.error", f"{remote}: {exc}")
                continue
            album = PurePosixPath(remote).parent.name
            photos.append(ctx.photo_record(local, remote, album=album, modified=mtime * 1000 if mtime else None))
        photos.sort(key=lambda p: p.taken or 0, reverse=True)
        return photos

    def voice(self, ctx: ExtractionContext) -> list[VoiceMemo]:
        files = find_files(self.t, VOICE_DIRS, AUDIO_EXTS)
        memos = []
        for i, (remote, size, mtime) in enumerate(files):
            ctx.progress("voice", i / max(1, len(files)), count=i)
            try:
                local = self._pull(ctx, remote, mtime, "voice")
            except Exception as exc:
                ctx.audit("adb.pull.error", f"{remote}: {exc}")
                continue
            digest = ctx.register(local, remote)
            memos.append(
                VoiceMemo(
                    title=PurePosixPath(remote).stem,
                    path=ctx.extraction.rel(local),
                    created=mtime * 1000 if mtime else None,
                    size=size,
                    sha256=digest,
                )
            )
        memos.sort(key=lambda m: m.created or 0, reverse=True)
        return memos
