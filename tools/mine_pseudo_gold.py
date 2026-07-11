"""P0-1 multi-teacher pseudo-gold miner — EDGAR-CORPUS join (giants_task2.md §2.1).

Expands the golden set beyond the 5 self-frozen filings by 3-way voting:
  ours        — this repo's pipeline (offset-exact spans)
  edgartools  — independent third engine (lineage: independent; pinned 5.42.0)
  corpus      — EDGAR-CORPUS weak labels (HF eloukas/edgar-corpus, Apache-2.0;
                lineage: edgar-crawler — machine-generated, NEVER gold on its own)

Sampling is corpus-driven (guardrail g6): we stream the first K records per
era-stratified year from the corpus `test` split, reverse-look-up the accession
from (CIK, year) via the SEC submissions API, then run our pipeline and
edgartools on the SAME primary document. Corpus composition is exactly
10-K ∪ 10-K405 ∪ 10-KT — never the KSB family, never /A amendments (build
config pinned at edgar-crawler commit 058a121a41).

Form-type → item-schema mapping (§2.1, applied on BOTH the join side and any
direct-extraction side):
  * form normalization is a FULL enumeration — `startswith("10-K")` misses the
    KSB family (`10KSB`, no hyphen) and `== "10-K"` misses every variant;
  * era schema by period-of-report (Release 33-8183: FYE >= 2003-12-15 puts
    Accountant Fees at 14, Exhibits at 15), double-checked in boundary years
    against the filing's own Item 14 heading (Exhibit -> PRE2003, Fees -> MODERN);
  * PRE2003: corpus section_14 means canonical 15 (Exhibits) and an empty
    section_15 is NO-SIGNAL, never an accountant-fees teacher vote (g2);
  * 10-KSB items shift (6=MD&A ...): ksb_to_canonical maps them; canonical
    6/7A are NOT_APPLICABLE for KSB, and a KSB filing degrades the vote to
    2-way because the corpus never holds KSB (g4);
  * 2016–2020 corpus section_15 tails carry Item 16 pollution (its extractor
    runs the last item to EOF) — cut at "Item 16" before comparing (g3).

Vote semantics:
  * corpus comparisons use compare_item(source="corpus") — the corpus was built
    with remove_tables=True, so only containment of the table-stripped corpus
    text in OUR span counts (a length-ratio vote would systematically flag
    Item 8); a corpus section LONGER than our span means we truncated;
  * lineage discount: corpus carries edgar-crawler lineage; if an edgar-crawler
    engine vote is ever added (P0-7a), corpus+crawler agreement counts as ONE
    independent confirmation, not two;
  * edgartools engine_suspect (P0-5 blind class, items 10-16 TOC junk) is
    no-signal from the engine, not a strike against our span;
  * pre-2001 layers where an engine cannot parse degrade honestly to 2-way;
  * /A never enters pseudo-gold (Rule 12b-15 partial restatements, g5) and is
    NOT rare (~17-25% of 10-K volume, g7) — amendments route to the hard-case
    queue, as do join collisions and any teacher disagreement.

Outputs (data/ artifacts are never committed):
  data/sec_eval/pseudo_gold/pseudo_gold_candidates.json  — freezable candidates
  data/sec_eval/pseudo_gold/hard_case_queue.json         — human-review queue

Usage:
  .venv/Scripts/python tools/mine_pseudo_gold.py [--per-year N] [--years Y1,Y2,..]
Requires SEC_EDGAR_USER_AGENT. Bounded to <= 30 filings per run.
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages"))

from sec_core.fetcher import EdgarFetcher  # noqa: E402
from sec_core.main_doc import pick_main_document  # noqa: E402
from sec_core.pipeline import extract_from_html  # noqa: E402
from sec_core.resolver import FilingResolver  # noqa: E402
from sec_core.third_engine import compare_item, extract_items_edgartools  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "sec_eval" / "pseudo_gold"
CACHE_DIR = OUT_DIR / "corpus_cache"
HF_BASE = "https://huggingface.co/datasets/eloukas/edgar-corpus/resolve/main"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
MAX_FILINGS = 30

# era-stratified default years (corpus spans 1993-2020): two pre-2001 text-era,
# 2003 straddles the Release 33-8183 schema boundary, 2016-2020 covers the g3
# Item-16 pollution window.
DEFAULT_YEARS = [1996, 1999, 2003, 2006, 2012, 2016, 2018, 2020]


# --- §2.1-1 form normalization (full enumeration; see module doc) -------------
_FORM_FAMILY = {
    "10-K": "10K", "10-K405": "10K",
    "10-KT": "10KT", "10KT405": "10KT", "10-KT405": "10KT",
    "10KSB": "10KSB", "10-KSB": "10KSB", "10KSB40": "10KSB",
}
CORPUS_FAMILIES = {"10K", "10KT"}  # corpus = 10-K ∪ 10-K405 ∪ 10-KT, never KSB


def normalize_form(form: str) -> tuple[str, bool]:
    """(family, is_amendment). family in {10K, 10KT, 10KSB, other}."""
    f = (form or "").strip().upper()
    is_amendment = f.endswith("/A")
    base = f[:-2] if is_amendment else f
    return _FORM_FAMILY.get(base, "other"), is_amendment


# --- §2.1-2 era schema ---------------------------------------------------------
def era_schema(report_date: str, item14_heading: str = "") -> str:
    """PRE2003 | MODERN. The filing's own Item 14 heading is the double-check
    and wins in boundary years: Exhibits -> PRE2003, Accountant Fees -> MODERN.
    Otherwise Release 33-8183: FYE >= 2003-12-15 -> MODERN."""
    h = (item14_heading or "").lower()
    if "exhibit" in h:
        return "PRE2003"
    if "accountant" in h or "fees" in h:
        return "MODERN"
    return "MODERN" if (report_date or "") >= "2003-12-15" else "PRE2003"


# --- §2.1-3 canonical mapping --------------------------------------------------
_SECTION_KEY_RE = re.compile(r"^section_(\d{1,2}[A-C]?)$", re.IGNORECASE)

# 10-KSB item -> canonical 10-K item (6=MD&A onward shifted; canonical 6 and 7A
# are NOT_APPLICABLE for KSB — they simply never appear as mapping targets).
KSB_TO_CANONICAL = {
    "1": "1", "2": "2", "3": "3", "4": "4", "5": "5",
    "6": "7", "7": "8", "8": "9", "8A": "9A", "8B": "9B",
    "9": "10", "10": "11", "11": "12", "12": "13", "13": "15",
}


def ksb_to_canonical(code: str) -> str | None:
    return KSB_TO_CANONICAL.get((code or "").strip().upper())


def corpus_section_to_canonical(key: str, schema: str) -> str | None:
    """Map a corpus column (section_1 .. section_15) to a canonical item code.
    None = no teacher signal for that column under the schema (guardrail g2)."""
    m = _SECTION_KEY_RE.match(key or "")
    if not m:
        return None
    code = m.group(1).upper()
    if schema == "PRE2003":
        if code == "14":
            return "15"  # pre-2003 'Item 14' IS Exhibits = canonical 15 (g2)
        if code in {"15", "1A", "1B", "9A", "9B"}:
            return None  # not in the pre-2003 schema: no-signal, never disagreement
        return code
    return code


# --- g3: 2016-2020 corpus section_15 tail pollution ---------------------------
_ITEM16_CUT_RE = re.compile(r"\bitem\s*16\b", re.IGNORECASE)


def strip_item16_tail(text: str, year: int, key: str) -> str:
    if (key or "").lower() == "section_15" and 2016 <= year <= 2020:
        m = _ITEM16_CUT_RE.search(text)
        if m:
            return text[:m.start()]
    return text


# --- g1/g5/g6 join: corpus (CIK, year) -> accession ----------------------------
def pick_join(rows: list[dict], year: int) -> dict:
    """Join one corpus record against submissions rows.

    rows: [{form, accession, filing_date, report_date, primary_document}, ...]
    Corpus 'year' is ambiguous between report/filing year, so try report-year
    first, then filing-year. Collisions resolve by g1 (drop /A + KSB first);
    a surviving collision is 'ambiguous'; only-/A years are 'amendment_only'
    (g5: Rule 12b-15 partial restatements never enter pseudo-gold).
    """
    fam_rows = []
    for r in rows:
        family, is_a = normalize_form(r.get("form", ""))
        if family in CORPUS_FAMILIES:
            fam_rows.append({**r, "family": family, "is_amendment": is_a})
    for basis in ("report_date", "filing_date"):
        hits = [r for r in fam_rows if (r.get(basis) or "").startswith(str(year))]
        if not hits:
            continue
        originals = [r for r in hits if not r["is_amendment"]]  # g1
        if len(originals) == 1:
            return {"outcome": "matched", "row": originals[0], "join_basis": basis,
                    "amendments_seen": len(hits) - len(originals)}
        if len(originals) > 1:
            return {"outcome": "ambiguous", "join_basis": basis,
                    "candidates": [r["accession"] for r in originals]}
        return {"outcome": "amendment_only", "join_basis": basis,
                "candidates": [r["accession"] for r in hits]}
    return {"outcome": "not_found"}


# --- vote tiers ----------------------------------------------------------------
def classify_vote(corpus_verdict: str, engine_verdict: str | None) -> str:
    """Tier of a per-item 3-way vote. The corpus vote is required (it is what
    this miner joins on); the engine vote upgrades 2-way -> 3-way. engine_suspect
    (P0-5) and engine_unavailable are no-signal, not disagreement."""
    if corpus_verdict == "disagree":
        return "hard_case"
    if corpus_verdict != "agree":
        return "no_corpus_signal"
    if engine_verdict == "agree":
        return "pseudo_gold_3way"
    if engine_verdict == "disagree":
        return "hard_case"  # teachers split: human adjudication
    return "pseudo_gold_2way_corpus_only"  # single weak teacher (crawler lineage)


# --- corpus streaming (bounded; cache-first; never committed) -------------------
def stream_corpus_records(year: int, k: int, user_agent: str) -> list[dict]:
    """First k records of {year}/test.jsonl, streamed with early stop so only a
    few MB transfer. Cached per record under corpus_cache/ for offline re-runs."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached = sorted(CACHE_DIR.glob(f"{year}_*.json"))
    if len(cached) >= k:
        return [json.loads(p.read_text(encoding="utf-8")) for p in cached[:k]]
    url = f"{HF_BASE}/{year}/test.jsonl"
    req = urllib.request.Request(url, headers={"User-Agent": user_agent or "research"})
    records: list[dict] = []
    buf = b""
    with urllib.request.urlopen(req, timeout=180) as resp:
        while len(records) < k:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf and len(records) < k:
                line, buf = buf.split(b"\n", 1)
                if line.strip():
                    records.append(json.loads(line))
    for i, rec in enumerate(records):
        p = CACHE_DIR / f"{year}_{i:02d}_{rec.get('cik', '0')}.json"
        p.write_text(json.dumps(rec), encoding="utf-8")
    return records


