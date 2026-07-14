"""Cross-reference-index filing detection (Intel / Citi / GE class).
The recurring corner case that sinks submissions: items marked extracted/ok
when the main document is only a pointer index into a bound annual report.
"""

from sec_core.cross_ref import detect_cross_reference_index, scan_bare_index
from sec_core.headings import detect_candidates
from sec_core.normalize import normalize_html
from sec_core.page_map import PageMap, resolve_page_ref
from sec_core.pipeline import extract_from_html
from sec_core.refine import classify_reference_stub

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


def test_bare_index_does_not_warn_unsupported():
    # A bare-index cross-reference filing (Citi-style) yields ZERO heading
    # candidates yet IS resolved via the xref path — it must NOT also emit the
    # "unsupported / non-10-K" warning (that string contradicted a successful
    # Citi run before the `and not xref.detected` guard).
    result = extract_from_html(BARE_INDEX, "synthetic-bare")
    assert result.filing_class == "cross_reference_index"
    assert len(result.candidates) == 0            # exercises the `not candidates` branch
    assert not any("unsupported or non-10-K" in w for w in result.warnings)


def test_pointers_show_own_entry_not_whole_index():
    # each unresolved pointer must span only its own index entry, never the
    # entire index block (which would make every pointer's text identical)
    result = extract_from_html(XREF_INDEX, "synthetic-xref")
    ptrs = [s for s in result.segments if s.provenance == "cross_reference_pointer"
            and s.end_offset > s.start_offset]
    spans = {(s.start_offset, s.end_offset) for s in ptrs}
    assert len(spans) == len(ptrs), "pointers share a span → index-block dump"
    for s in ptrs:
        assert (s.end_offset - s.start_offset) < 200


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


# --- regression: self-audited corner cases (2026-07-14 audit) -------------

def test_hole_b_long_incorporation_block_is_not_a_false_pass():
    """A verbose (>900 char) 'incorporated by reference to the proxy statement'
    block must classify as a pointer, not a substantive `pass`. Real XOM Item
    10/12 (1474 / 2013 chars) were shipped as `pass` before this fix."""
    caps = ["Election of Directors", "Corporate Governance", "Executive Compensation",
            "Compensation Discussion and Analysis", "Security Ownership of Beneficial "
            "Owners", "Related Person Transactions", "Audit Committee Report",
            "Ratification of Independent Auditors", "Director Independence"]
    long_ibr = ("The information required by this Item is incorporated herein by "
                "reference to the registrant's definitive Proxy Statement under the "
                "captions " + "; ".join(f"'{c}'" for c in caps * 3) + ".")
    assert len(long_ibr) > 900
    assert classify_reference_stub(long_ibr) is not None  # was None (-> pass) before
    # a hybrid item that ALSO prints a real data table (Item 12 equity-comp) is
    # NOT a pure pointer — its numeric density keeps it a substantive pass
    hybrid = ("Equity Compensation Plan Information. The following table sets forth "
              "the number of securities to be issued upon exercise of outstanding "
              "options, warrants and rights: "
              + " ".join(f"{n:,}" for n in range(4000, 4140))
              + ". Security ownership is incorporated by reference to the Proxy Statement.")
    assert len(hybrid) > 900  # strong tier, but numeric density keeps it a pass
    assert classify_reference_stub(hybrid) is None
    # and ordinary substantive prose stays a pass (no over-reach)
    prose = "The Company designs and sells consumer electronics. " * 40
    assert classify_reference_stub(prose) is None


def test_bare_index_detects_long_mdna_title():
    """Citi lists MD&A with its full 85-char canonical title; a 70-char cap
    silently dropped Item 7, leaving MD&A `missing` while its page anchor
    resolved fine. The bare index must now capture code 7 with its page ref."""
    rows = [
        ("1", "Business", "1-7"), ("1A", "Risk Factors", "49-62"),
        ("1B", "Unresolved Staff Comments", "None"), ("2", "Properties", "8"),
        ("3", "Legal Proceedings", "129"), ("4", "Mine Safety Disclosures", "None"),
        ("5", "Market for Common Equity", "63"),
        ("7", "Management's Discussion and Analysis of Financial Condition and "
              "Results of Operations", "8-36, 64-120"),
        ("7A", "Quantitative and Qualitative Disclosures About Market Risk", "64-120"),
        ("8", "Financial Statements and Supplementary Data", "134-298"),
    ]
    html = "<html><body><div>Item NumberPage</div>" + "".join(
        f"<div>{c}. {t} {p}</div>" for c, t, p in rows) + "</body></html>"
    idx = scan_bare_index(normalize_html(html))
    assert idx.detected
    assert "7" in idx.page_refs and idx.page_refs["7"].startswith("8-36")


def test_resolve_page_ref_prefers_earliest_start_not_widest():
    """Multi-range refs must resolve to the EARLIEST-start range (the item's own
    body), not the widest — else Citi MD&A ('8-36, 64-120') and Item 7A
    ('64-120, ...') collapse onto the same 64-120 span (a boundary collision)."""
    pm = PageMap(marker_start={p: p * 1000 for p in range(1, 130)},
                 marker_end={p: p * 1000 + 50 for p in range(1, 130)},
                 lo_page=1, hi_page=129)
    md_a = resolve_page_ref(pm, "8-36, 64-120")    # MD&A: earliest = 8-36
    m_risk = resolve_page_ref(pm, "64-120")         # 7A: 64-120
    assert md_a is not None and m_risk is not None
    assert md_a != m_risk                            # distinct spans (no collision)
    assert md_a[0] < m_risk[0]                        # MD&A body starts earlier


def test_resolve_page_ref_avoids_claimed_spans_no_collision():
    """No two distinct items may resolve to a byte-identical span. INTC lists
    Item 15 as '56-108, 110-115' (56-108 is Item 8's financials it references,
    110-115 is its own exhibit index) and Items 1C/9B both as 'Page 54'.
    Steering past claimed spans lands Item 15 on 110-115 and leaves the
    duplicate-only 9B unresolvable (-> honest pointer), never a shared body."""
    pm = PageMap(marker_start={p: p * 1000 for p in range(1, 130)},
                 marker_end={p: p * 1000 + 50 for p in range(1, 130)},
                 lo_page=1, hi_page=129)
    s8 = resolve_page_ref(pm, "56-108")                       # Item 8 claims financials
    s15 = resolve_page_ref(pm, "56-108, 110-115", avoid={s8})  # Item 15 -> own range
    assert s8 is not None and s15 is not None
    assert s8 != s15 and s15[0] > s8[0]                        # 15 steered to page 110+
    s1c = resolve_page_ref(pm, "54")                           # 1C claims page 54
    s9b = resolve_page_ref(pm, "54", avoid={s1c})              # 9B: no free range
    assert s1c is not None and s9b is None                     # -> caller uses pointer
