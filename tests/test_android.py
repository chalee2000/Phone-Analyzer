"""Android extraction against a fake device that replays realistic ADB output."""

import re
import shlex
from pathlib import Path

import pytest

from spni.android.content import ContentQueryError, parse_rows
from spni.android.extract import AndroidExtractor, parse_dumpsys_packages, parse_list_networks
from spni.android.info import parse_parcel_string
from spni.case.store import CaseStore
from spni.events import EventBus
from spni.extract import ExtractionContext

GETPROP = """\
[ro.product.brand]: [Redmi]
[ro.product.model]: [25028RN03A]
[ro.product.marketname]: [Redmi Note]
[ro.product.name]: [serenity_global]
[ro.product.device]: [serenity]
[ro.build.version.release]: [15]
[ro.build.version.sdk]: [35]
[ro.build.id]: [AP3A.240905.015.A2]
[ro.build.version.security_patch]: [2025-09-01]
[ro.serialno]: [9b01005930533036340014e659ae3c]
[ro.product.cpu.abi]: [arm64-v8a]
[gsm.operator.alpha]: [AIS,]
[gsm.sim.operator.alpha]: [AIS,TRUE-H]
[gsm.sim.state]: [LOADED,LOADED]
[persist.sys.timezone]: [Asia/Bangkok]
[ro.miui.ui.version.name]: [OS2.0]
"""

CALLS = """\
Row: 0 _id=1, number=+66812345678, date=1730956800000, duration=65, type=2, subscription_id=1, geocoded_location=Thailand, name=พี่ต้น
Row: 1 _id=2, number=021234567, date=1730960400000, duration=0, type=3, subscription_id=NULL, geocoded_location=NULL, name=NULL
"""

CONTACTS = """\
Row: 0 contact_id=7, mimetype=vnd.android.cursor.item/name, account_type=com.google, starred=0, data2=ต้น, display_name=พี่ต้น, data1=พี่ต้น
Row: 1 contact_id=7, mimetype=vnd.android.cursor.item/phone_v2, account_type=com.google, starred=0, data2=2, display_name=พี่ต้น, data1=081-234-5678
Row: 2 contact_id=7, mimetype=vnd.android.cursor.item/email_v2, account_type=com.google, starred=0, data2=1, display_name=พี่ต้น, data1=ton@example.com
"""

SMS = """\
Row: 0 _id=10, thread_id=3, address=+66812345678, date=1730956900000, type=1, read=1, body=ถึงไหนแล้ว, รอนานแล้วนะ
Row: 1 _id=11, thread_id=3, address=0812345678, date=1730957000000, type=2, read=1, body=อีก 10 นาที
ขึ้นบรรทัดใหม่, address=ไม่ใช่คอลัมน์
Row: 2 _id=12, thread_id=4, address=AIS, date=1730957100000, type=1, read=0, body=NULL
"""

WIFI = """\
Network Id      SSID                         Security type
0               AIS 4G Hi-Speed Home WiFi    wpa2-psk
1               Starbucks_WiFi               open
"""

PACKAGES = """\
Packages:
  Package [jp.naver.line.android] (abc):
    versionName=15.2.1
    firstInstallTime=2025-01-02 10:11:12
    lastUpdateTime=2025-10-01 08:00:00
    installerPackageName=com.android.vending
    pkgFlags=[ HAS_CODE ALLOW_CLEAR_USER_DATA ]
  Package [com.android.settings] (def):
    versionName=15
    pkgFlags=[ SYSTEM HAS_CODE ]
"""

DENIED = "Error while accessing provider:sms\njava.lang.SecurityException: Permission Denial: opening provider requires android.permission.READ_SMS\n"


