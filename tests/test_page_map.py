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


def test_synthetic_wrapper_resolves_item_body():
    # index that points Item 1A to a page range, plus a paginated body
    index = ("<div>Cross-Reference Index</div>"
             + "".join(f"<p><b>Item {c}. {t}</b></p><div>Pages {2+i}-{3+i}</div>"
                       for i, (c, t) in enumerate([
                           ("1", "Business"), ("1A", "Risk Factors"), ("2", "Properties"),
                           ("3", "Legal Proceedings"), ("5", "Market"), ("7", "MD&A"),
                           ("7A", "Market Risk"), ("8", "Financial Statements"),
                           ("9A", "Controls")])))
    html = f"<html><body>{index}{_body_with_pages()}</body></html>"
    result = extract_from_html(html, "synthetic-wrapper")
    assert result.filing_class == "cross_reference_index"
    resolved = [s for s in result.segments if s.provenance == "resolved_from_page_anchor"]
    assert resolved, "expected at least one item resolved from page anchors"
    for s in resolved:
        assert s.status == "partial" and s.needs_review is True
        assert s.text_sha256  # a real source-exact span, not a pointer
