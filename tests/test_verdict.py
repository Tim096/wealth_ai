"""The three-state rule is the platform's core anti-silent-failure defence:
lack of evidence must never upgrade to pass."""

from eval_core import ConditionCheck, combine_checks


def check(condition: str, observed: str, required: bool = True) -> ConditionCheck:
    return ConditionCheck(condition=condition, required=required, observed=observed)


def test_all_observed_pass():
    result = combine_checks([check("url_contains:results", "pass"), check("text_visible:Done", "pass")])
    assert result.status == "pass"
    assert result.missing_evidence == []


def test_any_violation_is_fail():
    result = combine_checks([check("url_contains:results", "pass"), check("captcha_visible", "fail", required=False)])
    assert result.status == "fail"
    assert "captcha_visible" in result.reason


def test_unobserved_condition_is_unknown_not_pass():
    result = combine_checks([check("url_contains:results", "pass"), check("download_exists:report.pdf", "unknown")])
    assert result.status == "unknown"
    assert result.missing_evidence == ["download_exists:report.pdf"]


def test_fail_beats_unknown():
    result = combine_checks([check("a", "unknown"), check("b", "fail")])
    assert result.status == "fail"


def test_no_checks_is_unknown():
    result = combine_checks([])
    assert result.status == "unknown"
