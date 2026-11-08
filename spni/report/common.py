"""Text, labels and tables shared by every report renderer."""

from __future__ import annotations

from typing import Any

from ..export.labels import DEVICE_FIELDS, KIND_LABELS, UNAVAILABLE, columns, device_rows, fmt_dt, fmt_duration, fmt_iso, header, thai_date
from ..models import ALL_KINDS
from .dataset import Dataset, DeviceData

T = {
    "title": ("รายงานผลการตรวจพิสูจน์ข้อมูลโทรศัพท์มือถือ", "Mobile Device Forensic Report"),
    "case": ("ข้อมูลคดี", "Case information"),
    "devices": ("อุปกรณ์ที่ตรวจพิสูจน์", "Examined devices"),
    "summary": ("สรุปจำนวนข้อมูล", "Data summary"),
    "analysis": ("ผลการวิเคราะห์", "Analysis"),
    "network": ("ผังความเชื่อมโยงเครือข่าย", "Link chart"),
    "cross": ("ความเชื่อมโยงข้ามเครื่อง", "Cross-device links"),
    "top": ("ผู้ติดต่อบ่อยที่สุด", "Most frequent contacts"),
    "bookmarks": ("เหตุการณ์สำคัญที่ผู้ตรวจทำเครื่องหมาย", "Bookmarked events"),
    "records": ("รายละเอียดข้อมูลรายหมวด", "Extracted records"),
    "hashes": ("ไฟล์ที่ได้มาและค่าแฮช (SHA-256)", "Acquired files and SHA-256 hashes"),
    "audit": ("บันทึกการทำงาน (Audit log)", "Audit log"),
    "signature": ("การรับรองผลการตรวจพิสูจน์", "Examiner certification"),
    "toc": ("สารบัญ", "Contents"),
    "report_id": ("เลขที่รายงาน", "Report ID"),
    "generated": ("จัดทำเมื่อ", "Generated"),
    "range": ("ช่วงเวลาข้อมูล", "Date range"),
    "all_time": ("ทั้งหมด", "All"),
    "demo": ("ข้อมูลจากอุปกรณ์จำลองเพื่อการสาธิต", "Synthetic demo data"),
    "category": ("หมวดข้อมูล", "Category"),
    "count": ("จำนวน", "Count"),
    "note": ("หมายเหตุ", "Note"),
    "shown": ("แสดง {n:,} จาก {total:,} รายการ (ดูทั้งหมดในไฟล์ Excel)", "Showing {n:,} of {total:,} rows (see the Excel file for all)"),
    "filtered": ("ในช่วงเวลาที่เลือก {n:,} จากทั้งหมด {total:,}", "{n:,} in range of {total:,}"),
    "no_rows": ("ไม่มีข้อมูล", "No records"),
    "certify": (
        "ข้าพเจ้าขอรับรองว่าได้ทำการสกัดและตรวจพิสูจน์ข้อมูลจากอุปกรณ์ข้างต้นด้วยวิธีการที่ระบุ ไฟล์ทุกไฟล์ที่ได้มาได้คำนวณค่าแฮช SHA-256 และบันทึกการทำงานไว้ครบถ้วน ข้อมูลในรายงานนี้ตรงกับข้อมูลที่ได้จากอุปกรณ์",
        "I certify that the devices above were extracted and examined using the stated methods, every acquired file was hashed with SHA-256, every step was logged, and this report reflects the data obtained from the devices.",
    ),
    "sign_examiner": ("ลงชื่อ ................................................ ผู้ตรวจพิสูจน์", "Signature ........................................ Examiner"),
    "sign_reviewer": ("ลงชื่อ ................................................ ผู้ตรวจทาน", "Signature ........................................ Reviewer"),
    "date_line": ("วันที่ ........ / ........ / ............", "Date ........ / ........ / ............"),
    "shared": ("รายการร่วม", "Shared"),
    "via": ("เชื่อมผ่าน", "Linked by"),
    "number": ("หมายเลข", "Number"),
    "name": ("ชื่อ", "Name"),
    "total": ("รวม", "Total"),
    "calls_out": ("โทรออก", "Out"),
    "calls_in": ("โทรเข้า", "In"),
    "missed": ("ไม่ได้รับ", "Missed"),
    "sms": ("SMS", "SMS"),
    "talk": ("เวลาสนทนา", "Talk time"),
    "days": ("วันที่ติดต่อ", "Active days"),
    "night": ("กลางคืน", "Night"),
    "first": ("ครั้งแรก", "First"),
    "last": ("ล่าสุด", "Last"),
    "devices_col": ("เครื่อง", "Devices"),
    "when": ("วันเวลา", "When"),
    "type": ("ประเภท", "Type"),
    "detail": ("รายละเอียด", "Detail"),
    "device": ("เครื่อง", "Device"),
    "file": ("ไฟล์", "File"),
    "source": ("ที่มา", "Source"),
    "time": ("เวลา", "Time"),
    "action": ("การกระทำ", "Action"),
    "item": ("รายการ", "Item"),
    "value": ("ข้อมูล", "Value"),
    "method": ("วิธีการสกัด", "Method"),
    "started": ("เริ่ม", "Started"),
    "finished": ("สิ้นสุด", "Finished"),
    "backup_files": ("ไฟล์ backup ของ iOS {n:,} ไฟล์ มีค่าแฮชครบใน manifest.json และไฟล์ Excel", "{n:,} iOS backup files are hashed in manifest.json and the Excel file"),
}

