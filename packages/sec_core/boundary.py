"""Boundary resolution (SPEC 7.10): pick the best body candidate per item,
enforce document-order consistency, derive end offsets from the next item's
start, and classify special cases (reserved / combined / incorporated by
reference / missing / ambiguous) honestly instead of faking pass.
"""

from __future__ import annotations

import re
from array import array
from dataclasses import dataclass, field, replace
from difflib import SequenceMatcher
from functools import lru_cache

from eval_core import ConditionCheck, combine_checks
from observability_core import sha256_text
from sec_core.adjudicator import BoundaryEvidence
from sec_core.confidence import OVERSHOOT_COMPONENT_MAX, ConfidenceBreakdown
from sec_core.confidence import ConfidenceComponent as CC
from sec_core.headings import (
    _PAGE_NUMBER_RE,
    _line_flag_ratio,
    VALID_CODES,
    HeadingCandidate,
    detect_candidates,
)
from sec_core.items import CANONICAL_ITEM_TITLES, ItemSegment
from sec_core.normalize import FLAG_TOC_LINK, Line, NormalizedDocument
from sec_core.refine import (
    classify_reference_stub,
    detect_appended_section_cut,
    is_boilerplate_none,
    trim_trailing_furniture,
)

# Terminal-item tail anchor: the SIGNATURES block heading, its letter-spaced
# plain-text form, or the signature-page preamble sentence ("Pursuant to the
# requirements of Section 13 or 15(d) ... duly caused this report to be
# signed"). The cover page's "ANNUAL REPORT PURSUANT TO SECTION 13 OR 15(d)"
# does NOT contain "the requirements of", so it never matches.
_SIGNATURES_RE = re.compile(
    r"^\s*signatures?\s*$"
    r"|^\s*s\s+i\s+g\s+n\s+a\s+t\s+u\s+r\s+e\s+s?\s*$"
    r"|^\s*pursuant\s+to\s+the\s+requirements\s+of\s+section\s+13\s+or\s+15\s*\(\s*d\s*\)",
    re.IGNORECASE | re.MULTILINE,
)
_RESERVED_RE = re.compile(r"\breserved\b", re.IGNORECASE)

AMBIGUITY_MARGIN = 0.85  # runner-up score / winner score above this => ambiguous


def _score(cand: HeadingCandidate) -> float:
    s = 0.0
    if "strict_regex" in cand.detectors:
        s += 2.0
    if "dom_heading" in cand.detectors:
        s += 1.0
    if "visual_layout" in cand.detectors:
        s += 0.5
    s += 2.0 * cand.title_similarity
    if cand.is_uppercase:
        s += 0.25
    return s


@dataclass
class ResolvedItem:
    code: str
    chosen: HeadingCandidate | None
    runner_up: HeadingCandidate | None
    rejected_toc: list[HeadingCandidate]
    ambiguous: bool
    warnings: list[str] = field(default_factory=list)


def _select_candidates(candidates: list[HeadingCandidate]) -> dict[str, ResolvedItem]:
    by_code: dict[str, list[HeadingCandidate]] = {}
    for c in candidates:
        by_code.setdefault(c.code, []).append(c)

    resolved: dict[str, ResolvedItem] = {}
    prev_start = -1
    for code in VALID_CODES:
        cands = by_code.get(code, [])
        body = sorted((c for c in cands if not c.toc_rejected), key=_score, reverse=True)
        toc = [c for c in cands if c.toc_rejected]
        warnings: list[str] = []

        # enforce document order: the chosen heading must come after the
        # previously chosen item's heading. Combined headings ("Items 1 and 2")
        # legitimately share an earlier offset and bypass the filter.
        ordered = [c for c in body if c.start > prev_start or c.combined_with]
        if body and not ordered:
            warnings.append(
                f"all candidates for item {code} appear before item sequence position; dropped"
            )
        chosen = ordered[0] if ordered else None
        runner_up = ordered[1] if len(ordered) > 1 else None

        ambiguous = False
        if chosen and runner_up and _score(chosen) > 0:
            if _score(runner_up) / _score(chosen) >= AMBIGUITY_MARGIN:
                ambiguous = True
                warnings.append(
                    f"runner-up candidate at offset {runner_up.start} scores within "
                    f"{int((1 - AMBIGUITY_MARGIN) * 100)}% of winner — needs adjudication"
                )
        if chosen and chosen.toc_reasons and not chosen.toc_rejected:
            warnings.append("chosen candidate carries TOC-like signals: " + "; ".join(chosen.toc_reasons))

        if chosen and chosen.start > prev_start:
            prev_start = chosen.start
        resolved[code] = ResolvedItem(
            code=code, chosen=chosen, runner_up=runner_up,
            rejected_toc=toc, ambiguous=ambiguous, warnings=warnings,
        )
    return resolved


