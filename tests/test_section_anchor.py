"""Page-top section anchoring (oracle-driven wrapper body resolution).

The CYD iXBRL oracle exposed two Item 1C failure modes that share one printed
structure — bound reports repeat the same short furniture lines (company
banner, running header) after every page-number marker, and a top-level
section starts where the first NON-furniture line of a page is itself a short
heading:

* GS class — an incorporated_by_reference stub quotes the exact section
  heading living inside ANOTHER item's span of the SAME filing ('See "MD&A -
  Risk Management - Cybersecurity Risk Management" in Part II, Item 7 of this
  Form 10-K'). resolve_intra_document_pointers anchors the quoted path's last
  component as a page-top section heading inside the referenced item's span.

* JPM class — a page-range stub resolves to whole pages that BEGIN at a
  parent section while the item's own body is a later section on those pages
  ("pages 146-149" begin at Operational Risk Management; the CYD-tagged body
  is the Cybersecurity risk section on page 147). reassemble_wrapper_bodies
  snaps the resolved window to the canonical-title-matching section.

Both refinements are structural (printed page data + title matching, no
ticker specifics) and share the kill-switch SEC_WRAPPER_SECTION_ANCHOR=0.
"""

import pytest

from sec_core.pipeline import extract_from_html

FILLER = (
    "The company manufactures precision widgets and distributes them through "
    "regional partners under long-term supply agreements reviewed annually. "
)

BANNER = "Acme Industries 2026 Form 10-K"
RUNNING_HEADER = "Management's Discussion and Analysis"


def _item(code: str, title: str, body: str) -> str:
    return f"<p><b>Item {code}. {title}</b></p><p>{body}</p>"


def _mdna_pages() -> str:
    """A paginated MD&A body (pages 84-92): every page top prints the same
    banner + page number + running header; top-level sections start where a
    short heading follows that furniture (pages 85, 87, 89); other pages
    continue the previous section with prose."""
    sections = {
        85: "Risk Management",        # parent chapter intro (7A quotes this)
        87: "Cybersecurity Program",  # the 1C body
        89: "Model Risk Review",      # next sibling — ends the 1C span
    }
    parts = ["<p>Introduction to our results of operations. " + FILLER * 4 + "</p>"]
    for pg in range(84, 93):
        parts.append(f"<div>{BANNER}</div><div>{pg}</div><div>{RUNNING_HEADER}</div>")
        if pg in sections:
            parts.append(f"<div>{sections[pg]}</div>")
        parts.append(f"<p>page-token-{pg} " + FILLER * 4 + "</p>")
    return "".join(parts)


def _gs_class_html() -> str:
    body = FILLER * 15
    return "<html><body>" + "".join([
        _item("1", "Business", body),
        _item("1A", "Risk Factors", "Risks and uncertainties. " + body),
        _item("1B", "Unresolved Staff Comments", "None."),
        _item("1C", "Cybersecurity",
              'See "Management\'s Discussion and Analysis - Risk Management - '
              'Cybersecurity Program" in Part II, Item 7 of this Form 10-K for '
              "further information about cybersecurity."),
        _item("2", "Properties", body),
        _item("3", "Legal Proceedings", body),
        _item("5", "Market for Registrant's Common Equity", body),
        _item("7", "Management's Discussion and Analysis of Financial Condition "
                   "and Results of Operations", _mdna_pages()),
        _item("7A", "Quantitative and Qualitative Disclosures About Market Risk",
              'Quantitative and qualitative disclosures about market risk are set '
              'forth in "Management\'s Discussion and Analysis - Risk Management" '
              "in Part II, Item 7 of this Form 10-K."),
        _item("8", "Financial Statements and Supplementary Data", body),
        _item("9A", "Controls and Procedures", body),
        _item("10", "Directors, Executive Officers and Corporate Governance", body),
        _item("11", "Executive Compensation",
              "Information about executive compensation will be in the 2026 Proxy "
              "Statement and is incorporated in this Form 10-K by reference."),
        _item("12", "Security Ownership of Certain Beneficial Owners", body),
        _item("15", "Exhibits, Financial Statement Schedules",
              "The following exhibits are filed herewith: " + FILLER * 10),
    ]) + "</body></html>"


@pytest.fixture(scope="module")
def gs_class():
    return extract_from_html(_gs_class_html(), "gs-class-fixture")


def _seg(result, code):
    return next(s for s in result.segments if s.item_code == code)


# --- GS class: in-document quoted-section pointer ----------------------------
def test_intra_doc_pointer_resolved(gs_class):
    seg = _seg(gs_class, "1C")
    assert seg.status == "partial"
    assert seg.provenance == "resolved_from_section_anchor"
    assert seg.needs_review is True
    assert seg.text_sha256
    body = gs_class.text_of("1C")
    # anchored at the quoted section's own page-top heading inside Item 7
    assert body.startswith("Cybersecurity Program")
    assert "page-token-87" in body
    assert "page-token-88" in body  # continuation page belongs to the section
    assert any("in-document pointer" in w for w in seg.warnings)


