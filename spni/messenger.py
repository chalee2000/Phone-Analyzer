"""Facebook Messenger messages from a Facebook data export.

Messenger keeps its messages in app-private storage (Android
``/data/data/com.facebook.orca``, no ``adb backup``), so a phone without root
cannot be read directly. The account's own exports can be imported instead:

* **Download Your Information** (JSON): ``…/messages/<folder>/<thread>/message_N.json``
  with ``participants``, ``title``, ``thread_path`` and ``messages`` whose items
  carry ``sender_name``, ``timestamp_ms``, ``content``, ``photos``/``videos``/
  ``audio_files``/``files``/``gifs`` (``uri``), ``sticker``, ``share``,
  ``call_duration``, ``is_unsent`` and ``reactions``. Text is UTF-8 written as
  one ``\\u00XX`` escape per byte, so Thai arrives garbled and is repaired here.
* **Secure storage download** of end-to-end encrypted chats: one JSON file per
  chat with the same idea in camelCase (``threadName``, ``senderName``, ``text``,
  ``timestamp``, ``media``, ``isUnsent``). Keys are read tolerantly.

Inputs may be zip files (Facebook splits large exports into parts), loose JSON
files or an extracted folder. Each import becomes one extraction in the case:
chats, attached photos (with thumbnails and EXIF), every copied file hashed,
and the source files' SHA-256 written to the audit log.
"""

from __future__ import annotations

import hashlib
import io
import json
import random
import re
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterator

from .case.store import Case
from .events import EventBus
from .extract import ExtractionContext
from .models import ALL_KINDS, ChatMessage
from .util import safe_name, sha256_file

APP = "Messenger"
ME = "ฉัน"
FOLDERS = ("inbox", "archived_threads", "filtered_threads", "message_requests", "e2ee_cutover")
REQUEST_FOLDERS = ("message_requests", "filtered_threads")
MSG_RE = re.compile(r"(?:^|/)messages/(" + "|".join(FOLDERS) + r")/([^/]+)/message_\d+\.(json|html)$", re.I)
PROFILE_RE = re.compile(r"(?:^|/)profile_information/profile_information\.json$", re.I)
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".bmp"}
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm", ".3gp"}
AUDIO_EXT = {".m4a", ".aac", ".mp3", ".wav", ".ogg", ".opus", ".amr"}
MEDIA_KEYS = (("photos", "[รูปภาพ]"), ("gifs", "[GIF]"), ("videos", "[วิดีโอ]"), ("audio_files", "[ข้อความเสียง]"), ("files", "[ไฟล์]"))

Progress = Callable[[str, float], None]


def fix_text(value: Any) -> str:
    """Undo Facebook's per-byte escaping (``à¸ª`` → ``ส``); leave correct text alone."""
    if not isinstance(value, str) or not value:
        return "" if value is None else str(value)
    try:
        return value.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value


def _ms(value: Any) -> int | None:
    try:
        ts = int(float(value))
    except (TypeError, ValueError):
        return None
    return ts * 1000 if ts < 10**12 else ts


