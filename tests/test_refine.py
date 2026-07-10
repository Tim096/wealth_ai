"""Unit tests for span refinement — the fixes for the audit's silent failures.
Each maps to a confirmed anomaly class in docs/failure_gallery.md."""

from sec_core.normalize import normalize_html
from sec_core.refine import (
    classify_reference_stub,
    detect_appended_section_cut,
    is_boilerplate_none,
    trim_trailing_furniture,
)


# --- reference-stub classification (FG-SEC-002) ---------------------------
def test_stub_refer_to_note():
    # MSFT Item 3 phrasing the old regex missed
    t = "Refer to Note 14 - Contingencies of the Notes to Financial Statements (Part II, Item 8 of this Form 10-K) for information regarding legal proceedings."
    assert classify_reference_stub(t) is not None


def test_stub_reference_is_made_to_section():
    # XOM Item 7 phrasing (references a named section, not an item number)
    t = 'Reference is made to the section entitled "Management\'s Discussion and Analysis of Financial Condition and Results of Operations" in the Financial Section of this report.'
    target = classify_reference_stub(t)
    assert target is not None and "Financial Section" in target


def test_stub_proxy_incorporation_any_word_order():
    # GS Item 11 phrasing: words between "incorporated" and "by reference"
    t = "Information relating to executive compensation will be in the 2026 Proxy Statement and is incorporated in this Form 10-K by reference."
    target = classify_reference_stub(t)
    assert target is not None and "proxy" in target.lower()


def test_stub_page_range_reference():
    # JPM Item 8 phrasing: points to page numbers
    t = "The Consolidated Financial Statements, together with the Notes thereto, appear on pages 162-314."
    assert classify_reference_stub(t) is not None


def test_boilerplate_none_is_not_a_stub():
    for body in ["None.", "Not applicable.", "not applicable", "None"]:
        assert classify_reference_stub(body) is None
        assert is_boilerplate_none(body)


def test_substantive_body_is_not_a_stub():
    # a long real body that mentions "see Note X" in passing must not be a stub
    body = ("Investing in our common stock involves risk. " * 60) + " See Note 5 for details."
    assert len(body) > 900
    assert classify_reference_stub(body) is None


# --- trailing furniture trim (FG-SEC-003) ---------------------------------
def test_trim_part_divider_and_page_number():
    html = "<p><b>Item 4. Mine Safety Disclosures</b></p><p>Not applicable.</p><div>18</div><div>PART II</div><p><b>Item 5. Market</b></p>"
    doc = normalize_html(html)
    # span covers item 4 heading through just before item 5
    start = doc.text.index("Item 4")
    end = doc.text.index("Item 5. Market")
    new_end, trimmed = trim_trailing_furniture(doc, start, end)
    kept = doc.text[start:new_end]
    assert "PART II" not in kept
    assert "18" not in kept.split("Not applicable.")[-1]
    assert "Not applicable." in kept
    assert trimmed


def test_trim_stops_at_real_content():
    html = "<p><b>Item 3. Legal Proceedings</b></p><p>We are party to a material lawsuit filed in Texas.</p><div>27</div><div>PART II</div>"
    doc = normalize_html(html)
    start = doc.text.index("Item 3")
    new_end, _ = trim_trailing_furniture(doc, start, len(doc.text))
    assert "material lawsuit" in doc.text[start:new_end]


# --- appended section cut (FG-SEC-004) ------------------------------------
def test_appended_financial_section_cut():
    filler = "".join("<p>financial data line for the appended section</p>" for _ in range(2000))
    html = ("<p><b>Item 16. Form 10-K Summary</b></p><p>None.</p><div>27</div>"
            "<div>Financial Section</div>" + filler)
    doc = normalize_html(html)
    start = doc.text.index("Item 16")
    cut = detect_appended_section_cut(doc, start, len(doc.text))
    assert cut is not None
    assert "None." in doc.text[start:cut]
    assert "financial data line" not in doc.text[start:cut]


def test_no_cut_for_normal_short_terminal_item():
    doc = normalize_html("<p><b>Item 16. Form 10-K Summary</b></p><p>None.</p>")
    assert detect_appended_section_cut(doc, 0, len(doc.text)) is None
