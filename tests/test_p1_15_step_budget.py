"""P1-15 tests: task-configurable step budget.

resolve_max_steps precedence (CLI override > task max_steps field > difficulty
tier > default 8), difficulty tiers easy 8 / medium 15 / hard 25, watchdog
timeout scaling with the step budget, and the P0-6 Budget caps remaining the
hard stop even under an enlarged (hard-tier) loop budget.
"""

import sys
from pathlib import Path

import pytest

from browser_agent.agent import (
    DEFAULT_MAX_STEPS, STEP_BUDGET_BY_DIFFICULTY, resolve_max_steps,
)
from browser_core import BrowserTaskContract, Budget, SuccessCondition

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.eval_worker import WORKER_TASK_TIMEOUT_S  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import browser_eval as be  # noqa: E402


def test_default_stays_8_for_existing_sets():
    # existing task defs carry neither max_steps nor difficulty -> unchanged 8
    assert DEFAULT_MAX_STEPS == 8
    assert resolve_max_steps() == 8
    assert resolve_max_steps({}) == 8
    assert resolve_max_steps({"task_id": "search-v1-widget", "layer": "mock_baseline"}) == 8


def test_difficulty_tiers():
    assert STEP_BUDGET_BY_DIFFICULTY == {"easy": 8, "medium": 15, "hard": 25}
    assert resolve_max_steps({"difficulty": "easy"}) == 8
    assert resolve_max_steps({"difficulty": "medium"}) == 15
    assert resolve_max_steps({"difficulty": "hard"}) == 25
    assert resolve_max_steps({"difficulty": "HARD"}) == 25      # case-insensitive
    assert resolve_max_steps({"difficulty": "nightmare"}) == 8  # unknown tier -> default


def test_task_field_beats_difficulty_and_override_beats_all():
    task = {"max_steps": 40, "difficulty": "medium"}
    assert resolve_max_steps(task) == 40                  # field > tier
    assert resolve_max_steps(task, override=12) == 12     # CLI override > field
    assert resolve_max_steps({"difficulty": "hard"}, override=5) == 5


def test_malformed_values_fall_through_never_zero_the_run():
    assert resolve_max_steps({"max_steps": 0}) == 8
    assert resolve_max_steps({"max_steps": -3, "difficulty": "medium"}) == 15
    assert resolve_max_steps({"max_steps": "12"}) == 8    # wrong type -> ignored
    assert resolve_max_steps({"max_steps": True}) == 8    # bool is not a budget
    assert resolve_max_steps({"max_steps": 10}, override=0) == 10  # bad override ignored


def test_watchdog_timeout_scales_with_step_budget():
    # base budget -> base timeout; larger budget -> linear scale; smaller
    # budget never shrinks below the base deadline
    assert be.watchdog_timeout_s(DEFAULT_MAX_STEPS) == pytest.approx(WORKER_TASK_TIMEOUT_S)
    assert be.watchdog_timeout_s(25) == pytest.approx(WORKER_TASK_TIMEOUT_S * 25 / 8)
    assert be.watchdog_timeout_s(15) == pytest.approx(WORKER_TASK_TIMEOUT_S * 15 / 8)
    assert be.watchdog_timeout_s(2) == pytest.approx(WORKER_TASK_TIMEOUT_S)


def test_cli_flag_reaches_the_harness():
    # the flag is plumbed end to end: main + both pass runners take max_steps
    import inspect
    assert "max_steps" in inspect.signature(be.main).parameters
    assert "max_steps" in inspect.signature(be.run_agentic_pass).parameters
    assert "max_steps" in inspect.signature(be.run_parallel_pass).parameters


class _NoopLoopPlanner:
    """Noops every turn — the run only ends when a budget stops it."""
    def available(self):
        return True

    def next_action(self, task, success_conditions, obs, history,
                    plan_steps=None, image_path=None):
        from browser_agent.planner import PlannerDecision
        return PlannerDecision(kind="noop", reason="stuck")


@pytest.mark.integration
def test_p0_6_budget_still_hard_stops_a_hard_tier_run(tmp_path):
    # a hard-tier task resolves to 25 loop steps, but Budget(max_steps=2)
    # stays the HARD stop — the enlarged loop budget never loosens P0-6 caps
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    from browser_agent.agent import BrowserAgent
    from browser_agent.memory_store import MemoryStore

    loop_budget = resolve_max_steps({"difficulty": "hard"})
    assert loop_budget == 25
    contract = BrowserTaskContract(
        task_id="hard-budget", natural_language_task="find the secret page",
        expected_outcome="secret visible",
        success_conditions=[SuccessCondition(type="text_visible", value="NEVER_THERE_XYZ")])
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        page = b.new_page()
        page.set_content("<p>plain page</p>")
        agent = BrowserAgent(page, MemoryStore(tmp_path / "m.json"), "live", "agentic")
        run = agent.run_agentic("hard-budget", contract, _NoopLoopPlanner(),
                                max_steps=loop_budget, budget=Budget(max_steps=2))
        b.close()
    assert sum(s.step == "planner" for s in run.steps) == 2   # not 25
    stop = next(s for s in run.steps if s.step == "budget")
    assert stop.action == "stop" and "steps 2 >= cap 2" in stop.detail
    assert run.status != "pass"                               # verifier still judged
