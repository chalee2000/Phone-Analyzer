"""Exports for the analysis views: network (i2 ANX, GraphML, Excel),
timeline (Excel, PDF) and call/contact query results (Excel)."""

from __future__ import annotations

import base64
import math
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from openpyxl import Workbook
from openpyxl.utils import get_column_letter

from .. import APP_NAME, __version__
from . import report_name
from .excel import _table
from .labels import fmt_dt, fmt_duration

I2_ICONS = {
    "device": "Mobile Phone", "phone": "Telephone", "person": "Person", "chat": "Communication", "account": "Email",
    "sim": "SIM Card", "wifi": "Wireless", "location": "Location", "organization": "Organisation", "service": "Telephone",
    "vehicle": "Vehicle", "address": "Address", "bank": "Bank Account", "event": "Event", "other": "Entity",
}
TYPE_TH = {
    "device": "เครื่องของกลาง", "phone": "หมายเลขโทรศัพท์", "person": "บุคคล", "chat": "ห้องแชต", "account": "บัญชี",
    "sim": "ซิมการ์ด", "wifi": "Wi-Fi", "location": "สถานที่", "organization": "องค์กร", "service": "เลขหมายบริการ",
    "vehicle": "ยานพาหนะ", "address": "ที่อยู่", "bank": "บัญชีธนาคาร", "event": "เหตุการณ์", "other": "อื่น ๆ",
}
EDGE_TH = {
    "comm": "ติดต่อสื่อสาร", "chat": "แชต", "own": "เบอร์ของเครื่อง", "sim": "ใช้ซิม", "number": "หมายเลข",
    "account": "บัญชีบนเครื่อง", "wifi": "เชื่อมต่อ Wi-Fi", "location": "ถ่ายรูปที่", "member": "สังกัด",
    "saved": "บันทึกในรายชื่อ", "manual": "เชื่อมโยง (ผู้ตรวจ)",
}


def _spread(graph: dict[str, Any]) -> dict[str, tuple[float, float]]:
    """Fallback coordinates when the UI did not send a layout: devices in the
    middle, every community on its own ring sector (no numpy needed)."""
    pos: dict[str, tuple[float, float]] = {}
    devices = [n for n in graph["nodes"] if n["type"] == "device"]
    for i, n in enumerate(devices):
        pos[n["id"]] = (i * 900.0, 0.0)
    others = sorted((n for n in graph["nodes"] if n["type"] != "device"),
                    key=lambda n: (n["metrics"]["community"], -n["metrics"]["strength"]))
    total = max(1, len(others))
    for i, n in enumerate(others):
        angle = 2 * math.pi * i / total
        radius = 1400 + 260 * (i % 4)
        pos[n["id"]] = (radius * math.cos(angle) + 450 * (len(devices) - 1), radius * math.sin(angle))
    return pos


