"""Extraction end-boundary fix (NTU boundary-bleed, giants_task2.md rerun):

the resolver's end offset used to be "start of the next DETECTED item", so one
missed intermediate heading made a span run through the next item's whole
body. Two extraction changes are under test:

1. scoped next-item rescan (boundary._rescan_end_cut): each span's own body is
   rescanned for a later EXPECTED item's heading — tier 1 uses the detected
   candidates (overshoot-guard plausibility rules), tier 2 a looser
   line-anchored shape (optional 'Item' prefix + code + the item's
   canonical/legacy title) for headings the detectors cannot see
   (e.g. '9B. OTHER INFORMATION' without the word 'Item');
2. terminal-item tail cut: the last detected item ends at the SIGNATURES
   block / signature-page preamble instead of EOF.

Both can only SHORTEN a span, and the capture-first coverage invariant holds:
whatever a cut trims off an item lands in the next item or an unclassified
gap — coverage.partition_document still tiles the whole document.
"""

from sec_core.boundary import _rescan_title_ok
from sec_core.coverage import partition_document
from sec_core.pipeline import extract_from_html

BODY = ("The company operates manufacturing facilities and distribution networks "
        "across several regions under long-term agreements reviewed annually. ")


def para(text: str) -> str:
    return f"<p>{text}</p>"


def bold(text: str) -> str:
    return f"<p><b>{text}</b></p>"


# --- tier 2: heading without the word 'Item' -----------------------------------

def _tier2_result():
    html = "".join([
        bold("Item 9A. Controls and Procedures"),
        para(BODY * 10),
        para("9B. OTHER INFORMATION"),  # no 'Item' word -> invisible to detectors
        para(BODY * 5),
        bold("Item 10. Directors, Executive Officers and Corporate Governance"),
        para(BODY * 5),
    ])
    return extract_from_html(html, "tier2-fixture")


class TestLooserNextItemRescan:
    def test_span_is_cut_at_the_undetected_9b_heading(self):
        result = _tier2_result()
        seg = result.segment("9A")
        heading_at = result.doc.text.find("9B. OTHER INFORMATION")
        assert heading_at > 0
        assert seg.end_offset <= heading_at  # cut there (± furniture trim)
        assert any("end rescan: span cut at inferred item 9B heading" in w
                   for w in seg.warnings)

    def test_cut_only_shortens_and_own_content_is_kept(self):
        result = _tier2_result()
        seg = result.segment("9A")
        old_end = result.segment("10").start_offset  # pre-fix end
        assert seg.end_offset < old_end
        # recall on the item's own body stays 1.0
        assert result.text_of("9A").count("manufacturing facilities") == 10

    def test_trimmed_tail_is_not_lost_coverage_invariant(self):
        # capture-first: the trimmed region must still be reachable — it
        # becomes an unclassified gap block in the document partition
        result = _tier2_result()
        blocks = partition_document(result.doc.text, result.segments)
        assert blocks[0].start == 0 and blocks[-1].end == len(result.doc.text)
        for a, b in zip(blocks, blocks[1:]):
            assert a.end == b.start  # no holes, no overlap
        heading_at = result.doc.text.find("9B. OTHER INFORMATION")
        owner = next(blk for blk in blocks if blk.start <= heading_at < blk.end)
        assert owner.code == ""  # unclassified gap, surfaced by compute_gaps

    def test_legacy_title_variant_is_recognized(self):
        # pre-2011 Item 6 'Selected Financial Data' (canonical is '[Reserved]')
        html = "".join([
            bold("Item 5. Market for Registrant's Common Equity, Related "
                 "Stockholder Matters and Issuer Purchases of Equity Securities"),
            para(BODY * 10),
            para("6. SELECTED FINANCIAL DATA"),  # undetectable legacy heading
            para(BODY * 5),
            bold("Item 7. Management's Discussion and Analysis of Financial "
                 "Condition and Results of Operations"),
            para(BODY * 5),
        ])
        result = extract_from_html(html, "legacy-title-fixture")
        seg = result.segment("5")
        heading_at = result.doc.text.find("6. SELECTED FINANCIAL DATA")
        assert seg.end_offset <= heading_at
        assert any("end rescan: span cut at inferred item 6 heading" in w
                   for w in seg.warnings)

    def test_numbered_list_line_starting_with_a_title_never_cuts(self):
        # '3. Legal Proceedings are described...' is a list line, not a heading
        html = "".join([
            bold("Item 2. Properties"),
            para(BODY * 10),
            para("3. Legal Proceedings are described in Note 12 to the "
                 "consolidated financial statements."),
            para(BODY * 5),
            bold("Item 3. Legal Proceedings"),
            para(BODY * 5),
        ])
        result = extract_from_html(html, "list-line-fixture")
        seg = result.segment("2")
        assert seg.end_offset >= result.doc.text.find("3. Legal Proceedings are")
        assert not any("end rescan" in w for w in seg.warnings)

    def test_toc_anchor_line_inside_body_never_cuts(self):
        # mini-index anchor line for a later item inside item 1's body — the
        # rescan must respect the TOC plausibility rules and leave it alone
        html = "".join([
            bold("Item 1. Business"),
            para(BODY * 10),
            '<p><a href="#prop">Item 2. Properties</a></p>',
            para(BODY * 10),
            bold("Item 2. Properties"),
            para(BODY * 5),
        ])
        result = extract_from_html(html, "toc-anchor-fixture")
        seg = result.segment("1")
        assert not any("end rescan" in w for w in seg.warnings)
        assert seg.end_offset >= result.doc.text.rfind("Item 2. Properties")


