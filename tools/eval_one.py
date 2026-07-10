"""Extract one ticker's latest 10-K and emit a JSON eval record to stdout.

Usage:
  .venv/Scripts/python tools/eval_one.py TICKER            # full JSON record
  .venv/Scripts/python tools/eval_one.py TICKER --item 7   # dump one item's span text

Requires SEC_EDGAR_USER_AGENT. Fetches go through the rate-limited cache;
pre-populated cache makes runs offline-deterministic.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from observability_core import EvidenceStore
from sec_core.fetcher import EdgarFetcher
from sec_core.main_doc import pick_main_document
from sec_core.pipeline import extract_from_html
from sec_core.resolver import FilingResolver
from sec_core.xbrl import certify_item8

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "data" / "sec_eval" / "evidence"


def run(ticker: str):
    fetcher = EdgarFetcher(cache_dir=ROOT / "data" / "raw_filings")
    resolver = FilingResolver(fetcher)
    cik = resolver.cik_for_ticker(ticker)
    filings = resolver.annual_filings(cik)
    ref = next((f for f in filings if not f.is_amendment), None)
    if ref is None:
        raise SystemExit(f"no original 10-K for {ticker}")
    resolver.load_files(ref)
    best = pick_main_document(ref)
    raw = fetcher.get(ref.file_url(best.name)).content.decode("utf-8", errors="replace")
    # persist a replayable EvidenceRecord JSONL per run through the shared store
    store = EvidenceStore(EVIDENCE)
    run_id = f"sec-{ticker}-{ref.accession}"
    result = extract_from_html(raw, filing_id=f"{ticker}-{ref.accession}",
                               evidence_store=store, run_id=run_id)
    # apply the XBRL oracle so the SHIPPED record carries the gated Item 8 status
    if result.filing_class == "standard":
        try:
            certify_item8(result, fetcher, cik, ref.accession)
        except Exception:  # noqa: BLE001 — certification is best-effort enrichment
            pass
    return ref, best, raw, result


def main() -> None:
    ticker = sys.argv[1].upper()
    ref, best, raw, result = run(ticker)

    if "--item" in sys.argv:
        code = sys.argv[sys.argv.index("--item") + 1].upper()
        print(result.text_of(code))
        return

    record = {
        "ticker": ticker,
        "cik": ref.cik,
        "accession": ref.accession,
        "form": ref.form,
        "filing_date": ref.filing_date,
        "report_date": ref.report_date,
        "filing_class": result.filing_class,
        "main_document": best.name,
        "main_document_score": best.score,
        "raw_chars": len(raw),
        "latency_ms": round(result.latency_ms, 1),
        "candidates": len(result.candidates),
        "toc_rejected": sum(1 for c in result.candidates if c.toc_rejected),
        "needs_review_items": [s.item_code for s in result.segments if s.needs_review],
        "pipeline_warnings": result.warnings,
        "items": {
            seg.item_code: {
                "status": seg.status,
                "confidence": round(seg.confidence, 3),
                "provenance": seg.provenance,
                "needs_review": seg.needs_review,
                "xbrl_check": seg.xbrl_check,
                "heading": seg.extracted_heading,
                "span_chars": (seg.end_offset - seg.start_offset)
                if seg.status not in ("missing", "reserved") or seg.text_sha256 else 0,
                "warnings": seg.warnings,
            }
            for seg in result.segments
        },
    }
    print(json.dumps(record, indent=1))


if __name__ == "__main__":
    main()
