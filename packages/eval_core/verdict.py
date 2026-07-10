"""Three-state verdict combination.

Core rule (SPEC 4.2 / 6.7): a task may only be `pass` when every required
condition is observed as satisfied. Any observed violation is `fail`. If
nothing is violated but at least one condition could not be observed, the
verdict is `unknown` — never `pass`. This is the structural defence against
silent failure: lack of evidence can never upgrade to success.
"""

from __future__ import annotations

from pydantic import BaseModel

from observability_core.evidence import VerifierResult, VerifierStatus


class ConditionCheck(BaseModel):
    """Outcome of checking one success/forbidden condition."""

    condition: str  # human-readable, e.g. 'url_contains:example.com/results'
    required: bool  # True = success condition, False = forbidden condition
    observed: VerifierStatus  # pass = satisfied, fail = violated, unknown = could not observe
    evidence_ref: str = ""  # artifact path or evidence step_id backing this check


def combine_checks(checks: list[ConditionCheck]) -> VerifierResult:
    if not checks:
        return VerifierResult(
            status="unknown",
            reason="no conditions were checked; refusing to claim success without evidence",
            required_evidence=[],
            observed_evidence=[],
            missing_evidence=["at least one verifiable condition"],
        )

    required = [c.condition for c in checks]
    observed = [c.condition for c in checks if c.observed != "unknown"]
    missing = [c.condition for c in checks if c.observed == "unknown"]

    violations = [c.condition for c in checks if c.observed == "fail"]
    if violations:
        return VerifierResult(
            status="fail",
            reason=f"violated: {', '.join(violations)}",
            required_evidence=required,
            observed_evidence=observed,
            missing_evidence=missing,
        )

    if missing:
        return VerifierResult(
            status="unknown",
            reason=f"insufficient evidence for: {', '.join(missing)}",
            required_evidence=required,
            observed_evidence=observed,
            missing_evidence=missing,
        )

    return VerifierResult(
        status="pass",
        reason="all conditions observed and satisfied",
        required_evidence=required,
        observed_evidence=observed,
        missing_evidence=[],
    )
