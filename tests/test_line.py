"""LINE on iPhone: every message type, chat names, WAL rows and attachments from a backup."""

import hashlib
import io
import json
import plistlib
import shutil
import sqlite3
from pathlib import Path

from PIL import Image

from spni.case.store import CaseStore
from spni.events import EventBus
from spni.extract import ExtractionContext
from spni.ios import parsers
from spni.ios.backup import BackupReader
from spni.ios.extract import IOSExtractor

T = 1_760_000_000_000  # ms, as LINE stores ZTIMESTAMP
DOMAIN = "AppDomainGroup-group.com.linecorp.line"
STORE = "Library/Application Support/PrivateStore/P_u0"
DB_REL = f"{STORE}/Messages/Line.sqlite"

SCHEMA = """
CREATE TABLE ZUSER(Z_PK INTEGER PRIMARY KEY, ZMID TEXT, ZNAME TEXT, ZCUSTOMNAME TEXT);
CREATE TABLE ZGROUP(Z_PK INTEGER PRIMARY KEY, ZID TEXT, ZNAME TEXT);
CREATE TABLE ZCHAT(Z_PK INTEGER PRIMARY KEY, ZMID TEXT, ZTYPE INTEGER);
CREATE TABLE ZMESSAGE(Z_PK INTEGER PRIMARY KEY, ZCHAT INTEGER, ZSENDER INTEGER, ZTEXT TEXT, ZTIMESTAMP TEXT,
  ZCONTENTTYPE INTEGER, ZID TEXT, ZCONTENTMETADATA BLOB, ZLATITUDE REAL, ZLONGITUDE REAL);
INSERT INTO ZUSER VALUES(1, 'u1', 'Ton', 'พี่ต้น'), (2, 'u2', 'สมศรี', NULL);
INSERT INTO ZGROUP VALUES(1, 'c1', 'ทีมขาย');
INSERT INTO ZCHAT VALUES(1, 'u1', 0), (2, 'c1', 2), (3, 'r1', 1);
"""


def keyed_archive(d: dict) -> bytes:
    objs = ["$null", {"NS.keys": [], "NS.objects": [], "$class": plistlib.UID(0)}]
    for k, v in d.items():
        objs.append(k)
        objs[1]["NS.keys"].append(plistlib.UID(len(objs) - 1))
        objs.append(v)
        objs[1]["NS.objects"].append(plistlib.UID(len(objs) - 1))
    return plistlib.dumps({"$archiver": "NSKeyedArchiver", "$top": {"root": plistlib.UID(1)}, "$objects": objs}, fmt=plistlib.FMT_BINARY)


MESSAGES = [
    # (chat, sender, text, ts offset, type, server id, metadata)
    (1, 1, "สวัสดีครับ", 1, 0, "1000", None),
    (1, None, "ว่าไง", 2, 0, "1009", None),
    (1, 1, None, 3, 1, "1001", None),
    (1, 1, None, 4, 2, "1002", json.dumps({"DURATION": "65000"}).encode()),
    (1, None, None, 5, 3, "1003", plistlib.dumps({"AUDLEN": "15000"}, fmt=plistlib.FMT_BINARY)),
    (1, 1, None, 6, 6, "1004", json.dumps({"DURATION": "154000", "TYPE": "A"}).encode()),
    (1, 1, None, 7, 7, "1005", json.dumps({"STKTXT": "ขอบคุณ"}).encode()),
    (1, 1, None, 8, 14, "1006", keyed_archive({"FILE_NAME": "สัญญา.pdf", "FILE_SIZE": "1234"})),
    (1, 1, "ร้านกาแฟ", 9, 15, "1007", None),
    (2, 2, "ประชุมกี่โมง", 10, 0, "2000", None),
    (2, 1, None, 11, 18, "2001", None),  # chat event without text: skipped
    (3, 1, "อยู่ไหน", 12, 0, "3000", None),
    (3, 2, "กำลังไป", 13, 0, "3001", None),
]


def make_db(path: Path, messages=MESSAGES) -> sqlite3.Connection:
    db = sqlite3.connect(path)
    db.executescript(SCHEMA)
    for i, (chat, sender, text, off, ct, sid, meta) in enumerate(messages, 1):
        lat, lon = (13.74560, 100.53410) if ct == 15 else (None, None)
        db.execute("INSERT INTO ZMESSAGE VALUES(?,?,?,?,?,?,?,?,?,?)", (i, chat, sender, text, str(T + off * 1000), ct, sid, meta, lat, lon))
    db.commit()
    return db


def jpeg(size=(80, 60)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (20, 120, 200)).save(buf, "JPEG")
    return buf.getvalue()


def test_parse_line_full(tmp_path):
    make_db(tmp_path / "Line.sqlite").close()
    items = parsers.parse_line_full(tmp_path / "Line.sqlite")
    by_body = {m.body: (m, sid, ct) for m, sid, ct in items}
    assert len(items) == len(MESSAGES) - 1  # the empty chat event is dropped
    m, sid, ct = by_body["สวัสดีครับ"]
    assert m.thread == "พี่ต้น" and m.sender == "พี่ต้น" and m.direction == "in" and m.timestamp == T + 1000
    assert by_body["ว่าไง"][0].sender == "ฉัน" and by_body["ว่าไง"][0].direction == "out"
    assert by_body["[รูปภาพ]"][1:] == ("1001", parsers.LINE_IMAGE)
    assert "[วิดีโอ] 1:05" in by_body
    assert "[ข้อความเสียง] 0:15" in by_body  # binary plist metadata
    assert "[โทรผ่าน LINE 2:34]" in by_body
    assert "[สติกเกอร์] ขอบคุณ" in by_body
    assert "[ไฟล์] สัญญา.pdf" in by_body  # keyed archive metadata
    assert "[ตำแหน่ง] ร้านกาแฟ (13.74560, 100.53410)" in by_body
    assert by_body["ประชุมกี่โมง"][0].thread == "ทีมขาย"  # group name
    assert by_body["อยู่ไหน"][0].thread == "พี่ต้น, สมศรี"  # room named after its members
    assert parsers.parse_line(tmp_path / "Line.sqlite")[0].app == "LINE"


