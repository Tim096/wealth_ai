"""Eval case schema shared by both apps.

Eval sets are layered (SPEC 6.10 / 7.14): public, mock, adversarial, held-out.
Held-out cases must never be used while developing detectors or prompts.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from observability_core.evidence import AppName

EvalLayer = Literal["public", "mock", "adversarial", "held_out"]


class EvalCase(BaseModel):
    case_id: str
    app: AppName
    layer: EvalLayer
    description: str
    input: dict[str, Any]
    expected: dict[str, Any]
    tags: list[str] = Field(default_factory=list)
