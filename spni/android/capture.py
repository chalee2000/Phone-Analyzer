"""Chat screen capture for apps whose data needs root (LINE, Messenger, …).

The examiner opens one chat on the unlocked phone. The program then repeats:

1. ``screencap -p`` → pull → SHA-256 (every page is kept as evidence)
2. ``uiautomator dump`` → pull → the on-screen texts with their positions
3. ``input swipe`` downwards, which scrolls the chat to older messages

until two screenshots in a row are identical (the first message is
reached), the page limit is hit or the examiner presses stop. Every ADB
command goes through the audited transport.

Pages become one conversation: texts on the right are sent, on the left
received; time labels and date separators give timestamps; overlapping
pages are stitched; pictures in bubbles are cut out of the screenshot so
they can be seen in the chat. If an app hides its texts from uiautomator,
the screenshots are still saved.
"""

from __future__ import annotations

import hashlib
import re
import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from PIL import Image

from ..models import ChatMessage, Photo

APPS = {
    "jp.naver.line.android": "LINE",
    "com.facebook.orca": "Messenger",
    "com.facebook.mlite": "Messenger Lite",
    "com.whatsapp": "WhatsApp",
    "org.telegram.messenger": "Telegram",
    "com.instagram.android": "Instagram",
    "com.zhiliaoapp.musically": "TikTok",
    "com.ss.android.ugc.trill": "TikTok",
}
ME = "ฉัน"
REMOTE_SHOT = "/sdcard/spni_capture.png"
REMOTE_DUMP = "/sdcard/spni_capture.xml"

TIME_RE = re.compile(r"^(?:(?:AM|PM|am|pm|ก่อนเที่ยง|หลังเที่ยง)\s*)?(\d{1,2})[:.](\d{2})(?:\s*([AaPp]\.?[Mm]\.?|น\.))?$")
READ_RE = re.compile(r"^(read|seen|อ่านแล้ว|เห็นแล้ว)(\s*\d+)?$", re.I)
THAI_MONTHS = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
EN_MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
TODAY = ("วันนี้", "today")
YESTERDAY = ("เมื่อวาน", "yesterday")
WEEKDAYS = [("จ.", "จันทร์", "mon"), ("อ.", "อังคาร", "tue"), ("พ.", "พุธ", "wed"), ("พฤ.", "พฤหัส", "thu"),
            ("ศ.", "ศุกร์", "fri"), ("ส.", "เสาร์", "sat"), ("อา.", "อาทิตย์", "sun")]


@dataclass
class Node:
    text: str
    desc: str
    cls: str
    rid: str
    package: str
    box: tuple[int, int, int, int]

    @property
    def cx(self) -> float:
        return (self.box[0] + self.box[2]) / 2

    @property
    def width(self) -> int:
        return self.box[2] - self.box[0]

    @property
    def height(self) -> int:
        return self.box[3] - self.box[1]


@dataclass
class Item:
    kind: str  # msg | image | time | date
    text: str
    side: str  # in | out | center
    box: tuple[int, int, int, int]
    page: int = 0
    crop: str = ""  # image items: relative path of the picture cut from the screenshot
    key: str = ""

    def ident(self) -> tuple[str, str, str]:
        return (self.kind, self.side, self.key or self.text)


@dataclass
class Page:
    title: str
    package: str
    items: list[Item]
    width: int
    height: int


def _box(text: str) -> tuple[int, int, int, int] | None:
    m = re.match(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]", text or "")
    return tuple(int(v) for v in m.groups()) if m else None  # type: ignore[return-value]


def parse_dump(xml_text: str) -> tuple[list[Node], int, int]:
    """Nodes with a box from a ``uiautomator dump`` file, plus the screen size."""
    root = ET.fromstring(xml_text)
    nodes: list[Node] = []
    width = height = 0
    for el in root.iter("node"):
        box = _box(el.get("bounds", ""))
        if not box:
            continue
        width, height = max(width, box[2]), max(height, box[3])
        nodes.append(Node(el.get("text", "") or "", el.get("content-desc", "") or "", el.get("class", "") or "",
                          el.get("resource-id", "") or "", el.get("package", "") or "", box))
    return nodes, width, height


