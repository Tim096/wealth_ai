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


# --- engine-blind class (P0-5): items 10-16 + TOC-junk engine text ----------

TOC_JUNK = ("ITEM 1.BUSINESS6Introduction6General Development8 "
            "ITEM 1A.RISK FACTORS21 ITEM 2.PROPERTIES44 ITEM 3.LEGAL PROCEEDINGS45 "
            "ITEM 7.MANAGEMENTS DISCUSSION AND ANALYSIS52 ITEM 8.FINANCIAL STATEMENTS60 "
            "ITEM 15.EXHIBITS110 ITEM 16.FORM 10-K SUMMARY112")


# Verbatim edgartools 5.42.0 output for NEM item 16 (FG-SEC-006): Item 1 TOC
# lines with page numbers glued to headings — only ONE item ref, so the
# multi-ref density signal alone would miss it (integration-gate regression).
NEM_ITEM16_JUNK = ("ITEM\xa01.BUSINESS6Introduction6Segment Information6Products6"
                   "Competition9Licenses and Concessions9Condition of Physical Assets "
                   "and Insurance9Environmental, Social and Governance10Risk Factor "
                   "Summary13Forward-Looking Statements15Available Information17")


def test_real_nem_item16_single_ref_glued_toc_is_engine_suspect():
    cmp = compare_item("16", "Item 16. Form 10-K Summary. None.", NEM_ITEM16_JUNK,
                       "pass", engine_version="5.42.0")
    assert cmp.verdict == "engine_suspect"


def test_item16_toc_junk_becomes_engine_suspect_not_disagree():
    # FG-SEC-006 class: our span is correct ("None."), edgartools' item 16
    # section holds Item 1 TOC lines. Pinned 5.42.x -> engine_suspect.
    cmp = compare_item("16", "Item 16. Form 10-K Summary. None.", TOC_JUNK, "pass",
                       engine_version="5.42.0")
    assert cmp.verdict == "engine_suspect"
    assert "FG-SEC-006" in cmp.detail and "9C" in cmp.detail


def test_engine_suspect_gate_disabled_on_unpinned_version():
    # upgrade => down-weighting rationale must be re-verified, gate falls back
    cmp = compare_item("16", "Item 16. Form 10-K Summary. None.", TOC_JUNK, "pass",
                       engine_version="6.1.0")
    assert cmp.verdict == "disagree"


def test_blind_class_does_not_cover_items_below_10():
    cmp = compare_item("3", "Item 3. Legal Proceedings. None pending.", TOC_JUNK, "pass",
                       engine_version="5.42.0")
    assert cmp.verdict == "disagree"


def test_item16_body_text_mismatch_still_disagrees():
    # NVDA/WMT class: engine text is misattributed BODY prose, not TOC junk —
    # the narrow gate leaves this a real disagreement (needs_review path).
    cmp = compare_item("16", "Item 16. Form 10-K Summary. None.", PROSE, "pass",
                       engine_version="5.42.0")
    assert cmp.verdict == "disagree"


def test_missed_item_with_toc_junk_engine_text_is_suspect():
    cmp = compare_item("14", "", TOC_JUNK, "missing", engine_version="5.42.0")
    assert cmp.verdict == "engine_suspect"


def test_prose_with_sparse_item_cross_references_is_not_toc_junk():
    # "see Item 7A" style cross-references must not trigger the junk heuristic
    body = PROSE + " See Item 7A for market risk and Item 8 and Item 15 for statements. "
    cmp = compare_item("16", "Item 16. None.", body, "pass", engine_version="5.42.0")
    assert cmp.verdict == "disagree"


# --- source-aware corpus mode (P0-1): table-stripped teacher votes ----------

TABLE_WORDS = " revenue 1234 5678 cost 910 1112 margin 1314 1516 total 1718 1920 " * 200


def test_corpus_table_stripped_item8_agrees_where_default_mode_disagrees():
    ours = PROSE + TABLE_WORDS          # our span keeps the tables
    theirs = PROSE                      # corpus built with remove_tables=True
    assert compare_item("8", ours, theirs, "pass", source="corpus").verdict == "agree"
    # the same texts under the default boundary-aware mode are a mismatch —
    # exactly the systematic Item 8 false disagree the corpus mode removes
    assert compare_item("8", ours, theirs, "pass").verdict == "disagree"


def test_corpus_mode_still_catches_our_truncation():
    ours = " ".join(PROSE.split()[:40])
    cmp = compare_item("7", ours, PROSE, "pass", source="corpus")
    assert cmp.verdict == "disagree"
    assert "corpus" in cmp.detail


def test_corpus_empty_section_is_no_signal_not_disagreement():
    # guardrail g2: an empty corpus section must never count against our span
    cmp = compare_item("15", PROSE, "", "pass", source="corpus")
    assert cmp.verdict == "engine_unavailable"