def _canonical_title_re(code: str) -> re.Pattern[str]:
    words = CANONICAL_ITEM_TITLES[code].split()
    return re.compile(r"\b" + r"\s+".join(re.escape(w) for w in words) + r"\b", re.IGNORECASE)


def _infer_combined_headings(resolved: dict[str, ResolvedItem]) -> None:
    """Combined-item inference fallback (P0-9): a singular heading like
    'Item 1. Business and Properties' leaves the covered item with no anchor of
    its own — its content lands inside the first item's span but its recall
    silently drops to zero as 'missing'. When a missing item's canonical title
    appears verbatim in an earlier chosen heading's title text, treat the pair
    as combined (same semantics as an explicit 'Items 1 and 2' heading) instead
    of silently missing.
    """
    for i, code in enumerate(VALID_CODES):
        r = resolved[code]
        if r.chosen is not None or code == "6":  # 6 already has the reserved path
            continue
        title_re = _canonical_title_re(code)
        for prev_code in reversed(VALID_CODES[:i]):
            prev = resolved[prev_code]
            # never chain: a heading already covering two items is exhausted
            if prev.chosen is None or prev.chosen.combined_with:
                continue
            if not title_re.search(prev.chosen.title_text):
                continue
            r.chosen = replace(prev.chosen, code=code, combined_with=prev_code)
            prev.chosen.combined_with = code
            r.warnings.append(
                f"no own heading for item {code}; inferred combined with item {prev_code} "
                f"because its heading title contains "
                f"{CANONICAL_ITEM_TITLES[code]!r}"
            )
            break


def _end_of_document_body(doc: NormalizedDocument, last_start: int) -> int:
    m = _SIGNATURES_RE.search(doc.text, last_start)
    return m.start() if m else len(doc.text)


def _evidence_for(doc: NormalizedDocument, item: ResolvedItem) -> list[BoundaryEvidence]:
    ev: list[BoundaryEvidence] = []
    if item.chosen:
        ev.append(
            BoundaryEvidence(
                kind="heading_match",
                detail=f"detectors: {', '.join(sorted(item.chosen.detectors))}; "
                f"title_similarity={item.chosen.title_similarity:.2f}",
                source_offset_start=item.chosen.start,
                source_offset_end=item.chosen.end,
                quote=item.chosen.heading_text,
            )
        )
    for rej in item.rejected_toc:
        ev.append(
            BoundaryEvidence(
                kind="toc_rejection",
                detail="; ".join(rej.toc_reasons),
                source_offset_start=rej.start,
                source_offset_end=rej.end,
                quote=rej.heading_text,
            )
        )
    return ev


