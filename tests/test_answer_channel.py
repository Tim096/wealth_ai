"""P2: answer channel — 答案型任務的交付通道 + answer_matches 條件.

真實 failure(使用者親測,承接 P1):任務「找到 intc 10-k 的財報 找到裡面的最新的
營收數字給我」是答案型任務,但系統沒有交付通道 —— extract_text 的結果被丟棄
(run_agentic 的 extracted 只放 __download__),沒有任何條件型能對「答案」下判斷,
verdict 只能靠 landmark(而 landmark 被 premature-landmark 打穿,見 P1)。

修復(本檔逐層驗證):
  (1) 通道:extract_text 成功結果 append 進 extracted['answer'],run 結束存進
      TaskRun.answer(UI rec 同名欄位)。
  (2) 判準:新 SuccessCondition type 'answer_matches'(value=regex)——有 answer
      且 match → pass;有 answer 不 match → fail;沒 answer → fail(沒做交付
      動作就是沒完成)。answer 來自 extract action 對真實頁面的擷取,不是 LLM
      的自述 —— 「verifier 不吃 agent 自述」的延伸。
  (3) 源頭:preflight 接受 answer_matches(regex 驗證後才採用)。
離線 eval:tools/answer_channel_eval.py(fixture: data/mock_sites/answer/)。
"""

import pytest

from browser_core import BrowserTaskContract, SuccessCondition
from browser_agent.observer import Observation
from browser_agent.planner import LLMPlanner
from browser_agent.verifier import subtract_baseline, verify_contract
from browser_agent.agent import is_meaningful_answer

ANSWER_RE = r"[\$][0-9][0-9,\.]+\s*(billion|million)?"


def obs(text="", url="https://example.com/"):
    return Observation(url=url, title="t", visible_text=text, candidates=[])


def contract(pattern=ANSWER_RE):
    return BrowserTaskContract(
        task_id="t", natural_language_task="找出頁面上的營收數字",
        expected_outcome="營收數字",
        success_conditions=[SuccessCondition(type="answer_matches", value=pattern)])


# ---------- (2) verifier: answer_matches 三態 ----------

def test_answer_extracted_and_matching_passes():
    v = verify_contract(contract(), obs(), {"answer": "Total revenue: $53.1 billion"})
    assert v.status == "pass"


def test_answer_extracted_but_unmatched_fails():
    # 交付了東西,但不是要的形狀(抓錯元素)→ fail,不是 unknown
    v = verify_contract(contract(), obs(), {"answer": "Founded in 1998, 14 countries."})
    assert v.status == "fail"


def test_no_answer_fails_even_when_visible_on_page():
    """核心語義:答案「看得到」不等於「交付了」。頁面上明明有數字,但 agent
    沒做 extract(沒有交付動作)→ extracted 無 answer → fail。修復前這種 run
    靠 text_visible landmark 可以 PASS(INTC 假陽性);修復後答案型任務的
    verdict 綁在交付通道上。"""
    v = verify_contract(contract(), obs("Total revenue: $53.1 billion"), {})
    assert v.status == "fail"


def test_agent_claim_in_reason_is_not_an_answer():
    # LLM 自述(done 的 reason 含正確數字)沒有通道進 verifier —— extracted 才算
    v = verify_contract(contract(), obs(), {})
    assert v.status == "fail"


def test_malformed_regex_is_unknown_not_pass():
    v = verify_contract(contract("[unclosed"), obs(), {"answer": "$53.1 billion"})
    assert v.status == "unknown"


def test_answer_matches_survives_baseline_subtraction():
    # t0 沒有 answer → fail(不是 pass)→ 絕不會被 premature-landmark 剔除
    c = contract()
    filtered, dropped = subtract_baseline(c, obs("Total revenue: $53.1 billion everywhere"))
    assert dropped == [] and filtered is c


def test_navigation_residue_is_not_a_meaningful_answer():
    assert not is_meaningful_answer("Skip contents")
    assert not is_meaningful_answer("  SKIP TO MAIN CONTENT  ")
    assert is_meaningful_answer("Total revenue: $53.1 billion")


# ---------- (3) preflight: answer_matches 源頭 ----------

class _FakeClient:
    def __init__(self, payload):
        self._payload = payload

    def available(self):
        return True

    def complete_json(self, system, user):
        return self._payload, None


