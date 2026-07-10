"""Aggregate runs/<sweep>/*.json eval records into a metrics summary (markdown).

Usage: .venv/Scripts/python tools/sweep_metrics.py runs/sweep1
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path


def main() -> None:
    sweep_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "runs/sweep1")
    records = [json.loads(p.read_text(encoding="utf-8-sig")) for p in sorted(sweep_dir.glob("*.json"))]
    if not records:
        raise SystemExit(f"no records in {sweep_dir}")

    status_counts: Counter[str] = Counter()
    per_ticker_rows = []
    confidences_pass: list[float] = []
    latencies: list[float] = []

    for rec in records:
        items = rec["items"]
        c: Counter[str] = Counter(v["status"] for v in items.values())
        status_counts.update(c)
        confidences_pass += [v["confidence"] for v in items.values() if v["status"] == "pass"]
        latencies.append(rec["latency_ms"])
        substantive = sum(v for k, v in c.items() if k in ("pass", "partial", "incorporated_by_reference", "reserved"))
        per_ticker_rows.append(
            f"| {rec['ticker']} | {rec['form']} {rec['report_date']} | {rec['raw_chars']:,} "
            f"| {c['pass']} | {c['missing']} | {substantive} | {rec['toc_rejected']}/{rec['candidates']} "
            f"| {rec['latency_ms']:.0f} |"
        )

    total_items = sum(status_counts.values())
    print(f"filings: {len(records)}; total items: {total_items}")
    print()
    print("| status | count | share |")
    print("|---|---|---|")
    for s, n in status_counts.most_common():
        print(f"| {s} | {n} | {n/total_items:.1%} |")
    print()
    print(f"pass-item confidence: mean {sum(confidences_pass)/len(confidences_pass):.3f}, "
          f"min {min(confidences_pass):.3f}")
    print(f"parse latency ms: mean {sum(latencies)/len(latencies):.0f}, max {max(latencies):.0f}")
    print()
    print("| ticker | filing | raw chars | pass | missing | substantive | toc_rej/cand | latency ms |")
    print("|---|---|---|---|---|---|---|---|")
    for row in per_ticker_rows:
        print(row)


if __name__ == "__main__":
    main()
