"""Parsers for the iOS databases found in a backup.

Each parser takes a local path to an already-extracted (and decrypted) file and
returns model records. Column sets differ between iOS versions, so queries
only use columns that exist.
"""

from __future__ import annotations

import gzip
import json
import plistlib
import sqlite3
from pathlib import Path
from typing import Any, Iterator

from ..models import CallRecord, ChatMessage, Contact, Note, SmsMessage, VoiceMemo, WebVisit, WifiNetwork
from ..util import cocoa_to_ms, normalize_phone, unix_to_ms

# (domain, relativePath) of the databases we read.
SMS_DB = ("HomeDomain", "Library/SMS/sms.db")
ADDRESSBOOK_DB = ("HomeDomain", "Library/AddressBook/AddressBook.sqlitedb")
CALLS_DB = ("HomeDomain", "Library/CallHistoryDB/CallHistory.storedata")
SAFARI_DB = ("HomeDomain", "Library/Safari/History.db")
NOTES_DB = ("AppDomainGroup-group.com.apple.notes", "NoteStore.sqlite")
WHATSAPP_DB = ("AppDomainGroup-group.net.whatsapp.WhatsApp.shared", "ChatStorage.sqlite")


def connect(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    return db


def columns(db: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {r[1] for r in db.execute(f"PRAGMA table_info({table})")}
    except sqlite3.Error:
        return set()


def pick(cols: set[str], *candidates: str) -> str:
    for c in candidates:
        if c in cols:
            return c
    return "NULL"


# ── Messages ────────────────────────────────────────────────────────────
def decode_attributed_body(blob: bytes | None) -> str:
    """Pull the plain text out of an NSAttributedString typedstream (iOS 16+)."""
    if not blob or b"NSString" not in blob:
        return ""
    try:
        data = blob.split(b"NSString", 1)[1][5:]
        if data[0] == 0x81:
            length = int.from_bytes(data[1:3], "little")
            data = data[3 : 3 + length]
        else:
            length = data[0]
            data = data[1 : 1 + length]
        return data.decode("utf-8", errors="replace")
    except Exception:
        return ""


def parse_sms(path: Path, names: dict[str, str]) -> list[SmsMessage]:
    db = connect(path)
    mcols = columns(db, "message")
    attributed = "m.attributedBody" if "attributedBody" in mcols else "NULL"
    rows = db.execute(
        f"""
        SELECT m.ROWID AS id, m.text, {attributed} AS attributed, m.date, m.is_from_me, m.service,
               m.is_read, h.id AS handle, c.chat_identifier, c.display_name
        FROM message m
        LEFT JOIN handle h ON m.handle_id = h.ROWID
        LEFT JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
        LEFT JOIN chat c ON c.ROWID = cmj.chat_id
        """
    ).fetchall()
    attachments: dict[int, list[str]] = {}
    try:
        for r in db.execute(
            "SELECT maj.message_id, a.filename, a.transfer_name FROM message_attachment_join maj "
            "JOIN attachment a ON a.ROWID = maj.attachment_id"
        ):
            attachments.setdefault(r[0], []).append(r[2] or Path(r[1] or "").name)
    except sqlite3.Error:
        pass
    out = []
    for r in rows:
        address = normalize_phone(r["handle"] or r["chat_identifier"] or "")
        body = r["text"] or decode_attributed_body(r["attributed"])
        out.append(
            SmsMessage(
                address=address,
                body=body.replace("￼", "").strip(),
                direction="out" if r["is_from_me"] else "in",
                timestamp=cocoa_to_ms(r["date"]),
                thread=r["display_name"] or r["chat_identifier"] or address,
                contact_name=names.get(address, ""),
                read=bool(r["is_read"]) or bool(r["is_from_me"]),
                service=r["service"] or "SMS",
                attachments=attachments.get(r["id"], []),
            )
        )
    db.close()
    out.sort(key=lambda m: m.timestamp or 0, reverse=True)
    return out


# ── Contacts ────────────────────────────────────────────────────────────
def parse_addressbook(path: Path) -> list[Contact]:
    db = connect(path)
    people = {}
    for r in db.execute("SELECT ROWID, First, Last, Organization, Note, CreationDate FROM ABPerson"):
        name = " ".join(x for x in (r["First"], r["Last"]) if x) or (r["Organization"] or "")
        people[r["ROWID"]] = Contact(
            name=name,
            organization=r["Organization"] or "",
            note=r["Note"] or "",
            account="iPhone",
            created=cocoa_to_ms(r["CreationDate"]),
        )
    for r in db.execute("SELECT record_id, property, value FROM ABMultiValue WHERE value IS NOT NULL"):
        c = people.get(r["record_id"])
        if not c:
            continue
        if r["property"] == 3:
            c.phones.append(str(r["value"]))
        elif r["property"] == 4:
            c.emails.append(str(r["value"]))
    db.close()
    return sorted((c for c in people.values() if c.name or c.phones), key=lambda c: c.name)


# ── Calls ───────────────────────────────────────────────────────────────
def parse_calls(path: Path, names: dict[str, str]) -> list[CallRecord]:
    db = connect(path)
    cols = columns(db, "ZCALLRECORD")
    name_col = pick(cols, "ZNAME")
    provider = pick(cols, "ZSERVICE_PROVIDER")
    location = pick(cols, "ZLOCATION")
    out = []
    for r in db.execute(
        f"SELECT ZADDRESS, ZDATE, ZDURATION, ZORIGINATED, ZANSWERED, ZCALLTYPE, {name_col} AS name, "
        f"{provider} AS provider, {location} AS location FROM ZCALLRECORD"
    ):
        raw = r["ZADDRESS"]
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        number = normalize_phone(raw or "")
        if r["ZORIGINATED"]:
            direction = "outgoing"
        elif r["ZANSWERED"]:
            direction = "incoming"
        else:
            direction = "missed"
        prov = r["provider"] or ""
        call_type = r["ZCALLTYPE"]
        if "whatsapp" in prov.lower():
            service = "WhatsApp"
        elif "line" in prov.lower():
            service = "LINE"
        elif call_type in (8, 16) or "facetime" in prov.lower():
            service = "FaceTime Video" if call_type == 8 else "FaceTime Audio"
        else:
            service = "cellular"
        out.append(
            CallRecord(
                number=number,
                name=r["name"] or names.get(number, ""),
                direction=direction,
                timestamp=cocoa_to_ms(r["ZDATE"]),
                duration=int(r["ZDURATION"] or 0),
                service=service,
                location=r["location"] or "",
            )
        )
    db.close()
    out.sort(key=lambda c: c.timestamp or 0, reverse=True)
    return out


# ── Safari ──────────────────────────────────────────────────────────────
def parse_safari(path: Path) -> list[WebVisit]:
    db = connect(path)
    out = [
        WebVisit(url=r["url"], title=r["title"] or "", timestamp=cocoa_to_ms(r["visit_time"]), visit_count=r["visit_count"] or 1, browser="Safari")
        for r in db.execute(
            "SELECT hi.url, hv.title, hv.visit_time, hi.visit_count FROM history_visits hv "
            "JOIN history_items hi ON hv.history_item = hi.id"
        )
    ]
    db.close()
    out.sort(key=lambda v: v.timestamp or 0, reverse=True)
    return out


# ── Notes ───────────────────────────────────────────────────────────────
def _pb_fields(data: bytes) -> Iterator[tuple[int, int, Any]]:
    """Minimal protobuf reader yielding (field number, wire type, value)."""
    i, n = 0, len(data)

    def varint() -> int:
        nonlocal i
        shift = result = 0
        while i < n:
            b = data[i]
            i += 1
            result |= (b & 0x7F) << shift
            if not b & 0x80:
                return result
            shift += 7
        raise ValueError("truncated varint")

    while i < n:
        key = varint()
        field, wire = key >> 3, key & 7
        if wire == 0:
            yield field, wire, varint()
        elif wire == 1:
            yield field, wire, data[i : i + 8]
            i += 8
        elif wire == 2:
            size = varint()
            yield field, wire, data[i : i + size]
            i += size
        elif wire == 5:
            yield field, wire, data[i : i + 4]
            i += 4
        else:
            raise ValueError(f"unsupported wire type {wire}")


def _pb_get(data: bytes, field: int) -> bytes | None:
    for f, w, v in _pb_fields(data):
        if f == field and w == 2:
            return v
    return None


def decode_note_body(blob: bytes | None) -> str:
    """NoteStore ZDATA: gzip → NoteStoreProto(2) → Document(3) → Note(2: text)."""
    if not blob:
        return ""
    try:
        raw = gzip.decompress(blob)
        doc = _pb_get(raw, 2)
        note = _pb_get(doc, 3) if doc else None
        text = _pb_get(note, 2) if note else None
        return text.decode("utf-8", errors="replace") if text else ""
    except Exception:
        return ""


def parse_notes(path: Path) -> list[Note]:
    db = connect(path)
    cols = columns(db, "ZICCLOUDSYNCINGOBJECT")
    created = pick(cols, "ZCREATIONDATE3", "ZCREATIONDATE1", "ZCREATIONDATE")
    modified = pick(cols, "ZMODIFICATIONDATE1", "ZMODIFICATIONDATE")
    snippet = pick(cols, "ZSNIPPET")
    joins, folder_sel, data_sel = "", "NULL", "NULL"
    if "ZFOLDER" in cols and "ZTITLE2" in cols:
        joins += " LEFT JOIN ZICCLOUDSYNCINGOBJECT f ON f.Z_PK = o.ZFOLDER"
        folder_sel = "f.ZTITLE2"
    if "ZNOTEDATA" in cols and columns(db, "ZICNOTEDATA"):
        joins += " LEFT JOIN ZICNOTEDATA d ON d.Z_PK = o.ZNOTEDATA"
        data_sel = "d.ZDATA"
    o = lambda c: c if c == "NULL" else f"o.{c}"  # noqa: E731
    rows = db.execute(
        f"SELECT o.ZTITLE1 AS title, {o(snippet)} AS snippet, {o(created)} AS created, {o(modified)} AS modified, "
        f"{folder_sel} AS folder, {data_sel} AS data FROM ZICCLOUDSYNCINGOBJECT o{joins} "
        "WHERE o.ZTITLE1 IS NOT NULL"
    ).fetchall()
    out = []
    for r in rows:
        body = decode_note_body(r["data"]) or (r["snippet"] or "")
        out.append(
            Note(
                title=r["title"] or "",
                body=body,
                folder=r["folder"] or "",
                created=cocoa_to_ms(r["created"]),
                modified=cocoa_to_ms(r["modified"]),
                source="Apple Notes",
            )
        )
    db.close()
    out.sort(key=lambda n: n.modified or 0, reverse=True)
    return out


# ── Wi-Fi ───────────────────────────────────────────────────────────────
def _ssid(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value or "")


def _date_ms(value: Any) -> int | None:
    if hasattr(value, "timestamp"):
        return int(value.timestamp() * 1000)
    return None


def parse_wifi_plist(path: Path) -> list[WifiNetwork]:
    data = plistlib.loads(path.read_bytes())
    nets: list[WifiNetwork] = []
    if isinstance(data, dict) and "List of known networks" in data:
        for n in data["List of known networks"]:
            nets.append(
                WifiNetwork(
                    ssid=_ssid(n.get("SSID_STR") or n.get("SSID")),
                    security=str(n.get("SecurityMode", "")),
                    bssid=str(n.get("BSSID", "")),
                    last_connected=_date_ms(n.get("lastJoined") or n.get("lastAutoJoined")),
                    hidden=bool(n.get("HIDDEN_NETWORK")),
                    source=path.name,
                )
            )
    elif isinstance(data, dict):
        for key, n in data.items():
            if not isinstance(n, dict) or not key.startswith("wifi.network"):
                continue
            joined = [n.get(k) for k in ("JoinedByUserAt", "JoinedBySystemAt", "AddedAt", "UpdatedAt")]
            last = max((_date_ms(d) or 0 for d in joined if d), default=0) or None
            sec = n.get("SupportedSecurityTypes")
            nets.append(
                WifiNetwork(
                    ssid=_ssid(n.get("SSID")) or key.split("wifi.network.ssid.", 1)[-1],
                    security=str(sec) if sec is not None else "",
                    bssid=str(n.get("BSSID", "") or ""),
                    last_connected=last,
                    hidden=bool(n.get("Hidden")),
                    source=path.name,
                )
            )
    nets.sort(key=lambda w: w.last_connected or 0, reverse=True)
    return nets


# ── WhatsApp / LINE ─────────────────────────────────────────────────────
WA_TYPES = {1: "[รูปภาพ]", 2: "[วิดีโอ]", 3: "[เสียง]", 4: "[ผู้ติดต่อ]", 5: "[ตำแหน่ง]", 8: "[ไฟล์]", 15: "[สติกเกอร์]"}


def parse_whatsapp(path: Path) -> list[ChatMessage]:
    db = connect(path)
    mcols = columns(db, "ZWAMESSAGE")
    push = pick(mcols, "ZPUSHNAME")
    out = []
    for r in db.execute(
        f"SELECT m.ZTEXT, m.ZISFROMME, m.ZMESSAGEDATE, m.ZFROMJID, m.ZMESSAGETYPE, {push} AS push, "
        "s.ZPARTNERNAME, s.ZCONTACTJID FROM ZWAMESSAGE m LEFT JOIN ZWACHATSESSION s ON m.ZCHATSESSION = s.Z_PK"
    ):
        mtype = r["ZMESSAGETYPE"] or 0
        body = r["ZTEXT"] or WA_TYPES.get(mtype, "")
        if not body:
            continue
        thread = r["ZPARTNERNAME"] or (r["ZCONTACTJID"] or "").split("@")[0]
        sender = "ฉัน" if r["ZISFROMME"] else (r["push"] or thread or (r["ZFROMJID"] or "").split("@")[0])
        out.append(
            ChatMessage(
                app="WhatsApp",
                thread=thread,
                sender=sender,
                body=body,
                direction="out" if r["ZISFROMME"] else "in",
                timestamp=cocoa_to_ms(r["ZMESSAGEDATE"]),
                attachment=WA_TYPES.get(mtype, "") if mtype else "",
            )
        )
    db.close()
    return out


# LINE message content types (LINE protocol ContentType).
LINE_IMAGE, LINE_VIDEO, LINE_AUDIO, LINE_CALL, LINE_STICKER, LINE_CONTACT, LINE_FILE, LINE_LOCATION, LINE_EVENT = 1, 2, 3, 6, 7, 13, 14, 15, 18
LINE_MEDIA = {LINE_IMAGE, LINE_VIDEO, LINE_AUDIO, LINE_FILE}


def _unarchive_dict(archive: dict[str, Any]) -> dict[str, Any]:
    """Top-level NSDictionary of an NSKeyedArchiver plist, values resolved one level."""
    objs = archive.get("$objects", [])

    def val(x: Any) -> Any:
        if isinstance(x, plistlib.UID):
            x = objs[x.data] if x.data < len(objs) else None
        return None if x == "$null" else x

    top = val((archive.get("$top") or {}).get("root"))
    if isinstance(top, dict) and "NS.keys" in top:
        return {str(val(k)): val(v) for k, v in zip(top["NS.keys"], top.get("NS.objects", []))}
    return {}


def line_metadata(blob: Any) -> dict[str, Any]:
    """ZCONTENTMETADATA: JSON, a plist dict or a keyed archive depending on the LINE version."""
    if not blob:
        return {}
    if isinstance(blob, str):
        blob = blob.encode("utf-8", "replace")
    try:
        data = json.loads(blob)
        return data if isinstance(data, dict) else {}
    except (ValueError, UnicodeDecodeError):
        pass
    try:
        data = plistlib.loads(blob)
    except Exception:
        return {}
    if isinstance(data, dict) and "$objects" in data:
        return _unarchive_dict(data)
    return data if isinstance(data, dict) else {}


def _clock_ms(value: Any) -> str:
    try:
        sec = int(float(value)) // 1000
    except (TypeError, ValueError):
        return ""
    if sec <= 0:
        return ""
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _line_body(ct: int, text: str, meta: dict[str, Any], lat: Any, lon: Any) -> str:
    def g(*keys: str) -> Any:
        return next((meta[k] for k in keys if meta.get(k) not in (None, "")), None)

    def with_clock(label: str, value: Any) -> str:
        clock = _clock_ms(value)
        return f"{label} {clock}" if clock else label

    if ct == 0:
        return text
    if ct == LINE_IMAGE:
        return "[รูปภาพ]"
    if ct == LINE_VIDEO:
        return with_clock("[วิดีโอ]", g("DURATION", "duration"))
    if ct == LINE_AUDIO:
        return with_clock("[ข้อความเสียง]", g("AUDLEN", "DURATION", "duration"))
    if ct == LINE_CALL:
        video = str(g("TYPE", "type") or "").upper().startswith("V")
        label = "วิดีโอคอลผ่าน LINE" if video else "โทรผ่าน LINE"
        clock = _clock_ms(g("DURATION", "duration"))
        return f"[{label} {clock}]" if clock else f"[{label}]"
    if ct == LINE_STICKER:
        caption = g("STKTXT")
        return f"[สติกเกอร์] {caption}" if caption else "[สติกเกอร์]"
    if ct == LINE_CONTACT:
        return f"[ผู้ติดต่อ] {g('displayName', 'DISPLAY_NAME') or ''}".strip()
    if ct == LINE_FILE:
        return f"[ไฟล์] {g('FILE_NAME', 'fileName') or ''}".strip()
    if ct == LINE_LOCATION:
        place = f"[ตำแหน่ง] {text}".strip()
        try:
            la, lo = float(lat), float(lon)
            if la or lo:
                place += f" ({la:.5f}, {lo:.5f})"
        except (TypeError, ValueError):
            pass
        return place
    if ct == LINE_EVENT:
        return f"[ห้องสนทนา] {text}" if text else ""
    return text or f"[ข้อความ LINE ประเภท {ct}]"


def parse_line_full(path: Path) -> list[tuple[ChatMessage, str, int]]:
    """LINE (Line.sqlite, Core Data). Returns (message, server message id, content type).

    The schema is undocumented and changes between versions, so every column is
    optional. Chats are named from the contact (1:1), the group table (groups)
    or the people who wrote in it (multi-person rooms).
    """
    db = connect(path)
    try:
        mcols = columns(db, "ZMESSAGE")
        if not mcols:
            return []
        ucols = columns(db, "ZUSER")
        by_pk: dict[Any, str] = {}
        by_mid: dict[str, str] = {}
        if ucols:
            sel = ", ".join(c for c in ("Z_PK", "ZMID", "ZNAME", "ZCUSTOMNAME", "ZADDRESSBOOKNAME") if c in ucols)
            for r in db.execute(f"SELECT {sel} FROM ZUSER"):
                d = dict(r)
                name = d.get("ZCUSTOMNAME") or d.get("ZADDRESSBOOKNAME") or d.get("ZNAME") or d.get("ZMID") or ""
                by_pk[d.get("Z_PK")] = name
                if d.get("ZMID"):
                    by_mid[d["ZMID"]] = name
        groups: dict[str, str] = {}
        gcols = columns(db, "ZGROUP")
        if gcols:
            for r in db.execute(f"SELECT {pick(gcols, 'ZID', 'ZMID')} AS id, {pick(gcols, 'ZNAME')} AS name FROM ZGROUP"):
                if r["id"]:
                    groups[r["id"]] = r["name"] or ""
        ccols = columns(db, "ZCHAT")
        chats: dict[Any, dict[str, Any]] = {}
        if ccols:
            for r in db.execute(f"SELECT Z_PK, {pick(ccols, 'ZMID')} AS mid, {pick(ccols, 'ZNAME')} AS name FROM ZCHAT"):
                chats[r["Z_PK"]] = dict(r)
        rows = db.execute(
            f"SELECT {pick(mcols, 'ZCHAT')} AS chat, {pick(mcols, 'ZSENDER')} AS sender, {pick(mcols, 'ZTEXT')} AS text, "
            f"{pick(mcols, 'ZTIMESTAMP')} AS ts, {pick(mcols, 'ZCONTENTTYPE')} AS ct, {pick(mcols, 'ZID', 'ZSERVERID')} AS sid, "
            f"{pick(mcols, 'ZCONTENTMETADATA')} AS meta, {pick(mcols, 'ZLATITUDE')} AS lat, {pick(mcols, 'ZLONGITUDE')} AS lon FROM ZMESSAGE"
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        db.close()

    writers: dict[Any, list[str]] = {}
    for r in rows:
        name = by_pk.get(r["sender"]) if r["sender"] is not None else None
        if name and name not in writers.setdefault(r["chat"], []):
            writers[r["chat"]].append(name)

    def title(chat_pk: Any) -> str:
        c = chats.get(chat_pk) or {}
        mid = c.get("mid") or ""
        return c.get("name") or by_mid.get(mid) or groups.get(mid) or ", ".join(writers.get(chat_pk, [])[:3]) or mid or "LINE"

    out: list[tuple[ChatMessage, str, int]] = []
    for r in rows:
        try:
            ct = int(r["ct"] or 0)
        except (TypeError, ValueError):
            ct = 0
        body = _line_body(ct, r["text"] or "", line_metadata(r["meta"]), r["lat"], r["lon"])
        if not body:
            continue
        mine = r["sender"] is None
        thread = title(r["chat"])
        out.append((
            ChatMessage(
                app="LINE",
                thread=thread,
                sender="ฉัน" if mine else (by_pk.get(r["sender"]) or thread),
                body=body,
                direction="out" if mine else "in",
                timestamp=unix_to_ms(r["ts"]),
            ),
            str(r["sid"] or ""),
            ct,
        ))
    return out


def parse_line(path: Path) -> list[ChatMessage]:
    return [m for m, _, _ in parse_line_full(path)]


# ── Voice memos ─────────────────────────────────────────────────────────
def parse_voice_titles(path: Path) -> dict[str, dict[str, Any]]:
    """CloudRecordings.db / Recordings.db → {file name: {title, duration, created}}."""
    db = connect(path)
    out: dict[str, dict[str, Any]] = {}
    cols = columns(db, "ZCLOUDRECORDING")
    if cols:
        title = pick(cols, "ZENCRYPTEDTITLE", "ZCUSTOMLABEL")
        for r in db.execute(f"SELECT ZPATH, {title} AS title, ZDATE, ZDURATION FROM ZCLOUDRECORDING"):
            if r["ZPATH"]:
                out[Path(r["ZPATH"]).name] = {"title": r["title"] or "", "duration": r["ZDURATION"], "created": cocoa_to_ms(r["ZDATE"])}
    db.close()
    return out


def voice_record(local: Path, rel: str, digest: str, meta: dict[str, Any], mtime: int | None) -> VoiceMemo:
    return VoiceMemo(
        title=meta.get("title") or local.stem,
        path=rel,
        duration=round(float(meta["duration"]), 1) if meta.get("duration") else None,
        created=meta.get("created") or mtime,
        size=local.stat().st_size,
        sha256=digest,
    )


def contact_index(contacts: list[Contact]) -> dict[str, str]:
    names: dict[str, str] = {}
    for c in contacts:
        for p in c.phones:
            names.setdefault(normalize_phone(p), c.name)
        for e in c.emails:
            names.setdefault(e.lower(), c.name)
    return names
