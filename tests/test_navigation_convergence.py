"""BUCKET 3 — navigation convergence: reduce premature give_up and strengthen
the stagnation→replan strategy switch, WITHOUT breaking the impossible-task
refusal path.

Two levers under test:
  (a) early-give_up gate: a soft give_up ('can't find it') with ample step
      budget left is rejected until a genuinely different approach is tried; a
      give_up naming a HARD block / impossibility is honoured at once (fast).
  (b) stagnation nudge: a detected loop/stall DIRECTS a strategy switch
      (restates the planned subgoal) and the frozen-page detector trips one
      observation earlier.
"""

import pytest

from browser_core import BrowserTaskContract, SuccessCondition
from browser_agent.agent import StepTrace, _hard_giveup, stagnation_nudge
from browser_agent.planner import PlannerDecision


# ---------- (a) give_up classification (pure) ----------

def test_hard_giveup_classifies_blocks_and_impossibility():
    # HARD blocks / impossibilities -> honoured immediately (fast refusal)
    for r in ("This page needs a login to continue",
              "A CAPTCHA / unusual traffic wall appeared",
              "The site returns HTTP 403 Forbidden to automation",
              "Behind a paywall; subscription required",
              "This task is impossible — the product does not exist",
              "No such filing exists on EDGAR"):
        assert _hard_giveup(r), r
    # SOFT give_ups -> NOT hard, so the budget gate governs them
    for r in ("can't find the search button",
              "no candidate advances the task on this screen",
              "the results look empty", ""):
        assert not _hard_giveup(r), r


# ---------- (b) stagnation nudge: strategy switch + earlier stall ----------

def _ptrace(n, action="click", selector='[data-aid="3"]'):
    return [StepTrace(step="planner", action=action, ok=False, mode="agent",
                      selector_used=selector) for _ in range(n)]


def test_loop_nudge_restates_subgoal_for_strategy_switch():
    # a detected loop now DIRECTS the switch by restating the planned subgoal,
    # and the first-rung nudge prescribes a concrete different approach
    steps = _ptrace(4)
    hashes = [f"h{i}" for i in range(6)]               # page changed: isolate loop
    n = stagnation_nudge(steps, hashes, ["click:fail", "click:ok"], 5, 20,
                         plan_steps=["open EDGAR", "download the 10-K"])
    assert n.startswith("NUDGE(")
    assert "download the 10-K" in n                    # subgoal restated
    assert "switch approach" in n.lower()              # directed strategy change


def test_page_stall_detected_one_observation_earlier():
    # 3 identical hashes (2 unchanged transitions) now trips the stall detector;
    # before BUCKET 3 it needed 4, so distinct-move wander on a frozen page was
    # caught one step later.
    steps = [StepTrace(step="planner", action=a, ok=True, mode="agent")
             for a in ("click", "fill", "press")]
    n = stagnation_nudge(steps, ["h1", "h1", "h1"], ["click:ok", "fill:ok"], 5, 10)
    assert n.startswith("NUDGE(") and "page unchanged" in n


# ---------- integration planners ----------

class _GiveUpTwiceThenSucceedPlanner:
    """Emulates the observed premature-give_up failure: give_up twice with a
    soft reason, then — only because the harness kept demanding a real attempt —
    goto the target URL, which satisfies the contract."""
    def __init__(self, url: str) -> None:
        self.url = url
        self.calls = 0

    def available(self) -> bool:
        return True

    def next_action(self, task, success_conditions, obs, history,
                    plan_steps=None, image_path=None) -> PlannerDecision:
        self.calls += 1
        if self.calls <= 2:
            return PlannerDecision(kind="give_up", reason="can't find the button")
        from browser_core.actions import GotoAction
        return PlannerDecision(kind="action", action=GotoAction(url=self.url),
                               reason="try the target URL directly")


class _HardBlockGiveUpPlanner:
    def __init__(self) -> None:
        self.calls = 0

    def available(self) -> bool:
        return True

    def next_action(self, task, success_conditions, obs, history,
                    plan_steps=None, image_path=None) -> PlannerDecision:
        self.calls += 1
        return PlannerDecision(
            kind="give_up",
            reason="this page requires login and the task is impossible")


@pytest.mark.integration
def test_multistep_task_not_abandoned_before_budget(tmp_path):
    """Before BUCKET 3a: the second give_up (step 1) was honoured, so the run
    quit before ever trying the target URL -> loss. After: the soft give_up is
    rejected while ample budget remains, the agent is forced to a different
    approach, and the task actually completes."""
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    from browser_agent.agent import BrowserAgent
    from browser_agent.memory_store import MemoryStore

    contract = BrowserTaskContract(
        task_id="multistep", natural_language_task="reach the target page",
        expected_outcome="landmark visible",
        success_conditions=[SuccessCondition(type="text_visible", value="FOUND_IT_XYZ")])
    planner = _GiveUpTwiceThenSucceedPlanner("data:text/html,<h1>FOUND_IT_XYZ</h1>")
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        page = b.new_page()
        page.set_content("<button id='b'>go</button><p>searching</p>")
        agent = BrowserAgent(page, MemoryStore(tmp_path / "m.json"), "web", "agentic")
        run = agent.run_agentic("multistep", contract, planner, max_steps=10)
        b.close()
    assert run.status == "pass"                                    # not abandoned
    rejected = [s for s in run.steps if s.action == "give_up_rejected"]
    assert len(rejected) == 2                                      # BOTH soft give_ups rejected
    assert any(s.step == "planner" and s.action == "goto" for s in run.steps)
    # never honoured a give_up on this run
    assert not any(s.step == "planner" and s.action == "give_up" for s in run.steps)


@pytest.mark.integration
def test_impossible_task_still_refuses_fast(tmp_path):
    """The refusal path must stay fast: a give_up naming a hard block /
    impossibility is honoured on the FIRST turn — never dragged out by the
    budget gate."""
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    from browser_agent.agent import BrowserAgent
    from browser_agent.memory_store import MemoryStore

    contract = BrowserTaskContract(
        task_id="impossible", natural_language_task="do the impossible thing",
        expected_outcome="cannot be done",
        success_conditions=[SuccessCondition(type="text_visible", value="NEVER_THERE_XYZ")])
    planner = _HardBlockGiveUpPlanner()
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        page = b.new_page()
        page.set_content("<p>a wall</p>")
        agent = BrowserAgent(page, MemoryStore(tmp_path / "m.json"), "web", "agentic")
        run = agent.run_agentic("impossible", contract, planner, max_steps=10)
        b.close()
    assert planner.calls == 1                                      # honoured at once
    assert any(s.step == "planner" and s.action == "give_up" for s in run.steps)
    assert not any(s.action == "give_up_rejected" for s in run.steps)
    assert run.status != "pass"                                    # verifier still judges
