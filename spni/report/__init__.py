"""Forensic report generator (wizard backend).

``generate(case, spec)`` collects the selected data from every chosen
extraction in a case and renders it as PDF, Word, Excel, HTML and/or a ZIP
report package with SHA-256 sums. Every output file is hashed and the hash is
written to the case audit log.
"""

from .generate import defaults, generate
from .spec import ReportSpec

__all__ = ["ReportSpec", "defaults", "generate"]
