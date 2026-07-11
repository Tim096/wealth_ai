"""P0-10 agent-mode cross-run replay cache + shadow-mode cache verification.

Pure tests cover the ReplayCache persistence/keying, the action<->ReplayStep
distillation, the cache FP-rate in TaskRun.as_dict and the dom_fingerprint
read-back accessor; integration tests drive the full loops — a verified run
banks its actions and the next run replays them with ZERO planner calls, a
drifted page invalidates the entry, and a script-mode cache hit is shadow-
checked (sampled + fingerprint-forced) with divergences counted.
"""

import pytest

from browser_core import BrowserTaskContract, ElementTarget, SuccessCondition
from browser_core.actions import (
    ClickAction, DownloadAction, FillAction, GotoAction, KeyboardAction,
    MouseAction, PressAction,
)
from browser_agent.memory_store import MemoryStore
from browser_agent.observer import ElementCandidate, Observation, structural_hashes
from browser_agent.replay_cache import (
    ReplayCache, ReplayStep, action_from_step, step_from_action,
)


def cand(**kw):
    base = dict(index=0, tag="input", type="text", id="", name="", role="", aria_label="",
                placeholder="", text="", href="", visible=True, x=0, y=0)
    base.update(kw)
    return ElementCandidate(**base)


def obs(cands):
    return Observation(url="u", title="t", visible_text="", candidates=cands)


# --- ReplayCache persistence + keying ---
def test_replay_cache_roundtrip_keyed_by_task(tmp_path):
    rc = ReplayCache(tmp_path / "replay_cache.json")
    steps = [ReplayStep(action="goto", value="https://x"),
             ReplayStep(action="fill", value="widget", selector="#q",
                        element_hash="EX", element_hash_stable="ST", label="fill box")]
    rc.bank("site", "search", "find widget", steps, timestamp="2026-01-01")
    rc.save()
    reloaded = ReplayCache(tmp_path / "replay_cache.json")
    got = reloaded.lookup("site", "search", "find widget")
    assert got == steps
    # the task text is part of the key — a DIFFERENT task never gets served
    # another task's fill values (whitespace-normalised, not fuzzy)
    assert reloaded.lookup("site", "search", "find gadget") == []
    assert reloaded.lookup("site", "search", "find   widget") == got
    # banking again bumps success_count; invalidate removes the entry
    reloaded.bank("site", "search", "find widget", steps)
    assert reloaded._data[ReplayCache._key("site", "search", "find widget")][
        "success_count"] == 2
    reloaded.invalidate("site", "search", "find widget")
    assert reloaded.lookup("site", "search", "find widget") == []


# --- action -> ReplayStep distillation ---
def test_step_from_action_records_durable_identity():
    c = cand(index=3, id="q", name="q", aria_label="Search products", parent_path="form")
    o = obs([c])
    t = ElementTarget(selector='[data-aid="3"]', selector_type="css")
    rs = step_from_action(FillAction(target=t, value="widget"), o, label="fill the box")
    assert rs.action == "fill" and rs.value == "widget" and rs.selector == "#q"
    assert (rs.element_hash, rs.element_hash_stable) == structural_hashes(c)
    assert rs.label == "fill the box"
    # press keeps its key; goto/keyboard need no element
    assert step_from_action(PressAction(target=t, key="Enter"), o).key == "Enter"
    assert step_from_action(GotoAction(url="https://x"), o).value == "https://x"
    kb = step_from_action(KeyboardAction(text="", keys="Escape"), o)
    assert kb.action == "keyboard" and kb.key == "Escape"
    # a URL/current-page download needs no element identity
    dl = step_from_action(DownloadAction(url="https://x/f.htm"), o)
    assert dl.action == "download" and dl.value == "https://x/f.htm" and not dl.selector


