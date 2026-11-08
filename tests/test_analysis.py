"""Network, timeline, call analysis and CDR import over a two-device demo case."""

import base64
import time
from xml.etree import ElementTree as ET

import networkx as nx
import pytest
from openpyxl import load_workbook

from spni.api import Api
from spni.cdr import demo_cdr_bytes, parse
from spni.demo import DEMO_ANDROID_NUMBER, DEMO_IOS_NUMBER, SHARED_PEOPLE, cdr_partners
from spni.events import EventBus


def extract(api: Api, device: str) -> None:
    assert api.connect(device)["ok"]
    assert api.start_extraction({})["ok"]
    for _ in range(400):
        if not api.state()["data"]["running"]:
            return
        time.sleep(0.05)
    raise AssertionError("extraction did not finish")


@pytest.fixture(scope="module")
def api(tmp_path_factory):
    api = Api(EventBus(), tmp_path_factory.mktemp("cases"), demo=True)
    assert api.create_case({"case_no": "77/2569", "title": "เครือข่ายทดสอบ"})["ok"]
    extract(api, "demo:android")
    extract(api, "demo:ios")
    return api


def test_network_links_both_devices(api):
    g = api.network_graph({})["data"]
    devices = [n for n in g["nodes"] if n["type"] == "device"]
    assert len(devices) == 2
    ids = {n["id"] for n in g["nodes"]}
    for _, _, number in SHARED_PEOPLE:
        assert f"ph:{number}" in ids
    common = set(g["insights"]["common"])
    assert {f"ph:{n}" for _, _, n in SHARED_PEOPLE} <= common
    # Each phone holds the other's number: device A ↔ number of B ↔ own-number edge of B.
    G = nx.Graph([(e["source"], e["target"]) for e in g["edges"]])
    a, b = (d["id"] for d in devices)
    assert nx.has_path(G, a, b)
    assert G.has_edge(a, f"ph:{DEMO_IOS_NUMBER}") or G.has_edge(b, f"ph:{DEMO_IOS_NUMBER}")
    pair = g["insights"]["device_pairs"][0]
    assert len(pair["shared"]) >= len(SHARED_PEOPLE)
    assert any(n["type"] == "wifi" and n["common"] for n in g["nodes"])
    assert all("betweenness" in n["metrics"] for n in g["nodes"])
    assert g["insights"]["communities"]


def test_network_filters_and_annotations(api):
    full = api.network_graph({})["data"]
    strict = api.network_graph({"min_weight": 8, "persons": False, "wifi": False, "locations": False})["data"]
    assert len(strict["nodes"]) < len(full["nodes"])
    assert not any(n["type"] in ("person", "wifi", "location") for n in strict["nodes"])
    node = f"ph:{SHARED_PEOPLE[0][2]}"
    assert api.network_annotate(node, "นาย ก. (ผู้ต้องสงสัย)", "เบอร์ติดต่อหลัก", ["เป้าหมาย"])["ok"]
    ent = api.network_add_entity({"type": "vehicle", "label": "กข 1234 กทม.", "note": "จากกล้อง LPR"}, [node], "ใช้รถ")["data"]
    g = api.network_graph({})["data"]
    by_id = {n["id"]: n for n in g["nodes"]}
    assert by_id[node]["label"] == "นาย ก. (ผู้ต้องสงสัย)" and by_id[node]["tags"] == ["เป้าหมาย"]
    assert by_id[ent["node_id"]]["type"] == "vehicle"
    assert any(e["type"] == "manual" and e["label"] == "ใช้รถ" for e in g["edges"])
    ev = api.network_evidence(f"comm:{[n for n in g['nodes'] if n['type'] == 'device'][0]['id']}|{node}")["data"]
    assert ev and all(r["number"] == SHARED_PEOPLE[0][2] for r in ev)
    assert api.network_delete_manual(ent["node_id"])["ok"]
    assert ent["node_id"] not in {n["id"] for n in api.network_graph({})["data"]["nodes"]}


def test_network_exports(api, tmp_path):
    anx = api.export_network("anx", {})["data"]["path"]
    root = ET.parse(anx).getroot()
    items = root.find("ChartItemCollection")
    assert root.tag == "Chart" and len(items.findall("ChartItem/End")) > 10 and items.findall("ChartItem/Link")
    gml = api.export_network("graphml", {})["data"]["path"]
    assert nx.read_graphml(gml).number_of_nodes() > 10
    xlsx = api.export_network("xlsx", {})["data"]["path"]
    assert load_workbook(xlsx).sheetnames == ["เอนทิตี", "ลิงก์", "i2 Import"]
    png = api.save_chart_image("data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\nfake").decode())["data"]
    assert png["name"].endswith(".png")


def test_timeline(api):
    data = api.timeline({})["data"]
    events = data["events"]
    assert len(data["devices"]) == 2
    assert [e["ts"] for e in events] == sorted(e["ts"] for e in events)
    lanes = {e["lane"] for e in events}
    assert lanes == {"people", "objects", "locations", "events"}
    assert any(e["kind"] == "photo" and e["lane"] == "locations" for e in events)
    saved = api.timeline_save_entry({"ts": events[10]["ts"] + 1, "lane": "events", "entity_type": "การจับกุม",
                                     "name": "จับกุมผู้ต้องหา", "description": "หน้าคอนโด"})["data"]
    assert api.timeline_bookmark(events[5]["id"], True, "สำคัญ")["ok"]
    again = api.timeline({})["data"]["events"]
    assert any(e["kind"] == "manual" and e["name"] == "จับกุมผู้ต้องหา" for e in again)
    assert next(e for e in again if e["id"] == events[5]["id"])["bookmark"] == "สำคัญ"
    ids = [e["id"] for e in again[:50]]
    x = api.export_timeline("xlsx", ids)["data"]["path"]
    assert load_workbook(x)["ไทม์ไลน์"].max_row == 51
    pdf = api.export_timeline("pdf", ids)["data"]["path"]
    assert open(pdf, "rb").read(5) == b"%PDF-"
    assert api.timeline_delete_entry(saved["id"])["ok"]


def test_cdr_parse_and_import(api):
    raw = demo_cdr_bytes(DEMO_ANDROID_NUMBER, cdr_partners(), n=120)
    parsed = parse("x.csv", raw)
    assert parsed["target"] == DEMO_ANDROID_NUMBER and parsed["calls"] and parsed["sms"]
    c = parsed["calls"][0]
    assert c.lat and c.lon and c.cell and c.azimuth is not None and 2020 < time.gmtime(c.timestamp / 1000).tm_year < 2100
    res = api.import_demo_cdr()["data"]
    assert res["target"] == DEMO_ANDROID_NUMBER and res["counts"]["calls"] > 100
    comms = api.comm_analysis({})["data"]
    assert len(comms["devices"]) == 3
    assert any(r["cell"] and r["lat"] for r in comms["rows"])
    top = comms["contacts"][0]
    assert top["total"] >= comms["contacts"][-1]["total"]
    out = api.export_comms([r["id"] for r in comms["rows"][:30]])["data"]["path"]
    assert load_workbook(out).sheetnames == ["ผลการค้นหา", "สรุปรายเบอร์"]


def test_cdr_rejects_unknown_columns(api):
    bad = base64.b64encode("foo,bar\n1,2\n".encode()).decode()
    assert api.import_cdr("bad.csv", bad)["error"] == "cdr_columns_not_found"
