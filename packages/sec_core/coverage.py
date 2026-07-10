"""Body-coverage completeness (the INTC lesson: nothing may be silently
dropped). Item segments are a best-effort classification; on a
cross-reference-index filing their resolved page-anchor spans are disjoint
and leave GAPS — document body that belongs to no item. Those gaps used to
be unreachable, so real prose (Intel's critical-accounting-estimate
paragraphs, which fall between two resolved ranges) simply vanished from
every view.

The principle here is completeness over classification: the union of what we
expose must equal the whole body. compute_gaps() returns every uncovered
region so the viewer can surface it as 'unclassified' content — we would
rather show text we could not label than drop it.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Gap:
    start: int
    end: int
    after_code: str   # item whose span ends just before this gap ("" = document head)
    before_code: str  # item whose span starts just after this gap ("" = document tail)
    preview: str      # first line of real text in the gap, for the row label

    @property
    def chars(self) -> int:
        return self.end - self.start


def compute_gaps(text: str, segments, min_chars: int = 120) -> list[Gap]:
    """Regions of `text` covered by NO item span, so nothing is unreachable.
    Spans are merged first (item spans on wrapper filings overlap), so an
    overlap never manufactures a false gap. Gaps below min_chars (whitespace /
    furniture between adjacent items) are skipped."""
    # (start, end, code) for every item that actually has a body
    spans = sorted((s.start_offset, s.end_offset, s.item_code)
                   for s in segments if s.end_offset > s.start_offset)
    gaps: list[Gap] = []
    cursor = 0
    after_code = ""
    # walk the merged coverage; a hole before the next span's start is a gap
    merged: list[list] = []
    for a, b, code in spans:
        if merged and a <= merged[-1][1]:
            if b > merged[-1][1]:
                merged[-1][1] = b
                merged[-1][2] = code  # last item touching this covered run
        else:
            merged.append([a, b, code])
    for a, b, code in merged:
        if a - cursor >= min_chars and text[cursor:a].strip():
            gaps.append(Gap(start=cursor, end=a, after_code=after_code,
                            before_code=code, preview=_preview(text, cursor, a)))
        cursor = b
        after_code = code
    if len(text) - cursor >= min_chars and text[cursor:].strip():
        gaps.append(Gap(start=cursor, end=len(text), after_code=after_code,
                        before_code="", preview=_preview(text, cursor, len(text))))
    return gaps


def _preview(text: str, start: int, end: int, limit: int = 70) -> str:
    for line in text[start:end].splitlines():
        line = line.strip()
        if len(line) >= 8:
            return line[:limit]
    return text[start:end].strip()[:limit]


def coverage_ratio(text: str, segments) -> float:
    if not text:
        return 1.0
    spans = sorted((s.start_offset, s.end_offset)
                   for s in segments if s.end_offset > s.start_offset)
    covered, hi = 0, -1
    for a, b in spans:
        a = max(a, hi)
        if b > a:
            covered += b - a
            hi = b
    return covered / len(text)
