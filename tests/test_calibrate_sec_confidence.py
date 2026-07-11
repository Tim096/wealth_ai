"""P0-3 verifier calibration curve — metric + collector unit tests."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from calibrate_sec_confidence import (  # noqa: E402
    CONF_GATE,
    auroc,
    collect_ntu,
    collect_pseudo_gold,
    ece,
    false_pass_point,
    risk_coverage,
    stratum_report,
)


def _s(conf, correct, needs_review=False):
    return {"confidence": conf, "correct": correct, "needs_review": needs_review}


# -- auroc ----------------------------------------------------------------------

def test_auroc_perfect_separation():
    samples = [_s(0.9, True), _s(0.8, True), _s(0.3, False), _s(0.2, False)]
    assert auroc(samples) == 1.0


def test_auroc_inverted():
    samples = [_s(0.1, True), _s(0.9, False)]
    assert auroc(samples) == 0.0


def test_auroc_all_tied_is_half():
    samples = [_s(0.5, True), _s(0.5, False), _s(0.5, True), _s(0.5, False)]
    assert auroc(samples) == 0.5


def test_auroc_single_class_undefined():
    assert auroc([_s(0.9, True), _s(0.8, True)]) is None
    assert auroc([]) is None


# -- ece ------------------------------------------------------------------------

def test_ece_perfectly_calibrated_bin():
    # one bin [0.7, 0.8): conf 0.75 mean, accuracy 0.75 -> ECE 0
    samples = [_s(0.75, True), _s(0.75, True), _s(0.75, True), _s(0.75, False)]
    e, bins = ece(samples)
    assert abs(e - 0.0) < 1e-9
    assert sum(b["n"] for b in bins) == 4


def test_ece_overconfident():
    # all conf 0.95, half correct -> |0.5 - 0.95| = 0.45
    samples = [_s(0.95, True), _s(0.95, False)]
    e, _ = ece(samples)
    assert abs(e - 0.45) < 1e-9


def test_ece_confidence_one_lands_in_top_bin():
    e, bins = ece([_s(1.0, True)])
    assert bins[-1]["n"] == 1


# -- risk-coverage ----------------------------------------------------------------

def test_risk_coverage_monotone_coverage_and_known_risks():
    samples = [_s(0.9, True), _s(0.8, True), _s(0.7, False), _s(0.6, True)]
    pts = risk_coverage(samples)
    assert [p["coverage"] for p in pts] == [0.25, 0.5, 0.75, 1.0]
    assert [p["risk"] for p in pts] == [0.0, 0.0, 0.3333, 0.25]


def test_risk_coverage_ties_enter_together():
    samples = [_s(0.9, True), _s(0.9, False), _s(0.5, True)]
    pts = risk_coverage(samples)
    # a threshold cannot split the two 0.9 items
    assert pts[0] == {"threshold": 0.9, "coverage": 0.6667, "risk": 0.5}


# -- false-pass gate ---------------------------------------------------------------

def test_false_pass_gate_matches_deliverable_b():
    samples = [
        _s(0.95, True),                       # clean pass, correct
        _s(0.9, False),                       # clean pass, WRONG -> false pass
        _s(0.9, False, needs_review=True),    # flagged: excluded from gate
        _s(0.3, False),                       # below CONF_GATE: excluded
    ]
    fp = false_pass_point(samples)
    assert fp["clean_pass_items"] == 2
    assert fp["false_pass_items"] == 1
    assert fp["false_pass_rate"] == 0.5
    assert fp["coverage"] == 0.5
    assert str(CONF_GATE) in fp["gate"]


def test_false_pass_gate_empty_is_none_not_zero():
    fp = false_pass_point([_s(0.1, False)])
    assert fp["false_pass_rate"] is None


# -- NTU collector -----------------------------------------------------------------

def _ntu_artifact():
    return {"filings": [
        {"uid": "42", "engines": {"ours": {
            "items": {
                "1": {"tp": 5, "fp": 0, "fn": 0, "f1": 1.0},     # correct
                "2": {"tp": 1, "fp": 9, "fn": 4, "f1": 0.2},     # wrong
                "3": {"tp": 0, "fp": 3, "fn": 0, "f1": 0.0},     # fp-only: skip
                "7A": {"tp": 0, "fp": 0, "fn": 2, "f1": 0.0},    # engine missing
            },
            "verifier": {
                "1": {"status": "pass", "confidence": 0.95, "needs_review": False},
                "2": {"status": "pass", "confidence": 0.7, "needs_review": True},
                "3": {"status": "pass", "confidence": 0.9, "needs_review": False},
                # no entry for 7A -> defaults conf 0.0 / needs_review False
            },
        }}},
        {"uid": "43", "engines": {"ours": {"error": "no items extracted"}}},
    ]}


def test_collect_ntu_labels_and_defaults():
    samples = collect_ntu(_ntu_artifact())
    by_item = {s["item"]: s for s in samples}
    assert set(by_item) == {"1", "2", "7A"}  # fp-only "3" has no gold lines
    assert by_item["1"]["correct"] is True
    assert by_item["2"]["correct"] is False and by_item["2"]["needs_review"] is True
    assert by_item["7A"]["confidence"] == 0.0 and by_item["7A"]["correct"] is False


def test_collect_ntu_skips_engine_failures():
    samples = collect_ntu(_ntu_artifact())
    assert all(s["filing"] == "ntu_42" for s in samples)


# -- pseudo-gold collector (edgartools excluded from the vote) ----------------------

def _pg_candidates():
    return {"records": [
        {"disposition": "voted", "cik": 1, "accession": "A-1", "items": {
            # corpus agree + edgartools agree -> correct (edgartools irrelevant)
            "1": {"teachers": {"corpus": {"verdict": "agree"},
                               "edgartools": {"verdict": "agree"}}},
            # corpus DISAGREE while edgartools agrees -> label must be WRONG:
            # the circularity-breaking case
            "15": {"teachers": {"corpus": {"verdict": "disagree"},
                                "edgartools": {"verdict": "agree"}}},
            # corpus no-signal -> dropped even though edgartools disagrees
            "9": {"teachers": {"corpus": {"verdict": "no_corpus_text"},
                               "edgartools": {"verdict": "disagree"}}},
        }},
        {"disposition": "hard_case:join_not_found", "cik": 2},
    ]}


def test_collect_pseudo_gold_corpus_only_label():
    conf = {"A-1": {"1": {"confidence": 0.98, "needs_review": False, "status": "pass"},
                    "15": {"confidence": 0.97, "needs_review": False, "status": "pass"}}}
    samples = collect_pseudo_gold(_pg_candidates(), conf)
    by_item = {s["item"]: s for s in samples}
    assert set(by_item) == {"1", "15"}  # "9" dropped: corpus no-signal
    assert by_item["1"]["correct"] is True
    assert by_item["15"]["correct"] is False  # edgartools' agree never voted
    assert by_item["15"]["confidence"] == 0.97


def test_collect_pseudo_gold_missing_confidence_defaults_zero():
    samples = collect_pseudo_gold(_pg_candidates(), {})
    assert all(s["confidence"] == 0.0 for s in samples)


# -- stratum report -----------------------------------------------------------------

def test_stratum_report_shape():
    rep = stratum_report([_s(0.9, True), _s(0.8, False), _s(0.2, False)])
    assert rep["n_items"] == 3 and rep["n_correct"] == 1
    assert rep["base_error_rate"] == 0.6667
    assert rep["auroc"] == 1.0  # pos {0.9} beats neg {0.8, 0.2}: 2/2 pairs
    assert len(rep["risk_coverage"]) == 3
    assert "verifier_false_pass" in rep
