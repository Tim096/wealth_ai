"""Failure taxonomy (SPEC 6.8). Self-correction is diagnosis-driven, not retry-driven:
every failure is classified before any repair is attempted, and each type maps to a
specific repair strategy (or to an honest `unknown`).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

FailureType = Literal[
    "selector_not_found",
    "multiple_candidates",
    "click_no_effect",
    "modal_blocking",
    "wrong_page",
    "timeout",
    "form_validation_error",
    "empty_result",
    "download_missing",
    "silent_failure_risk",
]


class FailureSpec(BaseModel):
    failure_type: FailureType
    detection: str
    repair_strategy: str
    repairable: bool
    # Honesty flag: is this type actually produced by the current diagnoser +
    # dispatched to its strategy today, or is it catalogued for flows (download,
    # multi-page forms) that the current demo does not exercise? Declared != dispatched.
    dispatched: bool = True


FAILURE_TAXONOMY: dict[str, FailureSpec] = {
    s.failure_type: s
    for s in [
        FailureSpec(
            failure_type="selector_not_found",
            detection="selector matches no element",
            repair_strategy="fall back to role / text / aria / placeholder targeting",
            repairable=True,
        ),
        FailureSpec(
            failure_type="multiple_candidates",
            detection="selector matches more than one element",
            repair_strategy="re-rank candidates by role, label, position, visible text",
            repairable=True,
        ),
        FailureSpec(
            failure_type="click_no_effect",
            detection="URL and DOM unchanged after click",
            repair_strategy="click parent/child element, or press Enter instead",
            repairable=True,
        ),
        FailureSpec(
            failure_type="modal_blocking",
            detection="cookie banner or modal intercepts pointer events",
            repair_strategy="dismiss modal or accept required options, then retry",
            repairable=True,
        ),
        FailureSpec(
            failure_type="wrong_page",
            detection="URL / title / expected text mismatch",
            repair_strategy="backtrack to last verified checkpoint",
            repairable=True,
        ),
        FailureSpec(
            failure_type="timeout",
            detection="wait condition not met within timeout",
            repair_strategy="switch wait condition or reduce task granularity",
            repairable=True,
        ),
        FailureSpec(
            failure_type="form_validation_error",
            detection="validation error text visible after submit",
            repair_strategy="refill fields once; otherwise mark fail",
            repairable=True,
            dispatched=False,  # activates when a form-submit flow exists (not the search demo)
        ),
        FailureSpec(
            failure_type="empty_result",
            detection="result container present but empty",
            repair_strategy="broaden query once; otherwise mark unknown",
            repairable=True,
        ),
        FailureSpec(
            failure_type="download_missing",
            detection="no download artifact on disk after download action",
            repair_strategy="parse href / network response directly",
            repairable=True,
            dispatched=False,  # activates when a download flow exists (not the search demo)
        ),
        FailureSpec(
            failure_type="silent_failure_risk",
            detection="verifier lacks evidence to confirm or deny success",
            repair_strategy="none — mark unknown and list missing evidence",
            repairable=False,
        ),
    ]
}
