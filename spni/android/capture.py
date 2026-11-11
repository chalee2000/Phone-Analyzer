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

"All chats" mode (``package=…``) drives the app itself: it opens LINE or
Messenger, goes to the chat list, opens each chat in turn (``input tap``),
captures it as above, goes back (``input keyevent 4``) and scrolls the list
for more, until every chat was seen, the chat limit is hit or the examiner
presses stop. It only taps chat rows, the "Chats" tab and Back: it never
types. Opening a chat marks it as read, so the phone should be in airplane
mode (USB keeps working).
"""

from __future__ import annotations

import hashlib
import logging
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
from ..util import local_ms, safe_name

log = logging.getLogger("spni.capture")

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
# The apps the "all chats" mode can drive (key used by the UI → package).
CHAT_APPS = {"line": "jp.naver.line.android", "messenger": "com.facebook.orca"}
ME = "ฉัน"
REMOTE_SHOT = "/sdcard/spni_capture.png"
REMOTE_DUMP = "/sdcard/spni_capture.xml"

TIME_RE = re.compile(r"^(?:(?:AM|PM|am|pm|ก่อนเที่ยง|หลังเที่ยง)\s*)?(\d{1,2})[:.](\d{2})(?:\s*([AaPp]\.?[Mm]\.?|น\.))?$")
READ_RE = re.compile(r"^(read|seen|อ่านแล้ว|เห็นแล้ว)(\s*\d+)?$", re.I)
THAI_MONTHS = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
EN_MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
TODAY = ("วันนี้", "today")
YESTERDAY = ("เมื่อวาน", "yesterday")
CHAT_TAB_RE = re.compile(r"^(แชท|แชต|chats?|ห้องแชท|チャット|トーク)$", re.I)
SEARCH_RE = re.compile(r"(ค้นหา|search|meta ai)", re.I)
BADGE_RE = re.compile(r"^\d{1,4}\+?$")
BUTTON_RE = re.compile(r"^(send|ส่ง|like|ถูกใจ|camera|กล้อง|gallery|แกลเลอรี|voice( message)?|ข้อความเสียง|emoji|อีโมจิ|stickers?|สติกเกอร์|"
                       r"more|เพิ่มเติม|back|ย้อนกลับ|กลับ|navigate up|call|โทร|audio call|video call|วิดีโอคอล|info|ข้อมูล|menu|เมนู)$", re.I)
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
    clickable: bool = False
    scrollable: bool = False
    selected: bool = False

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
                          el.get("resource-id", "") or "", el.get("package", "") or "", box,
                          el.get("clickable") == "true", el.get("scrollable") == "true", el.get("selected") == "true"))
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
    texts = [n for n in nodes if n.text.strip()]
    for n in nodes:
        mid_y = (n.box[1] + n.box[3]) / 2
        if mid_y <= head_bottom or mid_y >= foot_top or n.width <= 0 or n.height <= 0:
            continue
        text = n.text.strip()
        if not text and _desc_is_text(n, texts, width, height):
            text = n.desc.strip()
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


def _inside(inner: tuple[int, int, int, int], outer: tuple[int, int, int, int]) -> bool:
    return inner[0] >= outer[0] and inner[1] >= outer[1] and inner[2] <= outer[2] and inner[3] <= outer[3]


def _desc_is_text(n: Node, texts: list[Node], width: int, height: int) -> bool:
    """Some apps (Messenger) put a bubble's words only in its content-desc."""
    desc = n.desc.strip()
    if not desc or n.cls.endswith(("ImageView", "EditText", "Button", "ImageButton")) or BUTTON_RE.match(desc):
        return False
    if n.width < width * 0.15 or n.width > width * 0.92 or n.height > height * 0.5:
        return False
    return not any(_inside(t.box, n.box) for t in texts)  # a real text node already carries it


# ── the chat list ("all chats" mode) ────────────────────────────────────
@dataclass
class Row:
    title: str
    preview: str
    box: tuple[int, int, int, int]

    @property
    def key(self) -> str:
        return f"{self.title}|{self.preview[:24]}"

    @property
    def center(self) -> tuple[int, int]:
        return (self.box[0] + self.box[2]) // 2, (self.box[1] + self.box[3]) // 2


