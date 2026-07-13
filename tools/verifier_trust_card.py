"""Generate the Verifier Trust Card — a one-page scorecard for 「裁判本身可不可信」.

Every row is re-read from a tracked artifact (never a hand-typed number) and the
gate (PASS / MISS / n/a) is computed from that value, so a regenerated artifact
that fails its bar flips the card. Output is deterministic and timestamp-free:
`render()` returns the exact bytes written to docs/verifier_trust_card.md, and
tests/test_verifier_trust_card.py asserts the committed file still matches a
fresh render (drift gate) — a hand edit to the doc is therefore always caught.

Sources (all tracked):
  data/browser_eval/calibration/calibration_results.json   sensitivity/specificity, Rogan-Gladen
  data/sec_eval/calibration/calibration.json               NTU AUROC vs 0.75 gate
  data/sec_eval/calibration/topic_prior_attribution.json   needs_review interception (77/118)
  data/sec_eval/certification/item8_certification.json     XBRL certified/contradicted census
  data/sec_eval/cyd_groundtruth/cyd_agreement.json         CYD oracle agreement census
  data/browser_eval/impossible/impossible_results.json     silent-failure / honest-outcome rate
  data/sec_eval/triangulation/triangulation.json           third-engine agree/disagree census
  data/sec_eval/records/sweep3/                             sweep3 recorded verifier outputs
  data/claims_registry.json                                mutation-harness registry pins

The mutation-harness recall is recomputed by the harness at test time (no stored
per-run artifact); its value here is the registry pin, re-derived by the cited
pytest command. The clean false-alarm is computed by this tool from the sweep3
records + triangulation verdicts (same definition as the harness).

Usage:
  .venv/Scripts/python tools/verifier_trust_card.py [--check]

--check exits 1 (without rewriting) if docs/verifier_trust_card.md has drifted.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "verifier_trust_card.md"

BROWSER_CAL = ROOT / "data" / "browser_eval" / "calibration" / "calibration_results.json"
SEC_CAL = ROOT / "data" / "sec_eval" / "calibration" / "calibration.json"
ATTRIBUTION = ROOT / "data" / "sec_eval" / "calibration" / "topic_prior_attribution.json"
CERTIFICATION = ROOT / "data" / "sec_eval" / "certification" / "item8_certification.json"
CYD = ROOT / "data" / "sec_eval" / "cyd_groundtruth" / "cyd_agreement.json"
IMPOSSIBLE = ROOT / "data" / "browser_eval" / "impossible" / "impossible_results.json"
TRIANGULATION = ROOT / "data" / "sec_eval" / "triangulation" / "triangulation.json"
SWEEP3 = ROOT / "data" / "sec_eval" / "records" / "sweep3"
REGISTRY = ROOT / "data" / "claims_registry.json"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _walk(obj: Any, dot_path: str) -> Any:
    """Follow a dot-separated key path through nested JSON dicts (verify_claims.py)."""
    for key in dot_path.split("."):
        if not isinstance(obj, dict) or key not in obj:
            raise KeyError(f"path segment {key!r} not found (full path: {dot_path})")
        obj = obj[key]
    return obj


def _registry_expected(claim_id: str) -> Any:
    for claim in _load_json(REGISTRY):
        if claim.get("claim_id") == claim_id:
            return claim["expected"]
    raise KeyError(f"claim_id {claim_id!r} not in {REGISTRY.name}")


def _sweep3_clean_false_alarm() -> tuple[int, int, float]:
    """Same computation as tests/test_verifier_mutations.py::_sweep3_recorded_false_alarm
    and verify_claims.py: over all items the pipeline passed, the rate at which the
    recorded verifier outputs (needs_review flag or a triangulation disagree) alarmed."""
    tri = _load_json(TRIANGULATION)
    tri_by = {r["ticker"]: r["items"] for r in tri["records"]}
    total = alarms = 0
    for path in sorted(SWEEP3.glob("*.json")):
        rec = _load_json(path)
        for code, item in rec["items"].items():
            if item["status"] != "pass":
                continue
            total += 1
            verdict = tri_by.get(rec["ticker"], {}).get(code, {}).get("verdict")
            if item["needs_review"] or verdict == "disagree":
                alarms += 1
    if total == 0:
        raise ValueError(f"no passed items found under {SWEEP3}")
    return alarms, total, round(alarms / total, 4)


# ---------------------------------------------------------------------------
# row model
# ---------------------------------------------------------------------------

class Row:
    """One scorecard line: every field is derived from a tracked artifact."""

    def __init__(self, n: int, metric: str, value: str, gate: str, bar: str,
                 artifact: str, rerun: str, note: str | None = None) -> None:
        assert gate in ("PASS", "MISS", "n/a"), gate
        self.n = n
        self.metric = metric
        self.value = value
        self.gate = gate
        self.bar = bar
        self.artifact = artifact
        self.rerun = rerun
        self.note = note


def build_rows() -> list[Row]:
    bcal = _load_json(BROWSER_CAL)
    sens = _walk(bcal, "rates.sensitivity")
    spec = _walk(bcal, "rates.specificity")
    rg_obs = _walk(bcal, "rogan_gladen_corrected_success_rate.observed")
    rg_corr = _walk(bcal, "rogan_gladen_corrected_success_rate.corrected")

    recall_pin = _registry_expected("task2_mutation_recall_all_classes")
    fa_pin = _registry_expected("task2_mutation_sweep3_clean_false_alarm")
    fa_alarms, fa_total, fa_rate = _sweep3_clean_false_alarm()
    if fa_rate != fa_pin:
        raise ValueError(
            f"sweep3 clean false-alarm {fa_rate} != registry pin {fa_pin} "
            f"({fa_alarms}/{fa_total}) — artifact/registry drift")

    auroc = _walk(_load_json(SEC_CAL), "strata.ntu_human_labeled.auroc")

    caught = _walk(_load_json(ATTRIBUTION), "variants.margin_plus_ibr_SHIPPED.caught_errors")
    c_num, c_den = (int(x) for x in str(caught).split("/"))
    intercept_pct = c_num / c_den

    cert = _load_json(CERTIFICATION)
    certified = _walk(cert, "verdicts.certified")
    contradicted = _walk(cert, "verdicts.contradicted")

    cyd = _load_json(CYD)
    cyd_agree = _walk(cyd, "verdicts.agree")
    cyd_disagree = _walk(cyd, "verdicts.disagree")

    imp = _load_json(IMPOSSIBLE)
    silent_rate = _walk(imp, "metrics.silent_failure_rate")
    honest_rate = _walk(imp, "metrics.honest_outcome_rate")

    tri = _load_json(TRIANGULATION)
    tri_agree = _walk(tri, "verdict_totals.agree")
    tri_disagree = _walk(tri, "verdict_totals.disagree")

    calibrate_browser = ".venv/Scripts/python tools/calibrate_verifier.py"
    mutation_pytest = ".venv/Scripts/python -m pytest tests/test_verifier_mutations.py -q -s"
    calibrate_sec = ".venv/Scripts/python tools/calibrate_sec_confidence.py"
    intercept_rerun = (
        ".venv/Scripts/python -c \"import json;print(json.load(open("
        "'data/sec_eval/calibration/topic_prior_attribution.json'))"
        "['variants']['margin_plus_ibr_SHIPPED']['caught_errors'])\"")

    def gate(ok: bool) -> str:
        return "PASS" if ok else "MISS"

    return [
        Row(1, "Browser verifier sensitivity / specificity (calibration, n=50)",
            f"{sens} / {spec}", gate(sens == 1.0 and spec == 1.0), "target 1.0 / 1.0",
            "data/browser_eval/calibration/calibration_results.json", calibrate_browser),
        Row(2, "Browser Rogan–Gladen corrected success rate",
            f"{rg_corr} (observed {rg_obs} → corrected {rg_corr})", "n/a",
            "bias-corrected estimate",
            "data/browser_eval/calibration/calibration_results.json", calibrate_browser),
        Row(3, "Mutation harness six-class detection recall (min of 6 classes)",
            f"{recall_pin}", gate(recall_pin >= 0.95), "≥ 0.95",
            "tests/test_verifier_mutations.py", mutation_pytest, note="mut_recall"),
        Row(4, "Mutation harness clean false-alarm (sweep3 recorded)",
            f"{fa_rate} ({fa_alarms}/{fa_total})", gate(fa_rate <= 0.05), "≤ 0.05",
            "data/sec_eval/records/sweep3/ + data/sec_eval/triangulation/triangulation.json",
            mutation_pytest, note="mut_fa"),
        Row(5, "SEC confidence calibration AUROC (NTU human-labeled, n=512)",
            f"{auroc}", gate(auroc >= 0.75), "≥ 0.75",
            "data/sec_eval/calibration/calibration.json", calibrate_sec, note="auroc"),
        Row(6, "SEC needs_review error interception (NTU errors)",
            f"{intercept_pct * 100:.1f}% ({caught})", gate(intercept_pct >= 0.50), "≥ 50%",
            "data/sec_eval/calibration/topic_prior_attribution.json", intercept_rerun,
            note="intercept"),
        Row(7, "XBRL Item 8 certification census (11 filings)",
            f"{certified} certified / {contradicted} contradicted", "n/a",
            "corroboration census",
            "data/sec_eval/certification/item8_certification.json",
            ".venv/Scripts/python tools/certify.py", note="cert"),
        Row(8, "CYD iXBRL ground-truth agreement (11 filings)",
            f"{cyd_agree} agree / {cyd_disagree} disagree", gate(cyd_disagree == 0),
            "0 disagree vs oracle",
            "data/sec_eval/cyd_groundtruth/cyd_agreement.json",
            ".venv/Scripts/python tools/certify_cyd.py"),
        Row(9, "Impossible-task silent-failure rate (n=10)",
            f"{silent_rate}", gate(silent_rate == 0.0), "= 0, worst failure class",
            "data/browser_eval/impossible/impossible_results.json",
            ".venv/Scripts/python tools/impossible_tasks.py"),
        Row(10, "Impossible-task honest-outcome rate (n=10)",
            f"{honest_rate}", gate(honest_rate == 1.0), "= 1.0",
            "data/browser_eval/impossible/impossible_results.json",
            ".venv/Scripts/python tools/impossible_tasks.py"),
        Row(11, "Third-engine triangulation census (11 filings / 253 items)",
            f"{tri_agree} agree / {tri_disagree} disagree", "n/a", "corroboration census",
            "data/sec_eval/triangulation/triangulation.json",
            ".venv/Scripts/python tools/triangulate.py", note="tri"),
    ]


NOTES = {
    "mut_recall": ("recomputed at test time — no stored per-run artifact; the value is "
                   "the registry pin (`data/claims_registry.json` → "
                   "`task2_mutation_recall_all_classes`), re-derived by the rerun command."),
    "mut_fa": ("computed by this tool from the two artifacts (1 alarm over 178 passed "
               "items), cross-checked against registry pin "
               "`task2_mutation_sweep3_clean_false_alarm` = 0.0056."),
    "auroc": ("open gate — quoted honestly, never as 'acceptable'; the needs_review "
              "interception channel (row 6) is the primary axis for this verifier."),
    "intercept": ("interception count 77/118 lives in the shipped-variant field "
                  "`variants.margin_plus_ibr_SHIPPED.caught_errors` of "
                  "`topic_prior_attribution.json` (the P0-3 companion to "
                  "`calibration.json`); 77/118 = 65.3%."),
    "cert": ("census, not a threshold gate — the single contradiction is NVDA's "
             "incorporated-by-reference Item 8 stub, correctly flagged "
             "(`agrees_with_pipeline` = true)."),
    "tri": ("census — the 4 uncorroborated disagreements are all needs_review "
            "wrapper-10-K boundary items (JPM 1C/7A, XOM 7A/16)."),
}


def _gate_cell(row: Row) -> str:
    if row.gate == "n/a":
        return f"n/a ({row.bar})"
    return f"**{row.gate}** ({row.bar})"


def render() -> str:
    rows = build_rows()
    n_pass = sum(1 for r in rows if r.gate == "PASS")
    n_miss = sum(1 for r in rows if r.gate == "MISS")
    n_na = sum(1 for r in rows if r.gate == "n/a")

    out: list[str] = []
    out.append("# Verifier Trust Card — 裁判本身可不可信")
    out.append("")
    out.append("> 本卡由 `tools/verifier_trust_card.py` 從已追蹤的 artifact 自動生成;任何手動編輯"
               "都會在重新生成時被覆蓋,並由 `tests/test_verifier_trust_card.py` 的 drift 測試攔截。"
               "This card is generated by `tools/verifier_trust_card.py` from tracked artifacts — "
               "any hand edit is overwritten on regeneration and caught by the drift test.")
    out.append("")
    out.append(f"**Gate tally 門檻統計:** {n_pass} PASS · {n_miss} MISS · {n_na} n/a")
    out.append("")
    out.append("每一格數值都直接讀自 artifact,gate 由該數值即時比對門檻算出;MISS 與 PASS "
               "以相同粗體呈現,不淡化失敗。")
    out.append("")
    out.append("| # | Metric 指標 | Value 數值 | Gate 門檻 |")
    out.append("|---|---|---|---|")
    for r in rows:
        out.append(f"| {r.n} | {r.metric} | {r.value} | {_gate_cell(r)} |")
    out.append("")

    out.append("## 未過門檻 — 照實揭露 / Open gate (honest disclosure)")
    out.append("")
    miss_rows = [r for r in rows if r.gate == "MISS"]
    if miss_rows:
        for r in miss_rows:
            out.append(f"- **MISS · row {r.n} — {r.metric} = {r.value}, gate {r.bar}.** "
                       + (NOTES.get(r.note, "") if r.note else ""))
    else:
        out.append("- (none)")
    out.append("")

    out.append("## 證據與重跑 / Provenance & rerun")
    out.append("")
    out.append("Registry-backed rows (3, 4, 5, 11) are additionally re-derived end-to-end by "
               "`.venv/Scripts/python tools/verify_claims.py` (exit 0 = no drift).")
    out.append("")
    out.append("| # | Artifact 證據檔 | Rerun 重跑指令 |")
    out.append("|---|---|---|")
    for r in rows:
        out.append(f"| {r.n} | `{r.artifact}` | `{r.rerun}` |")
    out.append("")

    out.append("## 註記 / Notes")
    out.append("")
    for r in rows:
        if r.note and r.note in NOTES:
            out.append(f"- **row {r.n}:** {NOTES[r.note]}")
    out.append("")

    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="exit 1 if the committed card differs from a fresh render")
    args = parser.parse_args(argv)

    fresh = render()
    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != fresh:
            print(f"DRIFT: {OUTPUT.relative_to(ROOT)} differs from a fresh render "
                  "— run tools/verifier_trust_card.py to regenerate.")
            return 1
        print(f"OK: {OUTPUT.relative_to(ROOT)} matches a fresh render.")
        return 0

    with open(OUTPUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(fresh)
    print(f"wrote {OUTPUT.relative_to(ROOT)} ({len(fresh)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