def network_anx(graph: dict[str, Any], path: Path, positions: dict[str, Any] | None = None) -> Path:
    """i2 Analyst's Notebook Exchange (ANX) chart."""
    pos = {k: (v["x"] * 4, v["y"] * 4) for k, v in (positions or {}).items() if isinstance(v, dict)} or _spread(graph)
    chart = ET.Element("Chart", IdReferenceLinking="true", Rigorous="false")
    etypes = ET.SubElement(chart, "EntityTypeCollection")
    for t in sorted({n["type"] for n in graph["nodes"]}):
        ET.SubElement(etypes, "EntityType", Name=TYPE_TH.get(t, t), IconFile=I2_ICONS.get(t, "Entity"))
    ltypes = ET.SubElement(chart, "LinkTypeCollection")
    for t in sorted({e["type"] for e in graph["edges"]}):
        ET.SubElement(ltypes, "LinkType", Name=EDGE_TH.get(t, t), Colour="0")
    items = ET.SubElement(chart, "ChartItemCollection")
    ids = {}
    for i, n in enumerate(graph["nodes"]):
        ids[n["id"]] = f"E{i}"
        x, y = pos.get(n["id"], (i * 120.0, 0.0))
        desc = n.get("note") or n.get("sub") or ""
        item = ET.SubElement(items, "ChartItem", Label=n["label"], XPosition=str(int(x)), Description=desc)
        end = ET.SubElement(item, "End", Y=str(int(y)))
        ent = ET.SubElement(end, "Entity", EntityId=ids[n["id"]], Identity=n["id"])
        icon = ET.SubElement(ent, "Icon")
        ET.SubElement(icon, "IconStyle", Type=TYPE_TH.get(n["type"], n["type"]))
    for e in graph["edges"]:
        if e["source"] not in ids or e["target"] not in ids:
            continue
        label = e.get("label") or EDGE_TH.get(e["type"], e["type"])
        item = ET.SubElement(items, "ChartItem", Label=label)
        link = ET.SubElement(item, "Link", End1Id=ids[e["source"]], End2Id=ids[e["target"]])
        ET.SubElement(link, "LinkStyle", Type=EDGE_TH.get(e["type"], e["type"]), ArrowStyle="ArrowNone",
                      LineWidth=str(min(8, 1 + int(math.log2(max(1, e["weight"]))))))
    ET.indent(chart)
    path.write_bytes(b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(chart, encoding="utf-8"))
    return path


def network_graphml(graph: dict[str, Any], path: Path) -> Path:
    import networkx as nx

    from ..analysis.network import to_networkx

    nx.write_graphml(to_networkx(graph), path)
    return path


def network_xlsx(graph: dict[str, Any], path: Path, devices: dict[str, str]) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "เอนทิตี"
    rows = []
    for n in sorted(graph["nodes"], key=lambda n: -n["metrics"]["strength"]):
        m = n["metrics"]
        rows.append([n["label"], TYPE_TH.get(n["type"], n["type"]), n["props"].get("number", ""),
                     ", ".join((n["props"].get("names") or [])[:3]), ", ".join(devices.get(d, d) for d in n["devices"]),
                     m["degree"], m["strength"], m["betweenness"], m["community"] + 1, n.get("note", ""), n["id"]])
    _table(ws, 1, ["ชื่อ/ป้าย", "ประเภท", "หมายเลข", "ชื่อในรายชื่อ", "พบในเครื่อง", "จำนวนการเชื่อมโยง", "น้ำหนักรวม",
                   "Betweenness", "กลุ่ม", "หมายเหตุผู้ตรวจ", "รหัส"], rows, [26, 16, 14, 26, 30, 12, 12, 12, 8, 30, 30])
    ws.freeze_panes = "A2"
    labels = {n["id"]: n["label"] for n in graph["nodes"]}
    types = {n["id"]: n["type"] for n in graph["nodes"]}
    ls = wb.create_sheet("ลิงก์")
    lrows = []
    for e in sorted(graph["edges"], key=lambda e: -e["weight"]):
        s = e["stats"]
        lrows.append([labels.get(e["source"]), labels.get(e["target"]), EDGE_TH.get(e["type"], e["type"]), e["weight"],
                      s.get("calls_out", 0), s.get("calls_in", 0), s.get("missed", 0), s.get("sms_out", 0), s.get("sms_in", 0),
                      s.get("chats", 0), fmt_duration(s.get("duration", 0)), fmt_dt(s.get("first")), fmt_dt(s.get("last"))])
    _table(ls, 1, ["ต้นทาง", "ปลายทาง", "ประเภทลิงก์", "น้ำหนัก", "โทรออก", "โทรเข้า", "ไม่ได้รับ", "SMS ส่ง", "SMS รับ", "แชต",
                   "เวลาสนทนา", "ครั้งแรก", "ครั้งล่าสุด"], lrows, [26, 26, 16, 9, 8, 8, 8, 8, 8, 8, 11, 19, 19])
    ls.freeze_panes = "A2"
    i2 = wb.create_sheet("i2 Import")
    irows = [[labels.get(e["source"]), TYPE_TH.get(types.get(e["source"], ""), ""), labels.get(e["target"]),
              TYPE_TH.get(types.get(e["target"], ""), ""), e.get("label") or EDGE_TH.get(e["type"], e["type"]), e["weight"]]
             for e in graph["edges"]]
    _table(i2, 1, ["Entity1", "Type1", "Entity2", "Type2", "Link", "Count"], irows, [26, 18, 26, 18, 22, 8])
    wb.save(path)
    return path


