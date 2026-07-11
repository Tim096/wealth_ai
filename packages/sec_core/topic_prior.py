"""Gold-free span content-attribution prior (giants_task2 residual: the
length/position axis bottomed out at AUROC 0.66 — the remaining un-intercepted
pass errors are CONTENT misplacement, not size anomalies).

Two separately switched sub-signals (attribution runs flip them
independently; master kill-switch SEC_TOPIC_PRIOR=0 in pipeline.py):

  (a) misattribution margin  (SEC_TOPIC_PRIOR_MARGIN=0 to disable)
      Per-item lexicons are derived from corpus-only span texts (sweep3
      triangulation-agree pass spans + pseudo-gold 3-way-agree spans — the
      same gold-free sample rule as length_prior.py). A substantive pass
      span whose body covers ANOTHER item's distinctive vocabulary decisively
      better than its own is content-misattribution suspect. The flag
      threshold is the p99 of the (best_other - own) coverage margin observed
      on the build samples themselves — corpus-derived, no NTU labels.
      (A third candidate, an own-coverage "off-topic floor", was measured on
      the held-out fold and killed: 18 of its 20 fires hit correct items —
      dead key, not shipped; see giants_task2.md.)
  (b) pointer stub trust cap (SEC_TOPIC_PRIOR_IBR=0 to disable)
      An incorporated_by_reference stub carries pointer text only — the
      item's actual content was never extracted, so the CONTENT of the item
      is structurally unverifiable by every downstream oracle (topic, XBRL,
      triangulation all look at the stub, not the referenced body). Status
      trust is capped and the stub is routed to review. Structural rule from
      the extraction itself; no tuned parameters.

Gold-free by construction (P0-3 rule: NTU human labels are held-out
measurement only, never parameters). Enforcement mirrors length_prior.py:
needs_review + a zero-scored 3.5-weight confidence component; the span
offsets are NEVER changed, so macro-F1 is untouched.
"""

from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path

from sec_core.confidence import (
    OVERSHOOT_COMPONENT_MAX,
    ConfidenceBreakdown,
    ConfidenceComponent,
)
from sec_core.items import ItemSegment
from sec_core.length_prior import percentile
from sec_core.normalize import NormalizedDocument
from sec_core.refine import is_boilerplate_none

_ROOT = Path(__file__).resolve().parents[2]
LEXICON_PATH = _ROOT / "data" / "sec_eval" / "calibration" / "topic_lexicon.json"

# --- build parameters (corpus statistics, not NTU-tuned) ----------------------
MIN_SAMPLES = 5        # per-item lexicon needs this many corpus spans
TOP_K = 40             # distinctive tokens kept per item
MIN_ITEM_DF_FRAC = 0.4  # token must appear in >= this fraction of the item's spans
GENERIC_DF_FRAC = 0.5  # token in >= this fraction of ALL spans is corpus-generic
MIN_BUILD_BODY_CHARS = 400  # stubs/boilerplate are not the item's content
MARGIN_Q = 0.99        # flag threshold = p99 of build-sample margins

# --- runtime guards ------------------------------------------------------------
MIN_DOC_CHARS = 20_000  # lexicons come from complete filings; toy docs are OOD
MIN_SPAN_TOKENS = 50    # too few distinct tokens -> coverage is unstable

MISATTRIBUTION_COMPONENT = "topic_prior_misattribution"
POINTER_COMPONENT = "pointer_content_unverified"

_TOKEN_RE = re.compile(r"[a-z]{3,}")


def tokenize(text: str) -> set[str]:
    """Presence set of lowercase alphabetic tokens (>= 3 chars)."""
    return set(_TOKEN_RE.findall(text.lower()))


@dataclass(frozen=True)
class TopicPriors:
    lexicon: dict[str, dict[str, float]]   # item -> token -> weight
    margin_tau: float                       # flag when best_other - own > tau


def coverage(tokens: set[str], lex: dict[str, float]) -> float:
    """Weighted fraction of an item's distinctive vocabulary present."""
    total = sum(lex.values())
    if total <= 0:
        return 0.0
    return sum(w for t, w in lex.items() if t in tokens) / total


def attribution(tokens: set[str], priors: TopicPriors,
                own_code: str) -> tuple[float, str | None, float]:
    """(own_coverage, best_other_item, best_other_coverage)."""
    own = coverage(tokens, priors.lexicon[own_code])
    best_code, best_cov = None, 0.0
    for code, lex in priors.lexicon.items():
        if code == own_code:
            continue
        c = coverage(tokens, lex)
        if c > best_cov:
            best_code, best_cov = code, c
    return own, best_code, best_cov


