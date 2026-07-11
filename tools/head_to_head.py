"""Head-to-head per-item F1 on the NTU itemseg external benchmark (P0-2, sister
deliverable A) — our pipeline vs edgartools (5.42.0) vs datamule (optional) on
the SAME gold slice.

Gold: NTU itemseg line-level BIO labels (arXiv 2502.08875; fetch via
tools/fetch_ntu_itemseg.py — research-only data, never committed).

Metric (line-level per-item F1, shape comparable to tools/score_offsets.py):
  Every engine outputs item_code -> text. For each non-trivial gold line we
  test alnum-normalized substring containment in each item's normalized text;
  per item: tp = gold lines of that item found in it, fn = gold lines of that
  item not found, fp = other-item / outside lines found in it. This adapter is
  engine-agnostic and normalization-robust, but is a LOWER BOUND: NTU lines
  come from inscriptis rendering, engines render HTML differently (documented
  in docs/research/external_benchmark_spike.md). The NTU paper's own numbers
  are per-line BIO classification F1 — related but not identical; do not paste
  the two into one column without that caveat.

Sister deliverable B hook: for our engine each filing records per-item
needs_review/confidence, and the artifact reports verifier_false_pass = items
with line-F1 < 0.5 that our verifier passed clean (no needs_review, confidence
>= 0.6).

Usage (network: fetches the slice's EDGAR HTML through the rate-limited,
cached EdgarFetcher; SEC_EDGAR_USER_AGENT must be set):
  .venv/Scripts/python tools/head_to_head.py --slice 10 \
      [--dataset data/raw_filings/external/ntu_itemseg/itemseg10kdata] \
      [--engines ours,edgartools,edgar_crawler,datamule] \
      [--out data/sec_eval/scoring/head_to_head.json]
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from fetch_ntu_itemseg import (  # noqa: E402
    DEFAULT_DEST,
    gold_csv_path,
    gold_line_labels,
    load_report_list,
    parse_bio_csv,
)

MAX_SLICE = 30  # corpus-run bound: stratified sample <= 30 filings
MIN_LINE_CHARS = 8  # alnum chars; shorter lines are noise (page numbers, blanks)

_ALNUM = re.compile(r"[^a-z0-9]+")


def _norm(text: str) -> str:
    """Rendering-robust form: lowercase, alphanumeric only."""
    return _ALNUM.sub("", text.lower())


# -- scoring -------------------------------------------------------------------

def score_engine_lines(gold_rows: list[tuple[str, str]],
                       engine_items: dict[str, str],
                       min_line_chars: int = MIN_LINE_CHARS) -> dict:
    """Line-level per-item P/R/F1 for one filing.

    Returns {"items": {code: {tp, fp, fn, precision, recall, f1}},
             "macro_f1": float | None, "gold_lines_scored": int}.
    Items appear if they have gold lines OR engine text (fp-only items count).
    """
    norm_items = {code: _norm(text) for code, text in engine_items.items()
                  if text and _norm(text)}
    labels = gold_line_labels(gold_rows)

    counts: dict[str, dict[str, int]] = {}

    def _cnt(code: str) -> dict[str, int]:
        return counts.setdefault(code, {"tp": 0, "fp": 0, "fn": 0})

    scored = 0
    for (label_raw, line), gold_code in zip(gold_rows, labels):
        nline = _norm(line)
        if len(nline) < min_line_chars:
            continue
        scored += 1
        hits = {code for code, ntext in norm_items.items() if nline in ntext}
        if gold_code is not None:
            if gold_code in hits:
                _cnt(gold_code)["tp"] += 1
            else:
                _cnt(gold_code)["fn"] += 1
            for code in hits - {gold_code}:
                _cnt(code)["fp"] += 1
        else:
            for code in hits:
                _cnt(code)["fp"] += 1

    items: dict[str, dict] = {}
    f1s: list[float] = []
    for code in sorted(counts, key=lambda c: (len(c), c)):
        c = counts[code]
        tp, fp, fn = c["tp"], c["fp"], c["fn"]
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * p * r / (p + r) if p + r else 0.0
        items[code] = {"tp": tp, "fp": fp, "fn": fn,
                       "precision": round(p, 4), "recall": round(r, 4),
                       "f1": round(f1, 4)}
        if tp + fn:  # macro over items that actually have gold lines
            f1s.append(f1)
    return {"items": items,
            "macro_f1": round(sum(f1s) / len(f1s), 4) if f1s else None,
            "gold_lines_scored": scored}


# -- engines (each: raw_html -> dict[item_code, text] | None) -------------------

def run_ours(raw_html: str, filing_id: str) -> tuple[dict[str, str] | None, dict]:
    """Our pipeline. Second return: per-item verifier surface (deliverable B)."""
    from sec_core.pipeline import extract_from_html
    result = extract_from_html(raw_html, filing_id)
    items: dict[str, str] = {}
    verifier: dict[str, dict] = {}
    for seg in result.segments:
        # Score the DELIVERED clean text (two-layer output: TOC-navigation
        # backlink lines removed; raw span/offsets unchanged for provenance).
        text = result.clean_text_of(seg.item_code)
        if text.strip():
            items[seg.item_code] = text
        verifier[seg.item_code] = {
            "status": seg.status,
            "confidence": seg.confidence,
            "needs_review": seg.needs_review,
        }
    return (items or None), verifier


def run_edgartools(raw_html: str, filing_id: str) -> tuple[dict[str, str] | None, dict]:
    from sec_core.third_engine import extract_items_edgartools
    return extract_items_edgartools(raw_html), {}


def run_datamule(raw_html: str, filing_id: str) -> tuple[dict[str, str] | None, dict]:
    """datamule/doc2dict (MIT, pinned 5.0.1) — P0-7c engine adapter."""
    from sec_core.engines import extract_items_datamule
    items = extract_items_datamule(raw_html)
    if items is None:
        raise EngineUnavailable("datamule unavailable (not installed or parse crash)")
    return items, {}


def run_edgar_crawler(raw_html: str, filing_id: str) -> tuple[dict[str, str] | None, dict]:
    """nlpaueb/edgar-crawler run arms-length as an unmodified subprocess (P0-7a)."""
    from sec_core.engines import ensure_checkout, extract_items_edgar_crawler
    checkout = ensure_checkout()
    if checkout is None:
        raise EngineUnavailable("edgar-crawler checkout missing "
                                "(ensure_checkout(fetch=True) to clone)")
    items = extract_items_edgar_crawler(raw_html, checkout=checkout)
    if items is None:
        raise EngineUnavailable("edgar-crawler subprocess failed or no items")
    return items, {}


class EngineUnavailable(RuntimeError):
    pass


ENGINES = {"ours": run_ours, "edgartools": run_edgartools,
           "edgar_crawler": run_edgar_crawler, "datamule": run_datamule}


# -- slice selection -------------------------------------------------------------

def stratified_slice(reports: list[dict], n: int, fold: str = "test") -> list[dict]:
    """Evenly spaced over the date-sorted fold (era-stratified). Hard cap 30."""
    if n > MAX_SLICE:
        raise ValueError(f"slice {n} exceeds corpus-run bound {MAX_SLICE}")
    pool = sorted((r for r in reports if r["fold"] == fold),
                  key=lambda r: (r["date_filed"], r["uid"]))
    if not pool or n <= 0:
        return []
    if n >= len(pool):
        return pool
    step = len(pool) / n
    return [pool[int(i * step)] for i in range(n)]


# -- CLI harness -----------------------------------------------------------------

def _arg(flag: str, default: str) -> str:
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default


def main() -> None:  # pragma: no cover — network harness; pieces unit-tested
    dataset_dir = Path(_arg("--dataset", str(DEFAULT_DEST / "itemseg10kdata")))
    n = int(_arg("--slice", "10"))
    engine_names = [e.strip() for e in _arg("--engines", "ours,edgartools").split(",")]
    out_path = Path(_arg("--out", "data/sec_eval/scoring/head_to_head.json"))
    cache_dir = Path(_arg("--cache", str(DEFAULT_DEST / "html_cache")))

    if not dataset_dir.exists():
        raise SystemExit(f"dataset missing: {dataset_dir} — run tools/fetch_ntu_itemseg.py first")
    unknown = [e for e in engine_names if e not in ENGINES]
    if unknown:
        raise SystemExit(f"unknown engines {unknown}; choose from {sorted(ENGINES)}")

    from sec_core.fetcher import EdgarFetcher
    fetcher = EdgarFetcher(cache_dir=cache_dir)

    reports = load_report_list(dataset_dir)
    chosen = stratified_slice(reports, n)
    print(f"slice: {len(chosen)} test-fold filings (of "
          f"{sum(1 for r in reports if r['fold'] == 'test')})")

    filings: list[dict] = []
    for rpt in chosen:
        gold_rows = parse_bio_csv(gold_csv_path(dataset_dir, rpt["uid"], rpt["fold"]))
        t0 = time.perf_counter()
        raw_html = fetcher.get(rpt["link"]).content.decode("utf-8", errors="replace")
        row: dict = {"uid": rpt["uid"], "cik": rpt["cik"], "company": rpt["company"],
                     "date_filed": rpt["date_filed"], "link": rpt["link"],
                     "fetch_ms": round((time.perf_counter() - t0) * 1000, 1),
                     "engines": {}}
        for name in engine_names:
            try:
                items, verifier = ENGINES[name](raw_html, f"ntu_{rpt['uid']}")
            except EngineUnavailable as exc:
                row["engines"][name] = {"error": str(exc)}
                continue
            except Exception as exc:  # noqa: BLE001 — engine crash is its own result
                row["engines"][name] = {"error": f"engine crash: {exc!r}"}
                continue
            if not items:
                row["engines"][name] = {"error": "no items extracted"}
                continue
            scored = score_engine_lines(gold_rows, items)
            if name == "ours" and verifier:
                scored["verifier"] = verifier
                scored["verifier_false_pass"] = [
                    code for code, m in scored["items"].items()
                    if m["f1"] < 0.5 and m["tp"] + m["fn"] > 0
                    and not verifier.get(code, {}).get("needs_review", False)
                    and verifier.get(code, {}).get("confidence", 0.0) >= 0.6
                ]
            row["engines"][name] = scored
            print(f"  {rpt['uid']} {name}: macro_f1={scored['macro_f1']}")
        filings.append(row)

    # aggregate: per-engine macro over filings + per-item micro
    summary: dict[str, dict] = {}
    for name in engine_names:
        macros = [f["engines"][name]["macro_f1"] for f in filings
                  if "macro_f1" in f["engines"].get(name, {})
                  and f["engines"][name]["macro_f1"] is not None]
        failures = sum(1 for f in filings if "error" in f["engines"].get(name, {}))
        fp_count = sum(len(f["engines"][name].get("verifier_false_pass", []))
                       for f in filings if name == "ours" and "items" in f["engines"].get(name, {}))
        summary[name] = {
            "filings_scored": len(macros),
            "engine_failures": failures,
            "macro_f1_filings": round(sum(macros) / len(macros), 4) if macros else None,
        }
        if name == "ours":
            summary[name]["verifier_false_pass_items"] = fp_count

    artifact = {
        "generated_by": "tools/head_to_head.py",
        "gold": "NTU itemseg (arXiv 2502.08875), line-level BIO, test fold",
        "metric": "line-level per-item F1 via alnum-normalized containment (lower bound)",
        "slice": len(chosen),
        "summary": summary,
        "filings": filings,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(artifact, indent=1), encoding="utf-8")

    print()
    print("| engine | filings scored | engine failures | macro F1 (filings) |")
    print("|---|---|---|---|")
    for name, s in summary.items():
        print(f"| {name} | {s['filings_scored']} | {s['engine_failures']} "
              f"| {s['macro_f1_filings']} |")
    print(f"\nartifact -> {out_path}")


if __name__ == "__main__":
    main()
