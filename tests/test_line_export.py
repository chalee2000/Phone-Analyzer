"""LINE "Export chat history" text files: formats, owner, import, Android pickup."""

from datetime import datetime

import pytest

from spni import line_export as le
from spni.android.extract import AndroidExtractor
from spni.case.store import CaseStore

from test_android import FakeDevice, make_ctx  # tests/ is on sys.path (pytest rootdir)


def ms(*args) -> int:
    return int(datetime(*args).timestamp() * 1000)


THAI_ANDROID = """﻿[LINE] ประวัติการแชทกับ สมชาย ใจดี
วันที่บันทึก: 11/11/2569 13:40

พ., 05/11/2569
13:01\tสมชาย ใจดี\tสวัสดีครับ
13:02\tตำรวจ ทดสอบ\t"บรรทัดแรก
บรรทัดสอง"
13:05\tสมชาย ใจดี\t[รูป]
13:06\tสมชาย ใจดี\t☎ ระยะเวลาการโทร 2:35
13:07\tตำรวจ ทดสอบ\t☎ สายที่ไม่ได้รับ
13:08\tสมชาย ใจดี\t[สติกเกอร์]

พฤ., 06/11/2569
09:00\tสมชาย ใจดี\tยกเลิกข้อความ
"""

ENGLISH_GROUP = """[LINE] Chat history in Delivery team
Saved on: 2026/11/11 13:40

Mon, 11/02/2026
9:05AM\tตำรวจ ทดสอบ\tOn my way
12:30PM\tBoy\t[Photo]
12:31PM\tBoy\t[Voice message]
12:40PM\tBoy left the group.

Tue, 11/03/2026
11:59PM\tFai\t"quoted on one line"
"""

IOS_DATED = """[LINE] Chat with Fai
2026.11.04 13:00\tFai\tกินข้าวยัง
2026.11.04 13:05\tตำรวจ ทดสอบ\tยังเลย
"""


def test_thai_android_export():
    c = le.parse_text("[LINE] แชทกับ สมชาย ใจดี.txt", THAI_ANDROID)
    assert c.title == "สมชาย ใจดี" and not c.group and c.order == "dmy"
    bodies = [m["body"] for m in c.messages]
    assert bodies == ["สวัสดีครับ", "บรรทัดแรก\nบรรทัดสอง", "[รูปภาพ]", "[โทรผ่าน LINE 2:35]",
                      "[สายที่ไม่ได้รับผ่าน LINE]", "[สติกเกอร์]", "[ยกเลิกการส่งข้อความ]"]
    assert c.messages[0]["ts"] == ms(2026, 11, 5, 13, 1)  # 2569 BE
    assert c.messages[-1]["ts"] == ms(2026, 11, 6, 9, 0)


def test_english_group_export_with_am_pm_and_month_first_dates():
    c = le.parse_text("x.txt", ENGLISH_GROUP)
    assert c.title == "Delivery team" and c.group
    assert c.order == "mdy"  # 11/02 then 11/03 only moves forward month-first
    assert c.messages[0]["ts"] == ms(2026, 11, 2, 9, 5)
    assert c.messages[1]["ts"] == ms(2026, 11, 2, 12, 30) and c.messages[1]["body"] == "[รูปภาพ]"
    assert c.messages[2]["body"] == "[ข้อความเสียง]"
    assert c.messages[3]["sender"] == "" and c.messages[3]["body"] == "Boy left the group."
    assert c.messages[4]["ts"] == ms(2026, 11, 3, 23, 59) and c.messages[4]["body"] == "quoted on one line"


def test_date_on_every_line_and_day_first_evidence():
    c = le.parse_text("[LINE] Chat with Fai.txt", IOS_DATED)
    assert c.title == "Fai" and [m["ts"] for m in c.messages] == [ms(2026, 11, 4, 13, 0), ms(2026, 11, 4, 13, 5)]
    day_first = le.parse_text("x.txt", "[LINE] Chat with A\n\n13/11/2026\n10:00\tA\thi\n")
    assert day_first.order == "dmy" and day_first.messages[0]["ts"] == ms(2026, 11, 13, 10, 0)


