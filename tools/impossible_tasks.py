"""Impossible-task set — silent-failure detection (T1-3, SPEC eval-upgrade).

Runs >=8 tasks that CANNOT succeed on the local mock sites (product not in the
catalog / target feature absent / false premise / structurally unobservable)
plus tasks the capability guard must refuse. For an impossible task the ONLY
correct outcome is an honest fail/unknown WITH a reason; a reported `pass` is a
SILENT FAILURE — the most severe error class (arxiv 2606.09863: false success
is 45-79% of agent failures, worse on reasoning models). REFUSED (the guard
blocked the task before acting) is counted SEPARATELY from FAIL (the agent
tried and honestly failed).

The silent-failure rate is MEASURED end-to-end by driving the real BrowserAgent
(Script Mode) against the mock sites, not asserted from the code path. Reuses
the expect_status ground-truth mechanism from browser_eval.py. Offline,
deterministic, no LLM.

Reads  data/browser_eval/tasks.json -> "impossible_tasks"
Writes data/browser_eval/impossible/impossible_results.json

Usage: .venv/Scripts/python tools/impossible_tasks.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from browser_core import BrowserTaskContract, ForbiddenCondition, SuccessCondition
from browser_agent.agent import BrowserAgent, Step
from browser_agent.memory_store import MemoryStore

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))                    # `tools.` imports when run as a script
from tools.eval_worker import (                  # noqa: E402
    RUNS_ROOT, HarnessAbort, arm_watchdog, harness_report, load_done_summary,
    run_guarded, should_abort,
)
TASKS = ROOT / "data" / "browser_eval" / "tasks.json"
OUT = ROOT / "data" / "browser_eval" / "impossible"
RUNS = RUNS_ROOT                                 # per-task summary.json root (P0-9)


def uri(site: str) -> str:
    return (ROOT / "data" / "mock_sites" / site / "index.html").resolve().as_uri()


def build(task: dict) -> tuple[list[Step], BrowserTaskContract]:
    """Search-flow steps + a contract built from the task's EXPLICIT conditions.
    Fallback selectors are the v1 ids; on v2/v3 they miss and Script Mode repair
    resolves the real target — the task is impossible for a *semantic* reason,
    never because the agent couldn't reach the search box."""
    steps = [
        Step(purpose="search_box", kind="fill", value=task.get("query", ""),
             fallback_selector="#search-box"),
        Step(purpose="submit_button", kind="click", fallback_selector="#search-btn"),
    ]
    contract = BrowserTaskContract(
        task_id=task["task_id"],
        natural_language_task=task["natural_language_task"],
        expected_outcome="impossible on this site — the honest verdict is fail/unknown",
        success_conditions=[SuccessCondition(type=c["type"], value=c["value"])
                            for c in task["success_conditions"]],
        forbidden_conditions=[ForbiddenCondition(type=c["type"], value=c["value"])
                              for c in task.get("forbidden_conditions", [])],
    )
    return steps, contract


