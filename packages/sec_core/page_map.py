"""Page-anchor resolution for cross-reference-index filings (Intel/Citi/GE).

The main document of a wrapper 10-K is an index whose entries point to page
ranges of a separately-paginated body ("Item 1A. Risk Factors  Pages 37-51").
That body prints its page numbers as footer artifacts, which normalize to bare
"\\d+" lines. We recover a page->offset map from the longest monotonic run of
those markers, so a page range resolves to a real source-exact span — turning
an honest pointer into actual extracted content, robustly (the page numbers are
printed data, not a fragile title guess).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from sec_core.normalize import NormalizedDocument

_BARE_NUM = re.compile(r"\d{1,4}")
_PAGE_RANGE = re.compile(r"(\d{1,4})\s*[-–]\s*(\d{1,4})")


@dataclass
class PageMap:
    marker_start: dict[int, int] = field(default_factory=dict)  # page -> offset of its footer line start
    marker_end: dict[int, int] = field(default_factory=dict)    # page -> offset of its footer line end
    lo_page: int = 0
    hi_page: int = 0

    @property
    def ok(self) -> bool:
        return self.hi_page - self.lo_page >= 5  # a real body has many pages


def build_page_map(doc: NormalizedDocument) -> PageMap:
    markers = [(ln.start, ln.end, int(ln.text.strip()))
               for ln in doc.lines if _BARE_NUM.fullmatch(ln.text.strip())]
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
    pm = PageMap()
    for start, end, page in best:
        pm.marker_start.setdefault(page, start)
        pm.marker_end.setdefault(page, end)
    if best:
        pm.lo_page, pm.hi_page = best[0][2], best[-1][2]
    return pm


def resolve_page_ref(pm: PageMap, page_ref: str) -> tuple[int, int] | None:
    """Map a page reference string ('Pages 37-51', '49-62', '11, 32') to a
    (start_offset, end_offset) span, or None if it can't be resolved."""
    if not pm.ok:
        return None
    m = _PAGE_RANGE.search(page_ref)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
    else:
        nums = [int(x) for x in _BARE_NUM.findall(page_ref)]
        if not nums:
            return None
        a = b = nums[0]
    if not (pm.lo_page <= a <= pm.hi_page):
        return None
    b = min(b, pm.hi_page)
    # content of page A begins just after the page-(A-1) footer (or at the run
    # start); content of page B ends at the page-B footer marker.
    start = pm.marker_end.get(a - 1)
    if start is None:
        start = pm.marker_start.get(a)
    end = pm.marker_start.get(b)
    if start is None or end is None or end <= start:
        return None
    return start, end
