"""Page-anchor resolution for wrapper 10-Ks (Intel/Citi/GE and JPM/XOM).

A cross-reference-index filing's main document is an index whose entries point
to page ranges of a separately-paginated body ("Item 1A. Risk Factors  Pages
37-51"); a JPM/XOM-style wrapper keeps real item headings but defers Items
7/7A/8 via stubs into a Financial Section bound after the last item. Either
way the body prints its page numbers as footer artifacts, which normalize to
bare "\\d+" lines. We recover a page->offset map from the longest monotonic run
of those markers (optionally restricted to a document region, so an appended
annual report's own pagination is not confused with the main part's), so a
page range resolves to a real source-exact span — turning an honest pointer
into actual extracted content, robustly (the page numbers are printed data,
not a fragile title guess).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from sec_core.normalize import NormalizedDocument

_BARE_NUM = re.compile(r"\d{1,4}")
_PAGE_RANGE = re.compile(r"(\d{1,4})\s*[-–]\s*(\d{1,4})")
# successive printed pages never jump this far; a larger gap in the LIS chain
# means a stray year line ("2025") or unrelated number got threaded in
_MAX_PAGE_GAP = 100


@dataclass
class PageMap:
    marker_start: dict[int, int] = field(default_factory=dict)  # page -> offset of its footer line start
    marker_end: dict[int, int] = field(default_factory=dict)    # page -> offset of its footer line end
    lo_page: int = 0
    hi_page: int = 0

    @property
    def ok(self) -> bool:
        return self.hi_page - self.lo_page >= 5  # a real body has many pages


def build_page_map(doc: NormalizedDocument, start: int = 0, end: int | None = None) -> PageMap:
    """Recover the page->offset map, optionally from the [start, end) region
    only (a wrapper's appended Financial Section is paginated independently of
    the main part, so its map must not mix in the main part's footers)."""
    hi = len(doc.text) if end is None else end
    markers = [(ln.start, ln.end, int(ln.text.strip()))
               for ln in doc.lines
               if start <= ln.start < hi and _BARE_NUM.fullmatch(ln.text.strip())]
    # The body's true pagination is the longest strictly-increasing subsequence
    # of page numbers taken in document (offset) order. LIS is robust to
    # front-matter noise, duplicate header/footer numbers, and missing markers —
    # far better than a single greedy run that snaps at the first anomaly.
    pages = [m[2] for m in markers]
    n = len(pages)
    best: list[tuple[int, int, int]] = []
    if n:
        length = [1] * n
        prev = [-1] * n
        for i in range(n):
            for j in range(i):
                if pages[j] < pages[i] and length[j] + 1 > length[i]:
                    length[i] = length[j] + 1
                    prev[i] = j
        end = max(range(n), key=lambda k: length[k])
        chain = []
        while end != -1:
            chain.append(markers[end])
            end = prev[end]
        best = list(reversed(chain))
    if best:
        # split the chain at implausible jumps (stray year lines like "2025"
        # thread into an increasing subsequence); keep the longest real run
        runs: list[list[tuple[int, int, int]]] = [[best[0]]]
        for m in best[1:]:
            if m[2] - runs[-1][-1][2] > _MAX_PAGE_GAP:
                runs.append([])
            runs[-1].append(m)
        best = max(runs, key=len)
    pm = PageMap()
    for start, end, page in best:
        pm.marker_start.setdefault(page, start)
        pm.marker_end.setdefault(page, end)
    if best:
        pm.lo_page, pm.hi_page = best[0][2], best[-1][2]
    return pm


def resolve_page_ref(pm: PageMap, page_ref: str,
                     avoid: object = ()) -> tuple[int, int] | None:
    """Map a page reference string to a (start_offset, end_offset) span. The
    string may list several ranges/pages ("Pages 3-5, 18; Pages 3-24, 33"); we
    try them EARLIEST-start first (an item's body begins at its first page;
    later ranges are continuation or supplementary), and the caller marks the
    result partial + needs_review because the remaining scattered references
    are not included. Earliest-start beats widest-range: Citi lists MD&A as
    "8-36, 64-120" and Item 7A as "64-120, ..." — widest gave BOTH the same
    64-120 span; earliest keeps MD&A at 8-36.

    `avoid` is a set of (start,end) spans already claimed by earlier items; a
    range whose span collides with a claimed one is skipped so two distinct
    items never resolve to a byte-identical span. INTC Item 15 lists
    "56-108, 110-115" where 56-108 is Item 8's financials it merely references
    and 110-115 is its OWN exhibit index — skipping the claimed 56-108 lands
    Item 15 on its real 110-115 body; a single-page duplicate with no free
    alternative (INTC 1C and 9B both "Page 54") returns None so the caller
    falls back to an honest pointer instead of a duplicate body."""
    if not pm.ok:
        return None
    # candidate (start_page, end_page) pairs: explicit ranges, then bare pages
    ranges = [(int(m.group(1)), int(m.group(2))) for m in _PAGE_RANGE.finditer(page_ref)]
    if not ranges:
        nums = [int(x) for x in _BARE_NUM.findall(page_ref)]
        ranges = [(n, n) for n in nums]
    # keep only ranges that fall inside the recovered pagination
    valid = [(a, min(b, pm.hi_page)) for a, b in ranges if pm.lo_page <= a <= pm.hi_page]
    if not valid:
        return None
    claimed = set(avoid)
    # earliest-start first, wider as tiebreak; take the first whose span is free
    for a, b in sorted(valid, key=lambda r: (r[0], -(r[1] - r[0]))):
        # content of page A begins just after the page-(A-1) footer (or run
        # start); content of page B ends at the page-B footer marker.
        start = pm.marker_end.get(a - 1) or pm.marker_start.get(a)
        end = pm.marker_start.get(b) or pm.marker_end.get(b)
        if start is None or end is None or end <= start:
            continue
        if (start, end) in claimed:
            continue
        return start, end
    return None
