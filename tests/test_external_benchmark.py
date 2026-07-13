"""P0-2 external benchmark plumbing: NTU itemseg loaders + head-to-head scoring.

Offline only — no network, no dataset download; format facts (columns
`label,Content`, BIO labels like B1A/I15) verified against the real archive
(sha256 769bc7da...) on 2026-07-10, see docs/research/giants_task2.md section 4.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from fetch_ntu_itemseg import (  # noqa: E402
    DATASET_SHA256,
    gold_csv_path,
    gold_line_labels,
    label_to_item,
    load_report_list,
    parse_bio_csv,
    verify_archive,
)
from head_to_head import MAX_SLICE, score_engine_lines, stratified_slice  # noqa: E402


# -- fetch_ntu_itemseg loaders ---------------------------------------------------

def test_label_to_item_mapping():
    assert label_to_item("B1A") == "1A"
    assert label_to_item("I15") == "15"
    assert label_to_item("B9B") == "9B"
    assert label_to_item("O") is None


def test_parse_bio_csv_and_gold_labels(tmp_path):
    csv_path = tmp_path / "uid_1.csv"
    csv_path.write_text(
        'label,Content\n'
        'O,SECURITIES AND EXCHANGE COMMISSION\n'
        'B1,Item 1. Business\n'
        'I1,"We make widgets, mostly."\n'
        'B1A,Item 1A. Risk Factors\n'
        'I1A,Widgets may explode.\n',
        encoding="utf-8")
    rows = parse_bio_csv(csv_path)
    assert len(rows) == 5
    assert rows[2] == ("I1", "We make widgets, mostly.")
    assert gold_line_labels(rows) == [None, "1", "1", "1A", "1A"]


def test_load_report_list_and_gold_path(tmp_path):
    (tmp_path / "report_list.csv").write_text(
        "fold,uid,cik,company name,h_p_report,date_filed,Link to edgar,SIC\n"
        "train,10212218,1025315,24HOLDINGS INC,2008/12/31,2009/02/23,"
        "https://www.sec.gov/Archives/edgar/data/1025315/x.htm,6770\n"
        "test,10212501,42,AMERON,2008/11/30,2009/02/01,"
        "https://www.sec.gov/Archives/edgar/data/42/y.htm,3272\n",
        encoding="utf-8")
    reports = load_report_list(tmp_path)
    assert [r["fold"] for r in reports] == ["train", "test"]
    assert reports[1]["uid"] == "10212501"
    assert reports[1]["link"].endswith("y.htm")
    assert gold_csv_path(tmp_path, "10212501", "test") == tmp_path / "test_csv" / "uid_10212501.csv"
    assert gold_csv_path(tmp_path, "10212218", "train") \
        == tmp_path / "training_csv" / "uid_10212218.csv"


def test_verify_archive_rejects_wrong_bytes(tmp_path):
    fake = tmp_path / "itemseg10kdata.7z"
    fake.write_bytes(b"not the dataset")
    with pytest.raises(ValueError, match="size"):
        verify_archive(fake)
    assert len(DATASET_SHA256) == 64


# -- head_to_head scoring ----------------------------------------------------------

def _gold_rows():
    # Item 1: two substantive lines; Item 1A: two lines; one outside line.
    return [
        ("O", "UNITED STATES SECURITIES AND EXCHANGE COMMISSION"),
        ("B1", "Item 1. Business Overview"),
        ("I1", "We manufacture industrial widgets for the aerospace market."),
        ("B1A", "Item 1A. Risk Factors and Uncertainties"),
        ("I1A", "Our widgets may fail under sustained thermal load conditions."),
    ]


def test_score_perfect_engine():
    engine = {
        "1": "Item 1. Business Overview\nWe manufacture industrial widgets "
             "for the aerospace market.",
        "1A": "Item 1A. Risk Factors and Uncertainties\nOur widgets may fail "
              "under sustained thermal load conditions.",
    }
    scored = score_engine_lines(_gold_rows(), engine)
    assert scored["items"]["1"]["f1"] == 1.0
    assert scored["items"]["1A"]["f1"] == 1.0
    assert scored["macro_f1"] == 1.0


def test_score_missing_and_partial_items():
    engine = {
        # item 1 only got its heading line, not the body
        "1": "Item 1. Business Overview",
        # item 1A missing entirely; engine hallucinated the SEC cover line as item 2
        "2": "UNITED STATES SECURITIES AND EXCHANGE COMMISSION",
    }
    scored = score_engine_lines(_gold_rows(), engine)
    one = scored["items"]["1"]
    assert one["tp"] == 1 and one["fn"] == 1
    assert 0 < one["f1"] < 1
    assert scored["items"]["1A"] == {"tp": 0, "fp": 0, "fn": 2,
                                     "precision": 0.0, "recall": 0.0, "f1": 0.0}
    # fp-only item appears with zero F1 but does not enter macro (no gold lines)
    assert scored["items"]["2"]["fp"] == 1
    assert scored["macro_f1"] == round((scored["items"]["1"]["f1"] + 0.0) / 2, 4)


def test_score_normalization_is_rendering_robust():
    # engine text differs in case, whitespace, punctuation — still a match
    engine = {"1": "  ITEM 1 —  BUSINESS   OVERVIEW!!  we MANUFACTURE industrial\n"
                   "widgets ,for the aerospace market ."}
    scored = score_engine_lines(_gold_rows(), engine)
    assert scored["items"]["1"]["recall"] == 1.0


def test_short_lines_are_not_scored():
    rows = [("I1", "42"), ("I1", "Substantive line about widget manufacturing.")]
    scored = score_engine_lines(rows, {"1": "Substantive line about widget manufacturing."})
    assert scored["gold_lines_scored"] == 1
    assert scored["items"]["1"]["f1"] == 1.0


# -- slice selection ---------------------------------------------------------------

def _reports(n):
    return [{"fold": "test", "uid": str(i), "date_filed": f"2009/{i % 12 + 1:02d}/01"}
            for i in range(n)]


def test_stratified_slice_caps_at_bound():
    with pytest.raises(ValueError, match="bound"):
        stratified_slice(_reports(100), MAX_SLICE + 1)


def test_stratified_slice_even_spread_and_fold_filter():
    reports = _reports(90) + [{"fold": "train", "uid": "x", "date_filed": "2009/01/01"}]
    out = stratified_slice(reports, 9)
    assert len(out) == 9
    assert all(r["fold"] == "test" for r in out)
    assert len({r["uid"] for r in out}) == 9
    # asking for more than the pool returns the whole pool, no crash
    assert len(stratified_slice(_reports(5), 30)) == 5
