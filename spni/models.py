"""Record types produced by the extractors.

Every record is a plain dataclass that serialises to a JSON-friendly dict, so
the same objects are stored in the case database, sent to the UI and written to
reports. Timestamps are Unix milliseconds (UTC); the UI formats them.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class Kind(str, Enum):
    CALLS = "calls"
    CONTACTS = "contacts"
    SMS = "sms"
    CHATS = "chats"
    WEB = "web"
    NOTES = "notes"
    VOICE = "voice"
    WIFI = "wifi"
    SIM = "sim"
    PHOTOS = "photos"
    APPS = "apps"


ALL_KINDS: list[str] = [k.value for k in Kind]


class Unavailable(str, Enum):
    """Why a category could not be extracted. The UI translates these codes."""

    REQUIRES_ROOT = "requires_root"
    REQUIRES_ENCRYPTED_BACKUP = "requires_encrypted_backup"
    PERMISSION_DENIED = "permission_denied"
    NOT_IN_BACKUP = "not_in_backup"
    NOT_SUPPORTED = "not_supported"
    AGENT_DECLINED = "agent_declined"
    AGENT_MISSING = "agent_missing"
    SKIPPED = "skipped"
    ERROR = "error"


class Record:
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)  # type: ignore[arg-type]


@dataclass
class DeviceInfo(Record):
    platform: str  # "android" | "ios"
    serial: str
    brand: str = ""
    model: str = ""
    market_name: str = ""
    product: str = ""
    device_name: str = ""
    os_version: str = ""
    build_id: str = ""
    security_patch: str = ""
    fingerprint: str = ""
    cpu_abi: str = ""
    imei: str = ""
    imei2: str = ""
    phone_number: str = ""
    carrier: str = ""
    timezone: str = ""
    battery_level: int | None = None
    battery_status: str = ""
    storage_total: int | None = None
    storage_free: int | None = None
    wifi_mac: str = ""
    bluetooth_mac: str = ""
    bluetooth_name: str = ""
    accounts: list[str] = field(default_factory=list)
    extra: dict[str, str] = field(default_factory=dict)
    # Fields that the OS refused to reveal, with the reason code.
    restricted: dict[str, str] = field(default_factory=dict)


@dataclass
class CallRecord(Record):
    number: str
    name: str = ""
    direction: str = "unknown"  # incoming | outgoing | missed | rejected | blocked | unknown
    timestamp: int | None = None
    duration: int = 0
    sim: str = ""
    service: str = "cellular"
    location: str = ""
    # Filled by CDR imports (operator call detail records).
    own_number: str = ""
    cell: str = ""
    cell_end: str = ""
    site: str = ""
    lat: float | None = None
    lon: float | None = None
    azimuth: int | None = None


@dataclass
class Contact(Record):
    name: str
    phones: list[str] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    organization: str = ""
    note: str = ""
    account: str = ""
    starred: bool = False
    created: int | None = None


@dataclass
class SmsMessage(Record):
    address: str
    body: str
    direction: str  # in | out
    timestamp: int | None = None
    thread: str = ""
    contact_name: str = ""
    read: bool = True
    service: str = "SMS"  # SMS | MMS | iMessage | RCS
    attachments: list[str] = field(default_factory=list)


@dataclass
class ChatMessage(Record):
    app: str
    thread: str
    sender: str
    body: str
    direction: str  # in | out
    timestamp: int | None = None
    attachment: str = ""


@dataclass
class WebVisit(Record):
    url: str
    title: str = ""
    timestamp: int | None = None
    visit_count: int = 1
    browser: str = ""


@dataclass
class Note(Record):
    title: str
    body: str = ""
    folder: str = ""
    created: int | None = None
    modified: int | None = None
    source: str = ""


@dataclass
class VoiceMemo(Record):
    title: str
    path: str = ""  # relative to the extraction folder
    duration: float | None = None
    created: int | None = None
    size: int | None = None
    sha256: str = ""


@dataclass
class WifiNetwork(Record):
    ssid: str
    security: str = ""
    bssid: str = ""
    last_connected: int | None = None
    hidden: bool = False
    password: str = ""
    source: str = ""


@dataclass
class SimCard(Record):
    slot: str = ""
    iccid: str = ""
    imsi: str = ""
    number: str = ""
    carrier: str = ""
    country: str = ""
    display_name: str = ""
    active: bool = False
    last_seen: int | None = None


@dataclass
class Photo(Record):
    name: str
    path: str  # relative to the extraction folder
    thumb: str = ""
    size: int | None = None
    taken: int | None = None
    modified: int | None = None
    width: int | None = None
    height: int | None = None
    make: str = ""
    camera_model: str = ""
    lat: float | None = None
    lon: float | None = None
    album: str = ""
    sha256: str = ""
    source_path: str = ""


@dataclass
class App(Record):
    package: str
    name: str = ""
    version: str = ""
    installed: int | None = None
    updated: int | None = None
    system: bool = False
    installer: str = ""


def to_dicts(records) -> list[dict[str, Any]]:
    return [r.to_dict() if isinstance(r, Record) else dict(r) for r in records]