def export_network(fmt: str, graph: dict[str, Any], case: dict[str, Any], out_dir: Path, positions: dict[str, Any] | None) -> Path:
    devices = {d["id"]: d["label"] for d in graph["devices"]}
    meta = {"model": "Network", "serial": ""}
    if fmt == "anx":
        return network_anx(graph, out_dir / report_name(case, meta, "i2", ".anx"), positions)
    if fmt == "graphml":
        return network_graphml(graph, out_dir / report_name(case, meta, "Graph", ".graphml"))
    if fmt == "xlsx":
        return network_xlsx(graph, out_dir / report_name(case, meta, "Network", ".xlsx"), devices)
    raise ValueError(fmt)


def save_png(data_url: str, case: dict[str, Any], out_dir: Path, label: str) -> Path:
    raw = data_url.split(",", 1)[1] if "," in data_url else data_url
    path = out_dir / report_name(case, {"model": label, "serial": ""}, "Chart", ".png")
    path.write_bytes(base64.b64decode(raw))
    return path


# ── timeline ────────────────────────────────────────────────────────────
LANE_TH = {"people": "บุคคล", "objects": "วัตถุ", "locations": "สถานที่", "events": "เหตุการณ์"}
KIND_TH = {"call": "การโทร", "sms": "SMS", "chat": "แชต", "photo": "รูปภาพ", "web": "เว็บ", "note": "บันทึก", "voice": "บันทึกเสียง",
           "wifi": "Wi-Fi", "app": "ติดตั้งแอป", "sim": "ซิม", "extraction": "การสกัดข้อมูล", "manual": "บันทึกผู้ตรวจ"}


