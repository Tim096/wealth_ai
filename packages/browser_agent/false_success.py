"""Lightweight false-success detector (T1-6, SPEC eval-upgrade — opt-in triage).

A verifier FORE-triage. It reads a trajectory record and emits a suspicion
score + flag for "claimed success that may actually be a false success" (the
agent/self-report says done, the environment state disagrees — arxiv 2606.09863).

It NEVER changes the verdict. The verifier stays the sole judge (project law);
this detector only produces a hint for human / adjudicator review. It is opt-in
and off the core pipeline: nothing in run()/verify_contract calls it.

Route: HEURISTIC (interpretable features), because labeled trajectories are far
below the ~60 needed to train a model. The TF-IDF + XGBoost detector from the
source paper (AUROC 0.83 / 0.95, ~3300x faster than an LLM judge, same flag rate
but 4-8x more true catches — arxiv 2606.09863) is a roadmap item pending
trajectory collection; see tools/false_success_detector.py and the
`roadmap` block written into detector_results.json.

Design note on the features: the paper's core warning is that an LLM JUDGE gets
fooled because it OVER-weights a single surface proxy — confident closing tone,
action-sequence length — which are anti-correlated with truth. We therefore (a)
keep every feature transparent and (b) make the two surface proxies (length,
confident-closing) individually too weak to flag on their own: only a real
claim-vs-evidence contradiction, or an accumulation of proxies, crosses the bar.
"""

from __future__ import annotations

from typing import Any

from .trajectory import repetition_report

# Substrings that, when they share a line with a required success needle, mean
# the needle is almost certainly an ECHO of the query / a negative status line
# rather than a real hit (e.g. `0 results for "teleporter"`). Lower-cased match.
NEGATIVE_MARKERS = (
    "0 results", "no results", "no matches", "not found", "nothing found",
    "are you a robot", "captcha", "verify you are human", "access denied",
)

# Feature weights. Contradiction signals are strong enough to flag alone; the two
# surface proxies (confident_closing, length_anomaly) are deliberately weak so a
# lone proxy can never flag — mirroring the paper's caution against judges that
# do exactly that.
_W = {
    "claim_evidence_gap": 0.60,
    "hallucinated_claim": 0.60,
    "repetition": 0.25,
    "confident_closing": 0.25,
    "length_anomaly": 0.20,
}

# Reference band for a legit success trajectory on our mock sites (script/agent
# mode search tasks settle in ~2-4 steps, 0-2 repairs). Overridable per call.
REF_STEPS = 6
REF_REPAIRS = 2
FLAG_THRESHOLD = 0.5


def _lower_lines(text: str) -> list[str]:
    return [ln.strip().lower() for ln in text.splitlines() if ln.strip()]


def _claimed_success(record: dict[str, Any]) -> bool:
    """Did this trajectory CLAIM success? Triage only applies to claimed passes —
    an honest FAIL is not a false success. Reads the record's own top-level status
    and the verifier block; both are the trajectory's self-presentation, not
    ground truth."""
    if str(record.get("status", "")).lower() == "pass":
        return True
    v = record.get("verifier") or {}
    return str(v.get("status", "")).lower() == "pass"


def _feat_repetition(record: dict[str, Any]) -> tuple[float, str | None]:
    steps = record.get("steps") or []
    rep = record.get("repetition")
    if not rep:
        if not steps:
            return 0.0, None  # no trajectory detail available -> feature silent
        # reconstruct StepTrace-like objects: repetition_report reads attributes
        rep = repetition_report([_StepView(s) for s in steps])
    loop = bool(rep.get("loop_detected"))
    score = float(rep.get("repetition_score") or 0.0)
    if loop or score >= 0.34:
        return 1.0, (
            f"repetition: loop_detected={loop}, "
            f"repetition_score={round(score, 3)}"
        )
    return 0.0, None


def _feat_length(record: dict[str, Any], ref_steps: int, ref_repairs: int) -> tuple[float, str | None]:
    steps = record.get("steps") or []
    n_steps = len(steps) if steps else record.get("n_steps")
    repairs = record.get("repairs")
    hits = []
    if isinstance(n_steps, int) and n_steps > ref_steps * 2:
        hits.append(f"n_steps={n_steps}>2x ref({ref_steps})")
    if isinstance(repairs, int) and repairs > ref_repairs:
        hits.append(f"repairs={repairs}>ref({ref_repairs})")
    if hits:
        return 1.0, "length_anomaly: " + ", ".join(hits)
    return 0.0, None


