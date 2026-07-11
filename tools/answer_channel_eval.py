"""Answer-channel eval — answer-type tasks must DELIVER the answer (P2).

The observed real failure: 「找到 intc 10-k 的財報 找到裡面的最新的營收數字給我」
ended PASS after merely opening a search page — the answer was never delivered
because extract_text results were dropped and no condition type could judge
them. This runner measures the fix end-to-end, offline and deterministic:

  · the agent's extract_text output lands in extracted['answer'] and comes
    back on TaskRun.answer (the same field the test-center UI renders);
  · the answer_matches condition judges THAT text: extracted + regex match ->
    pass; extracted but unmatched -> fail; never extracted -> fail (claiming
    done without a delivery move is not done — the verifier never eats
    self-reports, even when the claim contains the correct number as bait).

Drives the real BrowserAgent (run_agentic) against the local fixture page
data/mock_sites/answer/index.html with a scripted planner. No LLM.

Reads  data/browser_eval/tasks.json -> "answer_tasks"
Writes data/browser_eval/answer_channel/answer_channel_results.json

Usage: .venv/Scripts/python tools/answer_channel_eval.py
"""

from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from browser_core import BrowserTaskContract, ElementTarget, SuccessCondition
from browser_core.actions import ExtractTextAction
from browser_agent.agent import BrowserAgent
from browser_agent.memory_store import MemoryStore
from browser_agent.planner import PlannerDecision

ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / "data" / "browser_eval" / "tasks.json"
OUT = ROOT / "data" / "browser_eval" / "answer_channel"


def uri(site: str) -> str:
    return (ROOT / "data" / "mock_sites" / site / "index.html").resolve().as_uri()


class ScriptedPlanner:
    """Deterministic stand-in for the LLM: plays a fixed script of
    {"extract": css} / {"done": reason} steps, then stops. The point under test
    is the CHANNEL (extract -> extracted['answer'] -> answer_matches), not the
    model's choices."""

    def __init__(self, script: list[dict]) -> None:
        self._script = list(script)

    def available(self) -> bool:
        return True

    def next_action(self, task, success_conditions, obs, history,
                    plan_steps=None, image_path=None) -> PlannerDecision:
        if not self._script:
            return PlannerDecision(kind="done", reason="script exhausted")
        step = self._script.pop(0)
        if "extract" in step:
            t = ElementTarget(selector=step["extract"], selector_type="css",
                              description="answer element")
            return PlannerDecision(kind="action", action=ExtractTextAction(target=t),
                                   reason=f"extract {step['extract']}")
        return PlannerDecision(kind="done", reason=step.get("done", "claims done"))


def build_contract(task: dict) -> BrowserTaskContract:
    return BrowserTaskContract(
        task_id=task["task_id"],
        natural_language_task=task["natural_language_task"],
        expected_outcome="the extracted answer text matches the deliverable pattern",
        success_conditions=[SuccessCondition(type=c["type"], value=c["value"])
                            for c in task["success_conditions"]],
    )


def run_all(tasks: list[dict]) -> list[dict]:
    rows: list[dict] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1000, "height": 800})
        for task in tasks:
            mem = MemoryStore(OUT / f"_mem-{task['task_id']}.json")
            page.goto(uri(task["site"]))
            agent = BrowserAgent(page, mem, site="answer", task_type="answer",
                                 artifact_dir=None, evidence_store=None)
            run = agent.run_agentic(task["task_id"], build_contract(task),
                                    ScriptedPlanner(task["script"]), max_steps=4)
            rows.append({
                "task_id": task["task_id"], "kind": task["kind"], "site": task["site"],
                "expected": task["expect_status"], "status": run.status,
                "matches_expected": run.status == task["expect_status"],
                # the delivery channel itself, observable in the artifact:
                "answer": run.answer,
                "answer_delivered": bool(run.answer),
                "answer_as_expected": bool(run.answer) == task["expect_answer"],
                # pass without a delivered answer would be the INTC failure reborn
                "silent_failure": run.status == "pass" and not run.answer,
                "verifier_status": run.verifier.status,
                "verifier_reason": run.verifier.reason,
            })
            (OUT / f"_mem-{task['task_id']}.json").unlink(missing_ok=True)
        browser.close()
    return rows


def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    return {
        "n_answer_tasks": n,
        "matches_expected": sum(r["matches_expected"] for r in rows),
        "answers_delivered": sum(r["answer_delivered"] for r in rows),
        "answer_channel_intact": all(r["answer_as_expected"] for r in rows),
        "silent_failures": sum(r["silent_failure"] for r in rows),
        "pass_with_answer": sum(r["status"] == "pass" and r["answer_delivered"] for r in rows),
        "fail_without_delivery": sum(r["status"] == "fail" and not r["answer_delivered"]
                                     for r in rows),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    spec = json.loads(TASKS.read_text(encoding="utf-8"))
    tasks = spec.get("answer_tasks", [])
    if not tasks:
        raise SystemExit("no answer_tasks in data/browser_eval/tasks.json")

    rows = run_all(tasks)
    metrics = summarize(rows)
    out = {
        "generated_by": "tools/answer_channel_eval.py",
        "source_tasks": "data/browser_eval/tasks.json -> answer_tasks",
        "definition": {
            "answer_channel": "extract_text output -> extracted['answer'] (append) -> "
                              "TaskRun.answer; answer_matches judges the extracted text, "
                              "never the model's self-report",
            "silent_failure": "status 'pass' with NO delivered answer — the INTC "
                              "premature-landmark failure shape; must be zero",
            "no_delivery_fail": "claiming done without any extract action is fail: the "
                                "task asked for an answer and none was produced",
        },
        "metrics": metrics,
        "tasks": rows,
    }
    (OUT / "answer_channel_results.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    print("answer-channel metrics:")
    for k, v in metrics.items():
        print(f"  {k}: {v}")
    print()
    for r in rows:
        tag = ("SILENT-FAIL" if r["silent_failure"] else
               "OK " if r["matches_expected"] and r["answer_as_expected"] else "XX ")
        ans = (r["answer"][:50] + "…") if len(r["answer"]) > 50 else r["answer"]
        print(f"  {tag:<11} {r['task_id']:<26} status={r['status']:<6} "
              f"expected={r['expected']:<6} answer={ans!r}")
    print(f"\nwrote {OUT / 'answer_channel_results.json'}")


if __name__ == "__main__":
    main()
