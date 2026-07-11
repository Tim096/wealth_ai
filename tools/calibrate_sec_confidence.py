"""P0-3 verifier calibration curve — AUROC / ECE / risk-coverage of per-item
confidence vs correctness (giants_task2.md §2 P0-3).

Stratified reporting (who-judges-the-judge §5.3):
  PRIMARY   ntu_human_labeled — NTU itemseg line-level BIO gold (arXiv
            2502.08875, human-labeled), consumed via the head_to_head.py
            artifact (data/sec_eval/scoring/head_to_head.json). Correctness =
            line-level item F1 >= 0.5, the same threshold as head_to_head's
            verifier_false_pass (deliverable B).
  AUXILIARY pseudo_gold_corpus_only — P0-1 pseudo-gold votes with edgartools
            EXCLUDED from the label: edgartools is both a teacher and part of
            the triangulation signal chain, so letting it vote on the label
            would correlate label noise with the confidence signal and inflate
            AUROC. Label = corpus teacher verdict alone (agree/disagree);
            corpus no-signal items are dropped. Per-item confidence comes from
            re-running our pipeline on the SAME cached raw filings (offline:
            cache-first EdgarFetcher).
  CONTEXT   sweep3 — unlabeled confidence distribution (pass mean ~0.975 per
            eval_report.md:91); no gold, so no curve, distribution only.

Deliverable includes the explicit verifier false-pass rate marked on the
risk-coverage curve: the clean-pass gate is head_to_head.py's deliverable-B
definition (needs_review == False AND confidence >= 0.6). The gate is not a
pure confidence threshold (needs_review adds information), so the operating
point is plotted as a marker, not a point of the threshold-swept curve.

Outputs:
  data/sec_eval/calibration/calibration.json
  data/sec_eval/calibration/calibration_curve.png

Usage (offline when the miner's raw-filing cache is warm):
  .venv/Scripts/python tools/calibrate_sec_confidence.py
Requires SEC_EDGAR_USER_AGENT (EdgarFetcher contract, even for cache hits).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))
sys.path.insert(0, str(ROOT / "tools"))

OUT_DIR = ROOT / "data" / "sec_eval" / "calibration"
HEAD_TO_HEAD = ROOT / "data" / "sec_eval" / "scoring" / "head_to_head.json"
PSEUDO_GOLD = ROOT / "data" / "sec_eval" / "pseudo_gold" / "pseudo_gold_candidates.json"
SWEEP3_DIR = ROOT / "data" / "sec_eval" / "records" / "sweep3"

CONF_GATE = 0.6  # head_to_head.py deliverable-B clean-pass gate — keep in sync
F1_CORRECT = 0.5  # same correctness threshold as verifier_false_pass
ECE_BINS = 10


# -- metrics (pure; unit-tested) -------------------------------------------------

def auroc(samples: list[dict]) -> float | None:
    """Tie-aware AUROC of confidence as a score for correct=True.
    None when a class is empty (undefined, never 0/1 by fiat)."""
    pos = [s["confidence"] for s in samples if s["correct"]]
    neg = [s["confidence"] for s in samples if not s["correct"]]
    if not pos or not neg:
        return None
    wins = sum(1.0 if p > n else 0.5 if p == n else 0.0 for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def ece(samples: list[dict], n_bins: int = ECE_BINS) -> tuple[float, list[dict]]:
    """Expected calibration error over equal-width confidence bins on [0, 1].
    Returns (ece, bins); confidence 1.0 lands in the top bin."""
    bins = [{"lo": i / n_bins, "hi": (i + 1) / n_bins, "n": 0,
             "conf_sum": 0.0, "correct": 0} for i in range(n_bins)]
    for s in samples:
        i = min(int(s["confidence"] * n_bins), n_bins - 1)
        b = bins[i]
        b["n"] += 1
        b["conf_sum"] += s["confidence"]
        b["correct"] += bool(s["correct"])
    total = len(samples)
    err = 0.0
    out = []
    for b in bins:
        row = {"lo": b["lo"], "hi": b["hi"], "n": b["n"]}
        if b["n"]:
            acc = b["correct"] / b["n"]
            conf = b["conf_sum"] / b["n"]
            err += (b["n"] / total) * abs(acc - conf)
            row.update({"accuracy": round(acc, 4), "mean_confidence": round(conf, 4)})
        out.append(row)
    return (err if total else 0.0), out


def risk_coverage(samples: list[dict]) -> list[dict]:
    """Selective-risk curve: sweep the confidence threshold downward; at each
    distinct confidence, cover everything at or above it. Ties enter together
    (a threshold cannot split equal confidences)."""
    ordered = sorted(samples, key=lambda s: -s["confidence"])
    n = len(ordered)
    points: list[dict] = []
    covered = errors = 0
    i = 0
    while i < n:
        j = i
        while j < n and ordered[j]["confidence"] == ordered[i]["confidence"]:
            errors += not ordered[j]["correct"]
            covered += 1
            j += 1
        points.append({"threshold": ordered[i]["confidence"],
                       "coverage": round(covered / n, 4),
                       "risk": round(errors / covered, 4)})
        i = j
    return points


def false_pass_point(samples: list[dict]) -> dict:
    """Deliverable-B operating point: items the verifier passed clean
    (needs_review False AND confidence >= CONF_GATE). false_pass_rate =
    P(incorrect | clean pass) — the number the spec wants marked on the curve."""
    gate = [s for s in samples
            if not s["needs_review"] and s["confidence"] >= CONF_GATE]
    false_pass = sum(1 for s in gate if not s["correct"])
    n = len(samples)
    return {
        "gate": f"needs_review == False and confidence >= {CONF_GATE}",
        "clean_pass_items": len(gate),
        "false_pass_items": false_pass,
        "false_pass_rate": round(false_pass / len(gate), 4) if gate else None,
        "coverage": round(len(gate) / n, 4) if n else None,
    }


def stratum_report(samples: list[dict]) -> dict:
    e, bins = ece(samples)
    a = auroc(samples)
    n_correct = sum(1 for s in samples if s["correct"])
    return {
        "n_items": len(samples),
        "n_correct": n_correct,
        "base_error_rate": round(1 - n_correct / len(samples), 4) if samples else None,
        "auroc": round(a, 4) if a is not None else None,
        "ece": round(e, 4),
        "reliability_bins": bins,
        "risk_coverage": risk_coverage(samples),
        "verifier_false_pass": false_pass_point(samples),
    }


# -- collectors -------------------------------------------------------------------

def collect_ntu(artifact: dict) -> list[dict]:
    """(confidence, correct) pairs from the head_to_head artifact — human gold.
    Only items with gold lines (tp + fn > 0) have a defined correctness; an
    item our engine never emitted gets confidence 0.0 / needs_review False,
    matching head_to_head's verifier_false_pass defaults."""
    samples: list[dict] = []
    for filing in artifact.get("filings", []):
        ours = filing.get("engines", {}).get("ours", {})
        if "items" not in ours:
            continue  # engine failure rows carry no per-item surface
        verifier = ours.get("verifier", {})
        for code, m in ours["items"].items():
            if m["tp"] + m["fn"] <= 0:
                continue  # fp-only item: no gold lines, correctness undefined
            v = verifier.get(code, {})
            samples.append({
                "filing": f"ntu_{filing['uid']}",
                "item": code,
                "confidence": float(v.get("confidence", 0.0)),
                "needs_review": bool(v.get("needs_review", False)),
                "status": v.get("status", "missing"),
                "correct": m["f1"] >= F1_CORRECT,
            })
    return samples


