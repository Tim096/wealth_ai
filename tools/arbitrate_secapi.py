"""sec-api.io Extractor API arbitration protocol (P0-7b) — a commercially
independent (closed-source) fourth lineage that adjudicates our triangulation
disagreements: for each uncorroborated disagree item it fetches sec-api's
extraction of the SAME item and rules which side it corroborates.

Hard constraints (why this tool is shaped the way it is):
- free tier = 100 LIFETIME calls: cache-first (every response hits disk
  BEFORE it is used), one call per unique (filing, item) ever, and an
  explicit per-run --max-calls budget (default 0 = plan only). Burning the
  quota is a USER decision: without SECAPI_KEY in the environment the tool
  only (re)generates the ready-to-run state doc
  data/sec_eval/arbitration/README.md — it NEVER signs up for an account.
- ToS: cached responses are internal eval material only. cache/ is gitignored
  (data/sec_eval/arbitration/.gitignore); artifacts store verdicts and word
  counts, never sec-api payload text.
- sec-api's 10-K Extractor supports items 1..15 (incl. 1A/1B/7A/9A/9B) but
  NOT 1C, 9C, 16 (documented capability gap — cf. docs/prior_art.md);
  unsupported items are listed as unadjudicable, not silently dropped.

Usage:
  .venv/Scripts/python tools/arbitrate_secapi.py            # plan/state doc
  SECAPI_KEY=... .venv/Scripts/python tools/arbitrate_secapi.py --max-calls 15
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from sec_core.third_engine import compare_item  # noqa: E402

TRIANGULATION = ROOT / "data" / "sec_eval" / "triangulation" / "triangulation.json"
ARBITRATION_DIR = ROOT / "data" / "sec_eval" / "arbitration"
ENDPOINT = "https://api.sec-api.io/extractor"
LIFETIME_QUOTA = 100
# sec-api 10-K Extractor item coverage (their docs): no 1C, 9C, 16.
SUPPORTED_ITEMS = frozenset(
    ["1", "1A", "1B", "2", "3", "4", "5", "6", "7", "7A", "8", "9", "9A", "9B",
     "10", "11", "12", "13", "14", "15"])
_SENTINEL_RE = re.compile(r"##TABLE_(?:START|END)")


# -- plan ------------------------------------------------------------------------

def load_targets(triangulation: dict) -> list[dict]:
    """Arbitration targets out of triangulation.json, two tiers:
      disagree — uncorroborated disagreements (needs_review is live): sec-api
                 breaks the tie between our span and every dissenting engine
      outvoted — items that aggregate to agree only because another engine
                 corroborated us over a dissent: cheap spot-checks that the
                 2-of-N vote outvoted the RIGHT side
    Tolerates the pre-P0-7 single-engine schema (verdict per item, no votes /
    doc_url) whose disagreements all land in the disagree tier."""
    targets = []
    for rec in triangulation.get("records", []):
        for code, entry in sorted(rec.get("items", {}).items()):
            votes = entry.get("votes") or {}
            dissent = sorted(s for s, v in votes.items() if v.get("verdict") == "disagree")
            if entry.get("verdict") == "disagree":
                tier = "disagree"
            elif entry.get("verdict") == "agree" and dissent:
                tier = "outvoted"
            else:
                continue
            detail = (votes.get(dissent[0]) if dissent else None) or {}
            targets.append({
                "ticker": rec["ticker"], "accession": rec["accession"],
                "cik": rec.get("cik"), "doc_url": rec.get("doc_url"),
                "item": code, "tier": tier, "dissenting": dissent,
                "detail": detail.get("detail") or entry.get("detail", ""),
                "supported": code in SUPPORTED_ITEMS,
            })
    targets.sort(key=lambda t: (t["tier"] != "disagree", t["ticker"], t["item"]))
    return targets


def cache_path(cache_dir: Path, accession: str, item: str) -> Path:
    return cache_dir / f"{accession}_{item}.json"


def get_secapi_text(target: dict, key: str, cache_dir: Path, budget: dict,
                    fetch_fn=None) -> tuple[str | None, str]:
    """Cache-first fetch of one item's sec-api extraction.
    -> (text | None, status in {cached, fetched, budget_exhausted, no_doc_url,
    fetch_error}). Responses are written to disk BEFORE being returned."""
    path = cache_path(cache_dir, target["accession"], target["item"])
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))["text"], "cached"
    if not target.get("doc_url"):
        return None, "no_doc_url"
    if budget["calls_made"] >= budget["max_calls"]:
        return None, "budget_exhausted"
    if fetch_fn is None:
        fetch_fn = _http_fetch
    try:
        text = fetch_fn(target["doc_url"], target["item"], key)
    except Exception as exc:  # noqa: BLE001 — record, don't crash the run
        return None, f"fetch_error: {type(exc).__name__}: {exc}"
    budget["calls_made"] += 1
    cache_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "fetched_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "doc_url": target["doc_url"], "item": target["item"], "text": text,
    }, indent=1), encoding="utf-8")  # cache IMMEDIATELY (100 lifetime calls)
    return text, "fetched"


def _http_fetch(doc_url: str, item: str, key: str) -> str:
    import httpx
    resp = httpx.get(ENDPOINT, params={"url": doc_url, "item": item,
                                       "type": "text", "token": key}, timeout=60)
    resp.raise_for_status()
    return resp.text


# -- adjudication ------------------------------------------------------------------

def adjudicate(code: str, secapi_text: str, our_text: str,
               engine_texts: dict[str, str]) -> dict:
    """Which side does sec-api's extraction corroborate? Reuses the
    third_engine shingle-containment metric symmetrically. Rulings:
    ours / engine / both / neither."""
    clean = _SENTINEL_RE.sub(" ", secapi_text)
    vs_ours = compare_item(code, our_text, clean, "pass", source="secapi").verdict
    vs_engines = {name: compare_item(code, text, clean, "pass", source="secapi").verdict
                  for name, text in engine_texts.items() if text}
    ours_ok = vs_ours == "agree"
    engine_ok = any(v == "agree" for v in vs_engines.values())
    ruling = ("both" if ours_ok and engine_ok else
              "ours" if ours_ok else
              "engine" if engine_ok else "neither")
    return {"ruling": ruling, "secapi_vs_ours": vs_ours,
            "secapi_vs_engines": vs_engines}


# -- state doc ---------------------------------------------------------------------

def render_readme(targets: list[dict], cache_dir: Path,
                  results: dict[str, dict] | None = None,
                  calls_made_this_run: int = 0) -> str:
    adjudicable = [t for t in targets if t["supported"]]
    uncached = [t for t in adjudicable
                if not cache_path(cache_dir, t["accession"], t["item"]).is_file()]
    n_disagree = sum(1 for t in targets if t["tier"] == "disagree")
    lines = [
        "# sec-api.io arbitration — state (P0-7b)",
        "",
        f"Generated by `tools/arbitrate_secapi.py` on "
        f"{_dt.date.today().isoformat()} from "
        f"`data/sec_eval/triangulation/triangulation.json`.",
        "",
        "sec-api.io Extractor API is the external, closed-source arbitration "
        "vote for triangulation disagreements. **Free tier = 100 LIFETIME "
        "calls**, so every call is cached to `cache/` (gitignored — ToS: "
        "internal eval only, payload text never committed) before use, and "
        "spending the quota requires an explicit `--max-calls` from the user. "
        "This tool never signs up for an account.",
        "",
        f"- targets: **{len(targets)}** — {n_disagree} uncorroborated "
        f"disagree (needs_review live) + {len(targets) - n_disagree} outvoted "
        f"(2-of-N ruled for us over a dissenting engine; sec-api spot-checks "
        f"the vote)",
        f"- adjudicable by sec-api (10-K items 1..15): **{len(adjudicable)}** "
        f"(items 1C/9C/16 are unsupported by sec-api — its capability gap, "
        f"documented, not ours)",
        f"- API calls still needed (uncached, one per filing+item): "
        f"**{len(uncached)}** of the {LIFETIME_QUOTA}-call lifetime budget",
        "",
        "Ready to run:",
        "",
        "```",
        f"SECAPI_KEY=<key> .venv/Scripts/python tools/arbitrate_secapi.py "
        f"--max-calls {len(uncached)}",
        "```",
        "",
        "| ticker | accession | item | tier | dissenting engines | adjudicable | status |",
        "|---|---|---|---|---|---|---|",
    ]
    for t in targets:
        key = f"{t['accession']}:{t['item']}"
        if results and key in results:
            status = results[key].get("status", "")
            ruling = results[key].get("ruling")
            status = f"{status}; ruling={ruling}" if ruling else status
        elif cache_path(cache_dir, t["accession"], t["item"]).is_file():
            status = "cached, unadjudicated"
        else:
            status = "pending (needs 1 call)" if t["supported"] else "not adjudicable"
        lines.append(f"| {t['ticker']} | {t['accession']} | {t['item']} | {t['tier']} | "
                     f"{', '.join(t['dissenting']) or '—'} | "
                     f"{'yes' if t['supported'] else 'no (sec-api lacks item)'} | {status} |")
    if results:
        lines += ["", f"Run outcome: {calls_made_this_run} new API call(s); "
                      f"verdicts in `arbitration.json` (word counts + rulings only, "
                      f"no sec-api payload text)."]
    return "\n".join(lines) + "\n"


# -- harness -----------------------------------------------------------------------

def _arg(flag: str, default: str) -> str:
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default


def main() -> None:  # pragma: no cover — network harness; pieces unit-tested
    triang_path = Path(_arg("--triangulation", str(TRIANGULATION)))
    out_dir = Path(_arg("--out", str(ARBITRATION_DIR)))
    max_calls = int(_arg("--max-calls", "0"))
    cache_dir = out_dir / "cache"
    out_dir.mkdir(parents=True, exist_ok=True)
    gitignore = out_dir / ".gitignore"
    if not gitignore.is_file():
        gitignore.write_text("cache/\n", encoding="utf-8")  # ToS: payloads stay local

    targets = load_targets(json.loads(triang_path.read_text(encoding="utf-8")))
    key = os.environ.get("SECAPI_KEY", "").strip()
    if not key:
        (out_dir / "README.md").write_text(render_readme(targets, cache_dir),
                                           encoding="utf-8")
        print(f"no SECAPI_KEY in env — wrote ready-to-run state doc for "
              f"{len(targets)} arbitration targets -> {out_dir / 'README.md'}")
        print("burning the 100-lifetime-call free tier is a user decision; "
              "re-run with SECAPI_KEY and --max-calls N to adjudicate.")
        return

    # adjudication run: rebuild every side's span from the SAME cached raw HTML
    from sec_core.engines import extract_items_datamule, extract_items_edgar_crawler
    from sec_core.fetcher import EdgarFetcher
    from sec_core.pipeline import extract_from_html
    from sec_core.third_engine import extract_items_edgartools

    engine_fns = {"edgartools": extract_items_edgartools,
                  "edgar_crawler": extract_items_edgar_crawler,
                  "datamule": extract_items_datamule}
    fetcher = EdgarFetcher(cache_dir=ROOT / "data" / "raw_filings")
    budget = {"calls_made": 0, "max_calls": max_calls}
    results: dict[str, dict] = {}
    by_doc: dict[str, list[dict]] = {}
    for t in targets:
        if t["supported"]:
            by_doc.setdefault(t["doc_url"] or "", []).append(t)
    for doc_url, doc_targets in by_doc.items():
        if not doc_url:
            for t in doc_targets:
                results[f"{t['accession']}:{t['item']}"] = {
                    "status": "no_doc_url (re-run tools/triangulate.py)"}
            continue
        raw = fetcher.get(doc_url).content.decode("utf-8", errors="replace")
        ours = extract_from_html(raw, f"arbitrate-{doc_targets[0]['accession']}")
        engine_cache: dict[str, dict[str, str]] = {}

        def _engine_items(name: str) -> dict[str, str]:
            if name not in engine_cache:
                engine_cache[name] = engine_fns[name](raw) or {}  # noqa: B023
            return engine_cache[name]

        for t in doc_targets:
            rkey = f"{t['accession']}:{t['item']}"
            text, status = get_secapi_text(t, key, cache_dir, budget)
            if text is None:
                results[rkey] = {"status": status}
                continue
            seg = ours.segment(t["item"])
            our_text = (ours.doc.slice(seg.start_offset, seg.end_offset)
                        if seg and seg.end_offset > seg.start_offset else "")
            # the "engine" side of the ruling = every DISSENTING engine's span
            engine_texts = {name: _engine_items(name).get(t["item"], "")
                            for name in (t["dissenting"] or ["edgartools"])}
            verdicts = adjudicate(t["item"], text, our_text, engine_texts)
            results[rkey] = {"status": status, "tier": t["tier"],
                             "secapi_words": len(text.split()),
                             "our_words": len(our_text.split()), **verdicts}
            print(f"{t['ticker']} item {t['item']} ({t['tier']}): {status}, "
                  f"ruling={verdicts['ruling']}")

    artifact = {
        "generated_by": "tools/arbitrate_secapi.py",
        "endpoint": ENDPOINT,
        "lifetime_quota": LIFETIME_QUOTA,
        "calls_made_this_run": budget["calls_made"],
        "targets": len(targets),
        "results": results,  # verdicts + word counts only; ToS: no payload text
    }
    (out_dir / "arbitration.json").write_text(json.dumps(artifact, indent=2),
                                              encoding="utf-8")
    (out_dir / "README.md").write_text(
        render_readme(targets, cache_dir, results, budget["calls_made"]),
        encoding="utf-8")
    rulings = [r.get("ruling") for r in results.values() if r.get("ruling")]
    print(f"\n{budget['calls_made']} API call(s) spent; rulings: "
          f"{ {r: rulings.count(r) for r in set(rulings)} or 'none'}")
    print(f"wrote {out_dir / 'arbitration.json'} and README.md")


if __name__ == "__main__":
    main()
