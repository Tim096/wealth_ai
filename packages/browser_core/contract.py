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
        "table_extracted",
        "field_value_equals",
        "screenshot_region_changed",
    ]
    value: str


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
    success_conditions: list[SuccessCondition] = Field(min_length=1)
    forbidden_conditions: list[ForbiddenCondition] = Field(default_factory=list)
