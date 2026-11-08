"""Column definitions and value formatting shared by all report formats."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from ..util import human_size

THAI_MONTHS = [
    "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
    "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม",
]

KIND_LABELS = {
    "calls": ("ประวัติการโทร", "Call log"),
    "contacts": ("รายชื่อ", "Contacts"),
    "sms": ("SMS / iMessage", "SMS / iMessage"),
    "chats": ("แชต", "Chats"),
    "web": ("ประวัติเว็บ", "Web history"),
    "notes": ("บันทึก", "Notes"),
    "voice": ("บันทึกเสียง", "Voice recordings"),
    "wifi": ("Wi-Fi", "Wi-Fi"),
    "sim": ("SIM", "SIM"),
    "photos": ("รูปภาพ", "Photos"),
    "apps": ("แอปพลิเคชัน", "Apps"),
}

DIRECTIONS = {
    "incoming": ("โทรเข้า", "Incoming"),
    "outgoing": ("โทรออก", "Outgoing"),
    "missed": ("ไม่ได้รับ", "Missed"),
    "rejected": ("ปฏิเสธ", "Rejected"),
    "blocked": ("บล็อก", "Blocked"),
    "voicemail": ("ฝากข้อความ", "Voicemail"),
    "unknown": ("ไม่ทราบ", "Unknown"),
    "in": ("รับ", "Received"),
    "out": ("ส่ง", "Sent"),
}

UNAVAILABLE = {
    "requires_root": ("ต้องใช้สิทธิ์ root (ข้อมูลอยู่ในพื้นที่ส่วนตัวของแอป)", "Requires root (app-private storage)"),
    "requires_encrypted_backup": ("ต้องใช้ backup แบบเข้ารหัส", "Requires an encrypted backup"),
    "permission_denied": ("ระบบปฏิบัติการไม่อนุญาตให้อ่าน", "Denied by the operating system"),
    "not_in_backup": ("ไม่พบใน backup", "Not present in the backup"),
    "not_supported": ("ไม่รองรับบนอุปกรณ์นี้", "Not supported on this device"),
    "agent_declined": ("ไม่ได้อนุญาตให้ติดตั้งแอปตัวช่วย", "Helper app not allowed"),
    "agent_missing": ("ไม่พบไฟล์แอปตัวช่วยในโปรแกรม", "Helper app not bundled"),
    "skipped": ("ไม่ได้เลือก", "Not selected"),
    "error": ("เกิดข้อผิดพลาด", "Error"),
}


# Set to 543 while rendering a report that uses the Buddhist era (see spni.report).
YEAR_OFFSET = 0


def fmt_dt(ms: Any) -> str:
    if not ms:
        return ""
    try:
        dt = datetime.fromtimestamp(int(ms) / 1000)
    except (ValueError, OSError, OverflowError):
        return ""
    return f"{dt:%d/%m/}{dt.year + YEAR_OFFSET}{dt:  %H:%M:%S}".replace("  ", " ")


def fmt_iso(value: Any) -> str:
    """ISO-8601 string from the case database → local ``dd/mm/yyyy HH:MM:SS``."""
    if not value:
        return ""
    try:
        return datetime.fromisoformat(str(value)).astimezone().strftime("%d/%m/%Y %H:%M:%S")
    except ValueError:
        return str(value)


def thai_date(dt: datetime | None = None) -> str:
    dt = dt or datetime.now()
    return f"{dt.day} {THAI_MONTHS[dt.month - 1]} {dt.year + 543}"


def fmt_duration(sec: Any) -> str:
    try:
        sec = int(float(sec or 0))
    except (TypeError, ValueError):
        return ""
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _dir(lang: int) -> Callable[[dict], str]:
    return lambda r: DIRECTIONS.get(r.get("direction", ""), (r.get("direction", ""),) * 2)[lang]


Column = tuple[str, str, Callable[[dict[str, Any]], Any], float]  # th, en, getter, relative width


def columns(kind: str, lang: str = "th") -> list[Column]:
    li = 0 if lang == "th" else 1
    cols: dict[str, list[Column]] = {
        "calls": [
            ("วันเวลา", "Date/time", lambda r: fmt_dt(r.get("timestamp")), 1.3),
            ("ประเภท", "Type", _dir(li), 0.8),
            ("หมายเลข", "Number", lambda r: r.get("number", ""), 1.1),
            ("ชื่อ", "Name", lambda r: r.get("name", ""), 1.4),
            ("ระยะเวลา", "Duration", lambda r: fmt_duration(r.get("duration")), 0.7),
            ("ซิม/บริการ", "SIM/Service", lambda r: " ".join(x for x in (r.get("sim", ""), "" if r.get("service") == "cellular" else r.get("service", "")) if x), 0.9),
        ],
        "contacts": [
            ("ชื่อ", "Name", lambda r: r.get("name", ""), 1.5),
            ("หมายเลขโทรศัพท์", "Phone numbers", lambda r: ", ".join(r.get("phones", [])), 1.6),
            ("อีเมล", "Email", lambda r: ", ".join(r.get("emails", [])), 1.4),
            ("องค์กร", "Organization", lambda r: r.get("organization", ""), 1.1),
            ("บัญชี", "Account", lambda r: r.get("account", ""), 0.9),
        ],
        "sms": [
            ("วันเวลา", "Date/time", lambda r: fmt_dt(r.get("timestamp")), 1.2),
            ("ทิศทาง", "Direction", _dir(li), 0.5),
            ("หมายเลข/ผู้ส่ง", "Number/Sender", lambda r: r.get("address", ""), 1.0),
            ("ชื่อ", "Name", lambda r: r.get("contact_name", ""), 1.0),
            ("ข้อความ", "Message", lambda r: r.get("body", ""), 3.4),
            ("บริการ", "Service", lambda r: r.get("service", ""), 0.6),
        ],
        "chats": [
            ("วันเวลา", "Date/time", lambda r: fmt_dt(r.get("timestamp")), 1.2),
            ("แอป", "App", lambda r: r.get("app", ""), 0.6),
            ("ห้องแชต", "Chat", lambda r: r.get("thread", ""), 1.2),
            ("ผู้ส่ง", "Sender", lambda r: r.get("sender", ""), 1.0),
            ("ข้อความ", "Message", lambda r: r.get("body", ""), 3.4),
        ],
        "web": [
            ("วันเวลา", "Date/time", lambda r: fmt_dt(r.get("timestamp")), 1.2),
            ("ชื่อหน้า", "Title", lambda r: r.get("title", ""), 2.0),
            ("URL", "URL", lambda r: r.get("url", ""), 3.0),
            ("ครั้ง", "Visits", lambda r: r.get("visit_count", ""), 0.5),
        ],
        "notes": [
            ("แก้ไขล่าสุด", "Modified", lambda r: fmt_dt(r.get("modified")), 1.2),
            ("ชื่อเรื่อง", "Title", lambda r: r.get("title", ""), 1.4),
            ("เนื้อหา", "Content", lambda r: r.get("body", ""), 4.0),
            ("โฟลเดอร์", "Folder", lambda r: r.get("folder", ""), 0.8),
        ],
        "voice": [
            ("วันเวลา", "Date/time", lambda r: fmt_dt(r.get("created")), 1.2),
            ("ชื่อ", "Title", lambda r: r.get("title", ""), 1.5),
            ("ความยาว", "Length", lambda r: fmt_duration(r.get("duration")) if r.get("duration") else "", 0.6),
            ("ขนาด", "Size", lambda r: human_size(r.get("size")), 0.6),
            ("SHA-256", "SHA-256", lambda r: r.get("sha256", ""), 3.0),
        ],
        "wifi": [
            ("ชื่อเครือข่าย (SSID)", "SSID", lambda r: r.get("ssid", ""), 2.0),
            ("ความปลอดภัย", "Security", lambda r: r.get("security", ""), 1.0),
            ("BSSID", "BSSID", lambda r: r.get("bssid", ""), 1.2),
            ("เชื่อมต่อล่าสุด", "Last joined", lambda r: fmt_dt(r.get("last_connected")), 1.2),
        ],
        "sim": [
            ("ช่อง", "Slot", lambda r: r.get("slot", ""), 0.6),
            ("ผู้ให้บริการ", "Carrier", lambda r: r.get("carrier", ""), 1.0),
            ("หมายเลข", "Number", lambda r: r.get("number", ""), 1.0),
            ("ICCID", "ICCID", lambda r: r.get("iccid", ""), 1.6),
            ("IMSI", "IMSI", lambda r: r.get("imsi", ""), 1.4),
            ("สถานะ", "Status", lambda r: ("ใช้งาน" if li == 0 else "Active") if r.get("active") else ("ไม่ใช้งาน" if li == 0 else "Inactive"), 0.7),
        ],
        "photos": [
            ("วันที่ถ่าย", "Taken", lambda r: fmt_dt(r.get("taken")), 1.2),
            ("ชื่อไฟล์", "File", lambda r: r.get("name", ""), 1.4),
            ("อัลบั้ม", "Album", lambda r: r.get("album", ""), 0.7),
            ("ขนาด", "Size", lambda r: human_size(r.get("size")), 0.6),
            ("พิกัด", "GPS", lambda r: f"{r['lat']:.5f}, {r['lon']:.5f}" if r.get("lat") is not None else "", 1.1),
            ("SHA-256", "SHA-256", lambda r: r.get("sha256", ""), 2.8),
        ],
        "apps": [
            ("ชื่อแอป", "App", lambda r: r.get("name") or r.get("package", ""), 1.3),
            ("แพ็กเกจ", "Package", lambda r: r.get("package", ""), 2.0),
            ("เวอร์ชัน", "Version", lambda r: r.get("version", ""), 0.8),
            ("ติดตั้งเมื่อ", "Installed", lambda r: fmt_dt(r.get("installed")), 1.2),
            ("ประเภท", "Type", lambda r: ("ระบบ" if li == 0 else "System") if r.get("system") else ("ผู้ใช้" if li == 0 else "User"), 0.6),
        ],
    }
    return cols[kind]


def header(col: Column, lang: str) -> str:
    return col[0] if lang == "th" else col[1]


DEVICE_FIELDS = [
    ("brand", "ยี่ห้อ", "Brand"),
    ("model", "รุ่น (Model)", "Model"),
    ("market_name", "ชื่อทางการตลาด", "Marketing name"),
    ("device_name", "ชื่ออุปกรณ์", "Device name"),
    ("product", "ชื่อผลิตภัณฑ์", "Product"),
    ("os_version", "เวอร์ชันระบบปฏิบัติการ", "OS version"),
    ("build_id", "รหัสบิลด์", "Build ID"),
    ("security_patch", "แพตช์ความปลอดภัย", "Security patch"),
    ("serial", "หมายเลขซีเรียล", "Serial number"),
    ("imei", "IMEI", "IMEI"),
    ("imei2", "IMEI 2", "IMEI 2"),
    ("phone_number", "เบอร์เครื่อง", "Device phone number"),
    ("carrier", "ผู้ให้บริการ", "Carrier"),
    ("wifi_mac", "Wi-Fi MAC", "Wi-Fi MAC"),
    ("bluetooth_mac", "Bluetooth MAC", "Bluetooth MAC"),
    ("timezone", "เขตเวลา", "Time zone"),
]


def device_rows(device: dict[str, Any], lang: str = "th") -> list[tuple[str, str]]:
    li = 1 if lang == "th" else 2
    rows = []
    for field in DEVICE_FIELDS:
        value = device.get(field[0])
        if field[0] == "imei" and not value and device.get("restricted", {}).get("imei"):
            value = "ไม่สามารถอ่านได้ (Android 10 ขึ้นไป)" if lang == "th" else "Not readable (Android 10+)"
        if value:
            rows.append((field[li], str(value)))
    if device.get("storage_total"):
        rows.append(("พื้นที่เก็บข้อมูล" if lang == "th" else "Storage",
                     f"{human_size(device.get('storage_free'))} / {human_size(device['storage_total'])}"))
    for acc in device.get("accounts") or []:
        rows.append(("บัญชีบนเครื่อง" if lang == "th" else "Account", acc))
    return rows
