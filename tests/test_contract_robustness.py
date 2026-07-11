"""BUCKET 2 — robust success conditions.

Two guarantees:
  1. Brittle literal-token variants that SHOULD match a substantively-done page
     now match (case / trailing punctuation / whitespace form / non-contiguous
     key tokens) — text_match.robust_contains.
  2. A genuinely-wrong / absent answer STILL fails — no tier ever matches on a
     strict subset of the needle, so robustness never becomes false success.
Plus: nl.derive_success and the planner condition author emit CLEAN needles
(no trailing-period artifact) so the brittle values never reach the verifier.
"""

from browser_agent.nl import derive_success
from browser_agent.text_match import normalize, robust_contains


# --- normalize ---------------------------------------------------------------

def test_normalize_strips_case_and_punctuation():
    assert normalize("Sirloin.") == "sirloin"
    assert normalize("Year  Award!") == "year award"
    assert normalize("量子計算。") == "量子計算"


# --- tier 1: normalised substring (the trailing-period / case artifact) ------

def test_trailing_period_token_matches_page():
    # 'sirloin.' — the reported brittle FAIL — now hits a page that says 'sirloin'
    assert robust_contains("sirloin.", "Grilled beef Sirloin steak, 12oz")


def test_case_insensitive_contiguous_phrase_matches():
    assert robust_contains("Year Award", "Voted Game of the Year Award 2025")


# --- tier 2: non-contiguous key-token subset ---------------------------------

def test_non_contiguous_key_tokens_match():
    # 'Year Award' rendered with the two tokens apart still counts as present
    page = "Game of the Year: winner announced\nBest Studio Award goes to ..."
    assert robust_contains("Year Award", page)


def test_single_token_needle_never_uses_token_subset():
    # a lone common token must not rubber-stamp via the subset tier
    assert not robust_contains("award", "Employee of the month program")


# --- tier 3: de-spaced compound word -----------------------------------------

def test_despaced_compound_word_matches():
    # 'boardgame' vs a page that spells it 'board game'
    assert robust_contains("boardgame", "Top rated board game of 2025")


def test_short_needle_is_not_despaced_into_false_hit():
    # gated: a 4-char needle must not fabricate a de-spaced substring match
    assert not robust_contains("acat", "a cat")  # despaced 'acat' < min len 5


# --- no false success: genuinely-absent / wrong answers still fail ------------

def test_absent_answer_fails_all_tiers():
    assert not robust_contains("chicken teriyaki", "Grilled beef sirloin plate")


def test_partial_token_overlap_is_not_a_match():
    # one of two needle tokens present is NOT enough (strict full-needle rule)
    assert not robust_contains("Nobel Prize", "Prize draw winners announced")


def test_empty_needle_never_matches():
    assert not robust_contains("", "anything at all")
    assert not robust_contains("   ", "anything at all")


# --- authoring: derive_success emits a CLEAN needle --------------------------

def test_derive_success_strips_trailing_period_artifact():
    # the latin-token regex captures a trailing '.' ('boardgame.'); the emitted
    # condition must be the clean needle, not the trailing-period artifact
    got = derive_success("找到 boardgame. 這個商品")
    assert got == ["text_visible:boardgame"]


def test_derive_success_keeps_internal_punctuation():
    # a ticker/hyphenated token keeps its internal dots/hyphens
    assert derive_success('查 "Berkshire-A" 股價') == ["text_visible:Berkshire-A"]


def test_derive_success_clean_needle_matches_page_via_robust_contains():
    # end-to-end: the cleaned needle now matches the real page
    (cond,) = derive_success("找到 Sirloin. 這道菜")
    needle = cond.split(":", 1)[1]
    assert robust_contains(needle, "Our Sirloin steak is 12oz")