def test_corpus_source_never_uses_edgartools_blind_gate():
    cmp = compare_item("16", "Item 16. None.", TOC_JUNK, "pass",
                       source="corpus", engine_version="5.42.0")
    assert cmp.verdict == "disagree"


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


def test_engine_suspect_records_warning_without_penalty(alpha):
    # pinned edgartools 5.42.0 is an installed dependency, so the auto-detected
    # version activates the blind-class gate inside apply_triangulation
    raw, _ = alpha
    result = extract_from_html(raw, "alpha_10k")
    seg = result.segment("14")
    before = (seg.confidence, seg.needs_review)
    comparisons = apply_triangulation(result, {"14": TOC_JUNK})
    cmp = next(c for c in comparisons if c.item_code == "14")
    assert cmp.verdict == "engine_suspect"
    assert seg.engine_check.startswith("engine_suspect")
    assert (seg.confidence, seg.needs_review) == before
    assert any("engine-blind class" in w for w in seg.warnings)
    breakdown = result.confidence.get("14")
    if breakdown is not None:
        assert not any(c.name == COMPONENT_NAME for c in breakdown.components)


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


# --- 2-of-N voting (P0-7): extra engines ------------------------------------

JUNK = "Completely unrelated text about mine safety disclosures. " * 40


def test_outvoted_dissent_is_warning_not_penalty(alpha):
    # edgartools corroborates our 1A span (2 votes for it); datamule dissents
    # -> outvoted: no deduction, no needs_review, aggregate stays agree
    raw, _ = alpha
    result = extract_from_html(raw, "alpha_10k")
    seg = result.segment("1A")
    before = seg.confidence
    engine_items = {s.item_code: result.text_of(s.item_code)
                    for s in result.segments if s.end_offset > s.start_offset}
    apply_triangulation(result, engine_items, {"datamule": {"1A": JUNK}})
    assert seg.engine_check.startswith("agree")
    assert "datamule=disagree" in seg.engine_check
    assert seg.confidence == before and not seg.needs_review
    assert any("outvoted 2-of-N" in w for w in seg.warnings)
    breakdown = result.confidence.get("1A")
    assert not any(c.name == COMPONENT_NAME for c in breakdown.components)


def test_uncorroborated_multi_engine_disagree_penalises_once(alpha):
    raw, _ = alpha
    result = extract_from_html(raw, "alpha_10k")
    seg = result.segment("1A")
    before = seg.confidence
    apply_triangulation(result, {"1A": JUNK}, {"datamule": {"1A": JUNK}})
    assert seg.engine_check.startswith("disagree")
    assert seg.needs_review and seg.confidence < before
    comps = [c for c in result.confidence["1A"].components if c.name == COMPONENT_NAME]
    assert len(comps) == 1
    assert "edgartools" in comps[0].reason and "datamule" in comps[0].reason


def test_extra_engine_unavailable_is_neutral(alpha):
    raw, _ = alpha
    result = extract_from_html(raw, "alpha_10k")
    engine_items = {s.item_code: result.text_of(s.item_code)
                    for s in result.segments if s.end_offset > s.start_offset}
    before = {s.item_code: (s.confidence, s.needs_review) for s in result.segments}
    comparisons = apply_triangulation(result, engine_items, {"edgar_crawler": None})
    assert any(c.source == "edgar_crawler" and c.verdict == "engine_unavailable"
               for c in comparisons)
    for seg in result.segments:
        assert (seg.confidence, seg.needs_review) == before[seg.item_code]


def test_extra_engine_agree_rescues_edgartools_unavailable_filing(alpha):
    # edgartools cannot parse the filing but datamule corroborates 1A ->
    # the item aggregates to agree, not engine_unavailable
    raw, _ = alpha
    result = extract_from_html(raw, "alpha_10k")
    apply_triangulation(result, None, {"datamule": {"1A": result.text_of("1A")}})
    assert result.segment("1A").engine_check.startswith("agree")
    assert not result.segment("1A").needs_review


def test_comparisons_carry_their_source(alpha):
    raw, _ = alpha
    result = extract_from_html(raw, "alpha_10k")
    comparisons = apply_triangulation(result, None, {"datamule": None})
    assert {c.source for c in comparisons} == {"edgartools", "datamule"}


# --- real edgartools, offline smoke -----------------------------------------

def test_edgartools_offline_extraction_smoke(alpha):
    raw, _ = alpha
    items = extract_items_edgartools(raw)
    # a dict of item texts or None (engine_unavailable) — never an exception
    assert items is None or (isinstance(items, dict) and all(
        isinstance(k, str) and isinstance(v, str) and v.strip() for k, v in items.items()))
