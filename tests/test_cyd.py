"""CYD iXBRL ground-truth tests — sec_core.cyd.

The CYD block-tags are the only SEC-mandated machine-readable item span
(Item 1C, fiscal years ending >= 2024-12-15). These tests exercise the tag
scanner, continuation chains, ix:hidden exclusion, raw->normalized offset
mapping and the agree/disagree/unavailable verdicts — all offline on
synthetic HTML (no network, no real filing needed).
"""

import pytest

from sec_core.cyd import (
    assemble_raw_intervals,
    certify_item1c,
    cyd_prefixes,
    parse_cyd_fragments,
    raw_to_norm,
)
from sec_core.items import ItemSegment
from sec_core.normalize import normalize_html
from sec_core.pipeline import ExtractionResult

CYBER_TEXT = ("We maintain a cybersecurity risk management program designed to "
              "identify assess and manage material risks from cybersecurity threats. ")
BOARD_TEXT = ("Our board of directors oversees cybersecurity risk through its audit "
              "committee which receives quarterly briefings from management. ")

FILING = f"""<html><body>
<div>Item 1B. Unresolved Staff Comments</div>
<p>None. This filler paragraph exists so the stub item has some body text.</p>
<div>Item 1C. Cybersecurity</div>
<p><ix:nonNumeric contextRef="c-1" id="f-1" continuedAt="f-1-1" escape="true"
 name="cyd:CybersecurityRiskManagementProcessesForAssessingIdentifyingAndManagingThreatsTextBlock"
>{CYBER_TEXT * 4}<ix:nonNumeric contextRef="c-1" id="f-2"
 name="cyd:CybersecurityRiskManagementProcessesIntegratedFlag">true</ix:nonNumeric></ix:nonNumeric></p>
<p><ix:continuation id="f-1-1">{BOARD_TEXT * 4}</ix:continuation></p>
<div>Item 2. Properties</div>
<p>Our principal properties consist of offices and data centers worldwide.</p>
<ix:hidden><ix:nonNumeric contextRef="c-1" id="f-9"
 name="cyd:CybersecurityRiskBoardOfDirectorsOversightTextBlock">hidden duplicate</ix:nonNumeric></ix:hidden>
</body></html>"""


def _segment(doc, start: int, end: int, status: str = "pass") -> ItemSegment:
    return ItemSegment(
        filing_id="synthetic", item_code="1C", canonical_title="Cybersecurity",
        extracted_heading="Item 1C. Cybersecurity", start_offset=start, end_offset=end,
        text_sha256="", status=status, confidence=0.9)


def _result(doc, seg: ItemSegment) -> ExtractionResult:
    return ExtractionResult(filing_id="synthetic", segments=[seg], confidence={},
                            doc=doc, candidates=[])


@pytest.fixture(scope="module")
def doc():
    return normalize_html(FILING)


@pytest.fixture(scope="module")
def span_1c(doc):
    """Normalized offsets of the true Item 1C section (heading -> Item 2)."""
    start = doc.text.find("Item 1C. Cybersecurity")
    end = doc.text.find("Item 2. Properties")
    assert 0 < start < end
    return start, end


# --- scanner ----------------------------------------------------------------

def test_scanner_finds_textblocks_not_flags():
    blocks, conts = parse_cyd_fragments(FILING)
    names = {b.name.split(":")[1] for b in blocks}
    assert "CybersecurityRiskManagementProcessesForAssessingIdentifyingAndManagingThreatsTextBlock" in names
    assert "CybersecurityRiskBoardOfDirectorsOversightTextBlock" in names
    assert not any("Flag" in n for n in names)  # boolean flags are not span tags
    assert "f-1-1" in conts


def test_scanner_marks_hidden_fragments():
    blocks, _ = parse_cyd_fragments(FILING)
    hidden = [b for b in blocks if b.hidden]
    assert len(hidden) == 1 and hidden[0].frag_id == "f-9"


def test_continuation_chain_and_hidden_exclusion():
    blocks, conts = parse_cyd_fragments(FILING)
    intervals, n_fragments, n_hidden = assemble_raw_intervals(blocks, conts)
    assert n_hidden == 1
    assert n_fragments == 3  # main block + continuation + hidden block
    # the visible intervals must contain both the main text and the continuation
    covered = " ".join(FILING[s:e] for s, e in intervals)
    assert CYBER_TEXT[:40] in covered and BOARD_TEXT[:40] in covered
    assert "hidden duplicate" not in covered


def test_prefix_detection_nonstandard():
    html = ('<html xmlns:cyber="http://xbrl.sec.gov/cyd/2024"><body>'
            '<ix:nonNumeric name="cyber:CybersecurityRiskRoleOfManagementTextBlock" id="a">'
            'management role text</ix:nonNumeric></body></html>')
    assert "cyber" in cyd_prefixes(html)
    blocks, _ = parse_cyd_fragments(html)
    assert len(blocks) == 1


def test_raw_to_norm_maps_into_document_text(doc):
    blocks, conts = parse_cyd_fragments(FILING)
    intervals, _, _ = assemble_raw_intervals(blocks, conts)
    s, e = intervals[0]
    ns, ne = raw_to_norm(doc, s), raw_to_norm(doc, e)
    assert doc.text[ns:ne].startswith("We maintain a cybersecurity")


# --- certify_item1c verdicts -------------------------------------------------

def test_agree_when_segment_covers_official_span(doc, span_1c):
    seg = _segment(doc, *span_1c)
    chk = certify_item1c(_result(doc, seg), FILING, report_date="2025-12-31")
    assert chk.verdict == "agree"
    assert chk.mandatory is True
    assert chk.coverage == 1.0
    assert 0 < chk.containment < 1  # heading is legitimately untagged
    assert seg.cyd_check.startswith("agree")
    assert not seg.needs_review


def test_disagree_when_segment_misses_official_span(doc):
    # a segment stuck on the Item 1B stub — official CYD span lies outside it
    start = doc.text.find("Item 1B")
    end = doc.text.find("Item 1C")
    seg = _segment(doc, start, end)
    chk = certify_item1c(_result(doc, seg), FILING, report_date="2025-12-31")
    assert chk.verdict == "disagree"
    assert chk.coverage < 0.85
    assert seg.needs_review  # disagree on a `pass` flags review
    assert seg.cyd_check.startswith("disagree")


def test_disagree_on_non_pass_does_not_flip_needs_review(doc):
    seg = _segment(doc, 0, 10, status="incorporated_by_reference")
    chk = certify_item1c(_result(doc, seg), FILING, report_date="2025-12-31")
    assert chk.verdict == "disagree"
    assert not seg.needs_review  # already an honest non-pass; recorded, not flipped


def test_unavailable_when_mandatory_but_untagged():
    html = "<html><body><div>Item 1C. Cybersecurity</div><p>text</p></body></html>"
    doc2 = normalize_html(html)
    seg = _segment(doc2, 0, len(doc2.text))
    chk = certify_item1c(_result(doc2, seg), html, report_date="2025-12-31")
    assert chk.verdict == "unavailable"
    assert chk.mandatory is True
    assert "not evidence against" in chk.detail


def test_not_required_before_mandate():
    html = "<html><body><div>Item 1C. Cybersecurity</div><p>text</p></body></html>"
    doc2 = normalize_html(html)
    seg = _segment(doc2, 0, len(doc2.text))
    chk = certify_item1c(_result(doc2, seg), html, report_date="2023-12-31")
    assert chk.verdict == "not_required"
    assert chk.mandatory is False
