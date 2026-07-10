"""Per-item topic-consistency oracle — trustworthy status for EVERY item.

XBRL certifies Item 8 against structured facts. But the manager's question is
broader: how do you trust the status of ALL items? This adds a second,
independent, deterministic signal for every item — does the extracted span
actually read like the item's canonical topic? A span labelled "Item 1A. Risk
Factors" that contains no risk-factor language is suspect regardless of what
the heading detector said. Lexical, no LLM, cheap, and it catches
mislabels/boundary errors the structural pipeline alone would miss.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# distinctive lexical signals per item topic (lowercased substring cues)
_TOPIC_SIGNALS: dict[str, list[str]] = {
    "1": ["our business", "we ", "products", "compete", "employees", "founded", "incorporated"],
    "1A": ["risk", "adversely", "could", "materially", "harm", "uncertain"],
    "1B": ["none", "unresolved", "staff comments"],
    "1C": ["cybersecurity", "threats", "board", "risk", "information security"],
    "2": ["properties", "square feet", "facilities", "lease", "headquarters", "own"],
    "3": ["legal proceedings", "litigation", "lawsuit", "claims", "court", "note"],
    "4": ["mine safety", "not applicable", "mine"],
    "5": ["common stock", "holders", "dividend", "repurchase", "market", "securities"],
    "6": ["reserved"],
    "7": ["results of operations", "liquidity", "compared", "revenue", "cash flows", "gross margin"],
    "7A": ["market risk", "interest rate", "foreign currency", "hypothetical", "quantitative"],
    "8": ["consolidated", "balance sheet", "cash flows", "notes to", "statements of", "financial"],
    "9": ["none", "changes in", "accountants", "disagreements"],
    "9A": ["disclosure controls", "internal control", "effective", "procedures"],
    "9B": ["none", "other information", "during the", "trading arrangement", "10b5-1", "rule 10b5"],
    "9C": ["foreign jurisdictions", "not applicable", "inspections"],
    "10": ["proxy statement", "incorporated", "directors", "officers", "governance"],
    "11": ["proxy statement", "incorporated", "compensation"],
    "12": ["proxy statement", "incorporated", "security ownership", "beneficial"],
    "13": ["proxy statement", "incorporated", "related", "independence"],
    "14": ["proxy statement", "incorporated", "accountant", "fees"],
    "15": ["exhibit", "financial statement schedules", "index to", "filed"],
    "16": ["none", "summary"],
}

_BOILERPLATE = re.compile(
    r"^(none|n/?a|not\s+applicable|none\s+applicable|not\s+applicable\.?\s*none|\[?reserved\]?)\.?$",
    re.IGNORECASE)


@dataclass
class TopicCheck:
    verdict: str          # consistent | weak | inconsistent | boilerplate | skipped
    matched: list[str]
    detail: str


def check_topic(item_code: str, body: str) -> TopicCheck:
    signals = _TOPIC_SIGNALS.get(item_code, [])
    stripped = body.strip()
    if not stripped:
        return TopicCheck("skipped", [], "empty body")
    if _BOILERPLATE.match(stripped):
        return TopicCheck("boilerplate", [], "None./Not applicable./Reserved — complete short answer")
    low = body.lower()
    matched = [s for s in signals if s in low]
    # for a substantive body, expect at least 2 distinct topic signals
    need = 1 if len(stripped) < 400 else 2
    if len(matched) >= need:
        return TopicCheck("consistent", matched,
                          f"{len(matched)} topic signal(s) present")
    if matched:
        return TopicCheck("weak", matched, f"only {len(matched)} topic signal(s) — thin")
    return TopicCheck("inconsistent", [],
                      "no canonical topic language found — span may be mislabelled or mis-bounded")
