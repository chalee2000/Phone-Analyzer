"""Pretend phones for the chat screen capture (demo mode and tests).

``DemoChatPhone`` shows one open chat; ``DemoChatApp`` is a whole chat app
(LINE-like or Messenger-like) with a chat list, a tab bar, an ad row and a
chat behind each row. Both answer the same ADB commands as a real phone
(screencap, uiautomator dump, input swipe/tap/keyevent, monkey, pm, rm) with
a rendered screenshot and a matching view hierarchy, so the real capture
code runs unchanged.
"""

from __future__ import annotations

import io
import random
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from xml.sax.saxutils import quoteattr

from PIL import Image, ImageDraw, ImageFont

from ..paths import font

W, H = 720, 1600
HEAD, FOOT = 160, 1440  # header bottom, input bar top
PKG = "jp.naver.line.android"
THAI_MONTHS = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
THAI_DAYS = ["จ.", "อ.", "พ.", "พฤ.", "ศ.", "ส.", "อา."]
LINES = ["ถึงไหนแล้ว", "ของมาพรุ่งนี้นะ ส่งที่เดิม", "โอนแล้ว เช็คด้วย", "อย่าโทร พิมพ์มา", "รับทราบครับ", "ส่งพิกัดมาที",
         "คืนนี้สองทุ่ม หน้าเซเว่น", "ลบแชตด้วยนะ", "ได้ครับพี่", "ระวังด่านแถวบางนา", "ของเหลือเท่าไหร่", "เดี๋ยวให้น้องไปเอา"]


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(str(font("Sarabun-SemiBold.ttf" if bold else "Sarabun-Regular.ttf")), size)
    except OSError:
        return ImageFont.load_default()


