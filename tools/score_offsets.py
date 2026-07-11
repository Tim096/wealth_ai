"""Score eval records against frozen offset gold (T2-2).

Usage:
  .venv/Scripts/python tools/score_offsets.py data/sec_eval/records/sweep3 \
      [--gold data/golden_labels/offsets] [--out data/sec_eval/scoring/offset_f1.json]

Pairs every gold file with <records_dir>/<TICKER>.json, computes per-item
char-offset precision/recall/F1, per-filing and overall macro averages, and
the present/null/MISSING confusion (omission vs hallucination separated).
Writes the committed JSON artifact and prints a markdown summary.
Accession mismatch between record and gold -> the filing is skipped, never
silently scored against the wrong document.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from sec_core.scoring import score_filing

ROOT = Path(__file__).resolve().parents[1]


def _arg(flag: str, default: str) -> str:
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default


def _rel(p: Path) -> str:
    """repo-relative POSIX path when p is under ROOT, else the raw path —
    keeps the artifact free of machine-specific absolute paths (no noise diff)."""
    try:
        return str(p.resolve().relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(p).replace("\\", "/")


def main() -> None:
    records_dir = Path(sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--")
                       else "data/sec_eval/records/sweep3")
    gold_dir = Path(_arg("--gold", "data/golden_labels/offsets"))
    out_path = Path(_arg("--out", "data/sec_eval/scoring/offset_f1.json"))

    filings: list[dict] = []
    skipped: list[dict] = []
    all_f1: list[float] = []
    all_p: list[float] = []
    all_r: list[float] = []
    outcome_totals: Counter[str] = Counter()

    for gold_path in sorted(gold_dir.glob("*.json")):
        gold = json.loads(gold_path.read_text(encoding="utf-8-sig"))
        record_path = records_dir / f"{gold['ticker']}.json"
        if not record_path.exists():
            skipped.append({"ticker": gold["ticker"], "reason": f"no record in {records_dir}"})
            continue
        record = json.loads(record_path.read_text(encoding="utf-8-sig"))
        if record.get("accession") != gold.get("accession"):
            skipped.append({"ticker": gold["ticker"], "reason":
                            f"accession mismatch: record {record.get('accession')} "
                            f"vs gold {gold.get('accession')}"})
            continue
        scored = score_filing(record, gold)
        filings.append(scored)
        outcome_totals.update(scored["outcome_counts"])
        for row in scored["items"]:
            if "f1" in row:
                all_f1.append(row["f1"])
                all_p.append(row["precision"])
                all_r.append(row["recall"])

    per_filing_macros = [f["macro_f1"] for f in filings if f["macro_f1"] is not None]
    totals = {
        "filings_scored": len(filings),
        "filings_skipped": len(skipped),
        "offset_items": len(all_f1),
        "macro_precision_items": round(sum(all_p) / len(all_p), 4) if all_p else None,
        "macro_recall_items": round(sum(all_r) / len(all_r), 4) if all_r else None,
        "macro_f1_items": round(sum(all_f1) / len(all_f1), 4) if all_f1 else None,
        "macro_f1_filings": round(sum(per_filing_macros) / len(per_filing_macros), 4)
        if per_filing_macros else None,
        "outcome_counts": dict(outcome_totals),
    }
    artifact = {
        "generated_by": "tools/score_offsets.py",
        "records_dir": _rel(records_dir),
        "gold_dir": _rel(gold_dir),
        "totals": totals,
        "filings": filings,
        "skipped": skipped,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(artifact, indent=1), encoding="utf-8")

    print(f"gold filings: {len(filings)} scored, {len(skipped)} skipped -> {out_path}")
    print()
    print("| ticker | gold items | offset items | macro P | macro R | macro F1 | omission | hallucination |")
    print("|---|---|---|---|---|---|---|---|")
    for f in filings:
        oc = f["outcome_counts"]
        print(f"| {f['ticker']} | {f['gold_items']} | {f['offset_items']} "
              f"| {f['macro_precision']} | {f['macro_recall']} | {f['macro_f1']} "
              f"| {oc.get('omission', 0)} | {oc.get('hallucination', 0)} |")
    print()
    print(f"overall: macro-F1 over items {totals['macro_f1_items']}, "
          f"over filings {totals['macro_f1_filings']}; outcomes {totals['outcome_counts']}")
    for s in skipped:
        print(f"SKIPPED {s['ticker']}: {s['reason']}")


if __name__ == "__main__":
    main()
