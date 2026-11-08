"""Forensic report as one self-contained HTML file (search + sortable tables)."""

from __future__ import annotations

import base64
import html
from pathlib import Path
from typing import Any

from .. import APP_NAME, __version__
from ..models import ALL_KINDS
from . import common as c
from .dataset import Dataset

CSS = """
:root{--navy:#0f2147;--gold:#d9a42b;--line:#dde4ef;--muted:#5b6b86;--bg:#f3f6fb}
*{box-sizing:border-box}body{margin:0;font-family:"Sarabun","Leelawadee UI","Tahoma",sans-serif;background:var(--bg);color:#0e1a33;font-size:14px}
header{background:var(--navy);color:#fff;padding:22px 32px;border-bottom:4px solid var(--gold)}
header h1{margin:0;font-size:24px}header .sub{color:#f2c14e;margin-top:4px}
.cls{background:#c62828;color:#fff;text-align:center;font-weight:700;padding:4px;letter-spacing:.1em}
main{max-width:1280px;margin:0 auto;padding:20px 24px 60px}
nav{background:#fff;border:1px solid var(--line);border-radius:14px;padding:12px 18px;margin-bottom:18px}
nav a{display:inline-block;margin:3px 14px 3px 0;color:var(--navy);text-decoration:none;font-weight:600}
section{background:#fff;border:1px solid var(--line);border-radius:14px;padding:18px 20px;margin-bottom:18px}
h2{margin:0 0 12px;color:var(--navy);font-size:19px}h3{margin:16px 0 8px;color:var(--navy);font-size:15px}
table{width:100%;border-collapse:collapse;font-size:12.5px}th{background:var(--navy);color:#fff;text-align:left;padding:6px 8px;cursor:pointer;position:sticky;top:0}
td{border-bottom:1px solid var(--line);padding:5px 8px;vertical-align:top}tr:nth-child(even) td{background:#f7f9fd}
.kv td:first-child{width:30%;font-weight:600;color:var(--navy);background:#eef3fc}
.search{width:100%;padding:8px 12px;border:1px solid var(--line);border-radius:10px;margin:4px 0 10px;font:inherit}
.scroll{max-height:560px;overflow:auto;border:1px solid var(--line);border-radius:10px}
.muted{color:var(--muted);font-size:12px}img.chart{max-width:100%;border-radius:10px;border:1px solid var(--line)}
.thumbs{display:flex;flex-wrap:wrap;gap:6px}.thumbs img{width:110px;height:110px;object-fit:cover;border-radius:8px}
footer{color:var(--muted);text-align:center;font-size:12px}
"""

JS = """
document.querySelectorAll('input.search').forEach(inp=>{inp.addEventListener('input',()=>{const q=inp.value.toLowerCase();
document.querySelectorAll('#'+inp.dataset.t+' tbody tr').forEach(tr=>{tr.style.display=tr.textContent.toLowerCase().includes(q)?'':'none'})})});
document.querySelectorAll('th').forEach(th=>th.addEventListener('click',()=>{const tb=th.closest('table').tBodies[0];const i=[...th.parentNode.children].indexOf(th);
const asc=th.dataset.a!=='1';th.dataset.a=asc?'1':'0';[...tb.rows].sort((a,b)=>{const x=a.cells[i].textContent,y=b.cells[i].textContent;
const nx=parseFloat(x.replace(/,/g,'')),ny=parseFloat(y.replace(/,/g,''));const r=(!isNaN(nx)&&!isNaN(ny))?nx-ny:x.localeCompare(y,'th');return asc?r:-r}).forEach(r=>tb.appendChild(r))}));
"""


def _e(v: Any) -> str:
    return html.escape("" if v is None else str(v))


def _table(tid: str, head: list[str], rows: list[list[Any]], ds: Dataset) -> str:
    out = [f'<input class="search" data-t="{tid}" placeholder="{"ค้นหาในตาราง…" if ds.th else "Search table…"}">', f'<div class="scroll"><table id="{tid}"><thead><tr>']
    out += [f"<th>{_e(h)}</th>" for h in head]
    out.append("</tr></thead><tbody>")
    for r in rows:
        out.append("<tr>" + "".join(f"<td>{_e(v)}</td>" for v in r) + "</tr>")
    out.append("</tbody></table></div>")
    return "".join(out)


def _kv(rows: list[tuple[str, str]]) -> str:
    return '<table class="kv">' + "".join(f"<tr><td>{_e(k)}</td><td>{_e(v)}</td></tr>" for k, v in rows) + "</table>"