def test_step_from_action_refuses_unreplayable_actions():
    o = obs([cand(index=3, id="q")])
    # mouse coordinates do not survive a new session -> not bankable
    assert step_from_action(MouseAction(x=10, y=20), o) is None
    # a non-aid selector cannot be resolved back to an observed candidate
    t = ElementTarget(selector="#raw", selector_type="css")
    assert step_from_action(ClickAction(target=t), o) is None
    # an aid that is not in the observation is equally unusable
    gone = ElementTarget(selector='[data-aid="99"]', selector_type="css")
    assert step_from_action(ClickAction(target=gone), o) is None


# --- ReplayStep -> action resolution against the CURRENT page ---
def test_action_from_step_resolves_by_hash_then_durable_selector():
    target = cand(index=7, id="q", name="q", parent_path="form")
    ex, st = structural_hashes(target)
    rs = ReplayStep(action="fill", value="w", selector="#q",
                    element_hash=ex, element_hash_stable=st)
    # hash hit -> the exact data-aid handle of the CURRENT element
    act = action_from_step(rs, obs([cand(index=1, tag="button"), target]))
    assert act.type == "fill" and act.target.selector == '[data-aid="7"]'
    assert act.value == "w"
    # hash miss -> the durable selector (Script-Mode trust level)
    other = cand(index=2, tag="textarea", id="big")
    act2 = action_from_step(rs, obs([other]))
    assert act2.target.selector == "#q"
    # nothing to address -> None (caller abandons the cache, never a guess)
    bare = ReplayStep(action="click")
    assert action_from_step(bare, obs([other])) is None
    # element-free steps rebuild directly
    assert action_from_step(ReplayStep(action="goto", value="https://x"),
                            obs([])).url == "https://x"
    kb = action_from_step(ReplayStep(action="keyboard", key="Enter"), obs([]))
    assert kb.type == "keyboard" and kb.keys == "Enter"
    dl = action_from_step(ReplayStep(action="download", value="https://x/f"), obs([]))
    assert dl.type == "download" and dl.url == "https://x/f" and dl.target is None
    # press without a recorded key defaults to Enter
    pr = action_from_step(ReplayStep(action="press", selector="#q"), obs([]))
    assert pr.key == "Enter"


# --- cache FP-rate in the eval row ---
def test_taskrun_as_dict_reports_cache_stats_and_fp_rate():
    from browser_agent.agent import TaskRun
    from observability_core import VerifierResult

    run = TaskRun(task_id="t", site="s", status="pass",
                  verifier=VerifierResult(status="pass", reason="ok"),
                  cache_stats={"script_cache_hits": 8, "shadow_checks": 4,
                               "shadow_divergence": 1, "replay_hits": 2})
    d = run.as_dict()
    assert d["cache"]["fp_rate"] == 0.25
    assert d["cache"]["replay_hits"] == 2
    # no shadow checks -> no fp_rate (never a fake 0-of-0 number)
    empty = TaskRun(task_id="t", site="s", status="pass",
                    verifier=VerifierResult(status="pass", reason="ok"))
    assert "fp_rate" not in empty.as_dict()["cache"]


# --- dom_fingerprint read-back accessor ---
def test_memory_store_fingerprint_readback(tmp_path):
    mem = MemoryStore(tmp_path / "m.json")
    assert mem.fingerprint("s", "t", "search_box") == ""
    mem.record("s", "t", "search_box", "#q", "2026-01-01", success=True,
               dom_fingerprint="fp-one")
    assert mem.fingerprint("s", "t", "search_box") == "fp-one"
    # a failure does not overwrite the banked fingerprint
    mem.record("s", "t", "search_box", "#q", "2026-01-02", success=False)
    assert mem.fingerprint("s", "t", "search_box") == "fp-one"


# --- integration fixtures ---
_SEARCH_HTML = (
    "<form onsubmit='return false'>"
    "<input id='q' name='q' aria-label='Search products'>"
    "<button id='go' type='submit' aria-label='Search' "
    "onclick=\"document.getElementById('r').textContent="
    "'results for '+document.getElementById('q').value+': Widget Pro'\">Go</button>"
    "</form><div id='r'></div>"
)


