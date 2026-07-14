"""ItemSegment schema (SPEC 7.11). Extracted text is always a source exact span
addressed by offsets + sha256 — the LLM never generates filing text.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from sec_core.adjudicator import BoundaryEvidence

ItemCode = Literal[
    "1", "1A", "1B", "1C",
    "2", "3", "4", "5", "6",
    "7", "7A", "8", "9", "9A", "9B", "9C",
    "10", "11", "12", "13", "14", "15", "16",
]

ItemStatus = Literal[
    "pass",
    "partial",
    "missing",
    "ambiguous",
    "incorporated_by_reference",
    "reserved",
    "unsupported",
]

CANONICAL_ITEM_TITLES: dict[str, str] = {
    "1": "Business",
    "1A": "Risk Factors",
    "1B": "Unresolved Staff Comments",
    "1C": "Cybersecurity",
    "2": "Properties",
    "3": "Legal Proceedings",
    "4": "Mine Safety Disclosures",
    "5": "Market for Registrant's Common Equity, Related Stockholder Matters and Issuer Purchases of Equity Securities",
    "6": "[Reserved]",
    "7": "Management's Discussion and Analysis of Financial Condition and Results of Operations",
    "7A": "Quantitative and Qualitative Disclosures About Market Risk",
    "8": "Financial Statements and Supplementary Data",
    "9": "Changes in and Disagreements with Accountants on Accounting and Financial Disclosure",
    "9A": "Controls and Procedures",
    "9B": "Other Information",
    "9C": "Disclosure Regarding Foreign Jurisdictions that Prevent Inspections",
    "10": "Directors, Executive Officers and Corporate Governance",
    "11": "Executive Compensation",
    "12": "Security Ownership of Certain Beneficial Owners and Management and Related Stockholder Matters",
    "13": "Certain Relationships and Related Transactions, and Director Independence",
    "14": "Principal Accountant Fees and Services",
    "15": "Exhibits, Financial Statement Schedules",
    "16": "Form 10-K Summary",
}


Provenance = Literal[
    "offset_exact_span",         # body is a source-exact span addressed by offsets (normal path)
    "cross_reference_pointer",   # only a pointer into an annual report / another section was found
    "resolved_from_page_anchor", # wrapper body recovered from printed page-number anchors (source-exact)
    "resolved_from_section_anchor",  # wrapper body recovered from the bound report's own section heading
    "unresolved",                # no addressable content found
]


class ItemSegment(BaseModel):
    filing_id: str
    item_code: ItemCode
    canonical_title: str
    extracted_heading: str
    start_offset: int
    end_offset: int
    # Multi-range body reassembly: normally empty, meaning the body is the single
    # source-exact span [start_offset, end_offset). When a cross-reference-index
    # item's body is split across several printed page ranges ("Pages 4-5, 18-39,
    # 45-46"), this holds every document-ordered (start, end) span; the body is
    # their CONCATENATION, start/end_offset hold the bounding envelope, and
    # text_sha256 is over the concatenation. text_of()/clean_text_of() honour it.
    source_ranges: list[tuple[int, int]] = Field(default_factory=list)
    text_sha256: str
    status: ItemStatus
    confidence: float = Field(ge=0.0, le=1.0)
    warnings: list[str] = Field(default_factory=list)
    evidence: list[BoundaryEvidence] = Field(default_factory=list)
    # --- trustworthiness surface (matches what strong submissions expose) ---
    provenance: Provenance = "offset_exact_span"
    needs_review: bool = False  # true => do not trust status without human/oracle check
    xbrl_check: str = ""        # independent-oracle result, set by xbrl cross-validation
    topic_check: str = ""       # per-item lexical topic-consistency verdict (all items)
    engine_check: str = ""      # third-engine (edgartools) triangulation verdict
    cyd_check: str = ""         # CYD iXBRL official Item 1C span agreement (Item 1C only)
