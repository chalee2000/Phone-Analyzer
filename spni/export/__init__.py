"""Report exporters: Excel workbook, PDF report and photos-to-Word."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from ..util import safe_name


def report_name(case: dict[str, Any], extraction: dict[str, Any], suffix: str, ext: str) -> str:
    label = case.get("case_no") or case.get("title") or "report"
    device = extraction.get("model") or extraction.get("serial") or "device"
    return safe_name(f"SPNI_{label}_{device}_{suffix}_{datetime.now():%Y%m%d-%H%M%S}") + ext


def export_report(fmt: str, **kw: Any) -> Path:
    kw["out_dir"].mkdir(parents=True, exist_ok=True)
    if fmt == "excel":
        from .excel import build

        return build(**kw)
    if fmt == "pdf":
        from .pdf import build

        return build(**kw)
    if fmt == "word":
        from .word import build_photos

        return build_photos(**kw)
    raise ValueError(f"unknown format {fmt}")
