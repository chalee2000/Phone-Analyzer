"""Forensic report as PDF: cover, contents, sections, page X / Y, optional
classification banners / watermark and password protection."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape, portrait
from reportlab.lib.pdfencrypt import StandardEncryption
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    BaseDocTemplate,
    CondPageBreak,
    Frame,
    Image,
    KeepTogether,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents

from .. import APP_NAME, __version__
from ..export.pdf import _register_fonts
from ..export.thai_wrap import wrap
from ..models import ALL_KINDS
from . import common as c
from .dataset import Dataset

NAVY = colors.HexColor("#0F2147")
GOLD = colors.HexColor("#D9A42B")
LINE = colors.HexColor("#D5DCE8")
ZEBRA = colors.HexColor("#F4F7FC")
MUTED = colors.HexColor("#5B6B86")
RED = colors.HexColor("#C62828")
MARGIN = 15 * mm
BODY = 8.4


def _styles() -> dict[str, ParagraphStyle]:
    return {
        "h1": ParagraphStyle("h1", fontName="Sarabun-Bold", fontSize=16, leading=22, textColor=NAVY, spaceBefore=4, spaceAfter=8),
        "h2": ParagraphStyle("h2", fontName="Sarabun-Bold", fontSize=12.5, leading=17, textColor=NAVY, spaceBefore=8, spaceAfter=5),
        "body": ParagraphStyle("body", fontName="Sarabun", fontSize=10.5, leading=15),
        "cell": ParagraphStyle("cell", fontName="Sarabun", fontSize=BODY, leading=BODY * 1.35),
        "head": ParagraphStyle("head", fontName="Sarabun-Bold", fontSize=BODY, leading=BODY * 1.3, textColor=colors.white),
        "key": ParagraphStyle("key", fontName="Sarabun-SemiBold", fontSize=9.5, leading=13, textColor=NAVY),
        "val": ParagraphStyle("val", fontName="Sarabun", fontSize=9.5, leading=13),
        "small": ParagraphStyle("small", fontName="Sarabun", fontSize=7.5, leading=9.5, textColor=MUTED),
        "toc1": ParagraphStyle("toc1", fontName="Sarabun-SemiBold", fontSize=11, leading=17, leftIndent=6),
        "toc2": ParagraphStyle("toc2", fontName="Sarabun", fontSize=9.5, leading=14, leftIndent=22, textColor=MUTED),
    }


def _p(text: Any, style: ParagraphStyle, width: float | None = None) -> Paragraph:
    text = "" if text is None else str(text)
    if width:
        lines = wrap(text, max(10.0, width - 6), lambda s: pdfmetrics.stringWidth(s, style.fontName, style.fontSize)) if text else [""]
        return Paragraph("<br/>".join(escape(ln) for ln in lines), style)
    return Paragraph(escape(text), style)


def _table(head: list[str], rows: list[list[Any]], rel: list[float], width: float, st) -> Table:
    widths = [width * w / sum(rel) for w in rel]
    data = [[_p(h, st["head"], w) for h, w in zip(head, widths)]]
    data += [[_p(v, st["cell"], w) for v, w in zip(r, widths)] for r in rows]
    t = Table(data, colWidths=widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE), ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]
    style += [("BACKGROUND", (0, i), (-1, i), ZEBRA) for i in range(2, len(data), 2)]
    t.setStyle(TableStyle(style))
    return t


def _kv(rows: list[tuple[str, str]], width: float, st) -> Table:
    widths = [width * 0.34, width * 0.66]
    t = Table([[_p(k, st["key"], widths[0]), _p(v, st["val"], widths[1])] for k, v in rows], colWidths=widths)
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5)]))
    return t


class _Doc(BaseDocTemplate):
    def afterFlowable(self, flowable) -> None:  # noqa: N802 - reportlab API
        if isinstance(flowable, Paragraph) and flowable.style.name in ("h1", "h2"):
            level = 0 if flowable.style.name == "h1" else 1
            text = flowable.getPlainText()
            key = f"h{id(flowable)}"
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(text, key, level=level, closed=level > 0)
            self.notify("TOCEntry", (level, text, self.page, key))


def _numbered_canvas(ds: Dataset, page_size):
    class NumberedCanvas(Canvas):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._pages: list[dict] = []

        def showPage(self):  # noqa: N802
            self._pages.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._pages)
            for state in self._pages:
                self.__dict__.update(state)
                if self._pageNumber > 1:
                    self.setFont("Sarabun", 7.5)
                    self.setFillColor(MUTED)
                    label = "หน้า" if ds.th else "Page"
                    self.drawRightString(page_size[0] - MARGIN, 7.5 * mm, f"{label} {self._pageNumber} / {total}")
                super().showPage()
            super().save()

    return NumberedCanvas


def _classification(canvas, ds: Dataset, w: float, h: float) -> None:
    cls = ds.spec.classification
    if not cls:
        return
    canvas.saveState()
    canvas.setFont("Sarabun-Bold", 11)
    canvas.setFillColor(RED)
    canvas.drawCentredString(w / 2, h - 5.2 * mm, cls)
    canvas.drawCentredString(w / 2, 3.2 * mm, cls)
    canvas.setFillAlpha(0.06)
    canvas.setFont("Sarabun-Bold", 110)
    canvas.translate(w / 2, h / 2)
    canvas.rotate(30)
    canvas.drawCentredString(0, -30, cls)
    canvas.restoreState()


def _logo(canvas, x: float, y: float, s: float) -> None:
    canvas.saveState()
    canvas.setFillColor(GOLD)
    canvas.roundRect(x, y, s, s, s * 0.27, stroke=0, fill=1)
    canvas.setFillColor(NAVY)
    canvas.roundRect(x + s * 0.22, y + s * 0.2, s * 0.36, s * 0.62, s * 0.08, stroke=0, fill=1)
    canvas.setFillColor(colors.HexColor("#1A3A7A"))
    canvas.roundRect(x + s * 0.27, y + s * 0.3, s * 0.26, s * 0.44, s * 0.03, stroke=0, fill=1)
    canvas.setStrokeColor(NAVY)
    canvas.setLineWidth(s * 0.055)
    canvas.setFillColor(colors.HexColor("#3D6FD1"))
    canvas.circle(x + s * 0.62, y + s * 0.42, s * 0.18, stroke=1, fill=1)
    canvas.line(x + s * 0.75, y + s * 0.29, x + s * 0.88, y + s * 0.16)
    canvas.restoreState()


def build(ds: Dataset, path: Path) -> Path:
    _register_fonts()
    st = _styles()
    page = landscape(A4) if ds.spec.orientation == "landscape" else portrait(A4)
    W, H = page
    width = W - 2 * MARGIN
    case_label = ds.case.get("case_no") or ds.case.get("title") or ""

    def cover(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(NAVY)
        canvas.rect(0, H - 62 * mm, W, 62 * mm, stroke=0, fill=1)
        canvas.setFillColor(GOLD)
        canvas.rect(0, H - 63.2 * mm, W, 1.2 * mm, stroke=0, fill=1)
        _logo(canvas, MARGIN, H - 44 * mm, 24 * mm)
        canvas.setFillColor(colors.white)
        canvas.setFont("Sarabun-Bold", 24 if ds.spec.orientation == "landscape" else 19)
        canvas.drawString(MARGIN + 30 * mm, H - 29 * mm, c.report_title(ds))
        canvas.setFont("Sarabun", 11)
        canvas.setFillColor(colors.HexColor("#F2C14E"))
        canvas.drawString(MARGIN + 30 * mm, H - 37 * mm, f"{APP_NAME} v{__version__}  ·  {c.tr(ds, 'report_id')} {ds.report_id}")
        canvas.setFillColor(MUTED)
        canvas.setFont("Sarabun", 8)
        canvas.drawString(MARGIN, 9 * mm, f"{APP_NAME} v{__version__}")
        canvas.restoreState()
        _classification(canvas, ds, W, H)

    def body(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(NAVY)
        canvas.rect(0, H - 11 * mm, W, 11 * mm, stroke=0, fill=1)
        canvas.setFillColor(GOLD)
        canvas.rect(0, H - 11.7 * mm, W, 0.7 * mm, stroke=0, fill=1)
        canvas.setFont("Sarabun-Bold", 10)
        canvas.setFillColor(colors.white)
        canvas.drawString(MARGIN, H - 7.3 * mm, APP_NAME)
        canvas.setFont("Sarabun", 8.5)
        canvas.drawRightString(W - MARGIN, H - 7.3 * mm, f"{'คดี' if ds.th else 'Case'} {case_label}  ·  {ds.report_id}")
        canvas.setFillColor(MUTED)
        canvas.setFont("Sarabun", 7.5)
        canvas.drawString(MARGIN, 7.5 * mm, c.report_title(ds))
        canvas.restoreState()
        _classification(canvas, ds, W, H)

    enc = None
    if ds.spec.pdf_password:
        perms = dict(canPrint=1, canModify=0, canCopy=0, canAnnotate=0)
        try:  # AES-256 needs the optional pyaes package; otherwise 128-bit
            enc = StandardEncryption(ds.spec.pdf_password, strength=256, **perms)
        except ValueError:
            enc = StandardEncryption(ds.spec.pdf_password, strength=128, **perms)
    doc = _Doc(str(path), pagesize=page, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=17 * mm, bottomMargin=14 * mm,
               title=c.report_title(ds), author=ds.case.get("examiner") or ds.case.get("investigator", ""), subject=case_label, encrypt=enc)
    frame_cover = Frame(MARGIN, 14 * mm, width, H - 82 * mm, id="cover")
    frame_body = Frame(MARGIN, 14 * mm, width, H - 31 * mm, id="body")
    doc.addPageTemplates([PageTemplate("cover", [frame_cover], onPage=cover), PageTemplate("body", [frame_body], onPage=body)])

    story: list[Any] = []
    # ── cover ──
    story.append(Paragraph(escape(c.tr(ds, "case")), ParagraphStyle("ch", parent=st["h2"], fontSize=14)))
    story.append(_kv(c.case_rows(ds), width * (0.62 if ds.spec.orientation == "landscape" else 1), st))
    if any(d.info.get("method") == "demo" for d in ds.devices):
        story.append(Spacer(1, 4 * mm))
        story.append(Paragraph(escape(c.tr(ds, "demo")), ParagraphStyle("demo", parent=st["body"], textColor=GOLD)))
    story.append(NextPageTemplate("body"))
    story.append(PageBreak())
    # ── contents ──
    toc = TableOfContents()
    toc.levelStyles = [st["toc1"], st["toc2"]]
    story.append(Paragraph(escape(c.tr(ds, "toc")), ParagraphStyle("tocTitle", parent=st["h1"])))
    story.append(toc)
    story.append(PageBreak())

    num = 0

    def h1(key: str) -> Paragraph:
        nonlocal num
        num += 1
        return Paragraph(escape(f"{num}. {c.tr(ds, key)}"), st["h1"])

    # ── devices + summary ──
    if ds.has("devices"):
        story.append(h1("devices"))
        for d in ds.devices:
            story.append(KeepTogether([Paragraph(escape(d.label), st["h2"]), _kv(c.device_info_rows(ds, d), width * 0.75, st)]))
    if ds.has("summary"):
        head, rows = c.summary_rows(ds)
        story.append(h1("summary"))
        story.append(_table(head, rows, [1.4] + [1] * len(ds.devices), width, st))
    # ── analysis ──
    analysis = [k for k in ("network", "cross_device", "top_contacts", "bookmarks") if ds.has(k)]
    if analysis and (ds.network_png or ds.cross_device or ds.top_contacts or ds.bookmarks):
        story.append(PageBreak())
        story.append(h1("analysis"))
        if ds.has("network") and ds.network_png and ds.network_png.is_file():
            img = Image(str(ds.network_png))
            ratio = img.imageHeight / float(img.imageWidth or 1)
            max_h = H - 70 * mm
            img.drawWidth = min(width, max_h / ratio)
            img.drawHeight = img.drawWidth * ratio
            story.append(KeepTogether([Paragraph(escape(c.tr(ds, "network")), st["h2"]), img]))
        if ds.has("cross_device") and ds.cross_device:
            head, rows, rel = c.cross_device_table(ds)
            story += [CondPageBreak(35 * mm), Paragraph(escape(c.tr(ds, "cross")), st["h2"])]
            story.append(_table(head, rows, rel, width, st))
        if ds.has("top_contacts") and ds.top_contacts:
            head, rows, rel = c.top_contacts_table(ds)
            story += [CondPageBreak(35 * mm), Paragraph(escape(c.tr(ds, "top")), st["h2"])]
            story.append(_table(head, rows, rel, width, st))
        if ds.has("bookmarks") and ds.bookmarks:
            head, rows, rel = c.bookmark_table(ds)
            story += [CondPageBreak(35 * mm), Paragraph(escape(c.tr(ds, "bookmarks")), st["h2"])]
            story.append(_table(head, rows, rel, width, st))
    # ── records ──
    if ds.has("records"):
        first = True
        for d in ds.devices:
            for kind in ALL_KINDS:
                recs = d.records.get(kind) or []
                if not recs:
                    continue
                story.append(PageBreak())
                if first:
                    story.append(h1("records"))
                    first = False
                label = c.KIND_LABELS[kind][0 if ds.th else 1]
                story += [CondPageBreak(35 * mm), Paragraph(escape(f"{d.label} — {label} ({len(recs):,})"), st["h2"])]
                if kind == "photos" and ds.has("photos") and ds.spec.thumbnails:
                    story += _contact_sheet(ds, d, recs[: min(len(recs), 240)], width, st)
                head, rows, rel = c.kind_table(ds, kind, recs)
                story.append(_table(head, rows, rel, width, st))
                if len(recs) > ds.spec.max_rows:
                    story.append(Paragraph(escape(c.tr(ds, "shown", n=ds.spec.max_rows, total=len(recs))), st["small"]))
    # ── hashes / audit ──
    if ds.has("hashes"):
        head, rows, rel, backup = c.hash_rows(ds)
        story.append(PageBreak())
        story.append(h1("hashes"))
        if backup:
            story.append(Paragraph(escape(c.tr(ds, "backup_files", n=backup)), st["small"]))
        story.append(_table(head, rows, rel, width, st))
    if ds.has("audit"):
        head, rows, rel = c.audit_rows(ds)
        story.append(PageBreak())
        story.append(h1("audit"))
        story.append(_table(head, rows, rel, width, st))
    if ds.has("signature"):
        story.append(PageBreak())
        story.append(h1("signature"))
        story.append(Paragraph(escape(c.tr(ds, "certify")), st["body"]))
        story.append(Spacer(1, 18 * mm))
        for key in ("sign_examiner", "sign_reviewer"):
            name = ds.case.get("examiner") if key == "sign_examiner" else ""
            story.append(Paragraph(escape(c.tr(ds, key)), st["body"]))
            story.append(Paragraph(escape(f"( {name or '................................................'} )"), ParagraphStyle("nm", parent=st["body"], leftIndent=40 * mm)))
            story.append(Paragraph(escape(c.tr(ds, "date_line")), ParagraphStyle("dl", parent=st["body"], leftIndent=40 * mm)))
            story.append(Spacer(1, 14 * mm))

    doc.multiBuild(story, canvasmaker=_numbered_canvas(ds, page))
    return path


def _contact_sheet(ds: Dataset, dev, items: list[dict[str, Any]], width: float, st) -> list[Any]:
    from ..export.labels import fmt_dt

    per_row = 6 if ds.spec.orientation == "landscape" else 4
    cell_w = width / per_row
    img_w = cell_w - 4 * mm
    rows, cells = [], []
    for i, p in enumerate(items, 1):
        parts: list[Any] = []
        thumb = dev.ext_dir / p["thumb"] if p.get("thumb") else None
        if thumb and thumb.is_file():
            try:
                img = Image(str(thumb))
                ratio = img.imageHeight / float(img.imageWidth or 1)
                img.drawWidth = img_w if ratio <= 0.9 else img_w * 0.9 / ratio
                img.drawHeight = img.drawWidth * ratio
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
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    return [t, Spacer(1, 4 * mm)]
