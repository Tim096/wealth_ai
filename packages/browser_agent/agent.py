"""Browser agent orchestrator (SPEC 6.2).

Runs a task as a sequence of purpose-tagged steps: resolve each step's target
from selector memory (Script Mode) or by repair (Repair Mode), execute the
controlled action, and on failure diagnose -> repair via the accessibility
tree -> small-step verify -> update memory -> resume. Finishes by verifying
the task contract; the result is pass / fail / unknown with a full evidence
trace, never a bare "looks done".
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from browser_core import BrowserTaskContract, ElementTarget, RepairEvent
from browser_core.actions import (
    ClickAction, FillAction, PressAction, WaitForAction, WaitCondition,
)
from browser_agent.executor import ActionExecutor, ActionOutcome
from browser_agent.memory_store import MemoryStore
from browser_agent.observer import PageObserver
from browser_agent.repair import diagnose_failure, repair_target
from browser_agent.verifier import verify_contract
from observability_core import VerifierResult, sha256_text


@dataclass
class Step:
    purpose: str          # search_box / submit_button / ...
    kind: str             # fill / click / press / wait
    value: str = ""       # fill value / press key / wait target
    fallback_selector: str = ""  # initial guess when memory is empty


@dataclass
class StepTrace:
    step: str
    action: str
    ok: bool
    mode: str                       # script | repair
    detail: str = ""
    diagnosis: str = ""
    repair_considered: list[str] = field(default_factory=list)
    repair_chosen: str = ""
    selector_used: str = ""
    latency_ms: float = 0.0
    screenshot: str = ""


@dataclass
class TaskRun:
    task_id: str
    site: str
    status: str                     # pass | fail | unknown
    verifier: VerifierResult
    steps: list[StepTrace] = field(default_factory=list)
    repairs: int = 0
    total_latency_ms: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id, "site": self.site, "status": self.status,
            "repairs": self.repairs, "total_latency_ms": round(self.total_latency_ms, 1),
            "verifier": {
                "status": self.verifier.status, "reason": self.verifier.reason,
                "observed": self.verifier.observed_evidence,
                "missing": self.verifier.missing_evidence,
            },
            "steps": [
                {"step": s.step, "action": s.action, "ok": s.ok, "mode": s.mode,
                 "detail": s.detail, "diagnosis": s.diagnosis,
                 "repair_considered": s.repair_considered, "repair_chosen": s.repair_chosen,
                 "selector_used": s.selector_used, "latency_ms": round(s.latency_ms, 1),
                 "screenshot": s.screenshot}
                for s in self.steps
            ],
        }


class BrowserAgent:
    def __init__(self, page, memory: MemoryStore, site: str, task_type: str,
                 artifact_dir: Path | str | None = None) -> None:
        self.page = page
        self.executor = ActionExecutor(page)
        self.observer = PageObserver(page)
        self.memory = memory
        self.site = site
        self.task_type = task_type
        self.artifact_dir = Path(artifact_dir) if artifact_dir else None
        if self.artifact_dir:
            self.artifact_dir.mkdir(parents=True, exist_ok=True)

    def _now(self) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def _screenshot(self, tag: str) -> str:
        if not self.artifact_dir:
            return ""
        p = self.artifact_dir / f"{tag}.png"
        try:
            self.page.screenshot(path=str(p))
            return str(p)
        except Exception:
            return ""

    def _dismiss_modal_if_present(self, trace: list[StepTrace]) -> None:
        obs = self.observer.observe()
        if not obs.modal_present:
            return
        rr = repair_target("submit_button", obs, want_value="accept")
        # find an accept/dismiss control among candidates
        for c in obs.candidates:
            blob = f"{c.id} {c.aria_label} {c.text}".lower()
            if any(w in blob for w in ("accept", "agree", "dismiss", "close", "ok")):
                out = self.executor.execute(ClickAction(
                    target=ElementTarget(selector=c.css(), selector_type="css")))
                trace.append(StepTrace(step="dismiss_modal", action="click", ok=out.ok,
                                       mode="repair", detail="dismissed blocking modal",
                                       diagnosis="modal_blocking", selector_used=c.css(),
                                       latency_ms=out.latency_ms,
                                       screenshot=self._screenshot("modal-dismissed")))
                return

    def _resolve_and_run(self, step: Step, trace: list[StepTrace]) -> ActionOutcome:
        # Script Mode: try the remembered / fallback selector first
        remembered = self.memory.preferred(self.site, self.task_type, step.purpose)
        selector = remembered or step.fallback_selector
        target = ElementTarget(selector=selector, selector_type="css", description=step.purpose)
        action = self._build_action(step, target)
        url_before = self.page.url
        out = self.executor.execute(action)

        if out.ok:
            self.memory.record(self.site, self.task_type, step.purpose, selector,
                               self._now(), success=True,
                               dom_fingerprint=sha256_text(self.page.content())[:16])
            trace.append(StepTrace(step=step.purpose, action=step.kind, ok=True, mode="script",
                                   detail=out.detail, selector_used=selector,
                                   latency_ms=out.latency_ms,
                                   screenshot=self._screenshot(f"{step.purpose}-ok")))
            return out

        # Repair Mode: diagnose, then search the accessibility tree
        obs = self.observer.observe()
        self._dismiss_modal_if_present(trace)
        obs = self.observer.observe()
        diag = diagnose_failure(out, obs, url_before != self.page.url)
        self.memory.record(self.site, self.task_type, step.purpose, selector,
                           self._now(), success=False)
        rr = repair_target(step.purpose, obs, want_value=step.value)
        considered = rr.considered
        if not rr.ok or rr.new_target is None:
            trace.append(StepTrace(step=step.purpose, action=step.kind, ok=False, mode="repair",
                                   diagnosis=diag.failure_type, detail="no viable candidate",
                                   repair_considered=considered,
                                   screenshot=self._screenshot(f"{step.purpose}-repair-fail")))
            return out
        # small-step verify: re-run the action against the repaired target
        action2 = self._build_action(step, rr.new_target)
        out2 = self.executor.execute(action2)
        repair = RepairEvent(
            timestamp=self._now(), failed_selector=selector, failure_type=diag.failure_type,
            candidates_considered=considered, chosen_selector=rr.new_target.selector,
            choice_reason=rr.chosen_reason, verified=out2.ok, evidence_run_id="",
        )
        self.memory.record(self.site, self.task_type, step.purpose, rr.new_target.selector,
                           self._now(), success=out2.ok,
                           dom_fingerprint=sha256_text(self.page.content())[:16], repair=repair)
        trace.append(StepTrace(step=step.purpose, action=step.kind, ok=out2.ok, mode="repair",
                               diagnosis=diag.failure_type, detail=diag.detail,
                               repair_considered=considered, repair_chosen=rr.chosen_reason,
                               selector_used=rr.new_target.selector, latency_ms=out2.latency_ms,
                               screenshot=self._screenshot(f"{step.purpose}-repaired")))
        return out2

    def _build_action(self, step: Step, target: ElementTarget):
        if step.kind == "fill":
            return FillAction(target=target, value=step.value)
        if step.kind == "click":
            return ClickAction(target=target)
        if step.kind == "press":
            return PressAction(target=target, key=step.value)
        if step.kind == "wait":
            return WaitForAction(condition=WaitCondition(kind="text_visible", value=step.value))
        raise ValueError(f"unknown step kind {step.kind}")

    def run(self, task_id: str, steps: list[Step], contract: BrowserTaskContract) -> TaskRun:
        t0 = time.perf_counter()
        trace: list[StepTrace] = []
        self._dismiss_modal_if_present(trace)
        repairs = 0
        for step in steps:
            out = self._resolve_and_run(step, trace)
            if trace and trace[-1].mode == "repair" and trace[-1].diagnosis:
                repairs += 1
        # small settle for lazy content, then observe + verify
        self.page.wait_for_timeout(400)
        obs = self.observer.observe()
        extracted: dict[str, str] = {}
        verdict = verify_contract(contract, obs, extracted)
        self.memory.save()
        return TaskRun(
            task_id=task_id, site=self.site, status=verdict.status, verifier=verdict,
            steps=trace, repairs=repairs, total_latency_ms=(time.perf_counter() - t0) * 1000,
        )
