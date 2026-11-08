"""Run a report: collect → render each format → hash → package → audit."""

from __future__ import annotations

import base64
import json
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Callable

from .. import APP_NAME, __version__
from ..analysis import comms
from ..case import workspace
from ..case.store import CASE_FIELDS, Case
from ..export import labels
from ..models import ALL_KINDS
from ..util import safe_name, sha256_file
from . import html as html_r
from . import office, pdf
from .dataset import collect
from .spec import ReportSpec

EXT = {"pdf": ".pdf", "docx": ".docx", "xlsx": ".xlsx", "html": ".html"}
Progress = Callable[[str, float], None]


def defaults(case: Case) -> dict[str, Any]:
    meta = case.meta()
    exts = comms.extractions(case)
    devices = []
    for i, e in enumerate(exts):
        entry = comms.device_entry(e, i)
        entry["counts"] = case.counts(e["id"])
        devices.append(entry)
    label = meta.get("case_no") or meta.get("title") or "report"
    first = exts[0] if exts else {}
    return {
        "file_name": safe_name(f"รายงาน_{label}_{(first.get('model') or '')}".strip("_")),
        "out_dir": str(case.path / "reports"),
        "case": {k: meta.get(k, "") for k in CASE_FIELDS},
        "devices": devices,
        "bookmarks": len(workspace.bookmarks(case)),
        "kinds": ALL_KINDS,
    }


def _out_dir(case: Case, spec: ReportSpec) -> Path:
    if spec.out_dir:
        p = Path(spec.out_dir).expanduser()
        if p.is_absolute():
            p.mkdir(parents=True, exist_ok=True)
            return p
    p = case.path / "reports"
    p.mkdir(parents=True, exist_ok=True)
    return p


def generate(case: Case, raw_spec: dict[str, Any], network_png: str | None = None, progress: Progress | None = None) -> dict[str, Any]:
    spec = ReportSpec.parse(raw_spec)
    say = progress or (lambda step, f: None)
    # Case details typed into the wizard are kept with the case.
    if spec.case:
        case.set_meta({k: (spec.case.get(k) or "").strip() for k in CASE_FIELDS if k in spec.case})
    out_dir = _out_dir(case, spec)
    stem = safe_name(spec.file_name or f"report_{case.id}")
    with tempfile.TemporaryDirectory() as tmp:
        png_path = None
        if network_png and "network" in spec.sections:
            png_path = Path(tmp) / "network.png"
            png_path.write_bytes(base64.b64decode(network_png.split(",", 1)[-1]))
        say("collect", 0.05)
        prev_offset = labels.YEAR_OFFSET
        labels.YEAR_OFFSET = 543 if (spec.buddhist_year and spec.lang == "th") else 0
        try:
            ds = collect(case, spec, png_path)
            renders = [f for f in spec.formats if f != "zip"]
            if "zip" in spec.formats:
                renders = list(dict.fromkeys(renders + ["pdf", "xlsx", "html"]))
            produced: dict[str, Path] = {}
            for i, fmt in enumerate(renders):
                say(fmt, 0.1 + 0.75 * i / max(1, len(renders)))
                target = out_dir / f"{stem}{EXT[fmt]}"
                if fmt == "pdf":
                    produced[fmt] = pdf.build(ds, target)
                elif fmt == "docx":
                    produced[fmt] = office.build_docx(ds, target)
                elif fmt == "xlsx":
                    produced[fmt] = office.build_xlsx(ds, target)
                elif fmt == "html":
                    produced[fmt] = html_r.build(ds, target)
        finally:
            labels.YEAR_OFFSET = prev_offset
        say("package", 0.9)
        results = []
        manifest = {
            "tool": f"{APP_NAME} v{__version__}",
            "report_id": ds.report_id,
            "generated": ds.generated.isoformat(timespec="seconds"),
            "case": ds.case,
            "spec": spec.public(),
            "devices": [{"id": d.info["id"], "label": d.label, "serial": d.info.get("serial"), "method": d.info.get("method"),
                         "counts": {k: len(v) for k, v in d.records.items()}} for d in ds.devices],
            "files": {},
        }
        for fmt, path in produced.items():
            digest = sha256_file(path)
            manifest["files"][path.name] = digest
            if fmt in spec.formats:
                results.append({"format": fmt, "path": str(path), "name": path.name, "size": path.stat().st_size, "sha256": digest})
        if "zip" in spec.formats:
            zpath = out_dir / f"{stem}.zip"
            sums = "".join(f"{h}  {n}\n" for n, h in manifest["files"].items())
            with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
                for path in produced.values():
                    z.write(path, path.name)
                z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
                z.writestr("SHA256SUMS.txt", sums)
            for fmt, path in produced.items():  # formats that were only built for the package
                if fmt not in spec.formats:
                    path.unlink(missing_ok=True)
            results.append({"format": "zip", "path": str(zpath), "name": zpath.name, "size": zpath.stat().st_size, "sha256": sha256_file(zpath)})
        if spec.hash_file:
            for r in results:
                Path(r["path"] + ".sha256").write_text(f"{r['sha256']}  {r['name']}\n", encoding="utf-8")
        for r in results:
            workspace.audit(case, f"report.{r['format']}", f"{ds.report_id} {r['name']} sha256={r['sha256']}")
        say("done", 1.0)
        return {"report_id": ds.report_id, "out_dir": str(out_dir), "files": results}
