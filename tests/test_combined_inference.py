"""P0-9: combined-item inference fallback.

A singular heading like 'Item 1. Business and Properties' covers a second item
that never gets its own anchor. Without inference the content is not lost (the
span runs to the next anchor) but the covered item's recall silently drops to
zero as 'missing'. The fallback marks the pair combined — same semantics as an
explicit 'Items 1 and 2' heading — and says why in warnings.
"""

from __future__ import annotations

from sec_core.boundary import ResolvedItem, _infer_combined_headings
from sec_core.headings import VALID_CODES, HeadingCandidate
from sec_core.pipeline import extract_from_html

# --- synthetic-filing builders (same pattern as test_landmines) -------------

_FILLER = (
    "The Company continues to evaluate developments in its markets and adjusts its "
    "operating plans accordingly, and management believes the factors described above "
    "are the material considerations relevant to this item. "
)


def _pad(text: str, target: int = 1400) -> str:
    while len(text) < target:
        text += " " + _FILLER
    return text


def _sec(heading: str, body: str, target: int = 1400) -> str:
    return f"<p><b>{heading}</b></p>\n<p>{_pad(body, target)}</p>\n"


def _doc(*parts: str) -> str:
    return "<html><body>" + "".join(parts) + "</body></html>"


# --- end-to-end: singular 'Business and Properties' heading -----------------

def _business_and_properties_result():
    html = _doc(
        "<div>PART I</div>",
        _sec("Item 1. Business and Properties",
             "We operate globally. Our principal facilities are owned offices and "
             "leased data centers in Texas and Ireland."),
        _sec("Item 1A. Risk Factors", "Demand for our products may decline."),
        _sec("Item 3. Legal Proceedings", "We are party to ordinary-course litigation."),
    )
    return extract_from_html(html, "combined-inferred")


def test_item2_inferred_combined_not_silent_missing():
    result = _business_and_properties_result()
    seg = result.segment("2")
    assert seg.status == "partial"  # combined semantics, never a fabricated pass
    assert any(w.startswith("combined heading") for w in seg.warnings)  # third_engine contract
    assert any("inferred" in w for w in seg.warnings)  # says it was inference, not an anchor


def test_inferred_pair_share_span_and_both_marked():
    result = _business_and_properties_result()
    s1, s2 = result.segment("1"), result.segment("2")
    assert (s1.start_offset, s1.end_offset) == (s2.start_offset, s2.end_offset)
    assert s1.status == "partial"
    assert any("combined heading" in w for w in s1.warnings)
    assert s1.text_sha256 == s2.text_sha256
    # the shared span carries the properties content — nothing was lost
    assert "principal facilities" in result.text_of("2")


def test_genuinely_missing_item2_stays_missing():
    html = _doc(
        "<div>PART I</div>",
        _sec("Item 1. Business", "We operate globally."),
        _sec("Item 1A. Risk Factors", "Demand for our products may decline."),
        _sec("Item 3. Legal Proceedings", "We are party to ordinary-course litigation."),
    )
    seg = extract_from_html(html, "truly-missing").segment("2")
    assert seg.status == "missing"


def test_inference_requires_whole_title_not_substring():
    # 'Property Holdings' must not read as the canonical 'Properties'
    html = _doc(
        "<div>PART I</div>",
        _sec("Item 1. Business and Property Holdings", "We operate globally."),
        _sec("Item 1A. Risk Factors", "Demand for our products may decline."),
        _sec("Item 3. Legal Proceedings", "We are party to ordinary-course litigation."),
    )
    seg = extract_from_html(html, "substring-guard").segment("2")
    assert seg.status == "missing"


def test_non_adjacent_pair_item3_and_4():
    html = _doc(
        "<div>PART I</div>",
        _sec("Item 1. Business", "We operate globally."),
        _sec("Item 3. Legal Proceedings and Mine Safety Disclosures",
             "We are party to ordinary-course litigation. Our mines reported no violations."),
        _sec("Item 5. Market for Registrant's Common Equity",
             "Common stock trades on Nasdaq."),
    )
    result = extract_from_html(html, "combined-3-4")
    s3, s4 = result.segment("3"), result.segment("4")
    assert s4.status == "partial"
    assert (s3.start_offset, s3.end_offset) == (s4.start_offset, s4.end_offset)


# --- unit: guards on the inference pass --------------------------------------

def _cand(code: str, start: int, title: str, combined_with: str | None = None) -> HeadingCandidate:
    return HeadingCandidate(
        code=code, line_index=0, start=start, end=start + 40,
        heading_text=f"Item {code}. {title}", title_text=title,
        combined_with=combined_with,
    )


def _resolved(chosen_by_code: dict[str, HeadingCandidate]) -> dict[str, ResolvedItem]:
    return {
        code: ResolvedItem(code=code, chosen=chosen_by_code.get(code),
                           runner_up=None, rejected_toc=[], ambiguous=False)
        for code in VALID_CODES
    }


def test_no_chained_inference_off_an_explicit_combined_heading():
    # 'Items 1 and 2' already covers two items — it must not also absorb a third
    resolved = _resolved({
        "1": _cand("1", 100, "Business and Properties", combined_with="2"),
        "2": _cand("2", 100, "Business and Properties", combined_with="1"),
    })
    _infer_combined_headings(resolved)
    assert resolved["3"].chosen is None


def test_inference_scans_past_intervening_items():
    # 1A sits between 1 and 2 in schema order; the match is on item 1's title
    resolved = _resolved({
        "1": _cand("1", 100, "Business and Properties"),
        "1A": _cand("1A", 500, "Risk Factors"),
    })
    _infer_combined_headings(resolved)
    inferred = resolved["2"].chosen
    assert inferred is not None
    assert inferred.start == 100
    assert inferred.combined_with == "1"
    assert resolved["1"].chosen is not None
    assert resolved["1"].chosen.combined_with == "2"
    assert resolved["2"].warnings and "inferred" in resolved["2"].warnings[0]


def test_reserved_item6_never_inferred():
    resolved = _resolved({
        "5": _cand("5", 100, "Market for Registrant's Common Equity [Reserved]"),
    })
    _infer_combined_headings(resolved)
    assert resolved["6"].chosen is None
