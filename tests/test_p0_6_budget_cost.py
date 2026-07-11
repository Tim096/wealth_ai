"""P0-6 tests: four-dimension hard budget (loop-head check), llm_cost_usd +
phase timings landing on TaskRun (the dead-code fix), and cost-per-success /
cost-per-repair aggregation.
"""

import pytest

from browser_core import BrowserTaskContract, Budget, SuccessCondition
from browser_agent.cost_metrics import cost_metrics
from browser_agent.planner import PlannerDecision
from llm_core.openai_client import LLMResponse


def test_budget_reports_first_exceeded_dimension():
    b = Budget(max_steps=3, max_tokens=1000, max_usd=0.01, max_wall_clock_s=60)
    assert b.exceeded(steps=0, tokens=0, usd=0.0, wall_clock_s=0.0) == ""
    assert b.exceeded(steps=3, tokens=0, usd=0.0, wall_clock_s=0.0).startswith("steps 3")
    assert b.exceeded(steps=0, tokens=1000, usd=0.0, wall_clock_s=0.0).startswith("tokens 1000")
    assert "llm_cost" in b.exceeded(steps=0, tokens=0, usd=0.02, wall_clock_s=0.0)
    assert "wall_clock" in b.exceeded(steps=0, tokens=0, usd=0.0, wall_clock_s=61)
    # steps fire before tokens when both are over — FIRST dimension wins
    assert b.exceeded(steps=5, tokens=9999, usd=0.0, wall_clock_s=0.0).startswith("steps")


def test_budget_zero_dimension_is_unlimited():
    assert Budget().exceeded(steps=10**6, tokens=10**9, usd=10**6,
                             wall_clock_s=10**6) == ""
    # a single capped dimension leaves the others unlimited
    assert Budget(max_usd=0.5).exceeded(steps=10**6, tokens=10**9, usd=0.4,
                                        wall_clock_s=10**6) == ""


def test_cost_metrics_cost_per_success_and_repair():
    rows = [
        {"status": "pass", "repairs": 1, "llm_cost_usd": 0.02},
        {"status": "pass", "repairs": 0, "llm_cost_usd": 0.01},
        {"status": "fail", "repairs": 1, "llm_cost_usd": 0.03},
        # P0-9 harness-error row: no verdict fields, must be excluded
        {"harness_status": "error"},
    ]
    m = cost_metrics(rows)
    assert m["llm_cost_usd_total"] == pytest.approx(0.06)
    assert m["cost_per_success_usd"] == pytest.approx(0.03)   # 0.06 / 2 passes
    assert m["cost_per_repair_usd"] == pytest.approx(0.03)    # 0.06 / 2 repairs


def test_cost_metrics_zero_denominator_is_none_not_zero():
    m = cost_metrics([{"status": "fail", "repairs": 0, "llm_cost_usd": 0.05}])
    assert m["llm_cost_usd_total"] == pytest.approx(0.05)
    assert m["cost_per_success_usd"] is None                  # not a fake 0.0
    assert m["cost_per_repair_usd"] is None
    assert cost_metrics([]) == {"llm_cost_usd_total": 0.0,
                                "cost_per_success_usd": None,
                                "cost_per_repair_usd": None}


class _NoopLoopPlanner:
    """Noops every turn — the run only ends when the budget stops it."""
    def available(self):
        return True

    def next_action(self, task, success_conditions, obs, history,
                    plan_steps=None, image_path=None):
        return PlannerDecision(kind="noop", reason="stuck")


class _CostedDonePlanner:
    """Claims done immediately, with an accounted LLM call attached — the
    cost that used to be summed and then dropped on the floor."""
    def available(self):
        return True

    def next_action(self, task, success_conditions, obs, history,
                    plan_steps=None, image_path=None):
        return PlannerDecision(kind="done", reason="finished", llm=LLMResponse(
            text="{}", input_tokens=100, output_tokens=20, cost_usd=0.00123,
            latency_ms=5.0, model="fake", prompt_sha256="deadbeef"))


def _contract(task_id):
    return BrowserTaskContract(
        task_id=task_id, natural_language_task="find the secret page",
        expected_outcome="secret visible",
        success_conditions=[SuccessCondition(type="text_visible", value="NEVER_THERE_XYZ")])


@pytest.mark.integration
def test_budget_stops_the_loop_at_the_head(tmp_path):
    # P0-6 wiring: Budget(max_steps=2) under max_steps=6 — the check at the
    # loop HEAD stops the run after exactly 2 planner turns, records WHICH cap
    # fired in the trace, and the verdict still comes from the verifier.
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    from browser_agent.agent import BrowserAgent
    from browser_agent.memory_store import MemoryStore

    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        page = b.new_page()
        page.set_content("<p>plain page</p>")
        agent = BrowserAgent(page, MemoryStore(tmp_path / "m.json"), "live", "agentic")
        run = agent.run_agentic("budget-stop", _contract("budget-stop"),
                                _NoopLoopPlanner(), max_steps=6,
                                budget=Budget(max_steps=2))
        b.close()
    assert sum(s.step == "planner" for s in run.steps) == 2   # not 6
    stop = next(s for s in run.steps if s.step == "budget")
    assert stop.action == "stop" and "steps 2 >= cap 2" in stop.detail
    assert run.status != "pass"                               # verifier still judged


@pytest.mark.integration
def test_llm_cost_and_phase_timings_land_on_taskrun(tmp_path):
    # The dead-code fix: llm_cost was accumulated then thrown away. It must now
    # land on TaskRun (+ tokens + phase timings), flow into as_dict() for eval
    # rows, and replace the hardcoded cost_usd=0.0 on the verdict evidence.
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    from browser_agent.agent import BrowserAgent
    from browser_agent.memory_store import MemoryStore
    from observability_core import EvidenceStore

    ev = EvidenceStore(tmp_path / "ev")
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        page = b.new_page()
        page.set_content("<p>plain page</p>")
        agent = BrowserAgent(page, MemoryStore(tmp_path / "m.json"), "live", "agentic",
                             evidence_store=ev)
        run = agent.run_agentic("costed", _contract("costed"),
                                _CostedDonePlanner(), max_steps=1)
        b.close()
    assert run.llm_cost_usd == pytest.approx(0.00123)
    assert run.llm_tokens == 120
    assert run.phase_timings["planner_ms"] >= 0
    assert run.phase_timings["verify_ms"] > 0                 # loop + final verify
    d = run.as_dict()
    assert d["llm_cost_usd"] == pytest.approx(0.00123)
    assert d["llm_tokens"] == 120
    assert set(d["phase_timings_ms"]) == {"planner_ms", "action_ms", "verify_ms"}
    verdict_rec = ev.read_run("agent-live-costed")[-1]
    assert verdict_rec.cost_usd == pytest.approx(0.00123)     # was hardcoded 0.0
