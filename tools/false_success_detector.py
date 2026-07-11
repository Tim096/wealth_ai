"""T1-6 (opt-in): run the lightweight false-success detector over a labeled
corpus assembled from COMMITTED artifacts, and write triage metrics.

Route decision (recorded in the output): the detector is HEURISTIC, not a trained
model, because the number of full labeled trajectories in this repo is far below
the ~60 the source paper needs to fit TF-IDF + XGBoost (arxiv 2606.09863). The
model route is written into the `roadmap` block with the sample size and expected
AUROC.

The corpus draws on the richest committed labeled data:
  * calibration cases (data/browser_eval/calibration/*) — each carries a real
    observation.visible_text, contract needles, and a by-construction label
    (success vs corrupted) + the verifier verdict. False-success ground truth =
    (label == corrupted AND verdict == pass).
  * impossible tasks (data/browser_eval/impossible/*) — silent_failure == True is
    a true false success (verifier said pass on an impossible task).

The detector NEVER changes any verdict; this tool only measures how well the
triage flag separates real false successes from legit claimed passes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # run as `python tools/...` (script) or `-m tools....`

from packages.browser_agent.false_success import detect_false_success  # noqa: E402
CAL_CASES = ROOT / "data/browser_eval/calibration/calibration_cases.json"
CAL_RES = ROOT / "data/browser_eval/calibration/calibration_results.json"
IMP_RES = ROOT / "data/browser_eval/impossible/impossible_results.json"
OUT = ROOT / "data/browser_eval/false_success/detector_results.json"

# Documented ground-truth observation for the impossible task that WAS a real
# silent failure before the verifier's query-echo fix (FG-BROWSER-003; verifier
# now masks zero-result echo lines, so the task is an honest fail).
# impossible_results.json did not log visible_text, so we attach the observation
# documented in the impossible-task root cause (v3 doSearch inserts `0 results
# for "<query>"` on 0 hits; success needle "Teleporter"). Flagged
# evidence_reconstructed so provenance is explicit.
_RECONSTRUCTED = {
    "imp-product-teleporter": {
        "visible_text": '0 results for "teleporter"',
        "success_needles": ["Teleporter"],
        "source": "impossible-task root cause (v3_heldout doSearch 0-hit status line)",
    },
}


def _load(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))


def build_corpus() -> list[dict[str, Any]]:
    corpus: list[dict[str, Any]] = []

    cases = {c["case_id"]: c for c in _load(CAL_CASES)["cases"]}
    for r in _load(CAL_RES)["per_case"]:
        cid = r["case_id"]
        c = cases[cid]
        verdict = r["verdict"]
        needles = [sc["value"] for sc in c["contract"]["success_conditions"]
                   if sc["type"] == "text_visible"]
        rec = {
            "id": cid,
            "source": "calibration",
            "corruption_class": r.get("corruption_class"),
            "status": verdict,
            "verifier": {"status": verdict, "missing": []},
            "visible_text": (c.get("observation") or {}).get("visible_text", ""),
            "success_needles": needles,
        }
        gt = (r["label"] == "corrupted" and verdict == "pass")
        corpus.append({"record": rec, "ground_truth_false_success": gt,
                       "evidence_reconstructed": False})

    for t in _load(IMP_RES)["tasks"]:
        tid = t["task_id"]
        rec: dict[str, Any] = {
            "id": tid,
            "source": "impossible",
            "kind": t.get("kind"),
            "status": t["status"],
            "repairs": t.get("repairs", 0),
            "verifier": {"status": t.get("verifier_status"),
                         "missing": t.get("missing_evidence", [])},
        }
        recon = _RECONSTRUCTED.get(tid)
        if recon:
            rec["visible_text"] = recon["visible_text"]
            rec["success_needles"] = recon["success_needles"]
        corpus.append({"record": rec,
                       "ground_truth_false_success": bool(t["silent_failure"]),
                       "evidence_reconstructed": bool(recon)})

    return corpus


def evaluate(corpus: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    tp = fp = fn = tn = 0
    feature_firing: dict[str, int] = {}
    for item in corpus:
        det = detect_false_success(item["record"])
        for k, v in det["features"].items():
            if v:
                feature_firing[k] = feature_firing.get(k, 0) + 1
        gt = item["ground_truth_false_success"]
        applicable = det["applicable"]
        if applicable:
            if det["flag"] and gt:
                tp += 1
            elif det["flag"] and not gt:
                fp += 1
            elif not det["flag"] and gt:
                fn += 1
            else:
                tn += 1
        rows.append({
            "id": item["record"]["id"],
            "source": item["record"]["source"],
            "evidence_reconstructed": item["evidence_reconstructed"],
            "ground_truth_false_success": gt,
            "applicable": applicable,
            "flag": det["flag"],
            "score": det["score"],
            "features": det["features"],
            "reasons": det["reasons"],
        })

    n_applicable = tp + fp + fn + tn
    precision = round(tp / (tp + fp), 4) if (tp + fp) else None
    recall = round(tp / (tp + fn), 4) if (tp + fn) else None
    flag_rate = round((tp + fp) / n_applicable, 4) if n_applicable else None
    return {
        "n_records": len(corpus),
        "n_applicable_claimed_success": n_applicable,
        "n_ground_truth_false_success_applicable": tp + fn,
        "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "precision": precision,
        "recall": recall,
        "flag_rate": flag_rate,
        "feature_firing_counts": feature_firing,
        "per_record": rows,
    }


def main() -> None:
    corpus = build_corpus()
    metrics = evaluate(corpus)
    out = {
        "generated_by": "tools/false_success_detector.py",
        "spec": "T1-6 lightweight false-success detector (opt-in triage)",
        "route": "heuristic",
        "route_reason": (
            "labeled full trajectories in-repo (<10 real TaskRun.as_dict + partial "
            "summaries) are far below the ~60 the source paper (arxiv 2606.09863) "
            "uses to fit TF-IDF+XGBoost; heuristic front-line triage instead."
        ),
        "invariant": "detector emits a triage flag only; the verifier stays the sole judge (verdict never changed).",
        "corpus_sources": {
            "calibration": "data/browser_eval/calibration/* (by-construction labels + real observation.visible_text)",
            "impossible": "data/browser_eval/impossible/* (silent_failure = true false success)",
        },
        "metrics": metrics,
        "known_limitations": [
            "the verifier fixes for FG-BROWSER-002 (content-first downloads) and "
            "FG-BROWSER-003 (query-echo masking) removed every false success from the "
            "committed corpus: cal-bad-dlname-annual-report and imp-product-teleporter "
            "are now honest fails, so the detector has zero applicable ground-truth "
            "false successes to catch (tp=fn=0) — good news upstream, but it means "
            "detector recall is currently unmeasurable on this corpus.",
            "impossible_results.json does not log visible_text, so only the documented "
            "query-echo case carries (reconstructed) evidence; other impossible records "
            "are evidence-starved and the detector cannot fire on them.",
        ],
        "roadmap_tfidf_xgboost": {
            "when": "collect >=60 labeled full trajectories (agent self-report text + observed state).",
            "features": "TF-IDF over agent reasoning/closing text + the heuristic numeric features here.",
            "expected_auroc": "0.83-0.95 (arxiv 2606.09863), ~3300x faster than an LLM judge, same flag rate but 4-8x more true catches.",
            "why_not_now": "current trajectory logs omit the agent self-report text and full observation needed as TF-IDF input; the detector is starved on the committed corpus.",
            "prereq": "log full Observation (visible_text) + agent self-report into every TaskRun.as_dict so the detector has input.",
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    m = metrics
    print(f"corpus={m['n_records']} applicable(claimed pass)={m['n_applicable_claimed_success']} "
          f"gt_false_success={m['n_ground_truth_false_success_applicable']}")
    print(f"confusion={m['confusion']} precision={m['precision']} recall={m['recall']} flag_rate={m['flag_rate']}")
    print(f"feature_firing={m['feature_firing_counts']}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