class FakeDevice:
    serial = "9b01005930533036340014e659ae3c"

    def __init__(self, deny_sms: bool = False, files: dict | None = None, contents: dict | None = None,
                 app_files: dict | None = None, deny_app_dir: bool = False):
        self.deny_sms = deny_sms
        self.files = files or {}  # shared storage: path -> (size, mtime)
        self.contents = contents or {}  # remote path -> bytes (anything else pulls as a JPEG)
        self.app_files = app_files or {}  # LINE's Android/data folder: path -> (size, mtime)
        self.deny_app_dir = deny_app_dir
        self.commands: list[str] = []

    def shell(self, cmd: str, timeout: float = 120) -> str:
        self.commands.append(cmd)
        if cmd == "getprop":
            return GETPROP
        if cmd.startswith("content query --uri content://call_log/calls"):
            return CALLS
        if cmd.startswith("content query --uri content://com.android.contacts/data"):
            return CONTACTS
        if cmd.startswith("content query --uri content://sms"):
            return DENIED if self.deny_sms else SMS
        if cmd.startswith("content query --uri content://telephony/siminfo"):
            return "Error while accessing provider:telephony\njava.lang.SecurityException: Permission Denial"
        if cmd == "dumpsys battery":
            return "Current Battery Service state:\n  AC powered: true\n  status: 2\n  level: 78\n"
        if cmd == "df -k /data":
            return "Filesystem 1K-blocks Used Available Use% Mounted on\n/dev/block/dm-50 115343360 72000000 43343360 63% /data\n"
        if cmd == "dumpsys account":
            return "Accounts: 1\n    Account {name=somchai@gmail.com, type=com.google}\n"
        if cmd == "cmd wifi list-networks":
            return WIFI
        if cmd == "dumpsys package packages":
            return PACKAGES
        if cmd.startswith("head -c "):
            path = cmd.split(" ", 3)[3].strip("'")
            return self.contents.get(path, b"")[:64].decode("utf-8", "replace")
        if cmd.startswith("ls -d /sdcard/Android/data/"):
            path = cmd.split()[2]
            if self.deny_app_dir:
                return f"ls: {path}: Permission denied"
            return path if self.app_files else f"ls: {path}: No such file or directory"
        if "od -An" in cmd:  # LINE app folder probe: size|mtime|path|first 16 bytes as hex
            return "\n".join(f"{size}|{mtime}|{path}|{self.contents.get(path, b'')[:16].hex()}" for path, (size, mtime) in self.app_files.items())
        if cmd.startswith("find "):
            exts = re.findall(r"-iname '\*(\.[^']+)'", cmd)
            dirs = [d.rstrip("/") for d in shlex.split(cmd[5:].split(" -type")[0])]
            return "\n".join(
                f"{size}|{mtime}|{path}" for path, (size, mtime) in self.files.items()
                if any(path.startswith(d + "/") for d in dirs) and (not exts or any(path.lower().endswith(e) for e in exts))
            )
        return ""

    def pull(self, remote: str, local: Path) -> None:
        local.parent.mkdir(parents=True, exist_ok=True)
        if remote in self.contents:
            local.write_bytes(self.contents[remote])
            return
        from PIL import Image

        Image.new("RGB", (64, 48), (200, 100, 50)).save(local, "JPEG")

    def push(self, local: Path, remote: str) -> None:
        pass


def make_ctx(tmp_path, kinds, options=None):
    store = CaseStore(tmp_path / "cases")
    case = store.create_case({"case_no": "1/2569"})
    ext = case.create_extraction({"platform": "android", "serial": "x"}, "adb-logical")
    events = []
    bus = EventBus()
    bus.subscribe(lambda n, p: events.append((n, p)))
    return ExtractionContext(ext, bus, "job", kinds, options or {}), case, events


def test_parse_rows_keeps_commas_and_newlines_in_body():
    rows = parse_rows(SMS, ["_id", "thread_id", "address", "date", "type", "read", "body"])
    assert rows[0]["body"] == "ถึงไหนแล้ว, รอนานแล้วนะ"
    assert rows[1]["body"] == "อีก 10 นาที\nขึ้นบรรทัดใหม่, address=ไม่ใช่คอลัมน์"
    assert rows[2]["body"] is None


def test_parse_rows_permission_denied():
    with pytest.raises(ContentQueryError) as exc:
        parse_rows(DENIED, ["_id"])
    assert exc.value.denied


