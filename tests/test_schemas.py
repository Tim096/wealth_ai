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


def test_contract_requires_at_least_one_success_condition():
    with pytest.raises(ValidationError):
        BrowserTaskContract(
            task_id="t1",
            natural_language_task="do nothing",
            expected_outcome="nothing",
            success_conditions=[],
        )


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
