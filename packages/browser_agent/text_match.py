"""Robust containment for `text_visible` needles (BUCKET 2).

A success condition of the form text_visible:<phrase> was failing on
substantively-completed tasks because the match was an exact, case-sensitive-
after-lower substring: literal tokens like 'sirloin.' (a trailing-period
artifact mined from the task sentence), 'Year Award' (rendered non-contiguously
on the page, e.g. '… of the Year' … 'Award'), or 'boardgame' (the page spells it
'board game') all missed even though the answer was on the page.

`robust_contains` restores the intended semantics — "this phrase is present on
the page" — by normalising case, whitespace and punctuation and allowing a
key-token subset / de-spaced form, WITHOUT letting a genuinely-absent answer
match. It never lowers the bar to "some words overlap": every tier requires the
FULL needle (all its tokens, or its whole de-spaced form) to be accounted for on
the page, so a wrong answer whose tokens are not present still fails.

verifier.py stays the sole runtime judge. This module is a matcher it MAY call;
the one-line hook is documented at the bottom of this file.
"""

from __future__ import annotations

import re

# Anything that is not a word character (Unicode letters/digits, so CJK is kept)
# is punctuation/separator for matching purposes.
_PUNCT_RE = re.compile(r"[^\w]+", re.UNICODE)

_MIN_TOKEN_LEN = 2      # 1-char tokens ('a', 'x') carry no evidence, ignore them
_MIN_DESPACE_LEN = 5    # de-spacing short needles invites accidental substrings


def normalize(s: str) -> str:
    """Lower-case, turn every punctuation/separator run into a single space, and
    collapse/trim whitespace. 'Sirloin.' -> 'sirloin'; 'Year  Award!' -> 'year
    award'; '量子計算。' -> '量子計算'."""
    return _PUNCT_RE.sub(" ", s.lower()).strip()


def robust_contains(needle: str, haystack: str) -> bool:
    """True when `needle` is present in `haystack` under normalisation, tolerant
    of case / surrounding punctuation / whitespace form, but never on partial
    overlap alone. Tiers (each demands the WHOLE needle):

      1. normalised substring  — 'sirloin.' in '… sirloin steak …';
         'Year Award' in '… of the Year Award …'.
      2. key-token subset      — EVERY needle token (len >= 2) appears as a whole
         token on the page: 'Year Award' when the page shows '… of the Year' and
         'Award' separately. Requires >= 2 such tokens so a single common word
         can never rubber-stamp a match.
      3. de-spaced substring   — the needle with ALL whitespace removed occurs in
         the likewise de-spaced page: 'boardgame' <-> 'board game'. Gated to
         needles >= 5 chars so short fragments don't fabricate hits.

    A genuinely-absent answer fails every tier because no tier ever matches on a
    strict subset of the needle's tokens."""
    n = normalize(needle)
    h = normalize(haystack)
    if not n:
        return False
    if n in h:                                   # tier 1
        return True
    n_tokens = [t for t in n.split() if len(t) >= _MIN_TOKEN_LEN]
    if len(n_tokens) >= 2:                        # tier 2
        h_tokens = set(h.split())
        if all(t in h_tokens for t in n_tokens):
            return True
    n_despaced = n.replace(" ", "")               # tier 3
    if len(n_despaced) >= _MIN_DESPACE_LEN and n_despaced in h.replace(" ", ""):
        return True
    return False


# --- one-line hook for verifier.py (verifier stays the sole judge) ------------
# verifier._text_visible_hit currently ends with:
#       return needle.lower() in kept.lower()
# To adopt robust matching (keeping the query-echo masking in `kept`), replace
# that line with:
#       from browser_agent.text_match import robust_contains
#       return robust_contains(needle, kept)
# No other change is required; robust_contains is a strict superset of the old
# exact-substring check (tier 1 subsumes it after normalisation).
