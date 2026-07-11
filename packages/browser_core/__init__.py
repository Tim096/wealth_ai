"""Browser agent domain types: controlled action space, task contract, failure taxonomy."""

from browser_core.actions import BrowserAction, ElementTarget, WaitCondition
from browser_core.budget import Budget
from browser_core.contract import BrowserTaskContract, ForbiddenCondition, SuccessCondition
from browser_core.failures import FAILURE_TAXONOMY, FailureType
from browser_core.selector_memory import RepairEvent, SelectorMemory, SelectorVersion

__all__ = [
    "BrowserAction",
    "BrowserTaskContract",
    "Budget",
    "ElementTarget",
    "FAILURE_TAXONOMY",
    "FailureType",
    "ForbiddenCondition",
    "RepairEvent",
    "SelectorMemory",
    "SelectorVersion",
    "SuccessCondition",
    "WaitCondition",
]
