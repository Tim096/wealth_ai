"""Triangulate extracted items against edgartools (independent third engine).

Usage: .venv/Scripts/python tools/triangulate.py TICKER [TICKER ...]
Runs our pipeline and edgartools on the SAME cached raw HTML, compares every
item span, writes per-item agree/disagree/engine_unavailable verdicts to
data/sec_eval/triangulation/triangulation.json. A disagree lowers the item's
confidence and flags needs_review (sec_core.third_engine). Requires
SEC_EDGAR_USER_AGENT (fetches are cache-first).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from sec_core.fetcher import EdgarFetcher
from sec_core.main_doc import pick_main_document
from sec_core.pipeline import extract_from_html
from sec_core.resolver import FilingResolver
from sec_core.third_engine import apply_triangulation, extract_items_edgartools

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "sec_eval" / "triangulation"

SWEEP_TICKERS = ["AAPL", "MSFT", "NVDA", "JPM", "GS", "WMT", "CAT", "XOM", "NEM", "MRNA", "KO"]


def main() -> None:
    tickers = [t.upper() for t in sys.argv[1:]] or SWEEP_TICKERS
    fetcher = EdgarFetcher(cache_dir=ROOT / "data" / "raw_filings")
    resolver = FilingResolver(fetcher)
    OUT.mkdir(parents=True, exist_ok=True)
    records = []
    print(f"{'ticker':<7} {'agree':>5} {'disagree':>8} {'unavail':>7}  disagreeing items")
    for t in tickers:
        try:
            cik = resolver.cik_for_ticker(t)
            ref = next((f for f in resolver.annual_filings(cik) if not f.is_amendment), None)
            if ref is None:
                print(f"{t:<7} no 10-K")
                continue
            resolver.load_files(ref)
            best = pick_main_document(ref)
            raw = fetcher.get(ref.file_url(best.name)).content.decode("utf-8", errors="replace")
            result = extract_from_html(raw, f"{t}-{ref.accession}")
            engine_items = extract_items_edgartools(raw)
            comparisons = apply_triangulation(result, engine_items)
            by_verdict = {"agree": 0, "disagree": 0, "engine_unavailable": 0}
            for c in comparisons:
                by_verdict[c.verdict] += 1
            disagreeing = [c.item_code for c in comparisons if c.verdict == "disagree"]
            records.append({
                "ticker": t, "cik": cik, "accession": ref.accession,
                "filing_class": result.filing_class,
                "engine_parsed": engine_items is not None,
                "engine_items": sorted(engine_items) if engine_items else [],
                "verdicts": by_verdict,
                "items": {
                    c.item_code: {
                        "verdict": c.verdict, "detail": c.detail,
                        "our_words": c.our_words, "engine_words": c.engine_words,
                        "overlap": round(c.overlap, 3),
                        "our_status": result.segment(c.item_code).status,
                        "confidence_after": round(result.segment(c.item_code).confidence, 3),
                        "needs_review": result.segment(c.item_code).needs_review,
                    } for c in comparisons
                },
            })
            print(f"{t:<7} {by_verdict['agree']:>5} {by_verdict['disagree']:>8} "
                  f"{by_verdict['engine_unavailable']:>7}  {', '.join(disagreeing) or '-'}")
        except Exception as e:  # noqa: BLE001 - tool records failures, does not crash the sweep
            print(f"{t:<7} ERROR {type(e).__name__}: {e}")

    try:
        import edgar
        engine_ver = f"edgartools {getattr(edgar, '__version__', '?')}"
    except Exception:  # noqa: BLE001
        engine_ver = "edgartools (not importable)"
    summary = {
        "engine": engine_ver,
        "filings": len(records),
        "verdict_totals": {v: sum(r["verdicts"][v] for r in records)
                           for v in ("agree", "disagree", "engine_unavailable")},
        "disagreements": {r["ticker"]: [k for k, v in r["items"].items()
                                        if v["verdict"] == "disagree"]
                          for r in records if r["verdicts"]["disagree"]},
        "records": records,
    }
    (OUT / "triangulation.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\n{summary['verdict_totals']} · disagreements: {summary['disagreements'] or 'none'}")
    print(f"wrote {OUT / 'triangulation.json'}")


if __name__ == "__main__":
    main()
