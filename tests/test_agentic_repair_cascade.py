"""HOLE B: the self-maintenance cascade never reached the deployed path.

The assignment asks, verbatim, for "self-maintenance — detect UI or selector
changes and adjust locator strategies dynamically". The machinery exists and is
good: _resolve_and_run runs diagnose_failure -> rebind_by_hash (P0-7
deterministic structural rebind) -> repair_target (a11y purpose scoring), and
banks the outcome in selector memory.

Its only caller was run() — Script Mode. Deployment, the eval harness and the
frontend all call run_agentic(), which never called _resolve_and_run,
repair_target, rebind_by_hash, memory.preferred or memory.record, and reported
TaskRun.repairs from a hardcoded literal 0 (agent.py:1244).

The measured tell: every selector-memory key ever written is `mockshop::*` —
the scripted demo site. Not one real site was learned, because the only path
that writes memory is the path no real run takes.

These tests pin the cascade to the AGENTIC loop:
  - a failed action is diagnosed and repaired, not just handed back to the LLM
  - TaskRun.repairs counts real repairs
  - selector memory is read AND written on the agentic path, for real sites
  - the ladder order is preserved: remembered selector -> hash rebind -> scoring
  - repair stays bounded (no new LLM calls, no unbounded retry)
"""


from browser_core import BrowserTaskContract, SuccessCondition
from browser_core.actions import ClickAction, ElementTarget, FillAction
from browser_agent.memory_store import MemoryStore
from browser_agent.observer import structural_hashes

from tests.fakes_browser import candidate, fake_agent

SITE = "news.ycombinator.com"

# The element the planner aims at and MISSES: a decoy the purpose scorer
# rejects outright (score -1), standing in for a stale/leftover aid.
DECOY = candidate(index=1, tag="a", id="decoy-link", text="Sponsored", href="/ad")
# The element that actually satisfies the purpose.
REAL_LINK = candidate(index=2, tag="a", id="real-story", text="Show HN: a tiny CAD kernel",
                      href="/item?id=1")
SEARCH_BOX = candidate(index=3, tag="input", type="text", id="q",
                       placeholder="Search stories", form="f1")
SUBMIT = candidate(index=4, tag="button", type="submit", id="go", text="Search", form="f1")

CANDIDATES = [DECOY, REAL_LINK, SEARCH_BOX, SUBMIT]


def contract(value="NEVER_ON_THIS_PAGE_XYZ"):
    return BrowserTaskContract(
        task_id="hole-b", natural_language_task="open the top story",
        expected_outcome="the story page",
        success_conditions=[SuccessCondition(type="text_visible", value=value)])


class _ClickThenDonePlanner:
    """Clicks the decoy aid once (it fails), then reports done. One planner
    action — so any repair MUST come from the agent, not from re-prompting."""

    def __init__(self, action=None):
        self.action = action or ClickAction(
            target=ElementTarget(selector='[data-aid="1"]', selector_type="css",
                                 description="top story link"))
        self.calls = 0

    def available(self):
        return True

    def next_action(self, task, success_conditions, obs, history,
                    plan_steps=None, image_path=None):
        from browser_agent.planner import PlannerDecision
        self.calls += 1
        if self.calls == 1:
            return PlannerDecision(kind="action", action=self.action,
                                   reason="open the top story")
        return PlannerDecision(kind="done", reason="done")


def _run(tmp_path, planner=None, ok_selectors=('[data-aid="2"]',), memory=None,
         candidates=CANDIDATES):
    agent = fake_agent(tmp_path, site=SITE, task_type="agentic",
                       url=f"https://{SITE}/", candidates=candidates,
                       visible_text="Hacker News\nnew | past | comments",
                       ok_selectors=list(ok_selectors), memory=memory)
    run = agent.run_agentic("hole-b", contract(), planner or _ClickThenDonePlanner(),
                            max_steps=5)
    return agent, run


# ---------- the cascade reaches the agentic path at all ----------

def test_failed_agentic_action_is_diagnosed_and_repaired(tmp_path):
    """Before: the failed click was handed straight back to the planner and the
    trace had no repair entry. After: diagnose -> purpose scoring -> retry."""
    agent, run = _run(tmp_path)
    repairs = [s for s in run.steps if s.mode == "repair" and s.diagnosis]
    assert repairs, "no repair-mode step in the agentic trace"
    assert repairs[0].diagnosis == "selector_not_found"
    # it acted on the element the purpose scorer chose, not the decoy
    assert '[data-aid="2"]' in agent.executor.selectors_tried()
    assert repairs[-1].ok


