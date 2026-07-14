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


def run(ticker: str, cik: int | None = None, accession: str | None = None):
    fetcher = EdgarFetcher(cache_dir=ROOT / "data" / "raw_filings")
    resolver = FilingResolver(fetcher)
    # `cik` overrides ticker resolution (for pseudo-tickers like CITI whose SEC
    # ticker is 'C'); `accession` pins a specific historical 10-K instead of the
    # latest — both needed to regenerate a frozen record deterministically.
    if cik is None:
        cik = resolver.cik_for_ticker(ticker)
    filings = resolver.annual_filings(cik)
    if accession:
        ref = next((f for f in filings if f.accession == accession), None)
    else:
        ref = next((f for f in filings if not f.is_amendment), None)
    if ref is None:
        raise SystemExit(f"no 10-K for {ticker} (cik={cik}, accession={accession or 'latest'})")
    resolver.load_files(ref)
    best = pick_main_document(ref)
    raw = fetcher.get(ref.file_url(best.name)).content.decode("utf-8", errors="replace")
    # persist a replayable EvidenceRecord JSONL per run through the shared store
    store = EvidenceStore(EVIDENCE)
    run_id = f"sec-{ticker}-{ref.accession}"
    result = extract_from_html(raw, filing_id=f"{ticker}-{ref.accession}",
                               evidence_store=store, run_id=run_id)
    # apply the XBRL oracle so the SHIPPED record carries the gated Item 8
    # status — including a cross-reference filing whose Item 8 we resolved from
    # page anchors (Intel), which is the strongest possible check: two
    # independent methods (page-anchor resolution + XBRL) must agree.
    item8 = next((s for s in result.segments if s.item_code == "8"), None)
    if item8 is not None and item8.end_offset > item8.start_offset:
        try:
            certify_item8(result, fetcher, cik, ref.accession)
        except Exception:  # noqa: BLE001 — certification is best-effort enrichment
            pass
    return ref, best, raw, result


def _arg(flag: str):
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else None


def main() -> None:
    ticker = sys.argv[1].upper()
    cik = _arg("--cik")
    ref, best, raw, result = run(ticker, cik=int(cik) if cik else None,
                                 accession=_arg("--accession"))

    if "--item" in sys.argv:
        code = sys.argv[sys.argv.index("--item") + 1].upper()
        print(result.text_of(code))
        return

    # TOC-rejected candidates are the filing's own claim of which items exist —
    # the scoring layer maps `missing` + toc_listed to the MISSING tri-state.
    toc_codes = {c.code for c in result.candidates if c.toc_rejected}
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
        "normalized_chars": len(result.doc.text),
        "latency_ms": round(result.latency_ms, 1),
        "llm_calls": result.llm_calls,
        "llm_tokens": result.llm_input_tokens + result.llm_output_tokens,
        "llm_usd": round(result.llm_cost_usd, 6),
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
                "start_offset": seg.start_offset,
                "end_offset": seg.end_offset,
                "source_ranges": [list(r) for r in seg.source_ranges],
                "text_sha256": seg.text_sha256,
                "toc_listed": seg.item_code in toc_codes,
                # real body length: sum of the multi-range spans (not the
                # envelope) for a reassembled item, else the single span
                "span_chars": (sum(b - a for a, b in seg.source_ranges) if seg.source_ranges
                               else (seg.end_offset - seg.start_offset)
                               if seg.status not in ("missing", "reserved") or seg.text_sha256 else 0),
                "warnings": seg.warnings,
            }
            for seg in result.segments
        },
    }
    print(json.dumps(record, indent=1))


if __name__ == "__main__":
    main()
