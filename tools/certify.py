"""Cross-validate a ticker's extracted Item 8 against SEC XBRL facts.

Usage: .venv/Scripts/python tools/certify.py TICKER [TICKER ...]
Prints, per filing, whether the independent XBRL oracle certifies or
contradicts the extracted financial-statements span. Requires
SEC_EDGAR_USER_AGENT.
"""

from __future__ import annotations

import sys
from pathlib import Path

from sec_core.fetcher import EdgarFetcher
from sec_core.main_doc import pick_main_document
from sec_core.pipeline import extract_from_html
from sec_core.resolver import FilingResolver
from sec_core.xbrl import fetch_company_facts, key_facts_for_accession, validate_span

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    tickers = [t.upper() for t in sys.argv[1:]] or ["AAPL"]
    fetcher = EdgarFetcher(cache_dir=ROOT / "data" / "raw_filings")
    resolver = FilingResolver(fetcher)
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
            facts = key_facts_for_accession(fetch_company_facts(fetcher, cik), ref.accession)
            chk = validate_span(result.text_of("8"), facts)
            print(f"{t:<7} {result.segment('8').status:<26} {chk.verdict:<13} {chk.detail}")
        except Exception as e:  # noqa: BLE001 - tool prints failures, does not crash the sweep
            print(f"{t:<7} ERROR {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
