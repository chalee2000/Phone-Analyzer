"""Collect and filter the data a report needs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from ..analysis import comms, network, timeline
from ..case.store import Case
from ..models import ALL_KINDS
from .spec import ReportSpec

TIME_FIELD = {
    "calls": "timestamp", "sms": "timestamp", "chats": "timestamp", "web": "timestamp", "notes": "modified",
    "voice": "created", "photos": "taken", "wifi": "last_connected", "apps": "installed", "sim": "last_seen",
}


@dataclass
class DeviceData:
    info: dict[str, Any]
    label: str
    ext_dir: Path
    records: dict[str, list[dict[str, Any]]]
    totals: dict[str, int]  # before the date filter
    files: list[dict[str, Any]]
    audit: list[dict[str, Any]]


@dataclass
class Dataset:
    spec: ReportSpec
    case: dict[str, Any]
    devices: list[DeviceData] = field(default_factory=list)
    top_contacts: list[dict[str, Any]] = field(default_factory=list)
    cross_device: list[dict[str, Any]] = field(default_factory=list)
    bookmarks: list[dict[str, Any]] = field(default_factory=list)
    case_audit: list[dict[str, Any]] = field(default_factory=list)
    network_png: Path | None = None
    generated: datetime = field(default_factory=datetime.now)
    report_id: str = ""

    @property
    def th(self) -> bool:
        return self.spec.lang == "th"

    def has(self, section: str) -> bool:
        return section in self.spec.sections

    def device_label(self, ext_id: str) -> str:
        return next((d.label for d in self.devices if d.info["id"] == ext_id), ext_id)


def _in_range(rec: dict[str, Any], kind: str, spec: ReportSpec) -> bool:
    if spec.date_from is None and spec.date_to is None:
        return True
    ts = rec.get(TIME_FIELD.get(kind, "timestamp"))
    if not ts:
        return kind in ("contacts",)  # undated records are kept only for contacts
    return (spec.date_from is None or ts >= spec.date_from) and (spec.date_to is None or ts <= spec.date_to)


def collect(case: Case, spec: ReportSpec, network_png: Path | None = None) -> Dataset:
    ds = Dataset(spec=spec, case=case.meta(), network_png=network_png)
    ds.report_id = f"RPT-{ds.generated:%Y%m%d-%H%M%S}"
    exts = comms.extractions(case, spec.extractions)
    for ext in exts:
        records: dict[str, list[dict[str, Any]]] = {}
        totals: dict[str, int] = {}
        for kind in ALL_KINDS:
            if kind not in spec.kinds:
                continue
            rows = case.records(ext["id"], kind)
            totals[kind] = len(rows)
            rows = [r for r in rows if _in_range(r, kind, spec)]
            key = TIME_FIELD.get(kind)
            if key:
                rows.sort(key=lambda r: r.get(key) or 0, reverse=spec.newest_first)
            records[kind] = rows
        ds.devices.append(DeviceData(
            info=ext, label=comms.device_label(ext), ext_dir=case.path / "extractions" / ext["id"],
            records=records, totals=totals, files=case.files(ext["id"]), audit=case.audit_entries(ext["id"]),
        ))
    ids = [e["id"] for e in exts]
    if spec.sections and ("top_contacts" in spec.sections):
        rows = comms.comm_rows(case, ids)["rows"]
        rows = [r for r in rows if _in_range({"timestamp": r["ts"]}, "calls", spec)]
        ds.top_contacts = [c for c in comms.summarize(rows) if c["kind"] == "phone"][: spec.top_n]
    if "cross_device" in spec.sections and len(ids) > 1:
        g = network.build(case, {"extractions": ids, "date_from": spec.date_from, "date_to": spec.date_to})
        by_id = {n["id"]: n for n in g["nodes"]}
        for pair in g["insights"]["device_pairs"]:
            ds.cross_device.append({
                "a": ds.device_label(pair["a"]), "b": ds.device_label(pair["b"]),
                "shared": [by_id[n] for n in pair["shared"] if n in by_id],
            })
    if "bookmarks" in spec.sections:
        events = timeline.build(case, ids)["events"]
        ds.bookmarks = [e for e in events if e.get("bookmark") is not None]
    if "audit" in spec.sections:
        ds.case_audit = [a for a in case.audit_entries() if not a.get("extraction_id")]
    return ds
