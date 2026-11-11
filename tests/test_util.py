from datetime import datetime, timezone

from spni.export.thai_wrap import COMBINING, FOLLOWING, wrap
from spni.util import cocoa_to_ms, normalize_phone, unix_to_ms


def test_normalize_thai_numbers():
    assert normalize_phone("+66 81-234-5678") == "0812345678"
    assert normalize_phone("66812345678") == "0812345678"
    assert normalize_phone("(02) 123 4567") == "021234567"
    assert normalize_phone("tel:+66812345678") == "0812345678"
    assert normalize_phone("AIS") == "AIS"  # sender names stay untouched
    assert normalize_phone("*123#") == "*123#"
    assert normalize_phone(None) == ""


def test_cocoa_seconds_and_nanoseconds():
    expected = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    seconds = 725_760_000  # 2024-01-01 in Apple epoch seconds
    assert cocoa_to_ms(seconds) == expected
    assert cocoa_to_ms(seconds * 1_000_000_000) == expected
    assert cocoa_to_ms(0) is None


def test_unix_seconds_and_millis():
    assert unix_to_ms("1700000000") == 1_700_000_000_000
    assert unix_to_ms(1_700_000_000_123) == 1_700_000_000_123
    assert unix_to_ms("NULL") is None


def test_thai_wrap_keeps_clusters_together():
    text = "ที่อยู่ส่งของ 99/12 หมู่ 5 ตำบลบางพลีใหญ่ อำเภอบางพลี จังหวัดสมุทรปราการ เบอร์ติดต่อพี่น้ำผึ้งที่ร้านกาแฟ"
    lines = wrap(text, 60, lambda s: len(s) * 4.0)
    assert "".join(lines).replace(" ", "") == text.replace(" ", "")
    for line in lines[1:]:
        assert ord(line[0]) not in COMBINING and ord(line[0]) not in FOLLOWING
    assert all(len(line) * 4.0 <= 60 for line in lines)


def test_local_ms_matches_python_and_survives_1970(monkeypatch):
    """Windows raises OSError for local times near 1970; the fallback must give the same value."""
    import time
    from datetime import datetime, timezone

    from spni.util import _local_ms_fallback, local_ms

    monkeypatch.setenv("TZ", "Asia/Bangkok")
    time.tzset()
    try:
        for dt in (datetime(1960, 5, 1, 12), datetime(1970, 1, 1, 7), datetime(1970, 1, 1), datetime(2026, 11, 11, 15, 56)):
            assert _local_ms_fallback(dt) == local_ms(dt) == int(dt.timestamp() * 1000)
        assert local_ms(datetime(1970, 1, 1, 7)) == 0  # Android's "installed at epoch" in UTC+7
        aware = datetime(1969, 12, 31, tzinfo=timezone.utc)
        assert _local_ms_fallback(aware) == local_ms(aware) == -86_400_000
    finally:
        monkeypatch.delenv("TZ")
        time.tzset()
