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
from browser_agent.capability import screen_action, screen_task
from browser_agent.executor import ActionExecutor, ActionOutcome
from browser_agent.memory_store import MemoryStore
from browser_agent.observer import PageObserver
from browser_agent.repair import diagnose_failure, repair_target
from browser_agent.verifier import verify_contract
from observability_core import EvidenceRecord, EvidenceStore, VerifierResult, sha256_text


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
    status: str                     # pass | fail | unknown | refused
    verifier: VerifierResult
    steps: list[StepTrace] = field(default_factory=list)
    repairs: int = 0
    total_latency_ms: float = 0.0
    confidence: float = 0.0         # numeric, derived from verifier + repair cost

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id, "site": self.site, "status": self.status,
            "confidence": round(self.confidence, 3),
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
                 artifact_dir: Path | str | None = None,
                 evidence_store: EvidenceStore | None = None,
                 downloads_dir: Path | str | None = None) -> None:
        self.page = page
        self.downloads_dir = Path(downloads_dir) if downloads_dir else None
        if self.downloads_dir:
            self.downloads_dir.mkdir(parents=True, exist_ok=True)
        self.executor = ActionExecutor(page, downloads_dir=self.downloads_dir)
        self.observer = PageObserver(page)
        self.memory = memory
        self.site = site
        self.task_type = task_type
        self.evidence_store = evidence_store
        self.artifact_dir = Path(artifact_dir) if artifact_dir else None
        if self.artifact_dir:
            self.artifact_dir.mkdir(parents=True, exist_ok=True)

    def _emit_evidence(self, run_id: str, task_id: str, run: "TaskRun") -> None:
        """Route the browser run through the SAME EvidenceRecord contract the SEC
        pipeline uses — one record per step + one verdict record."""
        if self.evidence_store is None:
            return
        for i, s in enumerate(run.steps):
            self.evidence_store.append(EvidenceRecord(
                run_id=run_id, app="browser_agent", step_id=f"{task_id}-step{i}-{s.step}",
                timestamp=s and self._now() or self._now(),
                input_hash=sha256_text(s.selector_used or s.step),
                output_hash=sha256_text(s.detail or s.repair_chosen or ""),
                tool_used=f"browser_agent.{s.mode}.{s.action}",
                latency_ms=s.latency_ms,
                status="pass" if s.ok else "fail",
                evidence_type="screenshot" if s.screenshot else "trace",
                artifact_path=s.screenshot or "",
                verifier_result=VerifierResult(
                    status="pass" if s.ok else "fail",
                    reason=s.diagnosis or s.detail or f"{s.step}.{s.action}",
                    required_evidence=[s.step], observed_evidence=[s.selector_used] if s.selector_used else [],
                    missing_evidence=[] if s.ok else [s.step]),
            ))
        self.evidence_store.append(EvidenceRecord(
            run_id=run_id, app="browser_agent", step_id=f"{task_id}-verdict",
            timestamp=self._now(), input_hash=sha256_text(task_id),
            output_hash=sha256_text(run.status), tool_used="browser_agent.verify_contract",
            latency_ms=run.total_latency_ms, cost_usd=0.0,
            status=run.status if run.status in ("pass", "fail", "unknown") else "unknown",
            evidence_type="metric", artifact_path="", verifier_result=run.verifier,
        ))

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
        # action-level capability guard: never enter credentials / hit irreversible controls
        ascreen = screen_action(action)
        if not ascreen.allowed:
            trace.append(StepTrace(step=step.purpose, action=step.kind, ok=False, mode="script",
                                   diagnosis="capability_refused", detail=ascreen.reason,
                                   selector_used=selector))
            return ActionOutcome(ok=False, action_type=step.kind, error="refused: " + ascreen.reason)
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

        # Repair Mode: diagnose FIRST, then dispatch a strategy by failure type
        obs = self.observer.observe()
        self._dismiss_modal_if_present(trace)
        obs = self.observer.observe()
        diag = diagnose_failure(out, obs, url_before != self.page.url)
        self.memory.record(self.site, self.task_type, step.purpose, selector,
                           self._now(), success=False)

        # diagnosis-driven, not one-size-fits-all retry (SPEC 6.8)
        if diag.failure_type == "click_no_effect":
            # try pressing Enter on the field instead of clicking the button
            alt = PressAction(target=ElementTarget(selector=selector, selector_type="css"), key="Enter")
            out_alt = self.executor.execute(alt)
            trace.append(StepTrace(step=step.purpose, action="press", ok=out_alt.ok, mode="repair",
                                   diagnosis=diag.failure_type,
                                   detail="click had no effect -> pressed Enter",
                                   selector_used=selector, latency_ms=out_alt.latency_ms,
                                   screenshot=self._screenshot(f"{step.purpose}-enter")))
            return out_alt
        if diag.failure_type == "empty_result":
            # not a selector problem — no evidence of success; refuse to repair-into-success
            trace.append(StepTrace(step=step.purpose, action=step.kind, ok=False, mode="repair",
                                   diagnosis=diag.failure_type,
                                   detail="empty result set — not repairable by selector; left for verifier",
                                   selector_used=selector,
                                   screenshot=self._screenshot(f"{step.purpose}-empty")))
            return out
        if diag.failure_type == "timeout":
            # dedicated strategy: switch the wait to network-idle and retry once
            self.executor.execute(WaitForAction(
                condition=WaitCondition(kind="network_idle", timeout_ms=8000)))
            out_retry = self.executor.execute(action)
            trace.append(StepTrace(step=step.purpose, action=step.kind, ok=out_retry.ok, mode="repair",
                                   diagnosis=diag.failure_type,
                                   detail="timeout -> switched wait condition to network_idle, retried",
                                   selector_used=selector, latency_ms=out_retry.latency_ms,
                                   screenshot=self._screenshot(f"{step.purpose}-waited")))
            return out_retry
        # selector_not_found / multiple_candidates / wrong_page -> a11y-tree search
        rr = repair_target(step.purpose, obs, want_value=step.value)
        considered = rr.considered
        if not rr.ok or rr.new_target is None:
            trace.append(StepTrace(step=step.purpose, action=step.kind, ok=False, mode="repair",
                                   diagnosis=diag.failure_type, detail="no viable candidate",
                                   repair_considered=considered,
                                   screenshot=self._screenshot(f"{step.purpose}-repair-fail")))
            return out
        # small-step verify: act on the EXACT element (data-aid), remember the
        # DURABLE selector so the fix survives a reload
        action2 = self._build_action(step, rr.new_target)
        out2 = self.executor.execute(action2)
        durable = rr.durable_selector
        repair = RepairEvent(
            timestamp=self._now(), failed_selector=selector, failure_type=diag.failure_type,
            candidates_considered=considered, chosen_selector=durable,
            choice_reason=rr.chosen_reason, verified=out2.ok, evidence_run_id="",
        )
        self.memory.record(self.site, self.task_type, step.purpose, durable,
                           self._now(), success=out2.ok,
                           dom_fingerprint=sha256_text(self.page.content())[:16], repair=repair)
        trace.append(StepTrace(step=step.purpose, action=step.kind, ok=out2.ok, mode="repair",
                               diagnosis=diag.failure_type, detail=diag.detail,
                               repair_considered=considered, repair_chosen=rr.chosen_reason,
                               selector_used=durable, latency_ms=out2.latency_ms,
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

    def run_agentic(self, task_id: str, contract: BrowserTaskContract, planner,
                    max_steps: int = 8, on_step=None) -> TaskRun:
        """Agent Mode (SPEC 6.2): an LLM planner chooses actions from the
        controlled schema; each is capability-screened and executed; the
        verifier — not the LLM — decides the outcome. Falls back cleanly if the
        planner has no credentials. `on_step(text)` is called live per step."""
        def _emit(text):
            if on_step:
                try:
                    on_step(text)
                except Exception:  # noqa: BLE001 — a UI callback must never break the run
                    pass
        t0 = time.perf_counter()
        cap = screen_task(contract.natural_language_task)
        if not cap.allowed:
            return TaskRun(task_id=task_id, site=self.site, status="refused",
                           verifier=VerifierResult(status="unknown", reason=cap.reason,
                                                   missing_evidence=["task refused by capability guard"]),
                           total_latency_ms=(time.perf_counter() - t0) * 1000)
        trace: list[StepTrace] = []
        history: list[str] = []
        llm_cost = 0.0
        self._dismiss_modal_if_present(trace)
        verdict = VerifierResult(status="unknown", reason="no steps taken")
        _emit(f"🧠 想任務:{contract.natural_language_task}")
        for _ in range(max_steps):
            obs = self.observer.observe()
            verdict = verify_contract(contract, obs, {})
            if verdict.status == "pass":
                break
            _emit("💭 看畫面、決定下一步…")
            decision = planner.next_action(
                contract.natural_language_task,
                [f"{c.type}:{c.value}" for c in contract.success_conditions], obs, history)
            if decision.llm is not None:
                llm_cost += decision.llm.cost_usd
            if decision.kind in ("done", "give_up"):
                history.append(f"{decision.kind}({decision.reason})")
                trace.append(StepTrace(step="planner", action=decision.kind, ok=decision.kind == "done",
                                       mode="agent", detail=decision.reason))
                _emit(f"✅ {decision.kind}:{decision.reason}")
                break
            action = decision.action
            ascreen = screen_action(action)
            if not ascreen.allowed:
                trace.append(StepTrace(step="planner", action=action.type, ok=False, mode="agent",
                                       diagnosis="capability_refused", detail=ascreen.reason))
                _emit(f"🛑 拒絕(責任邊界):{ascreen.reason}")
                break
            out = self.executor.execute(action)
            history.append(f"{action.type}:{'ok' if out.ok else 'fail'}")
            detail = decision.reason
            if action.type == "download" and out.ok:
                detail = f"下載完成 → {self.executor.last_download_path}"
            trace.append(StepTrace(step="planner", action=action.type, ok=out.ok, mode="agent",
                                   detail=detail, selector_used=getattr(
                                       getattr(action, "target", None), "selector", ""),
                                   latency_ms=out.latency_ms,
                                   screenshot=self._screenshot(f"agent-{len(trace)}")))
            _emit(f"{'⬇️' if action.type == 'download' and out.ok else ('👉' if out.ok else '⚠️')} "
                  f"{action.type}:{detail}")
            # settle before re-observing: an action that navigates or fires an
            # SPA fetch (goto/click/press) needs the new content to load, else
            # the next observation shows the OLD page and the planner loops
            # (this is why EDGAR full-text search kept re-filling the ticker).
            if action.type in ("goto", "click", "press"):
                try:
                    self.page.wait_for_load_state("networkidle", timeout=4000)
                except Exception:  # noqa: BLE001 — best-effort; some pages never idle
                    pass
            self.page.wait_for_timeout(300)
        extracted = {"__download__": self.executor.last_download_path} if self.executor.last_download_path else {}
        obs = self.observer.observe()
        verdict = verify_contract(contract, obs, extracted)
        base = {"pass": 1.0, "unknown": 0.4, "fail": 0.0}[verdict.status]
        run = TaskRun(task_id=task_id, site=self.site, status=verdict.status, verifier=verdict,
                      steps=trace, repairs=0, confidence=base,
                      total_latency_ms=(time.perf_counter() - t0) * 1000)
        self._emit_evidence(f"agent-{self.site}-{task_id}", task_id, run)
        return run

    def run(self, task_id: str, steps: list[Step], contract: BrowserTaskContract) -> TaskRun:
        t0 = time.perf_counter()
        # capability guard (SPEC 6.3/6.4): refuse out-of-scope tasks in code
        cap = screen_task(contract.natural_language_task)
        if not cap.allowed:
            return TaskRun(
                task_id=task_id, site=self.site, status="refused",
                verifier=VerifierResult(status="unknown", reason=cap.reason,
                                        required_evidence=[], observed_evidence=[],
                                        missing_evidence=["task refused by capability guard"]),
                steps=[], repairs=0, confidence=0.0,
                total_latency_ms=(time.perf_counter() - t0) * 1000,
            )
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
        base = {"pass": 1.0, "unknown": 0.4, "fail": 0.0}[verdict.status]
        confidence = max(0.0, base - 0.1 * repairs) if verdict.status == "pass" else base
        run = TaskRun(
            task_id=task_id, site=self.site, status=verdict.status, verifier=verdict,
            steps=trace, repairs=repairs, confidence=confidence,
            total_latency_ms=(time.perf_counter() - t0) * 1000,
        )
        self._emit_evidence(f"browser-{self.site}-{task_id}", task_id, run)
        return run