def _submission_rows(fetcher: EdgarFetcher, cik: int) -> list[dict]:
    """ALL filings (every form — resolver._collect_10k keeps only 10-K/10-K/A,
    which would hide 10-K405/10-KT from the join) from recent + paged blocks."""
    data = json.loads(fetcher.get(SUBMISSIONS_URL.format(cik=cik)).content)
    blocks = [data.get("filings", {}).get("recent", {})]
    for page in data.get("filings", {}).get("files", []):
        name = page.get("name")
        if not name:
            continue
        try:
            blocks.append(json.loads(fetcher.get(
                f"https://data.sec.gov/submissions/{name}").content))
        except Exception:  # noqa: BLE001 — one bad page must not drop the rest
            continue
    rows: list[dict] = []
    for block in blocks:
        forms = block.get("form", [])
        n = len(forms)
        for i, form in enumerate(forms):
            rows.append({
                "form": form,
                "accession": block.get("accessionNumber", [""] * n)[i],
                "filing_date": block.get("filingDate", [""] * n)[i],
                "report_date": block.get("reportDate", [""] * n)[i],
                "primary_document": block.get("primaryDocument", [""] * n)[i],
            })
    return rows


def _year_era(year: int) -> str:
    if year <= 2000:
        return "text_pre2001"
    if year <= 2008:
        return "html_2001_2008"
    if year <= 2018:
        return "xbrl_2009_2018"
    return "ixbrl_2019plus"


