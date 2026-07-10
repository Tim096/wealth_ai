"""Certify extracted Item 1C against the official CYD iXBRL block-tags — the
only SEC-mandated machine-readable item span (fiscal years ending >=
2024-12-15).

Usage: .venv/Scripts/python tools/certify_cyd.py [TICKER ...]
Runs our pipeline on the cached raw HTML, parses the CYD text-block tags from
the SAME bytes, maps their raw offsets into normalized offsets and measures
how much of the official span our Item 1C segment covers. Writes
data/sec_eval/cyd_groundtruth/cyd_agreement.json. Requires
SEC_EDGAR_USER_AGENT (fetches are cache-first).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from sec_core.cyd import certify_item1c
from sec_core.fetcher import EdgarFetcher
from sec_core.main_doc import pick_main_document
from sec_core.pipeline import extract_from_html
from sec_core.resolver import FilingResolver

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "sec_eval" / "cyd_groundtruth"

SWEEP_TICKERS = ["AAPL", "MSFT", "NVDA", "JPM", "GS", "WMT", "CAT", "XOM", "NEM", "MRNA", "KO"]


def main() -> None:
    tickers = [t.upper() for t in sys.argv[1:]] or SWEEP_TICKERS
    fetcher = EdgarFetcher(cache_dir=ROOT / "data" / "raw_filings")
    resolver = FilingResolver(fetcher)
    OUT.mkdir(parents=True, exist_ok=True)
    records = []
    print(f"{'ticker':<7} {'our_1C_status':<26} {'verdict':<13} {'coverage':>8} "
          f"{'contain':>8} {'official':>9} {'ours':>8}")
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
            chk = certify_item1c(result, raw, report_date=ref.report_date)
            seg = next((s for s in result.segments if s.item_code == "1C"), None)
            records.append({
                "ticker": t, "cik": cik, "accession": ref.accession,
                "report_date": ref.report_date, "mandatory": chk.mandatory,
                "filing_class": result.filing_class,
                "our_status": seg.status if seg else "no_segment",
                "our_offsets": [seg.start_offset, seg.end_offset] if seg else None,
                "our_chars": chk.our_chars,
                "official_intervals": chk.official_intervals,
                "official_chars": chk.official_chars,
                "n_text_blocks": chk.n_text_blocks,
                "n_fragments": chk.n_fragments,
                "n_hidden": chk.n_hidden,
                "coverage": chk.coverage,
                "containment": chk.containment,
                "verdict": chk.verdict,
                "detail": chk.detail,
                "needs_review_after": seg.needs_review if seg else None,
            })
            print(f"{t:<7} {(seg.status if seg else 'no_segment'):<26} {chk.verdict:<13} "
                  f"{chk.coverage:>8.1%} {chk.containment:>8.1%} "
                  f"{chk.official_chars:>9,} {chk.our_chars:>8,}")
        except Exception as e:  # noqa: BLE001 - tool records failures, does not crash the sweep
            print(f"{t:<7} ERROR {type(e).__name__}: {e}")

    summary = {
        "oracle": "CYD iXBRL block-tags (mandatory for fiscal years ending >= 2024-12-15)",
        "filings": len(records),
        "verdicts": {v: sum(1 for r in records if r["verdict"] == v)
                     for v in ("agree", "disagree", "unavailable", "not_required")},
        "disagreements": [r["ticker"] for r in records if r["verdict"] == "disagree"],
        "coverage_mean_over_available": round(
            sum(r["coverage"] for r in records if r["verdict"] in ("agree", "disagree"))
            / max(1, sum(1 for r in records if r["verdict"] in ("agree", "disagree"))), 4),
        "records": records,
    }
    (OUT / "cyd_agreement.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\n{summary['verdicts']} · disagreements: {summary['disagreements'] or 'none'}")
    print(f"wrote {OUT / 'cyd_agreement.json'}")


if __name__ == "__main__":
    main()
