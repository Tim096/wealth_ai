"""Eval infrastructure shared by both apps: three-state verdict logic and eval case schema."""

from eval_core.verdict import ConditionCheck, combine_checks
from eval_core.cases import EvalCase, EvalLayer

__all__ = ["ConditionCheck", "combine_checks", "EvalCase", "EvalLayer"]
