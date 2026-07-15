"""Part-level incorporation by reference + the confidence-0 review safety net.

Weakness C (held-out, measured 2026-07-15). Berkshire Hathaway FY2025 10-K
(CIK 1067983, accession 0001193125-26-083899) writes its Part III incorporation
as ONE PART-LEVEL PROSE SENTENCE with no per-Item headings:

    Part III
    Except for the information set forth under the caption "Executive Officers
    of the Registrant" in Part I hereof, information required by this Part
    (Items 10, 11, 12, 13 and 14) is incorporated by reference from the
    Registrant's definitive proxy statement, filed pursuant to Regulation 14A,
    for the Annual Meeting of Shareholders ...

The existing cross_ref / refine stub detection is per-Item-heading oriented, so
Items 10-14 came back status=missing, confidence=0.0, needs_review=False — a
silent failure twice over: the status is wrong AND a zero-confidence verdict
was not routed to a human.

Fixture: tests/fixtures/BRK_FY2025_part3_excerpt.htm is a SOURCE-EXACT slice
raw[9921332:9931486) of the real primary document
https://www.sec.gov/Archives/edgar/data/1067983/000119312526083899/brka-20251231.htm
(full doc sha256 878392c22e73b92722d63bb4f486586cdb5a0b8ce0d08bc403b1c0239b891282,
10,396,820 chars). The slice keeps Items 9/9A/9B/9C, the Part III declaration and
the Item 15 heading — the minimal region that reproduces the failure — so the
10 MB filing stays out of the repo. Excerpt sha256
007677747a8f8135183725f464c8e7fcdd0819507c3289adaca9c324bb027823.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

from observability_core import sha256_text
from sec_core.pipeline import extract_from_html

FIXTURES = Path(__file__).resolve().parent / "fixtures"
EXCERPT = FIXTURES / "BRK_FY2025_part3_excerpt.htm"
EXCERPT_SHA256 = "007677747a8f8135183725f464c8e7fcdd0819507c3289adaca9c324bb027823"

PART_III_ITEMS = ("10", "11", "12", "13", "14")


def _raw() -> str:
    raw = EXCERPT.read_text(encoding="utf-8")
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    assert digest == EXCERPT_SHA256, (
        f"BRK excerpt fixture drifted (sha256 {digest} != frozen {EXCERPT_SHA256}) — "
        "the fixture is a source-exact slice of the real filing; do not edit it")
    return raw


@pytest.fixture(scope="module")
def brk():
    return extract_from_html(_raw(), filing_id="BRK-FY2025-part3-excerpt")


def test_fixture_really_contains_the_part_level_declaration(brk):
    """Guards the fixture itself: the whole point is the Part-level prose form —
    an incorporation sentence naming Items 10-14 with NO per-item headings."""
    text = brk.doc.text
    assert re.search(
        r"information required by this Part \(Items 10, 11, 12, 13 and 14\) is "
        r"incorporated by reference from the Registrant's definitive proxy statement",
        text,
    ), "fixture lost the Part-level incorporation sentence"
    for code in PART_III_ITEMS:
        assert not re.search(rf"^Item {code}\.", text, re.MULTILINE), (
            f"fixture unexpectedly has a per-Item heading for Item {code} — "
            "then this is not the Part-level class any more")


@pytest.mark.parametrize("code", PART_III_ITEMS)
def test_part_level_declaration_is_classified_incorporated_by_reference(brk, code):
    """WEAKNESS C, part 1. The filing says these items ARE incorporated by
    reference from the proxy statement. 'missing' is factually wrong."""
    seg = brk.segment(code)
    assert seg.status == "incorporated_by_reference", (
        f"Item {code}: expected incorporated_by_reference, got {seg.status!r} — "
        "the Part-level declaration was not detected")
    assert seg.needs_review is True
    assert seg.provenance == "cross_reference_pointer"


@pytest.mark.parametrize("code", PART_III_ITEMS)
def test_part_level_pointer_keeps_source_exact_provenance_to_the_declaration(brk, code):
    """The pointer must be addressable back to the sentence that justifies it —
    never a guess, never fabricated body text."""
    seg = brk.segment(code)
    span = brk.doc.slice(seg.start_offset, seg.end_offset)
    assert seg.end_offset > seg.start_offset, "pointer must carry a real source span"
    assert sha256_text(span) == seg.text_sha256, "span/sha256 must be source-exact"
    assert "incorporated by reference" in span.lower()
    assert "proxy statement" in span.lower()
    # the span is the declaration, NOT invented item content
    assert "required by this Part" in span
    assert any("Part-level" in w or "part-level" in w for w in seg.warnings), (
        f"Item {code} must explain that it came from a Part-level declaration")


@pytest.mark.parametrize("enumeration,expected", [
    # the form Berkshire actually uses
    ("Items 10, 11, 12, 13 and 14", ["10", "11", "12", "13", "14"]),
    # range forms
    ("Items 10 through 14", ["10", "11", "12", "13", "14"]),
    ("Items 10 to 14", ["10", "11", "12", "13", "14"]),
    ("Items 10-14", ["10", "11", "12", "13", "14"]),
    # repeated-'Item' form
    ("Item 10 and Item 11", ["10", "11"]),
    ("Items 10, 11 and 12", ["10", "11", "12"]),
    ("Item 10", ["10"]),
    # never invent items that are not real 10-K codes
    ("Items 99, 42", []),
])
def test_item_enumeration_forms_are_parsed(enumeration, expected):
    from sec_core.cross_ref import parse_item_code_list

    assert parse_item_code_list(enumeration) == expected


def test_part_level_declaration_never_overwrites_an_extracted_body(brk):
    """The declaration must only fill in items that had NO body. Items 9/9A/9B
    have real bodies in this excerpt and must be left exactly as they were."""
    for code in ("9", "9A", "9B"):
        seg = brk.segment(code)
        assert seg.status == "pass", (
            f"Item {code} had a real body and must not be hijacked by the "
            f"Part III declaration (got {seg.status!r})")


# ---------------------------------------------------------------------------
# WEAKNESS C, part 2 — the INDEPENDENT safety net.
# This must hold for every unknown misjudgement class, not just Berkshire:
# a confidence-0.0 'missing' verdict that nobody is asked to look at is a
# silent failure by construction.
# ---------------------------------------------------------------------------

def test_zero_confidence_missing_items_are_always_routed_to_review(brk):
    for seg in brk.segments:
        if seg.status == "missing" and seg.confidence == 0.0:
            assert seg.needs_review is True, (
                f"Item {seg.item_code}: status=missing at confidence 0.0 but "
                "needs_review=False — a zero-confidence verdict must never be "
                "served without asking a human to look")


def test_zero_confidence_missing_safety_net_is_independent_of_berkshire():
    """The net is generic: a document with no resolvable item bodies at all
    still routes every confidence-0 miss to review."""
    html = "<html><body><div>Some unrelated prose with no item headings.</div></body></html>"
    result = extract_from_html(html, filing_id="no-items")
    missing = [s for s in result.segments if s.status == "missing" and s.confidence == 0.0]
    assert missing, "expected this document to produce confidence-0 missing items"
    for seg in missing:
        assert seg.needs_review is True, (
            f"Item {seg.item_code}: confidence-0 missing must be needs_review")
        assert any("confidence 0.0" in w or "zero-confidence" in w for w in seg.warnings), (
            f"Item {seg.item_code}: the review flag must explain itself")
