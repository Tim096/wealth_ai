"""P1: structurally kill the premature-landmark false PASS.

真實 failure(使用者親測):任務「找到 intc 10-k 的財報 找到裡面的最新的營收數字給我」
→ preflight 給 success 條件 text_visible:intc → agent 只是開了 EDGAR 搜尋頁,
頁面就含 "intc"(任務句自帶 token,任何搜尋/結果頁都為真)→ 條件命中 → PASS conf 高。
一步實質工作都沒做,verdict 卻是 pass。

兩層 code-enforced 防禦(本檔逐層驗證):
  (A) baseline-subtraction(verifier.subtract_baseline,agent 兜底):t0(開場頁
      載入後、任何動作前)就已滿足的條件是 vacuous —— 它不可能構成「任務完成」的
      證據 —— 剔除並寫進 trace;剔除後無條件剩餘 → 走既有 open-ended 路徑,誠實
      unknown,絕不 vacuous pass。
  (B) task-echo guard(planner.plan_preflight,源頭減量):text_visible 的 value
      若(正規化後)是任務句子字串且短(≤3 詞),直接不採用。
(B) 擋不住「條件合法但恰好開場為真」,所以 (A) 必須存在;(A) 不減少 preflight
垃圾條件,所以 (B) 也要。
"""

import pytest

from browser_core import BrowserTaskContract, SuccessCondition
from browser_agent.observer import Observation
from browser_agent.planner import LLMPlanner, _task_echo
from browser_agent.verifier import subtract_baseline, verify_contract

# The task the user actually typed was Chinese:
#   "找到 intc 10-k 的財報 找到裡面的最新的營收數字給我"
# Since 2026-07-16 the capability guard refuses task text it cannot screen, so
# the verbatim original now stops at `refused` and never reaches the verifier.
# This file locks baseline-subtraction, not the guard: keep the property that
# made the bug bite — the task text carries the "intc" token that any EDGAR
# page also shows — and carry it in a language that still runs.
INTC_TASK = "Find the intc 10-k filing and give me the latest revenue figure in it"


def obs(text="", url="https://example.com/"):
    return Observation(url=url, title="t", visible_text=text, candidates=[])


def contract(*conds):
    return BrowserTaskContract(
        task_id="t", natural_language_task=INTC_TASK,
        expected_outcome="最新營收數字",
        success_conditions=[SuccessCondition(type=t, value=v) for t, v in conds])


# ---------- (A) baseline-subtraction: unit ----------

def test_t0_true_condition_is_subtracted_and_reported():
    # INTC 案例核心:text_visible:intc 在 t0(EDGAR 搜尋頁)已成立 → vacuous,剔除;
    # 尚未成立的真 deliverable 條件保留。
    c = contract(("text_visible", "intc"), ("text_visible", "Total revenue"))
    t0 = obs("EDGAR full-text search — showing filings for intc")
    filtered, dropped = subtract_baseline(c, t0)
    assert dropped == ["text_visible:intc"]
    assert [x.value for x in filtered.success_conditions] == ["Total revenue"]


def test_all_conditions_t0_true_leads_to_unknown_not_pass():
    """前後對照:修復前 verify_contract 對 text_visible:intc 在任何含 'intc' 的
    頁面都 PASS(vacuous)。修復後:t0 已成立 → 全數剔除 → 空條件走 open-ended
    gate → 誠實 unknown。"""
    c = contract(("text_visible", "intc"))
    filtered, dropped = subtract_baseline(c, obs("search results for intc"))
    assert dropped == ["text_visible:intc"]
    v = verify_contract(filtered, obs("intc still visible later"), {})
    assert v.status == "unknown"
    assert "open-ended" in v.reason


def test_t0_false_then_true_still_passes():
    # 正常路徑不受影響:條件開場不成立 → 保留;之後成立 → 正常 pass。
    c = contract(("text_visible", "Total revenue"))
    filtered, dropped = subtract_baseline(c, obs("EDGAR search page"))
    assert dropped == [] and filtered is c
    v = verify_contract(filtered, obs("Total revenue was $53.1 billion"), {})
    assert v.status == "pass"