def test_device_info_from_getprop():
    info = AndroidExtractor(FakeDevice()).device_info()
    assert info.brand == "Redmi" and info.model == "25028RN03A" and info.os_version == "15"
    assert info.build_id == "AP3A.240905.015.A2"
    assert info.battery_level == 78 and info.battery_status == "charging"
    assert info.storage_total == 115343360 * 1024
    assert info.accounts == ["somchai@gmail.com (com.google)"]
    assert info.restricted["imei"] == "android_10_plus"


def test_full_extraction_with_providers(tmp_path):
    dev = FakeDevice(files={"/sdcard/DCIM/Camera/IMG_1.jpg": (1234, 1730956800)})
    ctx, case, events = make_ctx(tmp_path, ["contacts", "calls", "sms", "wifi", "sim", "apps", "photos", "chats"])
    AndroidExtractor(dev).run(ctx)
    ext = ctx.extraction
    calls = ext.records("calls")
    assert calls[0]["direction"] == "missed" and calls[1]["number"] == "0812345678"
    assert calls[1]["name"] == "พี่ต้น" and calls[1]["sim"] == "SIM 1"
    contacts = ext.records("contacts")
    assert contacts[0]["phones"] == ["081-234-5678"] and contacts[0]["emails"] == ["ton@example.com"]
    sms = ext.records("sms")
    assert {m["direction"] for m in sms} == {"in", "out"}
    assert any(m["contact_name"] == "พี่ต้น" for m in sms)
    assert [w["ssid"] for w in ext.records("wifi")] == ["AIS 4G Hi-Speed Home WiFi", "Starbucks_WiFi"]
    sims = ext.records("sim")
    assert [s["carrier"] for s in sims] == ["AIS", "TRUE-H"]
    apps = ext.records("apps")
    assert apps[0]["name"] == "LINE" and apps[0]["installed"]
    photos = ext.records("photos")
    assert photos[0]["sha256"] and photos[0]["thumb"].startswith("thumbs/")
    assert case.files(ext.id)[0]["source"] == "/sdcard/DCIM/Camera/IMG_1.jpg"
    info = case.extraction_info(ext.id)
    assert info["unavailable"]["chats"]["reason"] == "line_export_needed"  # no LINE export on this phone
    audit = [a["detail"] for a in case.audit_entries(ext.id)]
    assert any(d.startswith("getprop") for d in audit), "every ADB command must be audited"


def test_sms_denied_without_agent_permission(tmp_path):
    ctx, case, _ = make_ctx(tmp_path, ["sms"], {"android_allow_agent": False})
    AndroidExtractor(FakeDevice(deny_sms=True)).run(ctx)
    info = case.extraction_info(ctx.extraction.id)
    assert info["unavailable"]["sms"]["reason"] == "agent_declined"


def test_sms_denied_agent_missing(tmp_path):
    ctx, case, _ = make_ctx(tmp_path, ["sms"], {"android_allow_agent": True})
    AndroidExtractor(FakeDevice(deny_sms=True), agent_apk=tmp_path / "missing.apk").run(ctx)
    assert case.extraction_info(ctx.extraction.id)["unavailable"]["sms"]["reason"] == "agent_missing"


def test_wifi_and_packages_parsers():
    assert parse_list_networks("") == []
    apps = parse_dumpsys_packages(PACKAGES)
    assert apps[1].system and not apps[0].system


def test_packages_with_1970_install_time():
    """Xiaomi lists preinstalled apps as installed at the epoch (local time)."""
    out = """  Package [com.miui.home] (8f1e2a):
    versionName=4.39.9
    firstInstallTime=1970-01-01 07:00:00
    lastUpdateTime=1969-12-31 23:59:59
    pkgFlags=[ SYSTEM HAS_CODE ]
  Package [jp.naver.line.android] (77aa01):
    versionName=15.18.1
    firstInstallTime=2025-03-02 10:11:12
"""
    apps = {a.package: a for a in parse_dumpsys_packages(out)}
    assert apps["com.miui.home"].system and isinstance(apps["com.miui.home"].installed, int)
    assert isinstance(apps["com.miui.home"].updated, int)
    assert apps["jp.naver.line.android"].version == "15.18.1" and apps["jp.naver.line.android"].installed > 0


