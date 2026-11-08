"""Examiner work stored per case: annotations, manual entities and links,
timeline entries, bookmarks and the saved chart layout.

Everything lives in the case's ``case.db`` next to the extracted records and
every change is written to the case audit log (extraction_id = NULL).
"""

from __future__ import annotations

import json
import secrets
from typing import Any

from ..util import iso_now
from .store import Case

SCHEMA = """
CREATE TABLE IF NOT EXISTS annotations(node_id TEXT PRIMARY KEY, label TEXT, note TEXT, tags TEXT, updated TEXT);
CREATE TABLE IF NOT EXISTS manual_entities(id TEXT PRIMARY KEY, type TEXT, label TEXT, note TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS manual_links(id TEXT PRIMARY KEY, source TEXT, target TEXT, label TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS timeline_entries(
    id TEXT PRIMARY KEY, ts INTEGER, lane TEXT, entity_type TEXT, name TEXT, description TEXT,
    created TEXT, updated TEXT
);
CREATE TABLE IF NOT EXISTS bookmarks(event_id TEXT PRIMARY KEY, note TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS layouts(name TEXT PRIMARY KEY, data TEXT, updated TEXT);
"""

ENTITY_TYPES = ("person", "phone", "vehicle", "address", "bank", "organization", "location", "event", "other")
LANES = ("people", "objects", "locations", "events")


def _ensure(case: Case) -> None:
    if getattr(case, "_workspace_ready", False):
        return
    with case._lock:
        case.db.executescript(SCHEMA)
        case.db.commit()
    case._workspace_ready = True  # type: ignore[attr-defined]


def audit(case: Case, action: str, detail: str = "") -> None:
    with case._lock:
        case.db.execute(
            "INSERT INTO audit(extraction_id, ts, action, detail) VALUES(NULL,?,?,?)", (iso_now(), action, detail)
        )
        case.db.commit()


