"""EvidenceRecord schema — the shared contract of the whole platform.

Mirrors docs/SPEC.md section 5. Field names are kept identical to the SPEC's
TypeScript definition so the frontend and reports can consume them verbatim.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

AppName = Literal["browser_agent", "sec_extractor"]

StepStatus = Literal["pass", "fail", "unknown", "partial"]

VerifierStatus = Literal["pass", "fail", "unknown"]

EvidenceType = Literal[
    "screenshot",
    "trace",
    "dom_snapshot",
    "source_span",
    "html_offset",
    "log",
    "metric",
    "llm_judgment",
    "download_artifact",
]


class VerifierResult(BaseModel):
    """Three-state verdict. `unknown` is an honest boundary, never a disguised pass."""

    status: VerifierStatus
    reason: str
    required_evidence: list[str] = Field(default_factory=list)
    observed_evidence: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    # Why this `unknown` is unknown — the two kinds are NOT interchangeable:
    #   unverifiable=False: evidence is MISSING. The task may still be
    #       completable; an agent should keep working and a premature "done"
    #       should still be rejected.
    #   unverifiable=True:  the remaining conditions CANNOT discriminate a right
    #       answer from a wrong one (see browser_agent.verifier), so no number of
    #       further steps could ever turn this into a pass. Working on is
    #       guaranteed waste.
    # This is a control signal for callers deciding whether to continue; it never
    # softens the verdict itself, which stays `unknown`.
    unverifiable: bool = False


class EvidenceRecord(BaseModel):
    run_id: str
    app: AppName
    step_id: str
    timestamp: str
    input_hash: str
    output_hash: str
    tool_used: str
    llm_model: Optional[str] = None
    cost_usd: Optional[float] = None
    latency_ms: float
    status: StepStatus
    evidence_type: EvidenceType
    artifact_path: str
    verifier_result: VerifierResult
