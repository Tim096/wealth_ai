"""XBRL cross-validation — an INDEPENDENT oracle for status trustworthiness.

The manager's question is "how do you ensure `status` is trustworthy?" The
answer is not an LLM judging the pipeline's own output — it is an external,
structured ground truth. SEC already publishes every filing's financial facts
as machine-readable XBRL via the companyfacts API. So we can certify the most
consequential item, Item 8 (Financial Statements), against SEC's own numbers:

  a real Item 8 span must contain the reported Revenue / Net income / Total
  assets (at some scale). If it doesn't, the span is a wrapper stub or a
  boundary error — the oracle contradicts a `pass`, independently of the
  pipeline. This is deterministic, free, reproducible, and not an LLM guess.

This module fetches the facts and checks presence; it never lets XBRL
manufacture item text.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field

from sec_core.fetcher import EdgarFetcher

COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"

# concepts we look for, in priority order (us-gaap taxonomy)
_KEY_CONCEPTS = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "SalesRevenueNet",
    ],
    "net_income": ["NetIncomeLoss", "ProfitLoss"],
    "total_assets": ["Assets"],
}


@dataclass
class XbrlCheck:
    available: bool                       # were XBRL facts fetched for this filing?
    facts: dict[str, int] = field(default_factory=dict)  # metric -> value
    corroborated: dict[str, bool] = field(default_factory=dict)  # metric -> present in span?
    verdict: str = "inconclusive"         # certified | contradicted | inconclusive | unavailable
    detail: str = ""
    identity_notes: list[str] = field(default_factory=list)  # additive identity-drift findings


def fetch_company_facts(fetcher: EdgarFetcher, cik: int) -> dict:
    return json.loads(fetcher.get(COMPANYFACTS_URL.format(cik=cik)).content)


def key_facts_for_accession(facts: dict, accession: str) -> dict[str, int]:
    """Pull the headline numbers this specific 10-K reported (matched by accession)."""
    dashed = accession if "-" in accession else f"{accession[:10]}-{accession[10:12]}-{accession[12:]}"
    usgaap = facts.get("facts", {}).get("us-gaap", {})
    out: dict[str, int] = {}
    for metric, concepts in _KEY_CONCEPTS.items():
        for concept in concepts:
            units = usgaap.get(concept, {}).get("units", {}).get("USD", [])
            hits = [u for u in units if u.get("accn") == dashed and u.get("form", "").startswith("10-K")]
            # prefer the full-year / largest-magnitude figure reported in this filing
            if hits:
                out[metric] = max(hits, key=lambda u: abs(u.get("val", 0))).get("val", 0)
                break
    return out


# ---------------------------------------------------------------------------
# Fact identity — accession alone is not enough. A single 10-K's companyfacts
# carries several contexts for the same concept: the current fiscal year AND
# the comparative prior year(s), full-year durations AND quarterly ones, and
# (across unit keys) other currencies. "largest |value|" can lock onto the
# wrong one — a prior-year Assets balance, a foreign-currency figure — which is
# exactly the JPM/XOM headline drift the reviewer flagged. The functions below
# pin the *identity* of the headline fact: current period, USD, and the right
# duration/instant kind. This is an ADDITIVE layer; key_facts_for_accession and
# the main verdict are unchanged so the committed certification stays byte-stable.
# ---------------------------------------------------------------------------

# a duration concept reports a span (start+end); an instant concept a point (end only)
_CONCEPT_KIND = {"revenue": "duration", "net_income": "duration", "total_assets": "instant"}


@dataclass
class FactIdentity:
    metric: str
    value: int
    kind: str                 # duration | instant
    unit: str = "USD"
    fy: int | None = None
    fp: str = ""
    start: str = ""
    end: str = ""


def _dashed(accession: str) -> str:
    return accession if "-" in accession else f"{accession[:10]}-{accession[10:12]}-{accession[12:]}"


def _fact_kind(fact: dict) -> str:
    return "duration" if fact.get("start") else "instant"


def _duration_days(fact: dict) -> int:
    start, end = fact.get("start"), fact.get("end")
    if not start or not end:
        return 0
    try:
        return (dt.date.fromisoformat(end) - dt.date.fromisoformat(start)).days
    except ValueError:
        return 0


def _usd_candidates(facts: dict, metric: str, accession: str) -> list[dict]:
    """Every USD fact for this metric filed under THIS accession as a 10-K,
    restricted to the concept's temporal kind (duration vs instant). Only the
    USD unit key is read, so a EUR/GBP context can never enter selection."""
    dashed = _dashed(accession)
    want_kind = _CONCEPT_KIND[metric]
    usgaap = facts.get("facts", {}).get("us-gaap", {})
    out: list[dict] = []
    for concept in _KEY_CONCEPTS[metric]:
        units = usgaap.get(concept, {}).get("units", {}).get("USD", [])
        cands = [u for u in units
                 if u.get("accn") == dashed
                 and u.get("form", "").startswith("10-K")
                 and _fact_kind(u) == want_kind]
        if cands:
            out = cands
            break
    return out


def select_current_period_facts(facts: dict, accession: str) -> dict[str, FactIdentity]:
    """Identity-aware fact selection: for each metric lock onto the
    current-period, USD, correct-kind fact — NOT merely the largest value.

    Among the USD candidates of the right kind we take the latest period end
    (drops comparative prior-year contexts), then the longest duration among
    ties (drops a quarter that ends on the fiscal year-end), then the largest
    |value| as a final deterministic tiebreak for duplicate/restated contexts.
    """
    out: dict[str, FactIdentity] = {}
    for metric in _KEY_CONCEPTS:
        cands = _usd_candidates(facts, metric, accession)
        if not cands:
            continue
        best = max(cands, key=lambda u: (u.get("end", ""), _duration_days(u), abs(u.get("val", 0))))
        out[metric] = FactIdentity(
            metric=metric, value=best.get("val", 0), kind=_CONCEPT_KIND[metric],
            fy=best.get("fy"), fp=best.get("fp", ""),
            start=best.get("start", ""), end=best.get("end", ""))
    return out


def identity_mismatch(span_text: str, facts: dict, accession: str) -> list[str]:
    """Evidence-based drift detector for the ADDITIVE layer. For each metric it
    fires ONLY when the current-period identity value is absent from the span
    yet some *other* same-accession candidate value (a prior-year comparative,
    a quarter, a restatement) IS present — i.e. the span corroborated the wrong
    context. A genuine Item 8 prints the current-period figure, so a certified
    real filing never trips this; it targets silent context substitution."""
    hits: list[str] = []
    ident = select_current_period_facts(facts, accession)
    for metric, fid in ident.items():
        current_here = any(s in span_text for s in _scale_strings(fid.value))
        if current_here:
            continue
        decoys = {u.get("val", 0) for u in _usd_candidates(facts, metric, accession)
                  if u.get("val", 0) != fid.value}
        decoy_here = next((d for d in decoys if any(s in span_text for s in _scale_strings(d))), None)
        if decoy_here is not None:
            hits.append(
                f"{metric}: span shows a non-current-period value ({decoy_here:,}) but not the "
                f"current-period XBRL fact ({fid.value:,}, fy={fid.fp}{fid.fy}, end={fid.end})")
    return hits


def _scale_strings(value: int) -> list[str]:
    """A filing prints numbers in ones, thousands, or millions with separators."""
    out: set[str] = set()
    v = abs(value)
    for div in (1, 1_000, 1_000_000):
        scaled = round(v / div)
        if scaled >= 10:  # avoid matching tiny incidental numbers
            out.add(f"{scaled:,}")
    return list(out)


def validate_span(span_text: str, key_facts: dict[str, int]) -> XbrlCheck:
    if not key_facts:
        return XbrlCheck(available=False, verdict="unavailable",
                         detail="no XBRL headline facts found for this accession")
    corroborated: dict[str, bool] = {}
    for metric, value in key_facts.items():
        corroborated[metric] = any(s in span_text for s in _scale_strings(value))
    n_true = sum(corroborated.values())
    if n_true >= 2:
        verdict = "certified"
        detail = f"{n_true}/{len(key_facts)} XBRL headline figures found in the span"
    elif n_true == 0:
        verdict = "contradicted"
        detail = ("none of the XBRL headline figures appear in the span — the financial "
                  "statements are not here (wrapper stub or boundary error)")
    else:
        verdict = "inconclusive"
        detail = f"only {n_true}/{len(key_facts)} XBRL figures found — partial"
    return XbrlCheck(available=True, facts=key_facts, corroborated=corroborated,
                     verdict=verdict, detail=detail)


def certify_item8(result, fetcher, cik: int, accession: str) -> XbrlCheck:
    """Run the oracle against a live ExtractionResult and WRITE the verdict back
    onto the Item 8 segment (segment.xbrl_check). If the segment is `pass` but
    the oracle contradicts it, flip it to needs_review with a warning.

    Gating happens wherever this is called: tools/eval_one.py runs it so the
    committed eval records carry the gated status; tools/certify.py runs it for
    the certification artifact. The core extract_from_html stays network-free
    and deterministic by design — certification is a separate, opt-in pass so
    the offline parser has no hidden network dependency.
    """
    facts_json = fetch_company_facts(fetcher, cik)
    facts = key_facts_for_accession(facts_json, accession)
    seg = next(s for s in result.segments if s.item_code == "8")
    span = result.text_of("8")
    chk = validate_span(span, facts)
    seg.xbrl_check = f"{chk.verdict}: {chk.detail}"
    # ADDITIVE identity layer: the main verdict above is unchanged (byte-stable
    # against the committed certification). This only downgrades on hard evidence
    # that the span corroborated a WRONG-context value (prior-year / quarter /
    # restatement) instead of the current-period fact — never on a heuristic.
    chk.identity_notes = identity_mismatch(span, facts_json, accession)
    if chk.identity_notes and seg.status in ("pass", "partial"):
        seg.needs_review = True
        seg.warnings.append(
            "XBRL identity check: the Item 8 span matches a non-current-period figure but not the "
            "current-period fact — possible comparative/period drift. " + "; ".join(chk.identity_notes))
    if chk.verdict == "contradicted" and seg.status in ("pass", "partial"):
        # An Item 8 span that contains NONE of the XBRL headline figures is not
        # the financial statements — whether we called it a pass or a resolved
        # partial. Demote to unsupported rather than serve a wrong/truncated body
        # as content (a cross-reference partial on a polluted page map lands here).
        seg.status = "unsupported"
        seg.needs_review = True
        seg.warnings.append(
            "XBRL oracle contradicts this Item 8: none of the reported revenue/net income/assets "
            "appear in the extracted span — the financial statements are not here (boundary error "
            "or polluted page map). Demoted to unsupported."
        )
    return chk
