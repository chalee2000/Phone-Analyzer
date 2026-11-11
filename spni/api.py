"""The API exposed to the web UI.

In the desktop app pywebview exposes every public method of :class:`Api` as
``window.pywebview.api.<name>(...)``; the development server exposes the same
methods over HTTP. Every method returns ``{"ok": true, "data": ...}`` or
``{"ok": false, "error": <code>, "message": <text>}`` so both transports behave
identically. Long work (extraction) runs in a background thread and reports
progress through the event bus.
"""

from __future__ import annotations

import functools
import logging
import os
import subprocess
import sys
import threading
import traceback
import uuid
from pathlib import Path
from typing import Any, Callable

from . import __version__, diagnostics, logs
from .android.adb import AdbManager
from .analysis import comms as comms_mod
from .analysis import network as network_mod
from .analysis import timeline as timeline_mod
from .case import workspace
from .case.store import CASE_FIELDS, Case, CaseStore, default_cases_root
from .demo import DEMO_ANDROID_ID, DEMO_IOS_ID, DemoExtractor, demo_devices
from .events import EventBus
from .extract import BaseExtractor, Cancelled, ExtractionContext
from .models import ALL_KINDS
from .paths import agent_apk


class ApiError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code
        self.message = message or code


def endpoint(fn: Callable) -> Callable:
    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        try:
            return {"ok": True, "data": fn(self, *args, **kwargs)}
        except ApiError as exc:
            return {"ok": False, "error": exc.code, "message": exc.message}
        except ValueError as exc:
            code = str(exc) if str(exc).replace("_", "").isalnum() else "invalid"
            return {"ok": False, "error": code, "message": str(exc)}
        except Exception as exc:  # unexpected: report, never crash the UI
            traceback.print_exc()
            logging.getLogger("spni.api").exception("%s failed", fn.__name__)
            return {"ok": False, "error": "internal", "message": f"{type(exc).__name__}: {exc}"}

    wrapper._endpoint = True  # type: ignore[attr-defined]
    return wrapper


