"""iOS parsers and backup reader against synthetic databases."""

import gzip
import hashlib
import plistlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from spni.ios import parsers
from spni.ios.backup import BackupReader

COCOA_2024 = 725_760_000  # 2024-01-01T00:00:00Z


def _db(path: Path, script: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.executescript(script)
    db.commit()
    db.close()
    return path


def test_sms_with_attributed_body(tmp_path):
    body = "สวัสดีครับ".encode("utf-8")
    blob = b"\x04\x0bstreamtyped\x81\xe8\x03\x84\x01@\x84\x84\x84\x12NSAttributedString\x00\x84\x84\x08NSObject\x00\x85\x92\x84\x84\x84\x08NSString\x01\x94\x84\x01+" + bytes([len(body)]) + body + b"\x86\x84"
    path = _db(tmp_path / "sms.db", f"""
        CREATE TABLE handle(ROWID INTEGER PRIMARY KEY, id TEXT);
        CREATE TABLE message(ROWID INTEGER PRIMARY KEY, text TEXT, attributedBody BLOB, date INTEGER, is_from_me INTEGER, service TEXT, is_read INTEGER, handle_id INTEGER);
        CREATE TABLE chat(ROWID INTEGER PRIMARY KEY, chat_identifier TEXT, display_name TEXT);
        CREATE TABLE chat_message_join(chat_id INTEGER, message_id INTEGER);
        CREATE TABLE attachment(ROWID INTEGER PRIMARY KEY, filename TEXT, transfer_name TEXT);
        CREATE TABLE message_attachment_join(message_id INTEGER, attachment_id INTEGER);
        INSERT INTO handle VALUES(1, '+66812345678');
        INSERT INTO message VALUES(1, 'hello', NULL, {COCOA_2024 * 10**9}, 0, 'iMessage', 1, 1);
        INSERT INTO message VALUES(2, NULL, X'{blob.hex()}', {COCOA_2024 * 10**9 + 10**9}, 1, 'SMS', 1, 1);
        INSERT INTO chat VALUES(1, '+66812345678', '');
        INSERT INTO chat_message_join VALUES(1, 1), (1, 2);
        INSERT INTO attachment VALUES(1, '~/Library/SMS/Attachments/IMG_0001.HEIC', 'IMG_0001.HEIC');
        INSERT INTO message_attachment_join VALUES(1, 1);
    """)
    msgs = parsers.parse_sms(path, {"0812345678": "พี่ต้น"})
    assert [m.body for m in msgs] == ["สวัสดีครับ", "hello"]
    assert msgs[1].address == "0812345678" and msgs[1].contact_name == "พี่ต้น"
    assert msgs[1].attachments == ["IMG_0001.HEIC"]
    assert msgs[1].timestamp == int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)


def test_addressbook_and_calls(tmp_path):
    ab = _db(tmp_path / "AddressBook.sqlitedb", """
        CREATE TABLE ABPerson(ROWID INTEGER PRIMARY KEY, First TEXT, Last TEXT, Organization TEXT, Note TEXT, CreationDate REAL);
        CREATE TABLE ABMultiValue(record_id INTEGER, property INTEGER, value TEXT);
        INSERT INTO ABPerson VALUES(1, 'สมชาย', 'ใจดี', NULL, NULL, 725760000);
        INSERT INTO ABMultiValue VALUES(1, 3, '+66 81 234 5678'), (1, 4, 'somchai@example.com');
    """)
    contacts = parsers.parse_addressbook(ab)
    assert contacts[0].name == "สมชาย ใจดี" and contacts[0].phones == ["+66 81 234 5678"]
    names = parsers.contact_index(contacts)
    calls_db = _db(tmp_path / "CallHistory.storedata", f"""
        CREATE TABLE ZCALLRECORD(ZADDRESS BLOB, ZDATE REAL, ZDURATION REAL, ZORIGINATED INTEGER, ZANSWERED INTEGER, ZCALLTYPE INTEGER, ZSERVICE_PROVIDER TEXT);
        INSERT INTO ZCALLRECORD VALUES(CAST('+66812345678' AS BLOB), {COCOA_2024}, 42.5, 1, 1, 1, 'com.apple.Telephony');
        INSERT INTO ZCALLRECORD VALUES('0899999999', {COCOA_2024 + 60}, 0, 0, 0, 16, 'com.apple.FaceTime');
    """)
    calls = parsers.parse_calls(calls_db, names)
    assert calls[1].direction == "outgoing" and calls[1].name == "สมชาย ใจดี" and calls[1].duration == 42
    assert calls[0].direction == "missed" and calls[0].service == "FaceTime Audio"


