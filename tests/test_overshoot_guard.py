"""Overshoot guard — the NTU boundary-bleed fix (giants_task2.md §外部量測
rerun 2026-07-10).

The dominant NTU-fold failure mode (123/141 errors, 87%) is boundary bleed:
the span starts right (recall≈1) but the tail swallows the next item(s) while
confidence saturates at 1.0 and needs_review stays quiet. Two named signals
now cap it:

- overshoot_containment (boundary.apply_overshoot_guard): the span body holds
  a plausible LATER-item heading beyond a small head margin;
- overshoot_size_ratio (size_bands.apply_size_bands high side): span length
  above the empirical band's upper bound (the p95-proxy).

Each appends a zero-scored 3.5-weight component, so an otherwise-perfect
10.0-weight breakdown caps at 10/13.5 ≈ 0.74 — and needs_review is forced.

Legit cases that must NOT alarm: combined-item spans (P0-9, status partial),
TOC-like reference lines (anchor links / trailing page numbers), headings
quoted inside prose (no emphasis/layout evidence), and reassembled wrapper
bodies (JPM class, provenance != offset_exact_span; JPM's reassembled Item 7
~390K chars is also inside the committed item-7 band hi=464,192).
"""

from sec_core.boundary import (
    OVERSHOOT_CONTAINMENT_COMPONENT,
    apply_overshoot_guard,
    find_contained_later_heading,
    scan_span_overshoot,
)
from sec_core.pipeline import extract_from_html
from sec_core.size_bands import (
    OVERSHOOT_SIZE_COMPONENT,
    MIN_DOC_CHARS,
    SizeBand,
    apply_size_bands,
)

BODY = ("The company operates manufacturing facilities and distribution networks "
        "across several regions under long-term agreements reviewed annually. ")


def para(text: str) -> str:
    return f"<p>{text}</p>"


def bold(text: str) -> str:
    return f"<p><b>{text}</b></p>"


# --- real overshoot: item 6 span swallows 7/7A --------------------------------
# The resolver's failure chain mirrors the NTU bleed archetype: the real Item 7
# heading is wrapped in an internal anchor link, so TOC assessment rejects it
# in favour of a later duplicate; Item 7A's real heading then falls before the
# sequence position and is dropped — item 6's end lands at the late duplicate
# and its span swallows the real 7 and 7A bodies.

def _overshoot_result():
    html = "".join([
        bold("Item 5. Market for Registrant's Common Equity, Related Stockholder "
             "Matters and Issuer Purchases of Equity Securities"),
        para(BODY * 15),
        bold("Item 6. [Reserved]"),
        para("[Reserved]"),
        '<p><a href="#mda">Item 7. Management\'s Discussion and Analysis of '
        "Financial Condition and Results of Operations</a></p>",
        para(BODY * 20),
        bold("Item 7A. Quantitative and Qualitative Disclosures About Market Risk"),
        para(BODY * 10),
        bold("Item 7. Management's Discussion and Analysis of Financial Condition "
             "and Results of Operations"),
        para(BODY * 20),
        bold("Item 8. Financial Statements and Supplementary Data"),
        para(BODY * 10),
    ])
    return extract_from_html(html, "overshoot-fixture")


