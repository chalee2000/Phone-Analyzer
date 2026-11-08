"""End-to-end: demo device → case database → Excel / PDF / Word."""

import json
import time
import urllib.request

import pytest
from docx import Document
from openpyxl import load_workbook

from spni.api import Api
from spni.events import EventBus
from spni.media_server import MediaServer, resolve_media


def run_demo(api: Api, device: str) -> dict:
    assert api.connect(device)["ok"]
    assert api.create_case({"case_no": "99/2569", "title": "ทดสอบระบบ", "investigator": "ผู้ทดสอบ"})["ok"]
    started = api.start_extraction({})
    assert started["ok"], started
    for _ in range(300):
        if not api.state()["data"]["running"]:
            break
        time.sleep(0.05)
    return api.state()["data"]


@pytest.mark.parametrize("device,expected", [
    ("demo:android", {"calls": 222, "sms": 633, "contacts": 53, "wifi": 13, "sim": 5}),
    ("demo:ios", {"calls": 318, "chats": 555, "web": 140, "notes": 5}),
])
def test_demo_extraction_and_exports(cases_dir, device, expected):
    bus = EventBus()
    events = []
    bus.subscribe(lambda n, p: events.append(n))
    api = Api(bus, cases_dir, demo=True)
    state = run_demo(api, device)
    for kind, n in expected.items():
        assert state["counts"][kind] == n
    assert state["extraction"]["status"] == "completed"
    assert "extraction.done" in events and "extraction.step" in events

    ext_dir = cases_dir / state["case"]["id"] / "extractions" / state["extraction"]["id"]
    manifest = json.loads((ext_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["files"] and all(len(f["sha256"]) == 64 for f in manifest["files"])

    xlsx = api.export_report("excel", {"lang": "th"})["data"]["path"]
    wb = load_workbook(xlsx)
    assert wb.sheetnames[0] == "สรุป" and "ประวัติการโทร" in wb.sheetnames
    assert wb["ประวัติการโทร"].max_row == expected.get("calls", 0) + 1

    pdf = api.export_report("pdf", {"lang": "th"})["data"]["path"]
    with open(pdf, "rb") as fh:
        assert fh.read(5) == b"%PDF-"

    docx = api.export_report("word", {"lang": "en"})["data"]["path"]
    assert len(Document(docx).inline_shapes) == state["counts"]["photos"]

    audit = api.audit_log()["data"]
    assert any(a["action"] == "export.pdf" for a in audit)


def test_device_number_and_history(cases_dir):
    api = Api(EventBus(), cases_dir, demo=True)
    run_demo(api, "demo:android")
    assert api.set_device_number("0812345678")["ok"]
    assert api.state()["data"]["extraction"]["device"]["phone_number"] == "0812345678"
    history = api.device_history()["data"]
    assert history[0]["serial"] == "9b01005930533036340014e659ae3c" and history[0]["case_no"] == "99/2569"
    reopened = Api(EventBus(), cases_dir)
    info = reopened.open_extraction(history[0]["case_id"], history[0]["id"])
    assert info["ok"] and len(reopened.get_records("calls")["data"]) == 222


def test_api_errors_are_reported_not_raised(cases_dir):
    api = Api(EventBus(), cases_dir)
    assert api.start_extraction({}) == {"ok": False, "error": "no_device", "message": "no_device"}
    assert api.get_records("nope")["error"] == "bad_kind"
    assert api.create_case({})["error"] == "case_name_required"


def test_media_server_blocks_traversal(tmp_path):
    root = tmp_path / "cases"
    (root / "c1").mkdir(parents=True)
    (root / "c1" / "a.txt").write_text("ok")
    (tmp_path / "secret.txt").write_text("no")
    assert resolve_media(root, "c1/a.txt")
    assert resolve_media(root, "../secret.txt") is None
    assert resolve_media(root, "c1/%2e%2e/%2e%2e/secret.txt") is None

    server = MediaServer(lambda: root)
    server.start()
    try:
        with urllib.request.urlopen(f"{server.base_url}/c1/a.txt") as resp:
            assert resp.read() == b"ok"
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(f"http://127.0.0.1:{server.port}/wrong-token/c1/a.txt")
    finally:
        server.stop()
