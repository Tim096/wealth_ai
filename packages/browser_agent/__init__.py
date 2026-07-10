"""Capability-aware browser agent runtime (SPEC section 6).

Script Mode (known selectors, no LLM) -> Agent Mode (unknown) -> Repair Mode
(diagnosed failure). Every step is a controlled BrowserAction, every task is
verified against a contract, every failure is diagnosed then repaired via
the accessibility tree, and nothing is claimed successful without evidence.
"""

from browser_agent.observer import Observation, PageObserver, ElementCandidate
from browser_agent.executor import ActionExecutor, ActionOutcome
from browser_agent.verifier import verify_contract
from browser_agent.repair import diagnose_failure, repair_target
from browser_agent.capability import screen_action, screen_task, CapabilityDecision
from browser_agent.agent import BrowserAgent, TaskRun

__all__ = [
    "ActionExecutor",
    "ActionOutcome",
    "BrowserAgent",
    "CapabilityDecision",
    "ElementCandidate",
    "Observation",
    "PageObserver",
    "TaskRun",
    "diagnose_failure",
    "repair_target",
    "screen_action",
    "screen_task",
    "verify_contract",
]
