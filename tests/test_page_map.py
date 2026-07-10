"""Page-anchor resolution for cross-reference-index (wrapper) 10-Ks.
This is what completes the Intel/Citi core task: recover real source-exact
item bodies from the printed page-number footers, not just honest pointers.
"""

from sec_core.normalize import normalize_html
from sec_core.page_map import build_page_map, resolve_page_ref
from sec_core.pipeline import extract_from_html


def _body_with_pages():
    # a body that prints a page-number footer after each page's content
    parts = ["<div>Cover</div>"]
    for pg in range(1, 9):
        parts.append(f"<p>Body content on page {pg}. " + ("lorem ipsum dolor sit amet " * 20) + "</p>")
        parts.append(f"<div>{pg}</div>")  # footer marker
    return "".join(parts)


def test_build_page_map_recovers_sequence():
    doc = normalize_html(f"<html><body>{_body_with_pages()}</body></html>")
    pm = build_page_map(doc)
    assert pm.ok
    assert pm.lo_page == 1 and pm.hi_page == 8


def test_resolve_page_ref_maps_range_to_offsets():
    doc = normalize_html(f"<html><body>{_body_with_pages()}</body></html>")
    pm = build_page_map(doc)
    span = resolve_page_ref(pm, "Pages 3-5")
    assert span is not None
    lo, hi = span
    text = doc.text[lo:hi]
    assert "page 3" in text and "page 5" in text
    assert "page 8" not in text  # bounded, not the whole doc


def test_lis_ignores_front_matter_noise():
    # front matter has out-of-order small numbers; body has the real run
    doc = normalize_html("<div>7</div><div>2</div><div>99</div>" + f"<div>x</div>{_body_with_pages()}")
    pm = build_page_map(doc)
    assert pm.hi_page >= 8


def test_resolve_returns_none_when_no_pagination():
    doc = normalize_html("<html><body><p>No page numbers here at all.</p></body></html>")
    pm = build_page_map(doc)
    assert resolve_page_ref(pm, "Pages 3-5") is None


def _wrapper_body_with_headings():
    # a wrapper body that prints its section HEADING at the top of the item's
    # first page (as real annual-report bodies do) plus a page-number footer.
    # The trust gate resolves a page anchor to content only when the span head
    # actually carries that item's heading — so the heading must be present.
    headings = {3: "Risk Factors", 5: "Management's Discussion and Analysis"}
    parts = ["<div>Cover</div>"]
    for pg in range(1, 9):
        if pg in headings:
            parts.append(f"<p><b>{headings[pg]}</b></p>")
        parts.append(f"<p>Body content on page {pg}. " + ("lorem ipsum dolor sit amet " * 20) + "</p>")
        parts.append(f"<div>{pg}</div>")  # footer marker
    return "".join(parts)


def test_synthetic_wrapper_resolves_item_body():
    # index points Item 1A -> pages 3-4 and Item 7 -> pages 5-6, whose body pages
    # begin with the matching section heading, so the anchor is verifiable.
    entries = [("1", "Business", "8-9"), ("1A", "Risk Factors", "3-4"),
               ("2", "Properties", "8-9"), ("3", "Legal Proceedings", "8-9"),
               ("5", "Market", "8-9"), ("7", "MD&A", "5-6"),
               ("7A", "Market Risk", "8-9"), ("8", "Financial Statements", "8-9"),
               ("9A", "Controls", "8-9")]
    index = ("<div>Cross-Reference Index</div>"
             + "".join(f"<p><b>Item {c}. {t}</b></p><div>Pages {pr}</div>"
                       for c, t, pr in entries))
    html = f"<html><body>{index}{_wrapper_body_with_headings()}</body></html>"
    result = extract_from_html(html, "synthetic-wrapper")
    assert result.filing_class == "cross_reference_index"
    resolved = [s for s in result.segments if s.provenance == "resolved_from_page_anchor"]
    assert resolved, "expected at least one item resolved from page anchors"
    codes = {s.item_code for s in resolved}
    assert "1A" in codes and "7" in codes  # verified by their section headings
    for s in resolved:
        assert s.status == "partial" and s.needs_review is True
        assert s.text_sha256  # a real source-exact span, not a pointer


def test_page_anchor_without_matching_heading_is_demoted_not_mislabelled():
    # A page range that resolves to a body span whose head is NOT the item's
    # section heading must NOT be shown as content (that is the Intel silent
    # mislabel: "Properties" resolving onto unrelated prose). It is demoted to
    # an honest pointer instead.
    entries = [("1", "Business", "8-9"), ("1A", "Risk Factors", "8-9"),
               ("2", "Properties", "3-4"), ("3", "Legal Proceedings", "8-9"),
               ("5", "Market", "8-9"), ("7", "MD&A", "8-9"),
               ("7A", "Market Risk", "8-9"), ("8", "Financial Statements", "8-9"),
               ("9A", "Controls", "8-9")]
    index = ("<div>Cross-Reference Index</div>"
             + "".join(f"<p><b>Item {c}. {t}</b></p><div>Pages {pr}</div>"
                       for c, t, pr in entries))
    # pages 3-4 carry a "Risk Factors" heading, NOT "Properties"
    html = f"<html><body>{index}{_wrapper_body_with_headings()}</body></html>"
    result = extract_from_html(html, "synthetic-wrapper")
    props = result.segment("2")
    assert props.provenance == "cross_reference_pointer"
    assert props.status == "incorporated_by_reference"
    assert props.text_sha256 == ""  # never a fabricated/mislabelled body
