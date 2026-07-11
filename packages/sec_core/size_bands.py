"""Per-(form, schema, item) empirical size bands (P0-11).

The only length sanity the pipeline had was one global band (50..3,000,000
chars, boundary.py boundary_length_sanity) — it cannot notice an Item 1A that
is 40x too short or an Item 3 that swallowed the financial statements. This
module derives *empirical* per-item bands from entries where an independent
engine agreed with us AND our own verifier passed (agree-and-pass), and turns
them into a hard guardrail: an out-of-band substantive span is forced to
needs_review (never silently trusted).

Band rule (spec §2 P0-11): band = [p50/5, p50*8] around the agree-and-pass
median span length in chars; a band is only emitted when it has at least
MIN_SAMPLES supporting entries. Bands are keyed (form, schema, item) so the
pre-2003 item renumbering (14=Exhibits) can never pollute the modern 14=Fees
band.

Sample sources (both already on disk, no new labeling):
- data/sec_eval/records/sweep3/*.json (per-item span_chars, status) joined
  with data/sec_eval/triangulation/triangulation.json (per-item verdict);
- data/sec_eval/pseudo_gold/pseudo_gold_candidates.json 3-way-agree items
  (gitignored, used at build time only when present on disk).

Whole-filing invariant (SRAF): the Loughran-McDonald 10X Summaries CSV gives
an independent whole-document word count per accession. The sum of our
extracted item words must not exceed it by more than a tolerance — a cheap,
lineage-independent "did we hallucinate/duplicate content" reconciliation.
The CSV has no explicit license (SRAF requests citation) => three-tier rule
tier 2: fetch-on-demand only, never vendored or committed; when the CSV is
absent the build records skipped-with-reason instead of failing.

Enforcement (apply_size_bands, wired in pipeline.extract_from_html) only
gates substantive offset-exact pass items: boilerplate "None." answers,
combined spans, reference stubs and already-flagged items keep their existing
(honest) handling.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from statistics import median

from sec_core.confidence import (
    OVERSHOOT_COMPONENT_MAX,
    ConfidenceBreakdown,
    ConfidenceComponent,
)
from sec_core.items import ItemSegment
from sec_core.normalize import NormalizedDocument
from sec_core.refine import is_boilerplate_none

_ROOT = Path(__file__).resolve().parents[2]
BANDS_PATH = _ROOT / "data" / "sec_eval" / "size_bands" / "size_bands.json"

BAND_LO_DIVISOR = 5
BAND_HI_MULTIPLIER = 8
MIN_SAMPLES = 5
# Bands are learned from complete filings; enforcing them on excerpts or toy
# documents (adversarial fixtures, truncated inputs) is out-of-distribution —
# every band sample came from a filing normalizing to well above this floor
# (smallest sweep3/pseudo-gold source ≈ 60K chars).
MIN_DOC_CHARS = 50_000
# measured on the 14 SRAF-joined filings we can re-extract offline: max
# sum-of-items / N_Words ratio observed, plus headroom (see build artifact's
# sraf_invariant.filings for the per-accession numbers backing this).
SRAF_TOLERANCE = 1.25

_WORD_RE = re.compile(r"[A-Za-z]+")


@dataclass(frozen=True)
class SizeBand:
    form: str
    schema: str
    item_code: str
    n: int
    p50: int
    lo: int
    hi: int


def count_lm_words(text: str) -> int:
    """Alphabetic-token approximation of the LM Master Dictionary word count
    (SRAF N_Words counts dictionary tokens; numbers and markup never count)."""
    return len(_WORD_RE.findall(text))


def sraf_whole_filing_check(
    sum_item_words: int, sraf_n_words: int, tolerance: float = SRAF_TOLERANCE
) -> tuple[bool, float]:
    """Whole-filing upper-bound invariant: the words we extracted across all
    items cannot exceed an independent count of the words in the whole
    submission (main doc + exhibits) by more than `tolerance`. Returns
    (ok, ratio)."""
    if sraf_n_words <= 0:
        return True, 0.0  # no independent count => invariant not applicable
    ratio = sum_item_words / sraf_n_words
    return ratio <= tolerance, ratio


# --- load + enforce ----------------------------------------------------------

_cache: dict[Path, dict[tuple[str, str, str], SizeBand]] = {}


def load_size_bands(path: Path | None = None) -> dict[tuple[str, str, str], SizeBand]:
    """Load the derived-stats artifact. A missing artifact yields an empty
    mapping (the guardrail is inert, never a crash)."""
    p = path or BANDS_PATH
    if p in _cache:
        return _cache[p]
    bands: dict[tuple[str, str, str], SizeBand] = {}
    if p.exists():
        data = json.loads(p.read_text(encoding="utf-8"))
        for form, schemas in data.get("bands", {}).items():
            for schema, items in schemas.items():
                for code, b in items.items():
                    bands[(form, schema, code)] = SizeBand(
                        form=form, schema=schema, item_code=code,
                        n=b["n"], p50=b["p50"], lo=b["lo"], hi=b["hi"],
                    )
    _cache[p] = bands
    return bands


def check_size_band(
    span_chars: int,
    item_code: str,
    form: str = "10-K",
    schema: str = "MODERN",
    bands: dict[tuple[str, str, str], SizeBand] | None = None,
) -> SizeBand | None:
    """Return the violated band when span_chars falls outside the empirical
    band for (form, schema, item_code); None when in-band or no band exists."""
    if bands is None:
        bands = load_size_bands()
    band = bands.get((form, schema, item_code))
    if band is None:
        return None
    if band.lo <= span_chars <= band.hi:
        return None
    return band


OVERSHOOT_SIZE_COMPONENT = "overshoot_size_ratio"


def apply_size_bands(
    segments: list[ItemSegment],
    doc: NormalizedDocument,
    form: str = "10-K",
    schema: str = "MODERN",
    bands: dict[tuple[str, str, str], SizeBand] | None = None,
    breakdowns: dict[str, ConfidenceBreakdown] | None = None,
) -> int:
    """Hard guardrail: a substantive offset-exact pass item whose span length
    falls outside the empirical band is forced to needs_review. Boilerplate
    "None." answers, combined spans, stubs and non-pass items keep their
    existing handling (they are already flagged or legitimately short).
    A HIGH-side violation (span above the band's upper bound — the p95-proxy)
    is the boundary-bleed direction: when `breakdowns` is given it additionally
    caps confidence via a zero-scored `overshoot_size_ratio` component
    (total ≤ ~0.74) so calibration sees the overshoot, not just the flag.
    Returns the number of segments flagged."""
    if len(doc.text) < MIN_DOC_CHARS:
        return 0  # excerpt / toy document: bands would be out-of-distribution
    flagged = 0
    for seg in segments:
        if seg.status != "pass" or seg.provenance != "offset_exact_span":
            continue
        if seg.end_offset <= seg.start_offset:
            continue
        span_chars = seg.end_offset - seg.start_offset
        band = check_size_band(span_chars, seg.item_code, form, schema, bands)
        if band is None:
            continue
        text = doc.slice(seg.start_offset, seg.end_offset)
        nl = text.find("\n")
        body = text[nl + 1:].strip() if nl != -1 else ""
        if is_boilerplate_none(body):
            continue  # a complete short answer, not a boundary defect
        seg.needs_review = True
        seg.warnings.append(
            f"size-band guardrail: span {span_chars:,} chars is outside the empirical "
            f"agree-and-pass band [{band.lo:,}, {band.hi:,}] for item {seg.item_code} "
            f"({band.form}/{band.schema}, p50={band.p50:,}, n={band.n}) — hard needs_review"
        )
        if span_chars > band.hi:
            ratio = span_chars / band.p50
            seg.warnings.append(
                f"overshoot: size {ratio:.1f}x band median (p50 {band.p50:,} chars) — "
                f"the span tail likely swallows following content")
            bd = (breakdowns or {}).get(seg.item_code)
            if bd is not None:
                if not any(c.name == OVERSHOOT_SIZE_COMPONENT for c in bd.components):
                    bd.components.append(ConfidenceComponent(
                        name=OVERSHOOT_SIZE_COMPONENT, score=0.0,
                        max_score=OVERSHOOT_COMPONENT_MAX,
                        reason=f"span is {ratio:.1f}x the empirical band median for "
                               f"item {seg.item_code} (above the band upper bound "
                               f"{band.hi:,}) — boundary overshoot"))
                seg.confidence = bd.total
        flagged += 1
    return flagged


# --- build (derives data/sec_eval/size_bands/size_bands.json) ----------------

def collect_sweep_samples(sweep_dir: Path, triangulation_path: Path) -> list[dict]:
    """Agree-and-pass sweep entries: sweep status == pass, not needs_review,
    and the triangulation verdict for the same (ticker, item) is agree."""
    verdicts: dict[tuple[str, str], str] = {}
    tri = json.loads(triangulation_path.read_text(encoding="utf-8"))
    for rec in tri.get("records", []):
        for code, it in rec.get("items", {}).items():
            verdicts[(rec["ticker"], code)] = it.get("verdict", "")

    samples: list[dict] = []
    for f in sorted(sweep_dir.glob("*.json")):
        rec = json.loads(f.read_text(encoding="utf-8"))
        form = rec.get("form", "10-K")
        for code, it in rec.get("items", {}).items():
            if it.get("status") != "pass" or it.get("needs_review"):
                continue
            if verdicts.get((rec.get("ticker", ""), code)) != "agree":
                continue
            span = it.get("span_chars", it.get("end_offset", 0) - it.get("start_offset", 0))
            if span <= 0:
                continue
            samples.append({"form": form, "schema": "MODERN", "item": code,
                            "span_chars": span, "source": f"sweep3:{rec.get('ticker', f.stem)}"})
    return samples


def collect_pseudo_gold_samples(pseudo_gold_path: Path) -> list[dict]:
    """3-way-agree pseudo-gold items (P0-1 miner output; gitignored, build-time
    only). Their record carries the era schema, so pre-2003 items land in
    their own band group instead of polluting the modern one."""
    if not pseudo_gold_path.exists():
        return []
    data = json.loads(pseudo_gold_path.read_text(encoding="utf-8"))
    samples: list[dict] = []
    for rec in data.get("records", []):
        if rec.get("disposition") != "voted":
            continue
        form = rec.get("form", "10-K")
        schema = rec.get("schema", "MODERN")
        for code, it in rec.get("items", {}).items():
            if it.get("tier") != "pseudo_gold_3way" or it.get("our_status") != "pass":
                continue
            span = it.get("end_offset", 0) - it.get("start_offset", 0)
            if span <= 0:
                continue
            samples.append({"form": form, "schema": schema, "item": code,
                            "span_chars": span, "source": f"pseudo_gold:{rec.get('cik')}"})
    return samples


def build_bands(samples: list[dict]) -> dict:
    """p50/BAND_LO_DIVISOR .. p50*BAND_HI_MULTIPLIER per (form, schema, item);
    a band needs MIN_SAMPLES supporting entries or it is not emitted."""
    groups: dict[tuple[str, str, str], list[int]] = {}
    for s in samples:
        groups.setdefault((s["form"], s["schema"], s["item"]), []).append(s["span_chars"])
    bands: dict = {}
    for (form, schema, code), spans in sorted(groups.items()):
        if len(spans) < MIN_SAMPLES:
            continue
        p50 = int(median(spans))
        bands.setdefault(form, {}).setdefault(schema, {})[code] = {
            "n": len(spans),
            "p50": p50,
            "lo": max(1, p50 // BAND_LO_DIVISOR),
            "hi": p50 * BAND_HI_MULTIPLIER,
            "min_seen": min(spans),
            "max_seen": max(spans),
        }
    return bands


def in_band_fraction(samples: list[dict], bands: dict) -> float:
    """Specificity floor for the guardrail: the fraction of the build samples
    the derived bands themselves accept (they should nearly all be in-band —
    a band that rejects its own agree-and-pass evidence is miscalibrated)."""
    checked = hits = 0
    for s in samples:
        b = bands.get(s["form"], {}).get(s["schema"], {}).get(s["item"])
        if b is None:
            continue
        checked += 1
        if b["lo"] <= s["span_chars"] <= b["hi"]:
            hits += 1
    return hits / checked if checked else 1.0


def _sraf_join(sraf_csv: Path, accessions: dict[str, dict]) -> dict:
    """Stream the (never-committed) LM 10X Summaries CSV once and measure the
    whole-filing invariant for every accession we can re-extract offline."""
    import csv

    from sec_core.fetcher import EdgarFetcher
    from sec_core.pipeline import extract_from_html

    sraf_rows: dict[str, int] = {}
    with sraf_csv.open(newline="", encoding="utf-8", errors="replace") as fh:
        for row in csv.DictReader(fh):
            if row["ACC_NUM"] in accessions:
                sraf_rows[row["ACC_NUM"]] = int(row["N_Words"])

    fetcher = EdgarFetcher(cache_dir=_ROOT / "data" / "raw_filings",
                           user_agent="wealth-research p76091014@gs.ncku.edu.tw")
    filings, violations = [], 0
    for acc, meta in sorted(accessions.items()):
        n_words = sraf_rows.get(acc)
        if n_words is None:
            continue
        blob, _ = fetcher._cache_paths(meta["doc_url"])
        if not blob.exists():
            filings.append({"accession": acc, "label": meta["label"],
                            "sraf_n_words": n_words, "skipped": "raw filing not in offline cache"})
            continue
        raw = fetcher.get(meta["doc_url"]).content.decode("utf-8", errors="replace")
        result = extract_from_html(raw, filing_id=acc)
        spans = {(s.start_offset, s.end_offset) for s in result.segments
                 if s.end_offset > s.start_offset}
        total = sum(count_lm_words(result.doc.slice(a, b)) for a, b in spans)
        ok, ratio = sraf_whole_filing_check(total, n_words)
        if not ok:
            violations += 1
        filings.append({"accession": acc, "label": meta["label"],
                        "sum_item_words": total, "sraf_n_words": n_words,
                        "ratio": round(ratio, 4), "ok": ok})
    measured = [f for f in filings if "ratio" in f]
    return {
        "status": "measured",
        "source": "Loughran-McDonald 10X Summaries (SRAF, Notre Dame). No explicit license; "
                  "SRAF requests citation => three-tier rule tier 2: fetch-on-demand only, "
                  "CSV never vendored/committed (see docs/ATTRIBUTION.md norms).",
        "invariant": "sum of extracted item words (unique spans, alphabetic-token count) "
                     f"<= SRAF whole-submission N_Words * {SRAF_TOLERANCE}",
        "tolerance": SRAF_TOLERANCE,
        "joined": len(sraf_rows),
        "measured": len(measured),
        "violations": violations,
        "max_ratio": max((f["ratio"] for f in measured), default=0.0),
        "filings": filings,
    }


def measure_runtime_specificity(triangulation_path: Path) -> dict:
    """False-alarm rate of the shipped guardrail on the clean (unmutated)
    sweep corpus: run the live pipeline on every offline-cached sweep filing
    and count size-band flags among clean pass items. This is the specificity
    number the P0-4 harness gate (<= 0.05) reads."""
    from sec_core.fetcher import EdgarFetcher
    from sec_core.pipeline import extract_from_html

    fetcher = EdgarFetcher(cache_dir=_ROOT / "data" / "raw_filings",
                           user_agent="wealth-research p76091014@gs.ncku.edu.tw")
    tri = json.loads(triangulation_path.read_text(encoding="utf-8"))
    filings = clean_pass = 0
    flags: list[dict] = []
    for rec in tri.get("records", []):
        blob, _ = fetcher._cache_paths(rec["doc_url"])
        if not blob.exists():
            continue
        raw = fetcher.get(rec["doc_url"]).content.decode("utf-8", errors="replace")
        result = extract_from_html(raw, filing_id=rec["ticker"])  # pipeline applies bands
        filings += 1
        for s in result.segments:
            if s.status == "pass" and s.provenance == "offset_exact_span":
                clean_pass += 1
            if any("size-band guardrail" in w for w in s.warnings):
                flags.append({"ticker": rec["ticker"], "item": s.item_code,
                              "span_chars": s.end_offset - s.start_offset})
    return {
        "filings_measured": filings,
        "clean_pass_items": clean_pass,
        "flagged": len(flags),
        "false_alarm_rate": round(len(flags) / clean_pass, 4) if clean_pass else 0.0,
        "flags": flags,
    }


def build_artifact(
    sweep_dir: Path | None = None,
    triangulation_path: Path | None = None,
    pseudo_gold_path: Path | None = None,
    sraf_csv: Path | None = None,
    out_path: Path | None = None,
) -> dict:
    import time

    sweep_dir = sweep_dir or _ROOT / "data" / "sec_eval" / "records" / "sweep3"
    triangulation_path = triangulation_path or _ROOT / "data" / "sec_eval" / "triangulation" / "triangulation.json"
    pseudo_gold_path = pseudo_gold_path or _ROOT / "data" / "sec_eval" / "pseudo_gold" / "pseudo_gold_candidates.json"
    out_path = out_path or BANDS_PATH

    sweep_samples = collect_sweep_samples(sweep_dir, triangulation_path)
    pg_samples = collect_pseudo_gold_samples(pseudo_gold_path)
    samples = sweep_samples + pg_samples
    bands = build_bands(samples)

    # SRAF whole-filing invariant: accession -> re-extractable doc URL
    accessions: dict[str, dict] = {}
    tri = json.loads(triangulation_path.read_text(encoding="utf-8"))
    for rec in tri.get("records", []):
        accessions[rec["accession"]] = {"doc_url": rec["doc_url"], "label": rec["ticker"]}
    if pseudo_gold_path.exists():
        for rec in json.loads(pseudo_gold_path.read_text(encoding="utf-8")).get("records", []):
            if rec.get("disposition") != "voted":
                continue
            acc_nodash = rec["accession"].replace("-", "")
            url = (f"https://www.sec.gov/Archives/edgar/data/{rec['cik']}/"
                   f"{acc_nodash}/{rec['main_document']}")
            accessions[rec["accession"]] = {"doc_url": url, "label": f"cik{rec['cik']}"}

    if sraf_csv is not None and sraf_csv.exists():
        sraf = _sraf_join(sraf_csv, accessions)
    else:
        sraf = {
            "status": "skipped",
            "reason": "LM 10X Summaries CSV not present locally (fetch-on-demand only — "
                      "no explicit license, SRAF requests citation => tier 2, never committed); "
                      "pass --sraf-csv <path> after downloading from "
                      "https://sraf.nd.edu/sec-edgar-data/lm_10x_summaries/ to measure.",
        }

    artifact = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "spec": "P0-11: per-(form,schema,item) empirical size bands from agree-and-pass "
                "entries; band = [p50/5, p50*8]; out-of-band substantive pass item => "
                "hard needs_review (sec_core/size_bands.py)",
        "band_rule": {"lo": f"p50/{BAND_LO_DIVISOR}", "hi": f"p50*{BAND_HI_MULTIPLIER}",
                      "min_samples": MIN_SAMPLES},
        "sources": {
            "sweep": f"{sweep_dir.as_posix().split('data/')[-1]} x triangulation agree "
                     f"({len(sweep_samples)} samples)",
            "pseudo_gold": f"pseudo_gold_3way pass items ({len(pg_samples)} samples; "
                           "gitignored input, derived stats only)",
        },
        "samples_total": len(samples),
        "in_band_fraction": round(in_band_fraction(samples, bands), 4),
        "bands": bands,
        "sraf_invariant": sraf,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(artifact, indent=1) + "\n", encoding="utf-8")
    _cache.pop(out_path, None)

    # measured AFTER the artifact lands so the live pipeline path (which loads
    # it) is what gets measured — the number the P0-4 specificity gate reads.
    if out_path == BANDS_PATH:
        artifact["runtime_specificity"] = measure_runtime_specificity(triangulation_path)
        out_path.write_text(json.dumps(artifact, indent=1) + "\n", encoding="utf-8")
        _cache.pop(out_path, None)
    return artifact


if __name__ == "__main__":  # pragma: no cover - thin CLI
    import argparse

    ap = argparse.ArgumentParser(description="Derive per-(form,schema,item) size bands (P0-11)")
    ap.add_argument("--sraf-csv", type=Path, default=None,
                    help="local LM 10X Summaries CSV (fetch-on-demand; never committed)")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    art = build_artifact(sraf_csv=args.sraf_csv, out_path=args.out)
    print(json.dumps({k: art[k] for k in ("samples_total", "in_band_fraction")}, indent=1))
    print(json.dumps(art["sraf_invariant"], indent=1)[:1200])