def test_preflight_accepts_answer_matches_and_drops_bad_regex():
    p = LLMPlanner(_FakeClient({
        "start_url": "https://www.sec.gov/cgi-bin/browse-edgar?CIK=INTC&type=10-K",
        "success_conditions": [
            {"type": "answer_matches", "value": ANSWER_RE},
            {"type": "answer_matches", "value": "[unclosed"},   # dropped: 不可編譯
        ]}))
    url, conds, plan = p.plan_preflight("找到 intc 10-k 的財報 找到裡面的最新的營收數字給我")
    assert conds == [f"answer_matches:{ANSWER_RE}"]


def test_preflight_prompt_teaches_answer_channel():
    from browser_agent.planner import _PREFLIGHT_SYSTEM, _SYSTEM
    assert "answer_matches" in _PREFLIGHT_SYSTEM
    assert "extract_text" in _SYSTEM and "ANSWER TASKS" in _SYSTEM


# ---------- (1) 通道端到端:extract → TaskRun.answer → verdict ----------

@pytest.mark.integration
def test_extract_delivers_answer_and_passes(tmp_path):
    """端到端前後對照。修復前:extract_text 結果被丟棄、extracted 只有
    __download__ → answer 型任務無從 pass(或靠 landmark 假 pass)。修復後:
    scripted planner 對 #revenue 做 extract_text → extracted['answer'] 進
    verifier → answer_matches pass,且 TaskRun.answer 把答案交回使用者。"""
    pytest.importorskip("playwright.sync_api")
    from pathlib import Path
    from playwright.sync_api import sync_playwright

    from browser_agent.agent import BrowserAgent
    from browser_agent.memory_store import MemoryStore

    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from tools.answer_channel_eval import ScriptedPlanner, build_contract, uri

    root = Path(__file__).resolve().parents[1]
    if not (root / "data" / "mock_sites" / "answer" / "index.html").exists():
        pytest.skip("answer fixture missing")
    task = {"task_id": "ans", "natural_language_task": "找出頁面上的營收數字",
            "success_conditions": [{"type": "answer_matches", "value": ANSWER_RE}]}
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        page = b.new_page()
        page.goto(uri("answer"))
        agent = BrowserAgent(page, MemoryStore(tmp_path / "m.json"), "answer", "answer")
        run = agent.run_agentic("ans", build_contract(task),
                                ScriptedPlanner([{"extract": "#revenue"}]), max_steps=4)
        b.close()
    assert run.status == "pass"
    assert "$53.1 billion" in run.answer          # 答案真的交到手上
    assert run.as_dict()["answer"] == run.answer  # UI rec 走同一欄位


@pytest.mark.integration
def test_done_without_extract_fails_despite_visible_answer(tmp_path):
    # 自述型 done(reason 含正確數字)且答案在頁面上可見 → 仍 fail:沒交付
    pytest.importorskip("playwright.sync_api")
    from pathlib import Path
    from playwright.sync_api import sync_playwright

    from browser_agent.agent import BrowserAgent
    from browser_agent.memory_store import MemoryStore

    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from tools.answer_channel_eval import ScriptedPlanner, build_contract, uri

    root = Path(__file__).resolve().parents[1]
    if not (root / "data" / "mock_sites" / "answer" / "index.html").exists():
        pytest.skip("answer fixture missing")
    task = {"task_id": "ans-claim", "natural_language_task": "找出頁面上的營收數字",
            "success_conditions": [{"type": "answer_matches", "value": ANSWER_RE}]}
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        page = b.new_page()
        page.goto(uri("answer"))
        agent = BrowserAgent(page, MemoryStore(tmp_path / "m.json"), "answer", "answer")
        run = agent.run_agentic("ans-claim", build_contract(task),
                                ScriptedPlanner([{"done": "revenue is $53.1 billion"}]),
                                max_steps=4)
        b.close()
    assert run.status == "fail"
    assert run.answer == ""


# ---------- calibration: answer_wrong 類全數被抓 ----------

def test_calibration_answer_cases():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from tools.calibrate_verifier import build_cases, calibrate

    result = calibrate(build_cases())
    rows = [r for r in result["per_case"] if r["corruption_class"] == "answer_wrong"]
    assert len(rows) >= 2
    assert all(r["verdict"] == "fail" for r in rows)     # 答案錯/沒答案 → 全 fail
    oks = [r for r in result["per_case"] if r["case_id"].startswith("cal-ok-answer-")]
    assert len(oks) >= 2
    assert all(r["verdict"] == "pass" for r in oks)      # 答案對 → pass