def chat_rows(nodes: list[Node], width: int, height: int) -> list[Row]:
    """The chat rows visible on a chat-list screen, top to bottom.

    A row is a full-width tappable strip in the list area; its title is its
    first text (LINE) or the first part of its content-desc (Messenger).
    Search boxes, story carousels, times and unread badges are left out.
    """
    any_clickable = any(n.clickable for n in nodes)
    cands = [n for n in nodes
             if (n.clickable or not any_clickable) and n.width >= width * 0.85
             and height * 0.05 <= n.height <= height * 0.16
             and height * 0.08 <= (n.box[1] + n.box[3]) / 2 <= height * 0.96
             and not n.cls.endswith("EditText")]
    cands.sort(key=lambda n: -(n.width * n.height))
    rows: list[Row] = []
    for c in cands:
        if any(min(c.box[3], r.box[3]) - max(c.box[1], r.box[1]) > c.height * 0.5 for r in rows):
            continue  # nested in (or overlapping) a row already taken
        inner = [n for n in nodes if n is not c and _inside(n.box, c.box)]
        if any(n.cls.endswith("EditText") for n in inner):
            continue
        words = [n.text.strip() for n in [c, *inner] if n.text.strip()] + [n.desc.strip() for n in [c, *inner] if n.desc.strip()]
        if any(SEARCH_RE.search(w) for w in words[:3]):
            continue
        texts = [n for n in [c, *inner] if n.text.strip() and n.box[0] < width * 0.7
                 and not TIME_RE.match(n.text.strip()) and not BADGE_RE.match(n.text.strip())]
        texts.sort(key=lambda n: (n.box[1] // 12, n.box[0]))
        if texts:
            title = texts[0].text.strip()
            preview = texts[1].text.strip() if len(texts) > 1 else ""
        else:
            desc = next((n.desc.strip() for n in [c, *inner] if n.desc.strip()), "")
            parts = [p.strip() for p in desc.split(",")]
            title, preview = parts[0], (parts[1] if len(parts) > 1 else "")
        if title:
            rows.append(Row(title, preview, c.box))
    rows.sort(key=lambda r: r.box[1])
    return rows


def chat_tab(nodes: list[Node], height: int) -> Node | None:
    """The "Chats" tab of the app's navigation bar (LINE opens on Home)."""
    for n in nodes:
        label = n.text.strip() or n.desc.strip().split(",")[0].strip()
        mid = (n.box[1] + n.box[3]) / 2
        if label and CHAT_TAB_RE.match(label) and (mid >= height * 0.85 or mid <= height * 0.2):
            return n
    return None


def is_chat_screen(nodes: list[Node], width: int, height: int, title: str = "") -> bool:
    """An open conversation: a message box at the bottom, or the chat's name as the header."""
    if any(n.cls.endswith("EditText") and (n.box[1] + n.box[3]) / 2 >= height * 0.7 for n in nodes):
        return True
    if title:
        head = page_from_dump(nodes, width, height).title
        return bool(head) and (head.startswith(title[:12]) or title.startswith(head[:12]))
    return False


def merge_captured(old: list[dict], new: list[dict], complete: set[tuple[str, str]]) -> list[dict]:
    """Add captured messages to the ones already in the case without doubling them.

    A chat captured back to its first message replaces what an earlier
    capture had for it; otherwise only messages not seen before are added.
    """
    def key(m: dict) -> tuple:
        return (m.get("app"), m.get("thread"), m.get("direction"), m.get("body"), m.get("timestamp"))

    kept = [m for m in old if (m.get("app"), m.get("thread")) not in complete]
    seen = {key(m) for m in kept}
    out = kept + [m for m in new if (m.get("app"), m.get("thread")) in complete or key(m) not in seen]
    out.sort(key=lambda m: m.get("timestamp") or 0, reverse=True)
    return out


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
        # The older page's bottom overlaps the newer page's top. Either edge can
        # hold a partial item the other page lacks (a picture cut by the screen
        # edge is dropped but its time label stays), so up to two items may be
        # skipped at the older page's end and at the newer page's start.
        for k in range(min(len(items), len(seq)), 0, -1):
            for trim in range(0, 3):
                end = len(items) - trim
                if end - k < 0 or (k < 2 and trim):
                    continue
                tail = [i.ident() for i in items[end - k:end]]
                for offset in range(0, 3):
                    if [i.ident() for i in seq[offset:offset + k]] == tail:
                        seq = items[:end - k] + seq[offset:]
                        merged = True
                        break
                if merged:
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
                ts = local_ms(datetime(cur.year, cur.month, cur.day, *hm))
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
class CaptureError(Exception):
    """A capture that cannot start or go on; ``code`` is shown translated in the UI."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


@dataclass
class ChatCapture:
    title: str = ""
    app: str = ""
    pages: int = 0
    text_pages: int = 0
    reached_top: bool = False
    messages: list[ChatMessage] = field(default_factory=list)
    shots: list[Photo] = field(default_factory=list)
    pictures: list[Photo] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {"title": self.title, "app": self.app, "pages": self.pages, "messages": len(self.messages),
                "pictures": len(self.pictures), "reached_top": self.reached_top}


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
    chats: list[dict[str, Any]] = field(default_factory=list)  # one summary per chat (and per skipped row)
    interrupted: str = ""  # error code that ended an "all chats" run after some chats were saved

    def add(self, chat: ChatCapture) -> None:
        self.pages += chat.pages
        self.text_pages += chat.text_pages
        self.messages += chat.messages
        self.shots += chat.shots
        self.pictures += chat.pictures
        self.chats.append(chat.summary())

    @property
    def complete(self) -> set[tuple[str, str]]:
        """(app, chat) pairs captured back to their first message."""
        return {(c["app"], c["title"]) for c in self.chats if c.get("reached_top") and not c.get("skipped")}


class Capture:
    """Runs on a worker thread; ``stop()`` ends it after the current page.

    Without ``package`` it captures the chat that is open on the phone; with
    one (a key of ``CHAT_APPS`` or a package name) it captures every chat in
    that app, up to ``max_chats``. ``max_pages`` is per chat.
    """

    def __init__(self, transport: Any, ctx: Any, max_pages: int = 200, title: str = "",
                 progress: Callable[[dict[str, Any]], None] | None = None, settle: float = 0.8,
                 package: str = "", max_chats: int = 30) -> None:
        self.t = transport
        self.ctx = ctx
        self.max_pages = max(1, min(int(max_pages or 200), 2000))
        self.title_override = (title or "").strip()
        self.progress = progress or (lambda info: None)
        self.settle = settle
        self.package = CHAT_APPS.get(package, package)
        self.max_chats = max(1, min(int(max_chats or 30), 500))
        self._stop = threading.Event()
        self._stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self._done_messages = 0
        self._chat_no = 0

    @property
    def mode(self) -> str:
        return "all" if self.package else "current"

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> CaptureResult:
        try:
            return self._run_all() if self.package else self._run_current()
        finally:
            self.t.shell(f"rm -f {REMOTE_SHOT} {REMOTE_DUMP}", timeout=20)

    # ── one chat ─────────────────────────────────────────────────────────
    def _run_current(self) -> CaptureResult:
        res = CaptureResult()
        self._chat_no = 1
        chat = self._capture_chat(self.ctx.extraction.media_dir / "capture" / self._stamp, self.title_override)
        res.add(chat)
        res.title, res.app, res.reached_top = chat.title, chat.app, chat.reached_top
        res.stopped = self._stop.is_set()
        return res

    def _shot(self, path: Path) -> bytes:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.t.shell(f"screencap -p {REMOTE_SHOT}", timeout=30)
        self.t.pull(REMOTE_SHOT, path)
        return path.read_bytes()

    def _dump(self, path: Path) -> tuple[list[Node], int, int]:
        out = self.t.shell(f"uiautomator dump {REMOTE_DUMP}", timeout=60)
        if "ERROR" in out.upper():
            raise ValueError(out.strip()[:120])
        path.parent.mkdir(parents=True, exist_ok=True)
        self.t.pull(REMOTE_DUMP, path)
        return parse_dump(path.read_text(encoding="utf-8", errors="replace"))

    def _capture_chat(self, folder: Path, thread: str = "") -> ChatCapture:
        """Scroll the open chat up to its first message, page by page."""
        ext = self.ctx.extraction
        chat = ChatCapture(title=thread)
        pages: list[Page] = []
        last_digest = ""
        size = (1080, 2400)
        for n in range(1, self.max_pages + 1):
            if self._stop.is_set():
                break
            shot = folder / f"page_{n:03d}.png"
            digest = hashlib.sha256(self._shot(shot)).hexdigest()
            if digest == last_digest:  # the screen did not move: the first message is on screen
                shot.unlink(missing_ok=True)
                chat.reached_top = True
                break
            last_digest = digest
            page = Page("", "", [], *size)
            dump = folder / f"page_{n:03d}.xml"
            try:
                nodes, w, h = self._dump(dump)
                size = (w or size[0], h or size[1])
                page = page_from_dump(nodes, *size, page=n)
                cut_pictures(page, shot, folder / "pictures", ext.rel)
                self.ctx.register(dump, REMOTE_DUMP + f" (page {n})")
                chat.text_pages += 1
            except (ValueError, ET.ParseError, OSError) as exc:
                self.ctx.audit("capture.text_unavailable", f"page {n}: {exc}")
            pages.append(page)
            chat.pages = n
            chat.title = chat.title or thread or page.title
            chat.app = chat.app or APPS.get(page.package, page.package)
            chat.shots.append(self.ctx.photo_record(shot, f"{REMOTE_SHOT} (page {n})", album="", modified=int(time.time() * 1000)))
            self.progress({"mode": self.mode, "chat": self._chat_no, "page": n, "max": self.max_pages,
                           "title": chat.title, "app": chat.app, "preview": ext.rel(shot),
                           "messages": self._done_messages + sum(len(p.items) for p in pages)})
            w, h = size
            self.t.shell(f"input swipe {w // 2} {int(h * 0.32)} {w // 2} {int(h * 0.80)} 450", timeout=20)
            time.sleep(self.settle)
        chat.title = chat.title or "แชตจากหน้าจอ"
        chat.app = chat.app or APPS.get(self.package, "") or "แชต"
        for p in chat.shots:
            p.album = f"บันทึกหน้าจอ {chat.app}: {chat.title}"
        items = stitch(pages)
        chat.messages = to_messages(items, chat.app, chat.title, date.today())
        seen: set[str] = set()
        for it in items:
            if it.kind == "image" and it.crop and it.crop not in seen:
                seen.add(it.crop)
                chat.pictures.append(self.ctx.photo_record(ext.dir / it.crop, f"screen capture page {it.page}",
                                                           album=f"{chat.app} (จากหน้าจอ): {chat.title}", modified=None))
        self._done_messages += len(chat.messages)
        return chat

    # ── every chat in the app ────────────────────────────────────────────
    def _key(self, code: int) -> None:
        self.t.shell(f"input keyevent {code}", timeout=20)

    def _launch(self) -> None:
        self.t.shell(f"monkey -p {self.package} -c android.intent.category.LAUNCHER 1", timeout=30)
        time.sleep(self.settle * 3)

    def _look(self, folder: Path, name: str) -> tuple[list[Node], int, int, str]:
        nodes, w, h = self._dump(folder / f"{name}.xml")
        package = next((n.package for n in nodes if n.package), "")
        return nodes, w or 1080, h or 2400, package

    def _to_list(self, folder: Path, need_tab: bool = False) -> tuple[list[Node], int, int]:
        """Bring the app's chat list on screen (relaunching the app if it was left).

        The "Chats" tab is tapped only after a (re)launch: tapping it while it
        is active scrolls the list back to the top.
        """
        launches = 0
        for _ in range(8):
            nodes, w, h, package = self._look(folder, "screen")
            if package != self.package:
                if launches >= 2:
                    raise CaptureError("capture_app_not_open", package or "?")
                launches += 1
                self._key(224)  # wake the screen
                self._launch()
                need_tab = True
                continue
            if is_chat_screen(nodes, w, h):
                self._key(4)
                time.sleep(self.settle)
                continue
            if need_tab:
                need_tab = False
                tab = chat_tab(nodes, h)
                if tab is not None and not tab.selected:
                    self.ctx.audit("capture.chats_tab", f"tap ({int(tab.cx)},{(tab.box[1] + tab.box[3]) // 2})")
                    self.t.shell(f"input tap {int(tab.cx)} {(tab.box[1] + tab.box[3]) // 2}", timeout=20)
                    time.sleep(self.settle * 1.5)
                    continue
            return nodes, w, h
        raise CaptureError("capture_no_chat_list")

    def _run_all(self) -> CaptureResult:
        ext = self.ctx.extraction
        app = APPS.get(self.package, self.package)
        res = CaptureResult(app=app, title=f"{app}: ทุกห้องแชต")
        listing = self.t.shell(f"pm list packages {self.package}", timeout=30)
        if f"package:{self.package}" not in listing.split():
            raise CaptureError("capture_app_missing", self.package)
        root = ext.media_dir / "capture" / self._stamp
        lists = root / "chat_list"
        self._key(224)
        self._launch()
        nodes, w, h = self._to_list(lists, need_tab=True)
        try:
            self._crawl(res, app, root, lists, nodes, w, h)
        except CaptureError as exc:
            if not res.chats:
                raise
            res.interrupted = exc.code  # keep what was captured; the UI says why it ended early
            log.warning("all-chats capture ended early: %s", exc)
            self.ctx.audit("capture.interrupted", str(exc))
        res.stopped = self._stop.is_set()
        res.reached_top = bool(res.chats) and all(c["reached_top"] for c in res.chats if not c.get("skipped"))
        return res

    def _crawl(self, res: CaptureResult, app: str, root: Path, lists: Path, nodes: list[Node], w: int, h: int) -> None:
        seen: set[str] = set()
        list_pages: set[str] = set()
        idle_scrolls = 0
        captured = 0
        for _ in range(self.max_chats * 6 + 30):  # a hard bound: never loop forever on an odd screen
            if self._stop.is_set() or captured >= self.max_chats:
                break
            rows = chat_rows(nodes, w, h)
            page_key = "\n".join(r.key for r in rows)
            if rows and page_key not in list_pages:  # a new part of the chat list: keep it as evidence
                list_pages.add(page_key)
                k = len(list_pages)
                shot = lists / f"list_{k:02d}.png"
                self._shot(shot)
                self._dump(lists / f"list_{k:02d}.xml")
                self.ctx.register(lists / f"list_{k:02d}.xml", REMOTE_DUMP + f" (chat list {k})")
                res.shots.append(self.ctx.photo_record(shot, f"{REMOTE_SHOT} (chat list {k})", album=f"บันทึกหน้าจอ {app}: รายการแชต",
                                                       modified=int(time.time() * 1000)))
                log.info("chat list page %d: %d rows: %s", k, len(rows), ", ".join(r.title for r in rows))
                self.ctx.audit("capture.list", f"page {k}: {len(rows)} chats: " + " | ".join(r.title for r in rows))
            # A row cut by the list's edge shows less (no preview line): wait until a scroll shows it whole.
            heights = sorted(r.box[3] - r.box[1] for r in rows)
            typical = heights[len(heights) // 2] if heights else 0
            whole = [r for r in rows if len(rows) < 2 or r.box[3] - r.box[1] >= typical * 0.85]
            fresh = [r for r in whole if r.key not in seen]
            if not fresh:
                if idle_scrolls >= 2:
                    break
                idle_scrolls += 1
                self.t.shell(f"input swipe {w // 2} {int(h * 0.75)} {w // 2} {int(h * 0.35)} 400", timeout=20)
                time.sleep(self.settle)
                nodes, w, h = self._to_list(lists)
                continue
            idle_scrolls = 0
            row = fresh[0]
            seen.add(row.key)
            x, y = row.center
            self.ctx.audit("capture.open_chat", f"tap ({x},{y}) '{row.title}'")
            self.progress({"mode": "all", "chat": captured + 1, "page": 0, "max": self.max_pages, "title": row.title,
                           "app": app, "messages": self._done_messages, "chats_done": captured})
            if self._stop.is_set():
                break
            self.t.shell(f"input tap {x} {y}", timeout=20)
            time.sleep(self.settle * 1.5)
            inside, w2, h2, package = self._look(lists, "screen")
            if package != self.package or not is_chat_screen(inside, w2, h2, row.title):
                log.info("row '%s' did not open a chat (screen of %s); skipped", row.title, package)
                self.ctx.audit("capture.skip", f"'{row.title}' did not open a chat (screen of {package or '?'})")
                res.chats.append({"title": row.title, "app": app, "pages": 0, "messages": 0, "pictures": 0,
                                  "reached_top": False, "skipped": "not_a_chat"})
                self._key(4)
                time.sleep(self.settle)
                nodes, w, h = self._to_list(lists)
                continue
            self._chat_no = captured + 1
            chat = self._capture_chat(root / f"{captured + 1:03d}_{safe_name(row.title, 'chat')[:40]}", row.title)
            chat.app = app
            for m in chat.messages:
                m.app = app
            res.add(chat)
            captured += 1
            self.ctx.audit("capture.chat_done", f"'{row.title}': pages={chat.pages} messages={len(chat.messages)} "
                           f"pictures={len(chat.pictures)} reached_top={chat.reached_top}")
            self._key(4)
            time.sleep(self.settle)
            nodes, w, h = self._to_list(lists)
