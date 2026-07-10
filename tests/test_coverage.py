"""Completeness: item segments + gaps must cover the whole body (the INTC
lesson — content between two resolved page ranges must not vanish)."""

from __future__ import annotations

from dataclasses import dataclass

from sec_core.coverage import (
    compute_gaps, coverage_ratio, partition_document, region_at,
)


@dataclass
class _Seg:
    item_code: str
    start_offset: int
    end_offset: int


def test_gap_between_disjoint_spans_is_recovered():
    text = ("A" * 100) + ("\nmiddle prose that belongs to no item\n" + "B" * 200) + ("C" * 100)
    # two item spans leaving a hole in the middle where the prose lives
    segs = [_Seg("1", 0, 100), _Seg("7", 340, len(text))]
    gaps = compute_gaps(text, segs, min_chars=10)
    assert gaps, "the uncovered middle must surface as a gap"
    g = gaps[0]
    assert g.start == 100 and g.end == 340
    assert g.after_code == "1" and g.before_code == "7"
    assert "middle prose" in g.preview


def test_union_of_items_and_gaps_covers_everything():
    text = "x" * 5000
    segs = [_Seg("1", 0, 1000), _Seg("1A", 3000, 5000)]  # hole [1000,3000)
    gaps = compute_gaps(text, segs, min_chars=50)
    spans = [(s.start_offset, s.end_offset) for s in segs] + [(g.start, g.end) for g in gaps]
    spans.sort()
    hi, holes = 0, 0
    for a, b in spans:
        if a > hi:
            holes += a - hi
        hi = max(hi, b)
    holes += len(text) - hi
    assert holes == 0


def test_overlapping_spans_do_not_manufacture_a_gap():
    text = "y" * 1000
    segs = [_Seg("1", 0, 800), _Seg("2", 400, 1000)]  # overlap, fully covered
    assert compute_gaps(text, segs, min_chars=10) == []
    assert coverage_ratio(text, segs) == 1.0


def test_whitespace_only_gap_is_ignored():
    text = "A" * 100 + "   \n \t " + "B" * 100
    segs = [_Seg("1", 0, 100), _Seg("2", 107, len(text))]
    assert compute_gaps(text, segs, min_chars=1) == []


def test_partition_tiles_the_whole_document_without_overlap():
    text = "z" * 1000
    segs = [_Seg("1", 0, 800), _Seg("2", 400, 1000)]  # overlapping items
    blocks = partition_document(text, segs)
    assert blocks[0].start == 0 and blocks[-1].end == len(text)
    assert all(blocks[i].end == blocks[i + 1].start for i in range(len(blocks) - 1))


def test_partition_attributes_overlap_to_the_tightest_item():
    # Item 2 (Properties, narrow) is nested inside Item 1 (Business, wide).
    # A position inside the nested span must resolve to the tighter item — the
    # bug that made find report "the wrong place".
    text = "q" * 1000
    segs = [_Seg("1", 0, 900), _Seg("2", 300, 400)]
    assert region_at(350, partition_document(text, segs)).code == "2"
    assert region_at(100, partition_document(text, segs)).code == "1"
    assert region_at(950, partition_document(text, segs)).code == ""  # unclassified tail