def _looks_like_date(text: str) -> bool:
    t = text.strip().lower()
    return (t in TODAY or t in YESTERDAY or any(m in text for m in THAI_MONTHS) or any(m in t for m in EN_MONTHS)
            or bool(re.search(r"\d{1,4}[./-]\d{1,2}([./-]\d{1,4})?", t))
            or any(t.startswith(w[0].lower()) or t.startswith(w[1]) or t.startswith(w[2]) for w in WEEKDAYS))


def page_from_dump(nodes: list[Node], width: int, height: int, page: int = 0) -> Page:
    """Classify the visible nodes of one chat screen."""
    head_bottom, foot_top = height * 0.12, height * 0.90
    package = next((n.package for n in nodes if n.package), "")
    header = [n for n in nodes if n.text.strip() and n.box[1] >= height * 0.02 and n.box[3] <= head_bottom
              and not TIME_RE.match(n.text.strip()) and "%" not in n.text]
    header.sort(key=lambda n: (n.box[1], n.box[0]))
    title = header[0].text.strip() if header else ""
    items: list[Item] = []
    for n in nodes:
        mid_y = (n.box[1] + n.box[3]) / 2
        if mid_y <= head_bottom or mid_y >= foot_top or n.width <= 0 or n.height <= 0:
            continue
        text = n.text.strip()
        side = "out" if n.cx > width * 0.55 else "in" if n.cx < width * 0.45 else "center"
        if text:
            if READ_RE.match(text):
                continue
            if TIME_RE.match(text):
                items.append(Item("time", text, side if side != "center" else "in", n.box, page))
            elif side == "center" and n.width < width * 0.7 and _looks_like_date(text):
                items.append(Item("date", text, "center", n.box, page))
            else:
                items.append(Item("msg", text, side if side != "center" else ("out" if n.box[2] > width * 0.9 else "in"), n.box, page))
        elif n.cls.endswith("ImageView") and n.width >= width * 0.2 and n.height >= height * 0.08:
            items.append(Item("image", n.desc.strip(), side if side != "center" else "in", n.box, page))
    items.sort(key=lambda i: (i.box[1], i.box[0]))
    # A time label belongs to the bubble it sits beside (left of sent bubbles, right of received ones).
    bubbles = [i for i in items if i.kind in ("msg", "image")]
    for it in items:
        if it.kind != "time" or not bubbles:
            continue
        near = min(bubbles, key=lambda b: (abs(b.box[3] - it.box[3]), min(abs(b.box[0] - it.box[2]), abs(it.box[0] - b.box[2]))))
        if abs(near.box[3] - it.box[3]) <= height * 0.05:
            it.side = near.side
    return Page(title=title, package=package, items=items, width=width, height=height)


def cut_pictures(page: Page, shot: Path, out_dir: Path, rel: Callable[[Path], str]) -> None:
    """Crop picture bubbles that are fully on screen; key them by their pixels for stitching."""
    try:
        img = Image.open(shot).convert("RGB")
    except OSError:
        return
    top, bottom = page.height * 0.12, page.height * 0.90
    keep: list[Item] = []
    for it in page.items:
        if it.kind != "image":
            keep.append(it)
            continue
        x1, y1, x2, y2 = it.box
        if y1 <= top + 2 or y2 >= bottom - 2:  # cut by the screen edge: whole on another page
            continue
        crop = img.crop((x1, y1, x2, y2))
        small = crop.convert("L").resize((16, 16))
        it.key = hashlib.md5(small.tobytes()).hexdigest()
        path = out_dir / f"{it.key[:16]}.png"
        if not path.exists():
            out_dir.mkdir(parents=True, exist_ok=True)
            crop.save(path)
        it.crop = rel(path)
        keep.append(it)
    page.items = keep


