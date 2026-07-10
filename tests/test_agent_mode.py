"""Agent Mode tests. The planner logic + action validation run without a
browser or a key; one integration test drives the real loop with MockPlanner.
"""

from pathlib import Path

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


def test_build_action_supports_download():
    obs = Observation(url="u", title="t", visible_text="", candidates=[cand(index=5)])
    act = _build_action({"action": "download", "aid": 5}, obs)
    assert act.type == "download" and act.target.selector == '[data-aid="5"]'


@pytest.mark.integration
@pytest.mark.parametrize("with_close_button", [False, True])
def test_dismiss_overlay_clears_classless_popup(tmp_path, with_close_button):
    # A real-world popup can appear on ANY site with ANY (or no) class name.
    # This overlay has NO telltale class/id/role — a class allow-list would
    # miss it — so it proves the geometry-based detector + neutraliser.
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    from browser_agent.agent import BrowserAgent, _OVERLAY_DETECT_JS
    from browser_agent.memory_store import MemoryStore

    close_btn = ('<button aria-label="Close" onclick="this.closest(\'div\').remove()" '
                 'style="position:absolute;top:0;right:0">x</button>') if with_close_button else ""
    html = (
        "<p>main page content</p>"
        "<div style='position:fixed;top:0;left:0;width:100%;height:100%;"
        "background:rgba(0,0,0,.6);z-index:9999'>"
        f"<div style='position:absolute;top:25%;left:25%;width:50%;height:50%;background:#fff'>"
        f"Subscribe to our newsletter!{close_btn}</div></div>"
    )
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(viewport={"width": 1200, "height": 800})
        page = ctx.new_page()
        page.set_content(html)
        agent = BrowserAgent(page, MemoryStore(tmp_path / "m.json"), "web", "agentic")
        before = bool(page.evaluate(_OVERLAY_DETECT_JS).get("present"))
        trace = []
        acted = agent._dismiss_overlay(trace)
        after = bool(page.evaluate(_OVERLAY_DETECT_JS).get("present"))
        b.close()
    assert before is True          # the overlay was blocking
    assert acted is True           # we detected and acted on it
    assert after is False          # ...and it is no longer blocking the centre


@pytest.mark.integration
def test_agent_downloads_a_real_file(tmp_path):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    from browser_agent.executor import ActionExecutor
    from browser_core import ElementTarget
    from browser_core.actions import DownloadAction

    html = ('<a id="d" href="data:text/csv,name,val%0Aa,1%0Ab,2" '
            'download="report.csv">Download</a>')
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(accept_downloads=True)
        page = ctx.new_page()
        page.set_content(html)
        ex = ActionExecutor(page, downloads_dir=tmp_path)
        out = ex.execute(DownloadAction(target=ElementTarget(selector="#d", selector_type="css")))
        b.close()
    assert out.ok
    saved = tmp_path / "report.csv"
    assert saved.exists()
    assert "name,val" in saved.read_text()


@pytest.mark.integration
def test_download_falls_back_to_saving_inline_document(tmp_path):
    # An SEC .htm renders inline (no download event). The fallback must still
    # save the linked file's bytes so "download it" doesn't dead-end.
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    from browser_agent.executor import ActionExecutor
    from browser_core import ElementTarget
    from browser_core.actions import DownloadAction

    # a normal link (NO download attr) → clicking it navigates, never downloads
    html = '<a id="d" href="data:text/html,<h1>Risk Factors</h1>">open doc</a>'
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context()
        page = ctx.new_page()
        page.set_content(html)
        ex = ActionExecutor(page, downloads_dir=tmp_path)
        out = ex.execute(DownloadAction(target=ElementTarget(selector="#d", selector_type="css")))
        b.close()
    assert out.ok
    assert ex.last_download_path and Path(ex.last_download_path).exists()
    assert "Risk Factors" in Path(ex.last_download_path).read_text(encoding="utf-8", errors="replace")


def test_build_action_rejects_codey_output():
    obs = Observation(url="u", title="t", visible_text="", candidates=[])
    # no aid + not goto -> unusable, planner should give_up on this
    assert _build_action({"action": "click", "aid": None}, obs) is None


class _FakeClient:
    def __init__(self, payload):
        self._payload = payload
    def available(self):
        return True
    def complete_json(self, system, user):
        return self._payload, None


def test_preflight_parses_and_validates():
    p = LLMPlanner(_FakeClient({
        "start_url": "https://finlab.tw",
        "success_conditions": [
            {"type": "text_visible", "value": "訂閱方案"},
            {"type": "url_contains", "value": "/pricing"},
            {"type": "bogus", "value": "x"},          # dropped: bad type
            {"type": "text_visible", "value": ""},      # dropped: empty value
        ],
    }))
    url, conds = p.plan_preflight("看 finlab 訂閱價格")
    assert url == "https://finlab.tw"
    assert conds == ["text_visible:訂閱方案", "url_contains:/pricing"]


def test_preflight_drops_non_http_start_url():
    p = LLMPlanner(_FakeClient({"start_url": "javascript:alert(1)",
                                "success_conditions": [{"type": "download_exists", "value": ""}]}))
    url, conds = p.plan_preflight("下載檔案")
    assert url == "" and conds == ["download_exists:"]


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