# --- load + enforce ------------------------------------------------------------

_cache: dict[Path, TopicPriors | None] = {}


def load_topic_priors(path: Path | None = None) -> TopicPriors | None:
    """Load the derived lexicon artifact. Missing artifact -> None (the
    signal is inert, never a crash)."""
    p = path or LEXICON_PATH
    if p in _cache:
        return _cache[p]
    priors: TopicPriors | None = None
    if p.exists():
        data = json.loads(p.read_text(encoding="utf-8"))
        priors = TopicPriors(
            lexicon={code: dict(lex) for code, lex in data.get("lexicon", {}).items()},
            margin_tau=float(data.get("thresholds", {}).get("margin_tau", 1.0)),
        )
    _cache[p] = priors
    return priors


def _cap(seg: ItemSegment, breakdowns: dict[str, ConfidenceBreakdown] | None,
         component: str, reason: str) -> None:
    seg.needs_review = True
    bd = (breakdowns or {}).get(seg.item_code)
    if bd is not None:
        if not any(c.name == component for c in bd.components):
            bd.components.append(ConfidenceComponent(
                name=component, score=0.0,
                max_score=OVERSHOOT_COMPONENT_MAX, reason=reason))
        seg.confidence = bd.total


def apply_topic_prior(
    segments: list[ItemSegment],
    doc: NormalizedDocument,
    priors: TopicPriors | None = None,
    breakdowns: dict[str, ConfidenceBreakdown] | None = None,
) -> int:
    """Flag content-attribution suspects: needs_review + a zero-scored heavy
    confidence component (same enforcement shape as apply_length_prior).
    Never changes offsets. Returns the number of segments flagged."""
    margin_on = os.environ.get("SEC_TOPIC_PRIOR_MARGIN") != "0"
    ibr_on = os.environ.get("SEC_TOPIC_PRIOR_IBR") != "0"

    flagged = 0

    # (b) pointer stub trust cap — structural, needs no lexicon and no
    # document-scale guard. Already-flagged pointers (cross_reference_pointer
    # provenance etc.) are left alone: they carry the review flag.
    if ibr_on:
        for seg in segments:
            if seg.status != "incorporated_by_reference" or seg.needs_review:
                continue
            _cap(seg, breakdowns, POINTER_COMPONENT,
                 "incorporated-by-reference stub: the span is pointer text only — "
                 "the item's actual content was never extracted, so no content "
                 "oracle (topic/XBRL/triangulation) can verify it")
            seg.warnings.append(
                "pointer-content guardrail: item is an incorporated-by-reference "
                "stub; content-level trust is capped and the pointer routed to "
                "review — the referenced body is outside this filing's span")
            flagged += 1

    if not margin_on:
        return flagged
    if len(doc.text) < MIN_DOC_CHARS:
        return flagged  # excerpt / toy document: lexicon stats are OOD
    if priors is None:
        priors = load_topic_priors()
    if priors is None or len(priors.lexicon) < 3:
        return flagged

    for seg in segments:
        if seg.status != "pass" or seg.provenance != "offset_exact_span":
            continue
        if seg.item_code not in priors.lexicon:
            continue
        if seg.end_offset <= seg.start_offset:
            continue
        text = doc.slice(seg.start_offset, seg.end_offset)
        nl = text.find("\n")
        body = text[nl + 1:].strip() if nl != -1 else ""
        if is_boilerplate_none(body) or len(body) < MIN_BUILD_BODY_CHARS:
            continue  # short/boilerplate answers carry no stable topic signal
        tokens = tokenize(body)
        if len(tokens) < MIN_SPAN_TOKENS:
            continue
        own, best_code, best_cov = attribution(tokens, priors, seg.item_code)

        if best_code is not None and best_cov - own > priors.margin_tau:
            _cap(seg, breakdowns, MISATTRIBUTION_COMPONENT,
                 f"span covers item {best_code}'s distinctive vocabulary "
                 f"({best_cov:.2f}) decisively better than its own item "
                 f"{seg.item_code}'s ({own:.2f}); margin {best_cov - own:.2f} > "
                 f"corpus p99 {priors.margin_tau:.2f}")
            seg.warnings.append(
                f"topic-attribution guardrail (misattribution): body reads like "
                f"item {best_code} (coverage {best_cov:.2f}) more than like item "
                f"{seg.item_code} (coverage {own:.2f}); margin exceeds the "
                f"corpus-derived p99 ({priors.margin_tau:.2f}) — content may "
                f"belong to another item; needs_review")
            flagged += 1

    return flagged