def stitch(pages: list[Page]) -> list[Item]:
    """Pages captured newest-first (scrolling up) → one list, oldest first, overlaps removed."""
    seq: list[Item] = []
    for page in pages:
        items = [i for i in page.items]
        if not seq:
            seq = items
            continue
        merged = False
        for k in range(min(len(items), len(seq)), 0, -1):
            tail = [i.ident() for i in items[-k:]]
            for offset in range(0, 3):
                if [i.ident() for i in seq[offset:offset + k]] == tail:
                    seq = items[:-k] + seq[offset:]
                    merged = True
                    break
            if merged:
                break
        if not merged:
            seq = items + seq
    return seq


def parse_date_label(text: str, today: date) -> date | None:
    t = text.strip()
    low = t.lower()
    if any(low.startswith(w) for w in TODAY):
        return today
    if any(low.startswith(w) for w in YESTERDAY):
        return today - timedelta(days=1)
    day = month = year = None
    m = re.search(r"(\d{4})[./-](\d{1,2})[./-](\d{1,2})", t)
    if m:
        year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        m = re.search(r"(\d{1,2})[./-](\d{1,2})(?:[./-](\d{2,4}))?", t)
        if m:
            day, month = int(m.group(1)), int(m.group(2))
            year = int(m.group(3)) if m.group(3) else None
            if month > 12 >= day:  # month/day (US English)
                day, month = month, day
        else:
            for i, name in enumerate(THAI_MONTHS):
                if name in t:
                    month = i + 1
            for i, name in enumerate(EN_MONTHS):
                if name in low:
                    month = i + 1
            d = re.search(r"(?<!\d)(\d{1,2})(?!\d)", t)
            y = re.search(r"(?<!\d)(\d{4})(?!\d)", t)
            day = int(d.group(1)) if d and month else None
            year = int(y.group(1)) if y else None
    if day and month:
        if year and year < 100:
            year += 2000
        if year and year > 2400:
            year -= 543
        try:
            result = date(year or today.year, month, day)
        except ValueError:
            return None
        if not year and result > today:
            result = result.replace(year=today.year - 1)
        return result
    for i, names in enumerate(WEEKDAYS):  # a weekday alone: the latest such day
        if any(low.startswith(n.lower()) for n in names):
            back = (today.weekday() - i) % 7
            return today - timedelta(days=back)
    return None


def _clock(text: str) -> tuple[int, int] | None:
    m = TIME_RE.match(text.strip())
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    tag = (m.group(3) or "").lower().replace(".", "")
    lead = text.strip().lower()
    if (tag == "pm" or lead.startswith(("pm", "หลังเที่ยง"))) and h < 12:
        h += 12
    if (tag == "am" or lead.startswith(("am", "ก่อนเที่ยง"))) and h == 12:
        h = 0
    return (h, mi) if h < 24 and mi < 60 else None


def to_messages(items: list[Item], app: str, thread: str, today: date) -> list[ChatMessage]:
    """Oldest-first items → chat messages with timestamps where the screen showed them."""
    out: list[tuple[Item, ChatMessage]] = []
    cur: date | None = None
    untimed: list[ChatMessage] = []
    for it in items:
        if it.kind == "date":
            cur = parse_date_label(it.text, today) or cur
            untimed = []
            continue
        if it.kind == "time":
            hm = _clock(it.text)
            if hm and cur:
                ts = int(datetime(cur.year, cur.month, cur.day, *hm).timestamp() * 1000)
                for msg in untimed:
                    if msg.timestamp is None:
                        msg.timestamp = ts
            untimed = []
            continue
        body = it.text if it.kind == "msg" else ("[รูปภาพ]" if not it.text else f"[รูปภาพ] {it.text}")
        mine = it.side == "out"
        msg = ChatMessage(app=app, thread=thread, sender=ME if mine else thread, body=body,
                          direction="out" if mine else "in", attachment=it.crop)
        out.append((it, msg))
        untimed.append(msg)
    return [m for _, m in out]


