"""Gold-free per-item length-ratio prior (giants_task2 residual fix).

The size-band guardrail (P0-11) compares ABSOLUTE span chars against bands
learned from mega-cap sweep filings — it misfires on the external NTU fold
where whole filings are 10-40x smaller. This prior is scale-invariant: the
signal is the span's share of the WHOLE filing (span_chars / normalized doc
chars), whose per-item distribution is far more stable across eras.

Gold-free by construction (P0-3 rule: NTU human labels are held-out
measurement only, never parameters):
  - samples come from corpus-only sources — sweep3 records where the
    triangulation corpus teacher agreed AND our verifier passed clean, plus
    pseudo-gold 3-way-agree items (offsets over the normalized cached raw
    filing);
  - thresholds are the empirical p05/p95 of those ratio samples, keyed
    (form, schema, item) exactly like size_bands.

Enforcement (apply_length_prior, wired in pipeline.extract_from_html after
apply_size_bands; kill-switch SEC_LENGTH_PRIOR=0):
  - ratio > p95  -> boundary-bleed direction (span swallows following
    content): needs_review + zero-scored 'length_prior_overshoot' component;
  - ratio < p05  -> fragment direction (span far too small a share of the
    filing to be the real item body): needs_review + zero-scored
    'length_prior_undershoot' component.
Only substantive offset-exact pass spans are gated; boilerplate "None."
answers, combined spans, stubs and non-pass items keep their handling.
The span itself is NEVER changed — macro-F1 is untouched by this signal.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from sec_core.confidence import (
    OVERSHOOT_COMPONENT_MAX,
    ConfidenceBreakdown,
    ConfidenceComponent,
)
from sec_core.items import ItemSegment
from sec_core.normalize import NormalizedDocument
from sec_core.refine import is_boilerplate_none

_ROOT = Path(__file__).resolve().parents[2]
PRIOR_PATH = _ROOT / "data" / "sec_eval" / "calibration" / "length_prior.json"

P_LO = 0.05
P_HI = 0.95
MIN_SAMPLES = 5
# Ratios are scale-invariant, but they were learned from COMPLETE filings;
# a toy/excerpt document (test fixtures, adversarial mutants) is
# out-of-distribution for "share of the whole filing".
MIN_DOC_CHARS = 20_000

OVERSHOOT_PRIOR_COMPONENT = "length_prior_overshoot"
UNDERSHOOT_PRIOR_COMPONENT = "length_prior_undershoot"


def percentile(values: list[float], q: float) -> float:
    """Linear-interpolated quantile (numpy 'linear' method), q in [0, 1]."""
    if not values:
        raise ValueError("percentile of empty list")
    vals = sorted(values)
    idx = q * (len(vals) - 1)
    lo = int(idx)
    hi = min(lo + 1, len(vals) - 1)
    frac = idx - lo
    return vals[lo] * (1 - frac) + vals[hi] * frac


@dataclass(frozen=True)
class LengthPrior:
    form: str
    schema: str
    item_code: str
    n: int
    p05: float
    p50: float
    p95: float


# --- load + enforce ----------------------------------------------------------

_cache: dict[Path, dict[tuple[str, str, str], LengthPrior]] = {}


def load_length_priors(path: Path | None = None) -> dict[tuple[str, str, str], LengthPrior]:
    """Load the derived prior artifact. Missing artifact -> empty mapping
    (the signal is inert, never a crash)."""
    p = path or PRIOR_PATH
    if p in _cache:
        return _cache[p]
    priors: dict[tuple[str, str, str], LengthPrior] = {}
    if p.exists():
        data = json.loads(p.read_text(encoding="utf-8"))
        for form, schemas in data.get("priors", {}).items():
            for schema, items in schemas.items():
                for code, b in items.items():
                    priors[(form, schema, code)] = LengthPrior(
                        form=form, schema=schema, item_code=code,
                        n=b["n"], p05=b["p05"], p50=b["p50"], p95=b["p95"],
                    )
    _cache[p] = priors
    return priors


def apply_length_prior(
    segments: list[ItemSegment],
    doc: NormalizedDocument,
    form: str = "10-K",
    schema: str = "MODERN",
    priors: dict[tuple[str, str, str], LengthPrior] | None = None,
    breakdowns: dict[str, ConfidenceBreakdown] | None = None,
) -> int:
    """Flag substantive offset-exact pass spans whose share of the whole
    filing falls outside the corpus-derived per-item [p05, p95] ratio band:
    needs_review + a zero-scored heavy confidence component (total <= ~0.74).
    Never changes offsets. Returns the number of segments flagged."""
    doc_chars = len(doc.text)
    if doc_chars < MIN_DOC_CHARS:
        return 0  # excerpt / toy document: "share of the filing" is undefined
    if priors is None:
        priors = load_length_priors()
    if not priors:
        return 0
    flagged = 0
    for seg in segments:
        if seg.status != "pass" or seg.provenance != "offset_exact_span":
            continue
        if seg.end_offset <= seg.start_offset:
            continue
        prior = priors.get((form, schema, seg.item_code))
        if prior is None:
            continue
        ratio = (seg.end_offset - seg.start_offset) / doc_chars
        if prior.p05 <= ratio <= prior.p95:
            continue
        text = doc.slice(seg.start_offset, seg.end_offset)
        nl = text.find("\n")
        body = text[nl + 1:].strip() if nl != -1 else ""
        if is_boilerplate_none(body):
            continue  # a complete short answer, not a boundary defect
        if ratio > prior.p95:
            component, direction, detail = (
                OVERSHOOT_PRIOR_COMPONENT, "overshoot",
                "the span tail likely swallows following content")
        else:
            component, direction, detail = (
                UNDERSHOOT_PRIOR_COMPONENT, "undershoot",
                "the span is likely a fragment of the real item body")
        seg.needs_review = True
        seg.warnings.append(
            f"length-prior guardrail ({direction}): span is {ratio:.4f} of the whole "
            f"filing, outside the corpus-derived [{prior.p05:.4f}, {prior.p95:.4f}] "
            f"band for item {seg.item_code} ({prior.form}/{prior.schema}, "
            f"p50={prior.p50:.4f}, n={prior.n}) — {detail}; needs_review"
        )
        bd = (breakdowns or {}).get(seg.item_code)
        if bd is not None:
            if not any(c.name == component for c in bd.components):
                bd.components.append(ConfidenceComponent(
                    name=component, score=0.0,
                    max_score=OVERSHOOT_COMPONENT_MAX,
                    reason=f"whole-filing share {ratio:.4f} outside the gold-free "
                           f"per-item prior band [{prior.p05:.4f}, {prior.p95:.4f}] "
                           f"— {direction}"))
            seg.confidence = bd.total
        flagged += 1
    return flagged


# --- build (derives data/sec_eval/calibration/length_prior.json) -------------

def collect_sweep_ratios(sweep_dir: Path, triangulation_path: Path) -> list[dict]:
    """Agree-and-pass sweep entries as whole-filing ratios: sweep status pass,
    not needs_review, triangulation verdict agree; ratio = span_chars /
    normalized_chars (both already in the sweep record — corpus-only)."""
    verdicts: dict[tuple[str, str], str] = {}
    tri = json.loads(triangulation_path.read_text(encoding="utf-8"))
    for rec in tri.get("records", []):
        for code, it in rec.get("items", {}).items():
            verdicts[(rec["ticker"], code)] = it.get("verdict", "")

    samples: list[dict] = []
    for f in sorted(sweep_dir.glob("*.json")):
        rec = json.loads(f.read_text(encoding="utf-8"))
        doc_chars = rec.get("normalized_chars", 0)
        if doc_chars <= 0:
            continue
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
                            "ratio": span / doc_chars,
                            "source": f"sweep3:{rec.get('ticker', f.stem)}"})
    return samples


def collect_pseudo_gold_ratios(pseudo_gold_path: Path) -> list[dict]:
    """3-way-agree pseudo-gold items as whole-filing ratios. The record only
    carries offsets, so the cached raw filing is normalized (offline,
    cache-first) to obtain the whole-filing denominator."""
    if not pseudo_gold_path.exists():
        return []
    from sec_core.fetcher import EdgarFetcher
    from sec_core.normalize import normalize_html
    from sec_core.resolver import FilingResolver

    import sys
    sys.path.insert(0, str(_ROOT / "tools"))
    from mine_pseudo_gold import _fetch_raw

    fetcher = EdgarFetcher(cache_dir=_ROOT / "data" / "raw_filings")
    resolver = FilingResolver(fetcher)
    data = json.loads(pseudo_gold_path.read_text(encoding="utf-8"))
    samples: list[dict] = []
    for rec in data.get("records", []):
        if rec.get("disposition") != "voted":
            continue
        try:
            raw, _ = _fetch_raw(fetcher, resolver, rec["cik"], rec["accession"])
        except Exception as e:  # noqa: BLE001 — one filing must not sink the build
            print(f"  pseudo-gold SKIP cik={rec['cik']}: {type(e).__name__}: {e}")
            continue
        doc_chars = len(normalize_html(raw).text)
        if doc_chars <= 0:
            continue
        for code, it in rec.get("items", {}).items():
            if it.get("tier") != "pseudo_gold_3way" or it.get("our_status") != "pass":
                continue
            span = it.get("end_offset", 0) - it.get("start_offset", 0)
            if span <= 0:
                continue
            samples.append({"form": rec.get("form", "10-K"),
                            "schema": rec.get("schema", "MODERN"), "item": code,
                            "ratio": span / doc_chars,
                            "source": f"pseudo_gold:{rec.get('cik')}"})
    return samples


def build_priors(samples: list[dict]) -> dict:
    """p05/p50/p95 of the whole-filing ratio per (form, schema, item); a prior
    needs MIN_SAMPLES supporting entries or it is not emitted."""
    groups: dict[tuple[str, str, str], list[float]] = {}
    for s in samples:
        groups.setdefault((s["form"], s["schema"], s["item"]), []).append(s["ratio"])
    priors: dict = {}
    for (form, schema, code), ratios in sorted(groups.items()):
        if len(ratios) < MIN_SAMPLES:
            continue
        priors.setdefault(form, {}).setdefault(schema, {})[code] = {
            "n": len(ratios),
            "p05": percentile(ratios, P_LO),
            "p50": percentile(ratios, 0.50),
            "p95": percentile(ratios, P_HI),
            "min_seen": min(ratios),
            "max_seen": max(ratios),
        }
    return priors


def in_band_fraction(samples: list[dict], priors: dict) -> float:
    """Fraction of the build samples inside their own [p05, p95] band —
    by quantile construction this sits near 0.90, which is also the expected
    clean-corpus flag ceiling for items that have a prior."""
    checked = hits = 0
    for s in samples:
        b = priors.get(s["form"], {}).get(s["schema"], {}).get(s["item"])
        if b is None:
            continue
        checked += 1
        if b["p05"] <= s["ratio"] <= b["p95"]:
            hits += 1
    return hits / checked if checked else 1.0


def build_artifact(
    sweep_dir: Path | None = None,
    triangulation_path: Path | None = None,
    pseudo_gold_path: Path | None = None,
    out_path: Path | None = None,
) -> dict:
    import time

    sweep_dir = sweep_dir or _ROOT / "data" / "sec_eval" / "records" / "sweep3"
    triangulation_path = (triangulation_path
                          or _ROOT / "data" / "sec_eval" / "triangulation" / "triangulation.json")
    pseudo_gold_path = (pseudo_gold_path
                        or _ROOT / "data" / "sec_eval" / "pseudo_gold" / "pseudo_gold_candidates.json")
    out_path = out_path or PRIOR_PATH

    sweep_samples = collect_sweep_ratios(sweep_dir, triangulation_path)
    pg_samples = collect_pseudo_gold_ratios(pseudo_gold_path)
    samples = sweep_samples + pg_samples
    priors = build_priors(samples)

    artifact = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "spec": "gold-free per-item whole-filing length-ratio prior; band = "
                "[p05, p95] of corpus-only agree-and-pass ratio samples; "
                "out-of-band substantive pass span => needs_review + confidence "
                "cap (sec_core/length_prior.py; kill-switch SEC_LENGTH_PRIOR=0)",
        "gold_free": "samples: sweep3 x triangulation-agree + pseudo-gold 3way; "
                     "NTU human labels are never an input (held-out measurement only)",
        "rule": {"lo": f"p{int(P_LO * 100):02d}", "hi": f"p{int(P_HI * 100):02d}",
                 "min_samples": MIN_SAMPLES, "min_doc_chars": MIN_DOC_CHARS},
        "sources": {
            "sweep": f"{len(sweep_samples)} samples",
            "pseudo_gold": f"{len(pg_samples)} samples (gitignored input, derived stats only)",
        },
        "samples_total": len(samples),
        "in_band_fraction": round(in_band_fraction(samples, priors), 4),
        "priors": priors,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(artifact, indent=1) + "\n", encoding="utf-8")
    _cache.pop(out_path, None)
    return artifact


if __name__ == "__main__":  # pragma: no cover - thin CLI
    import argparse

    ap = argparse.ArgumentParser(
        description="Derive the gold-free per-item length-ratio prior")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    art = build_artifact(out_path=args.out)
    print(json.dumps({k: art[k] for k in ("samples_total", "in_band_fraction", "sources")},
                     indent=1))
