"""Offline extraction pipeline entry point: raw 10-K HTML in, ItemSegments +
evidence out. Deterministic — no LLM anywhere on this path; ambiguous
segments are flagged for the (separate, optional) adjudicator.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from observability_core import EvidenceRecord, EvidenceStore, VerifierResult, sha256_text
from sec_core.boundary import resolve_items
from sec_core.confidence import ConfidenceBreakdown
from sec_core.cross_ref import (
    build_cross_reference_segments,
    detect_cross_reference_index,
    scan_bare_index,
)
from sec_core.headings import HeadingCandidate, detect_candidates
from sec_core.items import ItemSegment
from sec_core.normalize import NormalizedDocument, normalize_html
from sec_core.toc import assess_toc
from sec_core.topic_check import check_topic


@dataclass
class ExtractionResult:
    filing_id: str
    segments: list[ItemSegment]
    confidence: dict[str, ConfidenceBreakdown]
    doc: NormalizedDocument
    candidates: list[HeadingCandidate]
    filing_class: str = "standard"  # standard | cross_reference_index | non_10k
    latency_ms: float = 0.0
    warnings: list[str] = field(default_factory=list)

    def segment(self, code: str) -> ItemSegment:
        return next(s for s in self.segments if s.item_code == code)

    def text_of(self, code: str) -> str:
        s = self.segment(code)
        return self.doc.slice(s.start_offset, s.end_offset)


def extract_from_html(
    raw_html: str,
    filing_id: str,
    evidence_store: EvidenceStore | None = None,
    run_id: str | None = None,
) -> ExtractionResult:
    t0 = time.perf_counter()

    # scanned-PDF / non-HTML guard (SPEC 7.10): code-enforce the 'unsupported'
    # boundary instead of only documenting it.
    head = raw_html.lstrip()[:2000]
    if head.startswith("%PDF") or "\x00" in raw_html[:4000] or (
            "<" not in head and "item" not in head.lower()):
        latency_ms = (time.perf_counter() - t0) * 1000
        doc = normalize_html("")
        return ExtractionResult(
            filing_id=filing_id, segments=[], confidence={}, doc=doc, candidates=[],
            filing_class="unsupported_scanned_or_binary", latency_ms=latency_ms,
            warnings=["input is a scanned PDF or non-HTML/binary document — unsupported; "
                      "the correct tool here is an OCR path (not an LLM), see docs/insights §3"],
        )

    doc = normalize_html(raw_html)
    candidates = detect_candidates(doc)
    assess_toc(doc, candidates)

    # Cross-reference-index filings (Intel / Citi / GE class): the main document
    # is a pointer index into a bound annual report, not the report body. Detect
    # it and classify honestly rather than emitting tiny ambiguous fragments.
    xref = detect_cross_reference_index(doc, candidates)
    if not xref.detected and len(candidates) < 8:
        # no "Item"-prefixed headings — try the bare '<code>.<title>' index form (Citi)
        xref = scan_bare_index(doc)
    if xref.detected:
        segments, breakdowns = build_cross_reference_segments(doc, xref, filing_id)
        filing_class = "cross_reference_index"
    else:
        segments, breakdowns = resolve_items(doc, candidates, filing_id)
        filing_class = "standard" if candidates else "non_10k"

    # per-item topic-consistency oracle (independent, lexical, all items) —
    # a span labelled Item 1A that has no risk-factor language is suspect even
    # if the heading matched. Flags a pass/partial item that fails its topic.
    for seg in segments:
        if seg.end_offset > seg.start_offset:
            body = doc.slice(seg.start_offset, seg.end_offset)
            nl = body.find("\n")
            body = body[nl + 1:] if nl != -1 else body
        else:
            body = ""
        tc = check_topic(seg.item_code, body)
        seg.topic_check = f"{tc.verdict}: {tc.detail}"
        if tc.verdict == "inconsistent" and seg.status in ("pass", "partial"):
            seg.needs_review = True
            seg.warnings.append(
                f"topic-consistency oracle: extracted span has no canonical "
                f"'{seg.canonical_title}' language — possible mislabel/mis-boundary; needs_review")

    latency_ms = (time.perf_counter() - t0) * 1000
    result = ExtractionResult(
        filing_id=filing_id,
        segments=segments,
        confidence=breakdowns,
        doc=doc,
        candidates=candidates,
        filing_class=filing_class,
        latency_ms=latency_ms,
    )
    if xref.detected:
        result.warnings.append(
            f"cross-reference-index 10-K detected: {xref.reason}. Items are pointers into the "
            f"annual report (needs_review); body resolution is a documented next step."
        )
    if not candidates:
        result.warnings.append("no item heading candidates found — unsupported or non-10-K document")

    if evidence_store is not None:
        rid = run_id or f"sec-{filing_id}"
        for seg in segments:
            evidence_store.append(EvidenceRecord(
                run_id=rid,
                app="sec_extractor",
                step_id=f"item-{seg.item_code}",
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                input_hash=sha256_text(raw_html),
                output_hash=seg.text_sha256 or sha256_text(""),
                tool_used="sec_core.pipeline.extract_from_html",
                latency_ms=latency_ms,
                status="pass" if seg.status == "pass" else (
                    "fail" if seg.status in ("missing",) and seg.item_code != "6" else "partial"
                ),
                evidence_type="source_span",
                artifact_path="",
                verifier_result=VerifierResult(
                    status="pass" if seg.status == "pass" else "unknown",
                    reason=f"segment status={seg.status}; " + ("; ".join(seg.warnings) or "ok"),
                    required_evidence=["heading_match", "sequence_check"],
                    observed_evidence=[e.kind for e in seg.evidence],
                    missing_evidence=[] if seg.evidence else ["heading_match"],
                ),
            ))

    return result
