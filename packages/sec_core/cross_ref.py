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
flagged needs_review, rather than fake bodies. When the referenced body is
bound into the SAME document and prints page-number footers, the pointer IS
resolved to a real source-exact span (L237-252 below via sec_core/page_map.py,
provenance `resolved_from_page_anchor` — docs/insights_and_directions.md §2);
`reassemble_wrapper_bodies` does the same for the JPM/XOM wrapper class whose
stubs defer Items 7/7A/8 into an appended Financial Section. Only pointers to
truly external documents (the proxy statement) or without resolvable anchors
stay honest pointers, because a wrong body is worse than an honest pointer.
"""

from __future__ import annotations

import os
import re
import statistics
from bisect import bisect_left
from dataclasses import dataclass, field
from difflib import SequenceMatcher

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
    entry_span: dict[str, tuple[int, int]] = field(default_factory=dict)  # item code -> its own index-entry offsets
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

    clustered = sorted((c for c in candidates if best_lo <= c.start <= best_hi),
                       key=lambda c: c.start)
    page_refs: dict[str, str] = {}
    entries: dict[str, str] = {}
    entry_span: dict[str, tuple[int, int]] = {}
    for i, c in enumerate(clustered):
        nxt = _following_line(doc, c)
        entries.setdefault(c.code, nxt)
        # this item's OWN index entry: its heading line, extended to include the
        # immediately-following page-ref line — so an unresolved pointer shows
        # just its own entry, never the whole index block.
        if c.code not in entry_span:
            end = c.end
            for ln in doc.lines:
                if ln.start >= c.end and ln.text.strip():
                    end = ln.end if _PAGE_REF_RE.match(ln.text.strip()) else c.end
                    break
            entry_span[c.code] = (c.start, end)
        # Gather ALL page references in this item's whole index sub-block
        # (heading -> next item heading). An item's entry can list several
        # sub-topics each with their own page ranges (Intel Item 1 / Item 7);
        # reading only the first line misses most of them.
        sub_end = clustered[i + 1].start if i + 1 < len(clustered) else min(best_hi + 1, len(doc.text))
        sub = doc.text[c.end:sub_end]
        refs = re.findall(r"pages?\s+\d[\d,\s\-–]*", sub, re.IGNORECASE)
        if not refs:  # Citi form: page range glued to the title line
            trailing = re.search(r"(\d{1,4}(?:\s*[-–]\s*\d{1,4})?)\s*$", c.heading_text)
            if trailing:
                refs = [trailing.group(1)]
        if refs and c.code not in page_refs:
            page_refs[c.code] = "; ".join(r.strip() for r in refs)

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
        entry_span=entry_span,
        reason=(f"{len(best_codes)} item headings clustered within {best_hi - best_lo} chars; "
                f"{trigger} — cross-reference index; item bodies are not in addressable Item "
                f"sections of the main document"),
    )


# title cap must clear the LONGEST canonical 10-K item title (Item 5 = 108
# chars, Item 12 = 94, Item 7 MD&A = 85); a 70-char cap silently dropped
# Citi's MD&A row ("7. Management's Discussion ... Results of Operations 8-36")
# so Item 7 came back `missing` even though its page anchor resolves. The
# full-line anchor + digit-only pageref + canonical-title similarity>=0.5 gate
# in scan_bare_index keep the wider cap from matching prose.
_BARE_INDEX_RE = re.compile(
    r"^\s*(\d{1,2}[A-C]?)\.\s*([A-Za-z][A-Za-z '&,./()-]{3,110}?)\s*(\d[\d\s,\-–]*)?$"
)


def scan_bare_index(doc: NormalizedDocument) -> CrossRefIndex:
    """Fallback for cross-reference indexes whose entries omit the word 'Item'
    (Citi: '1A.Risk Factors49-62'). Standard heading detection finds nothing,
    so we scan lines directly for '<code>.<title><pageref>' clustered together
    and confirmed by canonical-title similarity."""
    from difflib import SequenceMatcher

    hits: list[tuple[int, str, str, str, int]] = []  # (line_start, code, title, pageref, line_end)
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
        hits.append((ln.start, code, title, (m.group(3) or "").strip(), ln.end))

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
    entry_span: dict[str, tuple[int, int]] = {}
    for start, code, title, pageref, end in window:
        entries.setdefault(code, pageref or title)
        entry_span.setdefault(code, (start, end))
        if pageref:
            page_refs.setdefault(code, pageref)
    return CrossRefIndex(
        detected=True,
        index_start=min(h[0] for h in window),
        index_end=max(h[0] for h in window),
        page_refs=page_refs,
        entries=entries,
        entry_span=entry_span,
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
    # spans already resolved for earlier items — a later item that would resolve
    # to a byte-identical span (INTC Item 15 -> Item 8's financials, Item 9B ->
    # Item 1C's page 54) is steered to its own alternative range or, failing
    # that, left an honest pointer, so no two items share the same body span.
    claimed_spans: set[tuple[int, int]] = set()
    for code in VALID_CODES:
        canonical = CANONICAL_ITEM_TITLES[code]
        heading = f"Item {code}. {canonical}"
        following = index.entries.get(code, "")

        if code in index.page_refs:
            ref = index.page_refs[code]
            # try to RESOLVE the pointer to a real source-exact span via the
            # printed page-number footers (robust: printed data, not a guess)
            span = resolve_page_ref(page_map, ref, avoid=claimed_spans)
            if span is not None and span[1] - span[0] > 400:
                claimed_spans.add(span)
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
                        "heuristic — verify start/end against the filing. The index may "
                        "over-claim page ranges (e.g. Item 1 '4-36' vs MD&A '8-36'), so a "
                        "resolved span can overlap an adjacent item; identical spans are "
                        "de-duplicated but nesting is possible."],
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
            es = index.entry_span.get(code, (index.index_start, index.index_start))
            segments.append(ItemSegment(
                filing_id=filing_id, item_code=code, canonical_title=canonical,
                extracted_heading=heading, start_offset=es[0], end_offset=es[1], text_sha256="",
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
            es = index.entry_span.get(code, (index.index_start, index.index_start))
            segments.append(ItemSegment(
                filing_id=filing_id, item_code=code, canonical_title=canonical,
                extracted_heading=heading, start_offset=es[0], end_offset=es[1], text_sha256="",
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


# --- wrapper body reassembly (the JPM / XOM class) ---------------------------
# A wrapper 10-K keeps real item headings in the main Part I-IV text but writes
# some items (JPM: 1C/7/7A/8; XOM: 7/7A/8) as one-sentence stubs deferring to a
# Financial Section / annual report bound AFTER the last item heading.
# boundary.py already cuts that appended block off the terminal item
# (FG-SEC-004) and classifies the stubs incorporated_by_reference (FG-SEC-002);
# this pass reassembles the deferred bodies: a stub that points into the
# appended block by an explicit page range ("appears on pages 46-160") or a
# quoted section title ('the section entitled "Market Risks"') is resolved to a
# source-exact span inside the block. Pointers to external documents (proxy
# statement) or without resolvable anchors are left untouched.

_MIN_APPENDED_REGION = 20_000  # smaller tails are signature/exhibit furniture, not a bound report
_MIN_RESOLVED_SPAN = 400
# the FIRST page range mentioned is the item's own location; later ranges are
# supplementary ("...should be read in conjunction with ... on pages 165-314")
_STUB_PAGE_REF_RE = re.compile(r"pages?\s+\d{1,4}(?:\s*[-–]\s*\d{1,4})?", re.IGNORECASE)
_QUOTED_SECTION_RE = re.compile(
    r"section\s+entitled\s+[\"“]([^\"”]{4,120})[\"”]", re.IGNORECASE)
_PROXY_STMT_RE = re.compile(r"proxy\s+statement", re.IGNORECASE)
# the stub must point into THIS filing, not an external document
_THIS_FILING_RE = re.compile(
    r"financial\s+section|annual\s+report|on\s+pages?\s+\d", re.IGNORECASE)
# generic top-level headings of a bound financial report — used only as END
# boundaries for section-title spans, so Item 7A does not run into the audit
# report and Item 8 does not swallow the exhibit index / signatures
_SECTION_BOUNDARY_TITLES = (
    "management's report on internal control over financial reporting",
    "report of independent registered public accounting firm",
    "index to exhibits",
    "signatures",
)


def _find_section_anchor(doc: NormalizedDocument, region_start: int, title: str) -> int | None:
    """Offset of `title` as a real standalone section-heading line inside the
    appended region. The region's own table of contents repeats every title, so
    occurrences followed by a cluster of bare page-number lines (TOC entries)
    are skipped; a real heading is followed by prose."""
    want = title.casefold().replace("’", "'")
    lines = doc.lines
    for i, ln in enumerate(lines):
        if ln.start < region_start:
            continue
        if ln.text.strip().casefold().replace("’", "'") != want:
            continue
        following: list[str] = []
        for x in lines[i + 1:i + 12]:
            t = x.text.strip()
            if not t:
                continue
            if len(t) >= 80:
                break  # long prose line: the TOC pattern (if any) ends here
            following.append(t)
            if len(following) == 4:
                break
        if sum(1 for t in following if re.fullmatch(r"\d{1,4}", t)) >= 2:
            continue  # a TOC entry (short titles alternating with page numbers)
        return ln.start
    return None


# --- page-top section anchoring (oracle-driven boundary convergence) ---------
# Bound reports print a page-number marker plus the same short "furniture"
# lines (company banner, running header) at every page top; a top-level section
# starts where the FIRST non-furniture line of a page is itself a short heading
# line (a continuation page starts with prose instead). The CYD iXBRL oracle
# exposed two wrapper failure modes this printed structure fixes generically:
# (a) a page-range stub resolves to whole pages that BEGIN at a parent section
# while the item's own body is a later section on those pages (JPM Item 1C ->
# "pages 146-149" begin at Operational Risk Management, but the CYD-tagged body
# is the Cybersecurity risk section starting page 147), and (b) an in-document
# pointer quotes the exact section heading living inside ANOTHER item's span
# (GS Item 1C -> '... - Cybersecurity Risk Management' in Part II, Item 7).
# Kill-switch: SEC_WRAPPER_SECTION_ANCHOR=0 disables both refinements.
_SECTION_ANCHOR_ENV = "SEC_WRAPPER_SECTION_ANCHOR"
_BARE_PAGE_NUM_RE = re.compile(r"\d{1,4}")
_MAX_FURNITURE_LINE = 80     # furniture lines are short banner/header lines...
_FURNITURE_MIN_REPEATS = 3   # ...repeated near at least this many page markers
_MAX_SECTION_HEADING = 60    # a page-top section heading is a short line
_PAGE_TOP_SCAN = 6           # non-blank lines examined at each page top
_TOPIC_MATCH_MIN = 0.75      # canonical-title similarity for page-window snapping
# quoted section path pointing into another item of the SAME filing:
# 'See "MD&A - Risk Management - Cybersecurity Risk Management" in Part II,
#  Item 7 of this Form 10-K'
_INTRA_DOC_SECTION_REF_RE = re.compile(
    r"[\"“]([^\"”]{4,200})[\"”]\s+in\s+part\s+[ivx]+\s*,?\s+item\s+(\d{1,2}[a-c]?)"
    r"\s+of\s+this\s+form\s*10-k",
    re.IGNORECASE,
)


def _section_anchoring_enabled() -> bool:
    return os.environ.get(_SECTION_ANCHOR_ENV) != "0"


def _norm_title(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("’", "'").strip()).casefold()


def _digits_stripped(s: str) -> str:
    return re.sub(r"\d+", "", _norm_title(s))


def _page_top_sections(
    doc: NormalizedDocument, pm, lo: int, hi: int
) -> tuple[list[tuple[int, int, str]], set[str]]:
    """Top-level section headings printed at page tops inside [lo, hi).

    Returns (sections, furniture): sections is [(line_index, offset, text), ...]
    sorted by offset; furniture is the digit-stripped texts of the short lines
    repeated near many page markers (company banner, running header). All
    signals are printed page structure — no ticker- or filer-specific rules.
    """
    lines = doc.lines
    starts = [ln.start for ln in lines]
    marker_idx: list[int] = []
    for page in sorted(pm.marker_start):
        off = pm.marker_start[page]
        if lo <= off < hi:
            i = bisect_left(starts, off)
            if i < len(lines) and lines[i].start == off:
                marker_idx.append(i)
    # furniture: short lines that repeat near several page markers
    seen: dict[str, int] = {}
    for i in marker_idx:
        near: set[str] = set()
        for j in range(max(0, i - 2), min(len(lines), i + 1 + _PAGE_TOP_SCAN)):
            if j == i:
                continue
            t = lines[j].text.strip()
            if t and len(t) <= _MAX_FURNITURE_LINE and not _BARE_PAGE_NUM_RE.fullmatch(t):
                near.add(_digits_stripped(t))
        for key in near:
            seen[key] = seen.get(key, 0) + 1
    furniture = {k for k, n in seen.items() if n >= _FURNITURE_MIN_REPEATS}
    # the first non-furniture line of each page: short = section heading,
    # long prose = the page continues the previous section
    sections: list[tuple[int, int, str]] = []
    for i in marker_idx:
        scanned = 0
        for j in range(i + 1, len(lines)):
            t = lines[j].text.strip()
            if not t:
                continue
            scanned += 1
            if scanned > _PAGE_TOP_SCAN:
                break
            if _BARE_PAGE_NUM_RE.fullmatch(t) or _digits_stripped(t) in furniture:
                continue
            if len(t) <= _MAX_SECTION_HEADING:
                sections.append((j, lines[j].start, t))
            break
    sections.sort(key=lambda s: s[1])
    return sections, furniture


def _trim_page_furniture(doc: NormalizedDocument, line_index: int, furniture: set[str]) -> int:
    """Offset where body content ends before the page-top section heading at
    line_index: walk back over the contiguous page-break block (banner/header
    furniture lines, bare page numbers, blanks), so the previous section's span
    does not swallow the furniture."""
    end = doc.lines[line_index].start
    for j in range(line_index - 1, -1, -1):
        t = doc.lines[j].text.strip()
        if (not t or _BARE_PAGE_NUM_RE.fullmatch(t)
                or (len(t) <= _MAX_FURNITURE_LINE and _digits_stripped(t) in furniture)):
            end = doc.lines[j].start
            continue
        break
    return end


def _item_topic_match(code: str, heading: str) -> bool:
    """The anchored section heading must relate to the ITEM's own topic — this
    guards against resolving a body from a quoted PARENT-chapter title (GS
    Item 7A quotes 'MD&A - Risk Management': that page-top section is the risk
    chapter's intro, not the item's market-risk content; a wrong body is worse
    than an honest pointer)."""
    canonical = _norm_title(CANONICAL_ITEM_TITLES.get(code, ""))
    h = _norm_title(heading)
    if not canonical or not h:
        return False
    if SequenceMatcher(None, canonical, h).ratio() >= 0.5:
        return True
    return bool(set(re.findall(r"[a-z]{6,}", h))
                & set(re.findall(r"[a-z]{6,}", canonical)))


def _snap_window_to_item_section(
    doc: NormalizedDocument, pm, start: int, end: int, region_end: int, code: str
) -> tuple[int, int, str] | None:
    """A page-range stub can defer to pages that begin at a PARENT section while
    the item's own body is a later section on those pages. If a page-top section
    heading strictly inside the resolved window matches the item's canonical
    title, snap the span to that section (end = next page-top section, page
    furniture trimmed); otherwise leave the window untouched."""
    canonical = _norm_title(CANONICAL_ITEM_TITLES.get(code, ""))
    if not canonical:
        return None
    sections, furniture = _page_top_sections(doc, pm, start, region_end)
    best: tuple[float, int, int, str] | None = None
    for j, off, text in sections:
        if not (start < off < end):
            continue
        sim = SequenceMatcher(None, canonical, _norm_title(text)).ratio()
        if sim >= _TOPIC_MATCH_MIN and (best is None or sim > best[0]):
            best = (sim, j, off, text)
    if best is None:
        return None
    _, _, off, text = best
    new_end = end
    later = [(lj, loff) for lj, loff, _ in sections if loff > off]
    if later:
        trimmed = _trim_page_furniture(doc, later[0][0], furniture)
        if off < trimmed <= end:
            new_end = trimmed
    if new_end - off <= _MIN_RESOLVED_SPAN:
        return None
    return off, new_end, text


def reassemble_wrapper_bodies(
    doc: NormalizedDocument,
    segments: list[ItemSegment],
    breakdowns: dict[str, ConfidenceBreakdown],
) -> int:
    """Resolve incorporated_by_reference stubs that defer into an appended
    Financial Section / annual report bound after the last item (JPM/XOM
    wrapper class). Mutates matching segments in place to source-exact spans
    (status partial, needs_review — boundary alignment is heuristic) and
    returns how many items were reassembled."""
    region_start = max((s.end_offset for s in segments), default=0)
    region_end = len(doc.text)
    if region_start <= 0 or region_end - region_start < _MIN_APPENDED_REGION:
        return 0
    pm = build_page_map(doc, start=region_start)

    # plan: (segment, how, start, end|None); None ends resolve to the next anchor
    plans: list[tuple[ItemSegment, str, int, int | None]] = []
    anchors: list[int] = []
    for seg in segments:
        if seg.status != "incorporated_by_reference" or seg.provenance != "offset_exact_span":
            continue
        stub = doc.slice(seg.start_offset, seg.end_offset)
        if _PROXY_STMT_RE.search(stub) or not _THIS_FILING_RE.search(stub):
            continue  # external target (proxy) or not pointing into this filing
        m = _STUB_PAGE_REF_RE.search(stub)
        if m:
            span = resolve_page_ref(pm, m.group(0))
            if span is not None and span[1] - span[0] > _MIN_RESOLVED_SPAN:
                plans.append((seg, f"the page range '{m.group(0)}' via printed "
                                   f"page-number anchors", span[0], span[1]))
            continue
        qm = _QUOTED_SECTION_RE.search(stub)
        if qm:
            a = _find_section_anchor(doc, region_start, qm.group(1))
            if a is not None:
                plans.append((seg, f"the section heading {qm.group(1)!r}", a, None))
                anchors.append(a)

    for title in _SECTION_BOUNDARY_TITLES:
        a = _find_section_anchor(doc, region_start, title)
        if a is not None:
            anchors.append(a)

    resolved = 0
    for seg, how, start, end in plans:
        page_anchored = end is not None
        if end is None:
            later = sorted(a for a in anchors if a > start)
            end = later[0] if later else region_end
        if end - start <= _MIN_RESOLVED_SPAN:
            continue
        if page_anchored and _section_anchoring_enabled():
            # the pages may BEGIN at a parent section; if the item's own
            # section heading is printed at a later page top inside the
            # window, the body is that section, not the whole page range
            snapped = _snap_window_to_item_section(doc, pm, start, end, region_end,
                                                   seg.item_code)
            if snapped is not None:
                start, end, sect = snapped
                how += (f", then snapped to the item's own page-top section "
                        f"heading {sect!r} inside those pages")
        text = doc.slice(start, end)
        seg.start_offset, seg.end_offset = start, end
        seg.text_sha256 = sha256_text(text)
        seg.status = "partial"
        seg.provenance = ("resolved_from_page_anchor" if page_anchored
                          else "resolved_from_section_anchor")
        seg.needs_review = True
        seg.warnings = [w for w in seg.warnings
                        if "the span is the pointer text only" not in w]
        seg.warnings.append(
            f"wrapper 10-K: this item's body was deferred to the financial-report section "
            f"bound after the last item heading; reassembled from {how} (source-exact span "
            f"in the same document). Marked partial + needs_review because boundary "
            f"alignment is heuristic — verify start/end against the filing."
        )
        bd = ConfidenceBreakdown(components=[
            CC(name="content_substantiveness", score=1.4, max_score=2.0,
               reason=f"reassembled a {end - start}-char body span from {how}"),
            CC(name="heading_strength", score=1.5, max_score=2.0,
               reason="anchor resolved from printed page-number footers" if page_anchored
               else "anchor resolved from the bound report's own section heading"),
        ])
        breakdowns[seg.item_code] = bd
        seg.confidence = bd.total
        resolved += 1
    return resolved


def resolve_intra_document_pointers(
    doc: NormalizedDocument,
    segments: list[ItemSegment],
    breakdowns: dict[str, ConfidenceBreakdown],
) -> int:
    """Resolve incorporated_by_reference stubs that point at a quoted section
    heading inside ANOTHER item of the SAME Form 10-K (the GS class: Item 1C
    defers to 'See "MD&A - Risk Management - Cybersecurity Risk Management" in
    Part II, Item 7 of this Form 10-K'). The quoted path's LAST component must
    match a page-top section heading inside the referenced item's span exactly
    (title-normalized); the body runs to the next page-top section heading,
    page furniture trimmed. No exact match -> the stub stays an honest pointer
    (a wrong body is worse than an honest pointer). Mutates matching segments
    in place and returns how many were resolved.
    Kill-switch: SEC_WRAPPER_SECTION_ANCHOR=0."""
    if not _section_anchoring_enabled():
        return 0
    by_code = {s.item_code: s for s in segments}
    resolved = 0
    for seg in segments:
        if seg.status != "incorporated_by_reference" or seg.provenance != "offset_exact_span":
            continue
        stub = doc.slice(seg.start_offset, seg.end_offset)
        if _PROXY_STMT_RE.search(stub):
            continue  # external target — stays an honest pointer
        m = _INTRA_DOC_SECTION_REF_RE.search(stub)
        if m is None:
            continue
        target = by_code.get(m.group(2).upper())
        if (target is None or target is seg
                or target.end_offset - target.start_offset <= _MIN_RESOLVED_SPAN):
            continue
        title = _norm_title(re.split(r"\s+[-–—]\s+", m.group(1))[-1])
        pm = build_page_map(doc, start=target.start_offset, end=target.end_offset)
        if not pm.ok:
            continue
        sections, furniture = _page_top_sections(
            doc, pm, target.start_offset, target.end_offset)
        hit = next(((j, off, t) for j, off, t in sections if _norm_title(t) == title), None)
        if hit is None or not _item_topic_match(seg.item_code, hit[2]):
            continue
        j, start, text = hit
        later = [(lj, loff) for lj, loff, _ in sections if loff > start]
        end = (_trim_page_furniture(doc, later[0][0], furniture)
               if later else target.end_offset)
        if end - start <= _MIN_RESOLVED_SPAN:
            continue
        body = doc.slice(start, end)
        seg.start_offset, seg.end_offset = start, end
        seg.text_sha256 = sha256_text(body)
        seg.status = "partial"
        seg.provenance = "resolved_from_section_anchor"
        seg.needs_review = True
        seg.warnings = [w for w in seg.warnings
                        if "the span is the pointer text only" not in w]
        seg.warnings.append(
            f"in-document pointer: this item's body lives inside Item "
            f"{m.group(2).upper()}'s span under its own section heading; resolved from "
            f"the quoted section title {text!r} found as a page-top section heading "
            f"(source-exact span in the same document). Marked partial + needs_review "
            f"because boundary alignment is heuristic — verify start/end against the filing."
        )
        bd = ConfidenceBreakdown(components=[
            CC(name="content_substantiveness", score=1.4, max_score=2.0,
               reason=f"resolved a {end - start}-char body span from the quoted "
                      f"section heading {text!r}"),
            CC(name="heading_strength", score=1.5, max_score=2.0,
               reason="anchor is the referenced item's own page-top section heading"),
        ])
        breakdowns[seg.item_code] = bd
        seg.confidence = bd.total
        resolved += 1
    return resolved