def _confidence(doc: NormalizedDocument, item: ResolvedItem, start: int, end: int,
                verifier_pass: bool, content_kind: str) -> ConfidenceBreakdown:
    c = item.chosen
    assert c is not None
    length = end - start
    detector_count = len(c.detectors)
    # A reference stub captured a pointer, not the item's content — it must not
    # score like a clean pass. This is what makes confidence discriminate
    # (the audit found a flat ~0.958 regardless of stub vs full content).
    subst_score, subst_reason = {
        "substantive": (2.0, "body is substantive item content"),
        "boilerplate_none": (2.0, "body is a complete 'None.'/'Not applicable.' answer"),
        "combined": (1.2, "two items share one combined span"),
        "reference_stub": (0.0, "body is only a pointer to content located elsewhere"),
    }[content_kind]
    # A stub trivially satisfies the machine checks (heading present, nonempty),
    # so 'verifier pass' is not evidence of real content for a stub.
    verifier_score = 1.0 if (verifier_pass and content_kind != "reference_stub") else 0.0
    comps = [
        CC(name="heading_strength", score=2.0 if "strict_regex" in c.detectors else 1.0,
           max_score=2.0,
           reason="strict regex match" if "strict_regex" in c.detectors else "loose regex only"),
        CC(name="title_similarity", score=c.title_similarity, max_score=1.0,
           reason=f"similarity to canonical title = {c.title_similarity:.2f}"),
        CC(name="sequence_consistency", score=0.0 if item.warnings else 1.0, max_score=1.0,
           reason="; ".join(item.warnings) or "heading order consistent with item sequence"),
        CC(name="toc_disambiguation",
           score=1.0 if (item.rejected_toc or not c.toc_reasons) else 0.0, max_score=1.0,
           reason=(f"{len(item.rejected_toc)} TOC duplicate(s) explicitly rejected"
                   if item.rejected_toc else
                   ("no TOC interference" if not c.toc_reasons else "unresolved TOC-like signals"))),
        CC(name="boundary_length_sanity",
           # a legitimately short answer ("None." / combined / a reference stub)
           # must not be penalised for being short — only abnormal lengths fail
           score=1.0 if (content_kind in ("boilerplate_none", "combined", "reference_stub")
                         or 50 <= length <= 3_000_000) else 0.0,
           max_score=1.0,
           reason=f"segment length {length} chars"
                  + (" (short answer accepted)" if content_kind == "boilerplate_none" else "")),
        CC(name="cross_detector_agreement", score=min(detector_count, 3) / 3.0, max_score=1.0,
           reason=f"{detector_count} independent detectors agree"),
        CC(name="content_substantiveness", score=subst_score, max_score=2.0, reason=subst_reason),
        CC(name="verifier_result", score=verifier_score, max_score=1.0,
           reason="verifier pass" if verifier_score else
           ("stub body: verifier pass not counted as real content" if content_kind == "reference_stub"
            else "verifier did not pass")),
    ]
    return ConfidenceBreakdown(components=comps)


# --- overshoot guard (NTU boundary-bleed fix) --------------------------------
# The dominant NTU-fold failure mode (123/141 errors) is boundary bleed: the
# span STARTS right (recall≈1) but the tail swallows the next item(s) while
# confidence saturates at 1.0. This guard flags a pass span whose BODY contains
# a plausible LATER-item heading — that heading should have ended the span.

OVERSHOOT_CONTAINMENT_COMPONENT = "overshoot_containment"
# chars after the span start exempt from containment: the item's own heading
# line (and a combined partner's heading) legitimately live there
OVERSHOOT_HEAD_MARGIN = 300


def _plausible_body_heading(c: HeadingCandidate) -> bool:
    """Would this candidate read as a real later-item BODY heading — not a
    TOC/reference line and not a heading quoted inside prose?"""
    if c.toc_rejected or c.toc_reasons or c.in_toc_link or c.trailing_page_number:
        return False  # TOC / index / reference-line shaped
    if "strict_regex" not in c.detectors:
        return False  # mid-prose mentions never match the anchored strict form
    if not ({"dom_heading", "visual_layout"} & c.detectors):
        return False  # no emphasis or layout evidence — likely quoted in prose
    # the title must resemble the canonical one (or be a bare 'Item N.' line)
    return c.title_similarity >= 0.4 or not c.title_text


