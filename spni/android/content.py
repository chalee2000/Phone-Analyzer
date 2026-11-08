"""Parser for ``adb shell content query`` output.

Output looks like::

    Row: 0 _id=12, address=0812345678, date=1730956800000, body=hello, world
    Row: 1 _id=13, address=AIS, date=1730956900000, body=line one
    line two continues here

Values are not escaped, so commas and newlines can appear inside text. Because
we always pass ``--projection``, the column order is known; each row is split
by searching for ``, <next column>=`` in order, which keeps free text intact.
"""

from __future__ import annotations

import re

_ROW = re.compile(r"^Row: \d+ ", re.MULTILINE)

DENIED_MARKERS = (
    "Permission Denial",
    "SecurityException",
    "requires android.permission",
    "Error while accessing provider",
    "Unknown URI",
    "Could not find provider",
)


class ContentQueryError(Exception):
    def __init__(self, message: str, denied: bool = False) -> None:
        super().__init__(message)
        self.denied = denied


def build_query(uri: str, projection: list[str], where: str | None = None) -> str:
    cmd = f"content query --uri {uri} --projection {':'.join(projection)}"
    if where:
        cmd += f' --where "{where}"'
    return cmd


def check_output(output: str) -> None:
    head = output[:600]
    if "No result found" in head and not _ROW.search(output):
        return
    for marker in DENIED_MARKERS:
        if marker in head and not head.startswith("Row: "):
            raise ContentQueryError(head.strip().splitlines()[0] if head.strip() else marker, denied=True)
    if (head.startswith("Error") or "Exception" in head.split("\n", 1)[0]) and not head.startswith("Row: "):
        raise ContentQueryError(head.strip().splitlines()[0])


def parse_rows(output: str, columns: list[str]) -> list[dict[str, str | None]]:
    check_output(output)
    starts = [m.start() for m in _ROW.finditer(output)]
    rows = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(output)
        chunk = output[start:end]
        chunk = _ROW.sub("", chunk, count=1)
        if chunk.endswith("\r\n"):
            chunk = chunk[:-2]
        elif chunk.endswith("\n"):
            chunk = chunk[:-1]
        rows.append(_split_row(chunk, columns))
    return rows


def _split_row(text: str, columns: list[str]) -> dict[str, str | None]:
    values: dict[str, str | None] = {}
    positions: list[tuple[str, int, int]] = []  # (column, value start, key start)
    cursor = 0
    for idx, col in enumerate(columns):
        token = f"{col}=" if idx == 0 else f", {col}="
        pos = text.find(token, cursor)
        if pos < 0:
            continue
        positions.append((col, pos + len(token), pos))
        cursor = pos + len(token)
    for i, (col, vstart, _) in enumerate(positions):
        vend = positions[i + 1][2] if i + 1 < len(positions) else len(text)
        value = text[vstart:vend]
        values[col] = None if value == "NULL" else value
    for col in columns:
        values.setdefault(col, None)
    return values


def as_int(value: str | None, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default