def _search_contract(task_id="replay"):
    return BrowserTaskContract(
        task_id=task_id, natural_language_task="search the shop for widget stuff",
        expected_outcome="results shown",
        success_conditions=[SuccessCondition(type="text_visible", value="results for"),
                            SuccessCondition(type="text_visible", value="Widget Pro")])


class _CountingPlanner:
    """Fails the test loudly if the loop consults the LLM at all."""
    def __init__(self):
        self.calls = 0

    def available(self):
        return True

    def next_action(self, task, success_conditions, obs, history,
                    plan_steps=None, image_path=None):
        from browser_agent.planner import PlannerDecision
        self.calls += 1
        return PlannerDecision(kind="give_up", reason="planner should not be needed")


# --- integration: banked run replays with zero planner calls ---
@pytest.mark.integration
def test_passing_run_banks_then_replays_without_llm(tmp_path):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    from browser_agent.agent import BrowserAgent
    from browser_agent.planner import MockPlanner

    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        page = b.new_page()
        page.set_content(_SEARCH_HTML)
        # run 1: the planner works the task out; the pass banks the sequence
        agent1 = BrowserAgent(page, MemoryStore(tmp_path / "m.json"), "shop", "search")
        r1 = agent1.run_agentic("r1", _search_contract(), MockPlanner("widget"),
                                max_steps=6)
        assert r1.status == "pass"
        banked = agent1.replay.lookup("shop", "search",
                                      "search the shop for widget stuff")
        assert [s.action for s in banked] == ["fill", "click"]
        assert (tmp_path / "replay_cache.json").exists()

        # run 2: same task, fresh page — every step comes from the cache and
        # the planner is NEVER consulted (the whole LLM spend is saved)
        page.set_content(_SEARCH_HTML)
        counting = _CountingPlanner()
        agent2 = BrowserAgent(page, MemoryStore(tmp_path / "m.json"), "shop", "search")
        r2 = agent2.run_agentic("r2", _search_contract(), counting, max_steps=6)
        b.close()
    assert r2.status == "pass"
    assert counting.calls == 0
    assert r2.cache_stats["replay_hits"] == 2
    assert r2.llm_cost_usd == 0.0
    replayed = [s for s in r2.steps if s.step == "replay"]
    assert len(replayed) == 2 and all(s.ok and s.mode == "cache" for s in replayed)
    assert r2.as_dict()["cache"]["replay_hits"] == 2


# --- integration: a drifted page invalidates the entry, planner takes over ---
@pytest.mark.integration
def test_replay_divergence_invalidates_and_hands_over(tmp_path):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    from browser_agent.agent import BrowserAgent

    rc = ReplayCache(tmp_path / "replay_cache.json")
    rc.bank("shop", "search", "search the shop for widget stuff",
            [ReplayStep(action="fill", value="widget", selector="#gone",
                        element_hash="deadbeefdeadbeef",
                        element_hash_stable="beefdeadbeefdead")])
    rc.save()
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        page = b.new_page()
        page.set_content("<p>a completely different page</p>")
        counting = _CountingPlanner()
        agent = BrowserAgent(page, MemoryStore(tmp_path / "m.json"), "shop", "search")
        run = agent.run_agentic("drift", _search_contract("drift"), counting,
                                max_steps=4)
        b.close()
    assert run.status != "pass"
    assert run.cache_stats["replay_aborted"] == 1
    # the entry is gone — next run will not retry a known-stale sequence
    assert ReplayCache(tmp_path / "replay_cache.json").lookup(
        "shop", "search", "search the shop for widget stuff") == []
    aborted = next(s for s in run.steps if s.step == "replay")
    assert not aborted.ok and aborted.diagnosis == "cache_divergence"
    assert counting.calls >= 1          # the planner took over the same run


