"""Boundary resolution (SPEC 7.10): pick the best body candidate per item,
enforce document-order consistency, derive end offsets from the next item's
start, and classify special cases (reserved / combined / incorporated by
reference / missing / ambiguous) honestly instead of faking pass.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from eval_core import ConditionCheck, combine_checks
from observability_core import sha256_text
from sec_core.adjudicator import BoundaryEvidence
from sec_core.confidence import ConfidenceBreakdown
from sec_core.confidence import ConfidenceComponent as CC
from sec_core.headings import VALID_CODES, HeadingCandidate
from sec_core.items import CANONICAL_ITEM_TITLES, ItemSegment
from sec_core.normalize import NormalizedDocument

_SIGNATURES_RE = re.compile(r"^\s*signatures?\s*$", re.IGNORECASE | re.MULTILINE)
_INCORPORATED_RE = re.compile(r"incorporated\s+(?:herein\s+)?by\s+reference", re.IGNORECASE)
_CROSS_REF_RE = re.compile(r"(?:refer\s+to|see)\s+item\s+\d{1,2}[a-cA-C]?\b", re.IGNORECASE)
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
                verifier_pass: bool) -> ConfidenceBreakdown:
    c = item.chosen
    assert c is not None
    length = end - start
    detector_count = len(c.detectors)
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
           score=1.0 if 50 <= length <= 3_000_000 else 0.0, max_score=1.0,
           reason=f"segment length {length} chars"),
        CC(name="cross_detector_agreement", score=min(detector_count, 3) / 3.0, max_score=1.0,
           reason=f"{detector_count} independent detectors agree"),
        CC(name="verifier_result", score=1.0 if verifier_pass else 0.0, max_score=1.0,
           reason="verifier pass" if verifier_pass else "verifier did not pass"),
    ]
    return ConfidenceBreakdown(components=comps)


def resolve_items(doc: NormalizedDocument, candidates: list[HeadingCandidate],
                  filing_id: str) -> tuple[list[ItemSegment], dict[str, ConfidenceBreakdown]]:
    resolved = _select_candidates(candidates)
    chosen_items = [(code, r) for code, r in resolved.items() if r.chosen]
    chosen_items.sort(key=lambda x: x[1].chosen.start)  # type: ignore[union-attr]

    # end offset = start of the next chosen item that begins strictly later.
    # min-over-later (not "next in list") so combined items sharing one start
    # both get the full shared span instead of a zero-length one.
    all_starts = sorted({r.chosen.start for _, r in chosen_items})  # type: ignore[union-attr]
    ends: dict[str, int] = {}
    for code, r in chosen_items:
        assert r.chosen is not None
        later = [s for s in all_starts if s > r.chosen.start]
        ends[code] = later[0] if later else _end_of_document_body(doc, r.chosen.end)

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
        text = doc.slice(start, end)
        warnings = list(r.warnings)

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
        if r.chosen.combined_with:
            warnings.append(
                f"combined heading: items {code} and {r.chosen.combined_with} share one span"
            )
            status = "partial"
        body_len = len(text) - len(r.chosen.heading_text)
        if code in {"10", "11", "12", "13", "14"} and len(text) < 4000 and _INCORPORATED_RE.search(text):
            status = "incorporated_by_reference"
            warnings.append("content incorporated by reference to proxy statement; span is the reference text only")
        elif body_len < 600 and _CROSS_REF_RE.search(text):
            # e.g. JPM Item 11: entire body is "Refer to Item 10." — a stub
            # pointing at another item, not real content. Marking this pass
            # would be a silent failure.
            status = "incorporated_by_reference"
            warnings.append(
                "body is a cross-reference stub to another item; span is the reference text only"
            )
        elif code == "6" and len(text.strip()) < 200 and _RESERVED_RE.search(text):
            status = "reserved"
        elif r.ambiguous:
            status = "ambiguous"
        elif verdict.status == "fail":
            status = "partial"
            warnings.append(f"verifier: {verdict.reason}")
        elif verdict.status == "unknown":
            status = "ambiguous"
            warnings.append(f"verifier: {verdict.reason}")

        breakdown = _confidence(doc, r, start, end, verdict.status == "pass")
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