def find_contained_later_heading(
    code: str,
    candidates: list[HeadingCandidate],
    start: int,
    end: int,
    head_margin: int = OVERSHOOT_HEAD_MARGIN,
) -> HeadingCandidate | None:
    """Earliest plausible LATER-item heading strictly inside the span body
    (beyond the head margin). Its presence means the span is overshooting:
    the resolver derived `end` from a next-chosen start that lies too late
    (wrong later duplicate chosen, or the real heading dropped by the
    document-order filter)."""
    idx = VALID_CODES.index(code)
    later = set(VALID_CODES[idx + 1:])
    hits = [c for c in candidates
            if c.code in later and start + head_margin <= c.start
            and c.start < end and c.end <= end and _plausible_body_heading(c)]
    return min(hits, key=lambda c: c.start) if hits else None


# --- end-boundary rescan (NTU boundary-bleed EXTRACTION fix) -----------------
# The overshoot guard above only caps confidence; the resolver's end offset was
# still "start of the next DETECTED item", so one missed intermediate heading
# made a span run through the next item's whole body. The rescan moves the fix
# into extraction: before a span is emitted, its own body is rescanned for the
# heading of a later EXPECTED item (known 10-K order, e.g. 9A->9B->10, 5->6,
# 14->15) and the end is cut there. The cut can only SHORTEN a span — the
# current item's own content is never dropped (recall stays 1.0), and the
# trimmed tail is not lost: it falls to the next item or an unclassified gap
# (coverage.partition_document tiles the whole document either way).

# Pre-2011 item titles still common in the supported era's filings — the
# canonical (post-2021) titles alone would miss these headings in the rescan.
LEGACY_ITEM_TITLES: dict[str, tuple[str, ...]] = {
    "4": ("Submission of Matters to a Vote of Security Holders",),
    "6": ("Selected Financial Data",),
    "10": ("Directors and Executive Officers of the Registrant",),
    "14": ("Principal Accounting Fees and Services",),
}

# Looser line-anchored heading shape for the rescan: optional 'Item' prefix,
# the item code (optional '(T)' transitional suffix), optional separator, then
# the title text. Lines WITHOUT the 'Item' word (e.g. '9B. OTHER INFORMATION')
# are exactly the ones detect_candidates cannot see.
_RESCAN_LINE_RE = re.compile(
    r"^\s*(?:item[\s.]+)?(\d{1,2})\s*([a-cA-C])?(?:\(t\))?\s*[.:\-–—]?\s*(.*)$",
    re.IGNORECASE,
)


@lru_cache(maxsize=None)
def _title_fragment_re(code: str) -> re.Pattern[str]:
    """Match the first words of any known title variant for `code` — the
    fragment gate that keeps the loose line shape from cutting at numbered
    lists / dates / prose ('12,345 units', '10 May 2013')."""
    frags = []
    for title in (CANONICAL_ITEM_TITLES[code], *LEGACY_ITEM_TITLES.get(code, ())):
        words = re.findall(r"[A-Za-z]+", title)[:2]
        if words:
            frags.append(r"[\W_]+".join(re.escape(w) for w in words))
    return re.compile(r"(?:" + "|".join(frags) + r")\b", re.IGNORECASE)


def _rescan_title_ok(code: str, rest: str) -> bool:
    """Tier-2 title gate: the text after the code must BE the item's title
    (canonical or legacy), not merely start with it — a numbered list line
    like '3. Legal Proceedings are described in Note 12.' must never cut."""
    rest = rest.strip().rstrip(".:").strip()
    if not rest or not _title_fragment_re(code).match(rest):
        return False
    variants = (CANONICAL_ITEM_TITLES[code], *LEGACY_ITEM_TITLES.get(code, ()))
    return any(
        SequenceMatcher(None, v.casefold(), rest.casefold()).ratio() >= 0.6
        for v in variants
    )


