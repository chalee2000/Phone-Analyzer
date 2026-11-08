"""Excel workbook: summary sheet, one sheet per category, file hashes, audit."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .. import APP_NAME, __version__
from ..models import ALL_KINDS
from . import report_name
from .labels import KIND_LABELS, UNAVAILABLE, columns, device_rows, fmt_iso, header

FONT = "Tahoma"  # ships with every Windows install and renders Thai well
NAVY = "0F2147"
GOLD = "D9A42B"
HEAD_FILL = PatternFill("solid", fgColor=NAVY)
ZEBRA = PatternFill("solid", fgColor="F3F6FB")
THIN = Side(style="thin", color="D5DCE8")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
ILLEGAL = {i for i in range(32) if i not in (9, 10, 13)}


def _clean(value: Any) -> Any:
    if isinstance(value, str):
        value = "".join(ch for ch in value if ord(ch) not in ILLEGAL)
        if value[:1] in ("=", "+", "-", "@") and not value[1:2].isdigit():
            value = "'" + value  # never let device data become a formula
    return value


def _table(ws, start_row: int, headers: list[str], rows: list[list[Any]], widths: list[float] | None = None) -> None:
    for c, h in enumerate(headers, 1):
        cell = ws.cell(row=start_row, column=c, value=h)
        cell.font = Font(name=FONT, bold=True, color="FFFFFF", size=10)
        cell.fill = HEAD_FILL
        cell.alignment = Alignment(vertical="center", horizontal="center", wrap_text=True)
        cell.border = BORDER
    for r, row in enumerate(rows, start_row + 1):
        for c, value in enumerate(row, 1):
            cell = ws.cell(row=r, column=c, value=_clean(value))
            cell.font = Font(name=FONT, size=10)
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cell.border = BORDER
            if (r - start_row) % 2 == 0:
                cell.fill = ZEBRA
    if widths:
        for c, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(c)].width = w
    ws.row_dimensions[start_row].height = 24


def build(*, case, extraction, records, files, out_dir: Path, lang: str = "th", **_: Any) -> Path:
    th = lang == "th"
    wb = Workbook()
    ws = wb.active
    ws.title = "สรุป" if th else "Summary"
    ws.sheet_view.showGridLines = False
    ws["A1"] = "รายงานการสกัดข้อมูลโทรศัพท์มือถือ" if th else "Mobile Device Extraction Report"
    ws["A1"].font = Font(name=FONT, size=16, bold=True, color=NAVY)
    ws["A2"] = f"{APP_NAME} v{__version__}"
    ws["A2"].font = Font(name=FONT, size=10, color=GOLD, bold=True)

    case_rows = [
        ("เลขคดี" if th else "Case no.", case.get("case_no", "")),
        ("ชื่อคดี" if th else "Case title", case.get("title", "")),
        ("ผู้ตรวจ" if th else "Examiner", case.get("investigator", "")),
        ("หน่วยงาน" if th else "Unit", case.get("unit", "")),
        ("เริ่มสกัดข้อมูล" if th else "Started", fmt_iso(extraction.get("started"))),
        ("สิ้นสุด" if th else "Finished", fmt_iso(extraction.get("finished"))),
        ("วิธีการ" if th else "Method", extraction.get("method", "")),
        ("สถานะ" if th else "Status", extraction.get("status", "")),
    ]
    _table(ws, 4, ["รายการ" if th else "Item", "ข้อมูล" if th else "Value"], [list(r) for r in case_rows], [28, 60])
    row = 6 + len(case_rows)
    dev = device_rows(extraction.get("device", {}), lang)
    _table(ws, row, ["ข้อมูลอุปกรณ์" if th else "Device", ""], [list(r) for r in dev])
    row += len(dev) + 2
    counts = extraction.get("summary") or {}
    unavailable = extraction.get("unavailable") or {}
    summary = []
    for kind in ALL_KINDS:
        reason = unavailable.get(kind, {}).get("reason")
        note = UNAVAILABLE.get(reason, (reason or "",) * 2)[0 if th else 1] if reason else ""
        summary.append([KIND_LABELS[kind][0 if th else 1], counts.get(kind, 0), note])
    _table(ws, row, ["หมวดข้อมูล" if th else "Category", "จำนวน" if th else "Count", "หมายเหตุ" if th else "Note"], summary)
    ws.column_dimensions["C"].width = 50

    for kind in ALL_KINDS:
        items = records.get(kind) or []
        if not items:
            continue
        sheet = wb.create_sheet(KIND_LABELS[kind][0 if th else 1][:31].replace("/", "-"))
        cols = columns(kind, lang)
        heads = ["ลำดับ" if th else "#"] + [header(c, lang) for c in cols]
        rows = [[i] + [c[2](r) for c in cols] for i, r in enumerate(items, 1)]
        _table(sheet, 1, heads, rows, [7] + [max(10, c[3] * 16) for c in cols])
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = f"A1:{get_column_letter(len(heads))}{len(rows) + 1}"

    hs = wb.create_sheet("ค่าแฮช" if th else "Hashes")
    _table(hs, 1, ["ไฟล์" if th else "File", "ที่มา" if th else "Source", "ขนาด (ไบต์)" if th else "Size (bytes)", "SHA-256"],
           [[f["rel_path"], f["source"], f["size"], f["sha256"]] for f in files], [50, 60, 14, 70])
    hs.freeze_panes = "A2"

    path = out_dir / report_name(case, extraction, "Excel", ".xlsx")
    wb.save(path)
    return path
