"""Unified view of calls, SMS and chats across every extraction in a case.

Used by the call & contact analysis, the network chart and the timeline so
all three agree on numbers, names and directions.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime
from typing import Any, Iterable

from ..case.store import Case
from ..util import normalize_phone

_DIGITS = re.compile(r"\D")


def is_phone(value: str | None) -> bool:
    """True for real subscriber numbers (not short codes or sender names)."""
    if not value:
        return False
    v = value.strip()
    if not re.fullmatch(r"\+?[\d\s\-()]+", v):
        return False
    return len(_DIGITS.sub("", v)) >= 9


def device_label(info: dict[str, Any]) -> str:
    dev = info.get("device") or {}
    if info.get("method") == "cdr":
        return f"CDR {dev.get('phone_number') or info.get('serial', '')}"
    return dev.get("market_name") or dev.get("model") or info.get("model") or info.get("serial", "")


def extractions(case: Case, ext_ids: Iterable[str] | None = None) -> list[dict[str, Any]]:
    wanted = set(ext_ids) if ext_ids else None
    exts = [e for e in case.list_extractions() if wanted is None or e["id"] in wanted]
    exts.sort(key=lambda e: e["started"] or "")
    return exts


def device_entry(info: dict[str, Any], index: int) -> dict[str, Any]:
    dev = info.get("device") or {}
    return {
        "id": info["id"],
        "index": index,
        "label": device_label(info),
        "number": normalize_phone(dev.get("phone_number", "")),
        "platform": dev.get("platform") or info.get("platform", ""),
        "brand": dev.get("brand", ""),
        "serial": info.get("serial", ""),
        "method": info.get("method", ""),
        "started": info.get("started"),
    }


def own_numbers(case: Case, ext: dict[str, Any]) -> set[str]:
    nums = set()
    phone = normalize_phone((ext.get("device") or {}).get("phone_number", ""))
    if is_phone(phone):
        nums.add(phone)
    for s in case.records(ext["id"], "sim"):
        n = normalize_phone(s.get("number"))
        if is_phone(n):
            nums.add(n)
    return nums


def contact_names(case: Case, ext_id: str) -> dict[str, str]:
    names: dict[str, str] = {}
    for c in case.records(ext_id, "contacts"):
        for p in c.get("phones", []):
            n = normalize_phone(p)
            if n and c.get("name"):
                names.setdefault(n, c["name"])
    return names


_IN = {"in": "incoming", "out": "outgoing"}


def comm_rows(case: Case, ext_ids: Iterable[str] | None = None) -> dict[str, Any]:
    exts = extractions(case, ext_ids)
    devices = [device_entry(e, i) for i, e in enumerate(exts)]
    rows: list[dict[str, Any]] = []
    geo: list[dict[str, Any]] = []
    for ext in exts:
        eid = ext["id"]
        names = contact_names(case, eid)
        saved = set(names)
        for i, r in enumerate(case.records(eid, "calls")):
            number = normalize_phone(r.get("number"))
            rows.append({
                "id": f"{eid}:calls:{i}", "device": eid, "kind": "call", "ts": r.get("timestamp"),
                "dir": r.get("direction") or "unknown", "number": number,
                "name": r.get("name") or names.get(number, ""), "saved": number in saved,
                "duration": r.get("duration") or 0, "service": r.get("service") or "cellular",
                "location": r.get("location") or "", "cell": r.get("cell") or "", "cell_end": r.get("cell_end") or "",
                "site": r.get("site") or "", "lat": r.get("lat"), "lon": r.get("lon"), "azimuth": r.get("azimuth"),
                "body": "",
            })
        for i, r in enumerate(case.records(eid, "sms")):
            number = normalize_phone(r.get("address"))
            rows.append({
                "id": f"{eid}:sms:{i}", "device": eid, "kind": "sms", "ts": r.get("timestamp"),
                "dir": _IN.get(r.get("direction"), "incoming"), "number": number,
                "name": r.get("contact_name") or names.get(number, ""), "saved": number in saved,
                "duration": 0, "service": r.get("service") or "SMS", "body": r.get("body") or "",
                "lat": None, "lon": None, "cell": "", "cell_end": "", "site": "", "location": "", "azimuth": None,
            })
        for i, r in enumerate(case.records(eid, "chats")):
            rows.append({
                "id": f"{eid}:chats:{i}", "device": eid, "kind": "chat", "ts": r.get("timestamp"),
                "dir": _IN.get(r.get("direction"), "incoming"), "number": "",
                "name": r.get("thread") or "", "sender": r.get("sender") or "", "saved": False,
                "duration": 0, "service": r.get("app") or "", "body": r.get("body") or "",
                "lat": None, "lon": None, "cell": "", "cell_end": "", "site": "", "location": "", "azimuth": None,
            })
        for i, p in enumerate(case.records(eid, "photos")):
            if p.get("lat") is not None and p.get("lon") is not None:
                geo.append({
                    "id": f"{eid}:photos:{i}", "device": eid, "kind": "photo", "ts": p.get("taken"),
                    "lat": p["lat"], "lon": p["lon"], "label": p.get("name", ""), "thumb": p.get("thumb", ""),
                })
    rows.sort(key=lambda r: r["ts"] or 0, reverse=True)
    return {"devices": devices, "rows": rows, "geo": geo, "contacts": summarize(rows)}


def party_key(row: dict[str, Any]) -> str:
    if row["kind"] == "chat":
        return f"{row['service']}:{row['name']}"
    return row["number"] or row["name"]


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per counterpart: counts, talk time, first/last contact, devices, night share."""
    acc: dict[str, dict[str, Any]] = {}
    days: dict[str, set] = defaultdict(set)
    for r in rows:
        key = party_key(r)
        if not key:
            continue
        a = acc.get(key)
        if a is None:
            a = acc[key] = {
                "key": key, "number": r["number"], "name": r.get("name") or "", "kind": "chat" if r["kind"] == "chat" else "phone",
                "app": r["service"] if r["kind"] == "chat" else "", "is_phone": is_phone(r["number"]),
                "saved": False, "calls_in": 0, "calls_out": 0, "missed": 0, "sms_in": 0, "sms_out": 0, "chats": 0,
                "duration": 0, "first": None, "last": None, "night": 0, "total": 0, "devices": [],
            }
        if r.get("name") and not a["name"]:
            a["name"] = r["name"]
        a["saved"] = a["saved"] or bool(r.get("saved"))
        if r["kind"] == "call":
            if r["dir"] == "outgoing":
                a["calls_out"] += 1
            elif r["dir"] in ("missed", "rejected", "blocked"):
                a["missed"] += 1
            else:
                a["calls_in"] += 1
            a["duration"] += r.get("duration") or 0
        elif r["kind"] == "sms":
            a["sms_out" if r["dir"] == "outgoing" else "sms_in"] += 1
        else:
            a["chats"] += 1
        a["total"] += 1
        ts = r.get("ts")
        if ts:
            a["first"] = ts if a["first"] is None else min(a["first"], ts)
            a["last"] = ts if a["last"] is None else max(a["last"], ts)
            dt = datetime.fromtimestamp(ts / 1000)
            days[key].add(dt.date())
            if dt.hour >= 22 or dt.hour < 5:
                a["night"] += 1
        if r["device"] not in a["devices"]:
            a["devices"].append(r["device"])
    out = []
    for key, a in acc.items():
        a["active_days"] = len(days[key])
        out.append(a)
    out.sort(key=lambda a: a["total"], reverse=True)
    return out
