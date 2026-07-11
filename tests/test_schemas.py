import pytest
from pydantic import TypeAdapter, ValidationError

from browser_core import BrowserAction, BrowserTaskContract, FAILURE_TAXONOMY
from sec_core import AdjudicatorDecision, ConfidenceBreakdown
from sec_core.confidence import ConfidenceComponent


def test_browser_action_rejects_arbitrary_code():
    adapter = TypeAdapter(BrowserAction)
    with pytest.raises(ValidationError):
        adapter.validate_python({"type": "evaluate", "script": "window.close()"})


def test_browser_action_accepts_controlled_click():
    adapter = TypeAdapter(BrowserAction)
    action = adapter.validate_python(
        {"type": "click", "target": {"selector": "#search-btn", "selector_type": "css"}}
    )
    assert action.type == "click"


def test_contract_allows_zero_success_conditions_for_open_ended_tasks():
    """FIX-1 前後對照。修復前:success_conditions 有 min_length=1,LLM preflight
    誠實回報「開放式任務、無可驗證條件」(空陣列)時,建 contract 直接
    ValidationError,整個 run 變 ERROR(實例:「搜尋 33 號遠征隊的歌曲 並 播放」)
    —— schema 把誠實路徑當非法輸入,等於懲罰誠實。修復後:空條件是合法的
    開放式 contract;verifier 對它回 unknown,絕不 vacuous pass(見
    test_browser_agent.py 的 open_ended 測試)。"""
    c = BrowserTaskContract(
        task_id="t1",
        natural_language_task="搜尋 33 號遠征隊的歌曲 並 播放",
        expected_outcome="open-ended: no machine-checkable outcome",
        success_conditions=[],
    )
    assert c.success_conditions == []


def test_failure_taxonomy_covers_spec_types():
    assert set(FAILURE_TAXONOMY) == {
        "selector_not_found",
        "multiple_candidates",
        "click_no_effect",
        "modal_blocking",
        "wrong_page",
        "timeout",
        "form_validation_error",
        "empty_result",
        "download_missing",
        "silent_failure_risk",
    }
    assert FAILURE_TAXONOMY["silent_failure_risk"].repairable is False


def test_adjudicator_confident_decision_requires_quote():
    with pytest.raises(ValidationError):
        AdjudicatorDecision(decision="candidate_a", confidence=0.9, evidence_quote="", reason="looks right")


def test_adjudicator_unknown_needs_no_quote():
    d = AdjudicatorDecision(decision="unknown", confidence=0.0, evidence_quote="", reason="both candidates weak")
    assert d.decision == "unknown"


def test_confidence_total_is_normalized_and_explainable():
    breakdown = ConfidenceBreakdown(
        components=[
            ConfidenceComponent(name="heading_strength", score=2.0, max_score=2.0, reason="strict regex hit"),
            ConfidenceComponent(name="toc_disambiguation", score=0.0, max_score=1.0, reason="candidate near TOC zone"),
        ]
    )
    assert breakdown.total == pytest.approx(2.0 / 3.0)