def test_intra_doc_pointer_span_ends_before_next_section(gs_class):
    body = gs_class.text_of("1C")
    assert "Model Risk Review" not in body
    assert "page-token-89" not in body
    # the page-break furniture before the sibling heading is trimmed
    assert body.rstrip().endswith("reviewed annually.")


def test_intra_doc_pointer_stays_inside_referenced_item(gs_class):
    seg = _seg(gs_class, "1C")
    item7 = _seg(gs_class, "7")
    assert item7.start_offset <= seg.start_offset < seg.end_offset <= item7.end_offset


def test_parent_chapter_quote_stays_pointer(gs_class):
    # Item 7A quotes the PARENT chapter title ("Risk Management"): that page-top
    # section is the chapter intro, not the item's market-risk content — the
    # topic guard must keep the stub an honest pointer.
    seg = _seg(gs_class, "7A")
    assert seg.status == "incorporated_by_reference"
    assert seg.provenance == "offset_exact_span"


def test_proxy_pointer_stays_pointer(gs_class):
    seg = _seg(gs_class, "11")
    assert seg.status == "incorporated_by_reference"
    assert seg.provenance == "offset_exact_span"


def test_kill_switch_disables_intra_doc_resolution(monkeypatch):
    monkeypatch.setenv("SEC_WRAPPER_SECTION_ANCHOR", "0")
    result = extract_from_html(_gs_class_html(), "gs-class-killswitch")
    seg = _seg(result, "1C")
    assert seg.status == "incorporated_by_reference"
    assert seg.provenance == "offset_exact_span"


# --- JPM class: page-window snapped to the item's own section ----------------
def _jpm_class_html() -> str:
    body = FILLER * 15
    fin_sections = {
        3: "OPERATIONAL RISK MANAGEMENT",
        5: "Cybersecurity",              # the item's own section, mid-window
        6: "COMPLIANCE RISK MANAGEMENT",  # sibling — ends the snapped span
    }
    fin = ["<div>FINANCIAL SECTION</div>"]
    for pg in range(1, 11):
        fin.append(f"<div>{BANNER}</div><div>{pg}</div>")
        if pg in fin_sections:
            fin.append(f"<div>{fin_sections[pg]}</div>")
        fin.append(f"<p>page-token-{pg} " + FILLER * 18 + "</p>")
    return "<html><body>" + "".join([
        _item("1", "Business", body),
        _item("1A", "Risk Factors", "Risks and uncertainties. " + body),
        _item("1C", "Cybersecurity",
              "Refer to the Operational Risk Management section of the annual "
              "report on pages 3-6 for a discussion of cybersecurity risk."),
        _item("2", "Properties", body),
        _item("5", "Market for Registrant's Common Equity", body),
        _item("7", "Management's Discussion and Analysis of Financial Condition "
                   "and Results of Operations", body),
        _item("9A", "Controls and Procedures", body),
        _item("10", "Directors, Executive Officers and Corporate Governance", body),
        _item("12", "Security Ownership of Certain Beneficial Owners", body),
        _item("15", "Exhibits, Financial Statement Schedules",
              "The following exhibits are filed herewith: " + FILLER * 10),
        "".join(fin),
    ]) + "</body></html>"


@pytest.fixture(scope="module")
def jpm_class():
    return extract_from_html(_jpm_class_html(), "jpm-class-fixture")


def test_page_window_snapped_to_item_section(jpm_class):
    seg = _seg(jpm_class, "1C")
    assert seg.status == "partial"
    assert seg.provenance == "resolved_from_page_anchor"
    body = jpm_class.text_of("1C")
    # the deferred pages BEGIN at the parent section; the span snaps to the
    # item's own canonical-title-matching section printed at a later page top
    assert body.startswith("Cybersecurity")
    assert "page-token-5" in body
    assert "OPERATIONAL RISK MANAGEMENT" not in body
    assert "page-token-3" not in body
    assert any("snapped to the item's own page-top section heading" in w
               for w in seg.warnings)


def test_snapped_window_ends_before_sibling_section(jpm_class):
    body = jpm_class.text_of("1C")
    assert "COMPLIANCE RISK MANAGEMENT" not in body
    assert "page-token-6" not in body
    assert body.rstrip().endswith("reviewed annually.")


def test_kill_switch_disables_window_snapping(monkeypatch):
    monkeypatch.setenv("SEC_WRAPPER_SECTION_ANCHOR", "0")
    result = extract_from_html(_jpm_class_html(), "jpm-class-killswitch")
    seg = _seg(result, "1C")
    # still page-anchor resolved (that path predates the snap), just unsnapped
    assert seg.provenance == "resolved_from_page_anchor"
    body = result.text_of("1C")
    assert "OPERATIONAL RISK MANAGEMENT" in body
