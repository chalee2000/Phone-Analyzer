"""A pretend phone showing one LINE chat: drives spni.android.capture in demo mode and tests.

It answers the same ADB commands as a real phone (screencap, uiautomator dump,
input swipe, rm) with a rendered screenshot and a matching view hierarchy,
and scrolls when swiped, so the real capture code runs unchanged.
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
    def __init__(self, title: str = "หมู บางนา", seed: int = 5150, today: date | None = None) -> None:
        from ..demo import render_scene

        self.title = title
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
            return (f'<node index="0" text={quoteattr(text)} resource-id={quoteattr(rid)} class="{cls}" package="{PKG}" '
                    f'content-desc={quoteattr(desc)} bounds="[{x1},{y1}][{x2},{y2}]" />')

        parts = [node(self.title, "android.widget.TextView", (120, 55, 600, 105), rid=f"{PKG}:id/header_title")]
        for b, box in self._visible():
            if b["kind"] == "date":
                parts.append(node(b["text"], "android.widget.TextView", box))
                continue
            if b["kind"] == "image":
                parts.append(node("", "android.widget.ImageView", box, rid=f"{PKG}:id/chat_ui_image"))
            else:
                parts.append(node(b["text"], "android.widget.TextView", box, rid=f"{PKG}:id/chat_ui_text"))
            if b["side"] == "in":
                parts.append(node("", "android.widget.ImageView", (30, box[1], 90, box[1] + 60)))
            tx1, ty1, tx2, ty2 = b["time"]["box"]
            tb = (tx1, ty1 - self.offset + HEAD, tx2, ty2 - self.offset + HEAD)
            if HEAD < (tb[1] + tb[3]) / 2 < FOOT:
                parts.append(node(b["time"]["text"], "android.widget.TextView", tb))
        parts.append(node("", "android.widget.EditText", (30, FOOT + 40, W - 120, FOOT + 120)))
        return ("<?xml version='1.0' encoding='UTF-8' standalone='yes' ?><hierarchy rotation=\"0\">"
                f'<node index="0" text="" resource-id="" class="android.widget.FrameLayout" package="{PKG}" content-desc="" '
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