class DemoChatPhone:
    def __init__(self, title: str = "หมู บางนา", seed: int = 5150, today: date | None = None,
                 package: str = PKG, desc_only: bool = False) -> None:
        from ..demo import render_scene

        self.title = title
        self.package = package
        self.desc_only = desc_only  # Messenger-like: bubble words only in content-desc
        self.rng = rng = random.Random(seed)
        self.today = today or date.today()
        self.files: dict[str, bytes] = {}
        self.body_font, self.small_font, self.title_font = _font(30), _font(20), _font(34, bold=True)
        self.blocks: list[dict] = []  # content coordinates
        y = 30
        for back in (2, 1, 0):
            d = self.today - timedelta(days=back)
            label = "วันนี้" if back == 0 else "เมื่อวาน" if back == 1 else f"{THAI_DAYS[d.weekday()]} {d.day} {THAI_MONTHS[d.month - 1]}"
            self.blocks.append({"kind": "date", "text": label, "box": (W // 2 - 110, y, W // 2 + 110, y + 50)})
            y += 80
            t = datetime(d.year, d.month, d.day, rng.randint(9, 19), 0)
            for _ in range(rng.randint(9, 13)):
                t += timedelta(minutes=rng.randint(1, 25))
                side = rng.choice(["in", "out"])
                if rng.random() < 0.14:
                    pic = render_scene(rng, 360, 270)
                    x1 = 110 if side == "in" else W - 30 - 360
                    block = {"kind": "image", "side": side, "box": (x1, y, x1 + 360, y + 270), "image": pic}
                    y += 270
                else:
                    text = rng.choice(LINES)
                    lines = self._wrap(text, 430)
                    bw = int(max(self.body_font.getlength(ln) for ln in lines)) + 44
                    bh = 42 * len(lines) + 30
                    x1 = 110 if side == "in" else W - 30 - bw
                    block = {"kind": "msg", "side": side, "text": text, "lines": lines, "box": (x1, y, x1 + bw, y + bh)}
                    y += bh
                bx1, _, bx2, by2 = block["box"]
                stamp = f"{t:%H:%M}"
                tw = int(self.small_font.getlength(stamp))
                tx = bx2 + 10 if side == "in" else bx1 - 10 - tw
                block["time"] = {"text": stamp, "box": (tx, by2 - 28, tx + tw, by2)}
                self.blocks.append(block)
                y += 26
        self.content_h = y + 20
        self.view_h = FOOT - HEAD
        self.offset = max(0, self.content_h - self.view_h)  # opens at the newest message

    def _wrap(self, text: str, width: int) -> list[str]:
        lines, cur = [], ""
        for ch in text:
            if self.body_font.getlength(cur + ch) > width and cur:
                lines.append(cur)
                cur = ch
            else:
                cur += ch
        return lines + ([cur] if cur else [])

    # ── what the screen shows ──────────────────────────────────────────
    def _visible(self):
        for b in self.blocks:
            x1, y1, x2, y2 = b["box"]
            sy1, sy2 = y1 - self.offset + HEAD, y2 - self.offset + HEAD
            if sy2 > HEAD and sy1 < FOOT:
                yield b, (x1, sy1, x2, sy2)

    def screenshot(self) -> bytes:
        img = Image.new("RGB", (W, H), (139, 170, 205))
        d = ImageDraw.Draw(img)
        for b, (x1, y1, x2, y2) in self._visible():
            if b["kind"] == "date":
                d.rounded_rectangle((x1, y1, x2, y2), 25, fill=(110, 140, 175))
                d.text(((x1 + x2) / 2, (y1 + y2) / 2), b["text"], font=self.small_font, fill="white", anchor="mm")
                continue
            if b["kind"] == "image":
                img.paste(b["image"], (x1, y1))
            else:
                fill = (163, 236, 120) if b["side"] == "out" else (255, 255, 255)
                d.rounded_rectangle((x1, y1, x2, y2), 26, fill=fill)
                for i, ln in enumerate(b["lines"]):
                    d.text((x1 + 22, y1 + 15 + i * 42), ln, font=self.body_font, fill=(20, 20, 20))
            if b["side"] == "in":
                d.ellipse((30, y1, 90, y1 + 60), fill=(240, 170, 80))
            tx1, ty1, _, _ = b["time"]["box"]
            d.text((tx1, ty1 - self.offset + HEAD), b["time"]["text"], font=self.small_font, fill=(60, 70, 90))
        d.rectangle((0, 0, W, HEAD), fill=(36, 45, 64))
        d.text((120, 80), self.title, font=self.title_font, fill="white", anchor="lm")
        d.text((40, 80), "‹", font=self.title_font, fill="white", anchor="lm")
        d.rectangle((0, FOOT, W, H), fill=(245, 245, 245))
        d.rounded_rectangle((30, FOOT + 40, W - 120, FOOT + 120), 40, fill="white")
        buf = io.BytesIO()
        img.save(buf, "PNG")
        return buf.getvalue()

    def dump(self) -> str:
        def node(text: str, cls: str, box, desc: str = "", rid: str = "") -> str:
            x1, y1, x2, y2 = (int(v) for v in box)
            y1, y2 = max(y1, HEAD), min(y2, FOOT)
            return (f'<node index="0" text={quoteattr(text)} resource-id={quoteattr(rid)} class="{cls}" package="{self.package}" '
                    f'content-desc={quoteattr(desc)} bounds="[{x1},{y1}][{x2},{y2}]" />')

        pkg = self.package
        parts = [node(self.title, "android.widget.TextView", (120, 55, 600, 105), rid=f"{pkg}:id/header_title")]
        for b, box in self._visible():
            if b["kind"] == "date":
                parts.append(node(b["text"], "android.widget.TextView", box))
                continue
            if b["kind"] == "image":
                parts.append(node("", "android.widget.ImageView", box, rid=f"{pkg}:id/chat_ui_image"))
            elif self.desc_only:
                parts.append(node("", "android.view.ViewGroup", box, desc=b["text"]))
            else:
                parts.append(node(b["text"], "android.widget.TextView", box, rid=f"{pkg}:id/chat_ui_text"))
            if b["side"] == "in":
                parts.append(node("", "android.widget.ImageView", (30, box[1], 90, box[1] + 60)))
            tx1, ty1, tx2, ty2 = b["time"]["box"]
            tb = (tx1, ty1 - self.offset + HEAD, tx2, ty2 - self.offset + HEAD)
            if HEAD < (tb[1] + tb[3]) / 2 < FOOT:
                parts.append(node(b["time"]["text"], "android.widget.TextView", tb))
        parts.append(node("", "android.widget.EditText", (30, FOOT + 40, W - 120, FOOT + 120)))
        return ("<?xml version='1.0' encoding='UTF-8' standalone='yes' ?><hierarchy rotation=\"0\">"
                f'<node index="0" text="" resource-id="" class="android.widget.FrameLayout" package="{self.package}" content-desc="" '
                f'bounds="[0,0][{W},{H}]">' + "".join(parts) + "</node></hierarchy>")

    # ── the ADB surface used by spni.android.capture ───────────────────
    serial = "demo-capture"

    def shell(self, cmd: str, timeout: float = 120) -> str:
        if cmd.startswith("screencap -p "):
            self.files[cmd.split()[-1]] = self.screenshot()
            return ""
        if cmd.startswith("uiautomator dump "):
            path = cmd.split()[-1]
            self.files[path] = self.dump().encode("utf-8")
            return f"UI hierchary dumped to: {path}"
        m = re.match(r"input swipe (\d+) (\d+) (\d+) (\d+)", cmd)
        if m:
            dy = int(m.group(4)) - int(m.group(2))
            self.offset = max(0, self.offset - dy)
        return ""

    def pull(self, remote: str, local: Path) -> None:
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_bytes(self.files[remote])

    def push(self, local: Path, remote: str) -> None:
        pass

    @property
    def message_count(self) -> int:
        return sum(1 for b in self.blocks if b["kind"] in ("msg", "image"))

    @property
    def preview(self) -> str:
        last = [b for b in self.blocks if b["kind"] in ("msg", "image")][-1]
        return last.get("text") or "ส่งรูปภาพ"

    @property
    def last_time(self) -> str:
        return [b for b in self.blocks if b["kind"] in ("msg", "image")][-1]["time"]["text"]


MESSENGER = "com.facebook.orca"
LAUNCHER = "com.miui.home"
BROWSER = "com.android.chrome"
GROUPS = ["กลุ่ม ส่งของ บางนา", "ทีมงานโกดัง"]
TABS = [("หน้าหลัก", "home"), ("แชท", "list"), ("ข่าว", "news")]
TAB_TOP = 1440
LIST_TOP = 230


class DemoChatApp:
    """A chat app on a pretend phone: list → chat → back, with an ad row that opens a browser."""

    serial = "demo-capture"

    def __init__(self, package: str = PKG, titles: list[str] | None = None, seed: int = 4200,
                 row_h: int = 150, today: date | None = None, ad_at: int | None = 2,
                 installed: tuple[str, ...] = (PKG, MESSENGER)) -> None:
        from ..demo import SHARED_PEOPLE

        self.package = package
        self.installed = tuple(dict.fromkeys((package, *installed, LAUNCHER, BROWSER)))
        self.messenger = package == MESSENGER
        names = titles or [p[1] for p in SHARED_PEOPLE] + GROUPS
        self.chats = [DemoChatPhone(title=t, seed=seed + i * 31, today=today, package=package, desc_only=self.messenger)
                      for i, t in enumerate(names)]
        self.rows: list[DemoChatPhone | None] = list(self.chats)
        if ad_at is not None:
            self.rows.insert(min(ad_at, len(self.rows)), None)  # None = the sponsored row
        self.row_h = row_h
        self.screen = "off"  # off (launcher) | home | list | chat | browser
        self.resume = "list" if self.messenger else "home"
        self.current: DemoChatPhone | None = None
        self.list_offset = 0
        self.files: dict[str, bytes] = {}
        self.opened: list[str] = []
        self.font, self.small, self.bold = _font(28), _font(20), _font(30, bold=True)

    @property
    def message_counts(self) -> dict[str, int]:
        return {c.title: c.message_count for c in self.chats}

    # ── layout ─────────────────────────────────────────────────────────
    def _visible_rows(self):
        bottom = TAB_TOP if not self.messenger else H
        for i, row in enumerate(self.rows):
            y1 = LIST_TOP + i * self.row_h - self.list_offset
            y2 = y1 + self.row_h
            if y2 > LIST_TOP and y1 < bottom:
                yield i, row, (0, max(y1, LIST_TOP), W, min(y2, bottom)), y1

    def _max_offset(self) -> int:
        bottom = TAB_TOP if not self.messenger else H
        return max(0, len(self.rows) * self.row_h - (bottom - LIST_TOP))

    def _row_text(self, row: DemoChatPhone | None) -> tuple[str, str, str]:
        if row is None:
            return "โปรโมชันพิเศษ! รับคูปองส่วนลด", "ได้รับการสนับสนุน", ""
        return row.title, row.preview, row.last_time

    # ── screens ────────────────────────────────────────────────────────
    def _package(self) -> str:
        return {"off": LAUNCHER, "browser": BROWSER}.get(self.screen, self.package)

    def screenshot(self) -> bytes:
        if self.screen == "chat" and self.current:
            return self.current.screenshot()
        img = Image.new("RGB", (W, H), (255, 255, 255))
        d = ImageDraw.Draw(img)
        if self.screen == "off":
            img.paste((40, 60, 90), (0, 0, W, H))
            d.text((W // 2, H // 3), "15:56", font=_font(90, bold=True), fill="white", anchor="mm")
        elif self.screen == "browser":
            d.rectangle((0, 0, W, 140), fill=(240, 240, 240))
            d.text((40, 70), "https://ads.example/promo", font=self.small, fill=(60, 60, 60), anchor="lm")
            d.text((W // 2, H // 2), "โปรโมชันพิเศษ", font=self.bold, fill=(20, 20, 20), anchor="mm")
        elif self.screen == "home":
            d.text((40, 80), "หน้าหลัก", font=self.bold, fill=(20, 20, 20), anchor="lm")
            for i, chat in enumerate(self.chats[:6]):
                y = LIST_TOP + i * 130
                d.ellipse((30, y + 20, 110, y + 100), fill=(120, 190, 140))
                d.text((140, y + 60), chat.title, font=self.font, fill=(20, 20, 20), anchor="lm")
        else:
            d.text((40, 80), "แชต" if self.messenger else "แชท", font=self.bold, fill=(20, 20, 20), anchor="lm")
            d.rounded_rectangle((30, 125, W - 30, 205), 40, fill=(240, 241, 245))
            d.text((70, 165), "ค้นหา", font=self.small, fill=(140, 140, 150), anchor="lm")
            for i, row, (x1, y1, x2, y2), top in self._visible_rows():
                title, preview, stamp = self._row_text(row)
                colour = (250, 204, 120) if row is None else ((80, 130, 250) if self.messenger else (6, 199, 85))
                d.ellipse((30, top + 25, 120, top + 115), fill=colour)
                d.text((145, top + 50), title, font=self.font, fill=(20, 20, 20), anchor="lm")
                d.text((145, top + 98), preview[:28], font=self.small, fill=(120, 120, 130), anchor="lm")
                if stamp:
                    d.text((W - 40, top + 50), stamp, font=self.small, fill=(150, 150, 160), anchor="rm")
        if self.screen in ("home", "list") and not self.messenger:
            d.rectangle((0, TAB_TOP, W, H), fill=(250, 250, 250))
            for k, (label, key) in enumerate(TABS):
                cx = W * (2 * k + 1) // 6
                active = (self.screen == key)
                d.text((cx, TAB_TOP + 80), label, font=self.small, fill=(20, 20, 20) if active else (150, 150, 150), anchor="mm")
        buf = io.BytesIO()
        img.save(buf, "PNG")
        return buf.getvalue()

    def dump(self) -> str:
        if self.screen == "chat" and self.current:
            return self.current.dump()
        pkg = self._package()

        def node(text: str, cls: str, box, desc: str = "", clickable: bool = False, selected: bool = False, inner: str = "") -> str:
            x1, y1, x2, y2 = (int(v) for v in box)
            attrs = (f'index="0" text={quoteattr(text)} resource-id="" class="{cls}" package="{pkg}" content-desc={quoteattr(desc)} '
                     f'clickable="{str(clickable).lower()}" selected="{str(selected).lower()}" bounds="[{x1},{y1}][{x2},{y2}]"')
            return f"<node {attrs}>{inner}</node>" if inner else f"<node {attrs} />"

        parts: list[str] = []
        if self.screen == "browser":
            parts.append(node("https://ads.example/promo", "android.widget.EditText", (40, 40, W - 40, 110)))
            parts.append(node("โปรโมชันพิเศษ", "android.widget.TextView", (100, 760, W - 100, 840)))
        elif self.screen == "off":
            parts.append(node("15:56", "android.widget.TextView", (200, 480, 520, 600)))
        elif self.screen == "home":
            parts.append(node("หน้าหลัก", "android.widget.TextView", (40, 50, 300, 110)))
            for i, chat in enumerate(self.chats[:6]):
                y = LIST_TOP + i * 130
                parts.append(node("", "android.view.ViewGroup", (0, y, W, y + 130), clickable=True,
                                  inner=node(chat.title, "android.widget.TextView", (140, y + 40, 600, y + 80))))
        else:
            parts.append(node("แชต" if self.messenger else "แชท", "android.widget.TextView", (40, 50, 300, 110)))
            parts.append(node("", "android.widget.FrameLayout", (30, 125, W - 30, 205), clickable=True,
                              inner=node("ค้นหา", "android.widget.TextView", (70, 145, 300, 185))))
            for i, row, box, top in self._visible_rows():
                title, preview, stamp = self._row_text(row)
                if self.messenger:  # Litho-style: the whole row described, no text children
                    parts.append(node("", "android.view.ViewGroup", box, desc=f"{title}, {preview}, {stamp}", clickable=True))
                    continue
                kids = []
                for text, tb in ((title, (145, top + 30, 560, top + 72)), (preview, (145, top + 80, 600, top + 118)),
                                 (stamp, (590, top + 30, W - 40, top + 70))):
                    if text and tb[1] >= box[1] and tb[3] <= box[3]:
                        kids.append(node(text, "android.widget.TextView", tb))
                parts.append(node("", "android.view.ViewGroup", box, clickable=True, inner="".join(kids)))
        if self.screen in ("home", "list") and not self.messenger:
            for k, (label, key) in enumerate(TABS):
                x1 = W * k // 3
                parts.append(node(label, "android.widget.TextView", (x1, TAB_TOP + 20, x1 + W // 3, H - 20),
                                  clickable=True, selected=self.screen == key))
        return ("<?xml version='1.0' encoding='UTF-8' standalone='yes' ?><hierarchy rotation=\"0\">"
                f'<node index="0" text="" resource-id="" class="android.widget.FrameLayout" package="{pkg}" content-desc="" '
                f'bounds="[0,0][{W},{H}]">' + "".join(parts) + "</node></hierarchy>")

    # ── the ADB surface ────────────────────────────────────────────────
    def shell(self, cmd: str, timeout: float = 120) -> str:
        if cmd.startswith("screencap -p "):
            self.files[cmd.split()[-1]] = self.screenshot()
            return ""
        if cmd.startswith("uiautomator dump "):
            path = cmd.split()[-1]
            self.files[path] = self.dump().encode("utf-8")
            return f"UI hierchary dumped to: {path}"
        if cmd.startswith("pm list packages"):
            want = cmd.split()[-1] if len(cmd.split()) > 3 else ""
            return "\n".join(f"package:{p}" for p in self.installed if p.startswith(want))
        m = re.match(r"monkey -p (\S+)", cmd)
        if m:
            if m.group(1) == self.package and self.screen in ("off", "browser"):
                self.screen = self.resume
            return "Events injected: 1"
        m = re.match(r"input keyevent (\d+)", cmd)
        if m:
            if m.group(1) == "4":
                self.screen = {"chat": "list", "browser": "list", "list": "off", "home": "off"}.get(self.screen, self.screen)
                if self.screen != "off":
                    self.resume = self.screen
            return ""
        m = re.match(r"input tap (\d+) (\d+)", cmd)
        if m:
            self._tap(int(m.group(1)), int(m.group(2)))
            return ""
        m = re.match(r"input swipe (\d+) (\d+) (\d+) (\d+)", cmd)
        if m:
            dy = int(m.group(4)) - int(m.group(2))
            if self.screen == "chat" and self.current:
                self.current.shell(cmd)
            elif self.screen == "list":
                self.list_offset = max(0, min(self._max_offset(), self.list_offset - dy))
        return ""

    def _tap(self, x: int, y: int) -> None:
        if self.screen in ("home", "list") and not self.messenger and y >= TAB_TOP:
            key = TABS[min(2, x * 3 // W)][1]
            if key == "list" and self.screen == "list":
                self.list_offset = 0  # tapping the active tab jumps to the top, like the real apps
            if key in ("home", "list"):
                self.screen = self.resume = key
            return
        if self.screen != "list":
            return
        for i, row, (x1, y1, x2, y2), _ in self._visible_rows():
            if y1 <= y < y2:
                if row is None:
                    self.screen = "browser"
                else:
                    self.screen, self.current = "chat", row
                    row.offset = max(0, row.content_h - row.view_h)  # chats open at the newest message
                    self.opened.append(row.title)
                return

    def pull(self, remote: str, local: Path) -> None:
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_bytes(self.files[remote])

    def push(self, local: Path, remote: str) -> None:
        pass