# --- build (derives data/sec_eval/calibration/topic_lexicon.json) --------------

def _span_body(doc_text: str, start: int, end: int) -> str:
    text = doc_text[start:end]
    nl = text.find("\n")
    return text[nl + 1:].strip() if nl != -1 else ""


def collect_sweep_spans(sweep_dir: Path, triangulation_path: Path) -> list[dict]:
    """Agree-and-pass sweep3 spans as (item, body-token-set) samples. Span
    text comes from re-normalizing the cached raw filing (corpus-only)."""
    from sec_core.fetcher import EdgarFetcher
    from sec_core.normalize import normalize_html
    from sec_core.resolver import FilingResolver

    import sys
    sys.path.insert(0, str(_ROOT / "tools"))
    from mine_pseudo_gold import _fetch_raw

    verdicts: dict[tuple[str, str], str] = {}
    tri = json.loads(triangulation_path.read_text(encoding="utf-8"))
    for rec in tri.get("records", []):
        for code, it in rec.get("items", {}).items():
            verdicts[(rec["ticker"], code)] = it.get("verdict", "")

    fetcher = EdgarFetcher(cache_dir=_ROOT / "data" / "raw_filings")
    resolver = FilingResolver(fetcher)
    samples: list[dict] = []
    for f in sorted(sweep_dir.glob("*.json")):
        rec = json.loads(f.read_text(encoding="utf-8"))
        try:
            raw, _ = _fetch_raw(fetcher, resolver, int(rec["cik"]), rec["accession"])
        except Exception as e:  # noqa: BLE001 — one filing must not sink the build
            print(f"  sweep3 SKIP {rec.get('ticker', f.stem)}: {type(e).__name__}: {e}")
            continue
        doc_text = normalize_html(raw).text
        for code, it in rec.get("items", {}).items():
            if it.get("status") != "pass" or it.get("needs_review"):
                continue
            if verdicts.get((rec.get("ticker", ""), code)) != "agree":
                continue
            body = _span_body(doc_text, it.get("start_offset", 0), it.get("end_offset", 0))
            if len(body) < MIN_BUILD_BODY_CHARS or is_boilerplate_none(body):
                continue
            samples.append({"item": code, "tokens": tokenize(body),
                            "source": f"sweep3:{rec.get('ticker', f.stem)}"})
    return samples


def collect_pseudo_gold_spans(pseudo_gold_path: Path) -> list[dict]:
    """3-way-agree pseudo-gold spans as (item, body-token-set) samples."""
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
        except Exception as e:  # noqa: BLE001
            print(f"  pseudo-gold SKIP cik={rec['cik']}: {type(e).__name__}: {e}")
            continue
        doc_text = normalize_html(raw).text
        for code, it in rec.get("items", {}).items():
            if it.get("tier") != "pseudo_gold_3way" or it.get("our_status") != "pass":
                continue
            body = _span_body(doc_text, it.get("start_offset", 0), it.get("end_offset", 0))
            if len(body) < MIN_BUILD_BODY_CHARS or is_boilerplate_none(body):
                continue
            samples.append({"item": code, "tokens": tokenize(body),
                            "source": f"pseudo_gold:{rec.get('cik')}"})
    return samples


def build_lexicon(samples: list[dict]) -> dict[str, dict[str, float]]:
    """Per-item TOP_K distinctive tokens by smoothed log-odds vs all other
    items' spans; corpus-generic tokens (>= GENERIC_DF_FRAC of ALL spans) are
    excluded so the lexicon is discriminative, not SEC boilerplate."""
    n_all = len(samples)
    df_all: dict[str, int] = {}
    by_item: dict[str, list[set[str]]] = {}
    for s in samples:
        by_item.setdefault(s["item"], []).append(s["tokens"])
        for t in s["tokens"]:
            df_all[t] = df_all.get(t, 0) + 1

    generic = {t for t, df in df_all.items() if df / n_all >= GENERIC_DF_FRAC}

    lexicon: dict[str, dict[str, float]] = {}
    for code, spans in sorted(by_item.items()):
        n_i = len(spans)
        if n_i < MIN_SAMPLES:
            continue
        df_i: dict[str, int] = {}
        for tokens in spans:
            for t in tokens:
                df_i[t] = df_i.get(t, 0) + 1
        n_o = n_all - n_i
        scored: list[tuple[float, str]] = []
        for t, df in df_i.items():
            if t in generic or df / n_i < MIN_ITEM_DF_FRAC:
                continue
            df_o = df_all[t] - df
            w = (math.log((df + 0.5) / (n_i + 1.0))
                 - math.log((df_o + 0.5) / (n_o + 1.0)))
            if w > 0:
                scored.append((w, t))
        scored.sort(reverse=True)
        if scored[:TOP_K]:
            lexicon[code] = {t: round(w, 4) for w, t in scored[:TOP_K]}
    return lexicon