def _elapsed(ms: int) -> str:
    s = max(0, ms // 1000)
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    return f"+{d:02d}.{h:02d}:{m:02d}:{s:02d}"


def _timeline_rows(events: list[dict[str, Any]], devices: dict[str, str]) -> list[list[Any]]:
    start = events[0]["ts"] if events else 0
    rows = []
    for e in events:
        kind = e["extra"].get("entity_type") if e["kind"] == "manual" and e["extra"].get("entity_type") else KIND_TH.get(e["kind"], e["kind"])
        rows.append([fmt_dt(e["ts"]), _elapsed(e["ts"] - start), LANE_TH.get(e["lane"], e["lane"]), kind, e["name"],
                     e.get("number", ""), e.get("detail", ""), devices.get(e.get("device", ""), "ผู้ตรวจ"),
                     "★ " + e["bookmark"] if e.get("bookmark") is not None else ""])
    return rows


HEAD = ["วันเวลา", "เวลาที่ผ่านไป", "ช่อง", "ประเภท", "ชื่อ", "หมายเลข", "รายละเอียด", "เครื่อง", "ทำเครื่องหมาย"]


def export_timeline(fmt: str, events: list[dict[str, Any]], devices: dict[str, str], case: dict[str, Any], out_dir: Path) -> Path:
    meta = {"model": "Timeline", "serial": ""}
    rows = _timeline_rows(events, devices)
    if fmt == "xlsx":
        wb = Workbook()
        ws = wb.active
        ws.title = "ไทม์ไลน์"
        _table(ws, 1, HEAD, rows, [19, 14, 10, 14, 26, 14, 60, 20, 18])
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = f"A1:{get_column_letter(len(HEAD))}{len(rows) + 1}"
        path = out_dir / report_name(case, meta, "Timeline", ".xlsx")
        wb.save(path)
        return path
    if fmt == "pdf":
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

        from .pdf import MARGIN, PAGE, _register_fonts, _styles, _table as pdf_table

        _register_fonts()
        st = _styles()
        path = out_dir / report_name(case, meta, "Timeline", ".pdf")
        doc = SimpleDocTemplate(str(path), pagesize=PAGE, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN, bottomMargin=MARGIN,
                                title=f"{APP_NAME} Timeline")
        story = [Paragraph("ไทม์ไลน์เหตุการณ์", st["title"]),
                 Paragraph(f"คดี {case.get('case_no') or case.get('title') or ''} · {len(rows):,} รายการ · {APP_NAME} v{__version__}", st["subtitle"]),
                 Spacer(1, 10)]
        story.append(pdf_table(HEAD[:8], [r[:8] for r in rows[:5000]], [1.1, 0.9, 0.6, 0.8, 1.3, 0.9, 3.0, 1.0], st))
        doc.build(story)
        return path
    raise ValueError(fmt)


# ── call & contact query results ────────────────────────────────────────
DIR_TH = {"incoming": "เข้า", "outgoing": "ออก", "missed": "ไม่ได้รับ", "rejected": "ปฏิเสธ", "blocked": "บล็อก", "unknown": ""}


def export_comms(rows: list[dict[str, Any]], contacts: list[dict[str, Any]], devices: dict[str, str], case: dict[str, Any], out_dir: Path) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "ผลการค้นหา"
    data = [[i, devices.get(r["device"], r["device"]), fmt_dt(r["ts"]), {"call": "โทร", "sms": "SMS", "chat": "แชต"}.get(r["kind"], r["kind"]),
             DIR_TH.get(r["dir"], r["dir"]), r.get("number", ""), r.get("name", ""), fmt_duration(r.get("duration", 0)) if r["kind"] == "call" else "",
             r.get("cell", ""), r.get("site", ""), r.get("lat") or "", r.get("lon") or "", r.get("body", "")]
            for i, r in enumerate(rows, 1)]
    _table(ws, 1, ["#", "เครื่อง/เป้าหมาย", "วันเวลา", "ประเภท", "ทิศทาง", "หมายเลข", "ชื่อ", "ระยะเวลา", "เสา (Cell)", "ชื่อเสา",
                   "ละติจูด", "ลองจิจูด", "ข้อความ"], data, [6, 22, 19, 8, 10, 14, 22, 10, 18, 20, 11, 11, 50])
    ws.freeze_panes = "A2"
    cs = wb.create_sheet("สรุปรายเบอร์")
    cdata = [[c.get("name", ""), c.get("number") or c["key"], c["total"], c["calls_out"], c["calls_in"], c["missed"], c["sms_out"],
              c["sms_in"], c["chats"], fmt_duration(c["duration"]), c["active_days"], c["night"], fmt_dt(c["first"]), fmt_dt(c["last"]),
              ", ".join(devices.get(d, d) for d in c["devices"])] for c in contacts]
    _table(cs, 1, ["ชื่อ", "หมายเลข", "รวม", "โทรออก", "โทรเข้า", "ไม่ได้รับ", "SMS ส่ง", "SMS รับ", "แชต", "เวลาสนทนา", "จำนวนวัน",
                   "กลางคืน", "ครั้งแรก", "ครั้งล่าสุด", "เครื่อง"], cdata, [22, 14, 8, 8, 8, 8, 8, 8, 8, 11, 9, 9, 19, 19, 26])
    cs.freeze_panes = "A2"
    path = out_dir / report_name(case, {"model": "Calls", "serial": ""}, "Contacts", ".xlsx")
    wb.save(path)
    return path