def _rescan_end_cut(
    doc: NormalizedDocument,
    candidates: list[HeadingCandidate],
    code: str,
    chosen: HeadingCandidate,
    end: int,
) -> tuple[int, str] | None:
    """Scoped next-item rescan: earliest later-item heading inside the span
    body. Two tiers, both line-anchored and both able only to shorten:

    1. detected candidates — the earliest plausible later-item heading the
       document-level detectors already produced (same predicate as the
       overshoot guard: strict regex + emphasis/layout, never TOC-shaped);
    2. looser text scan — a line the detectors could not see (no 'Item' word),
       gated on the item code AND a canonical/legacy title fragment.

    Returns (cut_offset, description) or None. TOC-link lines, trailing-page-
    number lines and lines that already have a candidate (tier 1's
    jurisdiction, with its plausibility rules) are never tier-2 cuts.
    """
    floor = max(chosen.start + OVERSHOOT_HEAD_MARGIN, chosen.end + 1)
    best: tuple[int, str] | None = None

    hit = find_contained_later_heading(code, candidates, chosen.start, end)
    if hit is not None and hit.start >= floor:
        best = (hit.start,
                f"detected item {hit.code} heading {hit.heading_text[:60]!r}")

    idx = VALID_CODES.index(code)
    later = set(VALID_CODES[idx + 1:])
    candidate_starts = {c.start for c in candidates}
    hi = best[0] if best else end
    for line in doc.lines:
        if line.start < floor:
            continue
        if line.start >= hi:
            break
        txt = line.text.strip()
        if not txt or len(txt) > 120 or line.start in candidate_starts:
            continue
        m = _RESCAN_LINE_RE.match(txt)
        if not m:
            continue
        code2 = m.group(1) + (m.group(2) or "").upper()
        if code2 not in later or not _rescan_title_ok(code2, m.group(3)):
            continue
        if _PAGE_NUMBER_RE.search(txt):
            continue  # TOC/index stub line, not a body heading
        if _line_flag_ratio(doc, line.start, line.end, FLAG_TOC_LINK) >= 0.5:
            continue  # anchor-link line (mini index inside the body)
        return (line.start, f"inferred item {code2} heading {txt[:60]!r}")
    return best


def _span_doc(text: str) -> NormalizedDocument:
    """Wrap already-normalized span text (identity offsets, no DOM flags) so
    the line-based heading detectors can run on a span's own text."""
    doc = NormalizedDocument(
        raw_html=text, text=text,
        norm_to_raw=array("q", range(len(text))),
        flags=bytearray(len(text)), anchor_targets={},
    )
    start = 0
    for i, ch in enumerate(text):
        if ch == "\n":
            doc.lines.append(Line(start=start, end=i, text=text[start:i]))
            start = i + 1
    if start < len(text):
        doc.lines.append(Line(start=start, end=len(text), text=text[start:]))
    return doc


def scan_span_overshoot(code: str, span_text: str) -> HeadingCandidate | None:
    """Re-run the headings.py detectors + TOC assessment on a span's own text
    (offsets relative to the span) and return the earliest plausible
    later-item heading in its body. For verification layers that only hold
    the span text (e.g. the mutation harness); the pipeline path uses the
    richer document-level candidates (DOM anchor-link flags) directly."""
    from sec_core.toc import assess_toc  # local: toc imports headings, not us

    doc = _span_doc(span_text)
    cands = detect_candidates(doc)
    assess_toc(doc, cands)
    return find_contained_later_heading(code, cands, 0, len(span_text))


