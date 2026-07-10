from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class LLMCallRecord(BaseModel):
    """One accounted LLM call. Feeds cost_latency_report.md and the dashboard."""

    call_id: str
    run_id: str
    purpose: str  # e.g. 'planner', 'selector_repair', 'boundary_adjudicator'
    model: str
    prompt_sha256: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: float
    schema_valid: bool  # did the output parse against the required JSON schema
    prompt_log_path: Optional[str] = None  # link into prompts/ when applicable