def _segment_or_none(result, code: str):
    return next((s for s in result.segments if s.item_code == code), None)


def _fetch_raw(fetcher: EdgarFetcher, resolver: FilingResolver, cik: int,
               accession: str) -> tuple[str, str]:
    """(raw_text, main_document_name); old filings fall back to the full
    submission .txt when no usable named document exists."""
    ref = resolver.resolve_accession(cik, accession)
    ref.cik = cik
    try:
        best = pick_main_document(ref)
        raw = fetcher.get(ref.file_url(best.name)).content.decode("utf-8", errors="replace")
        if len(raw) >= 4000:
            return raw, best.name
    except LookupError:
        pass
    name = f"{accession}.txt"
    raw = fetcher.get(
        f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}.txt"
    ).content.decode("latin-1")
    return raw, name


def mine_one(fetcher: EdgarFetcher, resolver: FilingResolver, corpus_rec: dict,
             year: int) -> dict:
    cik = int(corpus_rec.get("cik", "0"))
    rows = _submission_rows(fetcher, cik)
    join = pick_join(rows, year)
    base = {"cik": cik, "corpus_filename": corpus_rec.get("filename", ""),
            "corpus_year": year, "era": _year_era(year), "join": join}
    if join["outcome"] != "matched":
        return {**base, "disposition": f"hard_case:join_{join['outcome']}"}

    row = join["row"]
    accession = row["accession"]
    raw, main_name = _fetch_raw(fetcher, resolver, cik, accession)
    result = extract_from_html(raw, f"cik{cik}-{accession}")
    seg14 = _segment_or_none(result, "14")
    schema = era_schema(row.get("report_date", ""),
                        seg14.extracted_heading if seg14 else "")
    base.update({"accession": accession, "form": row["form"],
                 "report_date": row.get("report_date", ""),
                 "main_document": main_name, "schema": schema,
                 "filing_class": result.filing_class})

    if result.filing_class == "non_10k" or len(result.segments) < 5:
        return {**base, "disposition": "hard_case:our_side_unsupported",
                "detail": f"filing_class={result.filing_class}, "
                          f"segments={len(result.segments)} — no offsets to freeze; "
                          f"honest degradation, not silently skipped"}

    engine_items = extract_items_edgartools(raw)
    items: dict[str, dict] = {}
    for key, text in corpus_rec.items():
        if not _SECTION_KEY_RE.match(key) or not (text or "").strip():
            continue
        code = corpus_section_to_canonical(key, schema)
        if code is None:
            continue  # g2: no-signal column under this schema
        corpus_text = strip_item16_tail(text, year, key)
        seg = _segment_or_none(result, code)
        our_text = (result.doc.slice(seg.start_offset, seg.end_offset)
                    if seg and seg.end_offset > seg.start_offset else "")
        our_status = seg.status if seg else "missing"
        corpus_cmp = compare_item(code, our_text, corpus_text, our_status, source="corpus")
        engine_cmp = (compare_item(code, our_text, engine_items.get(code, ""), our_status)
                      if engine_items is not None else None)
        tier = classify_vote(corpus_cmp.verdict, engine_cmp.verdict if engine_cmp else None)
        entry: dict = {
            "corpus_key": key,
            "tier": tier,
            "our_status": our_status,
            "teachers": {
                "corpus": {"verdict": corpus_cmp.verdict, "lineage": "edgar-crawler",
                           "detail": corpus_cmp.detail, "overlap": round(corpus_cmp.overlap, 3)},
            },
        }
        if engine_cmp is not None:
            entry["teachers"]["edgartools"] = {
                "verdict": engine_cmp.verdict, "lineage": "independent",
                "detail": engine_cmp.detail}
        if tier.startswith("pseudo_gold") and seg and seg.end_offset > seg.start_offset:
            entry.update({"start_offset": seg.start_offset, "end_offset": seg.end_offset,
                          "text_sha256": seg.text_sha256})
        items[code] = entry
    return {**base, "disposition": "voted",
            "engine_parsed": engine_items is not None, "items": items}


