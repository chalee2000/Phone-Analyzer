"""Line wrapping for Thai text in PDF tables.

Thai is written without spaces between words, so ReportLab cannot find break
points on its own. We break lines between grapheme clusters, never before a
combining mark or a following vowel and never right after a leading vowel, and
prefer real spaces when there are any. The text itself is never changed.
"""

from __future__ import annotations

from typing import Callable

COMBINING = set(range(0x0E31, 0x0E32)) | set(range(0x0E34, 0x0E3B)) | set(range(0x0E47, 0x0E4F))
FOLLOWING = {0x0E30, 0x0E32, 0x0E33, 0x0E45, 0x0E46}  # ะ า ำ ๅ ๆ
LEADING = set(range(0x0E40, 0x0E45))  # เ แ โ ใ ไ


def can_break_before(text: str, i: int) -> bool:
    if i <= 0 or i >= len(text):
        return False
    cur, prev = ord(text[i]), ord(text[i - 1])
    if cur in COMBINING or cur in FOLLOWING:
        return False
    if prev in LEADING:
        return False
    return True


def wrap(text: str, width: float, measure: Callable[[str], float]) -> list[str]:
    lines: list[str] = []
    for para in text.replace("\r\n", "\n").split("\n"):
        start = 0
        while start < len(para):
            if measure(para[start:]) <= width:
                lines.append(para[start:])
                break
            # Longest prefix that fits.
            lo, hi = start + 1, len(para)
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if measure(para[start:mid]) <= width:
                    lo = mid
                else:
                    hi = mid - 1
            end = lo
            space = para.rfind(" ", start + 1, end + 1)
            if space > start and space - start > (end - start) * 0.5:
                cut = space + 1
            else:
                cut = end
                while cut > start + 1 and not can_break_before(para, cut):
                    cut -= 1
                if cut <= start + 1:
                    cut = max(end, start + 1)
            lines.append(para[start:cut].rstrip(" "))
            start = cut
        if not para:
            lines.append("")
    return lines
