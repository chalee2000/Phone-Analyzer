"""Event timeline across every extraction in a case.

Every timestamped record becomes an event in one of four lanes:

* people     — communications with someone (calls, SMS, chats)
* objects    — things created or used on the device (photos without GPS,
               recordings, notes, web visits, app installs, SIM cards)
* locations  — anything with a place (photos with GPS, Wi-Fi networks,
               CDR calls with a cell site)
* events     — the examiner's own entries (search, arrest, seizure …) and
               the extractions themselves
"""

from __future__ import annotations

from typing import Any

from ..case import workspace
from ..case.store import Case
from .comms import device_label, extractions

DIR = {"in": "incoming", "out": "outgoing"}


def _call(r: dict[str, Any]) -> dict[str, Any]:
    has_cell = r.get("lat") is not None and r.get("lon") is not None
    return {
        "lane": "locations" if has_cell else "people", "kind": "call", "ts": r.get("timestamp"),
        "name": r.get("name") or r.get("number", ""), "number": r.get("number", ""),
        "detail": r.get("site") or r.get("location") or "",
        "extra": {"direction": r.get("direction"), "duration": r.get("duration"), "service": r.get("service"),
                  "cell": r.get("cell"), "lat": r.get("lat"), "lon": r.get("lon")},
    }


def _sms(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "lane": "people", "kind": "sms", "ts": r.get("timestamp"), "name": r.get("contact_name") or r.get("address", ""),
        "number": r.get("address", ""), "detail": r.get("body", ""),
        "extra": {"direction": DIR.get(r.get("direction"), "incoming"), "service": r.get("service")},
    }


def _chat(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "lane": "people", "kind": "chat", "ts": r.get("timestamp"), "name": r.get("thread", ""), "number": "",
        "detail": f"{r.get('sender', '')}: {r.get('body', '')}" if r.get("sender") else r.get("body", ""),
        "extra": {"direction": DIR.get(r.get("direction"), "incoming"), "app": r.get("app")},
    }


def _photo(r: dict[str, Any]) -> dict[str, Any]:
    geo = r.get("lat") is not None
    return {
        "lane": "locations" if geo else "objects", "kind": "photo", "ts": r.get("taken") or r.get("modified"),
        "name": r.get("name", ""), "number": "", "detail": r.get("album", ""),
        "extra": {"thumb": r.get("thumb"), "lat": r.get("lat"), "lon": r.get("lon"), "camera": r.get("camera_model")},
    }


def _web(r: dict[str, Any]) -> dict[str, Any]:
    return {"lane": "objects", "kind": "web", "ts": r.get("timestamp"), "name": r.get("title") or r.get("url", ""),
            "number": "", "detail": r.get("url", ""), "extra": {"browser": r.get("browser")}}


def _note(r: dict[str, Any]) -> dict[str, Any]:
    return {"lane": "objects", "kind": "note", "ts": r.get("modified") or r.get("created"), "name": r.get("title", ""),
            "number": "", "detail": (r.get("body") or "")[:400], "extra": {"folder": r.get("folder")}}


def _voice(r: dict[str, Any]) -> dict[str, Any]:
    return {"lane": "objects", "kind": "voice", "ts": r.get("created"), "name": r.get("title", ""), "number": "",
            "detail": "", "extra": {"duration": r.get("duration"), "path": r.get("path")}}


def _wifi(r: dict[str, Any]) -> dict[str, Any]:
    return {"lane": "locations", "kind": "wifi", "ts": r.get("last_connected"), "name": r.get("ssid", ""), "number": "",
            "detail": r.get("security", ""), "extra": {"bssid": r.get("bssid")}}


def _app(r: dict[str, Any]) -> dict[str, Any]:
    return {"lane": "objects", "kind": "app", "ts": r.get("installed"), "name": r.get("name") or r.get("package", ""),
            "number": "", "detail": r.get("package", ""), "extra": {"version": r.get("version"), "system": r.get("system")}}


def _sim(r: dict[str, Any]) -> dict[str, Any]:
    return {"lane": "objects", "kind": "sim", "ts": r.get("last_seen"), "name": f"{r.get('carrier', '')} {r.get('slot', '')}".strip(),
            "number": r.get("number", ""), "detail": r.get("iccid", ""), "extra": {"active": r.get("active")}}


MAPPERS = {
    "calls": _call, "sms": _sms, "chats": _chat, "photos": _photo, "web": _web,
    "notes": _note, "voice": _voice, "wifi": _wifi, "apps": _app, "sim": _sim,
}


def build(case: Case, ext_ids: list[str] | None = None, include_system_apps: bool = False) -> dict[str, Any]:
    exts = extractions(case, ext_ids)
    marks = workspace.bookmarks(case)
    events: list[dict[str, Any]] = []
    devices = []
    for i, ext in enumerate(exts):
        eid = ext["id"]
        devices.append({"id": eid, "index": i, "label": device_label(ext)})
        for kind, fn in MAPPERS.items():
            for seq, r in enumerate(case.records(eid, kind)):
                if kind == "apps" and r.get("system") and not include_system_apps:
                    continue
                ev = fn(r)
                if not ev.get("ts"):
                    continue
                ev["id"] = f"{eid}:{kind}:{seq}"
                ev["device"] = eid
                events.append(ev)
        for when, what in ((ext.get("started"), "start"), (ext.get("finished"), "finish")):
            ts = _iso_ms(when)
            if ts:
                events.append({
                    "id": f"{eid}:extraction:{what}", "lane": "events", "kind": "extraction", "ts": ts, "device": eid,
                    "name": device_label(ext), "number": "", "detail": f"{ext.get('method', '')} · {what}",
                    "extra": {"stage": what, "status": ext.get("status")},
                })
    for entry in workspace.timeline_entries(case):
        events.append({
            "id": f"man:{entry['id']}", "lane": entry["lane"], "kind": "manual", "ts": entry["ts"], "device": "",
            "name": entry["name"], "number": "", "detail": entry["description"],
            "extra": {"entity_type": entry["entity_type"], "entry_id": entry["id"]}, "manual": True,
        })
    for ev in events:
        if ev["id"] in marks:
            ev["bookmark"] = marks[ev["id"]]
    events.sort(key=lambda e: e["ts"])
    return {"events": events, "devices": devices}


def _iso_ms(value: str | None) -> int | None:
    if not value:
        return None
    from datetime import datetime

    try:
        return int(datetime.fromisoformat(value).timestamp() * 1000)
    except ValueError:
        return None
