"""Messenger import from Facebook data exports (DYI JSON + secure storage)."""

import base64
import io
import json
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from spni import messenger
from spni.api import Api
from spni.case.store import CaseStore
from spni.events import EventBus
from spni.util import sha256_file

ROOT = "your_facebook_activity/messages"
T0 = 1_760_000_000_000  # ms


def garble(obj):
    """Facebook's escaping: every UTF-8 byte becomes one code point."""
    if isinstance(obj, str):
        return obj.encode("utf-8").decode("latin-1")
    if isinstance(obj, list):
        return [garble(x) for x in obj]
    if isinstance(obj, dict):
        return {k: garble(v) for k, v in obj.items()}
    return obj


def jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), (200, 80, 40)).save(buf, "JPEG")
    return buf.getvalue()


def thread(title, members, msgs, path):
    return json.dumps(garble({"participants": [{"name": n} for n in members], "messages": msgs, "title": title, "thread_path": path}))


def write_zip(path: Path, files: dict[str, bytes | str]) -> str:
    with zipfile.ZipFile(path, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return str(path)


@pytest.fixture
def export(tmp_path):
    owner, somchai = "เจ้าของ บัญชี", "สมชาย ใจดี"
    one_to_one = [
        {"sender_name": somchai, "timestamp_ms": T0 + 9000, "content": "ของมาพรุ่งนี้", "reactions": [{"reaction": "👍", "actor": owner}]},
        {"sender_name": owner, "timestamp_ms": T0 + 8000, "content": "โอเค"},
        {"sender_name": somchai, "timestamp_ms": T0 + 7000, "photos": [{"uri": f"{ROOT}/inbox/somchai_100/photos/p1.jpg"}]},
        {"sender_name": owner, "timestamp_ms": T0 + 6000, "is_unsent": True},
        {"sender_name": somchai, "timestamp_ms": T0 + 5000, "call_duration": 154, "content": "The call ended."},
        {"sender_name": somchai, "timestamp_ms": T0 + 4000, "call_duration": 0, "content": "missed"},
    ]
    older = [
        {"sender_name": somchai, "timestamp_ms": T0 + 4000, "call_duration": 0, "content": "missed"},  # duplicate across parts
        {"sender_name": owner, "timestamp_ms": T0 + 3000, "sticker": {"uri": f"{ROOT}/stickers_used/s1.png"}},
        {"sender_name": somchai, "timestamp_ms": T0 + 2000, "content": "ดูนี่", "share": {"link": "https://example.org/x"}},
        {"sender_name": somchai, "timestamp_ms": T0 + 1000, "files": [{"uri": f"{ROOT}/inbox/somchai_100/files/doc.pdf"}]},
    ]
    group = [
        {"sender_name": "ฝ้าย", "timestamp_ms": T0 + 500, "content": "เจอกันสองทุ่ม"},
        {"sender_name": owner, "timestamp_ms": T0 + 400, "content": "รับทราบ"},
    ]
    request = [{"sender_name": "ร้านค้า", "timestamp_ms": T0 + 300, "content": "สนใจไหมครับ"}]
    part1 = write_zip(tmp_path / "facebook-part1.zip", {
        f"{ROOT}/inbox/somchai_100/message_1.json": thread(somchai, [somchai, owner], one_to_one, "inbox/somchai_100"),
        f"{ROOT}/inbox/somchai_100/photos/p1.jpg": jpeg(),
        f"{ROOT}/inbox/team_200/message_1.json": thread("ทีมงาน", [owner, "ฝ้าย", somchai], group, "inbox/team_200"),
        f"{ROOT}/message_requests/shop_300/message_1.json": thread("ร้านค้า", ["ร้านค้า", owner], request, "message_requests/shop_300"),
        "your_facebook_activity/posts/your_posts_1.json": json.dumps([{"title": "not a chat"}]),
        "__MACOSX/._junk.json": "{}",
    })
    part2 = write_zip(tmp_path / "facebook-part2.zip", {
        f"{ROOT}/inbox/somchai_100/message_2.json": thread(somchai, [somchai, owner], older, "inbox/somchai_100"),
        f"{ROOT}/stickers_used/s1.png": jpeg(),
        f"{ROOT}/inbox/somchai_100/files/doc.pdf": b"%PDF-1.4 demo",
    })
    e2ee = tmp_path / "ฝ้าย.json"
    e2ee.write_text(json.dumps({
        "participants": [owner, "ฝ้าย"], "threadName": "ฝ้าย",
        "messages": [
            {"senderName": "ฝ้าย", "timestamp": (T0 + 200) // 1000, "text": "ลบแชตด้วย", "isUnsent": False, "media": [], "reactions": []},
            {"senderName": owner, "timestamp": T0 + 100, "text": "", "media": [{"uri": "media/v1.mp4"}]},
        ],
    }, ensure_ascii=False), encoding="utf-8")
    return {"owner": owner, "paths": [part1, part2, str(e2ee)], "tmp": tmp_path}


def test_fix_text():
    assert messenger.fix_text(garble("สวัสดี ครับ")) == "สวัสดี ครับ"
    assert messenger.fix_text("สวัสดี") == "สวัสดี"  # already correct
    assert messenger.fix_text("hello") == "hello"
    assert messenger.fix_text(None) == ""


def test_preview(export):
    pv = messenger.preview(export["paths"])
    assert pv["owner"] == export["owner"]  # no profile file: the person in every thread
    assert pv["candidates"][0]["name"] == export["owner"]
    assert pv["threads"] == 4
    assert pv["e2ee_threads"] == 1
    assert pv["requests"] == 1
    assert pv["messages"] == 14  # 15 messages, one duplicated across the two parts
    assert [s["name"] for s in pv["sources"]] == ["facebook-part1.zip", "facebook-part2.zip", "ฝ้าย.json"]


@pytest.fixture
def imported(export):
    store = CaseStore(export["tmp"] / "cases")
    case = store.create_case({"case_no": "5/2569", "title": "ทดสอบ Messenger"})
    res = messenger.import_into(case, export["paths"])
    return case, res, export


def test_import_chats(imported):
    case, res, export = imported
    chats = case.records(res["extraction_id"], "chats")
    assert res["counts"] == {"chats": 14, "photos": 1}
    assert all(c["app"] == "Messenger" for c in chats)
    assert [c["timestamp"] for c in chats] == sorted((c["timestamp"] for c in chats), reverse=True)
    by_body = {c["body"]: c for c in chats}
    assert by_body["โอเค"]["sender"] == "ฉัน" and by_body["โอเค"]["direction"] == "out"
    first = by_body[f"ของมาพรุ่งนี้ · 👍 {export['owner']}"]
    assert first["sender"] == "สมชาย ใจดี" and first["direction"] == "in" and first["thread"] == "สมชาย ใจดี"
    assert "[ยกเลิกการส่งข้อความ]" in by_body
    assert "[โทรผ่าน Messenger 2:34]" in by_body
    assert "[สายที่ไม่ได้รับผ่าน Messenger]" in by_body
    assert "ดูนี่ [ลิงก์] https://example.org/x" in by_body
    assert "[ไฟล์] doc.pdf" in by_body
    assert by_body["[สติกเกอร์]"]["attachment"].endswith(".png")
    threads = {c["thread"] for c in chats}
    assert {"สมชาย ใจดี", "ทีมงาน", "ร้านค้า (คำขอข้อความ)", "ฝ้าย"} == threads
    e2ee = by_body["ลบแชตด้วย"]
    assert e2ee["timestamp"] == (T0 + 200) // 1000 * 1000  # seconds were scaled to ms
    assert by_body["[วิดีโอ]"]["sender"] == "ฉัน"


def test_import_media_hashes_and_audit(imported):
    case, res, export = imported
    ext_id = res["extraction_id"]
    ext_dir = case.path / "extractions" / ext_id
    photos = case.records(ext_id, "photos")
    assert len(photos) == 1 and photos[0]["album"] == "Messenger: สมชาย ใจดี"
    assert (ext_dir / photos[0]["thumb"]).is_file() and len(photos[0]["sha256"]) == 64
    assert photos[0]["taken"] == T0 + 7000
    chats = case.records(ext_id, "chats")
    photo_msg = next(c for c in chats if c["body"] == "[รูปภาพ]")
    assert (ext_dir / photo_msg["attachment"]).is_file()
    files = case.files(ext_id)
    sources = {f["source"] for f in files}
    assert any(s.startswith("facebook-part1.zip:") and s.endswith("message_1.json") for s in sources)
    assert any(s.endswith("doc.pdf") for s in sources)
    audit = " ".join(e["detail"] for e in case.audit_entries(ext_id))
    for p in export["paths"]:
        assert sha256_file(p) in audit
    info = case.extraction_info(ext_id)
    assert info["method"] == "fb-export"
    assert info["unavailable"]["calls"]["reason"] == "not_supported"
    assert res["missing_media"] == 1  # the E2EE video file was not part of the download


def test_html_and_empty_exports(tmp_path):
    html = write_zip(tmp_path / "html.zip", {f"{ROOT}/inbox/a_1/message_1.html": "<html></html>"})
    with pytest.raises(ValueError, match="fb_html_format"):
        messenger.preview([html])
    empty = write_zip(tmp_path / "empty.zip", {"readme.txt": "nothing"})
    with pytest.raises(ValueError, match="fb_no_messages"):
        messenger.preview([empty])


def test_api_flow_and_analysis(tmp_path):
    api = Api(EventBus(), tmp_path / "cases", demo=True)
    files = messenger.demo_export()
    paths = [api.messenger_upload(name, base64.b64encode(data).decode())["data"] for name, data in files]
    pv = api.messenger_preview(paths)["data"]
    assert pv["owner"] == messenger.DEMO_OWNER and pv["e2ee_threads"] == 1
    res = api.messenger_import(paths, pv["owner"])
    assert res["ok"], res
    data = res["data"]
    assert data["counts"]["chats"] == pv["messages"] and data["counts"]["photos"] > 5
    assert api.messenger_preview(["/no/such/file.zip"])["error"] == "not_found"
    # Messenger threads flow into the analysis views and the report.
    g = api.network_graph({})["data"]
    assert any(n["id"].startswith("chat:Messenger:") for n in g["nodes"])
    events = api.timeline({"date_from": None, "date_to": None})["data"]["events"]
    assert any((e.get("extra") or {}).get("app") == "Messenger" for e in events)
    rep = api.generate_report({"file_name": "ms", "formats": ["html"], "sections": ["devices", "summary", "records"]})["data"]
    html = Path(rep["files"][0]["path"]).read_text(encoding="utf-8")
    assert "Messenger · " + messenger.DEMO_OWNER in html and "ทีมขนของ" in html
    # The one-click demo import creates its own source too.
    assert api.import_demo_messenger()["ok"]
    assert len(api.case_devices()["data"]) == 2
