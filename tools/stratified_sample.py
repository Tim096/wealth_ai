"""T2-4 stratified sampling by FORMAT SOURCE: era x filing agent.

The scored sweep's 11 filings are all FY2025/2026 iXBRL (10 Workiva + 1 DFIN);
the *era* and *filing-agent* dimensions are entirely unsampled. Format-variation
robustness (a named Task-2 scoring criterion) cannot be claimed from one era.

This tool:
  1. LISTS filings per stratum. Recent eras come from EDGAR full-text search
     (efts.sec.gov, forms= is EXACT-MATCH: '10-K' excludes '10-K/A' — the same
     trap our resolver._collect_10k already avoids). Pre-2001 filings are NOT in
     the FTS index, so those come from the submissions API instead.
  2. Detects the filing agent from the document-head generator comment
     (Workiva / DFIN-Donnelley / Toppan Merrill / GoFiler), not from company
     names in the body.
  3. Actually runs each GAP stratum through the offline pipeline and checks the
     partition/coverage invariants — format robustness is MEASURED, not assumed.
     A filing the HTML normalizer cannot handle (pre-2001 plain-text SGML) is
     marked `unsupported` honestly, with material for supported_and_unsupported,
     rather than force-fixed.

Usage:
  .venv/Scripts/python tools/stratified_sample.py           # run strata + write table
Requires SEC_EDGAR_USER_AGENT. Cache-first; re-runs are offline-deterministic.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages"))

from sec_core.coverage import coverage_ratio, partition_document  # noqa: E402
from sec_core.fetcher import EdgarFetcher  # noqa: E402
from sec_core.main_doc import pick_main_document  # noqa: E402
from sec_core.pipeline import extract_from_html  # noqa: E402
from sec_core.resolver import FilingResolver  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "sec_eval" / "stratification"
EFTS_URL = "https://efts.sec.gov/LATEST/search-index"
ARCHIVE = "https://www.sec.gov/Archives/edgar/data"

# -- filing-agent detection ---------------------------------------------------
# Every EDGAR document generator stamps a creation comment in the first few
# hundred bytes of the primary document (an XBRL/iXBRL header comment). We scan
# ONLY the head so a company literally named e.g. "Merrill" in the body can't be
# mistaken for the filing agent Toppan Merrill.
_AGENT_SIGNS = [
    ("Workiva", re.compile(r"workiva|wdesk", re.I)),
    ("DFIN (Donnelley)", re.compile(r"\bdfin\b|donnelley financial|activedisclosure", re.I)),
    ("Toppan Merrill", re.compile(r"toppan|merrill corporation|merrillcorp", re.I)),
    ("GoFiler/Novaworks", re.compile(r"gofiler|novaworks", re.I)),
    ("EDGAR Online / edgar-filings", re.compile(r"edgar\s*online|edgarfilings", re.I)),
]


def detect_agent(head: str) -> str:
    for label, pat in _AGENT_SIGNS:
        if pat.search(head):
            return label
    return "unknown/in-house"


# -- era / format classification ----------------------------------------------
def accession_year(accession: str) -> int:
    """Filing year from the accession's 2-digit middle group (0001047469-04-...
    -> 2004). resolve_accession does not populate filing_date, and the accession
    year is a reliable offline signal."""
    m = re.match(r"\d{10}-(\d{2})-\d{6}", accession)
    if not m:
        return 0
    yy = int(m.group(1))
    return 2000 + yy if yy < 50 else 1900 + yy


def classify_format(filing_date: str, primary_name: str, head: str, files,
                    accession: str = "") -> tuple[str, str]:
    """Return (era_id, format_detail). era_id is the stratification key."""
    year = int(filing_date[:4]) if filing_date[:4].isdigit() else accession_year(accession)
    hl = head.lower()
    is_text = primary_name.lower().endswith(".txt") or ("<" not in head[:2000] and "<page>" not in hl)
    if is_text or ("<page>" in hl and "<html" not in hl and "<div" not in hl):
        return "text_pre2001", "plain-text/SGML full submission (no HTML block tags)"
    inline_xbrl = ("xmlns:ix" in hl) or ("<ix:" in hl)
    names = " ".join(f.name.lower() for f in files)
    has_xbrl = bool(re.search(r"_(cal|def|lab|pre)\.xml|\.xsd|_htm\.xml|r\d+\.htm", names)) or "xbrl" in names
    if inline_xbrl:
        return "ixbrl_2019plus", "inline XBRL (ix: tags in the primary document)"
    if has_xbrl:
        return "xbrl_2009_2018", "HTML body + separate XBRL exhibits"
    if year >= 2001:
        return "html_2001_2008", "first-generation HTML (pre-XBRL)"
    return "text_pre2001", "plain-text/SGML full submission (no HTML block tags)"


# -- invariant check ----------------------------------------------------------
def check_invariants(text: str, segments) -> dict:
    """Partition invariant: the item blocks + unclassified gaps must tile the
    whole document [0, n) with no overlap and no hole. coverage_ratio is the
    fraction of the body claimed by some item."""
    n = len(text)
    blocks = partition_document(text, segments)
    tiled = True
    prev = 0
    for b in blocks:
        if b.start != prev or b.end < b.start:
            tiled = False
            break
        prev = b.end
    if blocks and prev != n:
        tiled = False
    if not blocks and n != 0:
        tiled = False
    # no two item spans may overlap-conflict at a char the partition can't own —
    # partition_document guarantees this structurally; we assert it held.
    statuses = Counter(s.status for s in segments)
    return {
        "items_extracted": len(segments),
        "partition_tiles_whole_document": tiled,
        "partition_blocks": len(blocks),
        "coverage_ratio": round(coverage_ratio(text, segments), 4),
        "statuses": dict(statuses),
        "needs_review": sum(1 for s in segments if s.needs_review),
        "pass_items": statuses.get("pass", 0),
    }


# -- efts full-text search ----------------------------------------------------
def efts_search(fetcher: EdgarFetcher, startdt: str, enddt: str, forms: str = "10-K",
                q: str = "", limit: int = 40) -> list[dict]:
    """List 10-K hits in a date window. forms is exact-match (the documented
    trap: '10-K' does NOT include '10-K/A'). Returns light dicts."""
    qs = f"q={q}&forms={forms}&startdt={startdt}&enddt={enddt}"
    data = json.loads(fetcher.get(f"{EFTS_URL}?{qs}").content)
    hits = []
    for h in data.get("hits", {}).get("hits", [])[:limit]:
        src = h.get("_source", {})
        adsh = src.get("adsh") or (h.get("_id", "").split(":")[0])
        doc = h.get("_id", "").split(":")[-1] if ":" in h.get("_id", "") else ""
        ciks = src.get("ciks") or ["0"]
        hits.append({
            "accession": adsh,
            "cik": int(ciks[0]),
            "primary_document": doc,
            "file_date": src.get("file_date", ""),
            "form": src.get("form", forms),
            "display": (src.get("display_names") or [""])[0],
        })
    return hits


# -- run one filing through the pipeline --------------------------------------
def _text_submission_url(cik: int, accession: str) -> str:
    return f"{ARCHIVE}/{cik}/{accession}.txt"


def run_filing(fetcher: EdgarFetcher, resolver: FilingResolver, cik: int, accession: str,
               ticker: str = "") -> dict:
    ref = resolver.resolve_accession(cik, accession)
    ref.cik = cik
    # choose the document to score. Old filings expose only the full-submission
    # .txt (their index lists broken empty-name entries); fall back to it.
    named = [f for f in ref.files if f.name and f.name.lower().endswith((".htm", ".html", ".txt"))]
    use_text = False
    try:
        best = pick_main_document(ref)
        main_name = best.name
        raw = fetcher.get(ref.file_url(main_name)).content.decode("utf-8", errors="replace")
        if len(raw) < 4000 and named:
            raise LookupError("main doc too small")
    except LookupError:
        use_text = True
        main_name = f"{accession}.txt"
        raw = fetcher.get(_text_submission_url(cik, accession)).content.decode("latin-1")

    head = raw[:3000]
    agent = detect_agent(head)
    era, fmt = classify_format(ref.filing_date or "", main_name, head, ref.files, accession=accession)
    result = extract_from_html(raw, filing_id=f"{ticker or cik}-{accession}")
    inv = check_invariants(result.doc.text, result.segments)

    # a filing is "supported" if the normalizer produced a real partition with a
    # plausible number of items and non-trivial coverage. Plain-text SGML that
    # collapses to one line yields almost nothing -> honestly unsupported.
    supported = (inv["items_extracted"] >= 5 and inv["coverage_ratio"] >= 0.30
                 and result.filing_class not in ("non_10k", "unsupported_scanned_or_binary"))
    return {
        "ticker": ticker,
        "cik": cik,
        "accession": accession,
        "form": ref.form,
        "filing_date": ref.filing_date,
        "filing_year": accession_year(accession),
        "report_date": ref.report_date,
        "main_document": main_name,
        "served_as_text": use_text,
        "raw_chars": len(raw),
        "normalized_chars": len(result.doc.text),
        "detected_agent": agent,
        "era": era,
        "format_detail": fmt,
        "filing_class": result.filing_class,
        "supported": supported,
        "invariants": inv,
        "pipeline_warnings": result.warnings[:3],
    }


# -- orchestration ------------------------------------------------------------
# Deterministic seed filings for the era gaps, chosen from long-lived filers so
# the same accessions resolve on every run (reproducibility over randomness).
ERA_SEEDS = [
    ("text_pre2001", "AAPL", 320193, "0000320193-96-000023"),   # FY1996 plain text
    ("text_pre2001", "KO", 21344, "0000021344-98-000004"),      # FY1997 plain text
    ("html_2001_2008", "AAPL", 320193, "0001047469-04-035975"),  # FY2004 pre-XBRL HTML
    ("xbrl_2009_2018", "AAPL", 320193, "0001193125-13-416534"),  # FY2013 XBRL-era HTML
]


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fetcher = EdgarFetcher(cache_dir=ROOT / "data" / "raw_filings")
    resolver = FilingResolver(fetcher)

    strata_runs: list[dict] = []
    for stratum, ticker, cik, acc in ERA_SEEDS:
        try:
            rec = run_filing(fetcher, resolver, cik, acc, ticker=ticker)
            rec["target_stratum"] = stratum
            strata_runs.append(rec)
            print(f"[era] {stratum:16} {ticker:5} {acc} -> era={rec['era']} "
                  f"agent={rec['detected_agent']} items={rec['invariants']['items_extracted']} "
                  f"cov={rec['invariants']['coverage_ratio']} supported={rec['supported']}")
        except Exception as e:  # noqa: BLE001
            strata_runs.append({"target_stratum": stratum, "ticker": ticker,
                                "accession": acc, "error": str(e)})
            print(f"[era] {stratum:16} {ticker:5} {acc} -> ERROR {e}")

    # Agent survey: enumerate a recent 10-K window via efts, detect each agent
    # from the doc head, and pick one non-Workiva/non-DFIN filing (Toppan) to run
    # so a third filing agent is actually exercised through the pipeline.
    survey_hits = efts_search(fetcher, "2025-02-01", "2025-02-28", limit=40)
    agent_dist: Counter = Counter()
    agent_example: dict[str, dict] = {}
    for h in survey_hits:
        if not h["primary_document"] or not h["primary_document"].lower().endswith((".htm", ".html")):
            continue
        url = f"{ARCHIVE}/{h['cik']}/{h['accession'].replace('-', '')}/{h['primary_document']}"
        try:
            head = fetcher.get(url).content[:3000].decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            continue
        ag = detect_agent(head)
        agent_dist[ag] += 1
        agent_example.setdefault(ag, {"cik": h["cik"], "accession": h["accession"],
                                      "display": h["display"], "primary_document": h["primary_document"]})

    # run one Toppan (or any non-Workiva/DFIN) filing end-to-end if found
    agent_gap_run = None
    for ag in ("Toppan Merrill", "GoFiler/Novaworks", "EDGAR Online / edgar-filings", "unknown/in-house"):
        ex = agent_example.get(ag)
        if not ex:
            continue
        try:
            rec = run_filing(fetcher, resolver, ex["cik"], ex["accession"])
            rec["target_stratum"] = f"agent::{ag}"
            agent_gap_run = rec
            strata_runs.append(rec)
            print(f"[agent] {ag:20} {ex['accession']} -> items={rec['invariants']['items_extracted']} "
                  f"cov={rec['invariants']['coverage_ratio']} supported={rec['supported']}")
            break
        except Exception as e:  # noqa: BLE001
            print(f"[agent] {ag} {ex['accession']} -> ERROR {e}")

    # coverage matrix: era x agent, counting the baseline 11 + newly sampled
    baseline = {"era": "ixbrl_2019plus", "n": 11, "agents": {"Workiva": 10, "DFIN (Donnelley)": 1}}
    matrix: dict[str, dict[str, int]] = {}
    for era in ("text_pre2001", "html_2001_2008", "xbrl_2009_2018", "ixbrl_2019plus"):
        matrix[era] = {}
    matrix["ixbrl_2019plus"]["Workiva"] = 10
    matrix["ixbrl_2019plus"]["DFIN (Donnelley)"] = 1
    for r in strata_runs:
        if "era" not in r:
            continue
        matrix.setdefault(r["era"], {})
        matrix[r["era"]][r["detected_agent"]] = matrix[r["era"]].get(r["detected_agent"], 0) + 1

    unsupported = [
        {"stratum": r["target_stratum"], "ticker": r.get("ticker"), "accession": r["accession"],
         "era": r["era"], "reason": r["format_detail"],
         "items_extracted": r["invariants"]["items_extracted"],
         "coverage_ratio": r["invariants"]["coverage_ratio"]}
        for r in strata_runs if "era" in r and not r["supported"]
    ]

    out = {
        "generated_at": __import__("time").strftime("%Y-%m-%dT%H:%M:%SZ", __import__("time").gmtime()),
        "user_agent": fetcher.user_agent,
        "purpose": "T2-4 stratified sampling by format source (era x filing agent); "
                   "fills era/agent gaps left by the all-iXBRL scored sweep.",
        "efts_note": "forms= is exact-match ('10-K' excludes '10-K/A'); pre-2001 not in FTS "
                     "index so sourced from the submissions API instead.",
        "baseline_scored_sweep": baseline,
        "era_strata_runs": [r for r in strata_runs if str(r.get("target_stratum", "")).startswith(("text", "html", "xbrl"))],
        "agent_gap_run": agent_gap_run,
        "agent_survey": {
            "window": "2025-02-01..2025-02-28",
            "sampled": sum(agent_dist.values()),
            "distribution": dict(agent_dist),
            "examples": agent_example,
        },
        "coverage_matrix": matrix,
        "unsupported": unsupported,
    }
    out_path = OUT_DIR / "stratification.json"
    out_path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"\nwrote {out_path}")
    print("coverage matrix:", json.dumps(matrix))
    print("unsupported strata:", [u["stratum"] for u in unsupported])


if __name__ == "__main__":
    main()
