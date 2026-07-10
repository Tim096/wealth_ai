"""SEC 10-K extraction domain types: item segments, confidence components, adjudicator I/O."""

from sec_core.items import CANONICAL_ITEM_TITLES, ItemCode, ItemSegment, ItemStatus
from sec_core.confidence import ConfidenceBreakdown
from sec_core.adjudicator import AdjudicatorDecision, BoundaryEvidence

__all__ = [
    "AdjudicatorDecision",
    "BoundaryEvidence",
    "CANONICAL_ITEM_TITLES",
    "ConfidenceBreakdown",
    "ItemCode",
    "ItemSegment",
    "ItemStatus",
]
