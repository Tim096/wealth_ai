"""P0-1 pseudo-gold miner — offline unit tests for the §2.1 form-type→schema
mapping, guardrails g1/g2/g3/g5 and the 3-way vote tiers (tools/mine_pseudo_gold).
No network: every function under test is pure."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.mine_pseudo_gold import (  # noqa: E402
    classify_vote,
    corpus_section_to_canonical,
    era_schema,
    ksb_to_canonical,
    normalize_form,
    pick_join,
    strip_item16_tail,
)


# --- §2.1-1 form normalization: full enumeration, not startswith ------------

def test_standard_family_normalizes_to_10k():
    assert normalize_form("10-K") == ("10K", False)
    assert normalize_form("10-K405") == ("10K", False)


def test_transition_family():
    assert normalize_form("10-KT") == ("10KT", False)
    assert normalize_form("10KT405") == ("10KT", False)


def test_ksb_family_has_no_hyphen_and_is_not_missed():
    # the documented trap: startswith("10-K") misses the whole KSB family
    assert normalize_form("10KSB") == ("10KSB", False)
    assert normalize_form("10KSB40") == ("10KSB", False)
    assert normalize_form("10-KSB") == ("10KSB", False)


def test_amendment_suffix_is_a_separate_flag():
    assert normalize_form("10-K/A") == ("10K", True)
    assert normalize_form("10KSB/A") == ("10KSB", True)


def test_non_10k_forms_are_other():
    assert normalize_form("10-Q") == ("other", False)
    assert normalize_form("8-K") == ("other", False)
    assert normalize_form("") == ("other", False)


# --- §2.1-2 era schema: Release 33-8183 boundary + Item 14 title double-check

def test_pre2003_by_period_of_report():
    assert era_schema("1999-12-31") == "PRE2003"
    assert era_schema("2003-06-30") == "PRE2003"  # FYE before 2003-12-15


def test_modern_by_period_of_report():
    assert era_schema("2003-12-31") == "MODERN"  # FYE >= 2003-12-15
    assert era_schema("2010-01-31") == "MODERN"


def test_item14_heading_double_check_wins_in_boundary_years():
    assert era_schema("2003-12-31", "Item 14. Exhibits, Financial Statement "
                                    "Schedules and Reports on Form 8-K") == "PRE2003"
    assert era_schema("2003-06-30", "Item 14. Principal Accountant Fees "
                                    "and Services") == "MODERN"


# --- §2.1-3 canonical mapping + guardrail g2 ---------------------------------

def test_pre2003_section_14_is_canonical_15_exhibits():
    assert corpus_section_to_canonical("section_14", "PRE2003") == "15"


def test_pre2003_section_15_is_no_signal_never_fees_teacher():
    # g2: an empty/renumbered corpus section_15 must NEVER become an
    # accountant-fees disagreement vote
    assert corpus_section_to_canonical("section_15", "PRE2003") is None


def test_pre2003_items_absent_from_schema_are_no_signal():
    for key in ("section_1A", "section_1B", "section_9A", "section_9B"):
        assert corpus_section_to_canonical(key, "PRE2003") is None


def test_pre2003_7a_exists_since_fy1997():
    assert corpus_section_to_canonical("section_7A", "PRE2003") == "7A"


def test_modern_mapping_is_identity():
    assert corpus_section_to_canonical("section_14", "MODERN") == "14"
    assert corpus_section_to_canonical("section_15", "MODERN") == "15"
    assert corpus_section_to_canonical("section_1A", "MODERN") == "1A"


def test_non_section_keys_map_to_none():
    assert corpus_section_to_canonical("filename", "MODERN") is None
    assert corpus_section_to_canonical("cik", "PRE2003") is None


# --- §2.1-3 KSB shift ---------------------------------------------------------

def test_ksb_shift_mapping():
    assert ksb_to_canonical("6") == "7"    # KSB 6 = MD&A
    assert ksb_to_canonical("7") == "8"    # KSB 7 = FinStmt
    assert ksb_to_canonical("8A") == "9A"
    assert ksb_to_canonical("13") == "15"  # KSB 13 = Exhibits


def test_ksb_never_produces_canonical_6_or_7a():
    targets = {ksb_to_canonical(c) for c in
               ("1", "2", "3", "4", "5", "6", "7", "8", "8A", "8B",
                "9", "10", "11", "12", "13")}
    assert "6" not in targets and "7A" not in targets


# --- g3: 2016-2020 section_15 Item-16 tail pollution --------------------------

def test_g3_cuts_item16_tail_in_polluted_window():
    text = "Exhibit index and schedules here. Item 16. Form 10-K Summary None."
    assert strip_item16_tail(text, 2018, "section_15") == \
        "Exhibit index and schedules here. "


def test_g3_leaves_other_years_and_keys_alone():
    text = "Exhibits. Item 16. Summary."
    assert strip_item16_tail(text, 2010, "section_15") == text
    assert strip_item16_tail(text, 2018, "section_14") == text


# --- g1/g5 join ---------------------------------------------------------------

def _row(form, acc, filed, report):
    return {"form": form, "accession": acc, "filing_date": filed,
            "report_date": report, "primary_document": ""}


def test_join_single_original_matches():
    rows = [_row("10-K", "A-1", "1999-03-30", "1998-12-31"),
            _row("10-Q", "Q-1", "1998-08-10", "1998-06-30")]
    j = pick_join(rows, 1998)
    assert j["outcome"] == "matched"
    assert j["row"]["accession"] == "A-1"


def test_join_collision_resolved_by_dropping_amendment_g1():
    rows = [_row("10-K", "A-1", "1998-03-30", "1997-12-31"),
            _row("10-K/A", "A-2", "1998-06-01", "1997-12-31")]
    j = pick_join(rows, 1997)
    assert j["outcome"] == "matched"
    assert j["row"]["accession"] == "A-1"
    assert j["amendments_seen"] == 1


def test_join_amendment_only_is_hard_case_g5():
    # Rule 12b-15 allows partial restatement — /A never enters pseudo-gold
    rows = [_row("10-K/A", "A-2", "1999-06-01", "1998-12-31")]
    assert pick_join(rows, 1998)["outcome"] == "amendment_only"


def test_join_two_originals_is_ambiguous():
    rows = [_row("10-K", "A-1", "1998-03-30", "1997-12-31"),
            _row("10-K405", "A-2", "1998-04-15", "1997-12-31")]
    assert pick_join(rows, 1997)["outcome"] == "ambiguous"


def test_join_ksb_never_matches_corpus():
    # corpus composition = 10-K ∪ 10-K405 ∪ 10-KT, never the KSB family
    rows = [_row("10KSB", "K-1", "1998-03-30", "1997-12-31")]
    assert pick_join(rows, 1997)["outcome"] == "not_found"


def test_join_falls_back_to_filing_year():
    rows = [_row("10-K405", "A-1", "1998-03-30", "1997-12-31")]
    j = pick_join(rows, 1998)
    assert j["outcome"] == "matched" and j["join_basis"] == "filing_date"


# --- vote tiers + lineage discount ---------------------------------------------

def test_three_way_agreement_is_pseudo_gold():
    assert classify_vote("agree", "agree") == "pseudo_gold_3way"


def test_corpus_only_agreement_is_weak_two_way():
    # pre-2001 degradation: engine unavailable -> single crawler-lineage teacher
    assert classify_vote("agree", None) == "pseudo_gold_2way_corpus_only"
    assert classify_vote("agree", "engine_unavailable") == "pseudo_gold_2way_corpus_only"


def test_engine_suspect_is_no_signal_not_a_strike():
    # P0-5: the blind-class verdict must not block a corpus-confirmed span
    assert classify_vote("agree", "engine_suspect") == "pseudo_gold_2way_corpus_only"


def test_any_disagreement_routes_to_hard_case():
    assert classify_vote("disagree", "agree") == "hard_case"
    assert classify_vote("agree", "disagree") == "hard_case"


def test_no_corpus_signal_yields_no_candidate():
    assert classify_vote("engine_unavailable", "agree") == "no_corpus_signal"
