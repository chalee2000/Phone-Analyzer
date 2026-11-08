"""PDF report (A4 landscape, Thai font Sarabun with HarfBuzz shaping)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    CondPageBreak,
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .. import APP_NAME, __version__
from ..models import ALL_KINDS
from ..paths import font
from . import report_name
from .labels import KIND_LABELS, UNAVAILABLE, columns, device_rows, fmt_dt, fmt_iso, header, thai_date
from .thai_wrap import wrap

NAVY = colors.HexColor("#0F2147")
NAVY_2 = colors.HexColor("#1B3A73")
GOLD = colors.HexColor("#D9A42B")
LINE = colors.HexColor("#D5DCE8")
ZEBRA = colors.HexColor("#F4F7FC")
MUTED = colors.HexColor("#5B6B86")

PAGE = landscape(A4)
MARGIN = 14 * mm
BODY_SIZE = 8.6
MAX_ROWS = 5000  # per category; the Excel export always has everything


def _register_fonts() -> None:
    if "Sarabun" in pdfmetrics.getRegisteredFontNames():
        return
    pdfmetrics.registerFont(TTFont("Sarabun", str(font("Sarabun-Regular.ttf"))))
    pdfmetrics.registerFont(TTFont("Sarabun-Bold", str(font("Sarabun-Bold.ttf"))))
    pdfmetrics.registerFont(TTFont("Sarabun-SemiBold", str(font("Sarabun-SemiBold.ttf"))))
    from reportlab.pdfbase.pdfmetrics import registerFontFamily

    registerFontFamily("Sarabun", normal="Sarabun", bold="Sarabun-Bold", italic="Sarabun", boldItalic="Sarabun-Bold")


def _styles():
    return {
        "title": ParagraphStyle("title", fontName="Sarabun-Bold", fontSize=22, leading=28, textColor=NAVY),
        "subtitle": ParagraphStyle("subtitle", fontName="Sarabun", fontSize=11, leading=15, textColor=MUTED),
        "h2": ParagraphStyle("h2", fontName="Sarabun-Bold", fontSize=14, leading=19, textColor=NAVY, spaceBefore=6, spaceAfter=6),
        "cell": ParagraphStyle("cell", fontName="Sarabun", fontSize=BODY_SIZE, leading=BODY_SIZE * 1.35),
        "head": ParagraphStyle("head", fontName="Sarabun-Bold", fontSize=BODY_SIZE, leading=BODY_SIZE * 1.3, textColor=colors.white),
        "small": ParagraphStyle("small", fontName="Sarabun", fontSize=7, leading=9, textColor=MUTED),
    }


def _cell(text: Any, style: ParagraphStyle, width: float) -> Paragraph:
    text = "" if text is None else str(text)
    inner = max(10.0, width - 6)
    measure = lambda s: pdfmetrics.stringWidth(s, style.fontName, style.fontSize)  # noqa: E731
    lines = wrap(text, inner, measure) if text else [""]
    return Paragraph("<br/>".join(escape(ln) for ln in lines), style)


def _table(headers: list[str], rows: list[list[Any]], rel_widths: list[float], st) -> Table:
    avail = PAGE[0] - 2 * MARGIN
    total = sum(rel_widths)
    widths = [avail * w / total for w in rel_widths]
    data = [[_cell(h, st["head"], w) for h, w in zip(headers, widths)]]
    data += [[_cell(v, st["cell"], w) for v, w in zip(row, widths)] for row in rows]
    table = Table(data, colWidths=widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]
    for i in range(2, len(data), 2):
        style.append(("BACKGROUND", (0, i), (-1, i), ZEBRA))
    table.setStyle(TableStyle(style))
    return table


def _kv_table(rows: list[tuple[str, str]], st, key_w: float = 0.32) -> Table:
    avail = (PAGE[0] - 2 * MARGIN) / 2 - 6 * mm
    widths = [avail * key_w, avail * (1 - key_w)]
    data = [[_cell(k, ParagraphStyle("k", parent=st["cell"], fontName="Sarabun-SemiBold", textColor=NAVY), widths[0]),
             _cell(v, st["cell"], widths[1])] for k, v in rows]
    t = Table(data, colWidths=widths)
    t.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
    ]))
    return t


def build(*, case, extraction, records, files, ext_dir: Path, out_dir: Path, lang: str = "th", **_: Any) -> Path:
    _register_fonts()
    st = _styles()
    th = lang == "th"
    li = 0 if th else 1
    path = out_dir / report_name(case, extraction, "Report", ".pdf")
    device = extraction.get("device", {})
    case_label = case.get("case_no") or case.get("title") or ""

    def decorate(canvas, doc):
        canvas.saveState()
        w, h = PAGE
        canvas.setFillColor(NAVY)
        canvas.rect(0, h - 11 * mm, w, 11 * mm, stroke=0, fill=1)
        canvas.setFillColor(GOLD)
        canvas.rect(0, h - 11.8 * mm, w, 0.8 * mm, stroke=0, fill=1)
        canvas.setFont("Sarabun-Bold", 10.5)
        canvas.setFillColor(colors.white)
        canvas.drawString(MARGIN, h - 7.2 * mm, APP_NAME)
        canvas.setFont("Sarabun", 8.5)
        canvas.drawRightString(w - MARGIN, h - 7.2 * mm, f"{'คดี' if th else 'Case'} {case_label}  ·  {device.get('market_name') or device.get('model', '')}")
        canvas.setFillColor(MUTED)
        canvas.setFont("Sarabun", 7.5)
        canvas.drawString(MARGIN, 7 * mm, f"{APP_NAME} v{__version__}  ·  {extraction.get('id', '')}")
        canvas.drawRightString(w - MARGIN, 7 * mm, f"{'หน้า' if th else 'Page'} {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(str(path), pagesize=PAGE, leftMargin=MARGIN, rightMargin=MARGIN,
                            topMargin=18 * mm, bottomMargin=13 * mm,
                            title=f"{APP_NAME} Report", author=case.get("investigator", ""))
    story: list[Any] = []
    story.append(Paragraph("รายงานการสกัดข้อมูลโทรศัพท์มือถือ" if th else "Mobile Device Extraction Report", st["title"]))
    sub = f"{'จัดทำเมื่อ' if th else 'Generated'} {thai_date() if th else fmt_dt(time.time() * 1000)}"
    if extraction.get("method") == "demo":
        sub += "  ·  " + ("ข้อมูลจากอุปกรณ์จำลองเพื่อการสาธิต" if th else "Synthetic demo data")
    story.append(Paragraph(sub, st["subtitle"]))
    story.append(Spacer(1, 6 * mm))

    case_rows = [
        ("เลขคดี" if th else "Case no.", case.get("case_no", "")),
        ("ชื่อคดี" if th else "Case title", case.get("title", "")),
        ("ผู้ตรวจ" if th else "Examiner", case.get("investigator", "")),
        ("หน่วยงาน" if th else "Unit", case.get("unit", "")),
        ("เริ่มสกัดข้อมูล" if th else "Started", fmt_iso(extraction.get("started"))),
        ("สิ้นสุด" if th else "Finished", fmt_iso(extraction.get("finished"))),
        ("วิธีการ" if th else "Method", extraction.get("method", "")),
    ]
    left = [Paragraph("ข้อมูลคดี" if th else "Case", st["h2"]), _kv_table([r for r in case_rows if r[1]], st)]
    right = [Paragraph("ข้อมูลอุปกรณ์" if th else "Device", st["h2"]), _kv_table(device_rows(device, lang), st)]
    half = (PAGE[0] - 2 * MARGIN) / 2
    two = Table([[left, right]], colWidths=[half, half])
    two.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story.append(two)
    story.append(Spacer(1, 4 * mm))

    counts = extraction.get("summary") or {}
    unavailable = extraction.get("unavailable") or {}
    summary_rows = []
    for kind in ALL_KINDS:
        reason = (unavailable.get(kind) or {}).get("reason")
        note = UNAVAILABLE.get(reason, (reason or "",) * 2)[li] if reason else ""
        summary_rows.append([KIND_LABELS[kind][li], f"{counts.get(kind, 0):,}", note])
    story.append(KeepTogether([
        Paragraph("สรุปจำนวนข้อมูล" if th else "Summary", st["h2"]),
        _table(["หมวดข้อมูล" if th else "Category", "จำนวน" if th else "Count", "หมายเหตุ" if th else "Note"], summary_rows, [2, 1, 4], st),
    ]))

    for kind in ALL_KINDS:
        items = records.get(kind) or []
        if not items:
            continue
        story.append(PageBreak())
        title = f"{KIND_LABELS[kind][li]}  ({len(items):,})"
        story.append(Paragraph(title, st["h2"]))
        if kind == "photos":
            story.extend(_contact_sheet(items, ext_dir, st, th))
            story.append(CondPageBreak(60 * mm))
        cols = columns(kind, lang)
        shown = items[:MAX_ROWS]
        rows = [[i] + [c[2](r) for c in cols] for i, r in enumerate(shown, 1)]
        story.append(_table(["#"] + [header(c, lang) for c in cols], rows, [0.35] + [c[3] for c in cols], st))
        if len(items) > MAX_ROWS:
            story.append(Paragraph(
                (f"แสดง {MAX_ROWS:,} รายการแรกจาก {len(items):,} รายการ ดูทั้งหมดในไฟล์ Excel" if th
                 else f"First {MAX_ROWS:,} of {len(items):,} rows shown; see the Excel export for all rows."), st["small"]))

    story.append(PageBreak())
    story.append(Paragraph("ไฟล์ที่ได้มาและค่าแฮช (SHA-256)" if th else "Acquired files and SHA-256 hashes", st["h2"]))
    listed = [f for f in files if not str(f.get("source", "")).startswith("backup:")]
    backup = len(files) - len(listed)
    if backup:
        story.append(Paragraph(
            (f"ไฟล์ backup ของ iOS จำนวน {backup:,} ไฟล์ บันทึกค่าแฮชไว้ครบใน manifest.json และไฟล์ Excel" if th
             else f"{backup:,} iOS backup files are hashed in manifest.json and the Excel export."), st["small"]))
        story.append(Spacer(1, 2 * mm))
    story.append(_table(["ไฟล์" if th else "File", "ที่มา" if th else "Source", "SHA-256"],
                        [[f["rel_path"], f["source"], f["sha256"]] for f in listed[:MAX_ROWS]], [2.2, 2.6, 2.6], st))

    doc.build(story, onFirstPage=decorate, onLaterPages=decorate)
    return path


def _contact_sheet(items: list[dict[str, Any]], ext_dir: Path, st, th: bool) -> list[Any]:
    per_row = 6
    avail = PAGE[0] - 2 * MARGIN
    cell_w = avail / per_row
    img_w = cell_w - 4 * mm
    cells, rows = [], []
    for i, p in enumerate(items, 1):
        thumb = ext_dir / p["thumb"] if p.get("thumb") else None
        parts: list[Any] = []
        if thumb and thumb.is_file():
            try:
                img = Image(str(thumb))
                ratio = img.imageHeight / float(img.imageWidth or 1)
                img.drawWidth, img.drawHeight = img_w, min(img_w * ratio, img_w * 0.9)
                if img_w * ratio > img_w * 0.9:
                    img.drawWidth = img.drawHeight / ratio
                parts.append(img)
            except Exception:
                pass
        parts.append(Paragraph(f"{i}. {escape(p.get('name', ''))}<br/>{fmt_dt(p.get('taken'))}", st["small"]))
        cells.append(parts)
        if len(cells) == per_row:
            rows.append(cells)
            cells = []
    if cells:
        rows.append(cells + [""] * (per_row - len(cells)))
    if not rows:
        return []
    t = Table(rows, colWidths=[cell_w] * per_row)
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    return [t, Spacer(1, 4 * mm)]
