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


def test_certify_item8_gates_status_on_contradiction():
    """The load-bearing gate: a pass Item 8 that XBRL contradicts must flip to
    needs_review. Tests the gating logic with a fake fetcher (no network)."""
    from sec_core.items import ItemSegment
    from sec_core.xbrl import certify_item8

    seg = ItemSegment(filing_id="f", item_code="8", canonical_title="Financial Statements",
                      extracted_heading="Item 8.", start_offset=0, end_offset=50,
                      text_sha256="x", status="pass", confidence=0.9)

    class FakeResult:
        segments = [seg]
        def text_of(self, code):  # a wrapper stub with none of the figures
            return "Reference is made to the Financial Section of this report."

    facts_json = {"facts": {"us-gaap": {
        "Revenues": {"units": {"USD": [{"accn": "0000000000-00-000000", "form": "10-K", "val": 500_000_000_000}]}},
        "NetIncomeLoss": {"units": {"USD": [{"accn": "0000000000-00-000000", "form": "10-K", "val": 90_000_000_000}]}},
        "Assets": {"units": {"USD": [{"accn": "0000000000-00-000000", "form": "10-K", "val": 400_000_000_000}]}},
    }}}

    class FakeResp:
        content = __import__("json").dumps(facts_json).encode()

    class FakeFetcher:
        def get(self, url):
            return FakeResp()

    chk = certify_item8(FakeResult(), FakeFetcher(), cik=1, accession="0000000000-00-000000")
    assert chk.verdict == "contradicted"
    assert seg.status == "unsupported"   # a pass with no XBRL figures is demoted, not served
    assert seg.needs_review is True
    assert seg.xbrl_check.startswith("contradicted")
    assert any("XBRL oracle contradicts" in w for w in seg.warnings)


def test_certify_item8_demotes_contradicted_partial_to_unsupported():
    """A cross-reference-index Item 8 resolved to a `partial` span that XBRL
    contradicts (e.g. a polluted page map landed on the financials INDEX page,
    not the statements) must be demoted to `unsupported` — never served as a
    truncated partial that reads like content (INTC FY2019 regression)."""
    from sec_core.items import ItemSegment
    from sec_core.xbrl import certify_item8

    seg = ItemSegment(filing_id="f", item_code="8", canonical_title="Financial Statements",
                      extracted_heading="Item 8.", start_offset=0, end_offset=50,
                      text_sha256="x", status="partial", confidence=0.7,
                      provenance="resolved_from_page_anchor", needs_review=True)

    class FakeResult:
        segments = [seg]
        def text_of(self, code):  # the financials-index page, none of the figures
            return "Index to Consolidated Financial Statements ... see page 66."

    facts_json = {"facts": {"us-gaap": {
        "Revenues": {"units": {"USD": [{"accn": "0000000000-00-000000", "form": "10-K", "val": 71_965_000_000}]}},
        "NetIncomeLoss": {"units": {"USD": [{"accn": "0000000000-00-000000", "form": "10-K", "val": 21_048_000_000}]}},
        "Assets": {"units": {"USD": [{"accn": "0000000000-00-000000", "form": "10-K", "val": 136_524_000_000}]}},
    }}}

    class FakeResp:
        content = __import__("json").dumps(facts_json).encode()

    class FakeFetcher:
        def get(self, url):
            return FakeResp()

    chk = certify_item8(FakeResult(), FakeFetcher(), cik=1, accession="0000000000-00-000000")
    assert chk.verdict == "contradicted"
    assert seg.status == "unsupported"
    assert seg.needs_review is True


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


# ---------------------------------------------------------------------------
# Fact-identity mutation suite — synthetic, offline. Each fixture plants the
# correct current-period fact alongside a wrong-context decoy (prior year,
# quarter, wrong currency, restatement) and proves the identity selector locks
# onto the current-period fact so the wrong context is never the headline.
# ---------------------------------------------------------------------------

from sec_core.xbrl import identity_mismatch, select_current_period_facts  # noqa: E402

_ACCN = "0000000000-26-000001"


def _dur(val, *, start, end, fy=2026, fp="FY", accn=_ACCN, form="10-K"):
    return {"val": val, "accn": accn, "form": form, "fy": fy, "fp": fp, "start": start, "end": end}


def _inst(val, *, end, fy=2026, fp="FY", accn=_ACCN, form="10-K"):
    return {"val": val, "accn": accn, "form": form, "fy": fy, "fp": fp, "end": end}


def _facts(**concepts):
    # each concept is a plain list of USD facts -> wrap under the USD unit key
    return {"facts": {"us-gaap": {c: {"units": {"USD": units}} for c, units in concepts.items()}}}


# canonical current-period figures reused across cases
_CUR_REV, _CUR_NI, _CUR_TA = 400_000_000_000, 90_000_000_000, 360_000_000_000
_CUR = {"start": "2025-06-30", "end": "2026-06-27"}
_PRIOR = {"start": "2024-07-01", "end": "2025-06-28"}


