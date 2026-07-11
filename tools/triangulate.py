"""Triangulate extracted items against independent engines (2-of-N voting).

Usage: .venv/Scripts/python tools/triangulate.py [--engines LIST] [TICKER ...]
  --engines  comma list from {edgartools, edgar_crawler, datamule}
             (default: all three; unavailable engines degrade to
             engine_unavailable votes, never penalties)

Runs our pipeline and every requested engine on the SAME cached raw HTML and
writes per-item votes + the 2-of-N aggregate to
data/sec_eval/triangulation/triangulation.json. Only an uncorroborated
disagree lowers confidence / flags needs_review (sec_core.third_engine); an
engine outvoted by another engine's agreement is recorded as a warning.
edgar_crawler runs the UNMODIFIED GPLv3 CLI in a subprocess on a local
checkout (auto-cloned, pinned commit, gitignored path — sec_core.engines).
Requires SEC_EDGAR_USER_AGENT (fetches are cache-first).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from sec_core.engines import (
    ensure_checkout,
    extract_items_datamule,
    extract_items_edgar_crawler,
)
from sec_core.fetcher import EdgarFetcher
from sec_core.main_doc import pick_main_document
from sec_core.pipeline import extract_from_html
from sec_core.resolver import FilingResolver
from sec_core.third_engine import apply_triangulation, extract_items_edgartools

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "sec_eval" / "triangulation"

SWEEP_TICKERS = ["AAPL", "MSFT", "NVDA", "JPM", "GS", "WMT", "CAT", "XOM", "NEM", "MRNA", "KO"]
ALL_ENGINES = ("edgartools", "edgar_crawler", "datamule")
VERDICTS = ("agree", "disagree", "engine_suspect", "engine_unavailable")


def run_engines(raw: str, engines: list[str]) -> tuple[dict[str, str] | None, dict]:
    """-> (edgartools items, extra_engines dict) for apply_triangulation."""
    primary = extract_items_edgartools(raw) if "edgartools" in engines else None
    extras: dict[str, dict[str, str] | None] = {}
    if "edgar_crawler" in engines:
        extras["edgar_crawler"] = extract_items_edgar_crawler(raw)
    if "datamule" in engines:
        extras["datamule"] = extract_items_datamule(raw)
    return primary, extras


def main() -> None:
    args = sys.argv[1:]
    engines = list(ALL_ENGINES)
    if "--engines" in args:
        i = args.index("--engines")
        engines = [e.strip() for e in args[i + 1].split(",") if e.strip()]
        del args[i:i + 2]
    unknown = [e for e in engines if e not in ALL_ENGINES]
    if unknown:
        raise SystemExit(f"unknown engines {unknown}; choose from {list(ALL_ENGINES)}")
    tickers = [t.upper() for t in args] or SWEEP_TICKERS

    if "edgar_crawler" in engines:
        checkout = ensure_checkout(fetch=True)
        print(f"edgar-crawler checkout: {checkout or 'UNAVAILABLE (votes degrade)'}")

    fetcher = EdgarFetcher(cache_dir=ROOT / "data" / "raw_filings")
    resolver = FilingResolver(fetcher)
    OUT.mkdir(parents=True, exist_ok=True)
    records = []
    print(f"{'ticker':<7} {'agree':>5} {'disagree':>8} {'suspect':>7} {'unavail':>7}  "
          f"disagreeing items")
    for t in tickers:
        try:
            cik = resolver.cik_for_ticker(t)
            ref = next((f for f in resolver.annual_filings(cik) if not f.is_amendment), None)
            if ref is None:
                print(f"{t:<7} no 10-K")
                continue
            resolver.load_files(ref)
            best = pick_main_document(ref)
            doc_url = ref.file_url(best.name)
            raw = fetcher.get(doc_url).content.decode("utf-8", errors="replace")
            result = extract_from_html(raw, f"{t}-{ref.accession}")
            primary, extras = run_engines(raw, engines)
            comparisons = apply_triangulation(result, primary, extras or None)
            by_item: dict[str, dict] = {}
            for c in comparisons:
                by_item.setdefault(c.item_code, {"votes": {}})["votes"][c.source] = {
                    "verdict": c.verdict, "detail": c.detail,
                    "our_words": c.our_words, "engine_words": c.engine_words,
                    "overlap": round(c.overlap, 3),
                }
            by_verdict = dict.fromkeys(VERDICTS, 0)
            for code, entry in by_item.items():
                seg = result.segment(code)
                # aggregate 2-of-N verdict is the engine_check prefix
                entry["verdict"] = seg.engine_check.split(":", 1)[0]
                # our span's word count is engine-independent — kept at entry
                # level for consumers (tests/test_verifier_mutations.py proxies)
                entry["our_words"] = max(v["our_words"] for v in entry["votes"].values())
                entry["our_status"] = seg.status
                entry["confidence_after"] = round(seg.confidence, 3)
                entry["needs_review"] = seg.needs_review
                by_verdict[entry["verdict"]] += 1
            disagreeing = sorted(k for k, v in by_item.items() if v["verdict"] == "disagree")
            suspect = sorted(k for k, v in by_item.items() if v["verdict"] == "engine_suspect")
            records.append({
                "ticker": t, "cik": cik, "accession": ref.accession,
                "doc_url": doc_url,
                "filing_class": result.filing_class,
                "engines_run": engines,
                "engine_parsed": primary is not None,
                "engine_items": sorted(primary) if primary else [],
                "verdicts": by_verdict,
                "items": by_item,
            })
            print(f"{t:<7} {by_verdict['agree']:>5} {by_verdict['disagree']:>8} "
                  f"{by_verdict['engine_suspect']:>7} {by_verdict['engine_unavailable']:>7}  "
                  f"{', '.join(disagreeing) or '-'}"
                  + (f"  [suspect: {', '.join(suspect)}]" if suspect else ""))
        except Exception as e:  # noqa: BLE001 - tool records failures, does not crash the sweep
            print(f"{t:<7} ERROR {type(e).__name__}: {e}")

    try:
        import edgar
        engine_ver = f"edgartools {getattr(edgar, '__version__', '?')}"
    except Exception:  # noqa: BLE001
        engine_ver = "edgartools (not importable)"
    outvoted = {
        r["ticker"]: {k: [s for s, v in e["votes"].items() if v["verdict"] == "disagree"]
                      for k, e in r["items"].items()
                      if e["verdict"] == "agree"
                      and any(v["verdict"] == "disagree" for v in e["votes"].values())}
        for r in records
    }
    summary = {
        "engine": engine_ver,
        "engines": engines,
        "voting": "2-of-N (P0-7): any corroborating engine confirms; only an "
                  "uncorroborated disagree penalises",
        "filings": len(records),
        "verdict_totals": {v: sum(r["verdicts"].get(v, 0) for r in records)
                           for v in VERDICTS},
        "disagreements": {r["ticker"]: [k for k, v in r["items"].items()
                                        if v["verdict"] == "disagree"]
                          for r in records if r["verdicts"]["disagree"]},
        "engine_suspects": {r["ticker"]: [k for k, v in r["items"].items()
                                          if v["verdict"] == "engine_suspect"]
                            for r in records if r["verdicts"].get("engine_suspect")},
        "outvoted": {t: m for t, m in outvoted.items() if m},
        "records": records,
    }
    (OUT / "triangulation.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\n{summary['verdict_totals']} · disagreements: {summary['disagreements'] or 'none'}")
    if summary["outvoted"]:
        print(f"outvoted (agree despite a dissenting engine): {summary['outvoted']}")
    print(f"wrote {OUT / 'triangulation.json'}")


if __name__ == "__main__":
    main()