class TestContainmentOvershoot:
    def test_end_rescan_now_cuts_the_swallowing_span_at_the_contained_heading(self):
        # extraction end-boundary fix: the resolver itself rescans the span
        # body and CUTS at the contained 7A heading — the guard has nothing
        # left to flag on the pipeline path (it stays as a safety net below)
        result = _overshoot_result()
        seg = result.segment("6")
        cand_7a = min(c.start for c in result.candidates if c.code == "7A")
        assert seg.end_offset <= cand_7a
        assert any("end rescan: span cut at" in w for w in seg.warnings)

    def test_guard_still_flags_a_span_that_reaches_it_overshooting(self):
        # safety net: if a swallowing span ever reaches the guard (any future
        # path that bypasses the resolver's rescan), it is still flagged
        result = _overshoot_result()
        seg = result.segment("6")
        seg.end_offset = result.segment("8").start_offset  # re-extend past 7A
        seg.needs_review = False
        seg.warnings.clear()
        assert apply_overshoot_guard(result.segments, result.confidence,
                                     result.candidates) >= 1
        assert seg.needs_review is True
        assert any("overshoot: contains later item heading 7A" in w
                   for w in seg.warnings)
        bd = result.confidence["6"]
        comp = next(c for c in bd.components
                    if c.name == OVERSHOOT_CONTAINMENT_COMPONENT)
        assert comp.score == 0.0 and comp.max_score == 3.5 and comp.reason
        assert seg.confidence == bd.total <= 0.75

    def test_spans_without_contained_headings_are_untouched(self):
        result = _overshoot_result()
        for code in ("5", "7", "8"):
            assert not any("overshoot: contains" in w
                           for w in result.segment(code).warnings)
            assert not any(c.name == OVERSHOOT_CONTAINMENT_COMPONENT
                           for c in result.confidence[code].components)


# --- legit cases that must NOT alarm ------------------------------------------

class TestLegitSpansNotFlagged:
    def test_combined_item_span_is_never_flagged(self):
        # P0-9: 'Items 1 and 2' share one span (status partial) — guard skips
        html = "".join([
            bold("Items 1 and 2. Business and Properties"),
            para(BODY * 10),
            bold("Item 3. Legal Proceedings"),
            para(BODY * 5),
        ])
        result = extract_from_html(html, "combined-fixture")
        for code in ("1", "2"):
            seg = result.segment(code)
            assert seg.status == "partial"
            assert not any("overshoot" in w for w in seg.warnings)
        assert apply_overshoot_guard(result.segments, result.confidence,
                                     result.candidates) == 0

    def test_toc_like_reference_line_inside_span_is_not_an_overshoot(self):
        # a mini-index line (anchor link) for a later item inside item 1's body
        html = "".join([
            bold("Item 1. Business"),
            para(BODY * 10),
            '<p><a href="#prop">Item 2. Properties</a></p>',
            para(BODY * 10),
            bold("Item 2. Properties"),
            para(BODY * 5),
        ])
        result = extract_from_html(html, "toc-line-fixture")
        seg = result.segment("1")
        assert seg.end_offset > seg.start_offset
        assert not any("overshoot" in w for w in seg.warnings)

    def test_heading_quoted_in_prose_is_not_an_overshoot(self):
        # a plain paragraph starting with the later item's heading text — no
        # bold/layout evidence, so it never reads as a body heading
        html = "".join([
            bold("Item 2. Properties"),
            para(BODY * 10),
            para("Item 3. Legal Proceedings of this report describes the "
                 "litigation and regulatory matters we currently face."),
            para(BODY * 10),
            bold("Item 3. Legal Proceedings"),
            para(BODY * 5),
        ])
        result = extract_from_html(html, "quoted-prose-fixture")
        seg = result.segment("2")
        assert not any("overshoot" in w for w in seg.warnings)

    def test_non_offset_exact_provenance_is_skipped(self):
        # JPM class: a reassembled wrapper body (resolved_from_page_anchor)
        # keeps its own honest handling — the guard never re-flags it
        result = _overshoot_result()
        seg = result.segment("6")
        seg.provenance = "resolved_from_page_anchor"
        seg.needs_review = False
        seg.warnings.clear()
        assert apply_overshoot_guard(result.segments, result.confidence,
                                     result.candidates) == 0
        assert seg.needs_review is False

    def test_head_margin_exempts_own_heading_region(self):
        # a later-code candidate at the very span start (combined-heading
        # geometry) is inside the head margin -> never counted as containment
        result = _overshoot_result()
        cand = next(c for c in result.candidates if c.code == "7A")
        seg = result.segment("6")
        assert find_contained_later_heading(
            "6", result.candidates, cand.start, seg.end_offset) is None


# --- span-text scan (mutation-harness channel) --------------------------------

