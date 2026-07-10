"""LLM boundary adjudicator I/O (SPEC 7.13).

The adjudicator only chooses between existing boundary candidates when the
deterministic pipeline marks a segment ambiguous. It never produces filing
text. A decision without an exact evidence quote cannot carry high confidence.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, model_validator


class BoundaryEvidence(BaseModel):
    """Evidence backing a boundary decision, always anchored to source offsets."""

    kind: Literal[
        "heading_match",
        "toc_rejection",
        "sequence_check",
        "detector_agreement",
        "llm_adjudication",
    ]
    detail: str
    source_offset_start: int
    source_offset_end: int
    quote: str = ""


class AdjudicatorDecision(BaseModel):
    decision: Literal["candidate_a", "candidate_b", "unknown"]
    confidence: float
    evidence_quote: str
    reason: str

    @model_validator(mode="after")
    def _no_confident_decision_without_quote(self) -> "AdjudicatorDecision":
        if self.decision != "unknown" and self.confidence > 0.5 and not self.evidence_quote.strip():
            raise ValueError(
                "adjudicator may not return a confident decision without an exact evidence quote"
            )
        return self