def _certified_against_current(ident):
    """Build a span carrying exactly the selected current-period figures and
    assert the oracle certifies it — the correct-context fact IS certified."""
    key = {m: fid.value for m, fid in ident.items()}
    span = " ".join(f"{v // 1_000_000:,}" for v in key.values())  # printed in millions
    chk = validate_span(span, key)
    assert chk.verdict == "certified"


def test_identity_comparative_prior_year_not_chosen():
    # prior-year figures are LARGER (declining company): identity, not magnitude,
    # must drive the pick, so a naive max-|value| selector would fail this case
    facts = _facts(
        Revenues=[_dur(_CUR_REV, **_CUR), _dur(500_000_000_000, fy=2025, **_PRIOR)],
        NetIncomeLoss=[_dur(_CUR_NI, **_CUR), _dur(120_000_000_000, fy=2025, **_PRIOR)],
        Assets=[_inst(_CUR_TA, end="2026-06-27"), _inst(500_000_000_000, fy=2025, end="2025-06-28")],
    )
    ident = select_current_period_facts(facts, _ACCN)
    assert ident["revenue"].value == _CUR_REV       # latest end wins, not the bigger prior FY
    assert ident["total_assets"].value == _CUR_TA   # current balance, not last year's larger one
    _certified_against_current(ident)


def test_identity_quarterly_duration_not_chosen_as_full_year():
    # a Q4 duration ends on the fiscal year-end too; longest-duration tiebreak drops it
    # the quarter is given a LARGER value so the longest-duration tiebreak, not
    # magnitude, is what rejects it
    facts = _facts(
        Revenues=[_dur(_CUR_REV, **_CUR), _dur(500_000_000_000, start="2026-03-30", end="2026-06-27")],
        NetIncomeLoss=[_dur(_CUR_NI, **_CUR)],
        Assets=[_inst(_CUR_TA, end="2026-06-27")],
    )
    ident = select_current_period_facts(facts, _ACCN)
    assert ident["revenue"].value == _CUR_REV       # full-year, not the bigger quarter
    assert ident["revenue"].kind == "duration"
    _certified_against_current(ident)


def test_identity_duration_fact_not_chosen_for_instant_concept():
    # a stray duration-shaped Assets fact must be rejected — Assets is instant
    facts = _facts(
        Revenues=[_dur(_CUR_REV, **_CUR)],
        NetIncomeLoss=[_dur(_CUR_NI, **_CUR)],
        Assets=[_inst(_CUR_TA, end="2026-06-27"),
                _dur(999_000_000_000, start="2025-06-30", end="2026-06-27")],
    )
    ident = select_current_period_facts(facts, _ACCN)
    assert ident["total_assets"].value == _CUR_TA
    assert ident["total_assets"].kind == "instant"


def test_identity_wrong_currency_not_chosen():
    # a larger EUR value lives under a different unit key and must never be read
    facts = {"facts": {"us-gaap": {
        "Revenues": {"units": {
            "USD": [_dur(_CUR_REV, **_CUR)],
            "EUR": [_dur(999_000_000_000, **_CUR)],
        }},
        "NetIncomeLoss": {"units": {"USD": [_dur(_CUR_NI, **_CUR)]}},
        "Assets": {"units": {"USD": [_inst(_CUR_TA, end="2026-06-27")]}},
    }}}
    ident = select_current_period_facts(facts, _ACCN)
    assert ident["revenue"].value == _CUR_REV
    assert ident["revenue"].unit == "USD"
    _certified_against_current(ident)


def test_identity_wrong_period_fy_not_chosen():
    # an earlier-ending fiscal year tagged under the same accession is not current
    facts = _facts(
        Revenues=[_dur(_CUR_REV, **_CUR), _dur(500_000_000_000, fy=2024,
                                               start="2023-07-01", end="2024-06-29")],
        NetIncomeLoss=[_dur(_CUR_NI, **_CUR)],
        Assets=[_inst(_CUR_TA, end="2026-06-27")],
    )
    ident = select_current_period_facts(facts, _ACCN)
    assert ident["revenue"].value == _CUR_REV       # not the bigger earlier-FY figure
    assert ident["revenue"].fy == 2026


def test_identity_duplicate_context_is_deterministic():
    # two USD facts for the same period (e.g. a restatement) — selection must be
    # stable regardless of list order; largest |value| is the deterministic tiebreak
    a = _dur(_CUR_REV, **_CUR)
    b = _dur(401_000_000_000, **_CUR)
    facts_ab = _facts(Revenues=[a, b], NetIncomeLoss=[_dur(_CUR_NI, **_CUR)],
                      Assets=[_inst(_CUR_TA, end="2026-06-27")])
    facts_ba = _facts(Revenues=[b, a], NetIncomeLoss=[_dur(_CUR_NI, **_CUR)],
                      Assets=[_inst(_CUR_TA, end="2026-06-27")])
    v1 = select_current_period_facts(facts_ab, _ACCN)["revenue"].value
    v2 = select_current_period_facts(facts_ba, _ACCN)["revenue"].value
    assert v1 == v2 == 401_000_000_000


