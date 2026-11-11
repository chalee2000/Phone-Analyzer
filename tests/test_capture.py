"""Chat screen capture: screen parsing, stitching, dates, the capture loop and the API."""

import time
from datetime import date, datetime

from spni.android.capture import Capture, Item, Page, page_from_dump, parse_date_label, parse_dump, stitch, to_messages
from spni.android.capture_demo import DemoChatPhone
from spni.api import Api
from spni.case.store import CaseStore
from spni.events import EventBus
from spni.extract import ExtractionContext

DUMP = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?><hierarchy rotation="0">
<node index="0" text="" class="android.widget.FrameLayout" package="jp.naver.line.android" content-desc="" bounds="[0,0][1080,2400]">
  <node text="พี่ต้น" class="android.widget.TextView" package="jp.naver.line.android" content-desc="" bounds="[180,90][700,160]" />
  <node text="วันนี้" class="android.widget.TextView" package="jp.naver.line.android" content-desc="" bounds="[460,400][620,460]" />
  <node text="ถึงไหนแล้ว" class="android.widget.TextView" package="jp.naver.line.android" content-desc="" bounds="[160,500][520,580]" />
  <node text="13:01" class="android.widget.TextView" package="jp.naver.line.android" content-desc="" bounds="[530,550][600,580]" />
  <node text="" class="android.widget.ImageView" package="jp.naver.line.android" content-desc="" bounds="[600,640][1040,980]" />
  <node text="อ่านแล้ว" class="android.widget.TextView" package="jp.naver.line.android" content-desc="" bounds="[480,930][590,960]" />
  <node text="13:05" class="android.widget.TextView" package="jp.naver.line.android" content-desc="" bounds="[480,960][590,990]" />
  <node text="" class="android.widget.ImageView" package="jp.naver.line.android" content-desc="" bounds="[40,500][120,580]" />
  <node text="" class="android.widget.EditText" package="jp.naver.line.android" content-desc="" bounds="[40,2200][900,2320]" />
</node></hierarchy>"""


def test_screen_is_classified():
    nodes, w, h = parse_dump(DUMP)
    assert (w, h) == (1080, 2400)
    page = page_from_dump(nodes, w, h)
    assert page.title == "พี่ต้น" and page.package == "jp.naver.line.android"
    kinds = [(i.kind, i.text, i.side) for i in page.items]
    assert kinds == [("date", "วันนี้", "center"), ("msg", "ถึงไหนแล้ว", "in"), ("time", "13:01", "in"),
                     ("image", "", "out"), ("time", "13:05", "out")]  # read receipt, avatar and input box are left out


def test_stitch_removes_the_overlap_between_pages():
    def page(*texts):
        return Page("", "", [Item("msg", t, "in", (0, i * 10, 10, i * 10 + 5)) for i, t in enumerate(texts)], 100, 100)

    newest = page("c", "d", "e")
    older = page("a", "b", "c", "d")  # scrolled up: shares c and d
    oldest = page("a", "b")  # the top: nothing new
    assert [i.text for i in stitch([newest, older, oldest])] == ["a", "b", "c", "d", "e"]


def test_date_labels():
    today = date(2026, 11, 11)  # a Wednesday
    assert parse_date_label("วันนี้", today) == today
    assert parse_date_label("Yesterday", today) == date(2026, 11, 10)
    assert parse_date_label("พ. 5 พ.ย.", today) == date(2026, 11, 5)
    assert parse_date_label("Mon, 12/29", today) is not None
    assert parse_date_label("2025.12.31", today) == date(2025, 12, 31)
    assert parse_date_label("31/12/2568", today) == date(2025, 12, 31)
    assert parse_date_label("20 ธ.ค.", today) == date(2025, 12, 20)  # no year and in the future: last year
    assert parse_date_label("อ.", today) == date(2026, 11, 10)


def test_messages_get_the_time_shown_next_to_them():
    items = [Item("date", "วันนี้", "center", (0, 0, 0, 0)), Item("msg", "a", "in", (0, 0, 0, 0)), Item("msg", "b", "in", (0, 0, 0, 0)),
             Item("time", "1:05 PM", "in", (0, 0, 0, 0)), Item("image", "", "out", (0, 0, 0, 0), crop="media/x.png")]
    msgs = to_messages(items, "LINE", "พี่ต้น", date(2026, 11, 11))
    ts = int(datetime(2026, 11, 11, 13, 5).timestamp() * 1000)
    assert [(m.body, m.direction, m.timestamp) for m in msgs] == [("a", "in", ts), ("b", "in", ts), ("[รูปภาพ]", "out", None)]
    assert msgs[2].attachment == "media/x.png" and msgs[2].sender == "ฉัน"


def test_capture_rebuilds_the_whole_chat(tmp_path):
    case = CaseStore(tmp_path / "cases").create_case({"case_no": "C/1"})
    ext = case.create_extraction({"platform": "android", "serial": "x"}, "screen-capture")
    ctx = ExtractionContext(ext, EventBus(), "cap", ["chats", "photos"])
    phone = DemoChatPhone(title="เล้ง ตลาด", seed=7)
    pages = []
    res = Capture(phone, ctx, settle=0, progress=pages.append).run()
    assert res.reached_top and res.title == "เล้ง ตลาด" and res.app == "LINE" and res.text_pages == res.pages == len(pages)
    expected = [(b.get("text") or "[รูปภาพ]", b["side"], b["time"]["text"]) for b in phone.blocks if b["kind"] in ("msg", "image")]
    got = [(m.body, m.direction, datetime.fromtimestamp(m.timestamp / 1000).strftime("%H:%M")) for m in res.messages]
    assert got == expected
    assert len(res.pictures) == sum(1 for b in phone.blocks if b["kind"] == "image")
    assert all((ext.dir / m.attachment).is_file() for m in res.messages if m.body == "[รูปภาพ]")
    sources = {f["source"] for f in case.files(ext.id)}
    assert any(s.startswith("/sdcard/spni_capture.png (page 1)") for s in sources)


def test_capture_page_limit_and_api(tmp_path):
    bus = EventBus()
    events = []
    bus.subscribe(lambda n, p: events.append((n, p)))
    api = Api(bus, tmp_path / "cases", demo=True)
    assert api.capture_start({})["error"] == "capture_needs_android"
    api.connect("demo:android")
    ids = api.capture_start({"max_pages": 2})["data"]
    for _ in range(300):
        if not api.capture_state()["data"]:
            break
        time.sleep(0.05)
    done = [p for n, p in events if n == "capture.done"][-1]
    assert done["pages"] == 2 and not done["reached_top"] and done["messages"] > 0
    info = api._case.extraction_info(ids["extraction_id"])
    assert info["method"] == "screen-capture" and "บันทึกหน้าจอ" in info["device"]["market_name"]
    assert any(e["action"] == "adb.shell" and e["detail"].startswith("input swipe") for e in api._case.audit_entries(ids["extraction_id"]))