def main() -> None:
    years = DEFAULT_YEARS
    per_year = 3
    args = sys.argv[1:]
    if "--years" in args:
        years = [int(y) for y in args[args.index("--years") + 1].split(",")]
    if "--per-year" in args:
        per_year = int(args[args.index("--per-year") + 1])
    if len(years) * per_year > MAX_FILINGS:
        per_year = max(1, MAX_FILINGS // len(years))
        print(f"capped to {per_year}/year — corpus runs stay <= {MAX_FILINGS} filings")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fetcher = EdgarFetcher(cache_dir=ROOT / "data" / "raw_filings")
    resolver = FilingResolver(fetcher)

    filings: list[dict] = []
    hard_cases: list[dict] = []
    for year in years:
        try:
            records = stream_corpus_records(year, per_year, fetcher.user_agent)
        except Exception as e:  # noqa: BLE001 — one year must not sink the run
            print(f"[{year}] corpus stream ERROR {type(e).__name__}: {e}")
            continue
        for rec in records:
            try:
                out = mine_one(fetcher, resolver, rec, year)
            except Exception as e:  # noqa: BLE001
                out = {"cik": rec.get("cik"), "corpus_year": year,
                       "era": _year_era(year),
                       "disposition": f"hard_case:error_{type(e).__name__}",
                       "detail": str(e)}
            filings.append(out)
            if out["disposition"] != "voted":
                hard_cases.append(out)
            else:
                for code, entry in out["items"].items():
                    if entry["tier"] == "hard_case":
                        hard_cases.append({
                            "cik": out["cik"], "accession": out.get("accession"),
                            "corpus_year": year, "era": out["era"], "item": code,
                            "teachers": entry["teachers"],
                            "our_status": entry["our_status"]})
            tiers = {}
            for entry in out.get("items", {}).values():
                tiers[entry["tier"]] = tiers.get(entry["tier"], 0) + 1
            print(f"[{year}] cik={out.get('cik')} {out.get('accession', '-')} "
                  f"{out['disposition']} {tiers or ''}")

    tier_totals: dict[str, int] = {}
    for f in filings:
        for entry in f.get("items", {}).values():
            tier_totals[entry["tier"]] = tier_totals.get(entry["tier"], 0) + 1
    summary = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "spec": "docs/research/giants_task2.md §2.1 (P0-1)",
        "corpus": "HF eloukas/edgar-corpus (Apache-2.0), lineage edgar-crawler "
                  "(weak labels, never gold alone); composition 10-K∪10-K405∪10-KT, "
                  "no /A, no KSB; remove_tables=True -> compare_item(source='corpus')",
        "lineage_discount": "corpus shares edgar-crawler lineage; corpus + any "
                            "future edgar-crawler engine vote count as ONE "
                            "independent confirmation",
        "years": years, "per_year": per_year,
        "filings": len(filings),
        "dispositions": {d: sum(1 for f in filings if f["disposition"] == d)
                         for d in sorted({f["disposition"] for f in filings})},
        "item_tier_totals": tier_totals,
        "records": filings,
    }
    (OUT_DIR / "pseudo_gold_candidates.json").write_text(
        json.dumps(summary, indent=1), encoding="utf-8")
    (OUT_DIR / "hard_case_queue.json").write_text(json.dumps({
        "generated_at": summary["generated_at"],
        "note": "g5 amendments, join collisions, our-side unsupported eras and "
                "teacher splits — human adjudication queue; NEVER auto-frozen",
        "cases": hard_cases}, indent=1), encoding="utf-8")
    print(f"\nfilings={len(filings)} dispositions={summary['dispositions']}")
    print(f"item tiers={tier_totals}")
    print(f"wrote {OUT_DIR / 'pseudo_gold_candidates.json'}")
    print(f"wrote {OUT_DIR / 'hard_case_queue.json'} ({len(hard_cases)} cases)")


if __name__ == "__main__":
    main()