def _varint(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def _field(num: int, payload: bytes) -> bytes:
    return _varint(num << 3 | 2) + _varint(len(payload)) + payload


def test_notes_body_decoding(tmp_path):
    text = "รายการซื้อของ\nไข่ไก่ 1 แผง".encode("utf-8")
    proto = _field(2, _varint(1 << 3) + _varint(0) + _field(3, _field(2, text)))
    data = gzip.compress(proto)
    path = _db(tmp_path / "NoteStore.sqlite", f"""
        CREATE TABLE ZICCLOUDSYNCINGOBJECT(Z_PK INTEGER PRIMARY KEY, ZTITLE1 TEXT, ZTITLE2 TEXT, ZSNIPPET TEXT, ZCREATIONDATE3 REAL, ZMODIFICATIONDATE1 REAL, ZFOLDER INTEGER, ZNOTEDATA INTEGER);
        CREATE TABLE ZICNOTEDATA(Z_PK INTEGER PRIMARY KEY, ZDATA BLOB);
        INSERT INTO ZICCLOUDSYNCINGOBJECT VALUES(1, NULL, 'Notes', NULL, NULL, NULL, NULL, NULL);
        INSERT INTO ZICCLOUDSYNCINGOBJECT VALUES(2, 'รายการซื้อของ', NULL, 'ไข่ไก่', {COCOA_2024}, {COCOA_2024 + 5}, 1, 1);
        INSERT INTO ZICNOTEDATA VALUES(1, X'{data.hex()}');
    """)
    notes = parsers.parse_notes(path)
    assert len(notes) == 1 and notes[0].folder == "Notes"
    assert notes[0].body == "รายการซื้อของ\nไข่ไก่ 1 แผง"


def test_safari_and_wifi(tmp_path):
    path = _db(tmp_path / "History.db", f"""
        CREATE TABLE history_items(id INTEGER PRIMARY KEY, url TEXT, visit_count INTEGER);
        CREATE TABLE history_visits(id INTEGER PRIMARY KEY, history_item INTEGER, visit_time REAL, title TEXT);
        INSERT INTO history_items VALUES(1, 'https://pantip.com/topic/1', 3);
        INSERT INTO history_visits VALUES(1, 1, {COCOA_2024}, 'Pantip');
    """)
    visits = parsers.parse_safari(path)
    assert visits[0].url == "https://pantip.com/topic/1" and visits[0].visit_count == 3
    plist = tmp_path / "com.apple.wifi-networks.plist"
    plist.write_bytes(plistlib.dumps({
        "wifi.network.ssid.Home": {"SSID": b"Home", "JoinedByUserAt": datetime(2025, 5, 1), "SupportedSecurityTypes": 4},
        "wifi.network.ssid.Cafe": {"SSID": b"Cafe", "AddedAt": datetime(2024, 5, 1)},
    }, fmt=plistlib.FMT_BINARY))
    nets = parsers.parse_wifi_plist(plist)
    assert [n.ssid for n in nets] == ["Home", "Cafe"]


def test_backup_reader_resolves_files(tmp_path):
    backup = tmp_path / "backup"
    backup.mkdir()
    domain, rel = parsers.SAFARI_DB
    file_id = hashlib.sha1(f"{domain}-{rel}".encode()).hexdigest()
    (backup / file_id[:2]).mkdir()
    (backup / file_id[:2] / file_id).write_bytes(b"SQLite format 3\x00")
    meta = plistlib.dumps({"$objects": ["$null", {"Size": 16, "LastModified": 1700000000}]}, fmt=plistlib.FMT_BINARY)
    _db(backup / "Manifest.db", "CREATE TABLE Files(fileID TEXT PRIMARY KEY, domain TEXT, relativePath TEXT, flags INTEGER, file BLOB);")
    db = sqlite3.connect(backup / "Manifest.db")
    db.execute("INSERT INTO Files VALUES(?,?,?,?,?)", (file_id, domain, rel, 1, meta))
    db.commit()
    db.close()
    reader = BackupReader(backup, tmp_path / "work")
    path = reader.get(domain, rel)
    assert path and path.read_bytes().startswith(b"SQLite format 3")
    assert reader.get("HomeDomain", "missing.db") is None
    row = reader.find("Home%", "%History.db")[0]
    assert reader.file_info(row)["mtime"] == 1700000000
    reader.close()


def test_iphone_states_from_the_scan(monkeypatch):
    """Not paired → not_trusted (still connectable to ask for trust); real errors are reported, not hidden."""
    import types

    from pymobiledevice3 import exceptions, lockdown, usbmux

    from spni.ios import device

    outcomes = {
        "A": exceptions.NotPairedError(),
        "B": exceptions.InvalidHostIDError(),
        "C": exceptions.PasswordRequiredError(),
        "D": ConnectionResetError("usbmux went away"),
        "E": True,  # trusted: the client opened a session while being created
        "F": False,  # no pair record, or one the phone no longer accepts
        "G": exceptions.SessionActiveError("A lockdown session is already active.", "G", "26.1"),
    }

    class Lockdown:
        def __init__(self, paired: bool) -> None:
            self.paired = paired

        async def get_value(self, key=None, domain=None):
            return {"ProductType": "iPhone15,4", "DeviceName": "iPhone ของสมชาย"}[key]

        async def validate_pairing(self):  # like the real phone: a second StartSession is refused
            if self.paired:
                raise exceptions.SessionActiveError("A lockdown session is already active.", "E", "26.1")
            return False

        async def close(self):
            pass

    async def list_devices():
        return [types.SimpleNamespace(serial=s, is_usb=True) for s in outcomes]

    async def create(serial=None, autopair=True, **kw):
        assert autopair is False  # scanning must never pop the trust dialog
        out = outcomes[serial]
        if isinstance(out, Exception):
            raise out
        return Lockdown(out)

    monkeypatch.setattr(usbmux, "list_devices", list_devices)
    monkeypatch.setattr(lockdown, "create_using_usbmux", create)
    found = {d["serial"]: d for d in device.list_devices()}
    assert {k: v["state"] for k, v in found.items()} == {
        "A": "not_trusted", "B": "not_trusted", "C": "locked", "D": "error", "E": "ready", "F": "not_trusted", "G": "ready"}
    assert found["D"]["detail"].startswith("ConnectionResetError: usbmux went away")
    assert found["E"]["model"] == "iPhone 15" and found["E"]["name"] == "iPhone ของสมชาย"