class Api:
    def __init__(self, bus: EventBus | None = None, cases_root: Path | None = None, demo: bool = False) -> None:
        self._bus = bus or EventBus()
        self._store = CaseStore(cases_root or default_cases_root())
        self._adb = AdbManager()
        self._demo = demo
        self._window = None
        self._media_base = ""
        self._lock = threading.RLock()
        self._device: dict[str, Any] | None = None
        self._extractor: BaseExtractor | None = None
        self._case: Case | None = None
        self._extraction_id: str | None = None
        self._job: dict[str, Any] | None = None
        self._reporting = False
        self._report_paths: set[Path] = set()  # report outputs the examiner may open/reveal

    # ── wiring (not exposed: underscore names are hidden from JS) ───────────
    def _attach_window(self, window) -> None:
        self._window = window

    def _set_media_base(self, url: str) -> None:
        self._media_base = url

    @property
    def _cases_root(self) -> Path:
        return self._store.root

    # ── app / window ─────────────────────────────────────────────────────
    @endpoint
    def app_info(self) -> dict[str, Any]:
        return {
            "version": __version__,
            "demo": self._demo,
            "cases_root": str(self._store.root),
            "media_base": self._media_base,
            "platform": sys.platform,
            "agent_available": agent_apk().is_file(),
            "log_path": str(logs.path() or ""),
            "kinds": ALL_KINDS,
        }

    @endpoint
    def window_minimize(self) -> None:
        if self._window:
            self._window.minimize()

    @endpoint
    def window_toggle_maximize(self) -> None:
        if not self._window:
            return
        maximized = getattr(self._window, "_spni_maximized", False)
        if maximized:
            self._window.restore()
        else:
            self._window.maximize()
        self._window._spni_maximized = not maximized

    @endpoint
    def window_close(self) -> None:
        if self._job:
            self._job["ctx"].cancel_event.set()
        if self._window:
            self._window.destroy()

    @endpoint
    def set_demo(self, enabled: bool) -> bool:
        self._demo = bool(enabled)
        return self._demo

    # ── devices ──────────────────────────────────────────────────────────
    @endpoint
    def scan_devices(self, platform: str = "") -> dict[str, Any]:
        devices: list[dict[str, Any]] = []
        if platform in ("", "android"):
            devices += self._adb.list_devices()
        if platform in ("", "ios"):
            from .ios import device as ios_device

            devices += ios_device.list_devices()
        if self._demo:
            devices += [d for d in demo_devices() if platform in ("", d["platform"])]
        return {"devices": devices}

    def _make_extractor(self, device_id: str) -> BaseExtractor:
        if device_id == DEMO_ANDROID_ID:
            return DemoExtractor("android")
        if device_id == DEMO_IOS_ID:
            return DemoExtractor("ios")
        kind, _, serial = device_id.partition(":")
        if kind == "android":
            from .android.extract import AndroidExtractor

            return AndroidExtractor(self._adb.transport(serial), agent_apk())
        if kind == "ios":
            from .ios.extract import IOSExtractor

            return IOSExtractor(serial)
        raise ApiError("unknown_device", device_id)

    @endpoint
    def connect(self, device_id: str) -> dict[str, Any]:
        if self._job:
            raise ApiError("busy", "extraction in progress")
        extractor = self._make_extractor(device_id)
        try:
            info = extractor.device_info().to_dict()
        except Exception as exc:
            name = type(exc).__name__
            code = {
                "PairingDialogResponsePendingError": "ios_trust_pending",
                "UserDeniedPairingError": "ios_trust_denied",
                "PasswordRequiredError": "ios_locked",
                "NotPairedError": "ios_trust_pending",
                "AdbError": "android_unauthorized",
            }.get(name, "connect_failed")
            raise ApiError(code, f"{name}: {exc}")
        with self._lock:
            self._device = {"id": device_id, "info": info, "demo": device_id.startswith("demo:")}
            self._extractor = extractor
            self._extraction_id = None
        self._bus.emit("device.connected", self._device)
        return self._device

    @endpoint
    def disconnect(self) -> None:
        with self._lock:
            if self._job:
                raise ApiError("busy")
            if self._extractor:
                self._extractor.close()
            self._extractor = None
            self._device = None
            if self._case and self._extraction_id:
                # Keep the extracted data on screen for review, without a live device.
                info = self._case.extraction_info(self._extraction_id)
                self._device = {"id": f"offline:{info['serial']}", "info": info["device"], "offline": True}
        self._bus.emit("device.disconnected", {})

    @endpoint
    def close_extraction(self) -> None:
        """Stop reviewing the open extraction (the case stays open)."""
        with self._lock:
            if self._job:
                raise ApiError("busy")
            self._extraction_id = None
            if self._device and self._device.get("offline"):
                self._device = None

    @endpoint
    def state(self) -> dict[str, Any]:
        ext = None
        counts: dict[str, int] = {}
        if self._case and self._extraction_id:
            ext = self._case.extraction_info(self._extraction_id)
            counts = self._case.counts(self._extraction_id)
        return {
            "device": self._device,
            "case": self._case.meta() if self._case else None,
            "extraction": ext,
            "counts": counts,
            "running": bool(self._job),
        }

    @endpoint
    def set_device_number(self, number: str) -> dict[str, Any]:
        number = (number or "").strip()
        if self._device:
            self._device["info"]["phone_number"] = number
        if self._case and self._extraction_id:
            info = self._case.extraction_info(self._extraction_id)
            device = info["device"]
            device["phone_number"] = number
            ext = self._case.get_extraction(self._extraction_id)
            ext.update_device(device)
            ext.audit("device.phone_number", f"examiner set device number: {number}")
        return {"phone_number": number}

    # ── extraction ───────────────────────────────────────────────────────
    @endpoint
    def start_extraction(self, options: dict[str, Any] | None = None) -> dict[str, Any]:
        options = dict(options or {})
        with self._lock:
            if self._job:
                raise ApiError("busy")
            if not self._device or not self._extractor:
                raise ApiError("no_device")
            if not self._case:
                self._case = self._store.create_case({"title": "งานด่วน", "case_no": "", "note": "สร้างอัตโนมัติ"})
                self._bus.emit("case.opened", self._case.meta())
            kinds = [k for k in options.get("kinds") or ALL_KINDS if k in ALL_KINDS]
            extractor = self._extractor
            ext = self._case.create_extraction(self._device["info"], extractor.method, options.get("examiner", ""))
            ext.audit("options", ", ".join(f"{k}={v}" for k, v in options.items() if k != "ios_backup_password"))
            job_id = uuid.uuid4().hex[:10]
            ctx = ExtractionContext(ext, self._bus, job_id, kinds, options)
            self._job = {"id": job_id, "ctx": ctx}
            self._extraction_id = ext.id
        thread = threading.Thread(target=self._run_job, args=(extractor, ctx), daemon=True, name=f"extract-{job_id}")
        thread.start()
        self._bus.emit("extraction.started", {"job": job_id, "extraction_id": ext.id, "kinds": kinds})
        return {"job": job_id, "extraction_id": ext.id, "kinds": kinds}

    def _run_job(self, extractor: BaseExtractor, ctx: ExtractionContext) -> None:
        status, message = "completed", ""
        try:
            info = extractor.run(ctx)
            if info is not None:
                device = info.to_dict()
                # Keep a phone number the examiner already typed in.
                if self._device and self._device["info"].get("phone_number") and not device.get("phone_number"):
                    device["phone_number"] = self._device["info"]["phone_number"]
                ctx.extraction.update_device(device)
                if self._device:
                    self._device["info"] = device
        except Cancelled:
            status = "cancelled"
        except Exception as exc:
            traceback.print_exc()
            status, message = "failed", f"{type(exc).__name__}: {exc}"
            if type(exc).__name__ == "BackupPasswordRequired":
                message = "ios_backup_password_required"
            ctx.audit("extraction.error", message)
        counts = ctx.extraction.finish(status)
        info = ctx.extraction.case.extraction_info(ctx.extraction.id)
        with self._lock:
            self._job = None
        self._bus.emit(
            "extraction.done",
            {"job": ctx.job_id, "extraction_id": ctx.extraction.id, "status": status, "message": message,
             "counts": counts, "unavailable": info["unavailable"], "device": info["device"]},
        )

    @endpoint
    def cancel_extraction(self) -> bool:
        if self._job:
            self._job["ctx"].cancel_event.set()
            return True
        return False

    @endpoint
    def get_records(self, kind: str) -> list[dict[str, Any]]:
        if kind not in ALL_KINDS:
            raise ApiError("bad_kind", kind)
        if not self._case or not self._extraction_id:
            return []
        return self._case.records(self._extraction_id, kind)

    @endpoint
    def audit_log(self) -> list[dict[str, Any]]:
        if not self._case or not self._extraction_id:
            return []
        return self._case.audit_entries(self._extraction_id)

    # ── cases ────────────────────────────────────────────────────────────
    @endpoint
    def list_cases(self) -> list[dict[str, Any]]:
        return self._store.list_cases()

    @endpoint
    def create_case(self, info: dict[str, Any]) -> dict[str, Any]:
        if not (info.get("case_no") or info.get("title")):
            raise ApiError("case_name_required")
        case = self._store.create_case(info)
        self._set_case(case)
        return case.meta()

    @endpoint
    def open_case(self, case_id: str) -> dict[str, Any]:
        try:
            case = self._store.open_case(case_id)
        except FileNotFoundError:
            raise ApiError("case_not_found", case_id)
        self._set_case(case)
        exts = case.list_extractions()
        if exts:
            self._extraction_id = exts[0]["id"]
        return case.meta()

    def _set_case(self, case: Case) -> None:
        with self._lock:
            if self._job:
                raise ApiError("busy")
            if self._case:
                self._case.close()
            self._case = case
            self._extraction_id = None
        self._bus.emit("case.opened", case.meta())

    @endpoint
    def update_case(self, info: dict[str, Any]) -> dict[str, Any]:
        if not self._case:
            raise ApiError("no_case")
        self._case.set_meta({k: info[k] for k in CASE_FIELDS if k in info})
        return self._case.meta()

    @endpoint
    def list_extractions(self) -> list[dict[str, Any]]:
        return self._case.list_extractions() if self._case else []

    @endpoint
    def device_history(self) -> list[dict[str, Any]]:
        return self._store.device_history()

    @endpoint
    def open_extraction(self, case_id: str, extraction_id: str) -> dict[str, Any]:
        if not self._case or self._case.id != case_id:
            try:
                self._set_case(self._store.open_case(case_id))
            except FileNotFoundError:
                raise ApiError("case_not_found", case_id)
        info = self._case.extraction_info(extraction_id)  # type: ignore[union-attr]
        with self._lock:
            self._extraction_id = extraction_id
            if not self._device or self._device["info"].get("serial") != info["device"].get("serial"):
                # Offline review: show the stored device, no live connection.
                self._device = {"id": f"offline:{info['serial']}", "info": info["device"], "offline": True}
                self._extractor = None
        return info

    # ── export ───────────────────────────────────────────────────────────
    @endpoint
    def export_report(self, fmt: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
        from .export import export_report

        if not self._case or not self._extraction_id:
            raise ApiError("nothing_to_export")
        options = options or {}
        info = self._case.extraction_info(self._extraction_id)
        records = {k: self._case.records(self._extraction_id, k) for k in ALL_KINDS}
        path = export_report(
            fmt,
            case=self._case.meta(),
            extraction=info,
            records=records,
            files=self._case.files(self._extraction_id),
            ext_dir=self._case.path / "extractions" / self._extraction_id,
            out_dir=self._case.path / "reports",
            lang=options.get("lang", "th"),
        )
        self._case.get_extraction(self._extraction_id).audit(f"export.{fmt}", path.name)
        return {"path": str(path), "name": path.name}

    def _allowed(self, path: str) -> Path:
        """Only files inside the cases root, or reports produced this session."""
        target = Path(path).resolve()
        if target in self._report_paths:
            return target
        try:
            target.relative_to(self._store.root.resolve())
        except ValueError:
            raise ApiError("forbidden")
        return target

    @endpoint
    def reveal(self, path: str) -> None:
        target = self._allowed(path)
        if sys.platform == "win32":
            if target.is_file():
                subprocess.Popen(["explorer", "/select,", str(target)])
            else:
                os.startfile(str(target))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(target)])
        else:
            subprocess.Popen(["xdg-open", str(target.parent if target.is_file() else target)])

    @endpoint
    def media_probe(self, rel: str, failed: bool = True) -> dict[str, Any]:
        """A media file of the open extraction that the UI could not display: where it is.

        Logged so a support request carries the reason; the UI offers to open the
        file in the system viewer instead.
        """
        case = self._require_case()
        if not self._extraction_id:
            raise ApiError("nothing_to_export")
        target = self._allowed(str(case.path / "extractions" / self._extraction_id / rel))
        exists = target.is_file()
        size = target.stat().st_size if exists else None
        if failed:
            logging.getLogger("spni.media").warning(
                "UI could not display %s (exists=%s, size=%s, media_base=%s)", target, exists, size, self._media_base
            )
        return {"path": str(target), "exists": exists, "size": size, "log": str(logs.path() or "")}

    @endpoint
    def open_file(self, path: str) -> None:
        """Open a produced file with its default application."""
        target = self._allowed(path)
        if not target.is_file():
            raise ApiError("not_found", path)
        if sys.platform == "win32":
            os.startfile(str(target))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(target)])
        else:
            subprocess.Popen(["xdg-open", str(target)])

    @endpoint
    def choose_folder(self, initial: str = "") -> str | None:
        """Native folder picker (desktop only; the dev server has no window)."""
        if not self._window:
            return None
        import webview

        kind = getattr(getattr(webview, "FileDialog", None), "FOLDER", None) or webview.FOLDER_DIALOG
        start = initial if initial and Path(initial).is_dir() else ""
        res = self._window.create_file_dialog(kind, directory=start)
        if not res:
            return None
        return str(res[0] if isinstance(res, (list, tuple)) else res)

    @endpoint
    def choose_files(self, purpose: str = "messenger") -> list[str] | None:
        """Native multi-file picker (desktop only; the dev server has no window)."""
        if not self._window:
            return None
        import webview

        kind = getattr(getattr(webview, "FileDialog", None), "OPEN", None) or webview.OPEN_DIALOG
        types = (
            ("LINE chat export (*.txt;*.zip)", "All files (*.*)") if purpose == "line"
            else ("Facebook / Messenger export (*.zip;*.json)", "All files (*.*)")
        )
        res = self._window.create_file_dialog(kind, allow_multiple=True, file_types=types)
        if not res:
            return None
        return [str(p) for p in (res if isinstance(res, (list, tuple)) else [res])]

    # ── forensic report ──────────────────────────────────────────────────
    @endpoint
    def report_defaults(self) -> dict[str, Any]:
        from . import report

        return report.defaults(self._require_case())

    @endpoint
    def generate_report(self, spec: dict[str, Any], chart_png: str | None = None) -> dict[str, Any]:
        from . import report

        case = self._require_case()
        with self._lock:
            if self._job or self._reporting:
                raise ApiError("busy")
            self._reporting = True
        try:
            result = report.generate(
                case, spec or {}, chart_png,
                lambda step, frac: self._bus.emit("report.progress", {"step": step, "progress": round(frac, 3)}),
            )
        finally:
            self._reporting = False
        self._report_paths.add(Path(result["out_dir"]).resolve())
        for f in result["files"]:
            self._report_paths.add(Path(f["path"]).resolve())
        self._bus.emit("case.opened", case.meta())  # case details may have been edited in the wizard
        return result

    @endpoint
    def open_case_folder(self) -> None:
        if self._case:
            self.reveal(str(self._case.path))

    # ── diagnostics ──────────────────────────────────────────────────────
    @endpoint
    def diagnostics(self, platform: str) -> list[dict[str, Any]]:
        if platform == "ios":
            return diagnostics.ios_checks()
        return diagnostics.android_checks(self._adb)

    @endpoint
    def restart_adb(self) -> bool:
        return self._adb.restart_server()

    # ── analysis: shared ─────────────────────────────────────────────────
    def _require_case(self) -> Case:
        if not self._case:
            raise ApiError("no_case")
        return self._case

    def _ensure_case(self) -> Case:
        if not self._case:
            self._case = self._store.create_case({"title": "งานด่วน", "case_no": "", "note": "สร้างอัตโนมัติ"})
            self._bus.emit("case.opened", self._case.meta())
        return self._case

    def _saved(self, path: Path) -> dict[str, Any]:
        return {"path": str(path), "name": path.name}

    @endpoint
    def case_devices(self) -> list[dict[str, Any]]:
        case = self._require_case()
        return [comms_mod.device_entry(e, i) for i, e in enumerate(comms_mod.extractions(case))]

    # ── network analysis ─────────────────────────────────────────────────
    @endpoint
    def network_graph(self, options: dict[str, Any] | None = None) -> dict[str, Any]:
        return network_mod.build(self._require_case(), options)

    @endpoint
    def network_evidence(self, element_id: str) -> list[dict[str, Any]]:
        return network_mod.evidence(self._require_case(), element_id)

    @endpoint
    def network_annotate(self, node_id: str, label: str = "", note: str = "", tags: list[str] | None = None) -> dict[str, Any]:
        return workspace.set_annotation(self._require_case(), node_id, label, note, tags or [])

    @endpoint
    def network_add_entity(self, entity: dict[str, Any], link_to: list[str] | None = None, link_label: str = "") -> dict[str, Any]:
        case = self._require_case()
        ent = workspace.add_entity(case, entity.get("type", "other"), entity.get("label", ""), entity.get("note", ""))
        for target in link_to or []:
            workspace.add_link(case, f"man:{ent['id']}", target, link_label)
        return {**ent, "node_id": f"man:{ent['id']}"}

    @endpoint
    def network_add_link(self, source: str, target: str, label: str = "") -> dict[str, Any]:
        return workspace.add_link(self._require_case(), source, target, label)

    @endpoint
    def network_delete_manual(self, item_id: str) -> None:
        workspace.delete_manual(self._require_case(), item_id)

    @endpoint
    def network_save_layout(self, positions: dict[str, Any]) -> None:
        workspace.save_layout(self._require_case(), positions)

    @endpoint
    def network_load_layout(self) -> dict[str, Any]:
        return workspace.load_layout(self._require_case())

    @endpoint
    def export_network(self, fmt: str, options: dict[str, Any] | None = None, positions: dict[str, Any] | None = None) -> dict[str, Any]:
        from .export.analysis import export_network

        case = self._require_case()
        graph = network_mod.build(case, options)
        path = export_network(fmt, graph, case.meta(), case.path / "reports", positions)
        workspace.audit(case, f"export.network.{fmt}", path.name)
        return self._saved(path)

    @endpoint
    def save_chart_image(self, data_url: str, label: str = "Network") -> dict[str, Any]:
        from .export.analysis import save_png

        case = self._require_case()
        path = save_png(data_url, case.meta(), case.path / "reports", label)
        workspace.audit(case, "export.chart.png", path.name)
        return self._saved(path)

    # ── timeline ────────────────────────────────────────────────────────
    @endpoint
    def timeline(self, options: dict[str, Any] | None = None) -> dict[str, Any]:
        options = options or {}
        return timeline_mod.build(self._require_case(), options.get("extractions"), bool(options.get("system_apps")))

    @endpoint
    def timeline_save_entry(self, entry: dict[str, Any]) -> dict[str, Any]:
        return workspace.save_entry(self._require_case(), entry)

    @endpoint
    def timeline_delete_entry(self, entry_id: str) -> None:
        workspace.delete_entry(self._require_case(), entry_id)

    @endpoint
    def timeline_bookmark(self, event_id: str, on: bool, note: str = "") -> None:
        workspace.set_bookmark(self._require_case(), event_id, bool(on), note)

    @endpoint
    def export_timeline(self, fmt: str, ids: list[str] | None = None, options: dict[str, Any] | None = None) -> dict[str, Any]:
        from .export.analysis import export_timeline

        case = self._require_case()
        data = timeline_mod.build(case, (options or {}).get("extractions"), bool((options or {}).get("system_apps")))
        events = data["events"]
        if ids is not None:
            wanted = set(ids)
            events = [e for e in events if e["id"] in wanted]
        devices = {d["id"]: d["label"] for d in data["devices"]}
        path = export_timeline(fmt, events, devices, case.meta(), case.path / "reports")
        workspace.audit(case, f"export.timeline.{fmt}", f"{path.name} ({len(events)} events)")
        return self._saved(path)

    # ── call & contact analysis ─────────────────────────────────────────
    @endpoint
    def comm_analysis(self, options: dict[str, Any] | None = None) -> dict[str, Any]:
        return comms_mod.comm_rows(self._require_case(), (options or {}).get("extractions"))

    @endpoint
    def export_comms(self, ids: list[str] | None = None) -> dict[str, Any]:
        from .export.analysis import export_comms

        case = self._require_case()
        data = comms_mod.comm_rows(case)
        rows = data["rows"]
        if ids is not None:
            wanted = set(ids)
            rows = [r for r in rows if r["id"] in wanted]
        devices = {d["id"]: d["label"] for d in data["devices"]}
        path = export_comms(rows, comms_mod.summarize(rows), devices, case.meta(), case.path / "reports")
        workspace.audit(case, "export.comms.xlsx", f"{path.name} ({len(rows)} rows)")
        return self._saved(path)

    def _import_cdr(self, name: str, raw: bytes) -> dict[str, Any]:
        from . import cdr

        with self._lock:
            if self._job:
                raise ApiError("busy")
            case = self._ensure_case()
        result = cdr.import_into(case, name, raw)
        if not self._extraction_id:
            self._extraction_id = result["extraction_id"]
        self._bus.emit("case.opened", case.meta())
        return result

    @endpoint
    def import_cdr(self, name: str, data_b64: str) -> dict[str, Any]:
        import base64

        return self._import_cdr(name, base64.b64decode(data_b64.split(",", 1)[-1]))

    @endpoint
    def import_demo_cdr(self) -> dict[str, Any]:
        from . import cdr
        from .demo import DEMO_ANDROID_NUMBER, cdr_partners

        data = cdr.demo_cdr_bytes(DEMO_ANDROID_NUMBER, cdr_partners())
        return self._import_cdr(f"demo_cdr_{DEMO_ANDROID_NUMBER}.csv", data)

    # ── Messenger (Facebook data export) ────────────────────────────────
    def _uploads(self) -> Path:
        folder = self._store.root / ".uploads" / uuid.uuid4().hex[:12]
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    @staticmethod
    def _input_paths(paths: list[str] | str) -> list[str]:
        items = [paths] if isinstance(paths, str) else list(paths or [])
        if not items:
            raise ApiError("fb_no_messages")
        for p in items:
            if not isinstance(p, str) or not Path(p).exists():
                raise ApiError("not_found", str(p))
        return items

    @endpoint
    def messenger_upload(self, name: str, data_b64: str) -> str:
        """Browser / dev-server path: store an uploaded export so it can be read by path."""
        import base64

        from .util import safe_name

        dest = self._uploads() / safe_name(Path(name).name, "upload")
        dest.write_bytes(base64.b64decode(data_b64.split(",", 1)[-1]))
        return str(dest)

    @endpoint
    def messenger_preview(self, paths: list[str]) -> dict[str, Any]:
        from . import messenger

        return messenger.preview(self._input_paths(paths))

    def _import_messenger(self, paths: list[str], owner: str, module: Any = None) -> dict[str, Any]:
        """Import an account export as its own source (Messenger, or LINE chat exports)."""
        from . import messenger

        module = module or messenger
        with self._lock:
            if self._job or self._reporting:
                raise ApiError("busy")
            case = self._ensure_case()
            self._reporting = True
        try:
            result = module.import_into(
                case, paths, owner,
                progress=lambda step, frac: self._bus.emit("import.progress", {"step": step, "progress": round(frac, 3)}),
            )
        finally:
            self._reporting = False
        if not self._extraction_id:
            self._extraction_id = result["extraction_id"]
        result["case_id"] = case.id
        self._bus.emit("case.opened", case.meta())
        return result

    @endpoint
    def messenger_import(self, paths: list[str], owner: str = "") -> dict[str, Any]:
        return self._import_messenger(self._input_paths(paths), owner)

    @endpoint
    def messenger_demo_files(self) -> list[str]:
        """Write the demo export (DYI zip + secure-storage zip) and return their paths."""
        from . import messenger

        folder = self._uploads()
        out = []
        for name, data in messenger.demo_export():
            (folder / name).write_bytes(data)
            out.append(str(folder / name))
        return out

    # ── LINE "Export chat history" text files ──────────────────────────
    @endpoint
    def line_preview(self, paths: list[str]) -> dict[str, Any]:
        from . import line_export

        return line_export.preview(self._input_paths(paths))

    @endpoint
    def line_import(self, paths: list[str], owner: str = "") -> dict[str, Any]:
        from . import line_export

        return self._import_messenger(self._input_paths(paths), owner, line_export)

    @endpoint
    def line_demo_files(self) -> list[str]:
        from . import line_export

        folder = self._uploads()
        out = []
        for name, data in line_export.demo_files():
            (folder / name).write_bytes(data)
            out.append(str(folder / name))
        return out

    @endpoint
    def import_demo_messenger(self) -> dict[str, Any]:
        paths = self.messenger_demo_files()["data"]
        return self._import_messenger(paths, "")
