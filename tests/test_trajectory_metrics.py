"""Trajectory two-dimension observation metrics (T1-4). Pure logic runs without a
browser; one integration test drives the real Script-Mode flow and checks that
repetition + side-effect metrics are attached to the run."""

import pytest

from browser_agent.agent import StepTrace, TaskRun
from browser_agent.trajectory import (
    StateSnapshot, repetition_report, side_effect_report,
)
from observability_core import VerifierResult


def st(step="planner", action="click", selector="#a", ok=True):
    return StepTrace(step=step, action=action, ok=ok, mode="agent", selector_used=selector)


# --- repetitiveness ---
def test_repetition_all_distinct_scores_zero():
    steps = [st(action="fill", selector="#q"), st(action="click", selector="#go"),
             st(action="goto", selector="")]
    r = repetition_report(steps)
    assert r["repetition_score"] == 0.0
    assert r["unique_ratio"] == 1.0
    assert not r["loop_detected"]


def test_repetition_empty_is_neutral():
    r = repetition_report([])
    assert r["n_steps"] == 0
    assert r["repetition_score"] == 0.0
    assert not r["loop_detected"]


def test_repetition_consecutive_same_move_is_a_loop():
    steps = [st(action="click", selector="#same") for _ in range(3)]
    r = repetition_report(steps)
    assert r["max_consecutive_repeat"] == 3
    assert r["loop_detected"]
    # 3 identical -> 2 of 3 steps are duplicates
    assert r["repetition_score"] == pytest.approx(2 / 3, abs=1e-6)


def test_repetition_two_step_cycle_detected():
    # A B A B — the classic stuck-agent oscillation
    steps = [st(action="fill", selector="#q"), st(action="click", selector="#go"),
             st(action="fill", selector="#q"), st(action="click", selector="#go")]
    r = repetition_report(steps)
    assert r["loop_period"] == 2 and r["loop_repeats"] == 2
    assert r["loop_detected"]
    assert r["repetition_score"] == 0.5  # 2 unique of 4


def test_repetition_selector_distinguishes_same_action():
    # same action verb but different targets = NOT a repeat
    steps = [st(action="click", selector="#a"), st(action="click", selector="#b")]
    r = repetition_report(steps)
    assert r["repetition_score"] == 0.0
    assert not r["loop_detected"]


# --- side effects ---
def _snap(ls=None, ss=None, cookies="", forms=None):
    return StateSnapshot(url="http://site/", local_storage=ls or {}, session_storage=ss or {},
                         cookies=cookies, form_values=forms or {})


def test_side_effect_real_site_is_unknown():
    r = side_effect_report(_snap(), _snap(), environment="real")
    assert r["status"] == "unknown"


def test_side_effect_missing_snapshot_is_unknown():
    r = side_effect_report(None, _snap(), environment="mock")
    assert r["status"] == "unknown"


def test_side_effect_clean_when_no_delta():
    s = _snap(ls={"theme": "dark"})
    r = side_effect_report(s, _snap(ls={"theme": "dark"}), environment="mock")
    assert r["status"] == "clean"
    assert r["n_changes"] == 0


def test_side_effect_detects_localstorage_and_form_residue():
    pre = _snap()
    post = _snap(ls={"cart": "1"}, forms={"search-box": "widget"}, cookies="consent=1")
    r = side_effect_report(pre, post, environment="mock")
    assert r["status"] == "side_effects"
    assert r["local_storage"]["added"] == {"cart": "1"}
    assert r["form_residue"]["added"] == {"search-box": "widget"}
    assert "consent" in r["cookies"]["added"]
    assert r["n_changes"] == 3


def test_side_effect_detects_changed_and_removed():
    pre = _snap(ls={"k": "1", "gone": "x"})
    post = _snap(ls={"k": "2"})
    r = side_effect_report(pre, post, environment="mock")
    assert r["local_storage"]["changed"] == {"k": {"from": "1", "to": "2"}}
    assert r["local_storage"]["removed"] == ["gone"]
    assert r["n_changes"] == 2


# --- wiring: metrics surface on TaskRun.as_dict() ---
def test_taskrun_as_dict_emits_both_dimensions():
    run = TaskRun(task_id="t", site="v1", status="pass",
                  verifier=VerifierResult(status="pass", reason="ok"),
                  steps=[st(action="fill", selector="#q"), st(action="fill", selector="#q")])
    run.side_effects = side_effect_report(_snap(), _snap(forms={"q": "widget"}), environment="mock")
    d = run.as_dict()
    assert d["repetition"]["repetition_score"] == 0.5  # duplicate fill
    assert d["side_effects"]["status"] == "side_effects"


# --- integration: real flow attaches real metrics ---
@pytest.mark.integration
def test_trajectory_metrics_on_real_run(tmp_path):
    pytest.importorskip("playwright.sync_api")
    from pathlib import Path

    from playwright.sync_api import sync_playwright

    from browser_agent.memory_store import MemoryStore
    from browser_agent.observer import PageObserver
    import tools.trajectory_metrics as tm

    root = Path(__file__).resolve().parents[1]
    if not (root / "data" / "mock_sites" / "v1" / "index.html").exists():
        pytest.skip("mock sites not present")
    task = {"task_id": "search-v1-widget", "site": "v1", "layer": "mock_baseline",
            "query": "widget", "success_text": ["results for", "Widget"]}
    mem = MemoryStore(tmp_path / "mem.json")
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        page = b.new_page()
        obs = PageObserver(page)
        page.goto(tm.uri("v1"))
        pre = obs.snapshot_state()
        steps, contract = tm.build(task)
        run = tm.BrowserAgent(page, mem, "mockshop", "search").run("search-v1-widget", steps, contract)
        post = obs.snapshot_state()
        b.close()
    run.side_effects = side_effect_report(pre, post, environment="mock")
    d = run.as_dict()
    assert run.status == "pass"
    # a clean 2-step search is not repetitive
    assert not d["repetition"]["loop_detected"]
    # typing "widget" into the search box leaves form residue = an observable side effect
    assert d["side_effects"]["status"] == "side_effects"
    assert "widget" in str(d["side_effects"]["form_residue"]["added"]).lower()