def collect_pseudo_gold(candidates: dict,
                        confidence_by_filing: dict[str, dict[str, dict]]) -> list[dict]:
    """(confidence, correct) pairs from P0-1 votes, edgartools EXCLUDED.

    Label = corpus teacher verdict alone: agree -> correct, disagree ->
    incorrect, anything else (no-signal) -> dropped. The edgartools teacher
    never touches the label — it shares lineage with our triangulation signal
    (P0-3 circularity rule).
    confidence_by_filing: accession -> {item_code: {confidence, needs_review,
    status}} from re-running our pipeline on the cached raw filings.
    """
    samples: list[dict] = []
    for rec in candidates.get("records", []):
        if rec.get("disposition") != "voted":
            continue
        conf_map = confidence_by_filing.get(rec.get("accession", ""), {})
        for code, entry in rec.get("items", {}).items():
            verdict = entry.get("teachers", {}).get("corpus", {}).get("verdict")
            if verdict not in ("agree", "disagree"):
                continue
            v = conf_map.get(code, {})
            samples.append({
                "filing": f"cik{rec['cik']}-{rec.get('accession', '')}",
                "item": code,
                "confidence": float(v.get("confidence", 0.0)),
                "needs_review": bool(v.get("needs_review", False)),
                "status": v.get("status", "missing"),
                "correct": verdict == "agree",
            })
    return samples


