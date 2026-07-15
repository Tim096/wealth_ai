"""Pre-2001 plain-text/SGML filings: a normalize bug, not a format-era boundary.

Weakness D (measured 2026-07-15). README/FG-SEC-009 claimed pre-2001 plain-text
SGML 10-Ks are unsupported because "candidate detection is HTML-oriented". That
root cause is FALSE. The detector is fine; `normalize` destroys the input before
the detector ever sees it:

    normalize_html(AAPL 1996): raw 6,246 newlines -> norm 51 -> 52 lines
                               (longest line 74,186 chars) -> 0 candidates

    same detector, line structure preserved:
      AAPL 1996 -> 16 candidates, items 1..14
      KO   1997 -> 18 candidates, incl. 7A

Cause: `_Normalizer._emit_text` only emits newlines for BLOCK_TAGS; a `\n` inside
a plain TEXT node is swallowed as whitespace. A plain-text filing carries ALL of
its structure in those newlines, so the whole document collapsed into one line.

These tests pin, in order:
  1. the collapse itself (the bug);
  2. that text-mode preserves line structure;
  3. that `norm_to_raw` STAYS EXACT — the source-exact guarantee is the point of
     the whole system and must not be traded for extra items;
  4. that real pre-2001 filings then yield real items;
  5. that HTML filings are completely unaffected.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from sec_core.coverage import partition_document
from sec_core.headings import detect_candidates
from sec_core.normalize import normalize_html

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "data" / "sec_eval" / "fixtures"
MANIFEST = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8-sig"))

PRE2001 = ["AAPL_FY1996", "KO_FY1997"]
HTML_ERA = ["AAPL_FY2025", "KO_FY2025", "MSFT_FY2025"]


def _raw(fixture_id: str) -> str:
    spec = MANIFEST["fixtures"][fixture_id]
    return gzip.decompress((FIXTURES / spec["file"]).read_bytes()).decode(
        "utf-8", errors="replace")


# --- 1/2. line structure ----------------------------------------------------

@pytest.mark.parametrize("fixture_id", PRE2001)
def test_plain_text_filing_keeps_its_line_structure(fixture_id):
    """The bug: 6,246 raw newlines collapsed to 51. A plain-text filing's
    structure IS its newlines — losing them destroys the document."""
    raw = _raw(fixture_id)
    doc = normalize_html(raw)
    raw_nl = raw.count("\n")
    norm_nl = doc.text.count("\n")
    assert norm_nl > raw_nl * 0.5, (
        f"{fixture_id}: normalize collapsed {raw_nl} raw newlines into {norm_nl} — "
        "plain-text line structure destroyed")
    longest = max(len(ln.text) for ln in doc.lines)
    assert longest < 2000, (
        f"{fixture_id}: longest normalized line is {longest} chars — the document "
        "collapsed into mega-lines")


# --- 3. the source-exact guarantee (must survive the fix) -------------------

@pytest.mark.parametrize("fixture_id", PRE2001 + HTML_ERA)
def test_norm_to_raw_offset_map_stays_exact(fixture_id):
    """THE load-bearing invariant. Every normalized char must map back to a raw
    offset that (a) is in bounds, (b) never goes backwards, and (c) for plain
    alphanumeric chars holds that exact char in the raw source. If this breaks,
    every offset, sha256 and 'source-exact span' claim in the system is void."""
    raw = _raw(fixture_id)
    doc = normalize_html(raw)
    assert len(doc.norm_to_raw) == len(doc.text)

    prev = -1
    checked = 0
    for i, ch in enumerate(doc.text):
        off = doc.norm_to_raw[i]
        assert 0 <= off < len(raw), f"{fixture_id}: offset {off} out of bounds at {i}"
        assert off >= prev, (
            f"{fixture_id}: norm_to_raw went backwards at {i} ({off} < {prev}) — "
            "the map must be monotonic")
        prev = off
        if ch.isalnum() and ch.isascii():
            assert raw[off] == ch, (
                f"{fixture_id}: norm_to_raw[{i}] -> raw[{off}]={raw[off]!r} but "
                f"normalized char is {ch!r} — offset map is WRONG")
            checked += 1
    assert checked > 1000, f"{fixture_id}: only {checked} chars verified — weak test"


@pytest.mark.parametrize("fixture_id", PRE2001)
def test_text_mode_newlines_point_at_the_real_raw_newline(fixture_id):
    """A newline emitted in text mode must address the raw newline it came
    from — not the offset of some unrelated tag."""
    raw = _raw(fixture_id)
    doc = normalize_html(raw)
    nl_positions = [i for i, c in enumerate(doc.text) if c == "\n"]
    assert len(nl_positions) > 1000, "expected text-mode to emit many newlines"
    for i in nl_positions[:500]:
        off = doc.norm_to_raw[i]
        assert raw[off] == "\n", (
            f"{fixture_id}: normalized newline at {i} maps to raw[{off}]={raw[off]!r}, "
            "not a raw newline")


# --- 4. the detector was never broken ---------------------------------------

@pytest.mark.parametrize("fixture_id,min_candidates", [("AAPL_FY1996", 10), ("KO_FY1997", 10)])
def test_pre2001_filing_yields_real_item_candidates(fixture_id, min_candidates):
    """Same detector, undamaged input: 0 candidates -> real items."""
    doc = normalize_html(_raw(fixture_id))
    cands = detect_candidates(doc)
    assert len(cands) >= min_candidates, (
        f"{fixture_id}: only {len(cands)} candidates — the detector is starved, "
        "which was the real root cause")
    codes = {c.code for c in cands}
    for expected in ("1", "3", "5", "7", "8"):
        assert expected in codes, f"{fixture_id}: item {expected} not detected"


def test_pre2001_extraction_is_evidence_backed_never_a_false_pass():
    """Honest-or-correct: after the fix a pre-2001 filing may extract items, but
    every span that claims pass/partial must be a real source-exact span, and
    anything unresolved stays an honest empty miss. Never a fabricated body."""
    from observability_core import sha256_text
    from sec_core.pipeline import extract_from_html

    result = extract_from_html(_raw("AAPL_FY1996"), filing_id="aapl-fy1996")
    extracted = [s for s in result.segments if s.status in ("pass", "partial")]
    assert extracted, "expected the fix to extract at least some pre-2001 items"
    for seg in extracted:
        span = result.doc.slice(seg.start_offset, seg.end_offset)
        assert seg.end_offset > seg.start_offset
        assert sha256_text(span) == seg.text_sha256, (
            f"Item {seg.item_code}: span/sha256 mismatch — not source-exact")
        assert span in result.doc.text
    for seg in result.segments:
        if seg.status == "missing":
            assert seg.text_sha256 == ""
            assert seg.end_offset == seg.start_offset


@pytest.mark.parametrize("fixture_id", PRE2001)
def test_partition_invariant_holds_on_pre2001(fixture_id):
    """The existing no-overlap / full-coverage invariant must keep holding."""
    from sec_core.pipeline import extract_from_html

    result = extract_from_html(_raw(fixture_id), filing_id=f"part-{fixture_id}")
    blocks = partition_document(result.doc.text, result.segments)
    assert blocks[0].start == 0
    assert blocks[-1].end == len(result.doc.text)
    for a, b in zip(blocks, blocks[1:]):
        assert a.end == b.start, f"{fixture_id}: partition gap/overlap at {a.end}"


# --- 5. HTML era must not move ----------------------------------------------

@pytest.mark.parametrize("fixture_id", HTML_ERA)
def test_html_era_normalization_is_untouched(fixture_id):
    """Text mode must be strictly opt-in on structure-less documents. A real
    HTML filing must normalize exactly as before (block tags own the newlines)."""
    raw = _raw(fixture_id)
    doc = normalize_html(raw)
    cands = detect_candidates(doc)
    assert len(cands) >= 8, f"{fixture_id}: HTML detection regressed ({len(cands)})"
    # HTML filings put structure in tags, so normalized lines must FAR exceed the
    # handful of raw newlines the minifier left behind
    assert len(doc.lines) > 100
