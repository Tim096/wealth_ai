"""Selector memory persistence (SPEC 6.9). Per site+task+purpose selector
versions with success/fail counts and repair history, stored as JSON so UI
drift is repaired once and remembered."""

from __future__ import annotations

import json
from pathlib import Path

from browser_core import RepairEvent, SelectorMemory, SelectorVersion


class MemoryStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._mem: dict[str, SelectorMemory] = {}
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            for k, v in data.items():
                self._mem[k] = SelectorMemory.model_validate(v)

    @staticmethod
    def _key(site: str, task_type: str, purpose: str) -> str:
        return f"{site}::{task_type}::{purpose}"

    def get(self, site: str, task_type: str, purpose: str) -> SelectorMemory | None:
        return self._mem.get(self._key(site, task_type, purpose))

    def preferred(self, site: str, task_type: str, purpose: str) -> str | None:
        m = self.get(site, task_type, purpose)
        return m.preferred_selector if m and m.preferred_selector else None

    def record(self, site: str, task_type: str, purpose: str, selector: str,
               timestamp: str, success: bool, dom_fingerprint: str = "",
               repair: RepairEvent | None = None) -> None:
        key = self._key(site, task_type, purpose)
        m = self._mem.get(key) or SelectorMemory(site=site, task_type=task_type,
                                                 element_purpose=purpose)  # type: ignore[arg-type]
        ver = next((v for v in m.selector_versions if v.selector == selector), None)
        if ver is None:
            ver = SelectorVersion(selector=selector, selector_type="css",
                                  first_seen=timestamp, last_seen=timestamp,
                                  last_dom_fingerprint=dom_fingerprint)
            m.selector_versions.append(ver)
        ver.last_seen = timestamp
        if dom_fingerprint:
            ver.last_dom_fingerprint = dom_fingerprint
        if success:
            ver.success_count += 1
            m.preferred_selector = selector
        else:
            ver.fail_count += 1
        if repair is not None:
            m.repair_history.append(repair)
        self._mem[key] = m

    def save(self) -> None:
        data = {k: json.loads(v.model_dump_json()) for k, v in self._mem.items()}
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")
