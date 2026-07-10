"""Third-engine (edgartools) triangulation tests — sec_core.third_engine.

Comparison logic is tested with controlled engine outputs (no network, no
edgartools needed); one smoke test exercises the real edgartools parser
offline on the synthetic alpha fixture.
"""

from pathlib import Path

import pytest

from sec_core.pipeline import extract_from_html
from sec_core.third_engine import (
    COMPONENT_NAME,
    apply_triangulation,
    compare_item,
    extract_items_edgartools,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "data" / "sec_eval" / "fixtures"


@pytest.fixture(scope="module")
def alpha():
    raw = (FIXTURES / "alpha_10k.html").read_text(encoding="utf-8")
    return raw, extract_from_html(raw, "alpha_10k")


# --- compare_item unit behaviour -------------------------------------------

PROSE = ("The company designs manufactures and markets consumer devices and sells "
         "related services worldwide across geographic segments. " * 20)


def test_identical_text_agrees():
    cmp = compare_item("1", PROSE, PROSE, "pass")
    assert cmp.verdict == "agree"


def test_whitespace_and_punctuation_noise_still_agrees():
    noisy = PROSE.replace(" ", " \n ").replace("company", "company’")
    cmp = compare_item("1", PROSE, noisy, "pass")
    assert cmp.verdict == "agree"


def test_different_content_disagrees():
    other = ("Legal proceedings against the registrant include patent disputes "
             "and antitrust investigations in several jurisdictions. " * 20)
    cmp = compare_item("3", PROSE, other, "pass")
    assert cmp.verdict == "disagree"
    assert "content mismatch" in cmp.detail


def test_gross_length_mismatch_disagrees():
    cmp = compare_item("7", PROSE[:200], PROSE * 5, "pass")
    assert cmp.verdict == "disagree"
    assert "boundary mismatch" in cmp.detail or "content mismatch" in cmp.detail


def test_engine_missing_item_is_unavailable_not_our_failure():
    cmp = compare_item("1A", PROSE, "", "pass")
    assert cmp.verdict == "engine_unavailable"


def test_we_missed_an_item_the_engine_found():
    cmp = compare_item("9C", "", PROSE, "missing")
    assert cmp.verdict == "disagree"
    assert "missed item" in cmp.detail


def test_both_empty_agree():
    assert compare_item("16", "", "", "missing").verdict == "agree"


def test_reserved_item_with_short_engine_stub_agrees():
    assert compare_item("6", "", "Item 6. [Reserved]", "reserved").verdict == "agree"


def test_tiny_item_with_engine_page_furniture_agrees():
    # edgartools keeps running headers/page numbers our engine trims
    ours = "Item 4. Mine Safety Disclosures\nNot applicable."
    theirs = "Item 4. Mine Safety Disclosures\n\nNot applicable.\n\nApple Inc. | 2025 Form 10-K | 20"
    cmp = compare_item("4", ours, theirs, "pass")
    assert cmp.verdict == "agree"


def test_tiny_item_with_different_answer_disagrees():
    ours = "Item 4. Mine Safety Disclosures\nNot applicable."
    theirs = ("Item 4. Mine Safety Disclosures\nThe registrant operates several mines and "
              "reports citations under the Mine Act in Exhibit 95.")
    cmp = compare_item("4", ours, theirs, "pass")
    assert cmp.verdict == "disagree"


def test_combined_span_containing_engine_body_agrees():
    combined_span = PROSE + " Properties consist of owned and leased facilities. " * 10
    cmp = compare_item("1", combined_span, PROSE, "partial", combined=True)
    assert cmp.verdict == "agree"


# --- apply_triangulation writes back onto segments --------------------------

def test_agreeing_engine_output_leaves_confidence_untouched(alpha):
    raw, _ = alpha
    result = extract_from_html(raw, "alpha_10k")
    engine_items = {s.item_code: result.text_of(s.item_code)
                    for s in result.segments if s.end_offset > s.start_offset}
    before = {s.item_code: s.confidence for s in result.segments}
    comparisons = apply_triangulation(result, engine_items)
    assert all(c.verdict != "disagree" for c in comparisons)
    for seg in result.segments:
        assert seg.engine_check.startswith(("agree", "engine_unavailable"))
        assert seg.confidence == before[seg.item_code]


def test_disagreement_deducts_confidence_and_flags_review(alpha):
    raw, _ = alpha
    result = extract_from_html(raw, "alpha_10k")
    seg = result.segment("1A")
    assert seg.status == "pass" and not seg.needs_review
    before = seg.confidence
    engine_items = {"1A": "Completely unrelated text about mine safety disclosures "
                          "and executive compensation tables. " * 30}
    apply_triangulation(result, engine_items)
    assert seg.engine_check.startswith("disagree")
    assert seg.needs_review
    assert seg.confidence < before
    breakdown = result.confidence["1A"]
    comp = next(c for c in breakdown.components if c.name == COMPONENT_NAME)
    assert comp.score == 0.0 and comp.reason
    assert seg.confidence == pytest.approx(breakdown.total)


def test_triangulation_is_idempotent_on_rerun(alpha):
    raw, _ = alpha
    result = extract_from_html(raw, "alpha_10k")
    engine_items = {"1A": "Completely unrelated text about mine safety. " * 40}
    apply_triangulation(result, engine_items)
    once = result.segment("1A").confidence
    apply_triangulation(result, engine_items)
    assert result.segment("1A").confidence == once
    breakdown = result.confidence["1A"]
    assert sum(1 for c in breakdown.components if c.name == COMPONENT_NAME) == 1


def test_unparseable_filing_marks_engine_unavailable_without_penalty(alpha):
    raw, _ = alpha
    result = extract_from_html(raw, "alpha_10k")
    before = {s.item_code: (s.confidence, s.needs_review) for s in result.segments}
    comparisons = apply_triangulation(result, None)
    assert all(c.verdict == "engine_unavailable" for c in comparisons)
    for seg in result.segments:
        assert seg.engine_check.startswith("engine_unavailable")
        assert (seg.confidence, seg.needs_review) == before[seg.item_code]


# --- real edgartools, offline smoke -----------------------------------------

def test_edgartools_offline_extraction_smoke(alpha):
    raw, _ = alpha
    items = extract_items_edgartools(raw)
    # a dict of item texts or None (engine_unavailable) — never an exception
    assert items is None or (isinstance(items, dict) and all(
        isinstance(k, str) and isinstance(v, str) and v.strip() for k, v in items.items()))
