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
