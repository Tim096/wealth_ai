"""Real-EDGAR smoke run: resolve a ticker's latest 10-K, pick the main
document, extract items, and print an honest per-item report.

Usage: .venv/Scripts/python tools/smoke_real_filing.py [TICKER]
Requires SEC_EDGAR_USER_AGENT.
"""

from __future__ import annotations

import sys
from pathlib import Path

from sec_core.fetcher import EdgarFetcher
from sec_core.main_doc import pick_main_document
from sec_core.pipeline import extract_from_html
from sec_core.resolver import FilingResolver

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    fetcher = EdgarFetcher(cache_dir=ROOT / "data" / "raw_filings")
    resolver = FilingResolver(fetcher)

    cik = resolver.cik_for_ticker(ticker)
    print(f"{ticker} -> CIK {cik}")

    filings = resolver.annual_filings(cik)
    if not filings:
        raise SystemExit("no 10-K filings found")
    ref = next((f for f in filings if not f.is_amendment), filings[0])
    print(f"latest 10-K: accession {ref.accession}, filed {ref.filing_date}, "
          f"report date {ref.report_date}, primary={ref.primary_document}")

    resolver.load_files(ref)
    print(f"package has {len(ref.files)} files")
    best = pick_main_document(ref)
    print(f"main document: {best.name} (score {best.score})")
    for r in best.reasons:
        print(f"   {r}")

    raw = fetcher.get(ref.file_url(best.name)).content.decode("utf-8", errors="replace")
    print(f"fetched {len(raw):,} chars of raw HTML")

    result = extract_from_html(raw, filing_id=f"{ticker}-{ref.accession}")
    print(f"\nextraction latency: {result.latency_ms:.0f} ms; "
          f"{len(result.candidates)} heading candidates, "
          f"{sum(1 for c in result.candidates if c.toc_rejected)} TOC-rejected\n")

    print(f"{'item':<5} {'status':<28} {'conf':<6} heading")
    for seg in result.segments:
        print(f"{seg.item_code:<5} {seg.status:<28} {seg.confidence:<6.2f} "
              f"{seg.extracted_heading[:70]}")
    print("\nwarnings on non-pass items:")
    for seg in result.segments:
        if seg.status not in ("pass", "missing", "reserved") and seg.warnings:
            print(f"  item {seg.item_code}: {seg.warnings}")


if __name__ == "__main__":
    main()
