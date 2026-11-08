"""Forensic report as Word (.docx) and Excel (.xlsx)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from openpyxl import Workbook
from openpyxl.styles import Font

from .. import APP_NAME, __version__
from ..export.excel import _table as xl_table
from ..export.word import FONT, _font
from ..models import ALL_KINDS
from . import common as c
from .dataset import Dataset

NAVY = RGBColor(0x0F, 0x21, 0x47)
RED = RGBColor(0xC6, 0x28, 0x28)


# ── Word ────────────────────────────────────────────────────────────────
def _shade(cell, hex_fill: str) -> None:
    tcpr = cell._element.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_fill)
    tcpr.append(shd)


def _para(doc, text: str, size: float = 14, bold: bool = False, color=None, align=None, space_after: float = 2):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(space_after)
    if align is not None:
        p.alignment = align
    _font(p.add_run(text), size, bold, color)
    return p


def _heading(doc, text: str, level: int) -> None:
    h = doc.add_heading(level=level)
    _font(h.add_run(text), 20 if level == 1 else 16, True, NAVY)


def _dtable(doc, head: list[str], rows: list[list[Any]], size: float = 11) -> None:
    t = doc.add_table(rows=1, cols=len(head))
    t.style = "Table Grid"
    for i, h in enumerate(head):
        cell = t.rows[0].cells[i]
        cell.text = ""
        _font(cell.paragraphs[0].add_run(str(h)), size, True, RGBColor(0xFF, 0xFF, 0xFF))
        _shade(cell, "0F2147")
    for r in rows:
        cells = t.add_row().cells
        for i, v in enumerate(r):
            cells[i].text = ""
            _font(cells[i].paragraphs[0].add_run("" if v is None else str(v)), size)
    doc.add_paragraph()


def _kv(doc, rows: list[tuple[str, str]]) -> None:
    t = doc.add_table(rows=0, cols=2)
    t.style = "Table Grid"
    for k, v in rows:
        cells = t.add_row().cells
        _font(cells[0].paragraphs[0].add_run(k), 13, True, NAVY)
        _shade(cells[0], "EEF3FC")
        _font(cells[1].paragraphs[0].add_run(v), 13)
    doc.add_paragraph()


def build_docx(ds: Dataset, path: Path) -> Path:
    doc = Document()
    sec = doc.sections[0]
    if ds.spec.orientation == "landscape":
        sec.orientation = WD_ORIENT.LANDSCAPE
        sec.page_width, sec.page_height = Cm(29.7), Cm(21)
    else:
        sec.page_width, sec.page_height = Cm(21), Cm(29.7)
    sec.left_margin = sec.right_margin = Cm(2)
    sec.top_margin = sec.bottom_margin = Cm(1.8)
    style = doc.styles["Normal"]
    style.font.name = FONT
    style.element.rPr.rFonts.set(qn("w:cs"), FONT)
    if ds.spec.classification:
        for part in (sec.header, sec.footer):
            p = part.paragraphs[0]  # header/footer always start with one empty paragraph
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            _font(p.add_run(ds.spec.classification), 16, True, RED)
        _para(doc, ds.spec.classification, 18, True, RED, WD_ALIGN_PARAGRAPH.CENTER)
    _para(doc, c.report_title(ds), 26, True, NAVY, WD_ALIGN_PARAGRAPH.CENTER, 6)
    _para(doc, f"{APP_NAME} v{__version__} · {ds.report_id}", 13, False, RGBColor(0xB8, 0x86, 0x14), WD_ALIGN_PARAGRAPH.CENTER, 14)
    _heading(doc, c.tr(ds, "case"), 1)
    _kv(doc, c.case_rows(ds))
    num = 1
    if ds.has("devices"):
        num += 1
        _heading(doc, f"{num}. {c.tr(ds, 'devices')}", 1)
        for d in ds.devices:
            _heading(doc, d.label, 2)
            _kv(doc, c.device_info_rows(ds, d))
    if ds.has("summary"):
        num += 1
        _heading(doc, f"{num}. {c.tr(ds, 'summary')}", 1)
        head, rows = c.summary_rows(ds)
        _dtable(doc, head, rows, 12)
    if any(ds.has(k) for k in ("network", "cross_device", "top_contacts", "bookmarks")):
        num += 1
        _heading(doc, f"{num}. {c.tr(ds, 'analysis')}", 1)
        if ds.has("network") and ds.network_png and ds.network_png.is_file():
            _heading(doc, c.tr(ds, "network"), 2)
            doc.add_picture(str(ds.network_png), width=Cm(24 if ds.spec.orientation == "landscape" else 16.5))
        if ds.has("cross_device") and ds.cross_device:
            _heading(doc, c.tr(ds, "cross"), 2)
            head, rows, _ = c.cross_device_table(ds)
            _dtable(doc, head, rows)
        if ds.has("top_contacts") and ds.top_contacts:
            _heading(doc, c.tr(ds, "top"), 2)
            head, rows, _ = c.top_contacts_table(ds)
            _dtable(doc, head, rows, 10)
        if ds.has("bookmarks") and ds.bookmarks:
            _heading(doc, c.tr(ds, "bookmarks"), 2)
            head, rows, _ = c.bookmark_table(ds)
            _dtable(doc, head, rows)
    if ds.has("records"):
        num += 1
        _heading(doc, f"{num}. {c.tr(ds, 'records')}", 1)
        limit = min(ds.spec.max_rows, 1500)  # Word gets slow with huge tables; Excel has everything
        for d in ds.devices:
            for kind in ALL_KINDS:
                recs = d.records.get(kind) or []
                if not recs:
                    continue
                _heading(doc, f"{d.label} — {c.KIND_LABELS[kind][0 if ds.th else 1]} ({len(recs):,})", 2)
                head, rows, _ = c.kind_table(ds, kind, recs[:limit])
                _dtable(doc, head, rows, 10)
                if len(recs) > limit:
                    _para(doc, c.tr(ds, "shown", n=limit, total=len(recs)), 11)
    if ds.has("hashes"):
        num += 1
        _heading(doc, f"{num}. {c.tr(ds, 'hashes')}", 1)
        head, rows, _, backup = c.hash_rows(ds)
        if backup:
            _para(doc, c.tr(ds, "backup_files", n=backup), 11)
        _dtable(doc, head, rows[:2000], 9)
    if ds.has("signature"):
        num += 1
        _heading(doc, f"{num}. {c.tr(ds, 'signature')}", 1)
        _para(doc, c.tr(ds, "certify"), 15, space_after=30)
        for key in ("sign_examiner", "sign_reviewer"):
            _para(doc, c.tr(ds, key), 15)
            _para(doc, f"( {(ds.case.get('examiner') if key == 'sign_examiner' else '') or '................................................'} )", 15)
            _para(doc, c.tr(ds, "date_line"), 15, space_after=24)
    doc.save(path)
    return path


# ── Excel ───────────────────────────────────────────────────────────────
def build_xlsx(ds: Dataset, path: Path) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "สรุป" if ds.th else "Summary"
    ws.sheet_view.showGridLines = False
    if ds.spec.classification:
        ws["A1"] = ds.spec.classification
        ws["A1"].font = Font(name="Tahoma", size=14, bold=True, color="C62828")
    ws["A2"] = c.report_title(ds)
    ws["A2"].font = Font(name="Tahoma", size=16, bold=True, color="0F2147")
    ws["A3"] = f"{APP_NAME} v{__version__} · {ds.report_id}"
    row = 5
    rows = c.case_rows(ds)
    xl_table(ws, row, [c.tr(ds, "item"), c.tr(ds, "value")], [list(r) for r in rows], [28, 70])
    row += len(rows) + 2
    head, srows = c.summary_rows(ds)
    xl_table(ws, row, head, srows)
    for d in ds.devices:
        name = d.label[:28].replace("/", "-").replace(":", "-")
        ds_ws = wb.create_sheet(f"อุปกรณ์ {name}"[:31] if ds.th else f"Device {name}"[:31])
        rows = c.device_info_rows(ds, d)
        xl_table(ds_ws, 1, [c.tr(ds, "item"), c.tr(ds, "value")], [list(r) for r in rows], [30, 80])
    if ds.top_contacts:
        head, rows, _ = c.top_contacts_table(ds)
        xl_table(wb.create_sheet(c.tr(ds, "top")[:31]), 1, head, rows, [5, 22, 15, 8, 8, 8, 8, 8, 11, 9, 9, 19, 19, 30])
    if ds.cross_device:
        head, rows, _ = c.cross_device_table(ds)
        xl_table(wb.create_sheet(c.tr(ds, "cross")[:31]), 1, head, rows, [40, 40, 14])
    if ds.bookmarks:
        head, rows, _ = c.bookmark_table(ds)
        xl_table(wb.create_sheet((c.tr(ds, "bookmarks"))[:31]), 1, head, rows, [19, 14, 24, 60, 24, 22])
    if ds.has("records"):
        li = 0 if ds.th else 1
        for kind in ALL_KINDS:
            all_rows: list[list[Any]] = []
            head: list[str] = []
            for d in ds.devices:
                recs = d.records.get(kind) or []
                if not recs:
                    continue
                h, rows, _ = c.kind_table(ds, kind, recs)
                head = [c.tr(ds, "device")] + h
                all_rows += [[d.label] + r for r in rows]
            if all_rows:
                sheet = wb.create_sheet(c.KIND_LABELS[kind][li][:31].replace("/", "-"))
                xl_table(sheet, 1, head, all_rows, [18, 6] + [22] * (len(head) - 2))
                sheet.freeze_panes = "A2"
    if ds.has("hashes"):
        hs = wb.create_sheet("SHA-256")
        rows = [[d.label, f["rel_path"], f["source"], f["size"], f["sha256"]] for d in ds.devices for f in d.files]
        xl_table(hs, 1, [c.tr(ds, "device"), c.tr(ds, "file"), c.tr(ds, "source"), "Bytes", "SHA-256"], rows, [18, 50, 50, 12, 70])
    if ds.has("audit"):
        head, rows, _ = c.audit_rows(ds)
        xl_table(wb.create_sheet("Audit"), 1, head, rows, [20, 20, 22, 90])
    wb.save(path)
    return path