def _duration(sec: int) -> str:
    h, rem = divmod(int(sec), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _label_for(uri: str) -> str:
    ext = Path(uri).suffix.lower()
    if ext in IMAGE_EXT:
        return "[รูปภาพ]"
    if ext in VIDEO_EXT:
        return "[วิดีโอ]"
    if ext in AUDIO_EXT:
        return "[ข้อความเสียง]"
    return "[ไฟล์]"


# ── input sources ───────────────────────────────────────────────────────
class Source:
    """One input: a zip, a loose JSON file or an extracted export folder."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if not self.path.exists():
            raise ValueError("not_found")
        self.zip: zipfile.ZipFile | None = None
        self.folder: Path | None = None
        if self.path.is_dir():
            self.folder = self.path
        elif zipfile.is_zipfile(self.path):
            self.zip = zipfile.ZipFile(self.path)

    def names(self) -> list[str]:
        if self.zip:
            return [i.filename for i in self.zip.infolist() if not i.is_dir()]
        if self.folder:
            return [p.relative_to(self.folder).as_posix() for p in self.folder.rglob("*") if p.is_file()]
        return [self.path.name]

    def read(self, name: str) -> bytes:
        if self.zip:
            return self.zip.read(name)
        if self.folder:
            return (self.folder / name).read_bytes()
        return self.path.read_bytes()

    def copy_to(self, name: str, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if self.zip:
            with self.zip.open(name) as src, open(dest, "wb") as out:
                while block := src.read(1 << 20):
                    out.write(block)
        else:
            dest.write_bytes(self.read(name))

    def close(self) -> None:
        if self.zip:
            self.zip.close()


@dataclass
class Thread:
    key: str
    folder: str = "inbox"
    title: str = ""
    participants: list[str] = field(default_factory=list)
    e2ee: bool = False
    messages: list[dict[str, Any]] = field(default_factory=list)
    files: list[tuple[int, str]] = field(default_factory=list)  # (source index, json name)


@dataclass
class Export:
    sources: list[Source]
    threads: dict[str, Thread]
    owner_hint: str
    media: dict[str, tuple[int, str]]  # lookup key -> (source index, name)
    warnings: list[str]

    def close(self) -> None:
        for s in self.sources:
            s.close()

    def find_media(self, uri: str) -> tuple[int, str] | None:
        uri = (uri or "").strip().lstrip("./")
        if not uri or uri.startswith(("http://", "https://")):
            return None
        for key in (uri.lower(), _tail(uri), Path(uri).name.lower()):
            if key and key in self.media:
                return self.media[key]
        return None


def _tail(name: str) -> str:
    low = name.lower()
    i = low.find("messages/")
    return low[i:] if i >= 0 else ""


def _thread_json(data: Any) -> bool:
    return isinstance(data, dict) and isinstance(data.get("messages"), list) and any(
        k in data for k in ("participants", "title", "threadName", "thread_path", "threadPath")
    )


def _participants(data: dict[str, Any]) -> list[str]:
    out = []
    for p in data.get("participants") or []:
        name = p.get("name") if isinstance(p, dict) else p
        if name:
            out.append(fix_text(name))
    return out


def load(paths: list[str] | tuple[str, ...]) -> Export:
    """Index every input: message JSON per thread, media files and the profile."""
    if not paths:
        raise ValueError("fb_no_messages")
    sources = [Source(p) for p in paths]
    threads: dict[str, Thread] = {}
    media: dict[str, tuple[int, str]] = {}
    owner_hint = ""
    html_only = False
    warnings: list[str] = []
    for si, src in enumerate(sources):
        names = [n for n in src.names() if not n.rsplit("/", 1)[-1].startswith(".") and "__MACOSX" not in n]
        # A full DYI export holds many unrelated JSON files; only its message files matter.
        dyi = any(MSG_RE.search(n) for n in names)
        for name in names:
            low = name.lower()
            m = MSG_RE.search(name)
            if m and m.group(3).lower() == "html":
                html_only = True
                continue
            if PROFILE_RE.search(name):
                try:
                    prof = json.loads(src.read(name))
                    p = prof.get("profile_v2") or prof.get("profile") or {}
                    owner_hint = fix_text((p.get("name") or {}).get("full_name") or "") or owner_hint
                except (ValueError, AttributeError):
                    pass
                continue
            if not low.endswith(".json"):
                entry = (si, name)
                media.setdefault(low, entry)
                if tail := _tail(name):
                    media.setdefault(tail, entry)
                media.setdefault(Path(low).name, entry)
                continue
            if m is None and dyi:
                continue
            try:
                data = json.loads(src.read(name))
            except ValueError:
                continue
            if not _thread_json(data):
                continue
            if m:
                folder, tdir = m.group(1).lower(), m.group(2)
                key = f"{folder}/{tdir}"
            else:  # secure-storage (E2EE) download or a lone message_N.json
                camel = "threadName" in data or any(isinstance(x, dict) and "senderName" in x for x in data["messages"][:3])
                folder = "e2ee_cutover" if camel else "inbox"
                key = str(data.get("thread_path") or data.get("threadPath") or f"{folder}/{Path(name).stem}")
            t = threads.setdefault(key, Thread(key=key, folder=folder))
            t.title = t.title or fix_text(data.get("title") or data.get("threadName") or data.get("thread_name") or "")
            for p in _participants(data):
                if p not in t.participants:
                    t.participants.append(p)
            t.e2ee = t.e2ee or folder == "e2ee_cutover" or "threadName" in data
            t.messages.extend(x for x in data["messages"] if isinstance(x, dict))
            t.files.append((si, name))
    if not threads:
        for s in sources:
            s.close()
        raise ValueError("fb_html_format" if html_only else "fb_no_messages")
    if html_only:
        warnings.append("html_skipped")
    return Export(sources, threads, owner_hint, media, warnings)


def guess_owner(exp: Export) -> tuple[str, list[dict[str, Any]]]:
    """The account owner: from the profile file, else whoever is in the most threads."""
    in_threads: Counter[str] = Counter()
    sent: Counter[str] = Counter()
    for t in exp.threads.values():
        for p in set(t.participants):
            in_threads[p] += 1
        for msg in t.messages:
            sent[fix_text(msg.get("sender_name") or msg.get("senderName") or "")] += 1
    names = set(in_threads) | {n for n in sent if n}
    ranked = sorted(names, key=lambda n: (in_threads[n], sent[n]), reverse=True)
    owner = exp.owner_hint or (ranked[0] if ranked else "")
    if owner and owner not in ranked[:12]:
        ranked.insert(0, owner)
    candidates = [{"name": n, "threads": in_threads[n], "messages": sent[n]} for n in ranked[:12]]
    return owner, candidates


# ── messages ────────────────────────────────────────────────────────────
def _media_refs(m: dict[str, Any]) -> list[tuple[str, str]]:
    refs: list[tuple[str, str]] = []
    for key, label in MEDIA_KEYS:
        for item in m.get(key) or []:
            uri = item.get("uri") if isinstance(item, dict) else item
            if uri:
                refs.append((label, str(uri)))
    for item in m.get("media") or []:  # secure-storage format
        uri = item.get("uri") if isinstance(item, dict) else item
        if uri:
            refs.append((_label_for(str(uri)), str(uri)))
    return refs


def _body(m: dict[str, Any], refs: list[tuple[str, str]]) -> str:
    text = fix_text(m.get("content") or m.get("text") or "")
    if m.get("is_unsent") or m.get("isUnsent"):
        body = "[ยกเลิกการส่งข้อความ]"
    elif m.get("call_duration") is not None:
        dur = int(m.get("call_duration") or 0)
        body = f"[โทรผ่าน Messenger {_duration(dur)}]" if dur else "[สายที่ไม่ได้รับผ่าน Messenger]"
    elif text:
        body = text
        link = (m.get("share") or {}).get("link") if isinstance(m.get("share"), dict) else None
        if link and link not in text:
            body += f" [ลิงก์] {link}"
    elif refs:
        label, uri = refs[0]
        body = f"{label} {Path(uri).name}" if label == "[ไฟล์]" else label
        if len(refs) > 1:
            body += f" ×{len(refs)}"
    elif m.get("sticker"):
        body = "[สติกเกอร์]"
    elif isinstance(m.get("share"), dict) and m["share"].get("link"):
        body = f"[ลิงก์] {m['share']['link']}"
    else:
        return ""
    reactions = [
        f"{fix_text(r.get('reaction'))} {fix_text(r.get('actor'))}".strip()
        for r in (m.get("reactions") or [])
        if isinstance(r, dict)
    ]
    if reactions:
        body += " · " + ", ".join(reactions)
    return body


def _thread_title(t: Thread, owner: str) -> str:
    others = [p for p in t.participants if p != owner]
    title = t.title or ", ".join(others) or t.key.rsplit("/", 1)[-1]
    if t.folder in REQUEST_FOLDERS:
        title += " (คำขอข้อความ)"
    return title


def iter_messages(exp: Export, owner: str) -> Iterator[tuple[Thread, str, dict[str, Any], ChatMessage, list[tuple[str, str]]]]:
    seen: set[tuple[str, int | None, str, str]] = set()
    for t in exp.threads.values():
        title = _thread_title(t, owner)
        for m in t.messages:
            refs = _media_refs(m)
            sticker = m.get("sticker") if isinstance(m.get("sticker"), dict) else None
            body = _body(m, refs)
            if not body:
                continue
            sender_raw = fix_text(m.get("sender_name") or m.get("senderName") or m.get("sender") or "")
            ts = _ms(m.get("timestamp_ms") if m.get("timestamp_ms") is not None else m.get("timestamp"))
            key = (t.key, ts, sender_raw, body)
            if key in seen:
                continue
            seen.add(key)
            mine = bool(owner) and sender_raw == owner
            msg = ChatMessage(
                app=APP, thread=title, sender=ME if mine else (sender_raw or title), body=body,
                direction="out" if mine else "in", timestamp=ts, encrypted=t.e2ee,
            )
            all_refs = refs + ([("[สติกเกอร์]", str(sticker["uri"]))] if sticker and sticker.get("uri") else [])
            yield t, title, m, msg, all_refs


def preview(paths: list[str]) -> dict[str, Any]:
    exp = load(paths)
    try:
        owner, candidates = guess_owner(exp)
        times: list[int] = []
        media = 0
        count = 0
        for _t, _title, _m, msg, refs in iter_messages(exp, owner):
            count += 1
            media += len(refs)
            if msg.timestamp:
                times.append(msg.timestamp)
        return {
            "owner": owner,
            "candidates": candidates,
            "threads": len(exp.threads),
            "e2ee_threads": sum(1 for t in exp.threads.values() if t.e2ee),
            "requests": sum(1 for t in exp.threads.values() if t.folder in REQUEST_FOLDERS),
            "messages": count,
            "media": media,
            "first": min(times) if times else None,
            "last": max(times) if times else None,
            "sources": [{"name": s.path.name, "size": s.path.stat().st_size if s.path.is_file() else None, "path": str(s.path)} for s in exp.sources],
            "warnings": exp.warnings,
        }
    finally:
        exp.close()


# ── import ──────────────────────────────────────────────────────────────
def _short(name: str, limit: int = 60) -> str:
    p = Path(name)
    stem = safe_name(p.stem, "file")[:limit]
    return stem + p.suffix.lower()[:8]


def import_into(case: Case, paths: list[str], owner: str = "", examiner: str = "", progress: Progress | None = None) -> dict[str, Any]:
    say = progress or (lambda step, f: None)
    say("read", 0.02)
    exp = load(paths)
    try:
        guessed, _ = guess_owner(exp)
        owner = (owner or guessed).strip()
        # ASCII serial keeps the extraction folder name short and plain on Windows.
        serial = "fb-" + hashlib.sha1((owner or "unknown").encode("utf-8")).hexdigest()[:10]
        device = {
            "platform": "messenger", "serial": serial, "brand": "Facebook", "model": "Messenger",
            "market_name": f"Messenger · {owner}" if owner else "Messenger", "phone_number": "", "os_version": "",
            "accounts": [owner] if owner else [], "restricted": {},
            "extra": {"source_files": ", ".join(s.path.name for s in exp.sources), "owner": owner},
        }
        ext = case.create_extraction(device, "fb-export", examiner)
        ctx = ExtractionContext(ext, EventBus(), f"import-{ext.id}", ["chats", "photos"])
        # Chain of custody: hash every source as received.
        for s in exp.sources:
            if s.path.is_file():
                say("hash", 0.05)
                ext.audit("messenger.source", f"{s.path.name} size={s.path.stat().st_size} sha256={sha256_file(s.path)}")
            else:
                ext.audit("messenger.source", f"{s.path} (folder)")
        # Keep the message JSON exactly as exported.
        for t in exp.threads.values():
            for si, name in t.files:
                dest = ext.raw_dir / "messenger" / str(si + 1) / t.folder / _short(t.key.rsplit("/", 1)[-1], 40) / _short(Path(name).name)
                exp.sources[si].copy_to(name, dest)
                ext.register_file(dest, f"{exp.sources[si].path.name}:{name}")
        chats: list[dict[str, Any]] = []
        photos: list[dict[str, Any]] = []
        copied: dict[tuple[int, str], Path] = {}
        missing = 0
        items = list(iter_messages(exp, owner))
        for i, (t, title, _m, msg, refs) in enumerate(items):
            if i % 200 == 0:
                say("messages", 0.1 + 0.8 * i / max(1, len(items)))
            for label, uri in refs:
                found = exp.find_media(uri)
                if not found:
                    missing += 1
                    continue
                local = copied.get(found)
                if local is None:
                    si, name = found
                    local = ext.media_dir / "messenger" / _short(t.key.rsplit("/", 1)[-1], 40) / _short(Path(name).name)
                    n = 1
                    while local.exists():
                        local = local.with_name(f"{local.stem}_{n}{local.suffix}")
                        n += 1
                    exp.sources[si].copy_to(name, local)
                    copied[found] = local
                    if local.suffix.lower() in IMAGE_EXT and label != "[สติกเกอร์]":
                        photos.append(ctx.photo_record(local, f"{exp.sources[si].path.name}:{name}", album=f"Messenger: {title}", modified=msg.timestamp).to_dict())
                    else:
                        ext.register_file(local, f"{exp.sources[si].path.name}:{name}")
                if not msg.attachment:
                    msg.attachment = ext.rel(local)
            chats.append(msg.to_dict())
        chats.sort(key=lambda c: c.get("timestamp") or 0, reverse=True)
        photos.sort(key=lambda p: p.get("taken") or 0, reverse=True)
        say("save", 0.92)
        ext.set_records("chats", chats)
        ext.set_records("photos", photos)
        for kind in ALL_KINDS:
            if kind not in ("chats", "photos"):
                ext.set_unavailable(kind, "not_supported", "Messenger export")
        ext.audit(
            "messenger.import",
            f"owner={owner} threads={len(exp.threads)} e2ee={sum(1 for t in exp.threads.values() if t.e2ee)} "
            f"messages={len(chats)} photos={len(photos)} media={len(copied)} missing_media={missing}",
        )
        counts = ext.finish("completed")
        say("done", 1.0)
        return {"extraction_id": ext.id, "owner": owner, "threads": len(exp.threads), "counts": counts, "missing_media": missing}
    finally:
        exp.close()


# ── demo export (training, tests, screenshots) ─────────────────────────
def _garble(obj: Any) -> Any:
    """Write strings the way Facebook does: UTF-8 bytes as latin-1 code points."""
    if isinstance(obj, str):
        return obj.encode("utf-8").decode("latin-1")
    if isinstance(obj, list):
        return [_garble(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _garble(v) for k, v in obj.items()}
    return obj


DEMO_OWNER = "สมชาย ใจดี"
DEMO_LINES = [
    "ถึงไหนแล้ว", "ของมาพรุ่งนี้นะ", "โอนแล้ว เช็คด้วย", "เจอกันที่เดิม", "อย่าโทร พิมพ์มา", "ลบแชตด้วย",
    "ได้ครับพี่", "รอแป๊บ", "วันนี้ไม่สะดวก", "ส่งพิกัดมาที", "รับทราบ", "ของเหลือเท่าไหร่", "ขอเลื่อนเป็นพรุ่งนี้",
    "อยู่หน้าเซเว่นแล้ว", "ระวังด่านแถวบางนา", "ฝากบอกเฮียด้วย", "คืนนี้สองทุ่ม", "ส่งรูปมาดูหน่อย",
]


def demo_export(seed: int = 4242, days: int = 30) -> list[tuple[str, bytes]]:
    """Two files like a real case: a DYI export zip and a secure-storage (E2EE) zip."""
    from .demo import SHARED_PEOPLE, render_scene

    rng = random.Random(seed)
    now = datetime.now().replace(microsecond=0)
    start = now - timedelta(days=days)

    def ts() -> int:
        return int((start + timedelta(seconds=rng.randint(0, days * 86400))).timestamp() * 1000)

    def jpeg() -> bytes:
        buf = io.BytesIO()
        render_scene(rng, 640, 480).save(buf, "JPEG", quality=80)
        return buf.getvalue()

    root = "your_facebook_activity/messages"
    dyi = io.BytesIO()
    with zipfile.ZipFile(dyi, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("personal_information/profile_information/profile_information.json",
                   json.dumps(_garble({"profile_v2": {"name": {"full_name": DEMO_OWNER}}})))
        threads = [(name, "inbox") for _, name, _ in SHARED_PEOPLE[:6]] + [("ร้านมือถือ ดีลดี", "message_requests")]
        threads.append(("ทีมขนของ 🚚", "inbox"))
        for ti, (name, folder) in enumerate(threads):
            group = name.startswith("ทีม")
            members = [DEMO_OWNER] + ([n for _, n, _ in SHARED_PEOPLE[:4]] if group else [name])
            tdir = f"{safe_name(name, 'thread').replace(' ', '')}_{1000 + ti}"
            msgs = []
            for _ in range(rng.randint(14, 34) if folder == "inbox" else 3):
                sender = rng.choice(members)
                m: dict[str, Any] = {"sender_name": sender, "timestamp_ms": ts(), "is_geoblocked_for_viewer": False}
                roll = rng.random()
                if roll < 0.12:
                    fname = f"{rng.randint(10**8, 10**9)}_{rng.randint(10**14, 10**15)}_n.jpg"
                    uri = f"{root}/{folder}/{tdir}/photos/{fname}"
                    z.writestr(uri, jpeg())
                    m["photos"] = [{"uri": uri, "creation_timestamp": m["timestamp_ms"] // 1000}]
                elif roll < 0.16:
                    m["sticker"] = {"uri": f"{root}/stickers_used/369239263222822.png"}
                elif roll < 0.2:
                    m["call_duration"] = rng.choice([0, 37, 154, 412])
                    m["content"] = "การโทรสิ้นสุดลงแล้ว"
                elif roll < 0.23:
                    m["is_unsent"] = True
                elif roll < 0.26:
                    m["content"] = "ดูนี่"
                    m["share"] = {"link": "https://maps.app.goo.gl/bangna-demo"}
                else:
                    m["content"] = rng.choice(DEMO_LINES)
                if rng.random() < 0.08:
                    m["reactions"] = [{"reaction": "👍", "actor": rng.choice(members)}]
                msgs.append(m)
            msgs.sort(key=lambda x: x["timestamp_ms"], reverse=True)
            # Long chats are split the way Facebook does it.
            parts = [msgs[:20], msgs[20:]] if len(msgs) > 20 else [msgs]
            for pi, chunk in enumerate(parts, 1):
                body = {
                    "participants": [{"name": n} for n in members], "messages": chunk,
                    "title": name, "is_still_participant": True, "thread_path": f"{folder}/{tdir}", "magic_words": [],
                }
                z.writestr(f"{root}/{folder}/{tdir}/message_{pi}.json", json.dumps(_garble(body), indent=2))
        sticker = io.BytesIO()
        render_scene(rng, 160, 160).save(sticker, "PNG")
        z.writestr(f"{root}/stickers_used/369239263222822.png", sticker.getvalue())
    e2ee = io.BytesIO()
    with zipfile.ZipFile(e2ee, "w", zipfile.ZIP_DEFLATED) as z:
        friend = SHARED_PEOPLE[6][1]
        msgs = []
        for _ in range(18):
            sender = rng.choice([DEMO_OWNER, friend])
            m = {"senderName": sender, "timestamp": ts(), "text": rng.choice(DEMO_LINES), "isUnsent": False, "media": [], "reactions": [], "type": "text"}
            if rng.random() < 0.15:
                fname = f"media/{rng.randint(10**8, 10**9)}.jpg"
                z.writestr(fname, jpeg())
                m.update(text="", media=[{"uri": fname}], type="media")
            msgs.append(m)
        msgs.sort(key=lambda x: x["timestamp"], reverse=True)
        z.writestr(f"{friend}.json", json.dumps({"participants": [DEMO_OWNER, friend], "threadName": friend, "messages": msgs}, ensure_ascii=False, indent=2))
    stamp = now.strftime("%Y%m%d")
    return [(f"facebook-somchai-{stamp}-part1.zip", dyi.getvalue()), (f"messenger-secure-storage-{stamp}.zip", e2ee.getvalue())]
