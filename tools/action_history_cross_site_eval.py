"""Offline cross-site probe for repeated no-effect action recovery.

Agent Mode failure analysis exposed a planner-feedback defect: action history
said only ``click:ok`` and omitted which control was clicked. This
probe drives the real BrowserAgent over three unrelated DOM shapes. Each page
puts one inert control before a working control. A generic exploration planner
tries the first untried control; ``legacy`` strips target identity from its
history view to reproduce the old information channel, while ``grounded``
uses the production history unchanged.

No LLM, network, judge, or answer labels are involved.

Usage: .venv/Scripts/python tools/action_history_cross_site_eval.py
"""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

from browser_agent.agent import BrowserAgent
from browser_agent.memory_store import MemoryStore
from browser_agent.planner import PlannerDecision
from browser_core import BrowserTaskContract, ElementTarget, SuccessCondition
from browser_core.actions import ClickAction

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "browser_eval" / "action_history" / "results.json"

CASES = (
    {
        "id": "native_buttons",
        "done": "ALPHA COMPLETE",
        "html": """
            <main><h1>Alpha Console</h1>
              <button>Preview</button>
              <button onclick="done.textContent='ALPHA COMPLETE'">Apply</button>
              <p id="done">Ready</p>
            </main>""",
    },
    {
        "id": "aria_links",
        "done": "BRAVO COMPLETE",
        "html": """
            <main><h1>Bravo Portal</h1>
              <a href="#" role="button" onclick="return false">Open menu</a>
              <a href="#" role="button"
                 onclick="done.textContent='BRAVO COMPLETE';return false">Confirm</a>
              <p id="done">Ready</p>
            </main>""",
    },
    {
        "id": "custom_role_buttons",
        "done": "CHARLIE COMPLETE",
        "html": """
            <main><h1>Charlie Workspace</h1>
              <div role="button" tabindex="0">Details</div>
              <div role="button" tabindex="0"
                   onclick="done.textContent='CHARLIE COMPLETE'">Finish</div>
              <p id="done">Ready</p>
            </main>""",
    },
)

_TARGET_LABEL = re.compile(r'target=[^|]*?"([^"]+)"')


class ExploreUntriedControlPlanner:
    """Choose the first visible clickable label not named in action history."""

    def __init__(self, legacy_history: bool) -> None:
        self.legacy_history = legacy_history

    def next_action(self, task, success_conditions, obs, history,
                    plan_steps=None, image_path=None):
        visible_history = history
        if self.legacy_history:
            visible_history = [entry.split(" |", 1)[0] for entry in history]
        tried = {match.group(1) for entry in visible_history
                 if (match := _TARGET_LABEL.search(entry))}
        for candidate in obs.candidates:
            if not candidate.visible:
                continue
            if candidate.tag not in {"button", "a", "div"} and candidate.role != "button":
                continue
            label = candidate.aria_label or candidate.text or candidate.id
            if label and label not in tried:
                target = ElementTarget(selector=candidate.aid_selector(), selector_type="css")
                return PlannerDecision(
                    kind="action", action=ClickAction(target=target),
                    reason=f'explore untried control "{label}"')
        return PlannerDecision(kind="give_up", reason="all visible controls were tried")


def _run_case(page, temp: Path, case: dict, legacy: bool) -> dict:
    page.set_content(case["html"])
    contract = BrowserTaskContract(
        task_id=f'{case["id"]}-{"legacy" if legacy else "grounded"}',
        natural_language_task="complete this page using visible controls",
        expected_outcome=case["done"],
        success_conditions=[SuccessCondition(type="text_visible", value=case["done"])],
    )
    memory = MemoryStore(temp / f'{case["id"]}-{"legacy" if legacy else "grounded"}.json')
    agent = BrowserAgent(page, memory, case["id"], "cross-site-probe")
    run = agent.run_agentic(
        contract.task_id, contract, ExploreUntriedControlPlanner(legacy), max_steps=4)
    return {
        "case_id": case["id"],
        "mode": "legacy_generic_history" if legacy else "grounded_action_history",
        "status": run.status,
        "executed_clicks": sum(
            step.step == "planner" and step.action == "click" for step in run.steps),
        "repeated_no_effect_blocks": sum(
            step.diagnosis == "repeated_no_effect" for step in run.steps),
    }


def main() -> int:
    rows = []
    with tempfile.TemporaryDirectory(prefix="action-history-eval-") as td:
        temp = Path(td)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            for case in CASES:
                rows.append(_run_case(page, temp, case, legacy=True))
                rows.append(_run_case(page, temp, case, legacy=False))
            browser.close()

    def summary(mode: str) -> dict:
        selected = [row for row in rows if row["mode"] == mode]
        passed = sum(row["status"] == "pass" for row in selected)
        return {"passed": passed, "total": len(selected), "pass_rate": passed / len(selected)}

    result = {
        "protocol": (
            "offline deterministic cross-site mechanism probe; three distinct DOM shapes; "
            "same generic exploration policy; no LLM/network/judge"),
        "before": summary("legacy_generic_history"),
        "after": summary("grounded_action_history"),
        "cases": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["after"]["passed"] == len(CASES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
