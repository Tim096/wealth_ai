"""Offline extraction pipeline entry point: raw 10-K HTML in, ItemSegments +
evidence out. Deterministic — no LLM anywhere on this path; ambiguous
segments are flagged for the (separate, optional) adjudicator.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

from observability_core import EvidenceRecord, EvidenceStore, VerifierResult, sha256_text
from sec_core.adjudicator import BoundaryEvidence
from sec_core.boundary import resolve_items
from sec_core.confidence import ConfidenceBreakdown
from sec_core.cross_ref import (
    build_cross_reference_segments,
    detect_cross_reference_index,
    reassemble_wrapper_bodies,
    scan_bare_index,
)
from sec_core.headings import HeadingCandidate, detect_candidates
from sec_core.items import ItemSegment
from sec_core.normalize import NormalizedDocument, normalize_html
from sec_core.size_bands import apply_size_bands
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
    # LLM adjudication tier accounting (SPEC 7.13). Always zero on the
    # deterministic path — only adjudicate_ambiguous() increments these.
    llm_calls: int = 0
    llm_input_tokens: int = 0
    llm_output_tokens: int = 0
    llm_cost_usd: float = 0.0
    llm_call_records: list = field(default_factory=list)  # list[LLMCallRecord]

    def segment(self, code: str) -> ItemSegment:
        return next(s for s in self.segments if s.item_code == code)

    def text_of(self, code: str) -> str:
        s = self.segment(code)
        return self.doc.slice(s.start_offset, s.end_offset)


_ADJUDICATOR_SYSTEM = (
    "You adjudicate one ambiguous SEC 10-K item boundary. Two heading candidates are "
    "given with surrounding source context. Decide which candidate starts the real item "
    "body (not a table-of-contents entry, cross-reference or stray mention). Reply with "
    'ONE JSON object exactly: {"decision": "candidate_a"|"candidate_b"|"unknown", '
    '"confidence": <0.0-1.0>, "evidence_quote": "exact substring copied verbatim from '
    'one candidate\'s context", "reason": "short reason"}. Never generate, summarize or '
    'rewrite filing text. If unsure, decision must be "unknown".'
)


def _candidate_context(doc: NormalizedDocument, start: int, before: int = 200, after: int = 700) -> str:
    return doc.slice(max(0, start - before), min(len(doc.text), start + after))


def adjudicate_ambiguous(result: ExtractionResult, client=None) -> int:
    """LLM boundary-adjudication tier (SPEC 7.13). OFF the deterministic path:
    runs only when explicitly invoked (or via SEC_LLM_ADJUDICATE=1), and only on
    segments the deterministic pipeline marked ambiguous that still have a
    surviving runner-up candidate. The LLM only chooses between existing
    candidates — it never produces filing text, and the chosen span/offsets are
    left unchanged (the decision is recorded as evidence + warning;
    needs_review stays raised). Schema gate: output must validate as
    AdjudicatorDecision AND the evidence_quote must be a verbatim substring of
    the supplied context, else the decision is downgraded to unknown. Every
    call is accounted as an LLMCallRecord and aggregated onto the result
    (llm_calls / llm_*_tokens / llm_cost_usd). Returns the number of LLM calls.
    """
    from llm_core.calls import LLMCallRecord
    from llm_core.openai_client import OpenAIClient
    from sec_core.adjudicator import AdjudicatorDecision
    from sec_core.boundary import _score

    if client is None:
        client = OpenAIClient()
    if not client.available():
        result.warnings.append(
            "LLM adjudication requested but no client configured "
            "(set OPENAI_API_KEY / OPENAI_BASE_URL) — segments stay ambiguous")
        return 0

    calls = 0
    for seg in result.segments:
        if seg.status != "ambiguous":
            continue
        chosen = next((c for c in result.candidates
                       if c.code == seg.item_code and c.start == seg.start_offset), None)
        others = [c for c in result.candidates
                  if c.code == seg.item_code and not c.toc_rejected and c.start != seg.start_offset]
        if chosen is None or not others:
            continue  # ambiguity came from a verifier-unknown, not a runner-up duel
        runner_up = max(others, key=_score)
        ctx_a = _candidate_context(result.doc, chosen.start)
        ctx_b = _candidate_context(result.doc, runner_up.start)
        user = (
            f"Item code: {seg.item_code}\nCanonical title: {seg.canonical_title}\n\n"
            f"Candidate A (offset {chosen.start}, detectors {sorted(chosen.detectors)}, "
            f"score {_score(chosen):.2f}):\n---\n{ctx_a}\n---\n\n"
            f"Candidate B (offset {runner_up.start}, detectors {sorted(runner_up.detectors)}, "
            f"score {_score(runner_up):.2f}):\n---\n{ctx_b}\n---\n\n"
            "Which candidate starts the real item body?"
        )
        parsed, resp = client.complete_json(_ADJUDICATOR_SYSTEM, user)
        calls += 1
        result.llm_calls += 1
        result.llm_input_tokens += resp.input_tokens
        result.llm_output_tokens += resp.output_tokens
        result.llm_cost_usd += resp.cost_usd

        schema_valid = True
        try:
            decision = AdjudicatorDecision(
                decision=parsed.get("decision", "unknown"),
                confidence=float(parsed.get("confidence", 0.0)),
                evidence_quote=str(parsed.get("evidence_quote", "")),
                reason=str(parsed.get("reason", "")),
            )
        except (ValueError, TypeError):
            schema_valid = False
            decision = AdjudicatorDecision(
                decision="unknown", confidence=0.0, evidence_quote="",
                reason="adjudicator output failed schema validation")
        if (decision.decision != "unknown"
                and decision.evidence_quote not in ctx_a and decision.evidence_quote not in ctx_b):
            decision = AdjudicatorDecision(
                decision="unknown", confidence=0.0, evidence_quote="",
                reason="evidence_quote is not a verbatim substring of the supplied context — downgraded")

        result.llm_call_records.append(LLMCallRecord(
            call_id=f"{result.filing_id}-item{seg.item_code}-adj{calls}",
            run_id=f"sec-{result.filing_id}",
            purpose="boundary_adjudicator",
            model=resp.model,
            prompt_sha256=resp.prompt_sha256,
            input_tokens=resp.input_tokens,
            output_tokens=resp.output_tokens,
            cost_usd=resp.cost_usd,
            latency_ms=resp.latency_ms,
            schema_valid=schema_valid,
        ))
        picked = runner_up if decision.decision == "candidate_b" else chosen
        seg.evidence.append(BoundaryEvidence(
            kind="llm_adjudication",
            detail=f"decision={decision.decision} confidence={decision.confidence:.2f}: {decision.reason}",
            source_offset_start=picked.start,
            source_offset_end=picked.end,
            quote=decision.evidence_quote,
        ))
        seg.needs_review = True
        seg.warnings.append(
            f"LLM adjudicator: {decision.decision} (confidence {decision.confidence:.2f}); "
            f"span unchanged — decision recorded as evidence, human review still required")
    return calls


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
        # Wrapper 10-K body reassembly (JPM/XOM class): stubs that defer into
        # a Financial Section / annual report bound after the last item are
        # resolved to source-exact spans inside that appended block.
        reassemble_wrapper_bodies(doc, segments, breakdowns)

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
        # only the normal offset-exact path can be "mislabelled" — a pointer or a
        # page-anchor-resolved span is already needs_review, so don't double-flag.
        if (tc.verdict == "inconsistent" and seg.status == "pass"
                and seg.provenance == "offset_exact_span"):
            seg.needs_review = True
            seg.warnings.append(
                f"topic-consistency oracle: extracted span has no canonical "
                f"'{seg.canonical_title}' language — possible mislabel/mis-boundary; needs_review")

    # Per-(form,item) empirical size-band guardrail (P0-11): a substantive
    # offset-exact pass span far outside the agree-and-pass empirical band
    # (p50/5..p50*8, data/sec_eval/size_bands/) is forced to needs_review.
    # Bands are era-keyed; the pipeline enforces the MODERN 10-K group (the
    # supported class) — pre-2003 schemas get their own group once sampled.
    apply_size_bands(segments, doc)

    # Discoverability: when Item 8 is only a pointer stub, tell the reader WHERE
    # the financial statements actually are (often Item 15) instead of leaving
    # them to hunt — the financials are extracted, just under another item.
    item8 = next((s for s in segments if s.item_code == "8"), None)
    if item8 is not None and item8.status == "incorporated_by_reference":
        fin_markers = ("consolidated balance sheet", "consolidated statements of income",
                       "consolidated statements of operations", "report of independent registered")
        best_code, best_len = None, 0
        for s in segments:
            if s.item_code == "8" or s.end_offset <= s.start_offset:
                continue
            low = doc.slice(s.start_offset, min(s.end_offset, s.start_offset + 20000)).lower()
            if any(m in low for m in fin_markers) and (s.end_offset - s.start_offset) > best_len:
                best_code, best_len = s.item_code, s.end_offset - s.start_offset
        if best_code:
            item8.warnings.append(
                f"Item 8 here is a pointer; the actual financial statements are extracted under "
                f"Item {best_code} of this filing ({best_len:,} chars) — look there for the tables.")

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

    # Optional LLM adjudication tier (SPEC 7.13): opt-in only, so the default
    # pipeline stays deterministic and $0. Adjudication latency is accounted in
    # llm_call_records, not in parse latency_ms.
    if os.environ.get("SEC_LLM_ADJUDICATE") == "1" and any(
            s.status == "ambiguous" for s in segments):
        adjudicate_ambiguous(result)

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
