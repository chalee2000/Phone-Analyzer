"""Case storage: one folder per case, one SQLite database per case.

Layout::

    <cases root>/<case id>/
        case.db                       # metadata, records, file hashes, audit log
        extractions/<extraction id>/
            raw/                      # untouched files pulled from the device
            media/                    # photos, voice memos …
            thumbs/                   # generated previews (not evidence)
            manifest.json             # SHA-256 of every acquired file
            audit.log                 # human-readable mirror of the audit table
        reports/                      # Excel / PDF / Word exports
"""

from __future__ import annotations

import json
import os
import secrets
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .. import APP_NAME, __version__
from ..util import iso_now, safe_name, sha256_file

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS extractions(
    id TEXT PRIMARY KEY, started TEXT, finished TEXT, status TEXT,
    platform TEXT, serial TEXT, model TEXT, method TEXT,
    device_json TEXT, unavailable_json TEXT DEFAULT '{}', summary_json TEXT DEFAULT '{}',
    examiner TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS records(extraction_id TEXT, kind TEXT, seq INTEGER, data TEXT);
CREATE INDEX IF NOT EXISTS idx_records ON records(extraction_id, kind, seq);
CREATE TABLE IF NOT EXISTS files(
    extraction_id TEXT, rel_path TEXT, source TEXT, size INTEGER, sha256 TEXT, acquired TEXT
);
CREATE TABLE IF NOT EXISTS audit(
    id INTEGER PRIMARY KEY AUTOINCREMENT, extraction_id TEXT, ts TEXT, action TEXT, detail TEXT
);
"""

CASE_FIELDS = (
    "case_no", "title", "investigator", "unit", "note",
    # Forensic report details (filled in the report wizard and remembered per case)
    "examiner", "evidence_no", "location", "department", "organization", "crime_type",
)


def default_cases_root() -> Path:
    env = os.environ.get("SPNI_CASES_DIR")
    if env:
        return Path(env)
    docs = Path.home() / "Documents"
    return (docs if docs.is_dir() else Path.home()) / "Phone Analysis Cases"


class Case:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.id = path.name
        self._lock = threading.RLock()
        self.db = sqlite3.connect(path / "case.db", check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        with self._lock:
            self.db.executescript(SCHEMA)
            self.db.commit()

    # ── metadata ────────────────────────────────────────────────────────
    def meta(self) -> dict[str, Any]:
        with self._lock:
            rows = self.db.execute("SELECT key, value FROM meta").fetchall()
            n = self.db.execute("SELECT COUNT(*) FROM extractions").fetchone()[0]
        data = {r["key"]: r["value"] for r in rows}
        data["id"] = self.id
        data["path"] = str(self.path)
        data["extraction_count"] = n
        return data

    def set_meta(self, values: dict[str, Any]) -> None:
        with self._lock:
            for key, value in values.items():
                self.db.execute(
                    "INSERT INTO meta(key, value) VALUES(?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (key, "" if value is None else str(value)),
                )
            self.db.commit()

    # ── extractions ─────────────────────────────────────────────────────
    def create_extraction(self, device: dict[str, Any], method: str, examiner: str = "") -> "Extraction":
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        base = f"{stamp}_{safe_name(device.get('serial') or 'device')[:24]}"
        ext_id, n = base, 1
        while (self.path / "extractions" / ext_id).exists():  # same source twice within a second
            n += 1
            ext_id = f"{base}-{n}"
        folder = self.path / "extractions" / ext_id
        for sub in ("raw", "media", "thumbs"):
            (folder / sub).mkdir(parents=True, exist_ok=True)
        with self._lock:
            self.db.execute(
                "INSERT INTO extractions(id, started, status, platform, serial, model, method, device_json, examiner)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    ext_id,
                    iso_now(),
                    "running",
                    device.get("platform", ""),
                    device.get("serial", ""),
                    device.get("market_name") or device.get("model", ""),
                    method,
                    json.dumps(device, ensure_ascii=False),
                    examiner,
                ),
            )
            self.db.commit()
        ext = Extraction(self, ext_id, folder)
        ext.audit("extraction.start", f"{APP_NAME} v{__version__}; method={method}")
        return ext

    def get_extraction(self, ext_id: str) -> "Extraction":
        folder = self.path / "extractions" / ext_id
        with self._lock:
            row = self.db.execute("SELECT id FROM extractions WHERE id=?", (ext_id,)).fetchone()
        if not row:
            raise KeyError(ext_id)
        return Extraction(self, ext_id, folder)

    def list_extractions(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.db.execute("SELECT * FROM extractions ORDER BY started DESC").fetchall()
        return [self._extraction_row(r) for r in rows]

    def extraction_info(self, ext_id: str) -> dict[str, Any]:
        with self._lock:
            row = self.db.execute("SELECT * FROM extractions WHERE id=?", (ext_id,)).fetchone()
        if not row:
            raise KeyError(ext_id)
        return self._extraction_row(row)

    def _extraction_row(self, r: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": r["id"],
            "case_id": self.id,
            "started": r["started"],
            "finished": r["finished"],
            "status": r["status"],
            "platform": r["platform"],
            "serial": r["serial"],
            "model": r["model"],
            "method": r["method"],
            "examiner": r["examiner"],
            "device": json.loads(r["device_json"] or "{}"),
            "unavailable": json.loads(r["unavailable_json"] or "{}"),
            "summary": json.loads(r["summary_json"] or "{}"),
        }

    def records(self, ext_id: str, kind: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.db.execute(
                "SELECT data FROM records WHERE extraction_id=? AND kind=? ORDER BY seq", (ext_id, kind)
            ).fetchall()
        return [json.loads(r["data"]) for r in rows]

    def counts(self, ext_id: str) -> dict[str, int]:
        with self._lock:
            rows = self.db.execute(
                "SELECT kind, COUNT(*) AS n FROM records WHERE extraction_id=? GROUP BY kind", (ext_id,)
            ).fetchall()
        return {r["kind"]: r["n"] for r in rows}

    def files(self, ext_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.db.execute(
                "SELECT rel_path, source, size, sha256, acquired FROM files WHERE extraction_id=? ORDER BY rel_path",
                (ext_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def audit_entries(self, ext_id: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            if ext_id:
                rows = self.db.execute(
                    "SELECT * FROM audit WHERE extraction_id=? ORDER BY id", (ext_id,)
                ).fetchall()
            else:
                rows = self.db.execute("SELECT * FROM audit ORDER BY id").fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        with self._lock:
            self.db.close()


class Extraction:
    def __init__(self, case: Case, ext_id: str, folder: Path) -> None:
        self.case = case
        self.id = ext_id
        self.dir = folder
        self.raw_dir = folder / "raw"
        self.media_dir = folder / "media"
        self.thumbs_dir = folder / "thumbs"

    # Records -----------------------------------------------------------
    def set_records(self, kind: str, records: Iterable[dict[str, Any]]) -> int:
        rows = [
            (self.id, kind, i, json.dumps(rec, ensure_ascii=False, default=str))
            for i, rec in enumerate(records)
        ]
        with self.case._lock:
            self.case.db.execute("DELETE FROM records WHERE extraction_id=? AND kind=?", (self.id, kind))
            self.case.db.executemany("INSERT INTO records VALUES(?,?,?,?)", rows)
            self.case.db.commit()
        return len(rows)

    def records(self, kind: str) -> list[dict[str, Any]]:
        return self.case.records(self.id, kind)

    # Files -------------------------------------------------------------
    def rel(self, path: Path) -> str:
        return path.relative_to(self.dir).as_posix()

    def register_file(self, path: Path, source: str) -> str:
        """Hash an acquired file and record it for the chain of custody."""
        digest = sha256_file(path)
        with self.case._lock:
            self.case.db.execute(
                "INSERT INTO files VALUES(?,?,?,?,?,?)",
                (self.id, self.rel(path), source, path.stat().st_size, digest, iso_now()),
            )
            self.case.db.commit()
        return digest

    def register_many(self, items: Iterable[tuple[Path, str]], progress=None) -> int:
        """Hash many files with a single database commit (used for iOS backups)."""
        rows = []
        items = list(items)
        for i, (path, source) in enumerate(items):
            rows.append((self.id, self.rel(path), source, path.stat().st_size, sha256_file(path), iso_now()))
            if progress and i % 200 == 0:
                progress(i / max(1, len(items)))
        with self.case._lock:
            self.case.db.executemany("INSERT INTO files VALUES(?,?,?,?,?,?)", rows)
            self.case.db.commit()
        return len(rows)

    # Audit -------------------------------------------------------------
    def audit(self, action: str, detail: str = "") -> None:
        ts = iso_now()
        with self.case._lock:
            self.case.db.execute(
                "INSERT INTO audit(extraction_id, ts, action, detail) VALUES(?,?,?,?)",
                (self.id, ts, action, detail),
            )
            self.case.db.commit()
        try:
            with open(self.dir / "audit.log", "a", encoding="utf-8") as fh:
                fh.write(f"{ts}\t{action}\t{detail}\n")
        except OSError:
            pass

    # State -------------------------------------------------------------
    def update_device(self, device: dict[str, Any]) -> None:
        with self.case._lock:
            self.case.db.execute(
                "UPDATE extractions SET device_json=?, model=? WHERE id=?",
                (
                    json.dumps(device, ensure_ascii=False),
                    device.get("market_name") or device.get("model", ""),
                    self.id,
                ),
            )
            self.case.db.commit()

    def set_unavailable(self, kind: str, reason: str, detail: str = "") -> None:
        info = self.case.extraction_info(self.id)
        unavailable = info["unavailable"]
        unavailable[kind] = {"reason": reason, "detail": detail}
        with self.case._lock:
            self.case.db.execute(
                "UPDATE extractions SET unavailable_json=? WHERE id=?",
                (json.dumps(unavailable, ensure_ascii=False), self.id),
            )
            self.case.db.commit()

    def finish(self, status: str = "completed") -> dict[str, Any]:
        counts = self.case.counts(self.id)
        with self.case._lock:
            self.case.db.execute(
                "UPDATE extractions SET finished=?, status=?, summary_json=? WHERE id=?",
                (iso_now(), status, json.dumps(counts), self.id),
            )
            self.case.db.commit()
        self.audit("extraction.finish", f"status={status}; counts={json.dumps(counts)}")
        self.write_manifest()
        return counts

    def write_manifest(self) -> Path:
        info = self.case.extraction_info(self.id)
        manifest = {
            "tool": f"{APP_NAME} v{__version__}",
            "case": self.case.meta(),
            "extraction": {k: info[k] for k in ("id", "started", "finished", "status", "method", "examiner")},
            "device": info["device"],
            "counts": info["summary"],
            "files": self.case.files(self.id),
        }
        path = self.dir / "manifest.json"
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return path


@dataclass
class CaseStore:
    root: Path

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        self.root.mkdir(parents=True, exist_ok=True)

    def list_cases(self) -> list[dict[str, Any]]:
        cases = []
        for db in sorted(self.root.glob("*/case.db")):
            case = Case(db.parent)
            try:
                cases.append(case.meta())
            finally:
                case.close()
        cases.sort(key=lambda c: c.get("created", ""), reverse=True)
        return cases

    def create_case(self, info: dict[str, Any]) -> Case:
        case_no = (info.get("case_no") or "").strip()
        title = (info.get("title") or "").strip()
        label = safe_name(case_no or title or "case")
        folder = self.root / f"{datetime.now():%Y%m%d}_{label}_{secrets.token_hex(2)}"
        folder.mkdir(parents=True)
        (folder / "reports").mkdir()
        case = Case(folder)
        meta = {k: (info.get(k) or "").strip() for k in CASE_FIELDS}
        meta["created"] = iso_now()
        case.set_meta(meta)
        return case

    def open_case(self, case_id: str) -> Case:
        folder = self.root / case_id
        if not (folder / "case.db").is_file() or folder.parent != self.root:
            raise FileNotFoundError(case_id)
        return Case(folder)

    def device_history(self) -> list[dict[str, Any]]:
        history = []
        for db in self.root.glob("*/case.db"):
            case = Case(db.parent)
            try:
                meta = case.meta()
                for ext in case.list_extractions():
                    ext["case_no"] = meta.get("case_no", "")
                    ext["case_title"] = meta.get("title", "")
                    history.append(ext)
            finally:
                case.close()
        history.sort(key=lambda e: e["started"] or "", reverse=True)
        return history