def apply_overshoot_guard(
    segments: list[ItemSegment],
    breakdowns: dict[str, ConfidenceBreakdown],
    candidates: list[HeadingCandidate],
) -> int:
    """Boundary-bleed guard: a substantive offset-exact pass span whose body
    contains a plausible later-item heading is overshooting — force
    needs_review and cap confidence via a zero-scored heavy component
    (total ≤ ~0.74). Combined spans (status partial), reference stubs,
    reassembled wrapper bodies and already-degraded items keep their existing
    handling. Returns the number of segments flagged."""
    flagged = 0
    for seg in segments:
        if seg.status != "pass" or seg.provenance != "offset_exact_span":
            continue
        if seg.end_offset <= seg.start_offset:
            continue
        hit = find_contained_later_heading(
            seg.item_code, candidates, seg.start_offset, seg.end_offset)
        if hit is None:
            continue
        seg.needs_review = True
        seg.warnings.append(
            f"overshoot: contains later item heading {hit.code} "
            f"({hit.heading_text[:60]!r} at offset {hit.start}) — the span tail has "
            f"swallowed the next item's body; needs_review")
        bd = breakdowns.get(seg.item_code)
        if bd is not None:
            if not any(c.name == OVERSHOOT_CONTAINMENT_COMPONENT for c in bd.components):
                bd.components.append(CC(
                    name=OVERSHOOT_CONTAINMENT_COMPONENT, score=0.0,
                    max_score=OVERSHOOT_COMPONENT_MAX,
                    reason=f"span body contains a plausible later item heading "
                           f"({hit.code} at offset {hit.start}) — boundary overshoot"))
            seg.confidence = bd.total
        else:
            seg.confidence = min(seg.confidence, 0.75)
        flagged += 1
    return flagged


