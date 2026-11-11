"""Import operator call detail records (CDR) from CSV or Excel.

Column names differ between operators and request templates, so headers are
matched against a list of Thai and English aliases. Dates in the Buddhist era
(year > 2400) are converted. The number that appears in most rows is taken
as the target; the other party of each row becomes the counterpart.

The import is stored as an extraction with ``method = "cdr"`` so every
analysis (calls, network, timeline, map) works on it like a phone.
"""

from __future__ import annotations

import csv
import io
import random
import re
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .case.store import Case
from .models import ALL_KINDS, CallRecord, SmsMessage
from .util import local_ms, normalize_phone

ALIASES: dict[str, list[str]] = {
    "a": ["a_number", "anumber", "a_no", "calling", "calling_number", "caller", "msisdn", "origin", "from", "source",
          "เบอร์ต้นทาง", "หมายเลขต้นทาง", "ต้นทาง", "เลขหมายต้นทาง"],
    "b": ["b_number", "bnumber", "b_no", "called", "called_number", "callee", "destination", "to", "other_party",
          "เบอร์ปลายทาง", "หมายเลขปลายทาง", "ปลายทาง", "เลขหมายปลายทาง", "คู่สนทนา"],
    "datetime": ["start_time", "starttime", "datetime", "date_time", "call_date_time", "call_start", "start_date_time",
                 "event_time", "วันเวลา", "วันที่เวลา", "วัน_เวลา", "เวลาเริ่ม"],
    "date": ["date", "call_date", "start_date", "วันที่"],
    "time": ["time", "call_time", "start_time_only", "เวลา"],
    "duration": ["duration", "call_duration", "dur", "duration_sec", "duration_s", "seconds", "ระยะเวลา", "ระยะเวลา_วินาที"],
    "type": ["record_type", "call_type", "type", "usage_type", "event_type", "service", "ประเภท", "ประเภทการใช้งาน"],
    "direction": ["direction", "call_direction", "in_out", "mo_mt", "ทิศทาง"],
    "cell": ["cell_id", "cellid", "cell", "ci", "first_cell", "start_cell", "lac_ci", "cgi", "first_cell_id", "เสา", "รหัสเสา"],
    "cell_end": ["last_cell", "end_cell", "cell_end", "last_cell_id"],
    "site": ["site_name", "site", "cell_name", "location", "site_address", "tower", "ชื่อเสา", "ตำแหน่ง", "ที่ตั้งเสา"],
    "lat": ["lat", "latitude", "ละติจูด"],
    "lon": ["lon", "long", "lng", "longitude", "ลองจิจูด"],
    "azimuth": ["azimuth", "az", "bearing", "sector_azimuth", "ทิศทางเสา", "มุม"],
}

DATE_FORMATS = (
    "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y/%m/%d %H:%M:%S",
    "%d-%m-%Y %H:%M:%S", "%Y%m%d%H%M%S", "%m/%d/%Y %I:%M:%S %p", "%d/%m/%Y", "%Y-%m-%d",
)


def _norm(h: Any) -> str:
    return re.sub(r"[\s\-./()]+", "_", str(h or "").strip().lower()).strip("_")


def map_columns(header: list[Any]) -> dict[str, int]:
    found: dict[str, int] = {}
    normed = [_norm(h) for h in header]
    for key, aliases in ALIASES.items():
        al = [_norm(a) for a in aliases]
        for i, h in enumerate(normed):
            if h in al and i not in found.values():
                found[key] = i
                break
    return found


