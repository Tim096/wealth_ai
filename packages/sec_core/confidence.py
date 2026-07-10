"""Explainable confidence (SPEC 7.12). Confidence is a sum of named component
scores, each with a reason — never an LLM vibe. The frontend renders every
component and its deduction reason.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ConfidenceComponent(BaseModel):
    name: str  # e.g. 'heading_strength', 'toc_disambiguation'
    score: float
    max_score: float
    reason: str


class ConfidenceBreakdown(BaseModel):
    components: list[ConfidenceComponent] = Field(default_factory=list)

    COMPONENT_NAMES: tuple[str, ...] = (
        "heading_strength",
        "title_similarity",
        "sequence_consistency",
        "toc_disambiguation",
        "boundary_length_sanity",
        "cross_detector_agreement",
        "verifier_result",
    )

    @property
    def total(self) -> float:
        max_total = sum(c.max_score for c in self.components)
        if max_total <= 0:
            return 0.0
        return max(0.0, min(1.0, sum(c.score for c in self.components) / max_total))
