"""Everything the report wizard lets the examiner choose."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from ..models import ALL_KINDS

FORMATS = ("pdf", "docx", "xlsx", "html", "zip")
CLASSIFICATIONS = ("", "ปกปิด", "ลับ", "ลับมาก", "ลับที่สุด")
SECTIONS = ("devices", "summary", "network", "cross_device", "top_contacts", "bookmarks", "records", "photos", "hashes", "audit", "signature")


@dataclass
class ReportSpec:
    # General
    file_name: str = ""
    formats: list[str] = field(default_factory=lambda: ["pdf"])
    out_dir: str = ""  # empty → the case's reports folder
    title: str = ""
    # Case information (saved back to the case)
    case: dict[str, str] = field(default_factory=dict)
    # Dataset
    extractions: list[str] | None = None
    kinds: list[str] = field(default_factory=lambda: list(ALL_KINDS))
    sections: list[str] = field(default_factory=lambda: list(SECTIONS))
    date_from: int | None = None
    date_to: int | None = None
    top_n: int = 20
    # Security
    pdf_password: str = ""
    classification: str = ""
    hash_file: bool = True
    # Formatting
    lang: str = "th"
    buddhist_year: bool = True
    newest_first: bool = True
    orientation: str = "landscape"
    max_rows: int = 3000
    thumbnails: bool = True

    @classmethod
    def parse(cls, raw: dict[str, Any] | None) -> "ReportSpec":
        raw = dict(raw or {})
        spec = cls(**{k: v for k, v in raw.items() if k in cls.__dataclass_fields__})
        spec.formats = [f for f in spec.formats if f in FORMATS] or ["pdf"]
        spec.kinds = [k for k in spec.kinds if k in ALL_KINDS]
        spec.sections = [s for s in spec.sections if s in SECTIONS]
        if spec.classification not in CLASSIFICATIONS:
            spec.classification = ""
        if spec.orientation not in ("landscape", "portrait"):
            spec.orientation = "landscape"
        spec.max_rows = max(50, min(int(spec.max_rows or 3000), 50000))
        spec.top_n = max(5, min(int(spec.top_n or 20), 100))
        return spec

    def public(self) -> dict[str, Any]:
        """For the manifest: never store the PDF password."""
        data = asdict(self)
        data["pdf_password"] = "***" if self.pdf_password else ""
        return data
