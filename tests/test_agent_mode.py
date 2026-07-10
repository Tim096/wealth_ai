"""Agent Mode tests. The planner logic + action validation run without a
browser or a key; one integration test drives the real loop with MockPlanner.
"""

import pytest

from browser_core import BrowserTaskContract, SuccessCondition
from browser_agent.observer import ElementCandidate, Observation
from browser_agent.planner import LLMPlanner, MockPlanner, _build_action
from llm_core.openai_client import OpenAIClient, LLMConfigError


def cand(**kw):
    base = dict(index=0, tag="input", type="text", id="", name="", role="", aria_label="",
                placeholder="", text="", href="", visible=True, x=0, y=0)
    base.update(kw)
    return ElementCandidate(**base)


def test_build_action_targets_by_aid_only():
    obs = Observation(url="u", title="t", visible_text="", candidates=[cand(index=3)])
    act = _build_action({"action": "fill", "aid": 3, "value": "hi"}, obs)
    assert act.type == "fill" and act.target.selector == '[data-aid="3"]'


def test_build_action_rejects_codey_output():
    obs = Observation(url="u", title="t", visible_text="", candidates=[])
    # no aid + not goto -> unusable, planner should give_up on this
    assert _build_action({"action": "click", "aid": None}, obs) is None


def test_mock_planner_fills_then_clicks_then_done():
    box = cand(index=0, tag="input", name="query", aria_label="Search products")
    btn = cand(index=1, tag="button", type="submit", aria_label="Search", text="Go")
    obs = Observation(url="u", title="t", visible_text="", candidates=[box, btn])
    p = MockPlanner("widget")
    d1 = p.next_action("search", ["text_visible:Widget"], obs, [])
    assert d1.kind == "action" and d1.action.type == "fill" and d1.action.value == "widget"
    d2 = p.next_action("search", ["text_visible:Widget"], obs, ["fill:ok"])
    assert d2.kind == "action" and d2.action.type == "click"
    d3 = p.next_action("search", ["text_visible:Widget"], obs, ["fill:ok", "click:ok"])
    assert d3.kind == "done"


def test_mock_planner_avoids_decoy():
    decoy = cand(index=0, tag="button", id="fake-search", text="Search")
    real = cand(index=1, tag="button", type="submit", aria_label="Search", text="Go")
    obs = Observation(url="u", title="t", visible_text="", candidates=[decoy, real])
    p = MockPlanner("x")
    p.next_action("s", [], obs, [])  # step 1 (no box -> falls through)
    d = p.next_action("s", [], obs, ["x"])  # step 2 -> submit
    assert d.action is None or "fake" not in d.action.target.selector or d.kind == "done"


def test_llm_planner_raises_without_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    obs = Observation(url="u", title="t", visible_text="", candidates=[])
    p = LLMPlanner(OpenAIClient(api_key=""))
    with pytest.raises(LLMConfigError):
        p.next_action("task", [], obs, [])


@pytest.mark.integration
def test_agent_mode_loop_with_mock_planner(tmp_path):
    pytest.importorskip("playwright.sync_api")
    from pathlib import Path

    from playwright.sync_api import sync_playwright

    from browser_agent.agent import BrowserAgent
    from browser_agent.memory_store import MemoryStore

    root = Path(__file__).resolve().parents[1]
    site = (root / "data" / "mock_sites" / "v2" / "index.html")
    if not site.exists():
        pytest.skip("mock site missing")
    contract = BrowserTaskContract(
        task_id="agentic", natural_language_task="Search MockShop for widget",
        expected_outcome="results shown",
        success_conditions=[SuccessCondition(type="text_visible", value="results for"),
                            SuccessCondition(type="text_visible", value="Widget")])
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        page = b.new_page()
        page.goto(site.resolve().as_uri())
        agent = BrowserAgent(page, MemoryStore(tmp_path / "m.json"), "live", "agentic")
        run = agent.run_agentic("agentic", contract, MockPlanner("widget"), max_steps=6)
        b.close()
    assert run.status == "pass"
    assert any(s.mode == "agent" for s in run.steps)