def test_identity_mismatch_downgrades_when_span_shows_prior_year_only():
    # span corroborates the prior-year comparative but NOT the current fact:
    # the additive layer must flag it as identity drift (needs_review evidence)
    facts = _facts(
        Revenues=[_dur(_CUR_REV, **_CUR), _dur(380_000_000_000, fy=2025, **_PRIOR)],
        NetIncomeLoss=[_dur(_CUR_NI, **_CUR), _dur(80_000_000_000, fy=2025, **_PRIOR)],
        Assets=[_inst(_CUR_TA, end="2026-06-27"), _inst(350_000_000_000, fy=2025, end="2025-06-28")],
    )
    prior_only = "Revenues 380,000 ... Net income 80,000 ... Total assets 350,000"
    notes = identity_mismatch(prior_only, facts, _ACCN)
    assert notes, "prior-year-only span must trip the identity drift detector"
    assert any("revenue" in n for n in notes)


def test_identity_mismatch_silent_when_span_shows_current_period():
    # the certified real path: current figures are present, so no drift is flagged
    facts = _facts(
        Revenues=[_dur(_CUR_REV, **_CUR), _dur(380_000_000_000, fy=2025, **_PRIOR)],
        NetIncomeLoss=[_dur(_CUR_NI, **_CUR), _dur(80_000_000_000, fy=2025, **_PRIOR)],
        Assets=[_inst(_CUR_TA, end="2026-06-27"), _inst(350_000_000_000, fy=2025, end="2025-06-28")],
    )
    current = "Revenues 400,000 ... Net income 90,000 ... Total assets 360,000"
    assert identity_mismatch(current, facts, _ACCN) == []


def test_certify_item8_additive_layer_does_not_change_clean_pass():
    """Stability guard: a pass Item 8 whose span carries the current-period
    figures keeps status=pass — the additive identity layer stays silent, the
    committed real certification cannot flip through this path."""
    from sec_core.items import ItemSegment
    from sec_core.xbrl import certify_item8

    seg = ItemSegment(filing_id="f", item_code="8", canonical_title="Financial Statements",
                      extracted_heading="Item 8.", start_offset=0, end_offset=50,
                      text_sha256="x", status="pass", confidence=0.9)
    facts = _facts(
        Revenues=[_dur(_CUR_REV, **_CUR), _dur(380_000_000_000, fy=2025, **_PRIOR)],
        NetIncomeLoss=[_dur(_CUR_NI, **_CUR), _dur(80_000_000_000, fy=2025, **_PRIOR)],
        Assets=[_inst(_CUR_TA, end="2026-06-27"), _inst(350_000_000_000, fy=2025, end="2025-06-28")],
    )

    class FakeResult:
        segments = [seg]
        def text_of(self, code):
            return "Revenues 400,000 ... Net income 90,000 ... Total assets 360,000"

    class FakeResp:
        content = __import__("json").dumps(facts).encode()

    class FakeFetcher:
        def get(self, url):
            return FakeResp()

    chk = certify_item8(FakeResult(), FakeFetcher(), cik=1, accession=_ACCN)
    assert chk.verdict == "certified"
    assert seg.status == "pass"
    assert seg.needs_review is False
    assert chk.identity_notes == []


def test_certify_item8_additive_layer_flags_period_drift():
    """The capability: a span that only echoes the prior-year comparative is
    marked needs_review by the additive identity layer (status left to the main
    verdict — here still certified on the prior number, but flagged for review)."""
    from sec_core.items import ItemSegment
    from sec_core.xbrl import certify_item8

    seg = ItemSegment(filing_id="f", item_code="8", canonical_title="Financial Statements",
                      extracted_heading="Item 8.", start_offset=0, end_offset=50,
                      text_sha256="x", status="pass", confidence=0.9)
    facts = _facts(
        Revenues=[_dur(_CUR_REV, **_CUR), _dur(380_000_000_000, fy=2025, **_PRIOR)],
        NetIncomeLoss=[_dur(_CUR_NI, **_CUR), _dur(80_000_000_000, fy=2025, **_PRIOR)],
        Assets=[_inst(_CUR_TA, end="2026-06-27"), _inst(350_000_000_000, fy=2025, end="2025-06-28")],
    )

    class FakeResult:
        segments = [seg]
        def text_of(self, code):
            return "Revenues 380,000 ... Net income 80,000 ... Total assets 350,000"

    class FakeResp:
        content = __import__("json").dumps(facts).encode()

    class FakeFetcher:
        def get(self, url):
            return FakeResp()

    chk = certify_item8(FakeResult(), FakeFetcher(), cik=1, accession=_ACCN)
    assert chk.identity_notes, "prior-year-only span must produce identity notes"
    assert seg.needs_review is True
    assert any("identity check" in w for w in seg.warnings)
