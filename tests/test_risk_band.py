"""Risk-band mapping: boundaries and per-band false-pass rates must be derived
from the frozen calibration artifact, never invented (TODO.md L15).

The module packages/sec_core/risk_band.py hardcodes derived constants; these
tests recompute them from data/sec_eval/calibration/calibration.json and assert
exact consistency, and check the band is wired into the SEC API item payload.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

os.environ["PREWARM_TICKERS"] = ""  # no EDGAR at app import

from sec_core import risk_band as rb

ROOT = Path(__file__).resolve().parents[1]
CALIB = ROOT / "data" / "sec_eval" / "calibration" / "calibration.json"
FIXTURES = ROOT / "data" / "sec_eval" / "fixtures"


def _stratum() -> dict:
    return json.loads(CALIB.read_text(encoding="utf-8"))["strata"][rb.STRATUM]


def _bins_for(lo: float, hi: float, bins: list[dict]) -> tuple[int, int]:
    """Aggregate reliability bins fully inside [lo, hi): (sum n, sum correct)
    with per-bin correct = round(accuracy * n) — the artifact's own numbers."""
    n = c = 0
    for b in bins:
        if b["n"] == 0:
            continue
        if b["lo"] >= lo and b["hi"] <= hi:
            n += b["n"]
            c += round(b["accuracy"] * b["n"])
    return n, c


# ----------------------------------------------------- precondition: gate MISS
def test_auroc_gate_is_actually_missed():
    s = _stratum()
    assert s["auroc"] == rb.AUROC
    assert rb.AUROC < rb.AUROC_GATE          # 0.6667 < 0.75 → bands, not prob.
    assert rb.GATE_MISSED is True


# --------------------------------------------- boundaries + per-band recompute
def test_band_supports_and_false_pass_match_artifact():
    bins = _stratum()["reliability_bins"]
    for band in rb.BANDS:
        n, correct = _bins_for(band.lo, band.hi if band.hi < 1.0 else 1.0, bins)
        assert n == band.n, f"{band.band}: n {band.n} != artifact {n}"
        assert correct == band.correct, f"{band.band}: correct mismatch"
        # false_pass_rate is a pure function of (n, correct) — recompute it
        assert band.false_pass_rate == (n - correct) / n


def test_bands_partition_the_whole_stratum():
    s = _stratum()
    assert sum(b.n for b in rb.BANDS) == s["n_items"] == rb.N_ITEMS
    assert sum(b.correct for b in rb.BANDS) == s["n_correct"] == rb.N_CORRECT


def test_boundaries_are_real_reliability_bin_edges():
    bins = _stratum()["reliability_bins"]
    edges = {b["lo"] for b in bins} | {b["hi"] for b in bins}
    for boundary in (0.6, 0.9):
        assert boundary in edges, f"{boundary} is not a measured bin edge"
    # 0.6 is also the deployed clean-pass gate floor (honest anchor)
    assert "confidence >= 0.6" in _stratum()["verifier_false_pass"]["gate"]


def test_false_pass_rates_are_monotonic_and_measured():
    low = rb.band_for(0.95)
    medium = rb.band_for(0.7)
    review = rb.band_for(0.3)
    assert (low.band, medium.band, review.band) == ("low", "medium", "review")
    assert low.false_pass_rate < medium.false_pass_rate < review.false_pass_rate
    # exact measured values from the artifact
    assert round(low.false_pass_rate, 4) == 0.1538
    assert round(medium.false_pass_rate, 4) == 0.2419
    assert round(review.false_pass_rate, 4) == 0.4000


# ------------------------------------------------------------ band_for mapping
def test_band_for_boundaries_are_inclusive_lower():
    assert rb.band_for(0.9).band == "low"
    assert rb.band_for(0.8999).band == "medium"
    assert rb.band_for(0.6).band == "medium"
    assert rb.band_for(0.5999).band == "review"
    assert rb.band_for(0.0).band == "review"
    assert rb.band_for(1.0).band == "low"


def test_band_payload_shape():
    p = rb.band_payload(0.95)
    assert p == {"band": "low", "label": "低風險", "false_pass_rate": 0.1538,
                 "lo": 0.9, "hi": 1.0, "n": 273}


# ---------------------------------------- API wiring: item payload carries band
def test_items_payload_attaches_risk_band_per_item():
    from sec_core.pipeline import extract_from_html

    from apps.services.sec.main import _items_payload

    raw = (FIXTURES / "alpha_10k.html").read_text(encoding="utf-8")
    result = extract_from_html(raw, "alpha_10k")
    payload = _items_payload(result, {"source": "ALPHA"}, [])

    assert payload["items"], "fixture produced no items"
    for it, seg in zip(payload["items"], result.segments):
        assert "risk_band" in it, f"item {it['code']} missing risk_band"
        band = it["risk_band"]
        assert set(band) == {"band", "label", "false_pass_rate", "lo", "hi", "n"}
        # the served band must equal the one the module derives from raw conf
        assert band["band"] == rb.band_for(seg.confidence).band