def sweep3_context(records_dir: Path) -> dict:
    """Unlabeled sweep3 confidence distribution — context only (gold there is
    the 5-filing F1-1.0 frozen set: no error signal to calibrate against)."""
    confs: list[float] = []
    filings = 0
    for path in sorted(records_dir.glob("*.json")):
        rec = json.loads(path.read_text(encoding="utf-8"))
        filings += 1
        for item in rec.get("items", {}).values():
            if item.get("status") == "pass":
                confs.append(float(item.get("confidence", 0.0)))
    return {
        "filings": filings,
        "pass_items": len(confs),
        "pass_confidence_mean": round(sum(confs) / len(confs), 4) if confs else None,
        "pass_confidence_min": round(min(confs), 4) if confs else None,
        "note": "no gold with error signal -> distribution only, no curve",
    }


# -- pseudo-gold confidence re-run (cache-first; offline when cache is warm) -----

def rerun_confidences(candidates: dict) -> dict[str, dict[str, dict]]:
    from sec_core.fetcher import EdgarFetcher
    from sec_core.pipeline import extract_from_html
    from sec_core.resolver import FilingResolver

    from mine_pseudo_gold import _fetch_raw

    fetcher = EdgarFetcher(cache_dir=ROOT / "data" / "raw_filings")
    resolver = FilingResolver(fetcher)
    out: dict[str, dict[str, dict]] = {}
    for rec in candidates.get("records", []):
        if rec.get("disposition") != "voted":
            continue
        accession = rec["accession"]
        try:
            raw, _ = _fetch_raw(fetcher, resolver, rec["cik"], accession)
            result = extract_from_html(raw, f"cik{rec['cik']}-{accession}")
        except Exception as e:  # noqa: BLE001 — one filing must not sink the curve
            print(f"  rerun SKIP cik={rec['cik']} {accession}: {type(e).__name__}: {e}")
            continue
        out[accession] = {
            seg.item_code: {"confidence": seg.confidence,
                            "needs_review": seg.needs_review,
                            "status": seg.status}
            for seg in result.segments
        }
    return out


# -- plot -------------------------------------------------------------------------

