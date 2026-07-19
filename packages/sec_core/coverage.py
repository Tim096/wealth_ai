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


@dataclass
class Block:
    """One contiguous run of the document owned by exactly one region."""
    start: int
    end: int
    code: str          # item code, or "" for an unclassified (gap) run

    @property
    def chars(self) -> int:
        return self.end - self.start


def partition_document(text: str, segments) -> list[Block]:
    """Capture first, classify second: split the WHOLE document into
    non-overlapping, document-ordered blocks whose union is [0, len(text)).
    Every character belongs to exactly one block, so nothing is unreachable and
    a position is never ambiguous.

    Item spans on wrapper/cross-reference filings overlap (e.g. Item 2 nested
    inside Item 1, Item 7 straddling Item 1). Each character is attributed to
    the TIGHTEST span covering it (smallest width wins; ties broken toward the
    later-starting, i.e. more specific, item). Characters no item claims form a
    "" (unclassified) block. This keeps classification intact — every item
    still owns its span — while guaranteeing 100% coverage."""
    n = len(text)
    if n == 0:
        return []
    # A multi-range item owns only its actual (start, end) spans — expanding it
    # here (rather than its bounding envelope) keeps between-range prose as an
    # honest unclassified gap instead of falsely attributing it to this item.
    spans = [(a, min(b, n), s.item_code)
             for s in segments
             for a, b in (getattr(s, "source_ranges", None) or [(s.start_offset, s.end_offset)])
             if b > a and a < n]
    pts = {0, n}
    for a, b, _ in spans:
        pts.add(a)
        pts.add(b)
    ordered = sorted(p for p in pts if 0 <= p <= n)
    raw: list[Block] = []
    for lo, hi in zip(ordered, ordered[1:]):
        if lo >= hi:
            continue
        best_key = None
        owner = ""
        for a, b, code in spans:
            if a <= lo and b >= hi:                 # this span fully covers the slice
                key = (b - a, -a)                   # tightest, then later-starting
                if best_key is None or key < best_key:
                    best_key, owner = key, code
        raw.append(Block(lo, hi, owner))
    merged: list[Block] = []
    for blk in raw:                                  # coalesce adjacent same-owner runs
        if merged and merged[-1].code == blk.code:
            merged[-1].end = blk.end
        else:
            merged.append(blk)
    return merged


def region_at(offset: int, blocks: list[Block]) -> Block | None:
    """The block owning a document offset (binary search over the partition)."""
    lo, hi = 0, len(blocks) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        b = blocks[mid]
        if offset < b.start:
            hi = mid - 1
        elif offset >= b.end:
            lo = mid + 1
        else:
            return b
    return None


def gaps_from_blocks(text: str, blocks: list[Block], min_chars: int = 120) -> list[Gap]:
    """Return unclassified runs from an existing document partition."""
    gaps: list[Gap] = []
    for i, blk in enumerate(blocks):
        if blk.code != "":
            continue
        if blk.chars < min_chars or not text[blk.start:blk.end].strip():
            continue
        after = blocks[i - 1].code if i > 0 else ""
        before = blocks[i + 1].code if i + 1 < len(blocks) else ""
        gaps.append(Gap(start=blk.start, end=blk.end, after_code=after,
                        before_code=before, preview=_preview(text, blk.start, blk.end)))
    return gaps


def compute_gaps(text: str, segments, min_chars: int = 120) -> list[Gap]:
    """Every unclassified run, with items + gaps tiling the whole body."""
    return gaps_from_blocks(text, partition_document(text, segments), min_chars)


def _preview(text: str, start: int, end: int, limit: int = 70) -> str:
    for line in text[start:end].splitlines():
        line = line.strip()
        if len(line) >= 8:
            return line[:limit]
    return text[start:end].strip()[:limit]


def coverage_ratio(text: str, segments, blocks: list[Block] | None = None) -> float:
    if not text:
        return 1.0
    partition = blocks if blocks is not None else partition_document(text, segments)
    return sum(block.chars for block in partition if block.code) / len(text)
