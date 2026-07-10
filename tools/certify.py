"""Cross-validate a ticker's extracted Item 8 against SEC XBRL facts.

Usage: .venv/Scripts/python tools/certify.py TICKER [TICKER ...]
Prints, per filing, whether the independent XBRL oracle certifies or
contradicts the extracted financial-statements span. Requires
SEC_EDGAR_USER_AGENT.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from sec_core.fetcher import EdgarFetcher
from sec_core.main_doc import pick_main_document
from sec_core.pipeline import extract_from_html
from sec_core.resolver import FilingResolver
from sec_core.xbrl import certify_item8

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "sec_eval" / "certification"


def main() -> None:
    tickers = [t.upper() for t in sys.argv[1:]] or ["AAPL"]
    fetcher = EdgarFetcher(cache_dir=ROOT / "data" / "raw_filings")
    resolver = FilingResolver(fetcher)
    OUT.mkdir(parents=True, exist_ok=True)
    records = []
    print(f"{'ticker':<7} {'item8_status':<26} {'xbrl_verdict':<13} detail")
    for t in tickers:
        try:
            cik = resolver.cik_for_ticker(t)
            filings = resolver.annual_filings(cik)
            ref = next((f for f in filings if not f.is_amendment), None)
            if ref is None:
                print(f"{t:<7} no 10-K")
                continue
            resolver.load_files(ref)
            best = pick_main_document(ref)
            raw = fetcher.get(ref.file_url(best.name)).content.decode("utf-8", errors="replace")
            result = extract_from_html(raw, f"{t}-{ref.accession}")
            chk = certify_item8(result, fetcher, cik, ref.accession)  # writes seg.xbrl_check
            seg8 = result.segment("8")
            rec = {"ticker": t, "cik": cik, "accession": ref.accession,
                   "item8_status": seg8.status, "verdict": chk.verdict, "detail": chk.detail,
                   "facts": chk.facts, "corroborated": chk.corroborated,
                   "agrees_with_pipeline": (chk.verdict == "certified") == (seg8.status == "pass")}
            records.append(rec)
            print(f"{t:<7} {seg8.status:<26} {chk.verdict:<13} {chk.detail}")
        except Exception as e:  # noqa: BLE001 - tool records failures, does not crash the sweep
            print(f"{t:<7} ERROR {type(e).__name__}: {e}")

    summary = {
        "filings": len(records),
        "verdicts": {v: sum(1 for r in records if r["verdict"] == v)
                     for v in ("certified", "contradicted", "inconclusive", "unavailable")},
        "disagreements": [r["ticker"] for r in records if not r["agrees_with_pipeline"]],
        "records": records,
    }
    (OUT / "item8_certification.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\n{summary['verdicts']} · disagreements: {summary['disagreements'] or 'none'}")
    print(f"wrote {OUT / 'item8_certification.json'}")


if __name__ == "__main__":
    main()
