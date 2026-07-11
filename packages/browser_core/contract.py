"""Task contract (SPEC 6.7): every natural-language task compiles into
machine-checkable success/forbidden conditions before execution starts.
If the verifier cannot confirm success, the run is `unknown`, never `pass`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SuccessCondition(BaseModel):
    type: Literal[
        "url_contains",
        "text_visible",
        "download_exists",
        # answer channel (P2): value is a regex the DELIVERED answer must match.
        # The answer comes from extract_text actions against the real page
        # (extracted['answer']), never from the LLM's self-report; no answer
        # extracted => the deliverable was never produced => fail.
        "answer_matches",
        "table_extracted",
        "field_value_equals",
        "screenshot_region_changed",
    ]
    value: str
    # P0-5 latch semantics (WebCanvas key-node, arXiv:2406.12373): a condition
    # observed satisfied mid-run is banked permanently ("satisfied at step N")
    # even if a later navigation hides it — kills the false negative. WC's
    # blind spot: a pure latch cannot express "satisfied then destroyed"
    # (add to cart, then remove). Such a condition sets revocable=True: it
    # never latches and must hold at the FINAL observation.
    revocable: bool = False


class ForbiddenCondition(BaseModel):
    type: Literal[
        "error_text_visible",
        "captcha_visible",
        "login_required",
        "wrong_domain",
    ]
    value: str


class BrowserTaskContract(BaseModel):
    task_id: str
    natural_language_task: str
    expected_outcome: str
    # min_length=0: an open-ended task legitimately compiles to ZERO conditions
    # (the honest preflight answer "nothing is machine-checkable" must be a legal
    # contract, not a ValidationError that punishes honesty). The verifier turns
    # an empty list into an honest `unknown`, never a vacuous pass.
    success_conditions: list[SuccessCondition] = Field(min_length=0)
    forbidden_conditions: list[ForbiddenCondition] = Field(default_factory=list)
