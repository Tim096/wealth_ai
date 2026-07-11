"""P3: 自主性升級 — 卡住自動開視覺 + scroll playbook + 新分頁跟隨.

三個真實弱點(docs/usage_scenarios.md):
  · 卡住時無視覺升級(INTC failure 第三根因):vision 通道已 wired 但只有
    AGENT_VISION=1 選配 —— 框架幫不上時 agent 不會自己「看螢幕」。
  · #10 捲動:action schema 沒教 PageDown/End,模型不會想到往下捲。
  · #11 新分頁:target=_blank click 後 observe 的還是舊頁 → planner 看到
    「點了沒變化」→ 重試 → give_up,自述與事實不一致。

修復(本檔逐層驗證):
  (1) vision_escalation_reason(agent.py)——可測純函式:連續 N 步無進展
      (fail/noop/give_up_rejected)或頁面 hash 未變 ≥N 步 → 回理由字串;
      run_agentic 在 planner 支援 vision(supports_vision)+ 有 artifact_dir
      時自動切入 SoM 視覺模式,trace 記 step='vision'。AGENT_VISION=0 全關;
      mock/scripted planner 無 supports_vision → 永不升級(離線 eval 不變)。
      鐵律不破:vision 只是感知通道,action 仍走 schema,verifier 唯一裁判。
  (2) PLAYBOOK 教 keyboard keys="PageDown"/"End" 捲動(純 prompt,F11/#10)。
  (3) executor click/mouse 後檢查 context.pages,有新頁切換 self.page 至最新
      (ActionOutcome.followed_url),agent/observer 同步跟上,trace 記
      「↪ 跟隨新分頁」(F12/#11)。
"""

from pathlib import Path

import pytest

from browser_core import BrowserTaskContract, ElementTarget, SuccessCondition
from browser_core.actions import ClickAction
from browser_agent.agent import vision_escalation_reason
from browser_agent.planner import LLMPlanner, PlannerDecision


# ---------- (1) escalation 條件:純函式 ----------

def test_no_history_no_escalation():
    assert vision_escalation_reason([], []) == ""


def test_three_failed_actions_escalate():
    assert vision_escalation_reason(["click:fail", "click:fail", "press:fail"], [])


def test_mixed_no_progress_entries_escalate():
    # noop(換策略無效)、被駁回的 give_up、失敗的 action 都算無進展
    h = ["noop(model returned an unusable action)", "give_up_rejected(stuck)", "click:fail"]
    assert vision_escalation_reason(h, [])


def test_any_progress_in_window_blocks_escalation():
    assert vision_escalation_reason(["click:fail", "goto:ok", "click:fail"], []) == ""


def test_older_failures_outside_window_do_not_count():
    h = ["click:fail", "click:fail", "click:fail", "goto:ok"]
    assert vision_escalation_reason(h, []) == ""


def test_static_page_hash_escalates():
    assert vision_escalation_reason([], ["h1", "h1", "h1", "h1"])


def test_changing_page_hash_does_not_escalate():
    assert vision_escalation_reason([], ["h1", "h1", "h1", "h2"]) == ""


def test_too_few_hashes_do_not_escalate():
    assert vision_escalation_reason([], ["h1", "h1", "h1"]) == ""


# ---------- (1) planner 端:誰支援 vision ----------

def test_llm_planner_declares_vision_support():
    class _C:
        def available(self):
            return True
    assert LLMPlanner(_C()).supports_vision() is True


def test_mock_and_scripted_planners_do_not_declare_vision():
    # 無 supports_vision 屬性 → agent 的 getattr default 不升級(離線 eval 不變)
    from browser_agent.planner import MockPlanner
    assert not hasattr(MockPlanner("q"), "supports_vision")


# ---------- (2) scroll playbook:純 prompt ----------

def test_playbook_teaches_scrolling():
    from browser_agent.planner import _SYSTEM
    assert "PageDown" in _SYSTEM and '"End"' in _SYSTEM


# ---------- 測試用 planner ----------

class StuckPlanner:
    """連續 noop(模擬換策略無效)再 give_up;記錄每回合收到的 image_path,
    用來驗證「升級前無圖、升級後有圖」。本類刻意「無」supports_vision ——
    等同 mock/scripted planner(文字-only backend)。"""

    def __init__(self, noops: int = 3) -> None:
        self._noops = noops
        self.images: list = []

    def available(self) -> bool:
        return True

    def next_action(self, task, success_conditions, obs, history,
                    plan_steps=None, image_path=None) -> PlannerDecision:
        self.images.append(image_path)
        if len(self.images) <= self._noops:
            return PlannerDecision(kind="noop", reason="stuck")
        return PlannerDecision(kind="give_up", reason="stop")


class VisionStuckPlanner(StuckPlanner):
    """同上,但宣告支援 vision(等同 LLMPlanner 的多模態通道)。"""

    def supports_vision(self) -> bool:
        return True


def _contract(needle: str) -> BrowserTaskContract:
    return BrowserTaskContract(
        task_id="t", natural_language_task="integration task",
        expected_outcome="landmark visible",
        success_conditions=[SuccessCondition(type="text_visible", value=needle)])


# ---------- (1) 端到端:卡住 → 自動切視覺 ----------