def render_png(strata: dict[str, dict], out_path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    styles = {  # CVD-safe blue/amber pair; identity also carried by label + style
        "ntu_human_labeled": {"color": "#2563eb", "ls": "-", "label": "NTU human-labeled (primary)"},
        "pseudo_gold_corpus_only": {"color": "#d97706", "ls": "--",
                                    "label": "pseudo-gold, corpus-only vote (auxiliary)"},
    }
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.2), dpi=120)

    ax1.plot([0, 1], [0, 1], color="#9ca3af", lw=1, ls=":", zorder=1)
    for name, rep in strata.items():
        st = styles[name]
        xs = [b["mean_confidence"] for b in rep["reliability_bins"] if b["n"]]
        ys = [b["accuracy"] for b in rep["reliability_bins"] if b["n"]]
        ax1.plot(xs, ys, color=st["color"], ls=st["ls"], lw=2, marker="o",
                 ms=4, label=f"{st['label']}  ECE={rep['ece']:.3f}")
    ax1.set_xlabel("mean confidence (bin)")
    ax1.set_ylabel("empirical accuracy")
    ax1.set_title("Reliability diagram")
    ax1.set_xlim(0, 1)
    ax1.set_ylim(0, 1)
    ax1.legend(fontsize=7, loc="upper left")

    for name, rep in strata.items():
        st = styles[name]
        cov = [p["coverage"] for p in rep["risk_coverage"]]
        risk = [p["risk"] for p in rep["risk_coverage"]]
        ax2.plot(cov, risk, color=st["color"], ls=st["ls"], lw=2,
                 label=f"{st['label']}  AUROC={rep['auroc']}")
        fp = rep["verifier_false_pass"]
        if fp["false_pass_rate"] is not None:
            ax2.scatter([fp["coverage"]], [fp["false_pass_rate"]], s=70,
                        marker="X", color=st["color"], zorder=5,
                        edgecolors="white", linewidths=0.8)
            dy = 10 if st["ls"] == "--" else -24  # keep labels off curves/legend
            ax2.annotate(f"false-pass {fp['false_pass_rate']:.3f}\n@ cov {fp['coverage']:.2f}",
                         (fp["coverage"], fp["false_pass_rate"]),
                         textcoords="offset points", xytext=(-10, dy), fontsize=7,
                         ha="right", color=st["color"])
    ax2.set_xlabel("coverage (fraction of items answered)")
    ax2.set_ylabel("selective risk (error rate among covered)")
    ax2.set_title("Risk-coverage (X = clean-pass gate operating point)")
    ax2.set_xlim(0, 1.02)
    ax2.set_ylim(bottom=0)
    ax2.legend(fontsize=7, loc="lower left")

    for ax in (ax1, ax2):
        ax.grid(True, lw=0.4, alpha=0.4)
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle("SEC verifier confidence calibration (P0-3)", fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(out_path)
    plt.close(fig)


# -- CLI --------------------------------------------------------------------------

def main() -> None:  # pragma: no cover — thin orchestration; pieces unit-tested
    if not HEAD_TO_HEAD.exists():
        raise SystemExit(f"missing {HEAD_TO_HEAD} — run tools/head_to_head.py first")
    if not PSEUDO_GOLD.exists():
        raise SystemExit(f"missing {PSEUDO_GOLD} — run tools/mine_pseudo_gold.py first")

    ntu_samples = collect_ntu(json.loads(HEAD_TO_HEAD.read_text(encoding="utf-8")))
    candidates = json.loads(PSEUDO_GOLD.read_text(encoding="utf-8"))
    print(f"NTU samples: {len(ntu_samples)}")
    print("re-running pipeline for pseudo-gold confidences (cache-first) ...")
    pg_samples = collect_pseudo_gold(candidates, rerun_confidences(candidates))
    print(f"pseudo-gold samples (corpus-only label): {len(pg_samples)}")

    strata = {"ntu_human_labeled": stratum_report(ntu_samples),
              "pseudo_gold_corpus_only": stratum_report(pg_samples)}
    strata["ntu_human_labeled"]["role"] = "primary (human-labeled gold)"
    strata["pseudo_gold_corpus_only"]["role"] = (
        "auxiliary — label = corpus teacher verdict only; edgartools excluded "
        "from the vote to break teacher/signal circularity (P0-3)")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    png_path = OUT_DIR / "calibration_curve.png"
    render_png(strata, png_path)

    artifact = {
        "generated_by": "tools/calibrate_sec_confidence.py",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "spec": "docs/research/giants_task2.md §2 (P0-3)",
        "definitions": {
            "correct_ntu": f"line-level item F1 >= {F1_CORRECT} on NTU itemseg gold "
                           "(arXiv 2502.08875; lower-bound metric, see head_to_head.py)",
            "correct_pseudo_gold": "corpus teacher verdict == agree (edgartools "
                                   "excluded from the vote; no-signal dropped)",
            "clean_pass_gate": f"needs_review == False and confidence >= {CONF_GATE} "
                               "(head_to_head.py deliverable-B definition)",
            "false_pass_rate": "P(incorrect | clean pass) — marked X on the "
                               "risk-coverage panel; the gate uses needs_review, so "
                               "the point need not lie on the threshold-swept curve",
        },
        "strata": strata,
        "sweep3_context": sweep3_context(SWEEP3_DIR),
        "png": png_path.name,
    }
    out_json = OUT_DIR / "calibration.json"
    out_json.write_text(json.dumps(artifact, indent=1), encoding="utf-8")

    print("\n| stratum | n | AUROC | ECE | false-pass rate | coverage |")
    print("|---|---|---|---|---|---|")
    for name, rep in strata.items():
        fp = rep["verifier_false_pass"]
        print(f"| {name} | {rep['n_items']} | {rep['auroc']} | {rep['ece']} "
              f"| {fp['false_pass_rate']} | {fp['coverage']} |")
    print(f"sweep3 context: {artifact['sweep3_context']}")
    print(f"wrote {out_json}")
    print(f"wrote {png_path}")


if __name__ == "__main__":
    main()