def test_repairs_are_counted_not_hardcoded_zero(tmp_path):
    # agent.py:1244 read `repairs=0` literally, so the agentic path could never
    # report self-maintenance even when it happened.
    _, run = _run(tmp_path)
    assert run.repairs >= 1


def test_repair_needs_no_extra_planner_call(tmp_path):
    # the repair must be the agent's own cascade, not another LLM turn
    planner = _ClickThenDonePlanner()
    _, run = _run(tmp_path, planner=planner)
    assert run.llm_cost_usd == 0.0
    # one action turn + the done turns — the repair itself costs no planner call
    assert planner.calls <= 3


# ---------- selector memory is really read/written on the agentic path ----------

def test_agentic_run_learns_a_real_site_selector(tmp_path):
    """The `mockshop::*`-only evidence: memory was never written off the
    scripted path. A repaired agentic run must bank the durable selector."""
    agent, _ = _run(tmp_path)
    mem = agent.memory.get(SITE, "agentic", "result_link")
    assert mem is not None, f"nothing learned for {SITE}"
    assert mem.preferred_selector == "#real-story"      # durable, not the volatile aid
    assert mem.repair_history and mem.repair_history[-1].verified


def test_memory_is_persisted_to_disk(tmp_path):
    # run_agentic never called memory.save(), so even a learned selector died
    # with the process
    agent, _ = _run(tmp_path)
    saved = MemoryStore(agent.memory.path)
    assert saved.preferred(SITE, "agentic", "result_link") == "#real-story"


def test_successful_agentic_action_is_also_remembered(tmp_path):
    # learning must not require a failure first: an action that works the first
    # time is exactly the selector worth remembering
    planner = _ClickThenDonePlanner(action=ClickAction(
        target=ElementTarget(selector='[data-aid="2"]', selector_type="css")))
    agent, run = _run(tmp_path, planner=planner)
    assert run.repairs == 0                                  # nothing to repair
    assert agent.memory.preferred(SITE, "agentic", "result_link") == "#real-story"


def test_fill_action_learns_the_search_box_purpose(tmp_path):
    # purpose inference must not collapse every action into one bucket
    planner = _ClickThenDonePlanner(action=FillAction(
        target=ElementTarget(selector='[data-aid="3"]', selector_type="css"), value="rust"))
    agent, _ = _run(tmp_path, ok_selectors=['[data-aid="3"]'], planner=planner)
    assert agent.memory.preferred(SITE, "agentic", "search_box") == "#q"


# ---------- the ladder keeps its order ----------

def test_hash_rebind_precedes_purpose_scoring(tmp_path):
    """P0-7: a remembered structural hash rebinds deterministically, so the
    expensive a11y scoring is not consulted."""
    mem = MemoryStore(tmp_path / "memory.json")
    hx, hs = structural_hashes(REAL_LINK)
    # remembered from an earlier run, under a selector that no longer resolves
    mem.record(SITE, "agentic", "result_link", "#stale-selector", "t0", success=True,
               element_hash=hx, element_hash_stable=hs)
    _, run = _run(tmp_path, memory=mem)
    levels = [s.match_level for s in run.steps if s.match_level]
    assert "exact" in levels
    assert "purpose" not in levels


def test_remembered_selector_is_tried_before_scoring(tmp_path):
    """memory.preferred was never read on the agentic path. A selector already
    known to work for this purpose is the cheapest rung of the ladder."""
    mem = MemoryStore(tmp_path / "memory.json")
    mem.record(SITE, "agentic", "result_link", "#real-story", "t0", success=True)
    agent, run = _run(tmp_path, memory=mem, ok_selectors=["#real-story"])
    tried = agent.executor.selectors_tried()
    assert "#real-story" in tried
    levels = [s.match_level for s in run.steps if s.match_level]
    assert "script" in levels
    assert "purpose" not in levels


# ---------- bounded ----------

def test_repair_is_bounded_when_nothing_can_be_repaired(tmp_path):
    """Everything fails: the cascade must try its rungs once and stop — never
    spin. The step budget stays the outer bound."""
    agent, run = _run(tmp_path, ok_selectors=[])
    assert run.status != "pass"
    # each rung acts at most once per failed action; 5 steps x a few rungs
    assert len(agent.executor.calls) <= 12
    tried = [s for s in run.steps if s.mode == "repair"]
    assert tried and not any(s.ok for s in tried)   # tried, and honestly failed


def test_no_viable_candidate_is_reported_as_none(tmp_path):
    """Only a decoy on the page: the purpose scorer must refuse to pick it
    rather than repair into a wrong element."""
    _, run = _run(tmp_path, ok_selectors=[], candidates=[DECOY])
    assert any(s.match_level == "none" for s in run.steps)
    assert run.status != "pass"
