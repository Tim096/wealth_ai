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


class ItemSegment(BaseModel):
    filing_id: str
    item_code: ItemCode
    canonical_title: str
    extracted_heading: str
    start_offset: int
    end_offset: int
    text_sha256: str
    status: ItemStatus
    confidence: float = Field(ge=0.0, le=1.0)
    warnings: list[str] = Field(default_factory=list)
    evidence: list[BoundaryEvidence] = Field(default_factory=list)
