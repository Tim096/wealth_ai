"""P0-6 four-dimension hard budget (SK 四維硬預算): steps / tokens / USD /
wall-clock. Checked at the HEAD of every agent-loop turn — the first exceeded
dimension stops the run before another LLM call or action is spent, and the
final verdict still comes from the verifier over what was actually achieved.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Budget:
    """A dimension set to 0 is unlimited. `exceeded` returns the FIRST
    exceeded dimension as a human-readable reason ('' = within budget), so
    the trace records exactly which cap fired."""

    max_steps: int = 0            # planner turns already taken
    max_tokens: int = 0           # accumulated LLM input+output tokens
    max_usd: float = 0.0          # accumulated LLM cost
    max_wall_clock_s: float = 0.0  # seconds since the run started

    def exceeded(self, *, steps: int, tokens: int, usd: float,
                 wall_clock_s: float) -> str:
        if self.max_steps and steps >= self.max_steps:
            return f"steps {steps} >= cap {self.max_steps}"
        if self.max_tokens and tokens >= self.max_tokens:
            return f"tokens {tokens} >= cap {self.max_tokens}"
        if self.max_usd and usd >= self.max_usd:
            return f"llm_cost ${usd:.4f} >= cap ${self.max_usd:.4f}"
        if self.max_wall_clock_s and wall_clock_s >= self.max_wall_clock_s:
            return f"wall_clock {wall_clock_s:.1f}s >= cap {self.max_wall_clock_s:.1f}s"
        return ""