def resolve_items(doc: NormalizedDocument, candidates: list[HeadingCandidate],
                  filing_id: str) -> tuple[list[ItemSegment], dict[str, ConfidenceBreakdown]]:
    resolved = _select_candidates(candidates)
    _infer_combined_headings(resolved)
    chosen_items = [(code, r) for code, r in resolved.items() if r.chosen]
    chosen_items.sort(key=lambda x: x[1].chosen.start)  # type: ignore[union-attr]

    # end offset = start of the next chosen item that begins strictly later.
    # min-over-later (not "next in list") so combined items sharing one start
    # both get the full shared span instead of a zero-length one.
    all_starts = sorted({r.chosen.start for _, r in chosen_items})  # type: ignore[union-attr]
    terminal_code = chosen_items[-1][0] if chosen_items else None
    ends: dict[str, int] = {}
    appended_excluded: dict[str, tuple[int, int]] = {}  # code -> (cut_end, raw_end)
    rescan_cut: dict[str, tuple[int, int, str]] = {}  # code -> (cut, raw_end, what)
    for code, r in chosen_items:
        assert r.chosen is not None
        later = [s for s in all_starts if s > r.chosen.start]
        raw_end = later[0] if later else _end_of_document_body(doc, r.chosen.end)
        # Terminal-item runaway guard: a filing may bind an appended Financial
        # Section / annual report after the last item heading (the JPM/XOM
        # "wrapper 10-K" pattern). Cut it off so the terminal item does not
        # swallow ~300K-1M chars of misattributed financial statements.
        if code == terminal_code:
            cut = detect_appended_section_cut(doc, r.chosen.start, raw_end)
            if cut is not None:
                appended_excluded[code] = (cut, raw_end)
                raw_end = cut
        # Scoped next-item rescan (end-boundary bleed fix): a later expected
        # item's heading inside this span means the resolver's end came from
        # the wrong (too-late) anchor — cut at the intermediate heading. Can
        # only shorten; the trimmed tail lands in the next item / a gap.
        rescanned = _rescan_end_cut(doc, candidates, code, r.chosen, raw_end)
        if rescanned is not None and rescanned[0] < raw_end:
            rescan_cut[code] = (rescanned[0], raw_end, rescanned[1])
            raw_end = rescanned[0]
        ends[code] = raw_end

    segments: list[ItemSegment] = []
    breakdowns: dict[str, ConfidenceBreakdown] = {}

    for code in VALID_CODES:
        r = resolved[code]
        canonical = CANONICAL_ITEM_TITLES[code]

        if r.chosen is None:
            status = "reserved" if code == "6" else "missing"
            segments.append(ItemSegment(
                filing_id=filing_id, item_code=code, canonical_title=canonical,
                extracted_heading="", start_offset=0, end_offset=0,
                text_sha256="", status=status, confidence=0.0,
                warnings=r.warnings + [f"no heading candidate found for item {code}"],
                evidence=_evidence_for(doc, r),
            ))
            continue

        start, end = r.chosen.start, ends[code]
        # strip trailing page furniture (PART dividers, page numbers, running
        # headers) that would otherwise leak into the span end
        end, trimmed = trim_trailing_furniture(doc, start, end)
        text = doc.slice(start, end)
        warnings = list(r.warnings)
        if trimmed:
            warnings.append(f"trimmed trailing page furniture: {', '.join(trimmed)}")
        if code in appended_excluded:
            cut, raw = appended_excluded[code]
            warnings.append(
                f"excluded {raw - cut} chars of an appended non-item section (bound financial "
                f"statements / annual report) that followed this item's body; items that point "
                f"into it are marked incorporated_by_reference"
            )
        if code in rescan_cut:
            cut, raw, what = rescan_cut[code]
            warnings.append(
                f"end rescan: span cut at {what} (offset {cut}, was {raw}) — the raw end "
                f"overshot a later item's heading; the trimmed tail is not dropped, it "
                f"belongs to the following item(s) or the unclassified-gap view"
            )

        # body = text after the heading line — what we classify
        nl = text.find("\n")
        body = text[nl + 1:].strip() if nl != -1 else ""

        # verifier: machine-checkable conditions, three-state
        checks = [
            ConditionCheck(condition="heading_at_segment_start", required=True,
                           observed="pass" if text.lstrip().lower().startswith(
                               r.chosen.heading_text[:20].lower()) else "fail"),
            ConditionCheck(condition="start_before_end", required=True,
                           observed="pass" if start < end else "fail"),
            ConditionCheck(condition="segment_nonempty_body", required=True,
                           observed="pass" if len(text.strip()) > len(r.chosen.heading_text) else "fail"),
            ConditionCheck(condition="no_unresolved_toc_signals", required=True,
                           observed="unknown" if (r.chosen.toc_reasons and not r.rejected_toc) else "pass"),
        ]
        verdict = combine_checks(checks)

        status = "pass"
        content_kind = "substantive"
        ref_target = classify_reference_stub(body)
        if r.chosen.combined_with:
            warnings.append(
                f"combined heading: items {code} and {r.chosen.combined_with} share one span"
            )
            status = "partial"
            content_kind = "combined"
        elif ref_target is not None:
            # Short body that only points elsewhere (proxy, another item, a
            # financial-statement note, an appended section, a page range).
            # Marking this pass would be a silent failure — SPEC 7.2 / 4.1.
            status = "incorporated_by_reference"
            content_kind = "reference_stub"
            warnings.append(
                f"body is a reference stub pointing to {ref_target}; the span is the pointer "
                f"text only, not the referenced content"
            )
        elif code == "6" and len(text.strip()) < 200 and _RESERVED_RE.search(text):
            status = "reserved"
            content_kind = "boilerplate_none"  # "[Reserved]" is a complete short answer
        elif r.ambiguous:
            status = "ambiguous"
        elif verdict.status == "fail":
            status = "partial"
            warnings.append(f"verifier: {verdict.reason}")
        elif verdict.status == "unknown":
            status = "ambiguous"
            warnings.append(f"verifier: {verdict.reason}")
        elif is_boilerplate_none(body):
            content_kind = "boilerplate_none"

        breakdown = _confidence(doc, r, start, end, verdict.status == "pass", content_kind)
        breakdowns[code] = breakdown

        segments.append(ItemSegment(
            filing_id=filing_id, item_code=code, canonical_title=canonical,
            extracted_heading=r.chosen.heading_text,
            start_offset=start, end_offset=end,
            text_sha256=sha256_text(text),
            status=status,
            confidence=breakdown.total,
            warnings=warnings,
            evidence=_evidence_for(doc, r) + [
                BoundaryEvidence(
                    kind="sequence_check",
                    detail=verdict.reason,
                    source_offset_start=start,
                    source_offset_end=min(end, start + 200),
                    quote=text[:120],
                )
            ],
        ))

    return segments, breakdowns