@pytest.mark.integration
def test_stuck_run_auto_escalates_to_vision(tmp_path, monkeypatch):
    """前後對照:升級前(前 3 回合)planner 收到 image_path=None;第 3 步無進展
    後 escalation 觸發 → 第 4 回合起收到 SoM 截圖路徑,trace 記 step='vision'。"""
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    from browser_agent.agent import BrowserAgent
    from browser_agent.memory_store import MemoryStore

    monkeypatch.delenv("AGENT_VISION", raising=False)   # default = auto
    planner = VisionStuckPlanner()
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        page = b.new_page()
        page.set_content("<button>go</button><p>hello</p>")
        agent = BrowserAgent(page, MemoryStore(tmp_path / "m.json"), "web", "agentic",
                             artifact_dir=tmp_path / "art")
        run = agent.run_agentic("v", _contract("NEVER-THERE"), planner, max_steps=6)
        b.close()
    assert planner.images[:3] == [None, None, None]     # 文字通道先行
    assert planner.images[3] and Path(planner.images[3]).exists()  # 升級後有圖
    vis = [s for s in run.steps if s.step == "vision"]
    assert len(vis) == 1 and "視覺" in vis[0].detail
    assert run.status != "pass"                          # verifier 仍唯一裁判


@pytest.mark.integration
def test_planner_without_vision_support_never_escalates(tmp_path, monkeypatch):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    from browser_agent.agent import BrowserAgent
    from browser_agent.memory_store import MemoryStore

    monkeypatch.delenv("AGENT_VISION", raising=False)
    planner = StuckPlanner()                            # 無 supports_vision
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        page = b.new_page()
        page.set_content("<button>go</button>")
        agent = BrowserAgent(page, MemoryStore(tmp_path / "m.json"), "web", "agentic",
                             artifact_dir=tmp_path / "art")
        run = agent.run_agentic("nv", _contract("NEVER-THERE"), planner, max_steps=6)
        b.close()
    assert all(i is None for i in planner.images)
    assert not any(s.step == "vision" for s in run.steps)


@pytest.mark.integration
def test_agent_vision_0_disables_auto_escalation(tmp_path, monkeypatch):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    from browser_agent.agent import BrowserAgent
    from browser_agent.memory_store import MemoryStore

    monkeypatch.setenv("AGENT_VISION", "0")             # operator: text-only backend
    planner = VisionStuckPlanner()
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        page = b.new_page()
        page.set_content("<button>go</button>")
        agent = BrowserAgent(page, MemoryStore(tmp_path / "m.json"), "web", "agentic",
                             artifact_dir=tmp_path / "art")
        run = agent.run_agentic("v0", _contract("NEVER-THERE"), planner, max_steps=6)
        b.close()
    assert all(i is None for i in planner.images)
    assert not any(s.step == "vision" for s in run.steps)


# ---------- (3) 新分頁跟隨 ----------

class ClickThenDonePlanner:
    def __init__(self, selector: str) -> None:
        self._selector = selector
        self._clicked = False

    def available(self) -> bool:
        return True

    def next_action(self, task, success_conditions, obs, history,
                    plan_steps=None, image_path=None) -> PlannerDecision:
        if not self._clicked:
            self._clicked = True
            t = ElementTarget(selector=self._selector, selector_type="css")
            return PlannerDecision(kind="action", action=ClickAction(target=t),
                                   reason="open the external article")
        return PlannerDecision(kind="done", reason="article opened")


def _two_tab_site(tmp_path) -> str:
    target = tmp_path / "article.html"
    target.write_text("<h1>NEWTAB-LANDMARK</h1><p>article body</p>", encoding="utf-8")
    main = tmp_path / "main.html"
    main.write_text(f'<a id="ext" target="_blank" href="{target.as_uri()}">read more</a>',
                    encoding="utf-8")
    return main.as_uri()


@pytest.mark.integration
def test_executor_follows_target_blank_click(tmp_path):
    """前後對照:修復前 click 後 executor.page 停在舊分頁(observe 看不到新內容,
    planner 判「點了沒效果」);修復後 execute 回報 followed_url 並切到新分頁。"""
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    from browser_agent.executor import ActionExecutor

    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context()
        page = ctx.new_page()
        page.goto(_two_tab_site(tmp_path))
        ex = ActionExecutor(page)
        out = ex.execute(ClickAction(target=ElementTarget(selector="#ext", selector_type="css")))
        followed_page_url = ex.page.url
        b.close()
    assert out.ok
    assert out.followed_url.endswith("article.html")
    assert followed_page_url.endswith("article.html")


@pytest.mark.integration
def test_agent_follows_new_tab_and_verifies_there(tmp_path):
    """端到端:成功條件的 landmark 只存在新分頁上。修復前:observe 停留舊頁 →
    永遠看不到 landmark → fail/give_up;修復後:click 後跟隨新分頁,verifier 在
    新分頁看到 landmark → pass,trace 記「↪ 跟隨新分頁」。"""
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    from browser_agent.agent import BrowserAgent
    from browser_agent.memory_store import MemoryStore

    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context()
        page = ctx.new_page()
        page.goto(_two_tab_site(tmp_path))
        agent = BrowserAgent(page, MemoryStore(tmp_path / "m.json"), "web", "agentic")
        run = agent.run_agentic("tab", _contract("NEWTAB-LANDMARK"),
                                ClickThenDonePlanner("#ext"), max_steps=4)
        b.close()
    assert run.status == "pass"
    follows = [s for s in run.steps if s.step == "follow_tab"]
    assert len(follows) == 1 and "跟隨新分頁" in follows[0].detail
