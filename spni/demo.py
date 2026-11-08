"""Demo devices with realistic, entirely synthetic Thai data.

Used for training, UI development and automated tests when no phone is
connected. Every record is generated from a fixed random seed, so the output is
stable between runs. Demo extractions are labelled ``method=demo`` in the case
database and in every report.
"""

from __future__ import annotations

import io
import math
import os
import random
import struct
import time
import wave
from datetime import datetime, timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from .extract import BaseExtractor, ExtractionContext
from .models import (
    App,
    CallRecord,
    ChatMessage,
    Contact,
    DeviceInfo,
    Note,
    SimCard,
    SmsMessage,
    Unavailable,
    VoiceMemo,
    WebVisit,
    WifiNetwork,
)

DEMO_ANDROID_ID = "demo:android"
DEMO_IOS_ID = "demo:ios"
DEMO_ANDROID_NUMBER = "0861234001"
DEMO_IOS_NUMBER = "0951234002"

# People known to both demo owners: same numbers, saved under different names.
# Extracting both demo phones into one case shows cross-device links.
SHARED_PEOPLE = [
    ("เสี่ยหมู", "หมู บางนา", "0817001001"),
    ("พี่บอย วินมอไซค์", "บอย วิน", "0817001002"),
    ("ไอ้โต้ง", "โต้ง", "0817001003"),
    ("เฮียเล้ง", "เล้ง ตลาด", "0817001004"),
    ("พี่เอ็ม ขนส่ง", "เอ็ม ขนส่ง", "0817001005"),
    ("ธนพล ศรีวงศ์", "ธนพล", "0817001006"),
    ("น้องฝ้าย", "ฝ้าย", "0817001007"),
    ("อนุชา บุญเรือง", "อนุชา", "0817001008"),
]


def cdr_partners() -> list[str]:
    return [n for _, _, n in SHARED_PEOPLE] + [DEMO_IOS_NUMBER]

FIRST = [
    "สมชาย", "สมศักดิ์", "วิชัย", "ประเสริฐ", "สุนทร", "อนุชา", "ธนพล", "กิตติพงษ์", "ณัฐวุฒิ", "ศุภชัย",
    "พิมพ์ชนก", "สุดารัตน์", "กาญจนา", "วรรณา", "ศิริพร", "ปวีณา", "ธิดารัตน์", "อรอุมา", "จิราพร", "มาลัย",
    "ชยพล", "ภานุวัฒน์", "อภิชาติ", "นพดล", "เอกชัย", "รัชนี", "ปิยะพงษ์", "สุภาวดี", "ธีรวัฒน์", "วนิดา",
]
LAST = [
    "ใจดี", "แก้วมณี", "ศรีสุข", "บุญมา", "ทองดี", "สุขสวัสดิ์", "พรหมมา", "วงศ์ใหญ่", "จันทร์เพ็ญ", "มั่นคง",
    "รัตนชัย", "อินทร์แก้ว", "ชัยมงคล", "สายทอง", "เพชรรัตน์", "ศรีวงศ์", "บุญเรือง", "นาคสวัสดิ์",
]
NICK = [
    "พี่ต้น", "น้องแนน", "ลุงเหน่ง", "เจ๊หมวย ร้านข้าว", "ช่างแอร์ สมพงษ์", "แม่", "พ่อ", "พี่บอย วินมอไซค์",
    "ป้าแดง หอพัก", "เฮียเล้ง", "ไอ้โต้ง", "น้องฝ้าย", "เสี่ยหมู", "ครูอ้อย", "พี่เอ็ม ขนส่ง",
]
SERVICES = [
    ("AIS Call Center", "1175"), ("ธนาคารกสิกรไทย", "028888888"), ("Kerry Express", "1217"),
    ("Grab", "021292555"), ("โรงพยาบาลรามาฯ", "022011000"), ("Flash Express", "1496"),
]
CHAT_LINES = [
    "ถึงไหนแล้ว", "อีก 10 นาทีถึง", "โอเค รอหน้าเซเว่นนะ", "พรุ่งนี้ว่างไหม", "ว่างช่วงบ่าย", "โอนให้แล้วนะ",
    "ได้รับแล้ว ขอบคุณครับ", "เดี๋ยวโทรกลับ", "กินข้าวยัง", "ประชุมอยู่ เดี๋ยวโทรหา", "ส่งโลเคชั่นมาหน่อย",
    "ฝนตกหนักมาก รถติดสุด ๆ", "ของมาถึงแล้ว", "ไปรับที่เดิมนะ", "เจอกันสองทุ่ม", "ได้ครับ", "โอเคค่ะ 👍",
    "เลื่อนเป็นวันศุกร์ได้ไหม", "ขอเบอร์พี่เขาหน่อย", "ฝากซื้อน้ำด้วย", "เปลี่ยนที่นัดเป็นปั๊ม ปตท.",
    "ตอนนี้อยู่บางนา", "จอดรถไว้ชั้น 3", "ส่งรูปมาให้ดูก่อน", "ราคาเท่าไหร่", "ลดได้อีกไหม", "จัดให้เลย",
    "ขอบคุณมากครับ", "ฝันดีนะ", "ตื่นยัง", "ไม่ต้องรีบนะ", "อย่าลืมเอาเอกสารมาด้วย",
]
PLACES = [
    (13.7563, 100.5018, "กรุงเทพฯ"), (18.7883, 98.9853, "เชียงใหม่"), (12.9236, 100.8825, "พัทยา"),
    (12.5684, 99.9577, "หัวหิน"), (16.4419, 102.8360, "ขอนแก่น"), (7.8804, 98.3923, "ภูเก็ต"),
    (14.3532, 100.5689, "อยุธยา"), (13.8199, 100.0443, "นครปฐม"),
]


