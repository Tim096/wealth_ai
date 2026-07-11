"""Wrapper 10-K body reassembly (P0-10, the JPM/XOM class).

These filings keep real item headings but write Items 7/7A/8 (JPM: also 1C) as
one-sentence stubs deferring to a Financial Section / annual report bound after
the last item heading. boundary.py cuts the appended block off the terminal
item (FG-SEC-004); reassemble_wrapper_bodies resolves the stubs back into
source-exact spans inside that block — page-range stubs via printed page-number
anchors (JPM), quoted-section-title stubs via the bound report's own section
headings (XOM). External pointers (proxy statement) and unresolvable anchors
stay honest pointers.
"""

import pytest

from sec_core.normalize import normalize_html
from sec_core.page_map import build_page_map
from sec_core.pipeline import extract_from_html

FILLER = (
    "The company manufactures precision widgets and distributes them through "
    "regional partners under long-term supply agreements reviewed annually. "
)


def _item(code: str, title: str, body: str) -> str:
    return f"<p><b>Item {code}. {title}</b></p><p>{body}</p>"


def _financial_section(pages: int = 10, per_page: int = 18) -> str:
    """An appended, separately-paginated financial report: its own TOC, then
    pages 1..N each ending in a printed page-number footer. Section headings
    sit at the top of page 2 (Widget Performance Review) and page 5 (the audit
    report); a unique token marks every page."""
    parts = [
        "<div>FINANCIAL SECTION</div>",
        "<div>TABLE OF CONTENTS</div>",
        "<div>Widget Performance Review</div><div>2</div>",
        "<div>Report of Independent Registered Public Accounting Firm</div><div>5</div>",
        "<div>Supplemental Data</div><div>9</div>",
    ]
    for pg in range(1, pages + 1):
        if pg == 2:
            parts.append("<div>WIDGET PERFORMANCE REVIEW</div>")
        if pg == 5:
            parts.append("<div>REPORT OF INDEPENDENT REGISTERED PUBLIC ACCOUNTING FIRM</div>")
            parts.append("<p>To the Board of Directors and Shareholders: our audit opinion follows.</p>")
        if pg == 9:
            parts.append("<div>SUPPLEMENTAL DATA</div>")
        parts.append(f"<p>page-token-{pg} " + FILLER * per_page + "</p>")
        parts.append(f"<div>{pg}</div>")  # printed page-number footer
    parts.append("<div>SIGNATURES</div><p>Pursuant to the requirements of the Act.</p>")
    return "".join(parts)


def _wrapper_html() -> str:
    # substantive bodies must be big enough that the main part does not look
    # like one dense heading cluster (the cross-reference-index detector)
    body = FILLER * 35
    return "<html><body>" + "".join([
        _item("1", "Business", body),
        _item("1A", "Risk Factors", "Risks and uncertainties. " + body),
        _item("2", "Properties", body),
        _item("3", "Legal Proceedings",
              "Refer to Note 30 for a description of material legal proceedings."),
        _item("4", "Mine Safety Disclosures", "Not applicable."),
        _item("5", "Market for Registrant's Common Equity", body),
        _item("7", "Management's Discussion and Analysis of Financial Condition and Results of Operations",
              "Management's discussion and analysis, entitled \"Widget Performance Review,\" "
              "appear on pages 2-4. Such information should be read in conjunction with the "
              "Consolidated Financial Statements, which appear on pages 5-9."),
        _item("7A", "Quantitative and Qualitative Disclosures About Market Risk",
              "Reference is made to the section entitled \"Widget Performance Review\" "
              "in the Financial Section of this report."),
        _item("8", "Financial Statements and Supplementary Data",
              "The Consolidated Financial Statements, together with the Notes thereto, "
              "appear on pages 5-9 of the Financial Section."),
        _item("9", "Changes in and Disagreements with Accountants on Accounting and Financial Disclosure",
              "Refer to page 900 of the annual report for details."),
        _item("10", "Directors, Executive Officers and Corporate Governance", body),
        _item("11", "Executive Compensation",
              "Incorporated by reference to the section entitled \"Executive Pay\" of the "
              "registrant's 2026 Proxy Statement."),
        _item("12", "Security Ownership of Certain Beneficial Owners and Management", body),
        _item("15", "Exhibits, Financial Statement Schedules",
              "The following exhibits are filed herewith: " + FILLER * 20),
        _financial_section(),
    ]) + "</body></html>"


@pytest.fixture(scope="module")
def wrapper():
    return extract_from_html(_wrapper_html(), "wrapper-fixture")


def _seg(result, code):
    return next(s for s in result.segments if s.item_code == code)


