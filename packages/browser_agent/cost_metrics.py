"""P0-6 cost-per-outcome metrics (BG cache-aware cost accounting): cost and
correctness in the SAME artifact, so cost-per-success can be cross-read with
the eval verdict instead of living in a separate report.

Pure function over eval rows — tools/browser_eval.py's compute_metrics merges
this block; keeping the logic here keeps it unit-testable without a harness.
"""

from __future__ import annotations


def cost_metrics(rows: list[dict]) -> dict:
    """Aggregate the per-run llm_cost_usd now carried by TaskRun.as_dict().
    Only harness-done rows count (P0-9: error rows carry no verdict fields);
    a denominator of zero yields None — never a fake 0.0 that would read as
    'free successes'."""
    rows = [r for r in rows if r.get("harness_status", "done") == "done"]
    total = sum(r.get("llm_cost_usd", 0.0) for r in rows)
    n_pass = sum(r.get("status") == "pass" for r in rows)
    n_repair = sum(r.get("repairs", 0) for r in rows)
    return {
        "llm_cost_usd_total": round(total, 6),
        "cost_per_success_usd": round(total / n_pass, 6) if n_pass else None,
        "cost_per_repair_usd": round(total / n_repair, 6) if n_repair else None,
    }