def _speed() -> float:
    try:
        return float(os.environ.get("SPNI_DEMO_SPEED", "1"))
    except ValueError:
        return 1.0


def _sleep(seconds: float) -> None:
    s = seconds * _speed()
    if s > 0:
        time.sleep(s)


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def _thai_mobile(rng: random.Random) -> str:
    return rng.choice(["06", "08", "09"]) + "".join(str(rng.randint(0, 9)) for _ in range(8))


# ── synthetic photos ────────────────────────────────────────────────────
def _lerp(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))  # type: ignore[return-value]


PALETTES = [
    ((255, 183, 94), (237, 117, 56), (70, 52, 110)),   # sunset
    ((135, 206, 250), (176, 224, 230), (34, 85, 60)),  # day / green hills
    ((25, 25, 70), (90, 60, 140), (20, 20, 40)),       # night
    ((255, 214, 165), (255, 160, 122), (60, 90, 120)), # dawn
    ((120, 190, 220), (230, 245, 250), (40, 110, 150)),# sea
]


def render_scene(rng: random.Random, w: int = 960, h: int = 720) -> Image.Image:
    top, bottom, ground = rng.choice(PALETTES)
    img = Image.new("RGB", (w, h))
    px = ImageDraw.Draw(img)
    for y in range(h):
        px.line([(0, y), (w, y)], fill=_lerp(top, bottom, y / h))
    kind = rng.choice(["mountains", "city", "bokeh", "sea"])
    if kind == "bokeh":
        layer = Image.new("RGB", (w, h), (0, 0, 0))
        d = ImageDraw.Draw(layer)
        for _ in range(26):
            r = rng.randint(20, 90)
            x, y = rng.randint(0, w), rng.randint(0, h)
            col = _lerp(top, (255, 255, 255), rng.random() * 0.6)
            d.ellipse([x - r, y - r, x + r, y + r], fill=col)
        layer = layer.filter(ImageFilter.GaussianBlur(14))
        return Image.blend(img, layer, 0.55)
    sun_x, sun_y, sun_r = rng.randint(w // 5, 4 * w // 5), rng.randint(h // 8, h // 3), rng.randint(30, 60)
    px.ellipse([sun_x - sun_r, sun_y - sun_r, sun_x + sun_r, sun_y + sun_r], fill=_lerp(top, (255, 250, 230), 0.8))
    if kind == "city":
        x = 0
        while x < w:
            bw, bh = rng.randint(40, 110), rng.randint(h // 6, h // 2)
            col = _lerp(ground, (0, 0, 0), rng.random() * 0.4)
            px.rectangle([x, h - bh, x + bw, h], fill=col)
            for wy in range(h - bh + 12, h - 10, 22):
                for wx in range(x + 8, x + bw - 8, 16):
                    if rng.random() < 0.35:
                        px.rectangle([wx, wy, wx + 7, wy + 10], fill=(255, 221, 140))
            x += bw + rng.randint(0, 6)
        return img
    layers = 3 if kind == "mountains" else 1
    for i in range(layers):
        base = h * (0.55 + i * 0.12) if kind == "mountains" else h * 0.62
        col = _lerp(ground, bottom, 0.5 - i * 0.2)
        pts = [(0, h)]
        phase, amp = rng.random() * 6, rng.randint(30, 90)
        for x in range(0, w + 20, 20):
            y = base - amp * (0.6 * math.sin(x / 140 + phase) + 0.4 * math.sin(x / 57 + phase * 2))
            pts.append((x, int(y)))
        pts.append((w, h))
        px.polygon(pts, fill=col)
    if kind == "sea":
        for y in range(int(h * 0.62), h, 9):
            px.line([(rng.randint(0, w // 3), y), (rng.randint(w // 2, w), y)], fill=_lerp(bottom, (255, 255, 255), 0.4), width=2)
    return img


def _deg_to_dms(value: float) -> tuple[float, float, float]:
    value = abs(value)
    d = int(value)
    m = int((value - d) * 60)
    s = round((value - d - m / 60) * 3600, 2)
    return (float(d), float(m), s)


def make_demo_jpeg(path: Path, rng: random.Random, taken: datetime, make: str, model: str, gps: bool) -> None:
    img = render_scene(rng)
    exif = Image.Exif()
    exif[0x010F] = make
    exif[0x0110] = model
    exif[0x0132] = taken.strftime("%Y:%m:%d %H:%M:%S")
    exif[0x8769] = {0x9003: taken.strftime("%Y:%m:%d %H:%M:%S")}
    if gps:
        lat, lon, _ = rng.choice(PLACES)
        spread = 0.0004 if rng.random() < 0.6 else 0.05  # many shots at the same spots
        lat += rng.uniform(-spread, spread)
        lon += rng.uniform(-spread, spread)
        exif[0x8825] = {1: "N", 2: _deg_to_dms(lat), 3: "E", 4: _deg_to_dms(lon)}
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "JPEG", quality=84, exif=exif.tobytes())


def make_demo_wav(path: Path, rng: random.Random, seconds: float) -> None:
    rate = 16000
    freqs = [rng.choice([220, 247, 262, 294, 330]) for _ in range(3)]
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        frames = bytearray()
        for i in range(int(rate * seconds)):
            t = i / rate
            env = min(1.0, t * 4) * min(1.0, (seconds - t) * 4) * (0.6 + 0.4 * math.sin(t * 3))
            v = sum(math.sin(2 * math.pi * f * t) for f in freqs) / len(freqs)
            frames += struct.pack("<h", int(v * env * 9000))
        wav.writeframes(bytes(frames))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(buf.getvalue())


# ── generators ──────────────────────────────────────────────────────────
class _People:
    def __init__(self, rng: random.Random, n: int, ios: bool = False) -> None:
        self.rng = rng
        people: list[tuple[str, str]] = [(ios_name if ios else name, number) for name, ios_name, number in SHARED_PEOPLE]
        # Each demo owner has the other one saved.
        people.append(("วิชัย มั่นคง", DEMO_ANDROID_NUMBER) if ios else ("สมชาย ใจดี", DEMO_IOS_NUMBER))
        heavy = len(people)
        used: set[str] = {p[0] for p in people}
        for nick in NICK:
            if nick not in used:
                people.append((nick, _thai_mobile(rng)))
        while len(people) < n - len(SERVICES):
            name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
            if name in used:
                continue
            used.add(name)
            people.append((name, _thai_mobile(rng)))
        people.extend(SERVICES)
        self.people = people
        # A few people dominate communication, as in real data.
        self.weights = [max(1.0, 30 / (i + 1)) for i in range(len(people))]
        rng.shuffle(self.weights)
        for i in range(heavy):
            self.weights[i] = 26.0 - i * 1.6

    def pick(self) -> tuple[str, str]:
        return self.rng.choices(self.people, weights=self.weights, k=1)[0]


def _contacts(people: _People, account: str) -> list[Contact]:
    rng = people.rng
    out = []
    for name, number in people.people:
        phones = [number]
        if rng.random() < 0.12:
            phones.append(_thai_mobile(rng))
        emails = [f"user{rng.randint(100, 999)}@gmail.com"] if rng.random() < 0.2 else []
        out.append(
            Contact(
                name=name,
                phones=phones,
                emails=emails,
                organization=rng.choice(["", "", "", "บจก. ขนส่งไทย", "ร้านวัสดุก่อสร้าง", "สภ.เมือง"]),
                account=account,
                starred=rng.random() < 0.1,
            )
        )
    return out


def _random_time(rng: random.Random, now: datetime, days: int) -> datetime:
    day = now - timedelta(days=rng.random() * days)
    hour = rng.choices(range(24), weights=[1, 1, 1, 1, 1, 2, 4, 6, 8, 8, 7, 7, 8, 7, 6, 6, 7, 8, 9, 10, 10, 8, 5, 3])[0]
    return day.replace(hour=hour, minute=rng.randint(0, 59), second=rng.randint(0, 59), microsecond=0)


def _calls(people: _People, now: datetime, n: int, ios: bool) -> list[CallRecord]:
    rng = people.rng
    calls = []
    for _ in range(n):
        name, number = people.pick()
        direction = rng.choices(["incoming", "outgoing", "missed", "rejected"], weights=[40, 42, 14, 4])[0]
        duration = 0 if direction in ("missed", "rejected") else int(rng.expovariate(1 / 140)) + 5
        service = "cellular"
        if ios and rng.random() < 0.15:
            service = rng.choice(["FaceTime Audio", "WhatsApp"])
        calls.append(
            CallRecord(
                number=number,
                name=name,
                direction=direction,
                timestamp=_ms(_random_time(rng, now, 60)),
                duration=duration,
                sim=rng.choice(["SIM 1", "SIM 1", "SIM 2"]) if not ios else "",
                service=service,
            )
        )
    calls.sort(key=lambda c: c.timestamp or 0, reverse=True)
    return calls


def _sms(people: _People, now: datetime, n: int, ios: bool) -> list[SmsMessage]:
    rng = people.rng
    msgs: list[SmsMessage] = []
    templates = [
        ("KBank", lambda: f"รหัส OTP ของท่านคือ {rng.randint(100000, 999999)} (Ref: {rng.choice('ABCDEFGHJK')}{rng.randint(1000, 9999)}) ใช้ภายใน 5 นาที ห้ามบอกรหัสนี้แก่ผู้อื่น"),
        ("AIS", lambda: f"AIS: ยอดเงินคงเหลือ {rng.randint(5, 400)}.{rng.randint(10, 99)} บาท ใช้ได้ถึง {rng.randint(1, 28)}/12/2026"),
        ("TrueMove H", lambda: "สมัครเน็ตไม่อั้น 15Mbps 7 วัน 99 บ. กด *900*5531# โทรออก"),
        ("Flash", lambda: f"Flash Express: พัสดุ TH{rng.randint(10**11, 10**12 - 1)} กำลังนำส่ง กรุณารอรับสาย"),
        ("SCB", lambda: f"เงินเข้าบัญชี x{rng.randint(1000, 9999)} จำนวน {rng.randint(100, 25000):,}.00 บ. คงเหลือ {rng.randint(1000, 90000):,}.{rng.randint(10, 99)} บ."),
    ]
    automated = int(n * 0.35)
    for _ in range(automated):
        sender, text = rng.choice(templates)
        msgs.append(SmsMessage(address=sender, body=text(), direction="in", timestamp=_ms(_random_time(rng, now, 60)), thread=sender, contact_name=sender))
    while len(msgs) < n:
        name, number = people.pick()
        if number in {s[1] for s in SERVICES}:
            continue
        start = _random_time(rng, now, 60)
        for j in range(rng.randint(2, 9)):
            if len(msgs) >= n:
                break
            out = rng.random() < 0.5
            msgs.append(
                SmsMessage(
                    address=number,
                    body=rng.choice(CHAT_LINES),
                    direction="out" if out else "in",
                    timestamp=_ms(start + timedelta(minutes=j * rng.randint(1, 12))),
                    thread=number,
                    contact_name=name,
                    read=True,
                    service="iMessage" if ios and rng.random() < 0.5 else "SMS",
                )
            )
    msgs.sort(key=lambda m: m.timestamp or 0, reverse=True)
    return msgs


def _chats(people: _People, now: datetime, n: int) -> list[ChatMessage]:
    rng = people.rng
    msgs: list[ChatMessage] = []
    groups = ["กลุ่มเพื่อน ม.6", "ครอบครัวสุขสันต์", "งานส่งของ รอบเช้า"]
    while len(msgs) < n:
        app = rng.choice(["LINE", "LINE", "WhatsApp"])
        if rng.random() < 0.25:
            thread = rng.choice(groups)
        else:
            thread = people.pick()[0]
        start = _random_time(rng, now, 45)
        for j in range(rng.randint(3, 14)):
            if len(msgs) >= n:
                break
            out = rng.random() < 0.45
            sender = "ฉัน" if out else (thread if thread not in groups else people.pick()[0])
            attach = ""
            body = rng.choice(CHAT_LINES)
            if rng.random() < 0.06:
                attach, body = "image.jpg", "[รูปภาพ]"
            elif rng.random() < 0.04:
                attach, body = "sticker", "[สติกเกอร์]"
            msgs.append(
                ChatMessage(
                    app=app,
                    thread=thread,
                    sender=sender,
                    body=body,
                    direction="out" if out else "in",
                    timestamp=_ms(start + timedelta(minutes=j * rng.randint(1, 8))),
                    attachment=attach,
                )
            )
    msgs.sort(key=lambda m: m.timestamp or 0, reverse=True)
    return msgs


WEB = [
    ("https://www.google.com/search?q=ราคาทองวันนี้", "ราคาทองวันนี้ - ค้นหาด้วย Google"),
    ("https://pantip.com/topic/42815566", "รถติดถนนพระราม 2 ช่วงนี้ไปทางไหนดีครับ - Pantip"),
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "YouTube"),
    ("https://shopee.co.th/product/123456/7890", "หูฟังบลูทูธ ไร้สาย | Shopee Thailand"),
    ("https://www.lazada.co.th/products/i4455667.html", "พาวเวอร์แบงค์ 20000mAh | Lazada.co.th"),
    ("https://www.thairath.co.th/news/local/2789911", "ข่าวท้องถิ่น - ไทยรัฐออนไลน์"),
    ("https://www.google.com/maps/place/สยามพารากอน", "สยามพารากอน - Google Maps"),
    ("https://www.facebook.com/marketplace/", "Facebook Marketplace"),
    ("https://www.kasikornbank.com/th/personal", "ธนาคารกสิกรไทย"),
    ("https://www.google.com/search?q=เบอร์+kerry+express", "เบอร์ kerry express - ค้นหาด้วย Google"),
    ("https://www.tmd.go.th/", "กรมอุตุนิยมวิทยา"),
    ("https://www.sanook.com/news/", "ข่าววันนี้ - Sanook"),
]


def _web(rng: random.Random, now: datetime, n: int) -> list[WebVisit]:
    visits = []
    for _ in range(n):
        url, title = rng.choice(WEB)
        visits.append(WebVisit(url=url, title=title, timestamp=_ms(_random_time(rng, now, 30)), visit_count=rng.randint(1, 6), browser="Safari"))
    visits.sort(key=lambda v: v.timestamp or 0, reverse=True)
    return visits


def _notes(now: datetime) -> list[Note]:
    base = now - timedelta(days=3)
    items = [
        ("รายการซื้อของ", "ไข่ไก่ 1 แผง\nนมจืด 2 กล่อง\nข้าวสาร 5 กก.\nน้ำยาล้างจาน"),
        ("นัดหมายสัปดาห์นี้", "จันทร์ 10:00 ทำฟัน\nพุธ 14:00 ประชุมลูกค้า\nศุกร์ 19:00 กินข้าวกับพี่ต้น"),
        ("ที่อยู่ส่งของ", "99/12 ม.5 ต.บางพลีใหญ่ อ.บางพลี จ.สมุทรปราการ 10540"),
        ("ค่าใช้จ่ายเดือนนี้", "ค่าห้อง 4,500\nค่าไฟ 820\nค่าเน็ต 599\nผ่อนรถ 7,200"),
        ("ไอเดียของขวัญ", "นาฬิกา / หูฟัง / กระเป๋าสตางค์"),
    ]
    return [
        Note(title=t, body=b, folder="Notes", created=_ms(base - timedelta(days=i * 9)), modified=_ms(base - timedelta(days=i * 2)), source="Apple Notes")
        for i, (t, b) in enumerate(items)
    ]


WIFI = [
    ("AIS 4G Hi-Speed Home WiFi_5G", "WPA2-PSK"), ("TRUEGIGATEXT_2.4G_ab12", "WPA2-PSK"), ("3BB_Fiber_8842", "WPA2-PSK"),
    ("Starbucks_WiFi", "Open"), ("@TrueWiFi", "Open"), (".@ AIS SUPER WiFi", "Open"), ("Office-Staff", "WPA3-SAE"),
    ("iPhone ของ น้องแนน", "WPA2-PSK"), ("Condo_1204", "WPA2-PSK"), ("7-ELEVEn_FreeWiFi", "Open"),
    ("Amazon Cafe", "Open"), ("DIRECT-4C-HP LaserJet", "WPA2-PSK"), ("NT_Fiber_5G_7731", "WPA3-SAE"),
]


IOS_WIFI = [("Somchai_Home_5G", "WPA3-SAE"), ("Grand Hotel Guest", "Open"), ("AIRPORT FREE WIFI", "Open"),
            ("CentralWorld_WiFi", "Open"), ("Team-Office", "WPA2-PSK"), ("Mom-House", "WPA2-PSK")]


def _wifi(rng: random.Random, now: datetime, ios: bool = False) -> list[WifiNetwork]:
    out = []
    # The two demo owners share a few networks (same condo, same café): co-location evidence.
    nets = WIFI[:5] + IOS_WIFI if ios else WIFI
    for ssid, sec in nets:
        out.append(
            WifiNetwork(
                ssid=ssid,
                security=sec,
                bssid=":".join(f"{rng.randint(0, 255):02x}" for _ in range(6)),
                last_connected=_ms(_random_time(rng, now, 90)),
                hidden=rng.random() < 0.05,
                source="WifiConfigStore",
            )
        )
    out.sort(key=lambda w: w.last_connected or 0, reverse=True)
    return out


APPS = [
    ("jp.naver.line.android", "LINE"), ("com.facebook.katana", "Facebook"), ("com.facebook.orca", "Messenger"),
    ("com.zhiliaoapp.musically", "TikTok"), ("com.shopee.th", "Shopee"), ("com.lazada.android", "Lazada"),
    ("com.kasikorn.retail.mbanking.wap", "K PLUS"), ("com.scb.phone", "SCB EASY"), ("ktbcs.netbank", "Krungthai NEXT"),
    ("th.go.dga.pao", "เป๋าตัง"), ("com.grabtaxi.passenger", "Grab"), ("com.linecorp.linemanth", "LINE MAN"),
    ("org.telegram.messenger", "Telegram"), ("com.whatsapp", "WhatsApp"), ("com.instagram.android", "Instagram"),
    ("th.co.truemoney.wallet", "TrueMoney"), ("mm.com.wavemoney", "Bitkub"), ("th.co.ais.myais", "myAIS"),
    ("com.kerryexpress.th", "KEX Express"), ("th.or.dga.thaid", "ThaID"), ("com.bolt.client", "Bolt"),
    ("com.google.android.youtube", "YouTube"), ("com.google.android.apps.maps", "Google Maps"),
    ("com.android.chrome", "Chrome"), ("com.google.android.gm", "Gmail"),
]


def _apps(rng: random.Random, now: datetime, ios: bool) -> list[App]:
    out = []
    for pkg, name in APPS:
        installed = _random_time(rng, now, 400)
        out.append(
            App(
                package=pkg if not ios else "th." + pkg.split(".")[-1],
                name=name,
                version=f"{rng.randint(1, 15)}.{rng.randint(0, 30)}.{rng.randint(0, 9)}",
                installed=_ms(installed),
                updated=_ms(installed + timedelta(days=rng.randint(0, 200))),
                system=pkg.startswith("com.google") or pkg == "com.android.chrome",
                installer="App Store" if ios else "com.android.vending",
            )
        )
    out.sort(key=lambda a: a.name.lower())
    return out


# ── demo extractors ─────────────────────────────────────────────────────
class DemoExtractor(BaseExtractor):
    method = "demo"

    def __init__(self, platform: str) -> None:
        self.platform = platform
        self.seed = 4242 if platform == "android" else 1717

    def device_info(self) -> DeviceInfo:
        if self.platform == "android":
            return DeviceInfo(
                platform="android",
                serial="9b01005930533036340014e659ae3c",
                brand="Redmi",
                model="25028RN03A",
                product="serenity_global",
                device_name="serenity",
                os_version="15",
                build_id="AP3A.240905.015.A2",
                security_patch="2025-09-01",
                fingerprint="Redmi/serenity_global/serenity:15/AP3A.240905.015.A2/OS2.0.208.0.VGOMIXM:user/release-keys",
                cpu_abi="arm64-v8a",
                carrier="AIS",
                phone_number=DEMO_ANDROID_NUMBER,
                timezone="Asia/Bangkok",
                battery_level=78,
                battery_status="charging",
                storage_total=128 * 1024**3,
                storage_free=41 * 1024**3,
                wifi_mac="a4:c3:f0:12:7b:9e",
                bluetooth_name="Redmi 25028RN03A",
                accounts=["somchai.demo@gmail.com (com.google)", "Xiaomi Account (com.xiaomi)"],
                extra={"demo": "1", "ro.miui.ui.version.name": "OS2.0", "ro.product.cpu.abi": "arm64-v8a"},
                restricted={"imei": "android_10_plus"},
            )
        return DeviceInfo(
            platform="ios",
            serial="F2LXK0QJ0D",
            brand="Apple",
            model="iPhone16,1",
            market_name="iPhone 15 Pro",
            product="D83AP",
            device_name="iPhone ของสมชาย",
            os_version="18.6.2",
            build_id="22G100",
            imei="356789104512339",
            imei2="356789104598871",
            phone_number=DEMO_IOS_NUMBER,
            carrier="TrueMove H",
            timezone="Asia/Bangkok",
            battery_level=64,
            battery_status="unplugged",
            storage_total=256 * 1024**3,
            storage_free=97 * 1024**3,
            wifi_mac="3c:22:fb:91:0a:4d",
            bluetooth_mac="3c:22:fb:91:0a:4e",
            extra={"demo": "1", "UniqueDeviceID": "00008130-001A2B3C4D5E001E", "ActivationState": "Activated"},
        )

    def run(self, ctx: ExtractionContext) -> DeviceInfo | None:
        rng = random.Random(self.seed)
        now = datetime.now().replace(microsecond=0)
        ios = self.platform == "ios"
        info = self.device_info()
        people = _People(rng, 53 if not ios else 61, ios)
        ctx.audit("demo", "อุปกรณ์จำลอง: ข้อมูลทั้งหมดถูกสร้างขึ้นเพื่อการสาธิต")
        if ios:
            ctx.stage("backup", 0.0)
            for i in range(1, 11):
                _sleep(0.12)
                ctx.stage("backup", i / 10)

        def step(kind: str, builder, unavailable: str | None = None, delay: float = 0.35):
            if not ctx.wants(kind):
                return
            ctx.begin(kind)
            if unavailable:
                _sleep(0.15)
                ctx.unavailable(kind, unavailable)
                return
            for i in range(1, 4):
                _sleep(delay / 3)
                ctx.progress(kind, i / 4)
            ctx.save(kind, builder())

        account = "iCloud" if ios else "com.google"
        step("contacts", lambda: _contacts(people, account))
        step("calls", lambda: _calls(people, now, 222 if not ios else 318, ios))
        step("sms", lambda: _sms(people, now, 633 if not ios else 480, ios))
        step("chats", lambda: _chats(people, now, 555), None if ios else Unavailable.REQUIRES_ROOT.value)
        step("web", lambda: _web(rng, now, 140), None if ios else Unavailable.REQUIRES_ROOT.value)
        step("notes", lambda: _notes(now), None if ios else Unavailable.NOT_SUPPORTED.value)
        step("wifi", lambda: _wifi(rng, now, ios))
        step("sim", lambda: self._sims(rng, now, ios))
        step("apps", lambda: _apps(rng, now, ios))
        if ctx.wants("voice"):
            ctx.begin("voice")
            ctx.save("voice", self._voice(ctx, rng, now, ios))
        if ctx.wants("photos"):
            ctx.begin("photos")
            ctx.save("photos", self._photos(ctx, rng, now, ios))
        return info

    def _sims(self, rng: random.Random, now: datetime, ios: bool) -> list[SimCard]:
        carriers = [("AIS", "52001"), ("TrueMove H", "52004"), ("dtac", "52005")]
        n = 2 if ios else 5
        own = DEMO_IOS_NUMBER if ios else DEMO_ANDROID_NUMBER
        out = []
        for i in range(n):
            carrier, mccmnc = carriers[i % 3]
            out.append(
                SimCard(
                    slot=f"SIM {i + 1}" if i < 2 else "เคยใช้",
                    iccid="8966" + "".join(str(rng.randint(0, 9)) for _ in range(15)),
                    imsi=mccmnc + "".join(str(rng.randint(0, 9)) for _ in range(10)) if i < 2 else "",
                    number=own if i == 0 else (_thai_mobile(rng) if i < 2 else ""),
                    carrier=carrier,
                    country="TH",
                    display_name=carrier,
                    active=i < (1 if ios else 2),
                    last_seen=_ms(now - timedelta(days=0 if i < 2 else rng.randint(30, 400))),
                )
            )
        return out

    def _voice(self, ctx: ExtractionContext, rng: random.Random, now: datetime, ios: bool) -> list[VoiceMemo]:
        out = []
        titles = ["บันทึกประชุม", "เสียงพูดคุย", "นัดหมายลูกค้า", "Recording"]
        for i, title in enumerate(titles):
            ctx.progress("voice", i / len(titles))
            seconds = rng.uniform(2.5, 5.0)
            created = _random_time(rng, now, 40)
            name = f"{title.replace(' ', '_')}_{created:%Y%m%d_%H%M%S}.wav"
            local = ctx.extraction.media_dir / "voice" / name
            make_demo_wav(local, rng, seconds)
            src = ("/private/var/mobile/Media/Recordings/" if ios else "/sdcard/MIUI/sound_recorder/") + name
            digest = ctx.register(local, src)
            out.append(VoiceMemo(title=title, path=ctx.extraction.rel(local), duration=round(seconds, 1), created=_ms(created), size=local.stat().st_size, sha256=digest))
            _sleep(0.08)
        return out

    def _photos(self, ctx: ExtractionContext, rng: random.Random, now: datetime, ios: bool):
        n = 48 if ios else 72
        make, model = ("Apple", "iPhone 15 Pro") if ios else ("Xiaomi", "25028RN03A")
        photos = []
        for i in range(n):
            ctx.progress("photos", i / n, count=i)
            taken = _random_time(rng, now, 120)
            name = f"IMG_{taken:%Y%m%d_%H%M%S}.jpg"
            album = rng.choice(["Camera", "Camera", "Camera", "Screenshots", "LINE"])
            local = ctx.extraction.media_dir / "photos" / album / name
            make_demo_jpeg(local, rng, taken, make, model, gps=album == "Camera" and rng.random() < 0.8)
            src = ("/private/var/mobile/Media/DCIM/100APPLE/" if ios else f"/sdcard/DCIM/{album}/") + name
            photos.append(ctx.photo_record(local, src, album=album, modified=_ms(taken)))
            _sleep(0.01)
        photos.sort(key=lambda p: p.taken or 0, reverse=True)
        return photos


def demo_devices() -> list[dict]:
    out = []
    for dev_id, platform in ((DEMO_ANDROID_ID, "android"), (DEMO_IOS_ID, "ios")):
        info = DemoExtractor(platform).device_info()
        out.append(
            {
                "id": dev_id,
                "platform": platform,
                "serial": info.serial,
                "state": "ready",
                "brand": info.brand,
                "model": info.market_name or info.model,
                "name": info.device_name,
                "demo": True,
            }
        )
    return out
