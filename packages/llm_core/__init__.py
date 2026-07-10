"""Controlled LLM access layer.

Both apps go through this layer so every LLM call is (a) schema-constrained,
(b) cost- and latency-accounted, (c) logged as evidence. No module calls a
provider SDK directly.
"""

from llm_core.calls import LLMCallRecord

__all__ = ["LLMCallRecord"]
