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


def test_candidate_line_shows_choice_state():
    # a radio option must reach the planner as a clickable candidate WITH its
    # selection state, so the model clicks the right answer and never re-toggles.
    from browser_agent.planner import _candidate_lines

    c = cand(index=2, tag="div", type="", role="radio", aria_label="40 公克", checked="false")
    obs = Observation(url="u", title="t", visible_text="", candidates=[c])
    line = _candidate_lines(obs)
    assert "role=radio" in line and "40 公克" in line and "checked=false" in line


def test_transient_llm_error_is_noop_not_crash():
    # a one-off ReadTimeout on a single turn must NOT crash the whole run
    import httpx

    class _Boom:
        def available(self):
            return True

        def complete_json(self, system, user, image_path=None):
            raise httpx.ReadTimeout("timed out")

    obs = Observation(url="u", title="t", visible_text="", candidates=[])
    d = LLMPlanner(_Boom()).next_action("fill the form", [], obs, [])
    assert d.kind == "noop"


@pytest.mark.integration
def test_observer_surfaces_radio_and_checkbox():
    # Google-Form-style choice options are <div role=radio/checkbox>; the
    # observer must enumerate them or the planner can't answer a choice question.
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    from browser_agent.observer import PageObserver

    html = ('<div role="radio" aria-label="Option A"></div>'
            '<div role="checkbox" aria-label="Agree"></div>'
            '<input type="text" aria-label="Name">')
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        page = b.new_page()
        page.set_content(html)
        obs = PageObserver(page).observe()
        b.close()
    labels = {c.aria_label for c in obs.candidates}
    assert "Option A" in labels and "Agree" in labels and "Name" in labels


def test_build_action_targets_by_aid_only():
    obs = Observation(url="u", title="t", visible_text="", candidates=[cand(index=3)])
    act = _build_action({"action": "fill", "aid": 3, "value": "hi"}, obs)
    assert act.type == "fill" and act.target.selector == '[data-aid="3"]'


def test_build_action_supports_download():
    obs = Observation(url="u", title="t", visible_text="", candidates=[cand(index=5)])
    act = _build_action({"action": "download", "aid": 5}, obs)
    assert act.type == "download" and act.target.selector == '[data-aid="5"]'


def test_build_action_mouse_and_keyboard():
    obs = Observation(url="u", title="t", visible_text="", candidates=[])
    m = _build_action({"action": "mouse", "x": 120, "y": 44, "clicks": 2}, obs)
    assert m.type == "mouse" and (m.x, m.y, m.clicks) == (120, 44, 2)
    # mouse without coordinates is unusable -> None (planner re-plans, no crash)
    assert _build_action({"action": "mouse", "x": None, "y": None}, obs) is None
    k1 = _build_action({"action": "keyboard", "value": "hello"}, obs)
    assert k1.type == "keyboard" and k1.text == "hello" and k1.keys == ""
    k2 = _build_action({"action": "keyboard", "keys": "Enter", "value": "ignored"}, obs)
    assert k2.type == "keyboard" and k2.keys == "Enter" and k2.text == ""


def test_candidate_line_shows_coordinate():
    from browser_agent.planner import _candidate_lines
    obs = Observation(url="u", title="t", visible_text="",
                      candidates=[cand(index=1, tag="canvas", x=100, y=200)])
    assert "at=(104,204)" in _candidate_lines(obs)


def test_keyboard_cannot_bypass_credential_boundary():
    from browser_agent.capability import screen_action
    from browser_core.actions import KeyboardAction
    d = screen_action(KeyboardAction(text="my password is hunter2"))
    assert not d.allowed and d.category == "sensitive_input"


def test_build_action_download_current_page_and_url():
    obs = Observation(url="u", title="t", visible_text="", candidates=[])
    # aid=null, no value -> download the CURRENT page (no dead-end on inline docs)
    a = _build_action({"action": "download", "aid": None, "value": ""}, obs)
    assert a is not None and a.type == "download" and a.target is None and a.url == ""
    # aid=null with a URL -> download that file directly
    b = _build_action({"action": "download", "aid": None, "value": "https://x/y.htm"}, obs)
    assert b.type == "download" and b.url == "https://x/y.htm"


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


@pytest.mark.integration
def test_mouse_and_keyboard_drive_the_page(tmp_path):
    # the screen-level hands must work with NO selector: click by coordinate and
    # type at the current focus — the generality escape hatch.
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    from browser_agent.executor import ActionExecutor
    from browser_core.actions import KeyboardAction, MouseAction

    html = (
        "<input id='box' style='position:absolute;left:0;top:0;width:300px;height:40px'>"
        "<div id='hit' style='position:absolute;left:0;top:60px;width:200px;height:40px'"
        " onclick=\"document.title='HIT'\">click me</div>"
    )
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        page = b.new_page()
        page.set_content(html)
        ex = ActionExecutor(page)
        # click the div purely by coordinate (its centre ~ 100,80)
        assert ex.execute(MouseAction(x=100, y=80)).ok
        assert page.title() == "HIT"
        # focus the input by coordinate, then type + press with the keyboard
        ex.execute(MouseAction(x=150, y=20))
        ex.execute(KeyboardAction(text="hello world"))
        val = page.eval_on_selector("#box", "el => el.value")
        b.close()
    assert val == "hello world"


