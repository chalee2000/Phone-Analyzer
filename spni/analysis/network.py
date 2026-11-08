"""Link chart of everyone and everything the seized devices touched.

Nodes: devices, phone numbers, people (saved contacts), chat rooms, SIM
cards, Wi-Fi networks, photo locations, accounts, organisations and the
examiner's own entities. Phone numbers are merged across devices, so two
phones that called the same number — or each other — become connected.
Metrics (degree, weighted degree, betweenness) and Louvain communities are
computed with networkx.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import networkx as nx

from ..case import workspace
from ..case.store import Case
from ..util import normalize_phone
from .comms import comm_rows, contact_names, device_entry, extractions, is_phone, own_numbers


@dataclass
class NetOptions:
    extractions: list[str] | None = None
    persons: bool = True
    hide_services: bool = True
    contacts_only: bool = False  # saved numbers never contacted
    wifi: bool = True
    locations: bool = True
    accounts: bool = True
    min_weight: int = 1
    date_from: int | None = None
    date_to: int | None = None

    @classmethod
    def parse(cls, raw: dict[str, Any] | None) -> "NetOptions":
        raw = raw or {}
        known = {k: raw[k] for k in cls.__dataclass_fields__ if k in raw}
        return cls(**known)


@dataclass
class Graph:
    nodes: dict[str, dict[str, Any]] = field(default_factory=dict)
    edges: dict[str, dict[str, Any]] = field(default_factory=dict)

    def node(self, nid: str, type_: str, label: str, **props: Any) -> dict[str, Any]:
        n = self.nodes.get(nid)
        if n is None:
            n = self.nodes[nid] = {"id": nid, "type": type_, "label": label, "sub": "", "devices": [], "props": {}}
        if label and (not n["label"] or n["label"] == nid.split(":", 1)[-1]):
            n["label"] = label
        n["props"].update({k: v for k, v in props.items() if v not in (None, "")})
        return n

    def edge(self, src: str, dst: str, type_: str, **stats: Any) -> dict[str, Any]:
        eid = f"{type_}:{src}|{dst}"
        e = self.edges.get(eid)
        if e is None:
            e = self.edges[eid] = {"id": eid, "source": src, "target": dst, "type": type_, "weight": 0, "label": "", "stats": {}}
        for k, v in stats.items():
            if isinstance(v, (int, float)) and k not in ("first", "last"):
                e["stats"][k] = e["stats"].get(k, 0) + v
            elif k == "first" and v:
                e["stats"]["first"] = min(v, e["stats"].get("first") or v)
            elif k == "last" and v:
                e["stats"]["last"] = max(v, e["stats"].get("last") or v)
        return e


def _in_range(ts: int | None, o: NetOptions) -> bool:
    if ts is None:
        return o.date_from is None and o.date_to is None
    return (o.date_from is None or ts >= o.date_from) and (o.date_to is None or ts <= o.date_to)


def build(case: Case, raw_options: dict[str, Any] | None = None) -> dict[str, Any]:
    o = NetOptions.parse(raw_options)
    exts = extractions(case, o.extractions)
    g = Graph()
    data = comm_rows(case, [e["id"] for e in exts])
    devices = data["devices"]

    for ext, dev in zip(exts, devices):
        did = f"dev:{ext['id']}"
        info = ext.get("device") or {}
        g.node(did, "device", dev["label"], number=dev["number"], serial=dev["serial"], platform=dev["platform"],
               brand=info.get("brand", ""), method=ext.get("method", ""), index=dev["index"])
        g.nodes[did]["sub"] = dev["number"] or dev["serial"]
        # The device's own numbers (SIM / examiner-entered) tie it to calls made by other devices.
        for n in own_numbers(case, ext):
            g.node(f"ph:{n}", "phone", n, number=n)
            g.edge(did, f"ph:{n}", "own", weight=1)
        for s in case.records(ext["id"], "sim"):
            if not s.get("iccid"):
                continue
            sid = f"sim:{s['iccid']}"
            g.node(sid, "sim", f"{s.get('carrier') or 'SIM'} {s.get('slot') or ''}".strip(), iccid=s["iccid"], imsi=s.get("imsi"))
            g.edge(did, sid, "sim", weight=1)
            n = normalize_phone(s.get("number"))
            if is_phone(n):
                g.node(f"ph:{n}", "phone", n, number=n)
                g.edge(sid, f"ph:{n}", "number", weight=1)
        if o.accounts:
            for acc in info.get("accounts") or []:
                name = acc.split(" (", 1)[0]
                g.node(f"acc:{name}", "account", name, kind=acc)
                g.edge(did, f"acc:{name}", "account", weight=1)
        if o.wifi:
            for w in case.records(ext["id"], "wifi"):
                if not w.get("ssid"):
                    continue
                wid = f"wifi:{w['ssid']}"
                g.node(wid, "wifi", w["ssid"], security=w.get("security"))
                g.edge(did, wid, "wifi", weight=1, last=w.get("last_connected"))

    # Communications, aggregated per device ↔ counterpart.
    for r in data["rows"]:
        if not _in_range(r.get("ts"), o):
            continue
        did = f"dev:{r['device']}"
        if r["kind"] == "chat":
            cid = f"chat:{r['service']}:{r['name']}"
            g.node(cid, "chat", r["name"], app=r["service"])
            g.edge(did, cid, "chat", weight=1, chats=1, first=r["ts"], last=r["ts"])
            continue
        number = r["number"]
        if not is_phone(number):
            if o.hide_services or not number:
                continue
            nid = f"svc:{number}"
            g.node(nid, "service", number, number=number)
        else:
            nid = f"ph:{number}"
            g.node(nid, "phone", number, number=number)
        if r.get("name"):
            g.nodes[nid]["props"].setdefault("names", [])
            if r["name"] not in g.nodes[nid]["props"]["names"]:
                g.nodes[nid]["props"]["names"].append(r["name"])
        stats: dict[str, Any] = {"weight": 1, "first": r["ts"], "last": r["ts"]}
        if r["kind"] == "call":
            key = {"outgoing": "calls_out", "missed": "missed", "rejected": "missed", "blocked": "missed"}.get(r["dir"], "calls_in")
            stats[key] = 1
            stats["duration"] = r.get("duration") or 0
        else:
            stats["sms_out" if r["dir"] == "outgoing" else "sms_in"] = 1
        g.edge(did, nid, "comm", **stats)

    # People from address books (and numbers saved but never contacted, if asked).
    for ext in exts:
        did = f"dev:{ext['id']}"
        names = contact_names(case, ext["id"])
        for i, c in enumerate(case.records(ext["id"], "contacts")):
            phones = [normalize_phone(p) for p in c.get("phones", [])]
            phones = [p for p in phones if is_phone(p)]
            linked = [p for p in phones if f"ph:{p}" in g.nodes]
            if o.contacts_only:
                for p in phones:
                    if f"ph:{p}" not in g.nodes:
                        g.node(f"ph:{p}", "phone", p, number=p)
                        g.edge(did, f"ph:{p}", "saved", weight=1)
                linked = phones
            if not linked or not o.persons or not c.get("name"):
                continue
            pid = f"per:{ext['id']}:{i}"
            g.node(pid, "person", c["name"], organization=c.get("organization"), account=c.get("account"))
            g.nodes[pid]["devices"].append(ext["id"])
            for p in linked:
                g.edge(pid, f"ph:{p}", "number", weight=1)
            if c.get("organization"):
                oid = f"org:{c['organization']}"
                g.node(oid, "organization", c["organization"])
                g.edge(pid, oid, "member", weight=1)
        for n, name in names.items():
            node = g.nodes.get(f"ph:{n}")
            if node is not None:
                node["props"].setdefault("names", [])
                if name not in node["props"]["names"]:
                    node["props"]["names"].append(name)

    if o.locations:
        for p in data["geo"]:
            if not _in_range(p.get("ts"), o):
                continue
            lat, lon = round(p["lat"], 3), round(p["lon"], 3)
            lid = f"loc:{lat:.3f},{lon:.3f}"
            g.node(lid, "location", f"{lat:.3f}, {lon:.3f}", lat=lat, lon=lon)
            g.edge(f"dev:{p['device']}", lid, "location", weight=1, photos=1, first=p["ts"], last=p["ts"])

    # Examiner's own entities and links.
    for ent in workspace.manual_entities(case):
        nid = f"man:{ent['id']}"
        g.node(nid, ent["type"], ent["label"], note=ent.get("note"))
        g.nodes[nid]["manual"] = True
    for link in workspace.manual_links(case):
        if link["source"] in g.nodes and link["target"] in g.nodes:
            e = g.edge(link["source"], link["target"], "manual", weight=1)
            e["label"] = link["label"]
            e["manual_id"] = link["id"]

    # Weight filter, then drop what became isolated.
    threshold = max(1, int(o.min_weight or 1))
    for eid in [k for k, e in g.edges.items() if e["type"] == "comm" and e["stats"].get("weight", 0) < threshold]:
        del g.edges[eid]
    # Persons/orgs only hang off phone numbers: drop them when their numbers went away.
    _prune(g)

    _finish(g, devices, case)
    return _payload(g, devices, o)


def _prune(g: Graph) -> None:
    while True:
        degree: dict[str, int] = {}
        for e in g.edges.values():
            degree[e["source"]] = degree.get(e["source"], 0) + 1
            degree[e["target"]] = degree.get(e["target"], 0) + 1
        drop = [nid for nid, n in g.nodes.items() if n["type"] != "device" and not n.get("manual") and degree.get(nid, 0) == 0]
        # A phone whose only link is to a person (no communication left) is dropped together with that person.
        dangling = [
            nid for nid, n in g.nodes.items()
            if n["type"] == "person" and all(
                g.nodes[e["target"] if e["source"] == nid else e["source"]]["type"] in ("phone", "organization")
                and degree.get(e["target"] if e["source"] == nid else e["source"], 0) <= 1
                for e in g.edges.values() if nid in (e["source"], e["target"])
            )
        ]
        drop += dangling
        if not drop:
            return
        for nid in set(drop):
            g.nodes.pop(nid, None)
        g.edges = {k: e for k, e in g.edges.items() if e["source"] in g.nodes and e["target"] in g.nodes}


def _finish(g: Graph, devices: list[dict[str, Any]], case: Case) -> None:
    dev_ids = {f"dev:{d['id']}": d["id"] for d in devices}
    for e in g.edges.values():
        s = e["stats"]
        e["weight"] = max(1, int(s.get("weight", 1)))
        for a, b in ((e["source"], e["target"]), (e["target"], e["source"])):
            if a in dev_ids and dev_ids[a] not in g.nodes[b]["devices"]:
                g.nodes[b]["devices"].append(dev_ids[a])
        if e["type"] == "comm":
            parts = []
            calls = s.get("calls_in", 0) + s.get("calls_out", 0) + s.get("missed", 0)
            sms = s.get("sms_in", 0) + s.get("sms_out", 0)
            if calls:
                parts.append(f"{calls} โทร")
            if sms:
                parts.append(f"{sms} SMS")
            e["label"] = " · ".join(parts)
        elif e["type"] == "chat":
            e["label"] = f"{s.get('chats', 0)} ข้อความ"
        elif e["type"] == "location":
            e["label"] = f"{s.get('photos', 0)} รูป"
    # Persons inherit the devices of their numbers.
    for n in g.nodes.values():
        if n["type"] in ("phone",):
            names = n["props"].get("names") or []
            n["sub"] = names[0] if names else ""
    annotations = workspace.annotations(case)
    for nid, ann in annotations.items():
        n = g.nodes.get(nid)
        if not n:
            continue
        if ann.get("label"):
            n["orig_label"] = n["label"]
            n["label"] = ann["label"]
        n["note"] = ann.get("note", "")
        n["tags"] = ann.get("tags", [])

    G = nx.Graph()
    G.add_nodes_from(g.nodes)
    for e in g.edges.values():
        if G.has_edge(e["source"], e["target"]):
            G[e["source"]][e["target"]]["weight"] += e["weight"]
        else:
            G.add_edge(e["source"], e["target"], weight=e["weight"])
    n = G.number_of_nodes()
    if n and G.number_of_edges():
        k = None if n <= 1200 else 400
        btw = nx.betweenness_centrality(G, k=k, normalized=True, seed=42)
        comms = nx.community.louvain_communities(G, weight="weight", seed=42)
    else:
        btw, comms = {}, [{x} for x in G.nodes]
    comms = sorted(comms, key=len, reverse=True)
    community = {node: i for i, members in enumerate(comms) for node in members}
    for nid, node in g.nodes.items():
        node["metrics"] = {
            "degree": G.degree(nid),
            "strength": G.degree(nid, weight="weight"),
            "betweenness": round(btw.get(nid, 0.0), 5),
            "community": community.get(nid, 0),
        }
        node["common"] = len(node["devices"]) >= 2


def _payload(g: Graph, devices: list[dict[str, Any]], o: NetOptions) -> dict[str, Any]:
    nodes = list(g.nodes.values())
    others = [n for n in nodes if n["type"] != "device"]
    by = lambda key: sorted(others, key=lambda n: n["metrics"][key], reverse=True)  # noqa: E731
    communities: dict[int, list[dict[str, Any]]] = {}
    for n in nodes:
        communities.setdefault(n["metrics"]["community"], []).append(n)
    comm_list = []
    for cid, members in sorted(communities.items(), key=lambda kv: -len(kv[1]))[:14]:
        members.sort(key=lambda n: n["metrics"]["strength"], reverse=True)
        comm_list.append({"id": cid, "size": len(members), "members": [m["id"] for m in members[:6]], "lead": members[0]["label"]})
    pairs = []
    for i, a in enumerate(devices):
        for b in devices[i + 1:]:
            shared = [n["id"] for n in others if a["id"] in n["devices"] and b["id"] in n["devices"]]
            pairs.append({"a": a["id"], "b": b["id"], "shared": shared})
    counts: dict[str, int] = {}
    for n in nodes:
        counts[n["type"]] = counts.get(n["type"], 0) + 1
    return {
        "nodes": nodes,
        "edges": list(g.edges.values()),
        "devices": devices,
        "counts": counts,
        "insights": {
            "key_players": [n["id"] for n in by("strength")[:10]],
            "brokers": [n["id"] for n in by("betweenness")[:10] if n["metrics"]["betweenness"] > 0],
            "common": [n["id"] for n in sorted((n for n in others if n["common"]), key=lambda n: -n["metrics"]["strength"])],
            "communities": comm_list,
            "device_pairs": pairs,
        },
        "options": o.__dict__,
    }


def evidence(case: Case, element_id: str, limit: int = 300) -> list[dict[str, Any]]:
    """Records behind a node or an edge, newest first."""
    data = comm_rows(case)
    target = element_id
    device = None
    if element_id.startswith(("comm:", "chat:dev:", "location:")):
        # edge ids: "<type>:<source>|<target>"
        _, rest = element_id.split(":", 1)
        src, dst = rest.split("|", 1)
        device = src[4:] if src.startswith("dev:") else None
        target = dst
    out: list[dict[str, Any]] = []
    if target.startswith(("ph:", "svc:")):
        number = target.split(":", 1)[1]
        out = [r for r in data["rows"] if r["number"] == number and (device is None or r["device"] == device)]
    elif target.startswith("chat:"):
        _, app, thread = target.split(":", 2)
        out = [r for r in data["rows"] if r["kind"] == "chat" and r["service"] == app and r["name"] == thread and (device is None or r["device"] == device)]
    elif target.startswith("loc:"):
        lat, lon = (float(x) for x in target[4:].split(","))
        out = [
            {**p, "kind": "photo"} for p in data["geo"]
            if round(p["lat"], 3) == lat and round(p["lon"], 3) == lon and (device is None or p["device"] == device)
        ]
    out.sort(key=lambda r: r.get("ts") or 0, reverse=True)
    return out[:limit]


def to_networkx(graph: dict[str, Any]) -> nx.Graph:
    G = nx.Graph()
    for n in graph["nodes"]:
        G.add_node(
            n["id"], label=n["label"], type=n["type"], devices=",".join(n["devices"]),
            degree=n["metrics"]["degree"], strength=n["metrics"]["strength"],
            betweenness=n["metrics"]["betweenness"], community=n["metrics"]["community"],
            note=n.get("note", ""),
        )
    for e in graph["edges"]:
        s = e["stats"]
        G.add_edge(
            e["source"], e["target"], type=e["type"], weight=e["weight"], label=e.get("label", ""),
            calls_in=s.get("calls_in", 0), calls_out=s.get("calls_out", 0), missed=s.get("missed", 0),
            sms_in=s.get("sms_in", 0), sms_out=s.get("sms_out", 0), duration=s.get("duration", 0),
        )
    return G


__all__ = ["NetOptions", "build", "evidence", "to_networkx", "device_entry"]
