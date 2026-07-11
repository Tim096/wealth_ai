"""Scoring-layer tests (T2-2): char-offset span F1 + present/null/MISSING
tri-state mapping + gold-freeze rules. Pure logic on dicts, plus one
end-to-end round trip that freezes gold from the alpha fixture extraction
and scores the same extraction back (must be a perfect 1.0 — and must drop
when a boundary is perturbed).
"""

import json
from pathlib import Path

import pytest

from sec_core.pipeline import extract_from_html
from sec_core.scoring import score_filing, span_prf, tristate
from tools.freeze_offset_gold import freeze

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "data" / "sec_eval" / "fixtures"


# --- tri-state mapping ---
@pytest.mark.parametrize("status,toc_listed,expected", [
    ("pass", False, "present"),
    ("partial", True, "present"),
    ("ambiguous", False, "present"),
    ("reserved", True, "null"),
    ("incorporated_by_reference", True, "null"),
    ("missing", True, "MISSING"),
    ("missing", False, "null"),
    ("unsupported", True, "unsupported"),
])
def test_tristate_mapping(status, toc_listed, expected):
    assert tristate(status, toc_listed) == expected


# --- span P/R/F1 ---
def test_span_prf_exact_match_is_perfect():
    assert span_prf(100, 200, 100, 200) == (1.0, 1.0, 1.0)


def test_span_prf_disjoint_is_zero():
    assert span_prf(0, 100, 200, 300) == (0.0, 0.0, 0.0)


def test_span_prf_pred_superset_costs_precision_not_recall():
    p, r, f1 = span_prf(0, 200, 50, 150)
    assert r == 1.0
    assert p == 0.5
    assert f1 == pytest.approx(2 * 0.5 / 1.5)


def test_span_prf_empty_pred_is_zero():
    assert span_prf(0, 0, 100, 200) == (0.0, 0.0, 0.0)


# --- score_filing outcomes ---
def _record(items):
    return {"ticker": "T", "accession": "acc-1", "items": items}


def _gold(items):
    return {"ticker": "T", "accession": "acc-1", "items": items}


def test_matched_item_scores_f1_and_sha_exact():
    rec = _record({"1": {"status": "pass", "toc_listed": True,
                         "start_offset": 10, "end_offset": 110, "text_sha256": "abc"}})
    gold = _gold({"1": {"state": "present", "start_offset": 10, "end_offset": 110,
                        "text_sha256": "abc"}})
    s = score_filing(rec, gold)
    assert s["outcome_counts"] == {"matched": 1}
    assert s["macro_f1"] == 1.0
    assert s["items"][0]["sha_check"] == "sha_exact"


def test_same_offsets_different_sha_flags_normalization_drift():
    rec = _record({"1": {"status": "pass", "toc_listed": True,
                         "start_offset": 10, "end_offset": 110, "text_sha256": "abc"}})
    gold = _gold({"1": {"state": "present", "start_offset": 10, "end_offset": 110,
                        "text_sha256": "DIFFERENT"}})
    s = score_filing(rec, gold)
    assert s["items"][0]["sha_check"] == "normalization_drift"


def test_omission_counts_and_scores_zero_in_macro_f1():
    rec = _record({"1": {"status": "missing", "toc_listed": True,
                         "start_offset": 0, "end_offset": 0, "text_sha256": ""}})
    gold = _gold({"1": {"state": "present", "start_offset": 10, "end_offset": 110,
                        "text_sha256": "abc"}})
    s = score_filing(rec, gold)
    assert s["outcome_counts"] == {"omission": 1}
    assert s["macro_f1"] == 0.0  # omission stays in the average — honesty over flattery


def test_hallucination_is_separated_from_omission():
    rec = _record({"6": {"status": "pass", "toc_listed": False,
                         "start_offset": 5, "end_offset": 50, "text_sha256": "x"}})
    gold = _gold({"6": {"state": "null", "reason": "reserved"}})
    s = score_filing(rec, gold)
    assert s["outcome_counts"] == {"hallucination": 1}
    assert s["offset_items"] == 0  # no gold span -> never enters F1


def test_false_missing_alarm_and_correct_null():
    rec = _record({
        "9C": {"status": "missing", "toc_listed": True,
               "start_offset": 0, "end_offset": 0, "text_sha256": ""},
        "16": {"status": "missing", "toc_listed": False,
               "start_offset": 0, "end_offset": 0, "text_sha256": ""},
    })
    gold = _gold({"9C": {"state": "null"}, "16": {"state": "null"}})
    s = score_filing(rec, gold)
    assert s["outcome_counts"] == {"false_missing_alarm": 1, "correct_null": 1}


def test_unverified_gold_is_excluded_from_scoring():
    rec = _record({"2": {"status": "pass", "toc_listed": True,
                         "start_offset": 0, "end_offset": 10, "text_sha256": "x"}})
    gold = _gold({"2": {"state": "unverified"}})
    s = score_filing(rec, gold)
    assert s["outcome_counts"] == {"excluded": 1}
    assert s["macro_f1"] is None


def test_accession_mismatch_is_visible():
    rec = {"ticker": "T", "accession": "acc-OTHER", "items": {}}
    s = score_filing(rec, _gold({}))
    assert s["accession_match"] is False


# --- freeze rules ---
def _tri(verdicts):
    return {"records": [{"ticker": "T", "items":
                         {k: {"verdict": v} for k, v in verdicts.items()}}]}