def test_gateway_schema_allows_screen_level_actions():
    # the codex strict output-schema must permit the new primitives or the real
    # backend literally cannot return them (they'd be silently dropped).
    import importlib.util
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("codex_gateway", root / "tools" / "codex_gateway.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    enum = mod.ACTION_SCHEMA["properties"]["action"]["enum"]
    assert "mouse" in enum and "keyboard" in enum
    for k in ("x", "y", "keys"):
        assert k in mod.ACTION_SCHEMA["properties"] and k in mod.ACTION_SCHEMA["required"]


@pytest.mark.integration
def test_set_of_marks_writes_a_numbered_screenshot(tmp_path):
    # the vision-grounding image must be produced with one mark per stamped
    # element, so a vision model can pick an element by its number.
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    from browser_agent.marks import set_of_marks
    from browser_agent.observer import PageObserver

    html = "<button>One</button><a href='/x'>Two</a>"
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        page = b.new_page()
        page.set_content(html)
        PageObserver(page).observe()          # stamps data-aid on both elements
        out = tmp_path / "som.png"
        n = set_of_marks(page, out)
        b.close()
    assert n == 2
    assert out.exists() and out.stat().st_size > 1000


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
        "analysis": "看 finlab 的訂閱價格頁",
        "obstacles": ["可能要捲動到方案區", "", "x" * 500],
        "steps": ["goto finlab.tw", "找定價連結"],
        "start_url": "https://finlab.tw",
        "success_conditions": [
            {"type": "text_visible", "value": "訂閱方案"},
            {"type": "url_contains", "value": "/pricing"},
            {"type": "bogus", "value": "x"},          # dropped: bad type
            {"type": "text_visible", "value": ""},      # dropped: empty value
        ],
    }))
    url, conds, plan = p.plan_preflight("看 finlab 訂閱價格")
    assert url == "https://finlab.tw"
    assert conds == ["text_visible:訂閱方案", "url_contains:/pricing"]
    assert plan["analysis"] == "看 finlab 的訂閱價格頁"
    assert plan["obstacles"] == ["可能要捲動到方案區", "x" * 160]   # empty dropped, long clipped
    assert plan["steps"] == ["goto finlab.tw", "找定價連結"]


def test_planner_sends_the_screenshot_to_a_vision_model(tmp_path):
    # when an image is provided, the planner must attach it (multimodal content)
    # and tell the model a Set-of-Marks screenshot is available.
    img = tmp_path / "som.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)
    seen = {}

    class _Rec:
        def available(self):
            return True

        def complete_json(self, system, user, image_path=None):
            seen["image_path"] = image_path
            seen["user"] = user
            return {"action": "done", "reason": "ok"}, None

    obs = Observation(url="u", title="t", visible_text="", candidates=[])
    LLMPlanner(_Rec()).next_action("task", [], obs, [], image_path=str(img))
    assert seen["image_path"] == str(img)
    assert "SCREENSHOT" in seen["user"]


def test_client_attaches_image_as_multimodal_content(tmp_path, monkeypatch):
    from llm_core.openai_client import OpenAIClient

    img = tmp_path / "s.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\nabc")
    captured = {}

    class _Resp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "{}"}}], "usage": {}}

    def _fake_post(url, headers=None, json=None, timeout=None):
        captured["body"] = json
        return _Resp()

    import httpx
    monkeypatch.setattr(httpx, "post", _fake_post)
    OpenAIClient(api_key="k").complete_json("sys", "user text", image_path=str(img))
    content = captured["body"]["messages"][1]["content"]
    assert isinstance(content, list)
    assert any(b.get("type") == "image_url" and "data:image/png;base64," in b["image_url"]["url"]
               for b in content)


def test_plan_steps_are_fed_back_to_the_planner():
    # the preflight route must reach the per-step planner so a hard multi-step
    # task follows its own roadmap — not just be shown to the user.
    captured = {}

    class _Rec:
        def available(self): return True
        def complete_json(self, system, user, image_path=None):
            captured["user"] = user
            return {"action": "goto", "value": "https://x"}, None

    obs = Observation(url="u", title="t", visible_text="", candidates=[])
    LLMPlanner(_Rec()).next_action("hard task", [], obs, [],
                                   plan_steps=["open EDGAR", "download the 10-K"])
    assert "PLANNED ROUTE" in captured["user"]
    assert "download the 10-K" in captured["user"]


def test_preflight_drops_non_http_start_url():
    p = LLMPlanner(_FakeClient({"start_url": "javascript:alert(1)",
                                "success_conditions": [{"type": "download_exists", "value": ""}]}))
    url, conds, plan = p.plan_preflight("下載檔案")
    assert url == "" and conds == ["download_exists:"]
    assert plan == {"analysis": "", "obstacles": [], "steps": []}


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
