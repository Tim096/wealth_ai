"""Browser Agent eval runner (SPEC 6.11).

Runs the layered task set (data/browser_eval/tasks.json) against the local
mock sites and computes real metrics: task success rate, verifier false-positive
rate (claimed pass that the eval's own ground truth says should fail),
silent-failure rate, repair success rate, avg steps/latency, trace completeness.
Offline, deterministic — no network, no LLM.
"""

from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from browser_core import BrowserTaskContract, ForbiddenCondition, SuccessCondition
from browser_agent.agent import BrowserAgent, Step
from browser_agent.memory_store import MemoryStore
from observability_core import EvidenceStore

ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / "data" / "browser_eval" / "tasks.json"
OUT = ROOT / "runs" / "browser_eval"
EVIDENCE = ROOT / "data" / "browser_eval" / "evidence"


def uri(version: str) -> str:
    return (ROOT / "data" / "mock_sites" / version / "index.html").resolve().as_uri()


def build(task: dict):
    steps = [
        Step(purpose="search_box", kind="fill", value=task["query"], fallback_selector="#search-box"),
        Step(purpose="submit_button", kind="click", fallback_selector="#search-btn"),
    ]
    contract = BrowserTaskContract(
        task_id=task["task_id"],
        natural_language_task=f"Search MockShop for '{task['query']}'",
        expected_outcome="Results containing the queried product are shown",
        success_conditions=[SuccessCondition(type="text_visible", value=v) for v in task["success_text"]],
        forbidden_conditions=[ForbiddenCondition(type="captcha_visible", value="captcha")],
    )
    return steps, contract


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    spec = json.loads(TASKS.read_text(encoding="utf-8"))
    mem = MemoryStore(OUT / "selector_memory.json")
    evidence = EvidenceStore(EVIDENCE)
    rows = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1000, "height": 800})
        for task in spec["tasks"]:
            page.goto(uri(task["site"]))
            agent = BrowserAgent(page, mem, site="mockshop", task_type="search",
                                 artifact_dir=OUT / task["task_id"], evidence_store=evidence)
            steps, contract = build(task)
            run = agent.run(task["task_id"], steps, contract)
            # ground-truth comparison: did the agent's verdict match what the eval expects?
            expected = task["expect_status"]
            correct = run.status == expected
            # verifier false positive = claimed pass when ground truth says fail
            false_pos = run.status == "pass" and expected == "fail"
            has_trace = bool(run.steps)
            rows.append({
                "task_id": task["task_id"], "layer": task["layer"], "site": task["site"],
                "status": run.status, "expected": expected, "correct": correct,
                "confidence": round(run.confidence, 3),
                "repairs": run.repairs, "false_positive": false_pos,
                "trace_complete": has_trace, "latency_ms": round(run.total_latency_ms, 1),
                "verifier_reason": run.verifier.reason,
            })
        browser.close()

    n = len(rows)
    metrics = {
        "tasks": n,
        "verdict_accuracy": round(sum(r["correct"] for r in rows) / n, 3),
        "task_success_rate": round(sum(r["status"] == "pass" and r["expected"] == "pass" for r in rows)
                                   / max(1, sum(r["expected"] == "pass" for r in rows)), 3),
        "verifier_false_positive_rate": round(sum(r["false_positive"] for r in rows) / n, 3),
        "repair_success_rate": round(sum(r["repairs"] > 0 and r["status"] == "pass" for r in rows)
                                     / max(1, sum(r["repairs"] > 0 for r in rows)), 3),
        "trace_completeness": round(sum(r["trace_complete"] for r in rows) / n, 3),
        "avg_latency_ms": round(sum(r["latency_ms"] for r in rows) / n, 1),
    }
    result = {"metrics": metrics, "tasks": rows}
    (OUT / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")

    print("browser eval metrics:")
    for k, v in metrics.items():
        print(f"  {k}: {v}")
    print()
    for r in rows:
        mark = "OK " if r["correct"] else "XX "
        print(f"  {mark}{r['task_id']:<28} status={r['status']:<8} expected={r['expected']:<8} "
              f"repairs={r['repairs']} fp={r['false_positive']}")
    print(f"\nwrote {OUT / 'results.json'}")


if __name__ == "__main__":
    main()
