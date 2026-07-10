"""End-to-end extraction tests against synthetic fixtures with golden labels.

The fixtures are ground truth by construction (tools/gen_fixtures.py):
alpha = anchored TOC with page numbers (classic TOC trap), reserved item 6,
incorporated-by-reference Part III; beta = non-anchored TOC with dotted
leaders, combined 'Items 1 and 2', uppercase <center> headings, entities.
"""

import json
from pathlib import Path

import pytest

from observability_core import sha256_text
from sec_core.pipeline import extract_from_html

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "data" / "sec_eval" / "fixtures"
LABELS = ROOT / "data" / "golden_labels"


def load(filing_id: str):
    raw = (FIXTURES / f"{filing_id}.html").read_text(encoding="utf-8")
    labels = json.loads((LABELS / f"{filing_id}.json").read_text(encoding="utf-8"))
    return extract_from_html(raw, filing_id), labels


@pytest.fixture(scope="module")
def alpha():
    return load("alpha_10k")


@pytest.fixture(scope="module")
def beta():
    return load("beta_10k")


def assert_matches_labels(result, labels):
    for code, expected in labels["items"].items():
        seg = result.segment(code)
        assert seg.status == expected["status"], (
            f"item {code}: status {seg.status!r} != expected {expected['status']!r}; "
            f"warnings={seg.warnings}"
        )
        if "body_contains" in expected:
            assert expected["body_contains"] in result.text_of(code), (
                f"item {code}: expected body text not found in extracted span"
            )
        if "body_excludes" in expected:
            assert expected["body_excludes"] not in result.text_of(code), (
                f"item {code}: forbidden text leaked into extracted span"
            )


def test_alpha_statuses_match_golden_labels(alpha):
    result, labels = alpha
    assert_matches_labels(result, labels)


def test_beta_statuses_match_golden_labels(beta):
    result, labels = beta
    assert_matches_labels(result, labels)


def test_alpha_toc_candidates_rejected_with_reasons(alpha):
    result, _ = alpha
    rejected = [c for c in result.candidates if c.toc_rejected]
    assert len(rejected) >= 10  # the anchored TOC block
    for c in rejected:
        assert c.toc_reasons, f"TOC rejection without explanation: {c.heading_text}"
    assert any("anchor link" in r for c in rejected for r in c.toc_reasons)


def test_beta_non_anchor_toc_rejected(beta):
    result, _ = beta
    rejected = [c for c in result.candidates if c.toc_rejected]
    assert len(rejected) >= 4  # dotted-leader INDEX block has no anchors
    for c in rejected:
        assert c.toc_reasons


def test_extracted_text_is_source_exact_span(alpha):
    result, _ = alpha
    for seg in result.segments:
        if seg.status in ("missing", "reserved") and seg.text_sha256 == "":
            continue
        span = result.doc.slice(seg.start_offset, seg.end_offset)
        assert sha256_text(span) == seg.text_sha256


def test_offsets_map_back_to_raw_html(alpha):
    result, _ = alpha
    seg = result.segment("7")
    raw_start = result.doc.raw_offset(seg.start_offset)
    # the raw HTML at the mapped offset must be the heading's first character
    assert result.doc.raw_html[raw_start] == result.doc.text[seg.start_offset]
    assert "Item 7" in result.doc.raw_html[raw_start : raw_start + 40]


def test_script_content_never_extracted(alpha):
    result, _ = alpha
    assert "must never be extracted" not in result.doc.text


def test_combined_items_share_span_with_warning(beta):
    result, _ = beta
    s1, s2 = result.segment("1"), result.segment("2")
    assert (s1.start_offset, s1.end_offset) == (s2.start_offset, s2.end_offset)
    assert any("combined" in w for w in s1.warnings)
    assert any("combined" in w for w in s2.warnings)


def test_confidence_components_are_explained(alpha):
    result, _ = alpha
    breakdown = result.confidence["1A"]
    names = {c.name for c in breakdown.components}
    assert names == set(breakdown.COMPONENT_NAMES)
    assert all(c.reason for c in breakdown.components)
    assert result.segment("1A").confidence == pytest.approx(breakdown.total)


def test_pass_items_have_heading_evidence(alpha):
    result, _ = alpha
    for seg in result.segments:
        if seg.status == "pass":
            kinds = {e.kind for e in seg.evidence}
            assert "heading_match" in kinds
            heading_ev = next(e for e in seg.evidence if e.kind == "heading_match")
            assert heading_ev.quote == seg.extracted_heading


def test_non_10k_document_yields_no_false_items():
    result = extract_from_html("<html><body><p>Quarterly newsletter.</p></body></html>", "junk")
    assert all(s.status in ("missing", "reserved") for s in result.segments)
    assert result.warnings


def test_scanned_pdf_is_code_enforced_unsupported():
    result = extract_from_html("%PDF-1.7\n%\xe2\xe3\xcf\xd3 binary garbage", "scanned")
    assert result.filing_class == "unsupported_scanned_or_binary"
    assert result.segments == []
    assert any("OCR" in w for w in result.warnings)