def build(ds: Dataset, path: Path) -> Path:
    sections: list[tuple[str, str, str]] = []  # (anchor, title, html)
    sections.append(("case", c.tr(ds, "case"), _kv(c.case_rows(ds))))
    if ds.has("devices"):
        body = "".join(f"<h3>{_e(d.label)}</h3>{_kv(c.device_info_rows(ds, d))}" for d in ds.devices)
        sections.append(("devices", c.tr(ds, "devices"), body))
    if ds.has("summary"):
        head, rows = c.summary_rows(ds)
        sections.append(("summary", c.tr(ds, "summary"), _table("t-summary", head, rows, ds)))
    parts = []
    if ds.has("network") and ds.network_png and ds.network_png.is_file():
        b64 = base64.b64encode(ds.network_png.read_bytes()).decode()
        parts.append(f"<h3>{_e(c.tr(ds, 'network'))}</h3><img class='chart' src='data:image/png;base64,{b64}'>")
    if ds.has("cross_device") and ds.cross_device:
        head, rows, _ = c.cross_device_table(ds)
        parts.append(f"<h3>{_e(c.tr(ds, 'cross'))}</h3>" + _table("t-cross", head, rows, ds))
    if ds.has("top_contacts") and ds.top_contacts:
        head, rows, _ = c.top_contacts_table(ds)
        parts.append(f"<h3>{_e(c.tr(ds, 'top'))}</h3>" + _table("t-top", head, rows, ds))
    if ds.has("bookmarks") and ds.bookmarks:
        head, rows, _ = c.bookmark_table(ds)
        parts.append(f"<h3>{_e(c.tr(ds, 'bookmarks'))}</h3>" + _table("t-bm", head, rows, ds))
    if parts:
        sections.append(("analysis", c.tr(ds, "analysis"), "".join(parts)))
    if ds.has("records"):
        li = 0 if ds.th else 1
        body = []
        for di, d in enumerate(ds.devices):
            for kind in ALL_KINDS:
                recs = d.records.get(kind) or []
                if not recs:
                    continue
                body.append(f"<h3>{_e(d.label)} — {_e(c.KIND_LABELS[kind][li])} ({len(recs):,})</h3>")
                if kind == "photos" and ds.has("photos") and ds.spec.thumbnails:
                    thumbs = []
                    for p in recs[:120]:
                        f = d.ext_dir / p["thumb"] if p.get("thumb") else None
                        if f and f.is_file():
                            thumbs.append(f"<img title='{_e(p.get('name'))}' src='data:image/jpeg;base64,{base64.b64encode(f.read_bytes()).decode()}'>")
                    body.append("<div class='thumbs'>" + "".join(thumbs) + "</div>")
                head, rows, _ = c.kind_table(ds, kind, recs)
                body.append(_table(f"t-{di}-{kind}", head, rows, ds))
        sections.append(("records", c.tr(ds, "records"), "".join(body)))
    if ds.has("hashes"):
        head, rows, _, backup = c.hash_rows(ds)
        note = f"<p class='muted'>{_e(c.tr(ds, 'backup_files', n=backup))}</p>" if backup else ""
        sections.append(("hashes", c.tr(ds, "hashes"), note + _table("t-hash", head, rows, ds)))
    if ds.has("audit"):
        head, rows, _ = c.audit_rows(ds)
        sections.append(("audit", c.tr(ds, "audit"), _table("t-audit", head, rows, ds)))

    cls = f"<div class='cls'>{_e(ds.spec.classification)}</div>" if ds.spec.classification else ""
    nav = "".join(f"<a href='#{a}'>{i}. {_e(t)}</a>" for i, (a, t, _) in enumerate(sections, 1))
    body = "".join(f"<section id='{a}'><h2>{i}. {_e(t)}</h2>{h}</section>" for i, (a, t, h) in enumerate(sections, 1))
    page = (
        f"<!doctype html><html lang='{ds.spec.lang}'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{_e(c.report_title(ds))} · {_e(ds.report_id)}</title><style>{CSS}</style></head><body>{cls}"
        f"<header><h1>{_e(c.report_title(ds))}</h1><div class='sub'>{_e(APP_NAME)} v{__version__} · {_e(ds.report_id)} · {_e(c.generated_text(ds))}</div></header>"
        f"<main><nav><b>{_e(c.tr(ds, 'toc'))}</b><br>{nav}</nav>{body}<footer>{_e(APP_NAME)} v{__version__}</footer></main>{cls}<script>{JS}</script></body></html>"
    )
    path.write_text(page, encoding="utf-8")
    return path
