"""Shared-span disclosure: two items must never deliver the same bytes silently.

Measured 2026-07-15 (AAPL FY1996, after the normalize text-mode fix):

    14   [167211, 178039) partial conf=0.83 needs_review=False
    15   [167211, 178039) partial conf=0.73 needs_review=False
              ^^^^^^^^^^ identical span delivered as two different items

Two failures stack here:
  1. tie-break is undefined — the spans have the same start AND the same width,
     so "tightest span wins, later start breaks ties" cannot separate them;
  2. both are needs_review=False — a reader consuming Item 15 independently gets
     Item 14's content and the system says nothing. That is a silent failure of
     exactly the class the zero-confidence net exists to catch, in another shape.

NOTE on scope: this pins DISCLOSURE, not resolution. We do not guess which item
owns the span, we do not drop either one, and we do not touch era-aware schema
mapping (FY1996's "Item 14. Exhibits ... and Reports on Form 8-K" is really the
modern Item 15, and the modern Item 14 did not exist in 1996 — a separate, much
riskier decision that is deliberately out of scope here).

The guard is NOT pre-2001-specific: `_infer_combined_headings` (P0-9) and
explicit "Items 1 and 2" headings produce the same shared span on a modern HTML
filing, which is what test_modern_combined_heading_* below pins.

Do NOT justify this with coverage.partition_document: that invariant is about
tiling the DOCUMENT (every char belongs to exactly one block, overlap resolved
to the tightest span). It says nothing about whether two ITEM spans are
mutually exclusive, so it cannot endorse this output.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from sec_core.pipeline import extract_from_html

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "data" / "sec_eval" / "fixtures"
MANIFEST = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8-sig"))

_FILLER = (
    "The Company continues to evaluate developments in its markets and adjusts its "
    "operating plans accordingly, and management believes the factors described above "
    "are the material considerations relevant to this item. "
)


def _pad(text: str, target: int = 1400) -> str:
    while len(text) < target:
        text += " " + _FILLER
    return text


def _sec(heading: str, body: str) -> str:
    return f"<p><b>{heading}</b></p>\n<p>{_pad(body)}</p>\n"


def _raw(fixture_id: str) -> str:
    spec = MANIFEST["fixtures"][fixture_id]
    return gzip.decompress((FIXTURES / spec["file"]).read_bytes()).decode(
        "utf-8", errors="replace")


def _shared_span_groups(result) -> dict[tuple[int, int], list[str]]:
    """item codes grouped by the identical non-empty span they were resolved to."""
    groups: dict[tuple[int, int], list[str]] = {}
    for seg in result.segments:
        if seg.end_offset > seg.start_offset:
            groups.setdefault((seg.start_offset, seg.end_offset), []).append(seg.item_code)
    return {k: v for k, v in groups.items() if len(v) > 1}


# --- era-independent: a MODERN filing hits this too -------------------------

@pytest.fixture(scope="module")
def modern_combined():
    """'Item 1. Business and Properties' leaves Item 2 with no heading of its
    own, so P0-9 infers the pair as combined and BOTH items resolve to the
    identical span — on a perfectly ordinary modern HTML filing."""
    html = "<html><body>" + "".join([
        _sec("Item 1. Business and Properties", "BIZ_MARKER We design widgets and own facilities."),
        _sec("Item 1A. Risk Factors", "RISK_MARKER Investing involves risk."),
        _sec("Item 3. Legal Proceedings", "LEGAL_MARKER We are party to litigation."),
    ]) + "</body></html>"
    return extract_from_html(html, "combined-modern")


def test_modern_combined_heading_really_produces_an_identical_span(modern_combined):
    """Guards the repro itself — if this stops sharing a span the test below is
    no longer testing anything."""
    groups = _shared_span_groups(modern_combined)
    assert groups, "expected the combined heading to yield one span for two items"
    assert any(set(codes) == {"1", "2"} for codes in groups.values()), (
        f"expected items 1 and 2 to share a span, got {groups}")


def test_modern_combined_heading_items_are_flagged_for_review(modern_combined):
    """THE FIX. Two items delivering the same bytes must both say so."""
    for code in ("1", "2"):
        seg = modern_combined.segment(code)
        assert seg.needs_review is True, (
            f"Item {code} shares an identical span with another item but "
            "needs_review=False — the reader is silently handed another item's content")


def test_shared_span_warning_names_the_codes_and_the_span(modern_combined):
    """The warning must be checkable fact — which items, which span — not an
    adjective."""
    seg = modern_combined.segment("2")
    start, end = seg.start_offset, seg.end_offset
    hits = [w for w in seg.warnings if "identical span" in w]
    assert hits, f"Item 2 has no shared-span warning: {seg.warnings}"
    w = hits[0]
    assert "1" in w and "2" in w, f"warning must name the sharing item codes: {w}"
    assert str(start) in w and str(end) in w, f"warning must name the span offsets: {w}"


def test_unaffected_items_are_not_flagged_by_this_guard(modern_combined):
    """The guard must not spray review flags over items that own their span."""
    for code in ("1A", "3"):
        seg = modern_combined.segment(code)
        assert not [w for w in seg.warnings if "identical span" in w], (
            f"Item {code} does not share a span and must not be flagged by this guard")


# --- the original measured case --------------------------------------------

def test_aapl_fy1996_items_14_and_15_are_flagged():
    result = extract_from_html(_raw("AAPL_FY1996"), filing_id="aapl-fy1996")
    s14, s15 = result.segment("14"), result.segment("15")
    assert (s14.start_offset, s14.end_offset) == (s15.start_offset, s15.end_offset), (
        "fixture drifted: 14/15 no longer share a span")
    for seg in (s14, s15):
        assert seg.needs_review is True, (
            f"AAPL FY1996 Item {seg.item_code}: identical span to the other item but "
            "needs_review=False")
        assert [w for w in seg.warnings if "identical span" in w]


@pytest.mark.parametrize("fixture_id", ["AAPL_FY1996", "KO_FY1997"])
def test_every_shared_span_item_is_flagged_on_pre2001(fixture_id):
    result = extract_from_html(_raw(fixture_id), filing_id=f"shared-{fixture_id}")
    for span, codes in _shared_span_groups(result).items():
        for code in codes:
            seg = result.segment(code)
            if seg.provenance == "cross_reference_pointer":
                continue  # pointer text, not delivered as this item's content
            assert seg.needs_review is True, (
                f"{fixture_id} Item {code} shares span {span} with {codes} but is not flagged")


# --- the guard must not fire on honest shared POINTER text -------------------

def test_part_level_pointers_sharing_one_declaration_are_not_a_content_collision():
    """Berkshire's Items 10-14 all point at ONE Part-level declaration sentence,
    so they legitimately share that span — but it is pointer text, explicitly not
    the item's content (status=incorporated_by_reference, provenance=
    cross_reference_pointer). They are already needs_review by construction, so
    this guard must not additionally accuse them of a content collision."""
    excerpt = Path(__file__).resolve().parent / "fixtures" / "BRK_FY2025_part3_excerpt.htm"
    result = extract_from_html(excerpt.read_text(encoding="utf-8"), "brk-part3")
    for code in ("10", "11", "12", "13", "14"):
        seg = result.segment(code)
        assert seg.needs_review is True  # still flagged, by the pointer path
        assert not [w for w in seg.warnings if "identical span" in w], (
            f"Item {code}: shared POINTER text must not be reported as two items "
            "delivering the same content")


# --- modern real filings must not regress ------------------------------------

@pytest.mark.parametrize("fixture_id", ["AAPL_FY2025", "KO_FY2025", "MSFT_FY2025"])
def test_modern_real_filings_have_no_shared_content_spans(fixture_id):
    """If a real modern filing ever shares an item span, that is a finding in
    itself — this test says so out loud rather than letting it pass silently."""
    result = extract_from_html(_raw(fixture_id), filing_id=f"shared-{fixture_id}")
    collisions = {
        span: codes for span, codes in _shared_span_groups(result).items()
        if any(result.segment(c).provenance != "cross_reference_pointer" for c in codes)
    }
    assert not collisions, f"{fixture_id} delivers one span as several items: {collisions}"
