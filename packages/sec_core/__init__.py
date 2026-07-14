"""SEC 10-K extraction domain types: item segments, confidence components, adjudicator I/O."""

from sec_core.items import CANONICAL_ITEM_TITLES, ItemCode, ItemSegment, ItemStatus
from sec_core.confidence import ConfidenceBreakdown
from sec_core.adjudicator import AdjudicatorDecision, BoundaryEvidence

PIPELINE_REV = "sec-pipeline-2026.07"
"""Extraction-pipeline revision. Bump on any change that alters item spans, the
output schema, or provenance fields (e.g. the multi-range `source_ranges`
reassembly). Surfaced at wealth-sec /api/health.pipeline_rev so a deployed
instance's output contract is traceable, not merely inferable."""

__all__ = [
    "AdjudicatorDecision",
    "BoundaryEvidence",
    "CANONICAL_ITEM_TITLES",
    "ConfidenceBreakdown",
    "ItemCode",
    "ItemSegment",
    "ItemStatus",
    "PIPELINE_REV",
]