class TestRescanTitleGate:
    def test_exact_and_near_exact_titles_pass(self):
        assert _rescan_title_ok("9B", "OTHER INFORMATION")
        assert _rescan_title_ok("6", "Selected Financial Data")
        assert _rescan_title_ok(
            "15", "Exhibits, Financial Statement Schedules, and Reports on Form 8-K")

    def test_prose_and_list_lines_fail(self):
        assert not _rescan_title_ok(
            "3", "Legal Proceedings are described in Note 12.")
        assert not _rescan_title_ok(
            "2", "Properties acquired during the year are described above.")
        assert not _rescan_title_ok("9B", "")
        assert not _rescan_title_ok("10", "May 2013 board meeting minutes")


# --- terminal item: signature-page tail cut -------------------------------------

class TestTerminalSignaturesCut:
    def test_pursuant_preamble_cuts_the_last_item_without_a_bare_signatures_line(self):
        html = "".join([
            para("ANNUAL REPORT PURSUANT TO SECTION 13 OR 15(d) OF THE "
                 "SECURITIES EXCHANGE ACT OF 1934"),  # cover page — must NOT cut
            bold("Item 14. Principal Accountant Fees and Services"),
            para(BODY * 3),
            bold("Item 15. Exhibits, Financial Statement Schedules"),
            para(BODY * 5),
            para("Pursuant to the requirements of Section 13 or 15(d) of the "
                 "Securities Exchange Act of 1934, the registrant has duly caused "
                 "this report to be signed on its behalf by the undersigned, "
                 "thereunto duly authorized."),
            para("Chief Executive Officer"),
        ])
        result = extract_from_html(html, "signature-preamble-fixture")
        seg = result.segment("15")
        sig_at = result.doc.text.find("Pursuant to the requirements of Section 13")
        assert seg.start_offset < sig_at  # cover-page phrasing did not cut
        assert seg.end_offset <= sig_at
        assert result.text_of("15").count("manufacturing facilities") == 5  # own body intact

    def test_bare_signatures_heading_still_cuts(self):
        html = "".join([
            bold("Item 15. Exhibits, Financial Statement Schedules"),
            para(BODY * 5),
            para("SIGNATURES"),
            para(BODY),
        ])
        result = extract_from_html(html, "signatures-fixture")
        seg = result.segment("15")
        assert seg.end_offset <= result.doc.text.find("SIGNATURES")