def test_parse_line_tolerates_other_schemas(tmp_path):
    path = tmp_path / "old.sqlite"
    db = sqlite3.connect(path)
    db.executescript("CREATE TABLE ZMESSAGE(ZCHAT INTEGER, ZSENDER INTEGER, ZTEXT TEXT, ZTIMESTAMP INTEGER); INSERT INTO ZMESSAGE VALUES(1, NULL, 'hi', 1700000000);")
    db.commit()
    db.close()
    (msg, sid, ct), = parsers.parse_line_full(path)
    assert msg.body == "hi" and msg.thread == "LINE" and msg.timestamp == 1_700_000_000_000 and sid == ""
    empty = tmp_path / "empty.sqlite"
    sqlite3.connect(empty).close()
    assert parsers.parse_line_full(empty) == []


class FakeBackup:
    def __init__(self, root: Path) -> None:
        self.root = root
        root.mkdir()
        self.db = sqlite3.connect(root / "Manifest.db")
        self.db.execute("CREATE TABLE Files(fileID TEXT PRIMARY KEY, domain TEXT, relativePath TEXT, flags INTEGER, file BLOB)")

    def add(self, domain: str, rel: str, data: bytes) -> None:
        fid = hashlib.sha1(f"{domain}-{rel}".encode()).hexdigest()
        (self.root / fid[:2]).mkdir(exist_ok=True)
        (self.root / fid[:2] / fid).write_bytes(data)
        meta = plistlib.dumps({"$objects": ["$null", {"Size": len(data), "LastModified": 1700000000}]}, fmt=plistlib.FMT_BINARY)
        self.db.execute("INSERT INTO Files VALUES(?,?,?,?,?)", (fid, domain, rel, 1, meta))

    def close(self) -> None:
        self.db.commit()
        self.db.close()


def test_line_from_backup_with_wal_and_attachments(tmp_path):
    # A live database whose newest message exists only in the write-ahead log.
    src = tmp_path / "src"
    src.mkdir()
    db = make_db(src / "Line.sqlite")
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA wal_autocheckpoint=0")
    db.execute("INSERT INTO ZMESSAGE VALUES(99, 1, 1, 'ข้อความล่าสุดใน WAL', ?, 0, '9999', NULL, NULL, NULL)", (str(T + 99_000),))
    db.commit()
    fb = FakeBackup(tmp_path / "backup")
    for suffix in ("", "-wal", "-shm"):
        fb.add(DOMAIN, DB_REL + suffix, (src / f"Line.sqlite{suffix}").read_bytes())
    db.close()
    fb.add(DOMAIN, f"{STORE}/Message Attachments/u1/1001", jpeg())
    fb.add(DOMAIN, f"{STORE}/Message Attachments/u1/1001.thumb", jpeg((20, 15)))
    fb.add(DOMAIN, f"{STORE}/Message Attachments/u1/1002.thumb", jpeg((20, 15)))  # video: preview only
    fb.add(DOMAIN, f"{STORE}/Message Attachments/u1/1003", b"\x00\x00\x00\x20ftypM4A \x00\x00\x00\x00" + b"\x00" * 64)
    fb.close()

    case = CaseStore(tmp_path / "cases").create_case({"case_no": "L1", "title": "LINE"})
    ext = case.create_extraction({"platform": "ios", "serial": "TEST"}, "itunes-backup")
    ctx = ExtractionContext(ext, EventBus(), "job", ["chats", "photos"])
    reader = BackupReader(tmp_path / "backup", ext.raw_dir / "decoded")
    extractor = IOSExtractor("TEST")
    extractor._extra_photos = []
    msgs = extractor._chats(ctx, reader)
    by_body = {m.body: m for m in msgs}
    assert "ข้อความล่าสุดใน WAL" in by_body and msgs[0].body == "ข้อความล่าสุดใน WAL"

    photo_msg = by_body["[รูปภาพ]"]
    assert photo_msg.attachment.startswith("media/line/") and photo_msg.attachment.endswith("1001.jpg")
    assert (ext.dir / photo_msg.attachment).is_file()
    assert by_body["[วิดีโอ] 1:05"].attachment.endswith("1002_thumb.jpg")
    assert by_body["[ข้อความเสียง] 0:15"].attachment.endswith("1003.m4a")
    assert by_body["[ไฟล์] สัญญา.pdf"].attachment == ""  # never downloaded on the phone

    photos = extractor._photos(ctx, reader)  # no camera roll here: only the LINE picture
    assert len(photos) == 1 and photos[0].album == "LINE: พี่ต้น" and photos[0].thumb and len(photos[0].sha256) == 64
    assert photos[0].taken == T + 3000
    sources = {f["source"] for f in case.files(ext.id)}
    assert f"{DOMAIN}/{STORE}/Message Attachments/u1/1003" in sources
    audit = " ".join(e["detail"] for e in case.audit_entries(ext.id) if e["action"] == "ios.line")
    assert "media on phone 3/4" in audit
    reader.close()
    shutil.rmtree(src)