class TestScanSpanOvershoot:
    def test_uppercase_later_heading_in_span_text_is_found(self):
        span = ("Item 6. [Reserved]\n" + BODY * 6 + "\n"
                "ITEM 7A. QUANTITATIVE AND QUALITATIVE DISCLOSURES ABOUT MARKET RISK\n"
                + BODY * 4)
        hit = scan_span_overshoot("6", span)
        assert hit is not None and hit.code == "7A"

    def test_toc_stub_lines_with_page_numbers_are_ignored(self):
        span = ("Item 6. [Reserved]\n" + BODY * 6 + "\n"
                "Item 7. Management's Discussion and Analysis ........ 35\n"
                "Item 7A. Quantitative and Qualitative Disclosures ........ 58\n"
                + BODY * 4)
        assert scan_span_overshoot("6", span) is None

    def test_clean_span_yields_none(self):
        assert scan_span_overshoot("1A", "Item 1A. Risk Factors\n" + BODY * 8) is None


# --- size-ratio overshoot signal ----------------------------------------------

FILLER = BODY


def _sized_result(item1_reps: int):
    html = "".join([
        bold("Item 1. Business"),
        para(FILLER * item1_reps),
        bold("Item 1B. Unresolved Staff Comments"),
        para("None."),
        bold("Item 7. Management's Discussion and Analysis of Financial Condition "
             "and Results of Operations"),
        para(FILLER * (MIN_DOC_CHARS // len(FILLER) + 2)),
    ])
    return extract_from_html(html, "size-ratio-test")


class TestSizeRatioOvershoot:
    BANDS = {("10-K", "MODERN", "1"): SizeBand("10-K", "MODERN", "1",
                                               5, 1000, 200, 8000)}

    def test_high_side_violation_adds_overshoot_component_and_caps(self):
        result = _sized_result(item1_reps=100)  # ~13K chars >> hi 8000
        seg = result.segment("1")
        seg.needs_review = False
        seg.warnings.clear()
        n = apply_size_bands(result.segments, result.doc, bands=self.BANDS,
                             breakdowns=result.confidence)
        assert n == 1 and seg.needs_review is True
        assert any(w.startswith("overshoot: size ") and "band median" in w
                   for w in seg.warnings)
        bd = result.confidence["1"]
        comp = next(c for c in bd.components
                    if c.name == OVERSHOOT_SIZE_COMPONENT)
        assert comp.score == 0.0 and comp.max_score == 3.5
        assert seg.confidence == bd.total <= 0.75

    def test_component_is_appended_once_even_if_reapplied(self):
        result = _sized_result(item1_reps=100)
        for _ in range(2):
            apply_size_bands(result.segments, result.doc, bands=self.BANDS,
                             breakdowns=result.confidence)
        comps = [c for c in result.confidence["1"].components
                 if c.name == OVERSHOOT_SIZE_COMPONENT]
        assert len(comps) == 1

    def test_low_side_violation_gets_no_overshoot_component(self):
        result = _sized_result(item1_reps=1)  # ~130 chars << lo 200
        seg = result.segment("1")
        seg.needs_review = False
        seg.warnings.clear()
        apply_size_bands(result.segments, result.doc, bands=self.BANDS,
                         breakdowns=result.confidence)
        assert seg.needs_review is True  # existing hard flag still fires
        assert not any(w.startswith("overshoot:") for w in seg.warnings)
        assert not any(c.name == OVERSHOOT_SIZE_COMPONENT
                       for c in result.confidence["1"].components)

    def test_in_band_long_span_is_legit(self):
        # JPM-scale spans stay unflagged when inside the band (committed item-7
        # band hi=464,192 covers the reassembled ~390K-char Item 7)
        result = _sized_result(item1_reps=50)  # ~6.5K chars, inside 200..8000
        seg = result.segment("1")
        before_warnings = list(seg.warnings)
        n = apply_size_bands(result.segments, result.doc, bands=self.BANDS,
                             breakdowns=result.confidence)
        assert n == 0 and seg.warnings == before_warnings
        assert not any(c.name == OVERSHOOT_SIZE_COMPONENT
                       for c in result.confidence["1"].components)