CASE_LABELS = [
    ("case_no", "เลขคดี", "Case number"),
    ("title", "ชื่อคดี", "Case name"),
    ("crime_type", "ประเภทความผิด", "Crime type"),
    ("evidence_no", "เลขของกลาง", "Evidence number"),
    ("examiner", "ผู้ตรวจพิสูจน์", "Examiner"),
    ("investigator", "พนักงานสอบสวน", "Investigator"),
    ("department", "หน่วยงาน/กอง", "Department"),
    ("organization", "สังกัด", "Organization"),
    ("unit", "หน่วย", "Unit"),
    ("location", "สถานที่ตรวจ", "Location"),
    ("note", "หมายเหตุ", "Notes"),
]

METHODS = {
    "adb-logical": ("ADB (logical)", "ADB (logical)"),
    "itunes-backup": ("iOS backup (logical)", "iOS backup (logical)"),
    "cdr": ("นำเข้า CDR", "CDR import"),
    "demo": ("อุปกรณ์จำลอง (สาธิต)", "Demo device"),
}

KIND_TH = {"call": ("โทร", "Call"), "sms": ("SMS", "SMS"), "chat": ("แชต", "Chat"), "photo": ("รูปภาพ", "Photo"),
           "web": ("เว็บ", "Web"), "note": ("บันทึก", "Note"), "voice": ("บันทึกเสียง", "Recording"), "wifi": ("Wi-Fi", "Wi-Fi"),
           "app": ("ติดตั้งแอป", "App"), "sim": ("ซิม", "SIM"), "extraction": ("สกัดข้อมูล", "Extraction"), "manual": ("บันทึกผู้ตรวจ", "Examiner entry")}


def tr(ds: Dataset, key: str, **kw: Any) -> str:
    text = T[key][0 if ds.th else 1]
    return text.format(**kw) if kw else text


def report_title(ds: Dataset) -> str:
    return ds.spec.title or tr(ds, "title")


def generated_text(ds: Dataset) -> str:
    if ds.th and ds.spec.buddhist_year:
        return f"{thai_date(ds.generated)} เวลา {ds.generated:%H:%M} น."
    return f"{ds.generated:%d/%m/%Y %H:%M}"


def range_text(ds: Dataset) -> str:
    s = ds.spec
    if s.date_from is None and s.date_to is None:
        return tr(ds, "all_time")
    return f"{fmt_dt(s.date_from) or '…'} – {fmt_dt(s.date_to) or '…'}"


def case_rows(ds: Dataset) -> list[tuple[str, str]]:
    idx = 1 if ds.th else 2
    rows = [(f[idx], str(ds.case.get(f[0]) or "")) for f in CASE_LABELS if ds.case.get(f[0])]
    rows.append((tr(ds, "report_id"), ds.report_id))
    rows.append((tr(ds, "generated"), generated_text(ds)))
    rows.append((tr(ds, "range"), range_text(ds)))
    return rows


def device_info_rows(ds: Dataset, dev: DeviceData) -> list[tuple[str, str]]:
    rows = device_rows(dev.info.get("device") or {}, ds.spec.lang)
    method = dev.info.get("method", "")
    rows.append((tr(ds, "method"), METHODS.get(method, (method, method))[0 if ds.th else 1]))
    rows.append((tr(ds, "started"), fmt_iso(dev.info.get("started"))))
    rows.append((tr(ds, "finished"), fmt_iso(dev.info.get("finished"))))
    return rows


