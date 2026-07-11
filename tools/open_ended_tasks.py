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
TASKS = ROOT / "data" / "browser_eval" / "tasks.json"
OUT = ROOT / "data" / "browser_eval" / "open_ended"


def run_all(tasks: list[dict]) -> list[dict]:
    rows: list[dict] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1000, "height": 800})
        for task in tasks:
            mem = MemoryStore(OUT / f"_mem-{task['task_id']}.json")
            try:
                page.goto(uri(task["site"]))
                agent = BrowserAgent(page, mem, site="mockshop", task_type="search",
                                     artifact_dir=None, evidence_store=None)
                steps, contract = build(task)
                run = agent.run(task["task_id"], steps, contract)
                rows.append({
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
                })
            except Exception as e:  # noqa: BLE001 — a crash IS the measured failure mode
                rows.append({
                    "task_id": task["task_id"], "site": task["site"],
                    "expected": task["expect_status"], "status": "error",
                    "crashed": True, "matches_expected": False,
                    "vacuous_pass": False, "steps_executed": 0,
                    "verifier_status": "", "verifier_reason": f"{type(e).__name__}: {e}",
                    "missing_evidence": [],
                })
            (OUT / f"_mem-{task['task_id']}.json").unlink(missing_ok=True)
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

    rows = run_all(tasks)
    metrics = summarize(rows)
    out = {
        "generated_by": "tools/open_ended_tasks.py",
        "source_tasks": "data/browser_eval/tasks.json -> open_ended_tasks",
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


if __name__ == "__main__":
    main()
