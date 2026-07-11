"""Open-ended task set — zero-success-condition honesty check (FIX-1).

An open-ended task ("找找有什麼有趣的商品") honestly compiles to ZERO
machine-checkable success conditions. The bug this locks against: the honest
path (preflight reports no conditions) was rejected by the contract schema
(min_length=1 → ValidationError → the whole run became ERROR) — the system
punished honesty. The correct behaviour, measured end-to-end here:

  · zero crashes  — an empty-condition contract is legal and the run completes;
  · zero silent (vacuous) passes — no evidence can prove an open-ended task,
    so `pass` is never a correct verdict;
  · all honest `unknown` — the agent still executes and records a trace for
    human review; forbidden conditions are STILL checked (they can fail).

Reuses the Script-Mode driver from tools/impossible_tasks.py. Offline,
deterministic, no LLM.

Reads  data/browser_eval/tasks.json -> "open_ended_tasks"
Writes data/browser_eval/open_ended/open_ended_results.json

Usage: .venv/Scripts/python tools/open_ended_tasks.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from browser_agent.agent import BrowserAgent
from browser_agent.memory_store import MemoryStore

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))                    # `tools.` imports when run as a script
from tools.impossible_tasks import build, uri    # noqa: E402
from tools.eval_worker import (                  # noqa: E402
    RUNS_ROOT, HarnessAbort, arm_watchdog, harness_report, load_done_summary,
    run_guarded, should_abort,
)
TASKS = ROOT / "data" / "browser_eval" / "tasks.json"
OUT = ROOT / "data" / "browser_eval" / "open_ended"
RUNS = RUNS_ROOT                                 # per-task summary.json root (P0-9)


def run_all(tasks: list[dict], resume: bool = False) -> list[dict]:
    """P0-9: guarded like impossible_tasks.run_all — per-task summary.json,
    Playwright watchdog, >30% error abort. A raised task is BOTH a measured
    crash row (FIX-1: the crash IS the failure mode under test, so it stays in
    summarize) AND a harness-error for the abort guard / harness block."""
    rows: list[dict] = []
    n_error = n_attempted = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1000, "height": 800})
        arm_watchdog(page)
        for task in tasks:
            if resume:
                prior = load_done_summary(task["task_id"], out_root=RUNS)
                if prior:
                    row = prior["row"]
                    row["harness_status"] = "done"
                    row["resumed"] = True
                    rows.append(row)
                    continue
            mem = MemoryStore(OUT / f"_mem-{task['task_id']}.json")

            def _one(task=task, mem=mem):
                page.goto(uri(task["site"]))
                agent = BrowserAgent(page, mem, site="mockshop", task_type="search",
                                     artifact_dir=None, evidence_store=None)
                steps, contract = build(task)
                run = agent.run(task["task_id"], steps, contract)
                return {
                    "task_id": task["task_id"], "site": task["site"],
                    "expected": task["expect_status"], "status": run.status,
                    "crashed": False,
                    "matches_expected": run.status == task["expect_status"],
                    # any `pass` with zero success conditions is by definition
                    # vacuous — nothing was proven
                    "vacuous_pass": run.status == "pass",
                    "steps_executed": len(run.steps),
                    "verifier_status": run.verifier.status,
                    "verifier_reason": run.verifier.reason,
                    "missing_evidence": run.verifier.missing_evidence,
                }

            summary = run_guarded(task["task_id"], _one, out_root=RUNS)
            (OUT / f"_mem-{task['task_id']}.json").unlink(missing_ok=True)
            n_attempted += 1
            if summary["harness_status"] == "done":
                row = summary["row"]
                row["harness_status"] = "done"
            else:
                # a crash IS the measured failure mode here — keep the crashed-row
                # shape for summarize(), plus the harness axis for the guard
                n_error += 1
                row = {
                    "task_id": task["task_id"], "site": task["site"],
                    "expected": task["expect_status"], "status": "error",
                    "crashed": True, "matches_expected": False,
                    "vacuous_pass": False, "steps_executed": 0,
                    "verifier_status": "", "verifier_reason": summary["error"],
                    "missing_evidence": [],
                    "harness_status": "error", "harness_error": summary["error"],
                }
            rows.append(row)
            if should_abort(n_error, n_attempted):
                raise HarnessAbort(rows, n_error, n_attempted)
        browser.close()
    return rows


def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    return {
        "n_open_ended": n,
        "crashes": sum(r["crashed"] for r in rows),
        "vacuous_passes": sum(r["vacuous_pass"] for r in rows),
        "honest_unknown": sum(r["status"] == "unknown" for r in rows),
        "honest_unknown_rate": round(sum(r["status"] == "unknown" for r in rows) / n, 6) if n else None,
        "traces_recorded": sum(r["steps_executed"] > 0 for r in rows),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    spec = json.loads(TASKS.read_text(encoding="utf-8"))
    tasks = spec.get("open_ended_tasks", [])
    if not tasks:
        raise SystemExit("no open_ended_tasks in data/browser_eval/tasks.json")

    aborted = False
    try:
        rows = run_all(tasks)
    except HarnessAbort as ab:
        rows = ab.rows          # partial rows are persisted, not thrown away
        aborted = True
        print(ab)
    metrics = summarize(rows)
    out = {
        "generated_by": "tools/open_ended_tasks.py",
        "source_tasks": "data/browser_eval/tasks.json -> open_ended_tasks",
        "harness": harness_report(rows, n_planned=len(tasks), aborted=aborted),
        "definition": {
            "vacuous_pass": "status 'pass' on a contract with ZERO success conditions — "
                            "nothing was proven, so pass is never correct here",
            "crash": "the run raised instead of completing (the old min_length=1 "
                     "ValidationError that punished the honest empty-condition path)",
            "honest_unknown": "the agent executed, the trace was recorded, and the "
                              "verifier said unknown for lack of machine-checkable evidence",
        },
        "metrics": metrics,
        "tasks": rows,
    }
    (OUT / "open_ended_results.json").write_text(json.dumps(out, indent=2, ensure_ascii=False),
                                                 encoding="utf-8")

    print("open-ended task (honest-unknown) metrics:")
    for k, v in metrics.items():
        print(f"  {k}: {v}")
    print()
    for r in rows:
        tag = ("CRASH" if r["crashed"] else
               "VACUOUS-PASS" if r["vacuous_pass"] else
               "OK " if r["matches_expected"] else "XX ")
        print(f"  {tag:<12} {r['task_id']:<26} status={r['status']:<8} "
              f"expected={r['expected']}  steps={r['steps_executed']}")
    print(f"\nwrote {OUT / 'open_ended_results.json'}")
    if aborted:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