def test_url_contains_true_at_start_url_is_vacuous_too():
    # premature landmark 不限 text_visible:start_url 本身就含 fragment 的
    # url_contains 同樣在 t0 為真 → 同樣剔除。
    c = contract(("url_contains", "sec.gov"))
    filtered, dropped = subtract_baseline(c, obs("", url="https://www.sec.gov/cgi-bin/browse-edgar"))
    assert dropped == ["url_contains:sec.gov"]
    assert filtered.success_conditions == []


def test_download_exists_survives_baseline():
    # t0 沒有任何下載 → download_exists 是 unknown 而非 pass → 絕不能被誤剔除。
    c = contract(("download_exists", "Risk Factors"))
    filtered, dropped = subtract_baseline(c, obs("anything at all"))
    assert dropped == [] and filtered is c


# ---------- (B) task-echo guard: unit ----------

class _FakeClient:
    def __init__(self, payload):
        self._payload = payload

    def available(self):
        return True

    def complete_json(self, system, user):
        return self._payload, None


def test_preflight_drops_short_task_echo_text_visible():
    # INTC 案例源頭:preflight 想用 text_visible:intc(任務句自帶 token)→ 不採用。
    # "10-K" 同理(大小寫/空白正規化後仍是任務子字串)。
    p = LLMPlanner(_FakeClient({
        "start_url": "https://www.sec.gov/cgi-bin/browse-edgar?CIK=INTC&type=10-K",
        "success_conditions": [
            {"type": "text_visible", "value": "intc"},
            {"type": "text_visible", "value": "10-K"},
            {"type": "download_exists", "value": "Risk Factors"},
        ]}))
    url, conds, plan = p.plan_preflight(INTC_TASK)
    assert conds == ["download_exists:Risk Factors"]


def test_preflight_keeps_non_echo_conditions():
    # 不是任務句子字串的 deliverable 條件照常採用;guard 只管 text_visible。
    p = LLMPlanner(_FakeClient({
        "start_url": "https://www.sec.gov",
        "success_conditions": [
            {"type": "text_visible", "value": "Total revenue"},   # 不在任務句 → 留
            {"type": "url_contains", "value": "intc"},            # 非 text_visible → 留
        ]}))
    url, conds, plan = p.plan_preflight(INTC_TASK)
    assert conds == ["text_visible:Total revenue", "url_contains:intc"]


def test_task_echo_boundary():
    assert _task_echo("intc", INTC_TASK)                       # 1 詞、子字串 → echo
    assert _task_echo("INTC 10-K", "find intc 10-k report")    # 正規化後子字串 → echo
    assert not _task_echo("Total revenue", INTC_TASK)          # 非子字串 → 留
    assert not _task_echo("net revenue was reported in the filing",
                          "net revenue was reported in the filing 找出來")  # >3 詞 → 留
    assert not _task_echo("", INTC_TASK)                       # 空值不算


# ---------- 端到端:mock 頁開場就含 needle ----------

@pytest.mark.integration
def test_needle_visible_at_open_yields_unknown_not_pass(tmp_path):
    """INTC 案例最小重現(端到端前後對照)。修復前:開場頁就含 needle 'intc',
    run_agentic 迴圈第一次 verify 即 PASS —— agent 一步實質工作都沒做。修復後:
    t0 已成立的條件被 baseline-subtraction 剔除(trace 有 step='baseline' 讓人
    看得到)→ 無有效條件 → run 照跑並以誠實 unknown 收場。"""
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    from browser_agent.agent import BrowserAgent
    from browser_agent.memory_store import MemoryStore
    from browser_agent.planner import MockPlanner

    c = BrowserTaskContract(
        task_id="intc", natural_language_task=INTC_TASK,
        expected_outcome="最新營收數字",
        success_conditions=[SuccessCondition(type="text_visible", value="intc")])
    html = ("<h1>EDGAR full-text search</h1><p>results for intc</p>"
            "<form><input name='query' aria-label='Search'>"
            "<button type='submit'>Search</button></form>")
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        page = b.new_page()
        page.set_content(html)
        agent = BrowserAgent(page, MemoryStore(tmp_path / "m.json"), "live", "agentic")
        run = agent.run_agentic("intc", c, MockPlanner("intc"), max_steps=4)
        b.close()
    assert run.status == "unknown"          # 不是 pass:vacuous 條件撐不起 verdict
    baseline = [s for s in run.steps if s.step == "baseline"]
    assert baseline and "text_visible:intc" in baseline[0].detail   # 剔除事件在 trace
