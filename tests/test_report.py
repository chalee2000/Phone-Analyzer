"""Forensic report: every format from a two-device demo case + CDR."""

import hashlib
import json
import re
import time
import zipfile
from pathlib import Path

import pytest
from docx import Document
from openpyxl import load_workbook

from spni.api import Api
from spni.events import EventBus
from spni.export import labels


def extract(api: Api, device: str) -> None:
    assert api.connect(device)["ok"]
    assert api.start_extraction({})["ok"]
    for _ in range(400):
        if not api.state()["data"]["running"]:
            return
        time.sleep(0.05)
    raise AssertionError("extraction did not finish")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def api(tmp_path_factory):
    api = Api(EventBus(), tmp_path_factory.mktemp("cases"), demo=True)
    assert api.create_case({"case_no": "99/2569", "title": "รายงานทดสอบ"})["ok"]
    extract(api, "demo:android")
    extract(api, "demo:ios")
    assert api.import_demo_cdr()["ok"]
    events = api.timeline({})["data"]["events"]
    assert api.timeline_bookmark(events[10]["id"], True, "เหตุการณ์สำคัญ")["ok"]
    return api


SPEC = {
    "file_name": "รายงานทดสอบ",
    "formats": ["pdf", "docx", "xlsx", "html", "zip"],
    "classification": "ลับ",
    "max_rows": 200,
    "case": {"examiner": "ร.ต.อ. ทดสอบ ระบบ", "evidence_no": "ขก.1/2569", "crime_type": "ยาเสพติด", "organization": "ตำรวจภูธร"},
}


@pytest.fixture(scope="module")
def result(api):
    progress = []
    api._bus.subscribe(lambda name, payload: name == "report.progress" and progress.append(payload["step"]))
    res = api.generate_report(SPEC)
    assert res["ok"], res
    res["data"]["progress"] = progress
    return res["data"]


def files(result):
    return {f["format"]: Path(f["path"]) for f in result["files"]}


def test_defaults(api):
    d = api.report_defaults()["data"]
    assert len(d["devices"]) == 3  # android, iOS and the CDR
    assert d["case"]["case_no"] == "99/2569"
    assert d["bookmarks"] == 1
    assert "evidence_no" in d["case"]


def test_all_formats_written_and_hashed(api, result):
    f = files(result)
    assert set(f) == {"pdf", "docx", "xlsx", "html", "zip"}
    for r in result["files"]:
        p = Path(r["path"])
        assert p.is_file() and p.stat().st_size == r["size"]
        assert sha(p) == r["sha256"]
        side = Path(r["path"] + ".sha256").read_text(encoding="utf-8")
        assert side.split()[0] == r["sha256"]
    assert {"collect", "pdf", "package", "done"} <= set(result["progress"])
    assert labels.YEAR_OFFSET == 0  # restored after a Buddhist-era report


def test_case_details_saved(api, result):
    meta = api._case.meta()
    assert meta["examiner"] == "ร.ต.อ. ทดสอบ ระบบ"
    assert meta["evidence_no"] == "ขก.1/2569"


def test_pdf(result):
    data = files(result)["pdf"].read_bytes()
    assert data.startswith(b"%PDF") and b"/Encrypt" not in data
    assert b"/Outlines" in data  # bookmarks for each chapter


def test_docx(result):
    doc = Document(str(files(result)["docx"]))
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "รายงานผลการตรวจพิสูจน์ข้อมูลโทรศัพท์มือถือ" in text
    heads = [p.text for p in doc.paragraphs if p.style.name.startswith("Heading")]
    assert any("อุปกรณ์" in h for h in heads)
    assert any("ค่าแฮช" in h or "SHA-256" in h for h in heads)
    assert "ลับ" in doc.sections[0].header.paragraphs[0].text


def test_xlsx(result):
    wb = load_workbook(files(result)["xlsx"], read_only=True)
    names = wb.sheetnames
    assert names[0] == "สรุป"
    assert sum(n.startswith("อุปกรณ์") for n in names) == 3
    assert "SHA-256" in names and "Audit" in names
    assert any("ผู้ติดต่อบ่อย" in n for n in names)


def test_html(result):
    html = files(result)["html"].read_text(encoding="utf-8")
    assert html.count("<table") > 10
    assert "ผู้ตรวจพิสูจน์" in html and "ขก.1/2569" in html
    assert "class='cls'" in html  # classification banner
    assert re.search(r"\d\d/\d\d/25\d\d", html)  # Buddhist-era dates


def test_zip_package(result):
    z = zipfile.ZipFile(files(result)["zip"])
    names = set(z.namelist())
    assert {"manifest.json", "SHA256SUMS.txt", "รายงานทดสอบ.pdf", "รายงานทดสอบ.xlsx", "รายงานทดสอบ.html"} <= names
    for line in z.read("SHA256SUMS.txt").decode().splitlines():
        digest, name = line.split("  ", 1)
        assert hashlib.sha256(z.read(name)).hexdigest() == digest
    manifest = json.loads(z.read("manifest.json"))
    assert manifest["report_id"] == result["report_id"]
    assert len(manifest["devices"]) == 3


def test_audit_has_report_hashes(api, result):
    logged = " ".join(e["detail"] for e in api._case.audit_entries() if e["action"].startswith("report."))
    for r in result["files"]:
        assert r["sha256"] in logged


def test_password_english_and_filters(api, tmp_path):
    spec = {
        "file_name": "secured",
        "formats": ["pdf", "html"],
        "out_dir": str(tmp_path / "out"),
        "pdf_password": "s3cret",
        "lang": "en",
        "buddhist_year": True,  # ignored for English
        "kinds": ["calls"],
        "sections": ["devices", "summary", "records"],
        "hash_file": False,
    }
    res = api.generate_report(spec)
    assert res["ok"], res
    f = files(res["data"])
    assert f["pdf"].parent == tmp_path / "out"
    assert b"/Encrypt" in f["pdf"].read_bytes()
    assert not Path(str(f["pdf"]) + ".sha256").exists()
    html = f["html"].read_text(encoding="utf-8")
    assert "Mobile Device Forensic Report" in html and "Call log" in html
    assert not re.search(r"\d\d/\d\d/25\d\d", html)  # English reports always use AD years
    assert re.search(r"\d\d/\d\d/20\d\d", html)
    assert "id='hashes'" not in html and "id='audit'" not in html  # sections left out
    records = html.split("id='records'", 1)[1]
    assert "SMS" not in records  # only the call log was chosen
    # The produced files may be opened/revealed even outside the cases root.
    assert api._allowed(str(f["pdf"])) == f["pdf"].resolve()


def test_busy_and_no_case(tmp_path):
    api = Api(EventBus(), tmp_path / "c", demo=True)
    assert api.generate_report({})["error"] == "no_case"
    assert api.report_defaults()["error"] == "no_case"