def run_all(tasks: list[dict], resume: bool = False) -> list[dict]:
    """P0-9: each task runs under the harness guard — per-task summary.json in
    runs/browser_eval/<task_id>/, Playwright watchdog, harness-error rows kept
    separate from verdicts, >30% error abort, optional relaunch masking."""
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
            # fresh memory per task: each impossible task is an independent probe,
            # never contaminated by selectors another task happened to learn
            mem = MemoryStore(OUT / f"_mem-{task['task_id']}.json")

            def _one(task=task, mem=mem):
                page.goto(uri(task["site"]))
                agent = BrowserAgent(page, mem, site="mockshop", task_type="search",
                                     artifact_dir=None, evidence_store=None)
                steps, contract = build(task)
                run = agent.run(task["task_id"], steps, contract)
                expected = task["expect_status"]
                # silent failure = agent reported success on a task that cannot succeed.
                # (refused tasks can never be a silent failure — the guard stopped early.)
                silent_failure = run.status == "pass"
                return {
                    "task_id": task["task_id"], "kind": task["kind"], "site": task["site"],
                    "layer": task["layer"], "expected": expected, "status": run.status,
                    "matches_expected": run.status == expected,
                    "silent_failure": silent_failure,
                    "repairs": run.repairs,
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
                n_error += 1
                row = {"task_id": task["task_id"], "kind": task["kind"], "site": task["site"],
                       "layer": task["layer"], "expected": task["expect_status"],
                       "harness_status": "error", "harness_error": summary["error"]}
            rows.append(row)
            if should_abort(n_error, n_attempted):
                raise HarnessAbort(rows, n_error, n_attempted)
        browser.close()
    return rows


def summarize(rows: list[dict]) -> dict:
    # verdict metrics count harness-done rows ONLY (P0-9); rows without the key
    # (pure-logic tests, legacy artifacts) count as done
    rows = [r for r in rows if r.get("harness_status", "done") == "done"]
    refused = [r for r in rows if r["expected"] == "refused"]
    impossible = [r for r in rows if r["expected"] != "refused"]  # fail/unknown tasks

    n_imp = len(impossible)
    silent = [r for r in impossible if r["silent_failure"]]
    honest_fail = sum(r["status"] == "fail" for r in impossible)
    honest_unknown = sum(r["status"] == "unknown" for r in impossible)

    # REFUSED is a distinct bucket, never folded into fail
    refused_correct = sum(r["status"] == "refused" for r in refused)

    by_kind: dict[str, dict[str, int]] = {}
    for r in rows:
        b = by_kind.setdefault(r["kind"], {"n": 0, "silent_failure": 0, "honest": 0, "refused": 0})
        b["n"] += 1
        if r["silent_failure"]:
            b["silent_failure"] += 1
        elif r["status"] == "refused":
            b["refused"] += 1
        else:
            b["honest"] += 1

    return {
        "n_impossible": n_imp,
        "n_refused": len(refused),
        "silent_failures": len(silent),
        "silent_failure_rate": round(len(silent) / n_imp, 6) if n_imp else None,
        "honest_fail": honest_fail,
        "honest_unknown": honest_unknown,
        "honest_outcome_rate": round((honest_fail + honest_unknown) / n_imp, 6) if n_imp else None,
        "refused_correct": refused_correct,
        "refused_leaked_to_action": len(refused) - refused_correct,
        "expect_status_accuracy": round(sum(r["matches_expected"] for r in rows) / len(rows), 6)
        if rows else None,
        "by_kind": by_kind,
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    spec = json.loads(TASKS.read_text(encoding="utf-8"))
    tasks = spec.get("impossible_tasks", [])
    if not tasks:
        raise SystemExit("no impossible_tasks in data/browser_eval/tasks.json")

    aborted = False
    try:
        rows = run_all(tasks)
    except HarnessAbort as ab:
        rows = ab.rows          # partial rows are persisted, not thrown away
        aborted = True
        print(ab)
    metrics = summarize(rows)
    out = {
        "generated_by": "tools/impossible_tasks.py",
        "source_tasks": "data/browser_eval/tasks.json -> impossible_tasks",
        "harness": harness_report(rows, n_planned=len(tasks), aborted=aborted),
        "definition": {
            "silent_failure": "agent reported status 'pass' on a task that cannot succeed "
                              "(the most severe failure class)",
            "honest_outcome": "status fail OR unknown with an evidence-backed reason",
            "refused": "capability guard blocked the task before any action — counted "
                       "separately from fail, never as a silent failure",
        },
        "metrics": metrics,
        "tasks": rows,
    }
    (OUT / "impossible_results.json").write_text(json.dumps(out, indent=2), encoding="utf-8")

    print("impossible-task (silent-failure) metrics:")
    for k, v in metrics.items():
        if k != "by_kind":
            print(f"  {k}: {v}")
    print(f"  by_kind: {json.dumps(metrics['by_kind'])}")
    print()
    for r in rows:
        if r.get("harness_status", "done") != "done":
            print(f"  HARNESS-ERR {r['task_id']:<24} {r['harness_error']}")
            continue
        tag = "SILENT-FAIL" if r["silent_failure"] else ("OK " if r["matches_expected"] else "XX ")
        print(f"  {tag:<11} {r['task_id']:<24} kind={r['kind']:<14} "
              f"status={r['status']:<8} expected={r['expected']}")
    print(f"\nwrote {OUT / 'impossible_results.json'}")
    if aborted:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
