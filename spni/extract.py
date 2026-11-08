"""Extraction framework shared by the Android, iOS and demo extractors."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Iterable

from .case.store import Extraction
from .events import EventBus
from .media import IMAGE_EXTS, make_thumbnail, read_exif
from .models import DeviceInfo, Photo, Record, to_dicts


class Cancelled(Exception):
    pass


class ExtractionContext:
    """Everything an extractor needs while it runs.

    It writes records to the case database, hashes acquired files, keeps the
    audit log and reports progress to the UI.
    """

    def __init__(
        self,
        extraction: Extraction,
        bus: EventBus,
        job_id: str,
        kinds: Iterable[str],
        options: dict[str, Any] | None = None,
    ) -> None:
        self.extraction = extraction
        self.bus = bus
        self.job_id = job_id
        self.kinds = list(kinds)
        self.options = options or {}
        self.cancel_event = threading.Event()
        self.started = time.monotonic()

    # ── progress ────────────────────────────────────────────────────────
    def _emit(self, kind: str, status: str, **extra: Any) -> None:
        self.bus.emit(
            "extraction.step",
            {"job": self.job_id, "kind": kind, "status": status, **extra},
        )

    def begin(self, kind: str, message: str = "") -> None:
        self.check_cancel()
        self._emit(kind, "running", progress=0.0, message=message)

    def progress(self, kind: str, fraction: float, message: str = "", count: int | None = None) -> None:
        self.check_cancel()
        payload: dict[str, Any] = {"progress": max(0.0, min(1.0, fraction)), "message": message}
        if count is not None:
            payload["count"] = count
        self._emit(kind, "running", **payload)

    def stage(self, message: str, fraction: float | None = None) -> None:
        """Report a device-level stage that is not tied to one category."""
        self.bus.emit("extraction.stage", {"job": self.job_id, "message": message, "progress": fraction})

    def save(self, kind: str, records: Iterable[Record | dict[str, Any]]) -> int:
        items = to_dicts(records)
        count = self.extraction.set_records(kind, items)
        self.audit(f"records.{kind}", f"{count} records")
        self._emit(kind, "done", progress=1.0, count=count)
        return count

    def unavailable(self, kind: str, reason: str, detail: str = "") -> None:
        self.extraction.set_unavailable(kind, reason, detail)
        self.audit(f"unavailable.{kind}", f"{reason}: {detail}")
        self._emit(kind, "unavailable", reason=reason, detail=detail)

    def error(self, kind: str, exc: BaseException) -> None:
        self.extraction.set_unavailable(kind, "error", str(exc))
        self.audit(f"error.{kind}", repr(exc))
        self._emit(kind, "error", reason="error", detail=str(exc))

    def audit(self, action: str, detail: str = "") -> None:
        self.extraction.audit(action, detail)

    def check_cancel(self) -> None:
        if self.cancel_event.is_set():
            raise Cancelled()

    def wants(self, kind: str) -> bool:
        return kind in self.kinds

    # ── files ───────────────────────────────────────────────────────────
    def register(self, path: Path, source: str) -> str:
        return self.extraction.register_file(path, source)

    def photo_record(self, local: Path, source_path: str, album: str = "", modified: int | None = None) -> Photo:
        """Hash a pulled image, read its EXIF and create a thumbnail."""
        digest = self.register(local, source_path)
        rel = self.extraction.rel(local)
        meta = read_exif(local) if local.suffix.lower() in IMAGE_EXTS else {}
        thumb_rel = ""
        thumb = self.extraction.thumbs_dir / (digest[:16] + ".jpg")
        if make_thumbnail(local, thumb):
            thumb_rel = self.extraction.rel(thumb)
        return Photo(
            name=local.name,
            path=rel,
            thumb=thumb_rel,
            size=local.stat().st_size,
            taken=meta.get("taken") or modified,
            modified=modified,
            width=meta.get("width"),
            height=meta.get("height"),
            make=meta.get("make", ""),
            camera_model=meta.get("camera_model", ""),
            lat=meta.get("lat"),
            lon=meta.get("lon"),
            album=album,
            sha256=digest,
            source_path=source_path,
        )


class BaseExtractor:
    """Interface every device extractor implements."""

    platform: str = ""
    method: str = ""

    def device_info(self) -> DeviceInfo:  # pragma: no cover - interface
        raise NotImplementedError

    def run(self, ctx: ExtractionContext) -> DeviceInfo | None:  # pragma: no cover - interface
        """Extract every category in ``ctx.kinds``.

        May return an updated DeviceInfo (for example after an iOS backup
        revealed more details).
        """
        raise NotImplementedError

    def close(self) -> None:
        pass