_SHADOW_HTML = (
    "<form>"
    "<input id='promo' aria-label='Promo code'>"
    "<input id='search' name='q' aria-label='Search products'>"
    "<button id='go' type='submit' aria-label='Search'>Go</button>"
    "</form>"
)


def _script_contract():
    return BrowserTaskContract(
        task_id="t", natural_language_task="search for widgets",
        expected_outcome="query filled",
        success_conditions=[SuccessCondition(type="text_visible", value="NEVER_XYZ")])


def _fill_step():
    from browser_agent.agent import Step
    return Step(purpose="search_box", kind="fill", value="widget",
                fallback_selector="#never")


# --- integration: shadow check counts a lying cache as a divergence ---
@pytest.mark.integration
def test_shadow_check_divergence_and_agreement(tmp_path):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    from browser_agent.agent import BrowserAgent

    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        page = b.new_page()

        # divergence: memory points at the BAIT field; the fill "works", but
        # the shadow re-derivation picks the real search box -> counted, and
        # the run itself is untouched (the verifier stays the only judge)
        page.set_content(_SHADOW_HTML)
        mem = MemoryStore(tmp_path / "bad.json")
        mem.record("s", "t", "search_box", "#promo", "2026-01-01", success=True)
        r_bad = BrowserAgent(page, mem, "s", "t").run("bad", [_fill_step()],
                                                      _script_contract())
        assert r_bad.cache_stats["script_cache_hits"] == 1
        assert r_bad.cache_stats["shadow_checks"] == 1
        assert r_bad.cache_stats["shadow_divergence"] == 1
        assert r_bad.as_dict()["cache"]["fp_rate"] == 1.0
        sc = next(s for s in r_bad.steps if s.step == "shadow_check")
        assert not sc.ok and sc.diagnosis == "cache_divergence"
        assert "#promo" in sc.detail and "#search" in sc.detail

        # agreement: memory points at the element purpose scoring also picks
        page.set_content(_SHADOW_HTML)
        mem2 = MemoryStore(tmp_path / "good.json")
        mem2.record("s", "t", "search_box", "#search", "2026-01-01", success=True)
        r_ok = BrowserAgent(page, mem2, "s", "t").run("ok", [_fill_step()],
                                                      _script_contract())
        b.close()
    assert r_ok.cache_stats["shadow_checks"] == 1
    assert r_ok.cache_stats.get("shadow_divergence", 0) == 0
    assert r_ok.as_dict()["cache"]["fp_rate"] == 0.0
    assert next(s for s in r_ok.steps if s.step == "shadow_check").ok


# --- integration: dom_fingerprint drift forces the check past sampling ---
@pytest.mark.integration
def test_fingerprint_drift_forces_shadow_check(tmp_path, monkeypatch):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    from browser_agent.agent import BrowserAgent

    monkeypatch.setenv("CACHE_SHADOW_EVERY", "0")     # sampling OFF entirely
    mem = MemoryStore(tmp_path / "m.json")
    # banked under a fingerprint the current page can never reproduce
    mem.record("s", "t", "search_box", "#search", "2026-01-01", success=True,
               dom_fingerprint="0123456789abcdef")
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        page = b.new_page()
        page.set_content(_SHADOW_HTML)
        r1 = BrowserAgent(page, mem, "s", "t").run("fp1", [_fill_step()],
                                                   _script_contract())
        # run 1 re-banked the REAL fingerprint; an unchanged page no longer
        # forces anything and sampling is off -> zero checks in run 2
        page.set_content(_SHADOW_HTML)
        r2 = BrowserAgent(page, mem, "s", "t").run("fp2", [_fill_step()],
                                                   _script_contract())
        b.close()
    assert r1.cache_stats["shadow_checks"] == 1
    sc = next(s for s in r1.steps if s.step == "shadow_check")
    assert "dom_fingerprint drift" in sc.detail
    assert r2.cache_stats["script_cache_hits"] == 1
    assert r2.cache_stats.get("shadow_checks", 0) == 0