# ── the capture job ─────────────────────────────────────────────────────
@dataclass
class CaptureResult:
    pages: int = 0
    title: str = ""
    app: str = ""
    messages: list[ChatMessage] = field(default_factory=list)
    shots: list[Photo] = field(default_factory=list)
    pictures: list[Photo] = field(default_factory=list)
    text_pages: int = 0
    reached_top: bool = False
    stopped: bool = False


class Capture:
    """Runs on a worker thread; ``stop()`` ends it after the current page."""

    def __init__(self, transport: Any, ctx: Any, max_pages: int = 200, title: str = "",
                 progress: Callable[[dict[str, Any]], None] | None = None, settle: float = 0.8) -> None:
        self.t = transport
        self.ctx = ctx
        self.max_pages = max(1, min(int(max_pages or 200), 2000))
        self.title_override = (title or "").strip()
        self.progress = progress or (lambda info: None)
        self.settle = settle
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> CaptureResult:
        ext = self.ctx.extraction
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        folder = ext.media_dir / "capture" / stamp
        res = CaptureResult()
        pages: list[Page] = []
        last_digest = ""
        size = (1080, 2400)
        for n in range(1, self.max_pages + 1):
            if self._stop.is_set():
                res.stopped = True
                break
            shot = folder / f"page_{n:03d}.png"
            shot.parent.mkdir(parents=True, exist_ok=True)
            self.t.shell(f"screencap -p {REMOTE_SHOT}", timeout=30)
            self.t.pull(REMOTE_SHOT, shot)
            digest = hashlib.sha256(shot.read_bytes()).hexdigest()
            if digest == last_digest:  # the screen did not move: the first message is on screen
                shot.unlink(missing_ok=True)
                res.reached_top = True
                break
            last_digest = digest
            page = Page("", "", [], *size)
            out = self.t.shell(f"uiautomator dump {REMOTE_DUMP}", timeout=60)
            dump = folder / f"page_{n:03d}.xml"
            try:
                if "ERROR" in out.upper():
                    raise ValueError(out.strip()[:120])
                self.t.pull(REMOTE_DUMP, dump)
                nodes, w, h = parse_dump(dump.read_text(encoding="utf-8", errors="replace"))
                size = (w or size[0], h or size[1])
                page = page_from_dump(nodes, *size, page=n)
                cut_pictures(page, shot, folder / "pictures", ext.rel)
                self.ctx.register(dump, REMOTE_DUMP + f" (page {n})")
                res.text_pages += 1
            except (ValueError, ET.ParseError, OSError) as exc:
                self.ctx.audit("capture.text_unavailable", f"page {n}: {exc}")
            pages.append(page)
            res.pages = n
            res.title = res.title or self.title_override or page.title
            res.app = res.app or APPS.get(page.package, page.package)
            res.shots.append(self.ctx.photo_record(shot, f"{REMOTE_SHOT} (page {n})", album="", modified=int(time.time() * 1000)))
            self.progress({"page": n, "max": self.max_pages, "title": res.title, "app": res.app,
                           "messages": sum(len(p.items) for p in pages), "preview": ext.rel(shot)})
            w, h = size
            self.t.shell(f"input swipe {w // 2} {int(h * 0.32)} {w // 2} {int(h * 0.80)} 450", timeout=20)
            time.sleep(self.settle)
        self.t.shell(f"rm -f {REMOTE_SHOT} {REMOTE_DUMP}", timeout=20)
        thread = res.title or "แชตจากหน้าจอ"
        app = res.app or "แชต"
        album = f"บันทึกหน้าจอ {app}: {thread}"
        for p in res.shots:
            p.album = album
        items = stitch(pages)
        res.messages = to_messages(items, app, thread, date.today())
        seen: set[str] = set()
        for it in items:
            if it.kind == "image" and it.crop and it.crop not in seen:
                seen.add(it.crop)
                res.pictures.append(self.ctx.photo_record(ext.dir / it.crop, f"screen capture page {it.page}",
                                                          album=f"{app} (จากหน้าจอ): {thread}", modified=None))
        return res