# --- page-range stubs (JPM class) ------------------------------------------
def test_page_ref_stub_reassembled(wrapper):
    seg = _seg(wrapper, "8")
    assert seg.status == "partial"
    assert seg.provenance == "resolved_from_page_anchor"
    assert seg.needs_review is True
    assert seg.text_sha256
    body = wrapper.text_of("8")
    assert "page-token-6" in body            # inside pages 5-9
    assert "page-token-2" not in body        # bounded, not the whole block
    assert any("reassembled from" in w for w in seg.warnings)
    assert not any("the span is the pointer text only" in w for w in seg.warnings)


def test_first_page_range_wins_over_supplementary_mention(wrapper):
    # JPM Item 7: own range 2-4 first, "read in conjunction with ... 5-9" after.
    # The widest range is the WRONG one here; the first mention is the item's.
    body = wrapper.text_of("7")
    seg = _seg(wrapper, "7")
    assert seg.provenance == "resolved_from_page_anchor"
    assert "page-token-3" in body
    assert "page-token-8" not in body


# --- quoted-section-title stubs (XOM class) ---------------------------------
def test_section_title_stub_reassembled(wrapper):
    seg = _seg(wrapper, "7A")
    assert seg.status == "partial"
    assert seg.provenance == "resolved_from_section_anchor"
    body = wrapper.text_of("7A")
    # starts at the bound report's real section heading, not its TOC entry
    assert body.startswith("WIDGET PERFORMANCE REVIEW")
    assert "page-token-3" in body
    # ends at the next known section boundary (the audit report heading)
    assert "page-token-6" not in body
    assert "audit opinion" not in body


def test_section_anchor_skips_toc_entry(wrapper):
    # the Financial Section's own TOC lists the same title followed by page
    # numbers; the resolved span must anchor past it
    seg = _seg(wrapper, "7A")
    toc_offset = wrapper.doc.text.index("Widget Performance Review")
    assert seg.start_offset > toc_offset


# --- honest pointers stay pointers ------------------------------------------
def test_proxy_stub_untouched(wrapper):
    seg = _seg(wrapper, "11")
    assert seg.status == "incorporated_by_reference"
    assert seg.provenance == "offset_exact_span"


def test_note_pointer_stub_untouched(wrapper):
    seg = _seg(wrapper, "3")
    assert seg.status == "incorporated_by_reference"


def test_unresolvable_page_ref_stays_pointer(wrapper):
    # Item 9 points at page 900 — outside the recovered pagination
    seg = _seg(wrapper, "9")
    assert seg.status == "incorporated_by_reference"
    assert seg.provenance == "offset_exact_span"


def test_no_reassembly_without_appended_region():
    # same stub phrasing, but nothing bound after the last item -> untouched
    body = FILLER * 8
    html = "<html><body>" + "".join([
        _item("1", "Business", body),
        _item("1A", "Risk Factors", body),
        _item("2", "Properties", body),
        _item("3", "Legal Proceedings", body),
        _item("5", "Market for Registrant's Common Equity", body),
        _item("7", "Management's Discussion and Analysis",
              "The information appears in the report, which appear on pages 2-3."),
        _item("8", "Financial Statements and Supplementary Data", body),
        _item("9A", "Controls and Procedures", body),
        _item("15", "Exhibits, Financial Statement Schedules", "Exhibit list."),
    ]) + "</body></html>"
    result = extract_from_html(html, "no-tail-fixture")
    seg = next(s for s in result.segments if s.item_code == "7")
    assert seg.status == "incorporated_by_reference"
    assert seg.provenance == "offset_exact_span"


# --- page_map region + noise handling ---------------------------------------
def test_build_page_map_region_excludes_earlier_markers():
    main = "".join(f"<p>{FILLER}</p><div>{pg}</div>" for pg in range(1, 7))
    tail = "".join(f"<p>tail {FILLER}</p><div>{pg}</div>" for pg in range(40, 52))
    doc = normalize_html(f"<html><body>{main}<div>FINANCIAL SECTION</div>{tail}</body></html>")
    cut = doc.text.index("FINANCIAL SECTION")
    pm = build_page_map(doc, start=cut)
    assert pm.ok
    assert pm.lo_page >= 40  # main-part footers 1..6 are excluded


def test_page_chain_splits_at_year_pollution():
    # bare year lines ("2025") thread into an increasing subsequence; the
    # recovered pagination must not jump from page 8 to "page 2025"
    pages = "".join(f"<p>{FILLER * 3}</p><div>{pg}</div>" for pg in range(1, 9))
    years = "<div>2023</div><p>x</p><div>2024</div><p>y</p><div>2025</div>"
    doc = normalize_html(f"<html><body>{pages}{years}</body></html>")
    pm = build_page_map(doc)
    assert pm.hi_page == 8
