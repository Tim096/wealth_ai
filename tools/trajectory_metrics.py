"""Trajectory two-dimension observation metrics (T1-4, SPEC eval-upgrade).

Drives the real BrowserAgent (Script Mode) over the local mock sites and, for
each run, MEASURES two AgentRewardBench-style non-success axes (arxiv 2504.08942):

  * repetitiveness — computed from the recorded trajectory (TaskRun.steps) via
    trajectory.repetition_report; already emitted by TaskRun.as_dict().
  * side effects — a pre/post persistent-state diff (localStorage / sessionStorage
    / cookies / leftover form input) captured with PageObserver.snapshot_state
    AROUND the run. Purely observational: the agent's behaviour is unchanged.

Everything here is offline, deterministic, no LLM. Mock sites are the controlled
environment whose state we own, so side effects are attributable; a real site
would be reported `unknown` (see trajectory.side_effect_report).

Reads  data/browser_eval/tasks.json -> "tasks"
Writes data/browser_eval/trajectory/trajectory_results.json

Usage: .venv/Scripts/python tools/trajectory_metrics.py
"""

from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from browser_core import BrowserTaskContract, SuccessCondition
from browser_agent.agent import BrowserAgent, Step
from browser_agent.memory_store import MemoryStore
from browser_agent.observer import PageObserver
from browser_agent.trajectory import side_effect_report

ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / "data" / "browser_eval" / "tasks.json"
OUT = ROOT / "data" / "browser_eval" / "trajectory"


def uri(site: str) -> str:
    return (ROOT / "data" / "mock_sites" / site / "index.html").resolve().as_uri()


def build(task: dict) -> tuple[list[Step], BrowserTaskContract]:
    steps = [
        Step(purpose="search_box", kind="fill", value=task.get("query", ""),
             fallback_selector="#search-box"),
        Step(purpose="submit_button", kind="click", fallback_selector="#search-btn"),
    ]
    contract = BrowserTaskContract(
        task_id=task["task_id"],
        natural_language_task=f"search for {task.get('query', '')}",
        expected_outcome="results visible",
        success_conditions=[SuccessCondition(type="text_visible", value=t)
                            for t in task.get("success_text", [])],
    )
    return steps, contract


def run_all(tasks: list[dict]) -> list[dict]:
    rows: list[dict] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1000, "height": 800})
        observer = PageObserver(page)
        for task in tasks:
            mem = MemoryStore(OUT / f"_mem-{task['task_id']}.json")
            page.goto(uri(task["site"]))
            # pre snapshot AFTER the site loads = the clean baseline for this task
            pre = observer.snapshot_state()
            agent = BrowserAgent(page, mem, site="mockshop", task_type="search",
                                 artifact_dir=None, evidence_store=None)
            steps, contract = build(task)
            run = agent.run(task["task_id"], steps, contract)
            post = observer.snapshot_state()
            # mock sites are the controlled env -> side effects are attributable
            run.side_effects = side_effect_report(pre, post, environment="mock")
            d = run.as_dict()
            rows.append({
                "task_id": task["task_id"], "site": task["site"], "layer": task["layer"],
                "status": run.status, "repairs": run.repairs,
                "repetition": d["repetition"], "side_effects": d["side_effects"],
            })
            (OUT / f"_mem-{task['task_id']}.json").unlink(missing_ok=True)
        browser.close()
    return rows


def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    looped = [r for r in rows if r["repetition"]["loop_detected"]]
    with_side_fx = [r for r in rows if r["side_effects"].get("status") == "side_effects"]
    scores = [r["repetition"]["repetition_score"] for r in rows]
    return {
        "n_tasks": n,
        "mean_repetition_score": round(sum(scores) / n, 6) if n else None,
        "max_repetition_score": max(scores) if scores else None,
        "n_loops_detected": len(looped),
        "loop_task_ids": [r["task_id"] for r in looped],
        "n_with_side_effects": len(with_side_fx),
        "side_effect_task_ids": [r["task_id"] for r in with_side_fx],
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    spec = json.loads(TASKS.read_text(encoding="utf-8"))
    tasks = spec.get("tasks", [])
    if not tasks:
        raise SystemExit("no tasks in data/browser_eval/tasks.json")

    rows = run_all(tasks)
    metrics = summarize(rows)
    out = {
        "generated_by": "tools/trajectory_metrics.py",
        "source_tasks": "data/browser_eval/tasks.json -> tasks",
        "definition": {
            "repetition_score": "fraction of steps that repeat an earlier "
                                "(purpose, action, selector) move; 0 = all distinct",
            "loop_detected": "an immediately-repeated block, or the same move >=3x running",
            "side_effects.status": "'clean' (no persistent-state delta), 'side_effects' "
                                   "(localStorage/sessionStorage/cookie/form-residue delta), "
                                   "or 'unknown' (real site — state not attributable)",
        },
        "metrics": metrics,
        "tasks": rows,
    }
    (OUT / "trajectory_results.json").write_text(json.dumps(out, indent=2), encoding="utf-8")

    print("trajectory metrics (repetitiveness + side effects):")
    for k, v in metrics.items():
        print(f"  {k}: {v}")
    print()
    for r in rows:
        rep = r["repetition"]
        sfx = r["side_effects"].get("status")
        print(f"  {r['task_id']:<26} status={r['status']:<8} "
              f"rep_score={rep['repetition_score']:<6} loop={rep['loop_detected']!s:<5} "
              f"side_fx={sfx}")
    print(f"\nwrote {OUT / 'trajectory_results.json'}")


if __name__ == "__main__":
    main()
