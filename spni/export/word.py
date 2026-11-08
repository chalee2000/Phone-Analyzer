"""Photos to Word: a printable photo sheet with metadata and SHA-256 per image."""

from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from PIL import Image, ImageOps

from .. import __version__
from . import report_name
from .labels import fmt_dt, thai_date

FONT = "TH Sarabun New"  # standard Thai government font
NAVY = RGBColor(0x0F, 0x21, 0x47)
GOLD = RGBColor(0xB8, 0x86, 0x14)


def _font(run, size: float, bold: bool = False, color: RGBColor | None = None) -> None:
    run.font.name = FONT
    run.font.size = Pt(size)
    run.font.bold = bold
    rpr = run._element.get_or_add_rPr()
    fonts = rpr.find(qn("w:rFonts"))
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        rpr.append(fonts)
    for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        fonts.set(qn(attr), FONT)
    szcs = OxmlElement("w:szCs")
    szcs.set(qn("w:val"), str(int(size * 2)))
    rpr.append(szcs)
    if bold:
        rpr.append(OxmlElement("w:bCs"))
    if color is not None:
        run.font.color.rgb = color


def _para(container, text: str, size: float = 14, bold: bool = False, color=None, align=None):
    p = container.add_paragraph()
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.space_before = Pt(0)
    if align is not None:
        p.alignment = align
    _font(p.add_run(text), size, bold, color)
    return p


def _scaled_jpeg(path: Path, max_px: int = 1400) -> io.BytesIO | None:
    try:
        with Image.open(path) as img:
            img = ImageOps.exif_transpose(img)
            img.thumbnail((max_px, max_px))
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=88)
            buf.seek(0)
            return buf
    except Exception:
        return None


def build_photos(*, case, extraction, records, ext_dir: Path, out_dir: Path, lang: str = "th", **_: Any) -> Path:
    th = lang == "th"
    photos = records.get("photos") or []
    device = extraction.get("device", {})
    doc = Document()
    sec = doc.sections[0]
    sec.orientation = WD_ORIENT.PORTRAIT
    sec.page_width, sec.page_height = Cm(21), Cm(29.7)
    sec.left_margin = sec.right_margin = Cm(2)
    sec.top_margin = sec.bottom_margin = Cm(1.8)

    _para(doc, "ภาพถ่ายจากโทรศัพท์มือถือ" if th else "Photos extracted from the mobile device", 22, True, NAVY, WD_ALIGN_PARAGRAPH.CENTER)
    info = [
        ("เลขคดี" if th else "Case no.", case.get("case_no", "")),
        ("ชื่อคดี" if th else "Case", case.get("title", "")),
        ("อุปกรณ์" if th else "Device", f"{device.get('brand', '')} {device.get('market_name') or device.get('model', '')}".strip()),
        ("หมายเลขซีเรียล" if th else "Serial", device.get("serial", "")),
        ("เบอร์เครื่อง" if th else "Device number", device.get("phone_number", "")),
        ("จำนวนภาพ" if th else "Photos", f"{len(photos):,}"),
        ("จัดทำเมื่อ" if th else "Generated", thai_date() if th else datetime.now().strftime("%d/%m/%Y %H:%M")),
    ]
    for k, v in info:
        if v:
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(0)
            _font(p.add_run(f"{k}: "), 15, True, NAVY)
            _font(p.add_run(str(v)), 15)
    _para(doc, f"SPNI Phone Analysis v{__version__}", 11, False, GOLD)

    cols = 2
    table = doc.add_table(rows=0, cols=cols)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.style = "Table Grid"
    row_cells = None
    for i, p in enumerate(photos):
        if i % cols == 0:
            row_cells = table.add_row().cells
        cell = row_cells[i % cols]  # type: ignore[index]
        cell.width = Cm(8.5)
        first = cell.paragraphs[0]
        first.alignment = WD_ALIGN_PARAGRAPH.CENTER
        img = _scaled_jpeg(ext_dir / p["path"]) if p.get("path") else None
        if img:
            first.add_run().add_picture(img, width=Cm(7.8))
        else:
            _font(first.add_run("[ไม่สามารถแสดงภาพ]" if th else "[preview unavailable]"), 12)
        lines = [
            f"{i + 1}. {p.get('name', '')}",
            f"{'วันที่ถ่าย' if th else 'Taken'}: {fmt_dt(p.get('taken'))}",
        ]
        if p.get("lat") is not None:
            lines.append(f"{'พิกัด' if th else 'GPS'}: {p['lat']:.5f}, {p['lon']:.5f}")
        if p.get("camera_model"):
            lines.append(f"{'กล้อง' if th else 'Camera'}: {p.get('make', '')} {p['camera_model']}".strip())
        for ln in lines:
            _para(cell, ln, 13, ln.startswith(f"{i + 1}."))
        _para(cell, f"SHA-256: {p.get('sha256', '')}", 9, False, RGBColor(0x5B, 0x6B, 0x86))

    path = out_dir / report_name(case, extraction, "Photos", ".docx")
    doc.save(path)
    return path