def test_parcel_imei():
    out = """Result: Parcel(
  0x00000000: 00000000 0000000f 00350033 00370036 '........3.5.6.7.'
  0x00000010: 00390038 00310030 00350034 00320031 '8.9.0.1.4.5.1.2.'
  0x00000020: 00330033 00000039                   '3.3.9...        ')"""
    assert re.fullmatch(r"\d{15}", parse_parcel_string(out))


# ── LINE media without root ─────────────────────────────────────────────
def _jpeg() -> bytes:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (40, 30), (20, 160, 90)).save(buf, "JPEG")
    return buf.getvalue()


LINE_APP = "/sdcard/Android/data/jp.naver.line.android"


def test_line_media_from_shared_storage_and_app_folder(tmp_path):
    jpg = _jpeg()
    mp4 = b"\x00\x00\x00\x20ftypisom" + b"\x00" * 30000
    aac = b"\xff\xf1\x50\x80" + b"\x00" * 20000
    t = 1762790400
    dev = FakeDevice(
        files={
            "/sdcard/DCIM/Camera/IMG_1.jpg": (1000, t),
            "/sdcard/Pictures/LINE/LINE_P1.jpg": (1000, t),
            "/sdcard/Movies/LINE/LINE_MOVIE_1.mp4": (len(mp4), t + 1),
        },
        contents={
            "/sdcard/Movies/LINE/LINE_MOVIE_1.mp4": mp4,
            f"{LINE_APP}/files/storage/mo/1001": jpg,
            f"{LINE_APP}/files/storage/mo/1002": mp4,
            f"{LINE_APP}/files/storage/mo/1003": aac,
            f"{LINE_APP}/cache/sticker/55": jpg,
        },
        app_files={
            f"{LINE_APP}/files/storage/mo/1001": (len(jpg) + 9000, t + 2),
            f"{LINE_APP}/files/storage/mo/1002": (len(mp4), t + 3),
            f"{LINE_APP}/files/storage/mo/1003": (len(aac), t + 4),
            f"{LINE_APP}/cache/sticker/55": (len(jpg) + 9000, t + 5),
        },
    )
    ctx, case, _ = make_ctx(tmp_path, ["photos"])
    AndroidExtractor(dev).run(ctx)
    photos = {p["source_path"]: p for p in case.records(ctx.extraction.id, "photos")}
    assert photos["/sdcard/Pictures/LINE/LINE_P1.jpg"]["album"] == "LINE"  # pulled once, by the normal photo pass
    video = photos["/sdcard/Movies/LINE/LINE_MOVIE_1.mp4"]
    assert video["kind"] == "video" and video["album"] == "LINE" and len(video["sha256"]) == 64
    app_img = photos[f"{LINE_APP}/files/storage/mo/1001"]
    assert app_img["kind"] == "image" and app_img["album"] == "LINE (ในแอป)" and app_img["thumb"] and app_img["path"].endswith("1001.jpg")
    assert photos[f"{LINE_APP}/files/storage/mo/1002"]["path"].endswith("1002.mp4")
    assert photos[f"{LINE_APP}/files/storage/mo/1003"]["kind"] == "audio"
    assert f"{LINE_APP}/cache/sticker/55" not in photos  # stickers are not evidence media
    assert (ctx.extraction.dir / video["path"]).is_file()


def test_line_app_folder_refused_is_logged(tmp_path):
    dev = FakeDevice(files={"/sdcard/DCIM/Camera/IMG_1.jpg": (1000, 1762790400)}, deny_app_dir=True)
    ctx, case, _ = make_ctx(tmp_path, ["photos"])
    AndroidExtractor(dev).run(ctx)
    assert len(case.records(ctx.extraction.id, "photos")) == 1
    audit = " ".join(e["detail"] for e in case.audit_entries(ctx.extraction.id) if e["action"] == "line.media")
    assert "Permission denied" in audit
