"""Operational risk bands for SEC item confidence (Task 2, TODO.md P0 L15).

Why bands and not a probability
-------------------------------
The confidence-recalibration experiment (TODO.md P0 "Task 2 confidence
recalibration", docs/eval_report.md) set the gate AUROC >= 0.75 / ECE <= 0.10
on the untouched NTU human-labeled gold. The frozen result MISSED it:

    strata.ntu_human_labeled.auroc = 0.6667  (< 0.75)   # gate MISS
    strata.ntu_human_labeled.ece   = 0.1235  (> 0.10)
    (data/sec_eval/calibration/calibration.json)

TODO.md L15 promised: "若未達標,UI 改顯示 risk band,不宣稱 probability." This
module is that promise — it maps a raw item confidence to an operational risk
band carrying a *measured* false-pass rate, never a calibrated probability.

Derivation (never invented — recomputed by tests/test_risk_band.py)
-------------------------------------------------------------------
Bands aggregate the frozen per-confidence reliability bins of the primary
human-labeled stratum (`strata.ntu_human_labeled.reliability_bins`, n=512,
n_correct=394). Each band's measured false-pass rate is its band-local error
rate = 1 - (sum correct / sum n) over the bins it covers, where per-bin
correct = round(accuracy * n):

    band          confidence      bins covered           n    correct  false_pass
    低風險 low      c >= 0.9        [0.9,1.0)             273   231      42/273 = 0.1538
    中風險 medium   0.6 <= c < 0.9  [0.6,0.7)..[0.8,0.9)  124    94      30/124 = 0.2419
    需人工 review   c < 0.6         [0.0,0.1)..[0.5,0.6)  115    69      46/115 = 0.4000

The three band supports sum to n=512 and their correct counts to 394, matching
the stratum totals exactly (the test asserts this). Boundaries 0.6 and 0.9 are
measured reliability-bin edges; 0.6 is also the deployed clean-pass gate floor
(`verifier_false_pass.gate` = "needs_review == False and confidence >= 0.6").

The confidence here is the same raw score swept in the calibration artifact, so
a band reports the measured false-pass rate of items *at that confidence level*
on the human-labeled gold — not an item-specific probability (which the missed
AUROC gate forbids claiming).
"""

from __future__ import annotations

from dataclasses import dataclass

# --- calibration provenance (frozen artifact values, surfaced to the UI) -----
STRATUM = "ntu_human_labeled"
N_ITEMS = 512
N_CORRECT = 394
AUROC = 0.6667
AUROC_GATE = 0.75
ECE = 0.1235
GATE_MISSED = AUROC < AUROC_GATE  # True — hence risk bands, not probabilities


@dataclass(frozen=True)
class RiskBand:
    """A confidence bracket with its measured NTU-gold false-pass rate."""

    band: str          # stable id: "low" | "medium" | "review"
    label: str         # zh-TW display label
    lo: float          # inclusive lower confidence bound
    hi: float          # upper confidence bound (top band is inclusive at 1.0)
    n: int             # band support in the calibration stratum
    correct: int       # correct items in the band (reliability-bin recompute)

    @property
    def false_pass_rate(self) -> float:
        """Measured P(incorrect | confidence in this band) on NTU human gold."""
        return (self.n - self.correct) / self.n


# Derived from data/sec_eval/calibration/calibration.json
# strata.ntu_human_labeled.reliability_bins (see docstring; test recomputes).
_LOW = RiskBand("low", "低風險", 0.9, 1.0, 273, 231)
_MEDIUM = RiskBand("medium", "中風險", 0.6, 0.9, 124, 94)
_REVIEW = RiskBand("review", "需人工", 0.0, 0.6, 115, 69)

# Ordered low-confidence -> high-confidence.
BANDS: tuple[RiskBand, ...] = (_REVIEW, _MEDIUM, _LOW)


def band_for(confidence: float) -> RiskBand:
    """Map a raw item confidence to its operational risk band."""
    c = float(confidence)
    if c >= _LOW.lo:
        return _LOW
    if c >= _MEDIUM.lo:
        return _MEDIUM
    return _REVIEW


def band_payload(confidence: float) -> dict:
    """Compact per-item band descriptor for the API/UI (no probability claim)."""
    b = band_for(confidence)
    return {
        "band": b.band,
        "label": b.label,
        "false_pass_rate": round(b.false_pass_rate, 4),
        "lo": b.lo,
        "hi": b.hi,
        "n": b.n,
    }