def build_thresholds(samples: list[dict],
                     lexicon: dict[str, dict[str, float]]) -> tuple[float, list[dict]]:
    """Corpus-derived flag threshold: margin_tau = p99 of the
    (best_other - own) coverage margins over build samples (in-sample —
    disclosed in the artifact). The per-sample coverage rows are kept in the
    artifact for auditability."""
    priors = TopicPriors(lexicon=lexicon, margin_tau=1.0)
    margins: list[float] = []
    rows: list[dict] = []
    for s in samples:
        if s["item"] not in lexicon:
            continue
        own, best_code, best_cov = attribution(s["tokens"], priors, s["item"])
        margins.append(best_cov - own)
        rows.append({"item": s["item"], "source": s["source"], "own": round(own, 4),
                     "tokens": len(s["tokens"]),
                     "best_other": best_code, "best_other_cov": round(best_cov, 4)})
    tau = max(percentile(margins, MARGIN_Q), 0.0) if margins else 1.0
    return round(tau, 4), rows


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
    out_path = out_path or LEXICON_PATH

    sweep_samples = collect_sweep_spans(sweep_dir, triangulation_path)
    pg_samples = collect_pseudo_gold_spans(pseudo_gold_path)
    samples = sweep_samples + pg_samples
    lexicon = build_lexicon(samples)
    tau, rows = build_thresholds(samples, lexicon)

    per_item_n = {}
    for s in samples:
        per_item_n[s["item"]] = per_item_n.get(s["item"], 0) + 1

    artifact = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "spec": "gold-free per-item content-attribution lexicon; misattribution "
                "margin + IBR pointer trust cap "
                "(sec_core/topic_prior.py; kill-switch SEC_TOPIC_PRIOR=0, "
                "sub-switches SEC_TOPIC_PRIOR_{MARGIN,IBR}=0)",
        "gold_free": "samples: sweep3 x triangulation-agree + pseudo-gold 3way "
                     "span texts from cached raw filings; NTU human labels are "
                     "never an input (held-out measurement only). Thresholds are "
                     "in-sample corpus quantiles (disclosed: optimistic on the "
                     "build corpus itself).",
        "rule": {"min_samples": MIN_SAMPLES, "top_k": TOP_K,
                 "min_item_df_frac": MIN_ITEM_DF_FRAC,
                 "generic_df_frac": GENERIC_DF_FRAC,
                 "min_build_body_chars": MIN_BUILD_BODY_CHARS,
                 "margin_rule": f"p{int(MARGIN_Q * 100)} of build-sample margins",
                 "min_doc_chars": MIN_DOC_CHARS,
                 "min_span_tokens": MIN_SPAN_TOKENS},
        "sources": {"sweep": f"{len(sweep_samples)} spans",
                    "pseudo_gold": f"{len(pg_samples)} spans"},
        "samples_total": len(samples),
        "samples_per_item": dict(sorted(per_item_n.items())),
        "thresholds": {"margin_tau": tau},
        "build_coverage_rows": rows,
        "lexicon": lexicon,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(artifact, indent=1) + "\n", encoding="utf-8")
    _cache.pop(out_path, None)
    return artifact


if __name__ == "__main__":  # pragma: no cover - thin CLI
    import argparse

    ap = argparse.ArgumentParser(
        description="Derive the gold-free per-item content-attribution lexicon")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    art = build_artifact(out_path=args.out)
    print(json.dumps({"samples_total": art["samples_total"],
                      "samples_per_item": art["samples_per_item"],
                      "thresholds": art["thresholds"],
                      "items_with_lexicon": sorted(art["lexicon"])}, indent=1))
