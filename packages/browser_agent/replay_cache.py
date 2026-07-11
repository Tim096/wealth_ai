"""P0-10 agent-mode cross-run replay cache (SK fallback write-back / SG replay
cache / WC scheduled-replay invalidation loop).

Agent Mode used to pay full LLM cost every run and throw the recovered
trajectory away. Now a VERIFIER-passed run banks its successful actions —
keyed by (site, task_type, task) with per-step element identity — and the next
run of the SAME task replays them action-by-action before asking the LLM; the
first step that no longer resolves or fails invalidates the entry and hands
the run back to the planner. The verifier stays the only judge: a stale cache
can never fake success — it can only waste the steps it replayed.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from browser_core import ElementTarget
from browser_core.actions import (
    ClickAction, DownloadAction, ExtractTextAction, FillAction, GotoAction,
    KeyboardAction, PressAction,
)
from browser_agent.observer import Observation, structural_hashes
from browser_agent.repair import rebind_by_hash

# planner actions always address elements by the volatile data-aid handle;
# the cache must re-key them by durable selector + structural hash instead
_AID_RE = re.compile(r'\[data-aid="(\d+)"\]')


@dataclass
class ReplayStep:
    """One banked planner action, in a form that survives a new session."""
    action: str            # goto / click / fill / press / extract_text / download / keyboard
    value: str = ""        # fill text / goto url / download url / keyboard text
    key: str = ""          # press key / keyboard chord
    selector: str = ""     # durable selector of the element acted on
    element_hash: str = ""         # P0-7 EXACT identity of that element
    element_hash_stable: str = ""  # P0-7 STABLE identity
    label: str = ""        # the planner's reason — the step label / audit trail


def _candidate_for(target: ElementTarget | None, obs: Observation):
    m = _AID_RE.fullmatch(target.selector if target is not None else "")
    if not m:
        return None
    idx = int(m.group(1))
    return next((c for c in obs.candidates if c.index == idx), None)


def step_from_action(action, obs: Observation, label: str = "") -> ReplayStep | None:
    """Distil ONE successful planner action into a replayable step. Element
    targets are recorded by durable selector + structural hashes (data-aid is
    stamped fresh every observe and means nothing next session). Returns None
    for actions that cannot be replayed faithfully across sessions (mouse
    coordinates, snapshots, …) — a run containing one is not banked."""
    t = action.type
    if t == "goto":
        return ReplayStep(action=t, value=action.url, label=label)
    if t == "keyboard":
        return ReplayStep(action=t, value=action.text, key=action.keys, label=label)
    if t in ("click", "fill", "press", "extract_text", "download"):
        target = getattr(action, "target", None)
        if target is None and t == "download":
            # URL / current-page download needs no element identity
            return ReplayStep(action=t, value=action.url, label=label)
        cand = _candidate_for(target, obs)
        if cand is None:
            return None
        ex, st = structural_hashes(cand)
        rs = ReplayStep(action=t, selector=cand.css(), element_hash=ex,
                        element_hash_stable=st, label=label)
        if t == "fill":
            rs.value = action.value
        elif t == "press":
            rs.key = action.key
        elif t == "download":
            rs.value = action.url
        return rs
    return None


def action_from_step(rs: ReplayStep, obs: Observation):
    """Re-materialise a cached step against the CURRENT observation. Element
    steps resolve by the P0-7 hash cascade first (exactly-1 rule), falling
    back to the recorded durable selector — the same trust level Script Mode
    gives a remembered selector. Returns None when nothing addresses the
    element any more, so the caller abandons the cache (never a guess)."""
    if rs.action == "goto":
        return GotoAction(url=rs.value)
    if rs.action == "keyboard":
        return KeyboardAction(text=rs.value, keys=rs.key)
    if rs.action == "download" and not rs.selector and not rs.element_hash:
        return DownloadAction(url=rs.value)
    cand, _level = rebind_by_hash(rs.element_hash, rs.element_hash_stable, obs)
    sel = cand.aid_selector() if cand is not None else rs.selector
    if not sel:
        return None
    target = ElementTarget(selector=sel, selector_type="css",
                           description=f"replay {rs.label or rs.action}")
    if rs.action == "click":
        return ClickAction(target=target)
    if rs.action == "fill":
        return FillAction(target=target, value=rs.value)
    if rs.action == "press":
        return PressAction(target=target, key=rs.key or "Enter")
    if rs.action == "extract_text":
        return ExtractTextAction(target=target)
    if rs.action == "download":
        return DownloadAction(target=target, url=rs.value)
    return None


class ReplayCache:
    """JSON-persisted (site, task_type, task) -> banked action sequence, the
    MemoryStore write-back pattern applied to Agent Mode. Banked ONLY on a
    verifier pass; invalidated the moment a replayed step diverges."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict[str, dict] = {}
        if self.path.exists():
            self._data = json.loads(self.path.read_text(encoding="utf-8"))

    @staticmethod
    def _key(site: str, task_type: str, task: str) -> str:
        # the task text is part of the key: replaying "fill INTC" into a task
        # about another entity would be confidently wrong, so a cache entry
        # only ever serves the exact task that banked it
        th = hashlib.sha256(" ".join(task.split()).encode("utf-8")).hexdigest()[:16]
        return f"{site}::{task_type}::{th}"

    def lookup(self, site: str, task_type: str, task: str) -> list[ReplayStep]:
        entry = self._data.get(self._key(site, task_type, task))
        if not entry:
            return []
        return [ReplayStep(**s) for s in entry.get("steps", [])]

    def bank(self, site: str, task_type: str, task: str,
             steps: list[ReplayStep], timestamp: str = "") -> None:
        key = self._key(site, task_type, task)
        prev = self._data.get(key) or {}
        self._data[key] = {
            "task": task,
            "steps": [asdict(s) for s in steps],
            "banked_at": timestamp,
            "success_count": int(prev.get("success_count", 0)) + 1,
        }

    def invalidate(self, site: str, task_type: str, task: str) -> None:
        self._data.pop(self._key(site, task_type, task), None)

    def save(self) -> None:
        self.path.write_text(json.dumps(self._data, indent=2, ensure_ascii=False),
                             encoding="utf-8")