def test_freeze_only_blesses_third_engine_agreement():
    rec = _record({
        "1": {"status": "pass", "needs_review": False, "toc_listed": True,
              "start_offset": 10, "end_offset": 110, "text_sha256": "abc"},
        "2": {"status": "pass", "needs_review": False, "toc_listed": True,
              "start_offset": 200, "end_offset": 300, "text_sha256": "def"},
        "3": {"status": "pass", "needs_review": True, "toc_listed": True,
              "start_offset": 400, "end_offset": 500, "text_sha256": "ghi"},
    })
    gold = freeze(rec, _tri({"1": "agree", "2": "disagree", "3": "agree"}))
    assert gold["items"]["1"]["start_offset"] == 10
    assert gold["items"]["1"]["text_sha256"] == "abc"
    assert "start_offset" not in gold["items"]["2"]  # disagree -> no offset gold
    assert "offsets_excluded" in gold["items"]["2"]
    assert "start_offset" not in gold["items"]["3"]  # needs_review -> no offset gold


def test_freeze_null_and_unverified_states():
    rec = _record({
        "6": {"status": "reserved", "needs_review": False, "toc_listed": True,
              "start_offset": 0, "end_offset": 0, "text_sha256": ""},
        "10": {"status": "incorporated_by_reference", "needs_review": True,
               "toc_listed": True, "start_offset": 0, "end_offset": 5, "text_sha256": "p"},
        "9C": {"status": "missing", "needs_review": False, "toc_listed": False,
               "start_offset": 0, "end_offset": 0, "text_sha256": ""},
        "16": {"status": "missing", "needs_review": False, "toc_listed": True,
               "start_offset": 0, "end_offset": 0, "text_sha256": ""},
    })
    gold = freeze(rec, _tri({}))
    assert gold["items"]["6"]["state"] == "null"
    assert gold["items"]["10"]["state"] == "null"
    assert gold["items"]["9C"]["state"] == "null"
    assert gold["items"]["16"]["state"] == "unverified"  # TOC claims it — no blessing


# --- end-to-end round trip on the alpha fixture ---
@pytest.fixture(scope="module")
def alpha_record():
    raw = (FIXTURES / "alpha_10k.html").read_text(encoding="utf-8")
    result = extract_from_html(raw, "alpha_10k")
    toc_codes = {c.code for c in result.candidates if c.toc_rejected}
    items = {
        seg.item_code: {
            "status": seg.status,
            "needs_review": seg.needs_review,
            "toc_listed": seg.item_code in toc_codes,
            "start_offset": seg.start_offset,
            "end_offset": seg.end_offset,
            "text_sha256": seg.text_sha256,
        }
        for seg in result.segments
    }
    return {"ticker": "ALPHA", "accession": "fixture", "items": items}


def test_round_trip_self_score_is_perfect(alpha_record):
    tri = {"records": [{"ticker": "ALPHA", "items":
                        {code: {"verdict": "agree"} for code in alpha_record["items"]}}]}
    gold = freeze(alpha_record, tri)
    s = score_filing(alpha_record, gold)
    assert s["macro_f1"] == 1.0
    assert s["outcome_counts"].get("omission", 0) == 0
    assert s["outcome_counts"].get("hallucination", 0) == 0
    assert all(r.get("sha_check", "sha_exact") == "sha_exact" for r in s["items"])


def test_round_trip_detects_perturbed_boundary(alpha_record):
    tri = {"records": [{"ticker": "ALPHA", "items":
                        {code: {"verdict": "agree"} for code in alpha_record["items"]}}]}
    gold = freeze(alpha_record, tri)
    perturbed = json.loads(json.dumps(alpha_record))
    perturbed["items"]["7"]["start_offset"] += 500
    perturbed["items"]["7"]["text_sha256"] = "changed"
    s = score_filing(perturbed, gold)
    assert s["macro_f1"] < 1.0
    row7 = next(r for r in s["items"] if r["item"] == "7")
    assert row7["f1"] < 1.0
    assert row7["sha_check"] == "boundary_moved"


# --- sensitivity injection on real committed sweep3 (locks the eval_report
# sensitivity numbers: the scorer must not be a rubber stamp on real data) ---
SWEEP3 = ROOT / "data" / "sec_eval" / "records" / "sweep3"
OFFSET_GOLD = ROOT / "data" / "golden_labels" / "offsets"


def test_sensitivity_injection_on_real_sweep3_aapl():
    rec = json.loads((SWEEP3 / "AAPL.json").read_text(encoding="utf-8-sig"))
    gold = json.loads((OFFSET_GOLD / "AAPL.json").read_text(encoding="utf-8-sig"))
    assert score_filing(rec, gold)["macro_f1"] == 1.0  # constructive baseline

    mutated = json.loads(json.dumps(rec))
    # 1) boundary regression: truncate Item 1A by 20k chars
    mutated["items"]["1A"]["end_offset"] -= 20000
    mutated["items"]["1A"]["text_sha256"] = "mutated"
    # 2) omission: Item 3 vanishes although the TOC advertises it
    mutated["items"]["3"]["status"] = "missing"
    mutated["items"]["3"]["toc_listed"] = True
    # 3) hallucination: Item 6 (gold null, reserved) claims content
    mutated["items"]["6"]["status"] = "pass"

    s = score_filing(mutated, gold)
    assert (s["macro_precision"], s["macro_recall"], s["macro_f1"]) == (
        0.9375, 0.9191, 0.9267)
    assert s["outcome_counts"]["omission"] == 1
    assert s["outcome_counts"]["hallucination"] == 1
    rows = {r["item"]: r for r in s["items"]}
    assert rows["1A"]["outcome"] == "matched" and rows["1A"]["f1"] < 1.0
    assert rows["1A"]["sha_check"] == "boundary_moved"
    assert rows["3"]["outcome"] == "omission" and rows["3"]["f1"] == 0.0
    assert rows["6"]["outcome"] == "hallucination"
