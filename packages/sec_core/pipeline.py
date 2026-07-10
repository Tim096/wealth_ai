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
from sec_core.headings import HeadingCandidate, detect_candidates
from sec_core.items import ItemSegment
from sec_core.normalize import NormalizedDocument, normalize_html
from sec_core.toc import assess_toc


@dataclass
class ExtractionResult:
    filing_id: str
    segments: list[ItemSegment]
    confidence: dict[str, ConfidenceBreakdown]
    doc: NormalizedDocument
    candidates: list[HeadingCandidate]
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

    doc = normalize_html(raw_html)
    candidates = detect_candidates(doc)
    assess_toc(doc, candidates)
    segments, breakdowns = resolve_items(doc, candidates, filing_id)

    latency_ms = (time.perf_counter() - t0) * 1000
    result = ExtractionResult(
        filing_id=filing_id,
        segments=segments,
        confidence=breakdowns,
        doc=doc,
        candidates=candidates,
        latency_ms=latency_ms,
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
