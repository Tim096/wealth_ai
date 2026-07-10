"""XBRL cross-validation oracle — offline unit tests (no network).
The number-scale matching and verdict logic are what make status certifiable
against SEC's structured facts instead of the pipeline's own say-so.
"""

from sec_core.xbrl import _scale_strings, key_facts_for_accession, validate_span


def test_scale_strings_covers_ones_thousands_millions():
    s = _scale_strings(391_035_000_000)
    assert "391,035" in s          # reported in millions
    assert "391,035,000" in s      # reported in thousands
    assert "391,035,000,000" in s  # reported in ones


def test_certified_when_two_or_more_figures_present():
    facts = {"revenue": 391_035_000_000, "net_income": 93_736_000_000, "total_assets": 364_980_000_000}
    span = "Total net sales 391,035 ... Net income 93,736 ... Total assets 364,980 ..."
    chk = validate_span(span, facts)
    assert chk.verdict == "certified"
    assert all(chk.corroborated.values())


def test_contradicted_when_no_figure_present():
    facts = {"revenue": 391_035_000_000, "net_income": 93_736_000_000, "total_assets": 364_980_000_000}
    span = "Reference is made to the Financial Section of this report."
    chk = validate_span(span, facts)
    assert chk.verdict == "contradicted"
    assert not any(chk.corroborated.values())


def test_unavailable_when_no_facts():
    chk = validate_span("anything", {})
    assert chk.verdict == "unavailable"
    assert chk.available is False


def test_key_facts_matched_by_accession():
    facts = {
        "facts": {"us-gaap": {
            "Revenues": {"units": {"USD": [
                {"accn": "0000320193-25-000079", "form": "10-K", "val": 416_161_000_000},
                {"accn": "9999999999-99-999999", "form": "10-K", "val": 1},
            ]}},
            "NetIncomeLoss": {"units": {"USD": [
                {"accn": "0000320193-25-000079", "form": "10-K", "val": 112_010_000_000},
            ]}},
        }}
    }
    out = key_facts_for_accession(facts, "0000320193-25-000079")
    assert out["revenue"] == 416_161_000_000
    assert out["net_income"] == 112_010_000_000
