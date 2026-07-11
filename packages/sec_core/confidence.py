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


# Weight of a zero-scored overshoot component (boundary.py containment guard /
# size_bands.py size-ratio guard), appended post-hoc only when the signal
# fires — like third_engine_agreement. The base breakdown maxes at 10.0, so a
# single firing signal caps an otherwise-perfect item at 10/13.5 ≈ 0.74:
# below the 0.75 review line, and it de-saturates the 0.9-1.0 confidence bin
# the NTU boundary-bleed errors hide in.
OVERSHOOT_COMPONENT_MAX = 3.5


class ConfidenceBreakdown(BaseModel):
    components: list[ConfidenceComponent] = Field(default_factory=list)

    # Always-present base components (built by boundary._confidence). Guard
    # layers append CONDITIONAL components post-hoc only when their signal
    # fires: 'third_engine_agreement' (third_engine.py), and the overshoot
    # signals 'overshoot_containment' (boundary.py) / 'overshoot_size_ratio'
    # (size_bands.py) — calibration sees them through the same breakdown.
    COMPONENT_NAMES: tuple[str, ...] = (
        "heading_strength",
        "title_similarity",
        "sequence_consistency",
        "toc_disambiguation",
        "boundary_length_sanity",
        "cross_detector_agreement",
        "content_substantiveness",
        "verifier_result",
    )

    @property
    def total(self) -> float:
        max_total = sum(c.max_score for c in self.components)
        if max_total <= 0:
            return 0.0
        return max(0.0, min(1.0, sum(c.score for c in self.components) / max_total))
