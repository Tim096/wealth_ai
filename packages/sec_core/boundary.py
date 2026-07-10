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
from sec_core.refine import (
    classify_reference_stub,
    detect_appended_section_cut,
    is_boilerplate_none,
    trim_trailing_furniture,
)

_SIGNATURES_RE = re.compile(r"^\s*signatures?\s*$", re.IGNORECASE | re.MULTILINE)
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


def resolve_items(doc: NormalizedDocument, candidates: list[HeadingCandidate],
                  filing_id: str) -> tuple[list[ItemSegment], dict[str, ConfidenceBreakdown]]:
    resolved = _select_candidates(candidates)
    chosen_items = [(code, r) for code, r in resolved.items() if r.chosen]
    chosen_items.sort(key=lambda x: x[1].chosen.start)  # type: ignore[union-attr]

    # end offset = start of the next chosen item that begins strictly later.
    # min-over-later (not "next in list") so combined items sharing one start
    # both get the full shared span instead of a zero-length one.
    all_starts = sorted({r.chosen.start for _, r in chosen_items})  # type: ignore[union-attr]
    terminal_code = chosen_items[-1][0] if chosen_items else None
    ends: dict[str, int] = {}
    appended_excluded: dict[str, tuple[int, int]] = {}  # code -> (cut_end, raw_end)
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
