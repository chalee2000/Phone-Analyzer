"""LINE "Export chat history" text files (Android and iPhone, Thai and English).

LINE keeps its database in app-private storage, so a phone without root cannot
be read directly. LINE itself can export each chat as text (chat → ≡ →
Settings → Export chat history). This module reads those files, from the phone
during an Android extraction or chosen on the computer.

A file looks like::

    [LINE] ประวัติการแชทกับ สมชาย            ← title line
    วันที่บันทึก: 11/11/2569 13:40            ← saved-on line (ignored)

    พ., 11/11/2569                            ← date header
    13:01<TAB>สมชาย<TAB>สวัสดี                 ← time, sender, message
    13:02<TAB>เจ้าของ<TAB>"สองบรรทัด            ← multi-line messages are quoted
    บรรทัดที่สอง"

Formats differ by platform, language and version (date order, Buddhist-era
years, AM/PM, weekday names, quoting), so parsing is tolerant: the date order
is chosen from the evidence (a day above 12 settles it; otherwise the order
in which the headers keep going forward in time).
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import ChatMessage

APP = "LINE"
ME = "ฉัน"

TITLE_PREFIXES = (
    "chat history with", "chat history in", "chat with", "chats with", "talk history with",
    "ประวัติการแชทกับ", "ประวัติการแชตกับ", "ประวัติแชทกับ", "ประวัติแชตกับ",
    "ประวัติการแชทใน", "ประวัติการแชตใน", "ประวัติการแชทในกลุ่ม", "แชทกับ", "แชตกับ",
)
GROUP_HINTS = ("chat history in", "ประวัติการแชทใน", "ประวัติการแชตใน", "ประวัติการแชทในกลุ่ม")
SELF_NAMES = {"me", "ฉัน", "คุณ", "you"}

DATE_YMD = re.compile(r"(?<!\d)(\d{4})[./-](\d{1,2})[./-](\d{1,2})(?!\d)")
DATE_XXY = re.compile(r"(?<!\d)(\d{1,2})[./-](\d{1,2})[./-](\d{4})(?!\d)")
MSG = re.compile(r"^(?:(上午|下午|AM|PM|am|pm)\s*)?(\d{1,2})[:.](\d{2})(?:\s*([AaPp]\.?[Mm]\.?|น\.))?\t(.*)$")
MSG_DATED = re.compile(r"^(\d{1,4}[./-]\d{1,2}[./-]\d{1,4})\s+(\d{1,2}[:.]\d{2}.*\t.*)$")  # date on every line
SAVED = re.compile(r"^(saved on|วันที่บันทึก|บันทึกเมื่อ|保存日時)", re.I)

LABELS = [
    (re.compile(r"^\[(photo|photos|image|รูป|รูปภาพ|ภาพ)\]$", re.I), "[รูปภาพ]"),
    (re.compile(r"^\[(sticker|สติกเกอร์|สติ๊กเกอร์)\]$", re.I), "[สติกเกอร์]"),
    (re.compile(r"^\[(video|วิดีโอ|วีดีโอ)\]$", re.I), "[วิดีโอ]"),
    (re.compile(r"^\[(voice message|audio|ข้อความเสียง|ไฟล์เสียง|เสียง)\]$", re.I), "[ข้อความเสียง]"),
    (re.compile(r"^\[(contact|ผู้ติดต่อ|รายชื่อผู้ติดต่อ)\]$", re.I), "[ผู้ติดต่อ]"),
    (re.compile(r"^\[(location|ตำแหน่ง|ตำแหน่งที่ตั้ง)\]$", re.I), "[ตำแหน่ง]"),
    (re.compile(r"^\[(file|ไฟล์)\]$", re.I), "[ไฟล์]"),
    (re.compile(r"^\[(gif)\]$", re.I), "[GIF]"),
]
UNSENT = re.compile(r"(message unsent|unsent a message|ยกเลิกข้อความ|ยกเลิกการส่งข้อความ)", re.I)
CALL = re.compile(r"^☎\s*(.*)$")
DURATION = re.compile(r"(\d{1,2}:\d{2}(?::\d{2})?)")
MISSED = re.compile(r"(missed|no answer|ไม่ได้รับ|ไม่มีผู้รับ)", re.I)
CANCELED = re.compile(r"(cancel|ยกเลิก)", re.I)


@dataclass
class ExportChat:
    source: str
    title: str
    group: bool
    order: str  # "ymd" | "dmy" | "mdy" | "" (no dated lines)
    messages: list[dict[str, Any]] = field(default_factory=list)  # {ts, sender, body}

    @property
    def senders(self) -> list[str]:
        return list(dict.fromkeys(m["sender"] for m in self.messages if m["sender"]))


def decode(data: bytes) -> str:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    for enc in ("utf-8-sig", "cp874"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", "replace")


def is_line_export(data: bytes | str) -> bool:
    text = decode(data[:400]) if isinstance(data, bytes) else data[:400]
    return text.lstrip("﻿ \r\n").startswith("[LINE]")


def _title(first_line: str, name: str) -> tuple[str, bool]:
    rest = first_line.strip().lstrip("﻿")
    rest = rest[len("[LINE]"):].strip() if rest.startswith("[LINE]") else ""
    if not rest:
        rest = Path(name).stem.replace("[LINE]", "").strip()
    low = rest.lower()
    group = any(low.startswith(h) for h in GROUP_HINTS)
    for prefix in sorted(TITLE_PREFIXES, key=len, reverse=True):
        if low.startswith(prefix):
            return rest[len(prefix):].strip(" :") or rest, group
    return rest, group


def _year(y: int) -> int:
    return y - 543 if y > 2400 else y  # Buddhist era


def _date_candidates(line: str) -> tuple[str, tuple[int, int, int]] | None:
    """('ymd', (y, m, d)) or ('xxy', (a, b, y)) for the first date on a header line."""
    m = DATE_YMD.search(line)
    if m:
        return "ymd", (_year(int(m.group(1))), int(m.group(2)), int(m.group(3)))
    m = DATE_XXY.search(line)
    if m:
        return "xxy", (int(m.group(1)), int(m.group(2)), _year(int(m.group(3))))
    return None


def _choose_order(headers: list[tuple[int, int, int]], thai: bool) -> str:
    """Day-month or month-day for dd/mm/yyyy-like headers."""
    if any(a > 12 for a, _, _ in headers):
        return "dmy"
    if any(b > 12 for _, b, _ in headers):
        return "mdy"

    def forward(order: str) -> int:
        dates = []
        for a, b, y in headers:
            try:
                dates.append(datetime(y, a, b) if order == "mdy" else datetime(y, b, a))
            except ValueError:
                return -1
        return sum(1 for x, y in zip(dates, dates[1:]) if y >= x)

    dmy, mdy = forward("dmy"), forward("mdy")
    if dmy != mdy:
        return "dmy" if dmy > mdy else "mdy"
    return "dmy" if thai else "mdy"


def _to_date(kind: str, parts: tuple[int, int, int], order: str) -> datetime | None:
    try:
        if kind == "ymd":
            y, m, d = parts
        elif order == "mdy":
            m, d, y = parts
        else:
            d, m, y = parts
        return datetime(y, m, d)
    except ValueError:
        return None


def _hour(h: int, ampm: str | None, prefix: str | None) -> int:
    tag = (ampm or prefix or "").lower().replace(".", "")
    if tag in ("pm", "下午") and h < 12:
        return h + 12
    if tag in ("am", "上午") and h == 12:
        return 0
    return h


def normalize_body(text: str) -> str:
    t = text.strip()
    for rx, label in LABELS:
        if rx.match(t):
            return label
    if UNSENT.search(t) and len(t) < 80:
        return "[ยกเลิกการส่งข้อความ]"
    m = CALL.match(t)
    if m:
        rest = m.group(1)
        dur = DURATION.search(rest)
        if dur and not MISSED.search(rest):
            return f"[โทรผ่าน LINE {dur.group(1)}]"
        if MISSED.search(rest):
            return "[สายที่ไม่ได้รับผ่าน LINE]"
        if CANCELED.search(rest):
            return "[ยกเลิกการโทรผ่าน LINE]"
        return f"[การโทรผ่าน LINE] {rest}".strip()
    return t


def parse_text(name: str, text: str) -> ExportChat:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    title, group = _title(lines[0] if lines else "", name)
    thai = bool(re.search(r"[฀-๿]", "\n".join(lines[:3])))
    # First pass: date headers, to settle dd/mm vs mm/dd.
    xxy = [c[1] for ln in lines[1:] if not MSG.match(ln) and not SAVED.match(ln.strip()) and (c := _date_candidates(ln)) and c[0] == "xxy"]
    order = _choose_order(xxy, thai) if xxy else ("ymd" if any(DATE_YMD.search(ln) for ln in lines[1:]) else "")
    chat = ExportChat(source=name, title=title, group=group, order=order)
    day: datetime | None = None
    quoted = False
    for raw in lines[1:]:
        line = raw.rstrip("\n")
        dated = MSG_DATED.match(line)
        if dated:
            cand = _date_candidates(dated.group(1))
            if cand:
                day = _to_date(cand[0], cand[1], order) or day
                line = dated.group(2)
        if quoted:
            if (MSG.match(line) and day is not None) or dated:
                quoted = False  # an unbalanced quote: the next message has started
            else:
                msg = chat.messages[-1]
                if line.endswith('"'):
                    msg["body"] += "\n" + line[:-1]
                    quoted = False
                else:
                    msg["body"] += "\n" + line
                continue
        m = MSG.match(line)
        if m and day is not None:
            prefix, hh, mm, ampm, rest = m.groups()
            parts = rest.split("\t", 1)
            sender, body = (parts[0], parts[1]) if len(parts) == 2 else ("", parts[0])
            if body.startswith('"') and not (len(body) > 1 and body.endswith('"')):
                body, quoted = body[1:], True
            elif len(body) > 1 and body.startswith('"') and body.endswith('"') and "\n" not in body:
                body = body[1:-1]
            ts = day.replace(hour=_hour(int(hh), ampm, prefix) % 24, minute=int(mm))
            chat.messages.append({"ts": int(ts.timestamp() * 1000), "sender": sender.strip(), "body": body})
            continue
        if not line.strip() or SAVED.match(line.strip()):
            continue
        cand = _date_candidates(line)
        if cand and len(line) < 60 and "\t" not in line:
            day = _to_date(cand[0], cand[1], order) or day
            continue
        if chat.messages:  # an unquoted continuation line
            chat.messages[-1]["body"] += "\n" + line
    for msg in chat.messages:
        msg["body"] = normalize_body(msg["body"]) if "\n" not in msg["body"] else msg["body"].strip()
    return chat


def parse_bytes(name: str, data: bytes) -> ExportChat:
    return parse_text(name, decode(data))


def guess_owner(chats: list[ExportChat]) -> tuple[str, list[dict[str, Any]]]:
    """The exporting account: a self name, the other side of 1:1 titles, or whoever is in every chat."""
    in_chats: Counter[str] = Counter()
    sent: Counter[str] = Counter()
    hints: Counter[str] = Counter()
    for c in chats:
        senders = c.senders
        for s in senders:
            in_chats[s] += 1
        for m in c.messages:
            if m["sender"]:
                sent[m["sender"]] += 1
        if not c.group and c.title in senders:
            for s in senders:
                if s != c.title:
                    hints[s] += 1
    names = list(in_chats)
    selfish = [n for n in names if n.lower() in SELF_NAMES]
    ranked = sorted(names, key=lambda n: (n in selfish, hints[n], in_chats[n], sent[n]), reverse=True)
    owner = ranked[0] if ranked and (selfish or hints or len(chats) > 1) else ""
    candidates = [{"name": n, "threads": in_chats[n], "messages": sent[n]} for n in ranked[:12]]
    return owner, candidates


def to_messages(chats: list[ExportChat], owner: str) -> list[ChatMessage]:
    out: list[ChatMessage] = []
    seen: set[tuple[str, int, str, str]] = set()
    for c in chats:
        for m in c.messages:
            key = (c.title, m["ts"], m["sender"], m["body"])
            if key in seen:
                continue
            seen.add(key)
            mine = bool(owner) and m["sender"] == owner
            sender = ME if mine else (m["sender"] or c.title)
            body = m["body"] if m["sender"] else f"[ห้องสนทนา] {m['body']}"
            out.append(ChatMessage(app=APP, thread=c.title, sender=sender, body=body, direction="out" if mine else "in", timestamp=m["ts"]))
    out.sort(key=lambda x: x.timestamp or 0, reverse=True)
    return out


# ── import from the computer (files, folders or a zip of exports) ──────
def _read_inputs(paths: list[str]) -> tuple[list[tuple[str, str, bytes]], list[str]]:
    """(source path, name, bytes) of every LINE export among the inputs."""
    import zipfile

    found: list[tuple[str, str, bytes]] = []
    skipped: list[str] = []
    for p in paths:
        path = Path(p)
        if not path.exists():
            raise ValueError("not_found")
        if path.is_dir():
            items = [(str(f), f.name, f.read_bytes()) for f in sorted(path.rglob("*.txt")) if f.stat().st_size < 50 << 20]
        elif zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as z:
                items = [(f"{path}:{i.filename}", Path(i.filename).name, z.read(i)) for i in z.infolist()
                         if i.filename.lower().endswith(".txt") and i.file_size < 50 << 20]
        else:
            items = [(str(path), path.name, path.read_bytes())]
        for src, name, data in items:
            if is_line_export(data):
                found.append((src, name, data))
            else:
                skipped.append(name)
    return found, skipped


def load(paths: list[str]) -> tuple[list[ExportChat], list[tuple[str, str, bytes]], list[str]]:
    files, skipped = _read_inputs(paths)
    if not files:
        raise ValueError("line_no_chats")
    return [parse_bytes(name, data) for _, name, data in files], files, skipped


def preview(paths: list[str]) -> dict[str, Any]:
    chats, files, skipped = load(paths)
    owner, candidates = guess_owner(chats)
    times = [m["ts"] for c in chats for m in c.messages]
    return {
        "owner": owner,
        "candidates": candidates,
        "threads": len(chats),
        "e2ee_threads": 0,
        "requests": 0,
        "messages": sum(len(c.messages) for c in chats),
        "media": sum(1 for c in chats for m in c.messages if m["body"].startswith(("[รูปภาพ]", "[วิดีโอ]", "[ข้อความเสียง]", "[ไฟล์]"))),
        "first": min(times) if times else None,
        "last": max(times) if times else None,
        "sources": [{"name": name, "size": len(data), "path": src} for src, name, data in files],
        "warnings": (["skipped_files"] if skipped else []) + (["no_owner"] if not owner else []),
        "skipped": skipped,
    }


def import_into(case, paths: list[str], owner: str = "", examiner: str = "", progress=None) -> dict[str, Any]:
    import hashlib

    from .models import ALL_KINDS
    from .util import safe_name

    say = progress or (lambda step, f: None)
    say("read", 0.05)
    chats, files, skipped = load(paths)
    guessed, _ = guess_owner(chats)
    owner = (owner or guessed).strip()
    serial = "line-" + hashlib.sha1((owner or "unknown").encode("utf-8")).hexdigest()[:10]
    device = {
        "platform": "line", "serial": serial, "brand": "LINE", "model": "LINE",
        "market_name": f"LINE · {owner}" if owner else "LINE (ไฟล์ส่งออกแชต)", "phone_number": "", "os_version": "",
        "accounts": [owner] if owner else [], "restricted": {}, "extra": {"source_files": str(len(files)), "owner": owner},
    }
    ext = case.create_extraction(device, "line-export", examiner)
    say("save", 0.5)
    for i, (src, name, data) in enumerate(files, 1):
        dest = ext.raw_dir / "line_export" / f"{i:03d}_{safe_name(name, 'chat.txt')}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        digest = ext.register_file(dest, f"import:{src}")
        ext.audit("line.export.source", f"{src} size={len(data)} sha256={digest}")
    msgs = to_messages(chats, owner)
    ext.set_records("chats", [m.to_dict() for m in msgs])
    for kind in ALL_KINDS:
        if kind != "chats":
            ext.set_unavailable(kind, "not_supported", "LINE chat export")
    ext.audit("line.export.import", f"owner={owner} chats={len(chats)} messages={len(msgs)} skipped_files={len(skipped)}")
    counts = ext.finish("completed")
    say("done", 1.0)
    return {"extraction_id": ext.id, "owner": owner, "threads": len(chats), "counts": counts, "missing_media": 0}


# ── demo files (training, tests, screenshots) ─────────────────────────
def demo_files() -> list[tuple[str, bytes]]:
    """Two exports as LINE writes them: Thai (Android, BE dates) and English (iPhone)."""
    import random
    from datetime import timedelta

    from .demo import SHARED_PEOPLE

    rng = random.Random(9090)
    owner = "สมชาย ใจดี"
    now = datetime.now().replace(second=0, microsecond=0)
    lines_th = ["ของถึงยัง", "เดี๋ยวโอนให้", "อย่าโทรนะ พิมพ์มา", "เจอกันที่เดิม", "รับทราบครับ", "ส่งพิกัดมา", "ลบแชตด้วย", "[รูป]", "[สติกเกอร์]", "☎ ระยะเวลาการโทร 1:42", "☎ สายที่ไม่ได้รับ"]
    out = []
    friend = SHARED_PEOPLE[0][1]
    body = [f"[LINE] ประวัติการแชทกับ {friend}", f"วันที่บันทึก: {now:%d/%m}/{now.year + 543} {now:%H:%M}", ""]
    for d in range(12, 0, -3):
        day = now - timedelta(days=d)
        body += ["", f"{'จ.อ.พ.พฤ.ศ.ส.อา.'.split('.')[day.weekday()]}., {day:%d/%m}/{day.year + 543}"]
        t = day.replace(hour=rng.randint(8, 12), minute=0)
        for _ in range(rng.randint(4, 8)):
            t += timedelta(minutes=rng.randint(1, 40))
            who = rng.choice([owner, friend])
            text = rng.choice(lines_th)
            if rng.random() < 0.1:
                text = '"ของ 2 ชิ้น\nส่งพรุ่งนี้เช้า"'
            body.append(f"{t:%H:%M}\t{who}\t{text}")
    out.append((f"[LINE] แชทกับ {friend}.txt", "\n".join(body).encode("utf-8")))
    group = "ทีมส่งของ"
    members = [owner] + [p[1] for p in SHARED_PEOPLE[1:4]]
    body = [f"[LINE] Chat history in {group}", f"Saved on: {now:%Y/%m/%d %H:%M}", ""]
    for d in range(10, 0, -2):
        day = now - timedelta(days=d)
        body += ["", f"{day:%a, %Y/%m/%d}"]
        t = day.replace(hour=rng.randint(18, 21), minute=0)
        for _ in range(rng.randint(3, 6)):
            t += timedelta(minutes=rng.randint(1, 25))
            h12 = t.hour % 12 or 12
            body.append(f"{h12}:{t:%M}{'PM' if t.hour >= 12 else 'AM'}\t{rng.choice(members)}\t{rng.choice(['On my way', 'ok', '[Photo]', '[Sticker]', 'คืนนี้สองทุ่ม', 'Message unsent'])}")
    out.append((f"[LINE] Chat in {group}.txt", "\n".join(body).encode("utf-8")))
    return out