def _feat_confident_closing(record: dict[str, Any]) -> tuple[float, str | None]:
    """Confident closing despite execution trouble: high asserted confidence yet
    the trajectory shows repairs / a failed step / a recorded diagnosis. The paper
    finds confident closing correlates with false success — used only as a WEAK
    proxy here, never a lone flag."""
    conf = record.get("confidence")
    if not isinstance(conf, (int, float)) or conf < 0.9:
        return 0.0, None
    steps = record.get("steps") or []
    trouble = []
    if isinstance(record.get("repairs"), int) and record["repairs"] > 0:
        trouble.append(f"repairs={record['repairs']}")
    if any(s.get("ok") is False for s in steps):
        trouble.append("a step ok=false")
    if any((s.get("diagnosis") or "") for s in steps):
        trouble.append("a diagnosis recorded")
    if trouble:
        return 1.0, f"confident_closing: confidence={conf} despite " + ", ".join(trouble)
    return 0.0, None


def _feat_claim_evidence_gap(record: dict[str, Any]) -> tuple[float, str | None]:
    """Direct claim-vs-evidence contradiction. Two channels:
      1. verifier claims pass yet lists missing evidence (internally inconsistent);
      2. a required success needle shares a line with a NEGATIVE_MARKER in the
         observed visible_text -> the needle is an echo (`0 results for "x"`),
         not a real hit. This is the query-echo silent-failure family (FG-BROWSER,
         arxiv 2507.08794 one-token-to-fool)."""
    reasons = []
    v = record.get("verifier") or {}
    if str(v.get("status", "")).lower() == "pass" and (v.get("missing") or []):
        reasons.append(f"verifier pass but missing={v.get('missing')}")

    evidence = record.get("evidence") or {}
    visible = evidence.get("visible_text") or record.get("visible_text") or ""
    needles = [str(n).lower() for n in (record.get("success_needles") or []) if str(n).strip()]
    if visible and needles:
        for line in _lower_lines(visible):
            if any(m in line for m in NEGATIVE_MARKERS):
                echoed = [n for n in needles if n in line]
                if echoed:
                    reasons.append(
                        f"success needle {echoed} appears only in a negative line: "
                        f"{line[:80]!r}"
                    )
                    break
    if reasons:
        return 1.0, "claim_evidence_gap: " + "; ".join(reasons)
    return 0.0, None


def _feat_hallucinated_claim(record: dict[str, Any]) -> tuple[float, str | None]:
    """A self-report asserts a required needle that is ABSENT from observed
    evidence — the hallucinated-final-response failure WebJudge cites as the main
    source of judge false positives (arxiv 2504.01382). Needs both a `claim` text
    and observed evidence; silent otherwise."""
    claim = str(record.get("claim") or "").lower()
    evidence = record.get("evidence") or {}
    visible = (evidence.get("visible_text") or record.get("visible_text") or "").lower()
    needles = [str(n).lower() for n in (record.get("success_needles") or []) if str(n).strip()]
    if not claim or not visible or not needles:
        return 0.0, None
    hallucinated = [n for n in needles if n in claim and n not in visible]
    if hallucinated:
        return 1.0, (
            f"hallucinated_claim: self-report asserts {hallucinated} "
            f"absent from observed evidence"
        )
    return 0.0, None


class _StepView:
    """Adapts a step dict to the attribute access repetition_report expects."""

    __slots__ = ("action", "selector_used", "step")

    def __init__(self, d: dict[str, Any]) -> None:
        self.action = d.get("action", "")
        self.selector_used = d.get("selector_used", "")
        self.step = d.get("step", "")


def detect_false_success(
    record: dict[str, Any],
    *,
    ref_steps: int = REF_STEPS,
    ref_repairs: int = REF_REPAIRS,
    flag_threshold: float = FLAG_THRESHOLD,
) -> dict[str, Any]:
    """Score one trajectory record for false-success risk. Returns a triage dict;
    the verdict is untouched. `applicable` is False when the trajectory did not
    claim success (an honest fail is not a false success) — such records get
    score 0 and flag False, and are excluded from triage precision/recall.

    A record is any dict with (all optional): status, confidence, repairs, steps[],
    verifier{status,observed,missing}, and — for the strongest signals —
    evidence{visible_text} or visible_text, success_needles[], claim (self-report).
    """
    applicable = _claimed_success(record)
    features: dict[str, float] = {}
    reasons: list[str] = []

    extractors = {
        "claim_evidence_gap": _feat_claim_evidence_gap(record),
        "hallucinated_claim": _feat_hallucinated_claim(record),
        "repetition": _feat_repetition(record),
        "confident_closing": _feat_confident_closing(record),
        "length_anomaly": _feat_length(record, ref_steps, ref_repairs),
    }
    for name, (val, why) in extractors.items():
        features[name] = val
        if why:
            reasons.append(why)

    if applicable:
        score = min(1.0, round(sum(_W[k] * v for k, v in features.items()), 6))
    else:
        score = 0.0
    flag = applicable and score >= flag_threshold

    return {
        "applicable": applicable,
        "flag": bool(flag),
        "score": score,
        "flag_threshold": flag_threshold,
        "features": features,
        "reasons": reasons,
        "verdict_unchanged": True,  # invariant: triage never overrides the verifier
        "note": (
            "triage hint only — the verifier remains the sole judge"
            if applicable
            else "not a claimed success; false-success triage does not apply"
        ),
    }
