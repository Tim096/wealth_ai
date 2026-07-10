"""TOC false-positive defence (SPEC 7.9).

Every rejection is explainable: a candidate is never silently dropped — it
carries the list of TOC signals that condemned it, and the boundary resolver
records those as toc_rejection evidence on the winning candidate's segment.
"""

from __future__ import annotations

import re

from sec_core.headings import HeadingCandidate
from sec_core.normalize import NormalizedDocument

_TOC_MARKER_RE = re.compile(r"table\s+of\s+contents|\bindex\b", re.IGNORECASE)

# Signals and their weights. Classification threshold is 2.0: no single weak
# signal can reject a candidate, and the strongest single signal (anchor link)
# is decisive on its own only when duplicates exist later in the document.
_WEIGHTS = {
    "anchor_link": 2.0,
    "trailing_page_number": 1.0,
    "near_toc_marker": 1.0,
    "dense_cluster": 1.0,
    "short_section": 0.75,
}
_THRESHOLD = 2.0


def assess_toc(doc: NormalizedDocument, candidates: list[HeadingCandidate]) -> None:
    """Mutates candidates: sets toc_rejected + toc_reasons."""

    marker_positions = [m.start() for m in _TOC_MARKER_RE.finditer(doc.text)]
    starts = sorted(c.start for c in candidates)
    last_start_by_code: dict[str, int] = {}
    for c in candidates:
        last_start_by_code[c.code] = max(last_start_by_code.get(c.code, -1), c.start)

    for cand in candidates:
        signals: dict[str, str] = {}

        if cand.in_toc_link:
            signals["anchor_link"] = "heading line sits inside an internal anchor link (<a href=\"#...\">)"
        if cand.trailing_page_number:
            signals["trailing_page_number"] = "line ends with a page number / dotted leaders"
        near = [p for p in marker_positions if 0 <= cand.start - p <= 3000]
        if near:
            signals["near_toc_marker"] = (
                f"'Table of Contents' marker {cand.start - max(near)} chars before this line"
            )
        neighbours = [s for s in starts if s != cand.start and abs(s - cand.start) <= 1500]
        after = [s for s in neighbours if s > cand.start]
        # a real body heading right after the TOC has many neighbours BEFORE it
        # but a full section body after it; a TOC line has neighbours on both
        # sides (or immediately after). Require following neighbours.
        if len(neighbours) >= 4 and len(after) >= 2:
            signals["dense_cluster"] = (
                f"{len(neighbours)} other item headings within 1500 chars "
                f"({len(after)} after) — heading list, not body"
            )
        following = [s for s in starts if s > cand.start]
        if following and following[0] - cand.end < 300:
            signals["short_section"] = (
                f"only {following[0] - cand.end} chars before the next item heading — no real section body"
            )

        score = sum(_WEIGHTS[k] for k in signals)
        has_later_duplicate = last_start_by_code[cand.code] > cand.start

        if score >= _THRESHOLD and has_later_duplicate:
            cand.toc_rejected = True
            cand.toc_reasons = [f"{k}: {v}" for k, v in signals.items()]
        elif score >= _THRESHOLD and not has_later_duplicate:
            # Looks like TOC but there is no body candidate to prefer. Keep it,
            # flag it — boundary resolver will degrade status, never fake pass.
            cand.toc_reasons = [f"{k}: {v}" for k, v in signals.items()] + [
                "kept despite TOC signals: no later candidate exists for this item"
            ]
