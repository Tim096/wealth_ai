"""Per-item topic-consistency oracle — trustworthy status for every item,
not just Item 8. Independent lexical cross-check, no LLM."""

from sec_core.topic_check import check_topic


def test_risk_factors_body_is_consistent():
    body = ("Investing in our common stock involves risk. Supply chain disruption could "
            "materially and adversely affect our operating results and harm the business.")
    assert check_topic("1A", body).verdict == "consistent"


def test_mislabelled_span_is_inconsistent():
    # a span labelled Item 1A (Risk Factors) that is actually an exhibit list
    body = "Exhibit 21.1 Subsidiaries of the Registrant. Exhibit 23.1 Consent of Auditors."
    assert check_topic("1A", body).verdict == "inconsistent"


def test_boilerplate_none_is_recognised():
    for body in ["None.", "Not applicable.", "Reserved"]:
        assert check_topic("1B", body).verdict == "boilerplate"


def test_mda_body_is_consistent():
    body = ("Net revenue increased compared with the prior year. Liquidity remained strong "
            "and cash flows from operations were $980 million; results of operations improved.")
    assert check_topic("7", body).verdict == "consistent"


def test_financial_statements_body_is_consistent():
    body = ("Consolidated Balance Sheets. Consolidated Statements of Operations. Notes to "
            "Consolidated Financial Statements. Cash flows from operating activities.")
    assert check_topic("8", body).verdict == "consistent"


def test_empty_body_skipped():
    assert check_topic("7", "").verdict == "skipped"
