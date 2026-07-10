"""Cross-reference-index filing detection (the Intel / Citi / GE class).

Some registrants file a 10-K whose main document is not the report body but a
*cross-reference index*: each item heading is immediately followed by a page
range ("Item 1A. Risk Factors  Pages 37-51", or Citi's "1A.Risk Factors49-62")
pointing into a separately-bound annual report. The real Item 1A/7/8 prose is
NOT in an addressable "Item N" section, so naive extraction returns tiny
ambiguous fragments — which is exactly the corner case that sinks most
submissions (they mark those fragments extracted/ok).

We detect the class from structure alone and classify honestly: the items
become `incorporated_by_reference` pointers to the annual-report page ranges,
flagged needs_review, rather than fake bodies. Full body resolution (following
the pointer into the annual-report exhibit) is a documented next step —
docs/insights_and_directions.md §2 — deliberately not shipped as a fragile
guess, because a wrong body is worse than an honest pointer.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field

from observability_core import sha256_text
from sec_core.confidence import ConfidenceBreakdown
from sec_core.confidence import ConfidenceComponent as CC
from sec_core.headings import VALID_CODES, HeadingCandidate
from sec_core.items import CANONICAL_ITEM_TITLES, ItemSegment
from sec_core.normalize import NormalizedDocument
from sec_core.page_map import build_page_map, resolve_page_ref

# a page reference right after a heading: "Pages 37-51", "49-62", "4-36, 121-127"
_PAGE_REF_RE = re.compile(
    r"^\s*(?:pages?\s*)?\d{1,4}(?:\s*[-–]\s*\d{1,4})?(?:\s*,\s*\d{1,4}(?:\s*[-–]\s*\d{1,4})?)*\s*$",
    re.IGNORECASE,
)

# structural thresholds
_MIN_CLUSTERED_ITEMS = 8      # need most of the 10-K's items in one block
_CLUSTER_SPAN = 8_000        # ...all within this many normalized chars
_MIN_PAGE_REF_RATIO = 0.25   # ...and a meaningful fraction point to page ranges
_MAX_INDEX_GAP = 300         # ...OR the headings are packed with no body between them
_NONE_LINE_RE = re.compile(r"^(none|not\s+applicable|\[?reserved\]?)\.?$", re.IGNORECASE)


@dataclass
class CrossRefIndex:
    detected: bool
    index_start: int = 0
    index_end: int = 0
    page_refs: dict[str, str] = field(default_factory=dict)  # item code -> page range text
    entries: dict[str, str] = field(default_factory=dict)    # item code -> line following the heading
    reason: str = ""


def _following_line(doc: NormalizedDocument, cand: HeadingCandidate) -> str:
    for ln in doc.lines:
        if ln.start >= cand.end and ln.text.strip():
            return ln.text.strip()
    return ""


def detect_cross_reference_index(
    doc: NormalizedDocument, candidates: list[HeadingCandidate]
) -> CrossRefIndex:
    if len(candidates) < _MIN_CLUSTERED_ITEMS:
        return CrossRefIndex(detected=False, reason="too few item headings")

    starts = sorted(c.start for c in candidates)
    # find the densest window containing the most distinct item codes
    best_lo, best_hi, best_codes = 0, 0, set()
    for c in candidates:
        window = [x for x in candidates if 0 <= x.start - c.start <= _CLUSTER_SPAN]
        codes = {x.code for x in window}
        if len(codes) > len(best_codes):
            best_codes = codes
            best_lo = c.start
            best_hi = max(x.end for x in window)

    if len(best_codes) < _MIN_CLUSTERED_ITEMS:
        return CrossRefIndex(
            detected=False,
            reason=f"only {len(best_codes)} item codes within {_CLUSTER_SPAN} chars — real body, not an index",
        )

    # Critical discriminator: a normal filing has a TOC/index at the top AND
    # real item bodies elsewhere. A cross-reference-index filing has ONLY the
    # index. If several item codes have a body candidate OUTSIDE the cluster,
    # this is a normal TOC, not an index — do not hijack it.
    outside_codes = {c.code for c in candidates if not (best_lo <= c.start <= best_hi)}
    if len(outside_codes) >= 3:
        return CrossRefIndex(
            detected=False,
            reason=f"{len(outside_codes)} item codes have body candidates outside the cluster — "
                   f"normal filing with a TOC, not a cross-reference index",
        )

    clustered = [c for c in candidates if best_lo <= c.start <= best_hi]
    page_refs: dict[str, str] = {}
    entries: dict[str, str] = {}
    for c in clustered:
        nxt = _following_line(doc, c)
        entries.setdefault(c.code, nxt)
        # the page ref may be glued to the title (Citi "1A.Risk Factors49-62")
        trailing = re.search(r"(\d{1,4}(?:\s*[-–]\s*\d{1,4})?(?:\s*,\s*\d[\d\s,\-–]*)?)\s*$",
                             c.heading_text)
        if _PAGE_REF_RE.match(nxt):
            page_refs.setdefault(c.code, nxt)
        elif trailing and c.code not in page_refs:
            page_refs.setdefault(c.code, trailing.group(1).strip())

    ratio = len(page_refs) / max(1, len(best_codes))
    clustered_starts = sorted(c.start for c in clustered)
    gaps = [clustered_starts[i + 1] - clustered_starts[i] for i in range(len(clustered_starts) - 1)]
    median_gap = statistics.median(gaps) if gaps else 10**9
    # An index is confirmed by EITHER page-range pointers OR headings packed so
    # tightly there is no room for real bodies between them. (Normal filings are
    # already excluded above by having body candidates outside the cluster.)
    if ratio < _MIN_PAGE_REF_RATIO and median_gap > _MAX_INDEX_GAP:
        return CrossRefIndex(
            detected=False,
            reason=f"only {ratio:.0%} page references and median heading gap {median_gap:.0f} "
                   f"chars — item bodies present, not an index",
        )

    trigger = (f"{len(page_refs)} point to annual-report page ranges"
               if ratio >= _MIN_PAGE_REF_RATIO
               else f"median heading gap {median_gap:.0f} chars (no bodies between items)")
    return CrossRefIndex(
        detected=True,
        index_start=best_lo,
        index_end=best_hi,
        page_refs=page_refs,
        entries=entries,
        reason=(f"{len(best_codes)} item headings clustered within {best_hi - best_lo} chars; "
                f"{trigger} — cross-reference index; item bodies are not in addressable Item "
                f"sections of the main document"),
    )


_BARE_INDEX_RE = re.compile(
    r"^\s*(\d{1,2}[A-C]?)\.\s*([A-Za-z][A-Za-z '&,./()-]{3,70}?)\s*(\d[\d\s,\-–]*)?$"
)


def scan_bare_index(doc: NormalizedDocument) -> CrossRefIndex:
    """Fallback for cross-reference indexes whose entries omit the word 'Item'
    (Citi: '1A.Risk Factors49-62'). Standard heading detection finds nothing,
    so we scan lines directly for '<code>.<title><pageref>' clustered together
    and confirmed by canonical-title similarity."""
    from difflib import SequenceMatcher

    hits: list[tuple[int, str, str, str]] = []  # (line_start, code, title, pageref)
    for ln in doc.lines:
        m = _BARE_INDEX_RE.match(ln.text)
        if not m:
            continue
        code = m.group(1).upper()
        if code not in CANONICAL_ITEM_TITLES:
            continue
        title = m.group(2).strip()
        sim = SequenceMatcher(None, title.casefold(),
                              CANONICAL_ITEM_TITLES[code].casefold()).ratio()
        if sim < 0.5:
            continue
        hits.append((ln.start, code, title, (m.group(3) or "").strip()))

    if len({h[1] for h in hits}) < _MIN_CLUSTERED_ITEMS:
        return CrossRefIndex(detected=False, reason="no bare cross-reference index found")

    # keep the densest cluster
    starts = [h[0] for h in hits]
    lo = min(starts)
    window = [h for h in hits if h[0] - lo <= _CLUSTER_SPAN * 3]
    if len({h[1] for h in window}) < _MIN_CLUSTERED_ITEMS:
        return CrossRefIndex(detected=False, reason="bare index entries not clustered")

    entries: dict[str, str] = {}
    page_refs: dict[str, str] = {}
    for _, code, title, pageref in window:
        entries.setdefault(code, pageref or title)
        if pageref:
            page_refs.setdefault(code, pageref)
    return CrossRefIndex(
        detected=True,
        index_start=min(h[0] for h in window),
        index_end=max(h[0] for h in window),
        page_refs=page_refs,
        entries=entries,
        reason=(f"{len(set(h[1] for h in window))} bare item entries ('<code>. <title>') "
                f"clustered, {len(page_refs)} with page references — cross-reference index "
                f"without the word 'Item'; item bodies are in the bound annual report"),
    )


def build_cross_reference_segments(
    doc: NormalizedDocument, index: CrossRefIndex, filing_id: str
) -> tuple[list[ItemSegment], dict[str, ConfidenceBreakdown]]:
    """Honest segments for a cross-reference-index filing: each item is a
    pointer into the annual report, never a fabricated body."""
    page_map = build_page_map(doc)
    segments: list[ItemSegment] = []
    breakdowns: dict[str, ConfidenceBreakdown] = {}
    for code in VALID_CODES:
        canonical = CANONICAL_ITEM_TITLES[code]
        heading = f"Item {code}. {canonical}"
        following = index.entries.get(code, "")

        if code in index.page_refs:
            ref = index.page_refs[code]
            # try to RESOLVE the pointer to a real source-exact span via the
            # printed page-number footers (robust: printed data, not a guess)
            span = resolve_page_ref(page_map, ref)
            if span is not None and span[1] - span[0] > 400:
                start, end = span
                text = doc.slice(start, end)
                bd = ConfidenceBreakdown(components=[
                    CC(name="content_substantiveness", score=1.4, max_score=2.0,
                       reason=f"resolved page range {ref} to a {end - start}-char body span"),
                    CC(name="heading_strength", score=1.5, max_score=2.0,
                       reason="page anchor resolved from printed page-number footers"),
                ])
                breakdowns[code] = bd
                segments.append(ItemSegment(
                    filing_id=filing_id, item_code=code, canonical_title=canonical,
                    extracted_heading=heading, start_offset=start, end_offset=end,
                    text_sha256=sha256_text(text), status="partial", confidence=bd.total,
                    provenance="resolved_from_page_anchor", needs_review=True,
                    warnings=[
                        f"cross-reference-index 10-K: Item body resolved from the annual-report "
                        f"page range {ref} via printed page-number anchors (source-exact span). "
                        "Marked partial + needs_review because page-boundary alignment is "
                        "heuristic — verify start/end against the filing."],
                ))
                continue
            # could not resolve — honest pointer
            bd = ConfidenceBreakdown(components=[
                CC(name="content_substantiveness", score=0.0, max_score=2.0,
                   reason="cross-reference index: only a page pointer was found, not item body"),
                CC(name="heading_strength", score=1.0, max_score=2.0,
                   reason="item heading present in the cross-reference index"),
            ])
            breakdowns[code] = bd
            segments.append(ItemSegment(
                filing_id=filing_id, item_code=code, canonical_title=canonical,
                extracted_heading=heading, start_offset=index.index_start,
                end_offset=index.index_end, text_sha256="",
                status="incorporated_by_reference", confidence=bd.total,
                provenance="cross_reference_pointer", needs_review=True,
                warnings=[
                    "cross-reference-index 10-K: this item's body is NOT in an addressable Item "
                    f"section; the filing points to the bound annual report at page(s) {ref}, but "
                    "the page anchors could not be resolved — this is a pointer, not content."
                ],
            ))
        elif code == "6":
            segments.append(ItemSegment(
                filing_id=filing_id, item_code=code, canonical_title=canonical,
                extracted_heading=heading, start_offset=0, end_offset=0, text_sha256="",
                status="reserved", confidence=0.0, provenance="offset_exact_span",
                needs_review=False, warnings=[],
            ))
        elif _NONE_LINE_RE.match(following.strip()):
            # the index answers this item inline with None/Not applicable — a complete answer
            segments.append(ItemSegment(
                filing_id=filing_id, item_code=code, canonical_title=canonical,
                extracted_heading=heading, start_offset=0, end_offset=0, text_sha256="",
                status="missing", confidence=0.0, provenance="unresolved", needs_review=True,
                warnings=[f"cross-reference index lists item {code} as '{following.strip()[:20]}' "
                          "— treated as no-content but not source-span verified; needs_review"],
            ))
        elif code in index.entries:
            # named a subtopic but no addressable body in the main document
            bd = ConfidenceBreakdown(components=[
                CC(name="content_substantiveness", score=0.0, max_score=2.0,
                   reason="cross-reference index: item body is not in the main document"),
                CC(name="heading_strength", score=1.0, max_score=2.0,
                   reason="item heading present in the cross-reference index"),
            ])
            breakdowns[code] = bd
            segments.append(ItemSegment(
                filing_id=filing_id, item_code=code, canonical_title=canonical,
                extracted_heading=heading, start_offset=index.index_start,
                end_offset=index.index_end, text_sha256="",
                status="incorporated_by_reference", confidence=bd.total,
                provenance="cross_reference_pointer", needs_review=True,
                warnings=["cross-reference-index 10-K: item body is not in an addressable Item "
                          "section of the main document; content is in the bound annual report."],
            ))
        else:
            status = "missing"
            segments.append(ItemSegment(
                filing_id=filing_id, item_code=code, canonical_title=canonical,
                extracted_heading="", start_offset=0, end_offset=0, text_sha256="",
                status=status, confidence=0.0, provenance="unresolved", needs_review=True,
                warnings=[f"no cross-reference index entry found for item {code}"],
            ))
    return segments, breakdowns
