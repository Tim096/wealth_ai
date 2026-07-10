"""Cross-reference-index filing detection (Intel / Citi / GE class).
The recurring corner case that sinks submissions: items marked extracted/ok
when the main document is only a pointer index into a bound annual report.
"""

from sec_core.cross_ref import detect_cross_reference_index, scan_bare_index
from sec_core.headings import detect_candidates
from sec_core.normalize import normalize_html
from sec_core.pipeline import extract_from_html

# a cross-reference index: every item heading followed by a page range, no bodies
XREF_INDEX = "<html><body><div>Cross-Reference Index</div>" + "".join(
    f"<p><b>Item {code}. {title}</b></p><div>Pages {10 + i}-{20 + i}</div>"
    for i, (code, title) in enumerate([
        ("1", "Business"), ("1A", "Risk Factors"), ("1B", "Unresolved Staff Comments"),
        ("2", "Properties"), ("3", "Legal Proceedings"), ("5", "Market for Common Equity"),
        ("7", "Management's Discussion and Analysis"), ("7A", "Market Risk"),
        ("8", "Financial Statements"), ("9A", "Controls and Procedures"),
    ])
) + "</body></html>"

# Citi-style bare index: '<code>.<title><pageref>' with no word 'Item'
BARE_INDEX = "<html><body><div>Item NumberPage</div>" + "".join(
    f"<div>{code}.{title}{40 + i}-{50 + i}</div>"
    for i, (code, title) in enumerate([
        ("1", "Business"), ("1A", "Risk Factors"), ("1B", "Unresolved Staff Comments"),
        ("2", "Properties"), ("3", "Legal Proceedings"), ("4", "Mine Safety Disclosures"),
        ("5", "Market for Common Equity"), ("7", "Management's Discussion and Analysis"),
        ("8", "Financial Statements"), ("9A", "Controls and Procedures"),
    ])
) + "</body></html>"


def test_cross_reference_index_detected():
    doc = normalize_html(XREF_INDEX)
    cands = detect_candidates(doc)
    idx = detect_cross_reference_index(doc, cands)
    assert idx.detected
    assert idx.page_refs.get("1A", "").startswith(("Pages", "1", "2", "3"))


def test_cross_reference_items_are_honest_pointers():
    result = extract_from_html(XREF_INDEX, "synthetic-xref")
    assert result.filing_class == "cross_reference_index"
    s = result.segment("1A")
    assert s.status == "incorporated_by_reference"
    assert s.provenance == "cross_reference_pointer"
    assert s.needs_review is True
    # never fake a body
    assert s.text_sha256 == ""


def test_bare_index_without_item_prefix_detected():
    doc = normalize_html(BARE_INDEX)
    cands = detect_candidates(doc)
    assert len(cands) < 8  # standard detection finds little/nothing
    idx = scan_bare_index(doc)
    assert idx.detected
    assert "1A" in idx.entries


def test_normal_filing_not_flagged_as_cross_reference():
    from pathlib import Path

    html = (Path(__file__).resolve().parents[1] / "data" / "sec_eval" / "fixtures"
            / "alpha_10k.html").read_text(encoding="utf-8")
    result = extract_from_html(html, "alpha")
    assert result.filing_class == "standard"
    # a normal filing's real bodies must still be pass, not pointers
    assert result.segment("1").status == "pass"


def test_needs_review_flag_defaults_false_for_clean_pass():
    from pathlib import Path

    html = (Path(__file__).resolve().parents[1] / "data" / "sec_eval" / "fixtures"
            / "alpha_10k.html").read_text(encoding="utf-8")
    result = extract_from_html(html, "alpha")
    assert result.segment("1").needs_review is False