def _rows(case: Case, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    _ensure(case)
    with case._lock:
        return [dict(r) for r in case.db.execute(sql, params).fetchall()]


def _write(case: Case, sql: str, params: tuple = ()) -> None:
    _ensure(case)
    with case._lock:
        case.db.execute(sql, params)
        case.db.commit()


def new_id(prefix: str) -> str:
    return f"{prefix}{secrets.token_hex(5)}"


# ── annotations ─────────────────────────────────────────────────────────
def annotations(case: Case) -> dict[str, dict[str, Any]]:
    out = {}
    for r in _rows(case, "SELECT * FROM annotations"):
        r["tags"] = [t for t in (r.get("tags") or "").split(",") if t]
        out[r["node_id"]] = r
    return out


def set_annotation(case: Case, node_id: str, label: str, note: str, tags: list[str]) -> dict[str, Any]:
    label, note = (label or "").strip(), (note or "").strip()
    tags = [t.strip() for t in tags or [] if t and t.strip()]
    if not label and not note and not tags:
        _write(case, "DELETE FROM annotations WHERE node_id=?", (node_id,))
        audit(case, "annotation.clear", node_id)
        return {}
    _write(
        case,
        "INSERT INTO annotations VALUES(?,?,?,?,?) ON CONFLICT(node_id) DO UPDATE SET "
        "label=excluded.label, note=excluded.note, tags=excluded.tags, updated=excluded.updated",
        (node_id, label, note, ",".join(tags), iso_now()),
    )
    audit(case, "annotation.set", f"{node_id}: {label} | {note} | {','.join(tags)}")
    return {"node_id": node_id, "label": label, "note": note, "tags": tags}


# ── manual entities and links ───────────────────────────────────────────
def manual_entities(case: Case) -> list[dict[str, Any]]:
    return _rows(case, "SELECT * FROM manual_entities ORDER BY created")


def manual_links(case: Case) -> list[dict[str, Any]]:
    return _rows(case, "SELECT * FROM manual_links ORDER BY created")


def add_entity(case: Case, type_: str, label: str, note: str = "") -> dict[str, Any]:
    if type_ not in ENTITY_TYPES:
        type_ = "other"
    ent = {"id": new_id("e"), "type": type_, "label": (label or "").strip() or type_, "note": note or "", "created": iso_now()}
    _write(case, "INSERT INTO manual_entities VALUES(?,?,?,?,?)", tuple(ent.values()))
    audit(case, "entity.add", json.dumps(ent, ensure_ascii=False))
    return ent


def add_link(case: Case, source: str, target: str, label: str = "") -> dict[str, Any]:
    link = {"id": new_id("l"), "source": source, "target": target, "label": label or "", "created": iso_now()}
    _write(case, "INSERT INTO manual_links VALUES(?,?,?,?,?)", tuple(link.values()))
    audit(case, "link.add", json.dumps(link, ensure_ascii=False))
    return link


def delete_manual(case: Case, item_id: str) -> None:
    raw = item_id.split(":", 1)[-1]  # accepts "man:e123" node ids or "mlink:l123" edge ids
    _write(case, "DELETE FROM manual_entities WHERE id=?", (raw,))
    _write(case, "DELETE FROM manual_links WHERE id=? OR source=? OR target=?", (raw, f"man:{raw}", f"man:{raw}"))
    audit(case, "manual.delete", raw)


# ── timeline entries and bookmarks ──────────────────────────────────────
def timeline_entries(case: Case) -> list[dict[str, Any]]:
    return _rows(case, "SELECT * FROM timeline_entries ORDER BY ts")


def save_entry(case: Case, entry: dict[str, Any]) -> dict[str, Any]:
    ts = int(entry.get("ts") or 0)
    if ts <= 0:
        raise ValueError("timestamp required")
    lane = entry.get("lane") if entry.get("lane") in LANES else "events"
    row = {
        "id": entry.get("id") or new_id("t"),
        "ts": ts,
        "lane": lane,
        "entity_type": (entry.get("entity_type") or "").strip(),
        "name": (entry.get("name") or "").strip(),
        "description": (entry.get("description") or "").strip(),
    }
    now = iso_now()
    _write(
        case,
        "INSERT INTO timeline_entries VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET ts=excluded.ts, "
        "lane=excluded.lane, entity_type=excluded.entity_type, name=excluded.name, "
        "description=excluded.description, updated=excluded.updated",
        (row["id"], row["ts"], row["lane"], row["entity_type"], row["name"], row["description"], now, now),
    )
    audit(case, "timeline.save", json.dumps(row, ensure_ascii=False))
    return row


def delete_entry(case: Case, entry_id: str) -> None:
    _write(case, "DELETE FROM timeline_entries WHERE id=?", (entry_id,))
    audit(case, "timeline.delete", entry_id)


def bookmarks(case: Case) -> dict[str, str]:
    return {r["event_id"]: r["note"] or "" for r in _rows(case, "SELECT * FROM bookmarks")}


def set_bookmark(case: Case, event_id: str, on: bool, note: str = "") -> None:
    if on:
        _write(
            case,
            "INSERT INTO bookmarks VALUES(?,?,?) ON CONFLICT(event_id) DO UPDATE SET note=excluded.note",
            (event_id, note or "", iso_now()),
        )
    else:
        _write(case, "DELETE FROM bookmarks WHERE event_id=?", (event_id,))
    audit(case, "bookmark.set" if on else "bookmark.clear", f"{event_id} {note or ''}".strip())


# ── chart layout ────────────────────────────────────────────────────────
def save_layout(case: Case, positions: dict[str, Any], name: str = "default") -> None:
    _write(
        case,
        "INSERT INTO layouts VALUES(?,?,?) ON CONFLICT(name) DO UPDATE SET data=excluded.data, updated=excluded.updated",
        (name, json.dumps(positions), iso_now()),
    )


def load_layout(case: Case, name: str = "default") -> dict[str, Any]:
    rows = _rows(case, "SELECT data FROM layouts WHERE name=?", (name,))
    return json.loads(rows[0]["data"]) if rows else {}