def test_owner_and_messages():
    chats = [le.parse_text("a.txt", THAI_ANDROID), le.parse_text("b.txt", ENGLISH_GROUP), le.parse_text("c.txt", IOS_DATED)]
    owner, candidates = le.guess_owner(chats)
    assert owner == "ตำรวจ ทดสอบ" and candidates[0]["name"] == owner
    msgs = le.to_messages(chats, owner)
    assert {m.app for m in msgs} == {"LINE"}
    mine = [m for m in msgs if m.direction == "out"]
    assert mine and all(m.sender == "ฉัน" for m in mine)
    assert any(m.body == "[ห้องสนทนา] Boy left the group." for m in msgs)
    assert le.is_line_export(THAI_ANDROID.encode("utf-8")) and not le.is_line_export(b"hello")
    assert le.decode(THAI_ANDROID.encode("utf-16")) .startswith("﻿[LINE]") or le.decode(THAI_ANDROID.encode("utf-16")).startswith("[LINE]")


def test_import_from_computer(tmp_path):
    files = []
    for name, data in le.demo_files():
        (tmp_path / name).write_bytes(data)
        files.append(str(tmp_path / name))
    (tmp_path / "notes.txt").write_text("not a LINE export", encoding="utf-8")
    pv = le.preview(files + [str(tmp_path / "notes.txt")])
    assert pv["threads"] == 2 and pv["owner"] == "สมชาย ใจดี" and pv["skipped"] == ["notes.txt"]
    case = CaseStore(tmp_path / "cases").create_case({"case_no": "L/1"})
    res = le.import_into(case, files, pv["owner"])
    chats = case.records(res["extraction_id"], "chats")
    assert res["counts"]["chats"] == len(chats) == pv["messages"]
    info = case.extraction_info(res["extraction_id"])
    assert info["method"] == "line-export" and info["unavailable"]["photos"]["reason"] == "not_supported"
    assert any("sha256=" in e["detail"] for e in case.audit_entries(res["extraction_id"]) if e["action"] == "line.export.source")
    with pytest.raises(ValueError, match="line_no_chats"):
        le.preview([str(tmp_path / "notes.txt")])


def test_android_extraction_picks_up_exports(tmp_path):
    export = THAI_ANDROID.encode("utf-8")
    renamed = ENGLISH_GROUP.encode("utf-8")
    dev = FakeDevice(
        files={
            "/sdcard/Download/[LINE] แชทกับ สมชาย ใจดี.txt": (len(export), 1762790400),
            "/sdcard/Documents/backup-chat.txt": (len(renamed), 1762790400),  # renamed: found by its first line
            "/sdcard/Download/shopping.txt": (12, 1762790400),
            "/sdcard/DCIM/Camera/IMG_1.jpg": (1000, 1762790400),
        },
        contents={
            "/sdcard/Download/[LINE] แชทกับ สมชาย ใจดี.txt": export,
            "/sdcard/Documents/backup-chat.txt": renamed,
            "/sdcard/Download/shopping.txt": b"milk, eggs",
        },
    )
    ctx, case, _ = make_ctx(tmp_path, ["chats"])
    AndroidExtractor(dev).run(ctx)
    chats = case.records(ctx.extraction.id, "chats")
    assert {c["thread"] for c in chats} == {"สมชาย ใจดี", "Delivery team"}
    assert any(c["direction"] == "out" and c["sender"] == "ฉัน" for c in chats)
    sources = {f["source"] for f in case.files(ctx.extraction.id)}
    assert "/sdcard/Download/[LINE] แชทกับ สมชาย ใจดี.txt" in sources and "/sdcard/Download/shopping.txt" not in sources
