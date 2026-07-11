"""Selector memory (SPEC 6.9): per-site, per-purpose selector versions with
success/fail counters and repair history, so UI drift is repaired once and
remembered instead of re-diagnosed every run.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ElementPurpose = Literal[
    "search_box",
    "submit_button",
    "result_link",
    "download_button",
    "filter_dropdown",
]


class SelectorVersion(BaseModel):
    selector: str
    selector_type: Literal["css", "xpath", "role", "text", "semantic"]
    first_seen: str
    last_seen: str
    success_count: int = 0
    fail_count: int = 0
    last_dom_fingerprint: str = ""
    # P0-7 structural identity (BU cascading locator / SK cleaned-JSON SHA256
    # rebind): hashes of the element this selector bound to when it last
    # WORKED, so drift can be repaired by deterministic hash match first.
    element_hash: str = ""          # EXACT level — full cleaned structural fields
    element_hash_stable: str = ""   # STABLE level — drift-tolerant subset


class RepairEvent(BaseModel):
    timestamp: str
    failed_selector: str
    failure_type: str
    candidates_considered: list[str]
    chosen_selector: str
    choice_reason: str
    verified: bool
    evidence_run_id: str


class SelectorMemory(BaseModel):
    site: str
    task_type: str
    element_purpose: ElementPurpose
    selector_versions: list[SelectorVersion] = Field(default_factory=list)
    preferred_selector: str = ""
    repair_history: list[RepairEvent] = Field(default_factory=list)
