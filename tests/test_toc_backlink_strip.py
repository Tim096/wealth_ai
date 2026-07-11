"""Two-layer output: table-of-contents navigation backlink lines are removed from
the DELIVERED clean item text, while the raw source span (offsets + sha256 +
coverage) stays intact for provenance. Only the anchor-backed 'Table of Contents'
navigation class is stripped — never genuine body sentences or legitimate
recurring financial content (broad recurring-line stripping was rejected, see
docs/research/giants_task2.md §18:40).
"""

from observability_core import sha256_text
from sec_core.normalize import FLAG_TOC_LINK, normalize_html


# A minimal item body: two paragraphs of real content (with a legitimately
# recurring 'Net sales grew.' line), interleaved with a 'Table of Contents'
# navigation backlink rendered as an internal anchor (<a href="#toc">) at each
# page break — plus a genuine 'TABLE OF CONTENTS' section heading (NOT an anchor).
BODY_HTML = (
    "<h2>TABLE OF CONTENTS</h2>"
    "<div>Item 1. Business</div>"
    "<div>We operate manufacturing facilities worldwide. Net sales grew.</div>"
    '<div><a href="#toc">Table of Contents</a></div>'
    "<div>Our properties span three states and two countries. Net sales grew.</div>"
    '<div><a href="#toc">Table of Contents</a></div>'
    "<div>Risk factors are described in the following section.</div>"
)


def _doc():
    return normalize_html(BODY_HTML)


def test_backlink_line_dropped_from_clean_slice():
    doc = _doc()
    raw = doc.slice(0, len(doc.text))
    clean = doc.clean_slice(0, len(doc.text))
    assert raw.count("Table of Contents") == 2  # the two anchor backlinks
    assert "Table of Contents" not in clean     # both removed from delivery
    # real body sentences survive verbatim
    assert "manufacturing facilities worldwide" in clean
    assert "Our properties span three states" in clean
    assert "Risk factors are described" in clean


def test_recurring_financial_content_never_stripped():
    doc = _doc()
    clean = doc.clean_slice(0, len(doc.text))
    # 'Net sales grew.' recurs but is real content, not a TOC nav phrase — kept both times
    assert clean.count("Net sales grew.") == 2


def test_genuine_toc_heading_not_an_anchor_is_kept():
    doc = _doc()
    clean = doc.clean_slice(0, len(doc.text))
    # the uppercase 'TABLE OF CONTENTS' section heading is not inside an anchor,
    # so it is a real heading, not a backlink — must survive
    assert "TABLE OF CONTENTS" in clean


def test_backlink_lines_are_internal_anchors_but_headings_are_not():
    doc = _doc()
    heading = next(ln for ln in doc.lines if ln.text.strip() == "TABLE OF CONTENTS")
    backlink = next(ln for ln in doc.lines if ln.text.strip() == "Table of Contents")
    assert not any(doc.flags[i] & FLAG_TOC_LINK for i in range(heading.start, heading.end))
    assert all(doc.flags[i] & FLAG_TOC_LINK for i in range(backlink.start, backlink.end)
               if not doc.text[i].isspace())
    assert doc._is_toc_backlink_line(backlink)
    assert not doc._is_toc_backlink_line(heading)


def test_raw_span_and_provenance_are_unchanged():
    doc = _doc()
    n = len(doc.text)
    raw = doc.slice(0, n)
    # slice() is the provenance layer — backlinks retained, sha256 addresses it
    assert "Table of Contents" in raw
    assert sha256_text(raw) == sha256_text(doc.text)
    # clean output is strictly a subsequence-by-lines of the raw (nothing added)
    clean = doc.clean_slice(0, n)
    assert len(clean) < len(raw)
    for line in clean.split("\n"):
        if line.strip():
            assert line in raw


def test_clean_slice_noop_when_no_backlinks():
    doc = normalize_html("<div>Item 1. Business</div><div>Plain body, no navigation.</div>")
    n = len(doc.text)
    assert doc.clean_slice(0, n) == doc.slice(0, n)


def test_partial_backlink_phrase_in_prose_is_not_stripped():
    # a line that merely mentions the phrase inside a sentence must be kept —
    # stripping requires the WHOLE line to be the nav phrase
    doc = normalize_html(
        "<div>See the table of contents for a full list of exhibits.</div>"
        '<div><a href="#toc">Table of Contents</a></div>'
    )
    clean = doc.clean_slice(0, len(doc.text))
    assert "See the table of contents for a full list" in clean
    assert clean.count("Table of Contents") == 0  # only the standalone anchor line went