def parse_dt(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        dt = None
        for fmt in DATE_FORMATS:
            try:
                dt = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        if dt is None:
            try:
                dt = datetime.fromisoformat(text)
            except ValueError:
                return None
    if dt.year > 2400:  # Buddhist era
        dt = dt.replace(year=dt.year - 543)
    return dt


def parse_duration(value: Any) -> int:
    if value in (None, ""):
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if ":" in text:
        parts = [int(float(p or 0)) for p in text.split(":")]
        while len(parts) < 3:
            parts.insert(0, 0)
        return parts[-3] * 3600 + parts[-2] * 60 + parts[-1]
    try:
        return int(float(text))
    except ValueError:
        return 0


def _float(value: Any) -> float | None:
    try:
        v = float(str(value).strip())
        return v if v == v else None
    except (TypeError, ValueError):
        return None


def read_table(name: str, data: bytes) -> list[list[Any]]:
    if name.lower().endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook

        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        ws = wb.active
        return [list(r) for r in ws.iter_rows(values_only=True)]
    for enc in ("utf-8-sig", "cp874", "tis-620", "latin-1"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|") if text.strip() else csv.excel
    return [row for row in csv.reader(io.StringIO(text), dialect)]


def parse(name: str, data: bytes) -> dict[str, Any]:
    table = read_table(name, data)
    header_row, cols = 0, {}
    for i, row in enumerate(table[:15]):
        cols = map_columns(row)
        if "a" in cols and "b" in cols:
            header_row = i
            break
    if "a" not in cols or "b" not in cols:
        raise ValueError("cdr_columns_not_found")
    rows = [r for r in table[header_row + 1:] if r and any(c not in (None, "") for c in r)]

    def cell(row: list[Any], key: str) -> Any:
        i = cols.get(key)
        return row[i] if i is not None and i < len(row) else None

    counts: Counter[str] = Counter()
    for r in rows:
        for k in ("a", "b"):
            n = normalize_phone(str(cell(r, k) or ""))
            if n:
                counts[n] += 1
    target = counts.most_common(1)[0][0] if counts else ""
    calls, sms, skipped = [], [], 0
    for r in rows:
        a = normalize_phone(str(cell(r, "a") or ""))
        b = normalize_phone(str(cell(r, "b") or ""))
        dt = parse_dt(cell(r, "datetime"))
        if dt is None and cols.get("date") is not None:
            d = cell(r, "date")
            t = cell(r, "time")
            dt = parse_dt(f"{d} {t}" if t not in (None, "") and not isinstance(d, datetime) else d)
            if dt is not None and isinstance(t, str) and isinstance(d, datetime):
                dt = parse_dt(f"{d:%d/%m/%Y} {t}")
        if dt is None:
            skipped += 1
            continue
        rtype = str(cell(r, "type") or "").lower()
        if any(x in rtype for x in ("data", "gprs", "internet", "lte data")):
            skipped += 1
            continue
        dir_raw = str(cell(r, "direction") or "").lower()
        if dir_raw:
            out = any(x in dir_raw for x in ("mo", "out", "orig", "ออก"))
        elif "moc" in rtype or "mo_" in rtype or rtype.endswith("mo"):
            out = True
        elif "mtc" in rtype or "mt_" in rtype or rtype.endswith("mt"):
            out = False
        else:
            out = a == target
        other = b if a == target else a
        ts = local_ms(dt)
        if "sms" in rtype:
            sms.append(SmsMessage(address=other, body="", direction="out" if out else "in", timestamp=ts, thread=other, service="SMS"))
            continue
        az = _float(cell(r, "azimuth"))
        calls.append(CallRecord(
            number=other, direction="outgoing" if out else "incoming", timestamp=ts,
            duration=parse_duration(cell(r, "duration")), own_number=target,
            cell=str(cell(r, "cell") or ""), cell_end=str(cell(r, "cell_end") or ""),
            site=str(cell(r, "site") or ""), lat=_float(cell(r, "lat")), lon=_float(cell(r, "lon")),
            azimuth=int(az) if az is not None else None, location=str(cell(r, "site") or ""),
        ))
    calls.sort(key=lambda c: c.timestamp or 0, reverse=True)
    sms.sort(key=lambda m: m.timestamp or 0, reverse=True)
    return {"target": target, "calls": calls, "sms": sms, "skipped": skipped, "columns": sorted(cols), "rows": len(rows)}


def import_into(case: Case, name: str, data: bytes, examiner: str = "") -> dict[str, Any]:
    parsed = parse(name, data)
    target = parsed["target"]
    device = {
        "platform": "cdr", "serial": target, "brand": "CDR", "model": "CDR", "market_name": f"CDR {target}",
        "phone_number": target, "os_version": "", "accounts": [], "extra": {"source_file": name, "rows": str(parsed["rows"])},
        "restricted": {},
    }
    ext = case.create_extraction(device, "cdr", examiner)
    raw = ext.raw_dir / Path(name).name
    raw.write_bytes(data)
    ext.register_file(raw, f"import:{name}")
    ext.audit("cdr.import", f"{name}: target={target} rows={parsed['rows']} skipped={parsed['skipped']} columns={','.join(parsed['columns'])}")
    ext.set_records("calls", [c.to_dict() for c in parsed["calls"]])
    ext.set_records("sms", [m.to_dict() for m in parsed["sms"]])
    for kind in ALL_KINDS:
        if kind not in ("calls", "sms"):
            ext.set_unavailable(kind, "not_supported", "CDR")
    counts = ext.finish("completed")
    return {"extraction_id": ext.id, "target": target, "counts": counts, "skipped": parsed["skipped"], "columns": parsed["columns"]}


# ── demo CDR ────────────────────────────────────────────────────────────
TOWERS = [
    ("BKK-Lat Phrao 2", 13.8160, 100.5610), ("BKK-Ratchada 5", 13.7790, 100.5740), ("BKK-Huai Khwang", 13.7680, 100.5790),
    ("BKK-Bang Na 3", 13.6680, 100.6040), ("BKK-Sukhumvit 71", 13.7230, 100.6010), ("BKK-On Nut", 13.7050, 100.6010),
    ("BKK-Siam", 13.7460, 100.5340), ("BKK-Silom", 13.7290, 100.5340), ("NBI-Pak Kret", 13.9130, 100.4980),
    ("SPK-Bang Phli", 13.6070, 100.7060), ("BKK-Don Mueang", 13.9130, 100.6060), ("BKK-Min Buri", 13.8130, 100.7480),
]


def demo_cdr_bytes(target: str, partners: list[str], seed: int = 777, days: int = 30, n: int = 420) -> bytes:
    """A realistic CDR export (CSV, Buddhist-era dates) for training and tests."""
    rng = random.Random(seed)
    now = datetime.now().replace(microsecond=0)
    home, work = TOWERS[3], TOWERS[1]
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["A_NUMBER", "B_NUMBER", "START_TIME", "DURATION", "RECORD_TYPE", "CELL_ID", "SITE_NAME", "LATITUDE", "LONGITUDE", "AZIMUTH"])
    for _ in range(n):
        day = now - timedelta(days=rng.random() * days)
        hour = rng.choices(range(24), weights=[2, 1, 1, 1, 1, 2, 4, 6, 8, 8, 7, 7, 8, 7, 6, 6, 7, 8, 9, 9, 8, 6, 4, 3])[0]
        dt = day.replace(hour=hour, minute=rng.randint(0, 59), second=rng.randint(0, 59))
        if hour < 7 or hour >= 21:
            site = home
        elif 9 <= hour < 17 and rng.random() < 0.7:
            site = work
        else:
            site = rng.choice(TOWERS)
        az = rng.choice([0, 120, 240])
        cell_id = f"520-01-{1000 + TOWERS.index(site) * 37}-{az // 120 + 1}"
        partner = rng.choice(partners) if rng.random() < 0.8 else "0" + rng.choice("689") + "".join(str(rng.randint(0, 9)) for _ in range(8))
        outgoing = rng.random() < 0.5
        a, b = (target, partner) if outgoing else (partner, target)
        kind = rng.choices(["VOICE", "SMS"], weights=[78, 22])[0]
        dur = 0 if kind == "SMS" else int(rng.expovariate(1 / 120)) + 3
        be = dt.replace(year=dt.year + 543)
        w.writerow([a, b, be.strftime("%d/%m/%Y %H:%M:%S"), dur, f"{kind}-{'MO' if outgoing else 'MT'}", cell_id, site[0],
                    f"{site[1] + rng.uniform(-0.002, 0.002):.6f}", f"{site[2] + rng.uniform(-0.002, 0.002):.6f}", az])
    return out.getvalue().encode("utf-8-sig")