def summary_rows(ds: Dataset) -> tuple[list[str], list[list[Any]]]:
    li = 0 if ds.th else 1
    head = [tr(ds, "category")] + [d.label for d in ds.devices]
    rows = []
    for kind in ALL_KINDS:
        if kind not in ds.spec.kinds:
            continue
        row: list[Any] = [KIND_LABELS[kind][li]]
        for d in ds.devices:
            n = len(d.records.get(kind, []))
            total = d.totals.get(kind, 0)
            reason = (d.info.get("unavailable") or {}).get(kind, {}).get("reason")
            if not total and reason:
                row.append("— " + UNAVAILABLE.get(reason, (reason, reason))[li])
            else:
                row.append(f"{n:,}" if n == total else f"{n:,} / {total:,}")
        rows.append(row)
    return head, rows


def kind_table(ds: Dataset, kind: str, records: list[dict[str, Any]]) -> tuple[list[str], list[list[Any]], list[float]]:
    cols = columns(kind, ds.spec.lang)
    head = ["#"] + [header(c, ds.spec.lang) for c in cols]
    rows = [[i] + [c[2](r) for c in cols] for i, r in enumerate(records[: ds.spec.max_rows], 1)]
    return head, rows, [0.35] + [c[3] for c in cols]


def top_contacts_table(ds: Dataset) -> tuple[list[str], list[list[Any]], list[float]]:
    head = ["#", tr(ds, "name"), tr(ds, "number"), tr(ds, "total"), tr(ds, "calls_out"), tr(ds, "calls_in"), tr(ds, "missed"),
            tr(ds, "sms"), tr(ds, "talk"), tr(ds, "days"), tr(ds, "night"), tr(ds, "first"), tr(ds, "last"), tr(ds, "devices_col")]
    rows = [[i, c.get("name") or "", c.get("number") or c["key"], c["total"], c["calls_out"], c["calls_in"], c["missed"],
             c["sms_in"] + c["sms_out"], fmt_duration(c["duration"]), c["active_days"], c["night"], fmt_dt(c["first"]),
             fmt_dt(c["last"]), ", ".join(ds.device_label(d) for d in c["devices"])] for i, c in enumerate(ds.top_contacts, 1)]
    return head, rows, [0.3, 1.3, 1.1, 0.5, 0.5, 0.5, 0.5, 0.5, 0.7, 0.5, 0.5, 1.1, 1.1, 1.6]


def cross_device_table(ds: Dataset) -> tuple[list[str], list[list[Any]], list[float]]:
    head = [tr(ds, "devices_col"), tr(ds, "via"), tr(ds, "type")]
    rows = []
    for pair in ds.cross_device:
        for n in pair["shared"]:
            names = ", ".join((n["props"].get("names") or [])[:2])
            rows.append([f"{pair['a']} — {pair['b']}", f"{n['label']}" + (f" ({names})" if names and names != n["label"] else ""), n["type"]])
    return head, rows, [1.5, 2.2, 0.8]


def bookmark_table(ds: Dataset) -> tuple[list[str], list[list[Any]], list[float]]:
    li = 0 if ds.th else 1
    head = [tr(ds, "when"), tr(ds, "type"), tr(ds, "name"), tr(ds, "detail"), tr(ds, "note"), tr(ds, "device")]
    rows = [[fmt_dt(e["ts"]), e["extra"].get("entity_type") if e["kind"] == "manual" else KIND_TH.get(e["kind"], (e["kind"],) * 2)[li],
             e["name"], e.get("detail", ""), e.get("bookmark") or "", ds.device_label(e["device"]) if e.get("device") else ""]
            for e in ds.bookmarks]
    return head, rows, [1.1, 0.8, 1.3, 2.6, 1.2, 1.1]


def hash_rows(ds: Dataset) -> tuple[list[str], list[list[Any]], list[float], int]:
    head = [tr(ds, "device"), tr(ds, "file"), tr(ds, "source"), "SHA-256"]
    rows, backup = [], 0
    for d in ds.devices:
        for f in d.files:
            if str(f.get("source", "")).startswith("backup:"):
                backup += 1
                continue
            rows.append([d.label, f["rel_path"], f["source"], f["sha256"]])
    return head, rows[: ds.spec.max_rows], [0.9, 1.8, 2.0, 2.6], backup


def audit_rows(ds: Dataset) -> tuple[list[str], list[list[Any]], list[float]]:
    head = [tr(ds, "time"), tr(ds, "device"), tr(ds, "action"), tr(ds, "detail")]
    raw = [(a["ts"], d.label, a) for d in ds.devices for a in d.audit] + [(a["ts"], "", a) for a in ds.case_audit]
    raw.sort(key=lambda r: r[0] or "")
    rows = [[fmt_iso(ts), label, a["action"], a["detail"]] for ts, label, a in raw]
    return head, rows[: ds.spec.max_rows], [1.1, 1.0, 1.1, 4.0]


__all__ = ["DEVICE_FIELDS"]
