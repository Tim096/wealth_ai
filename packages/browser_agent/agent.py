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

from browser_core import BrowserTaskContract, Budget, ElementTarget, RepairEvent
from browser_core.actions import (
    ClickAction, FillAction, PressAction, WaitForAction, WaitCondition,
)
from browser_agent.capability import screen_action, screen_task
from browser_agent.executor import ActionExecutor, ActionOutcome
from browser_agent.marks import set_of_marks
from browser_agent.memory_store import MemoryStore
from browser_agent.observer import (
    _ELEMENT_FIELDS_JS, PageObserver, diff_observations, structural_hashes,
)
from browser_agent.repair import diagnose_failure, rebind_by_hash, repair_target
from browser_agent.replay_cache import (
    ReplayCache, ReplayStep, action_from_step, step_from_action,
)
from browser_agent.trajectory import repetition_report
from browser_agent.verifier import check_conditions, subtract_baseline, verify_contract
from observability_core import EvidenceRecord, EvidenceStore, VerifierResult, sha256_text


# Popups appear on ANY site with ANY class name, so we detect a blocking
# overlay by GEOMETRY/BEHAVIOUR, not a class allow-list: a positioned, visible
# layer with a high stacking order that covers the viewport centre. The same
# pass stamps a close control (by label OR by top-right position) so we can
# click it; if it survives, a second routine neutralises it outright.
_OVERLAY_DETECT_JS = r"""
() => {
  const vw = innerWidth, vh = innerHeight, area = vw * vh || 1;
  const cands = [];
  for (const el of document.querySelectorAll('body *')) {
    const cs = getComputedStyle(el);
    if (!['fixed','absolute','sticky'].includes(cs.position)) continue;
    if (cs.visibility === 'hidden' || cs.display === 'none' || parseFloat(cs.opacity || '1') < 0.1) continue;
    if (cs.pointerEvents === 'none') continue;
    const r = el.getBoundingClientRect();
    if (r.width < 40 || r.height < 40) continue;
    const z = parseInt(cs.zIndex) || 0;
    const coversCentre = r.left <= vw/2 && r.right >= vw/2 && r.top <= vh/2 && r.bottom >= vh/2;
    const frac = (r.width * r.height) / area;
    // a translucent full-viewport dim layer is the tell-tale of a modal backdrop
    // and is independent of z-index (real modals use z as low as 10)
    const mm = (cs.backgroundColor || '').match(/rgba?\(([^)]+)\)/);
    const alpha = mm ? (mm[1].split(',').map(parseFloat)[3] ?? 1) : 1;
    const backdrop = mm && alpha > 0.05 && alpha < 0.98 && frac > 0.6;
    if (!coversCentre || frac <= 0.12) continue;
    // modal if it has real stacking OR looks like a dim backdrop
    if (z >= 50 || backdrop) cands.push({el, z, frac, backdrop});
  }
  if (!cands.length) return {present:false};
  cands.sort((a,b) => (b.backdrop - a.backdrop) || b.z - a.z || b.frac - a.frac);
  const top = cands[0].el;
  top.setAttribute('data-ovl','1');
  const closeRe = /\b(close|dismiss|no thanks|not now|skip|cancel|accept|agree|got it|ok|allow)\b|[×✕✖✗╳]/i;
  let close = null;
  for (const c of top.querySelectorAll('button,a,[role=button],[aria-label],[title]')) {
    const lbl = ((c.getAttribute('aria-label')||'') + ' ' + (c.getAttribute('title')||'') + ' ' + (c.textContent||'')).trim();
    if (lbl.length <= 30 && closeRe.test(lbl)) { close = c; break; }
  }
  if (!close) {                       // common case: an unlabeled × at the top-right corner
    const r = top.getBoundingClientRect(); let best = null, bestD = 1e9;
    for (const c of top.querySelectorAll('button,a,[role=button],svg,span,i')) {
      const cr = c.getBoundingClientRect();
      if (cr.width > 0 && cr.width < 64 && cr.height < 64) {
        const d = Math.hypot(cr.right - r.right, cr.top - r.top);
        if (d < bestD && d < 90) { bestD = d; best = c; }
      }
    }
    close = best;
  }
  let closeSel = '';
  if (close) { close.setAttribute('data-ovl-close','1'); closeSel = '[data-ovl-close]'; }
  return {present:true, closeSel, z:cands[0].z, frac:Math.round(cands[0].frac*100)/100};
}
"""

_OVERLAY_HIDE_JS = r"""
() => {
  let n = 0;
  const vw = innerWidth, vh = innerHeight;
  for (const el of document.querySelectorAll('[data-ovl]')) {
    el.style.setProperty('display','none','important'); n++;
  }
  for (const el of document.querySelectorAll('body *')) {   // also kill full-screen backdrops
    const cs = getComputedStyle(el);
    if (cs.position !== 'fixed') continue;
    const r = el.getBoundingClientRect();
    if (r.width >= vw*0.9 && r.height >= vh*0.9 && (parseInt(cs.zIndex)||0) >= 50) {
      el.style.setProperty('display','none','important'); n++;
    }
  }
  document.documentElement.style.overflow = ''; document.body.style.overflow = '';   // restore scroll
  return n;
}
"""


def vision_escalation_reason(history: list[str], page_hashes: list[str],
                             window: int = 3) -> str:
    """P3 auto-vision escalation trigger — a PURE function so the stuck
    heuristic is unit-testable. Returns a human-readable reason when the run
    looks stuck, '' otherwise. Stuck means either:
      (a) the last `window` planner turns made no progress — every entry is a
          failed action (":fail"), a noop re-plan, or a rejected give_up; or
      (b) the page looked identical for `window` consecutive steps
          (window+1 equal observation hashes).
    Escalation only upgrades PERCEPTION (a Set-of-Marks screenshot for a
    multimodal model); actions stay schema-validated and the verifier stays
    the only judge."""
    def _no_progress(h: str) -> bool:
        h = h.split(" | env:")[0]     # P0-4 appends an env note after the status
        return h.startswith(("noop(", "give_up_rejected(")) or h.endswith(":fail")
    if len(history) >= window and all(_no_progress(h) for h in history[-window:]):
        return f"連續 {window} 步無進展"
    if len(page_hashes) >= window + 1 and len(set(page_hashes[-(window + 1):])) == 1:
        return f"頁面連續 {window} 步未變化"
    return ""


# P0-1 stagnation ladder: step thresholds at which the nudge tone escalates,
# and how many consecutive no-progress turns trigger a full REPLAN prompt.
_NUDGE_LADDER = (5, 8, 12)
_REPLAN_FAILS = 3

# P1-15 long-horizon step budgets: the historical default stays 8 (existing
# sets unchanged), but a task definition can now size its own loop — an
# explicit `max_steps` field, or a `difficulty` tier — and an explicit
# override (CLI flag) beats both. Imported medium/hard sets (P1-1
# reference_length layering) are no longer doomed by a one-size-fits-all 8.
# The P0-6 Budget caps (steps/tokens/USD/wall-clock) remain the HARD stop:
# this only sizes the loop, it never loosens a Budget dimension.
DEFAULT_MAX_STEPS = 8

# Open-ended verdict evidence: the final page's text is re-read at this raised
# (but bounded) budget so key-point quotes have something to ground against —
# the observer's 5k obs cap was too truncated to quote from (live 18/18 abstain).
_OPEN_ENDED_FINAL_TEXT_CAP = 12_000
STEP_BUDGET_BY_DIFFICULTY = {"easy": 8, "medium": 15, "hard": 25}


def resolve_max_steps(task: dict | None = None,
                      override: int | None = None) -> int:
    """Resolve the step budget for one task. Precedence: explicit override
    (CLI flag) > task['max_steps'] field > task['difficulty'] tier >
    DEFAULT_MAX_STEPS. Malformed values (non-positive, unknown tier) fall
    through to the next source so a bad field can never zero the run."""
    if override is not None and override > 0:
        return override
    if task:
        ms = task.get("max_steps")
        if isinstance(ms, int) and not isinstance(ms, bool) and ms > 0:
            return ms
        tier = STEP_BUDGET_BY_DIFFICULTY.get(str(task.get("difficulty", "")).lower())
        if tier:
            return tier
    return DEFAULT_MAX_STEPS


def _no_progress_entry(h: str) -> bool:
    """A history entry that advanced nothing: a failed action, a planner noop,
    or a rejected give_up/done. The P0-4 env note (' | env: …') is stripped
    first so the status token stays the thing being tested."""
    h = h.split(" | env:")[0]
    return (h.startswith(("noop(", "give_up_rejected(", "done_rejected("))
            or h.endswith(":fail"))


# BUCKET 3a give_up classification: a give_up naming a HARD block (CAPTCHA /
# login / paywall / HTTP 403) or a genuine impossibility is honoured at once —
# a fast, honest refusal (and the impossible-task path stays fast). A soft
# "can't find it / no candidate" give_up matches nothing here and is gated by
# remaining budget so a hard/multi-step task is not abandoned 2-3 steps in.
_HARD_GIVEUP_CUES = (
    "captcha", "recaptcha", "unusual traffic", "are you a robot", "robot check",
    "login", "log in", "sign in", "sign-in", "signin", "authenticat",
    "account required", "requires an account", "paywall", "subscription required",
    "subscribe to", "payment", "requires payment", "purchase required",
    "402", "403", "forbidden", "access denied", "blocked by",
    "impossible", "not possible", "cannot be completed", "cannot be done",
    "does not exist", "doesn't exist", "no such", "not available anywhere",
)


def _hard_giveup(reason: str) -> bool:
    """True when a give_up reason names a genuine dead-end (a hard block or an
    impossibility), so it is honoured immediately. A soft give_up ('can't find
    the button', 'no candidate advances the task') matches nothing here and is
    gated by remaining step budget."""
    r = (reason or "").lower()
    return any(cue in r for cue in _HARD_GIVEUP_CUES)


def stagnation_nudge(planner_steps: list, page_hashes: list[str],
                     history: list[str], step_i: int, max_steps: int,
                     plan_steps: list[str] | None = None) -> str:
    """P0-1 in-loop stagnation detection (BU ActionLoopDetector / Magentic-One
    dual-ledger / SV deterministic loop detector / BU consecutive_failures →
    REPLAN) — a PURE function so the trigger logic is unit-testable. Returns
    the text to inject into the planner's history ('' = keep quiet). Two
    triggers, strongest first:
      (a) REPLAN — the last `_REPLAN_FAILS` turns all made no progress:
          restate the facts (planned route, remaining budget) and demand a
          genuinely different action.
      (b) loop — repetition_report over the recent planner steps (until now a
          post-run observation) flags a repeated move/cycle, or the page
          fingerprint sat unchanged for 3 observations: nudge with a tone that
          escalates along the 5/8/12 step ladder. Below the first rung the
          agent is left alone — early repetition (scrolling, a retry after
          dismissing a modal) is often legitimate.
    Prompt-only: the action space stays schema-validated and the verifier
    stays the only judge."""
    remaining = max_steps - step_i
    if (len(history) >= _REPLAN_FAILS
            and all(_no_progress_entry(h) for h in history[-_REPLAN_FAILS:])):
        route = f" Planned route: {'; '.join(plan_steps)}." if plan_steps else ""
        return (f"REPLAN({_REPLAN_FAILS} consecutive turns made no progress; "
                f"{remaining} steps left):{route} State what is already "
                "achieved, then choose a genuinely different action — another "
                "element, goto a visible href, dismiss an overlay, or scroll "
                "to reveal the target.")
    if step_i < _NUDGE_LADDER[0]:
        return ""
    # BUCKET 3b: widen the repetition window (catch an A-B-A-B wander cycle a
    # 6-step window misses) and trip the frozen-page detector one observation
    # earlier (3 identical hashes = 2 unchanged transitions) so a silent-failure
    # wander is caught sooner.
    rep = repetition_report(planner_steps[-8:])
    stalled = len(page_hashes) >= 3 and len(set(page_hashes[-3:])) == 1
    if not (rep["loop_detected"] or stalled):
        return ""
    why = ("page unchanged" if stalled
           else f"same move repeated {max(rep['max_consecutive_repeat'], rep['loop_repeats'])}x")
    # BUCKET 3b: restate the current subgoal so the nudge DIRECTS a strategy
    # switch back toward the planned route, not merely escalates tone.
    aim = f" Refocus on the plan: {'; '.join(plan_steps)}." if plan_steps else ""
    if step_i >= _NUDGE_LADDER[2]:
        return (f"NUDGE-FINAL({why}; only {remaining} steps left): you ARE "
                "stuck. Abandon this approach NOW — take the most direct "
                "different route (goto a target URL / extract what is already "
                "on screen), or give_up honestly." + aim)
    if step_i >= _NUDGE_LADDER[1]:
        return (f"NUDGE-STRONG({why}): this approach is not working. Switch "
                "strategy THIS turn: a different element, press instead of "
                "click, goto a seen href, or scroll to new content." + aim)
    return (f"NUDGE({why}): you may be looping — STOP repeating the last move "
            "and switch approach: a different element, press instead of click, "
            "goto a seen href, or scroll to reveal the target." + aim)


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
    # P0-7 MatchLevel telemetry: which cascade level resolved this step's
    # target — script / exact / stable / purpose / none ('' = not a resolution)
    match_level: str = ""
    # P0-5 per-step obs persistence (SK action-history evidence / SG post-step
    # probe): the observation each planner decision was made against, kept in
    # the trace instead of being consumed and dropped — the per-step evidence
    # the false_success detector and a second judge need to audit a run.
    obs_hash: str = ""          # sha256(url|visible_text) at decision time
    obs_excerpt: str = ""       # first lines of visible text
    obs_candidates: str = ""    # compact summary of the candidate elements


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
    # P0-6 cost accounting (BG cache-aware cost accounting): the accumulated
    # planner LLM spend used to be summed in run_agentic and then dropped —
    # eval rows carried zero cost. It now lands here, next to the verdict, so
    # cost-per-success can be computed in the same artifact.
    llm_cost_usd: float = 0.0
    llm_tokens: int = 0             # input+output tokens across planner calls
    # phase timings (ms): where the wall-clock went — planner_ms (LLM calls),
    # action_ms (executor), verify_ms (per-step rescan + contract verdicts)
    phase_timings: dict[str, float] = field(default_factory=dict)
    # Answer channel (P2): text the agent DELIVERED via extract_text actions,
    # concatenated in extraction order. This is page evidence, not the LLM's
    # self-report — the verifier's answer_matches condition judges it, and the
    # UI shows it so an answer-type task actually hands the answer to the user.
    answer: str = ""
    # T1-4 observation-layer metric: pre/post persistent-state diff. Empty until a
    # runner captures snapshots around the run; on a real site it stays 'unknown'.
    side_effects: dict[str, Any] = field(default_factory=dict)
    # P0-10 cache telemetry: replay hits/aborts (agent mode) and script-mode
    # shadow-check counters — the raw numbers the cost report derives the
    # cache FP-rate from. Empty when no cache was in play.
    cache_stats: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        # P0-7 MatchLevel hit rates: how each step's target was resolved,
        # counted per cascade level — the telemetry that shows whether drift
        # is being absorbed deterministically (hash) or expensively (purpose).
        match_levels: dict[str, int] = {}
        for s in self.steps:
            if s.match_level:
                match_levels[s.match_level] = match_levels.get(s.match_level, 0) + 1
        # P0-10 cache FP-rate: shadow divergences over shadow checks — the
        # "does the cache lie" number, measured instead of assumed.
        cache = dict(self.cache_stats)
        if cache.get("shadow_checks"):
            cache["fp_rate"] = round(
                cache.get("shadow_divergence", 0) / cache["shadow_checks"], 3)
        return {
            "task_id": self.task_id, "site": self.site, "status": self.status,
            "confidence": round(self.confidence, 3),
            "answer": self.answer,
            "repairs": self.repairs, "total_latency_ms": round(self.total_latency_ms, 1),
            "llm_cost_usd": round(self.llm_cost_usd, 6),
            "llm_tokens": self.llm_tokens,
            "phase_timings_ms": {k: round(v, 1) for k, v in self.phase_timings.items()},
            # T1-4 repetitiveness: derived purely from the recorded steps, so it is
            # computed here (observation only, never influences agent behaviour).
            "repetition": repetition_report(self.steps),
            "match_levels": match_levels,
            "cache": cache,
            "side_effects": self.side_effects,
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
                 "match_level": s.match_level,
                 "screenshot": s.screenshot, "obs_hash": s.obs_hash,
                 "obs_excerpt": s.obs_excerpt, "obs_candidates": s.obs_candidates}
                for s in self.steps
            ],
        }


class BrowserAgent:
    def __init__(self, page, memory: MemoryStore, site: str, task_type: str,
                 artifact_dir: Path | str | None = None,
                 evidence_store: EvidenceStore | None = None,
                 downloads_dir: Path | str | None = None,
                 replay_cache: ReplayCache | None = None) -> None:
        self.page = page
        self.downloads_dir = Path(downloads_dir) if downloads_dir else None
        if self.downloads_dir:
            self.downloads_dir.mkdir(parents=True, exist_ok=True)
        self.executor = ActionExecutor(page, downloads_dir=self.downloads_dir)
        self.observer = PageObserver(page)
        self.memory = memory
        self.site = site
        self.task_type = task_type
        # P0-10: the agent-mode replay cache lives next to the selector memory
        # (same write-back pattern), so the two self-maintenance stores travel
        # together; tests may inject their own instance.
        self.replay = replay_cache or ReplayCache(
            self.memory.path.with_name("replay_cache.json"))
        # P0-10 per-run cache telemetry (reset at each run entry point)
        self.cache_stats: dict[str, int] = {}
        self.evidence_store = evidence_store
        self.artifact_dir = Path(artifact_dir) if artifact_dir else None
        if self.artifact_dir:
            self.artifact_dir.mkdir(parents=True, exist_ok=True)
        # Vision channel (SoM screenshots for a multimodal model):
        #   AGENT_VISION=1  -> always on (every turn, costs image tokens)
        #   AGENT_VISION=0  -> never (operator declares a non-vision backend)
        #   unset (default) -> AUTO: off until the run looks stuck, then
        #                      escalate (P3) if the planner supports vision.
        import os as _os
        _v = _os.environ.get("AGENT_VISION", "")
        self._vision = _v == "1"
        self._vision_auto = _v != "0"

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
            latency_ms=run.total_latency_ms, cost_usd=run.llm_cost_usd,
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

    def _dismiss_overlay(self, trace: list[StepTrace]) -> bool:
        """General, class-agnostic popup handling: detect a blocking overlay by
        geometry, click its close control, else press Escape, else neutralise
        it in the DOM. Works on any site because it never depends on a known
        popup class. Returns True if it acted."""
        try:
            info = self.page.evaluate(_OVERLAY_DETECT_JS)
        except Exception:  # noqa: BLE001
            return False
        if not info or not info.get("present"):
            return False
        acted = False
        if info.get("closeSel"):
            try:
                self.page.locator(info["closeSel"]).first.click(timeout=1500)
                acted = True
            except Exception:  # noqa: BLE001
                pass
        if not acted:
            try:
                self.page.keyboard.press("Escape")
            except Exception:  # noqa: BLE001
                pass
        # if the overlay is still blocking, remove it outright so the task can proceed
        hidden = 0
        try:
            still = self.page.evaluate(_OVERLAY_DETECT_JS)
            if still and still.get("present"):
                hidden = self.page.evaluate(_OVERLAY_HIDE_JS)
        except Exception:  # noqa: BLE001
            pass
        trace.append(StepTrace(
            step="dismiss_overlay", action="click" if acted else ("hide" if hidden else "escape"),
            ok=True, mode="repair", diagnosis="modal_blocking",
            detail=f"cleared blocking overlay (z={info.get('z')}, frac={info.get('frac')}, hidden={hidden})",
            screenshot=self._screenshot("overlay-cleared")))
        return True

    def _dismiss_modal_if_present(self, trace: list[StepTrace]) -> None:
        obs = self.observer.observe()
        if not obs.modal_present:
            return
        # find an accept/dismiss/close control among candidates
        cues = ("accept", "agree", "dismiss", "close", "ok", "got it", "no thanks",
                "not now", "later", "skip", "continue", "×", "✕", "x")
        for c in obs.candidates:
            blob = f"{c.id} {c.aria_label} {c.text}".lower().strip()
            if any(w in blob for w in cues) and len(blob) < 40:
                out = self.executor.execute(ClickAction(
                    target=ElementTarget(selector=c.css(), selector_type="css")))
                if out.ok:
                    trace.append(StepTrace(step="dismiss_modal", action="click", ok=True,
                                           mode="repair", detail=f"dismissed blocking modal via '{blob[:20]}'",
                                           diagnosis="modal_blocking", selector_used=c.css(),
                                           latency_ms=out.latency_ms,
                                           screenshot=self._screenshot("modal-dismissed")))
                    return
        # universal fallback: most modals close on Escape
        try:
            self.page.keyboard.press("Escape")
            trace.append(StepTrace(step="dismiss_modal", action="press", ok=True, mode="repair",
                                   detail="pressed Escape to dismiss modal", diagnosis="modal_blocking"))
        except Exception:  # noqa: BLE001
            pass

    def _element_hashes(self, selector: str) -> tuple[str, str]:
        """P0-7: (exact, stable) structural hashes of the FIRST element the
        selector currently binds to — computed from the live DOM so a working
        selector's identity can be remembered. ('', '') when unresolvable."""
        try:
            fields = self.page.evaluate(_ELEMENT_FIELDS_JS, selector)
        except Exception:  # noqa: BLE001 — non-Playwright fakes / dead page
            return "", ""
        return structural_hashes(fields) if fields else ("", "")

    def _bump(self, key: str) -> None:
        self.cache_stats[key] = self.cache_stats.get(key, 0) + 1

    # P0-10 shadow-mode sampling: every Nth script-mode cache hit is
    # re-derived from scratch and compared (CACHE_SHADOW_EVERY overrides;
    # 0 disables sampling — dom_fingerprint drift still forces a check).
    _SHADOW_EVERY = 4

    def _shadow_check(self, step: Step, remembered: str, hit_hash: str,
                      forced: bool, trace: list[StepTrace]) -> None:
        """P0-10 shadow-mode cache verification (SV shadow-mode / WC
        scheduled-replay failure report): a script-mode cache hit is sampled
        and the SAME target re-derived by purpose scoring over a fresh
        observation; the two answers are compared by element identity (P0-7
        hash), not selector spelling. A divergence never changes the run —
        the verifier stays the only judge — it is COUNTED, so the cache's
        FP-rate is a measured number in the eval/cost artifact."""
        import os as _os
        self._bump("script_cache_hits")
        hits = self.cache_stats["script_cache_hits"]
        try:
            every = int(_os.environ.get("CACHE_SHADOW_EVERY", self._SHADOW_EVERY))
        except ValueError:
            every = self._SHADOW_EVERY
        if not (forced or (every > 0 and (hits - 1) % every == 0)):
            return
        self._bump("shadow_checks")
        obs = self.observer.observe()
        rr = repair_target(step.purpose, obs, want_value=step.value)
        diverged = False
        if rr.ok and rr.new_target is not None:
            detail = f"cache {remembered!r} vs purpose choice {rr.durable_selector!r}"
            if rr.durable_selector != remembered:
                # same element under two selector spellings is agreement —
                # only a different ELEMENT is a divergence
                shadow_hx, _ = self._element_hashes(rr.new_target.selector)
                diverged = bool(shadow_hx and hit_hash) and shadow_hx != hit_hash
        else:
            detail = f"cache {remembered!r}: purpose scorer found no candidate"
        if forced:
            detail = "dom_fingerprint drift forced the check — " + detail
        if diverged:
            self._bump("shadow_divergence")
        trace.append(StepTrace(
            step="shadow_check", action="compare", ok=not diverged, mode="script",
            diagnosis="cache_divergence" if diverged else "",
            detail=detail, selector_used=remembered))

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
            # P0-10 dom_fingerprint read-back: the fingerprint banked at the
            # last verified success, read BEFORE record() overwrites it —
            # drift since then makes this cache hit suspect (forced shadow).
            prior_fp = self.memory.fingerprint(
                self.site, self.task_type, step.purpose) if remembered else ""
            cur_fp = sha256_text(self.page.content())[:16]
            # P0-7: hash the element the working selector bound to, so its
            # identity is remembered and drift can be rebound deterministically
            hx, hs = self._element_hashes(selector)
            self.memory.record(self.site, self.task_type, step.purpose, selector,
                               self._now(), success=True,
                               dom_fingerprint=cur_fp,
                               element_hash=hx, element_hash_stable=hs)
            trace.append(StepTrace(step=step.purpose, action=step.kind, ok=True, mode="script",
                                   detail=out.detail, selector_used=selector,
                                   latency_ms=out.latency_ms, match_level="script",
                                   screenshot=self._screenshot(f"{step.purpose}-ok")))
            if remembered:
                self._shadow_check(step, remembered, hx,
                                   forced=bool(prior_fp) and prior_fp != cur_fp,
                                   trace=trace)
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
        # selector_not_found / multiple_candidates / wrong_page: P0-7 hash-match
        # fast path FIRST (BU cascading locator / SK cleaned-JSON SHA256
        # rebind) — the remembered element's structural hash against the
        # current candidates; exactly one EXACT (then STABLE) hit rebinds
        # deterministically, 0 or >1 falls back to purpose scoring below.
        known_exact, known_stable = self.memory.hashes(self.site, self.task_type, step.purpose)
        cand, level = rebind_by_hash(known_exact, known_stable, obs)
        if cand is not None:
            action_hb = self._build_action(step, ElementTarget(
                selector=cand.aid_selector(), selector_type="css",
                description=f"hash-rebound {step.purpose}"))
            out_hb = self.executor.execute(action_hb)
            if out_hb.ok:
                durable = cand.css()
                hx, hs = structural_hashes(cand)
                repair = RepairEvent(
                    timestamp=self._now(), failed_selector=selector,
                    failure_type=diag.failure_type, candidates_considered=[],
                    chosen_selector=durable,
                    choice_reason=f"hash-{level} rebind: exactly one structural match",
                    verified=True, evidence_run_id="")
                self.memory.record(self.site, self.task_type, step.purpose, durable,
                                   self._now(), success=True,
                                   dom_fingerprint=sha256_text(self.page.content())[:16],
                                   repair=repair, element_hash=hx, element_hash_stable=hs)
                trace.append(StepTrace(step=step.purpose, action=step.kind, ok=True, mode="repair",
                                       diagnosis=diag.failure_type,
                                       detail=f"hash-{level} rebind (deterministic, no scoring)",
                                       repair_chosen=repair.choice_reason,
                                       selector_used=durable, match_level=level,
                                       latency_ms=out_hb.latency_ms,
                                       screenshot=self._screenshot(f"{step.purpose}-hash-rebound")))
                return out_hb
            # the rebound element did not act — recorded, then purpose scoring
            trace.append(StepTrace(step=step.purpose, action=step.kind, ok=False, mode="repair",
                                   diagnosis=diag.failure_type, match_level=level,
                                   detail=f"hash-{level} rebind matched but the action failed"
                                          " -> purpose scoring"))
        # a11y-tree purpose scoring (the cascade's last functional level)
        rr = repair_target(step.purpose, obs, want_value=step.value)
        considered = rr.considered
        if not rr.ok or rr.new_target is None:
            trace.append(StepTrace(step=step.purpose, action=step.kind, ok=False, mode="repair",
                                   diagnosis=diag.failure_type, detail="no viable candidate",
                                   repair_considered=considered, match_level="none",
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
        # P0-7: a verified purpose repair also banks the element's identity,
        # so the NEXT drift can take the deterministic hash path
        hx, hs = self._element_hashes(rr.new_target.selector) if out2.ok else ("", "")
        self.memory.record(self.site, self.task_type, step.purpose, durable,
                           self._now(), success=out2.ok,
                           dom_fingerprint=sha256_text(self.page.content())[:16], repair=repair,
                           element_hash=hx, element_hash_stable=hs)
        trace.append(StepTrace(step=step.purpose, action=step.kind, ok=out2.ok, mode="repair",
                               diagnosis=diag.failure_type, detail=diag.detail,
                               repair_considered=considered, repair_chosen=rr.chosen_reason,
                               selector_used=durable, latency_ms=out2.latency_ms,
                               match_level="purpose",
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
                    max_steps: int = DEFAULT_MAX_STEPS, on_step=None, plan_steps=None,
                    budget: Budget | None = None) -> TaskRun:
        """Agent Mode (SPEC 6.2): an LLM planner chooses actions from the
        controlled schema; each is capability-screened and executed; the
        verifier — not the LLM — decides the outcome. Falls back cleanly if the
        planner has no credentials. `on_step(text)` is called live per step.
        `plan_steps` is the preflight dynamic-workflow route; it is fed back to
        the planner each turn so a hard, multi-step task follows (and re-plans
        against) its own roadmap instead of deciding each step blind."""
        plan_steps = plan_steps or []
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
        llm_tokens = 0
        # P0-6 phase timings: where the wall-clock goes, accumulated per phase
        phase = {"planner_ms": 0.0, "action_ms": 0.0, "verify_ms": 0.0}
        give_ups = 0
        dones = 0    # P0-3: premature-done rejections spent (front gate fires once)
        # Answer channel (P2): every successful extract_text APPENDS here — the
        # observed INTC failure was extract results dropped on the floor while
        # extracted only ever carried __download__, so an answer-type task had
        # no delivery channel and its verdict rested on premature landmarks.
        answers: list[str] = []

        def _extracted() -> dict[str, str]:
            ex: dict[str, str] = {}
            if answers:
                ex["answer"] = "\n".join(answers)
            if self.executor.last_download_path:
                ex["__download__"] = self.executor.last_download_path
            return ex
        # P0-10 cross-run replay: a verified previous run of the SAME task
        # banked its successful actions — replay them before paying for the
        # planner. Every successful action of THIS run is re-recorded, so a
        # passing run refreshes the entry (write-back on verifier pass only).
        self.cache_stats = {}
        replay_steps = self.replay.lookup(self.site, self.task_type,
                                          contract.natural_language_task)
        replay_i = 0
        recorded: list[ReplayStep] = []   # this run's successful actions
        replay_bankable = True            # False once an un-replayable action ran
        if replay_steps:
            _emit(f"⚡ 快取:上次驗證成功的 {len(replay_steps)} 步先重放,失效才問 LLM")
        self._dismiss_overlay(trace)
        # Baseline-subtraction (premature-landmark kill): a condition already
        # true on the OPENING page proves nothing about completion — e.g. the
        # INTC failure where text_visible:intc (a task-sentence token) was true
        # on the first search page → false PASS. Drop t0-true conditions here;
        # if none remain, the run continues on the open-ended path (honest
        # unknown + full trace for human review), never a vacuous pass.
        contract, baseline_dropped = subtract_baseline(contract, self.observer.observe())
        if baseline_dropped:
            trace.append(StepTrace(
                step="baseline", action="subtract", ok=True, mode="agent",
                detail="開場即成立、已剔除的條件(不能作為完成證據):" + "; ".join(baseline_dropped)))
            _emit(f"🚫 條件在開場就成立(vacuous),已剔除:{'; '.join(baseline_dropped)}")
        verdict = VerifierResult(status="unknown", reason="no steps taken")
        # P3 auto-vision: starts in the env-selected mode; can only escalate
        # (off -> on) when the run is stuck AND the planner is multimodal AND
        # there is an artifact dir to write the SoM screenshot into. Planners
        # without supports_vision (mock/scripted) never escalate.
        vision_on = self._vision
        _sv = getattr(planner, "supports_vision", None)
        vision_capable = bool(_sv and callable(_sv) and _sv()) and self.artifact_dir is not None
        page_hashes: list[str] = []
        prev_obs = None      # P0-4: the previous observation, for the env diff
        # P0-5 latch ledger (WC key-node semantics, arXiv:2406.12373):
        # 'type:value' -> step at which the condition was FIRST observed
        # satisfied. Every verdict below merges it, so evidence that genuinely
        # held mid-run survives a navigation away (kills the false negative);
        # revocable conditions never latch (verify_contract skips them).
        latched: dict[str, int] = {}

        def _stamp_obs(st: StepTrace) -> StepTrace:
            """P0-5 per-step obs persistence: attach the observation THIS
            planner decision was made against, so the trace carries auditable
            per-step evidence instead of consuming and dropping it."""
            st.obs_hash = page_hashes[-1] if page_hashes else ""
            st.obs_excerpt = obs.visible_text[:200]
            st.obs_candidates = "; ".join(
                f"{c.tag}[{c.id or c.name or c.aria_label or c.text[:24]}]"
                for c in obs.candidates[:8])
            return st
        _emit(f"🧠 想任務:{contract.natural_language_task}")
        for step_i in range(max_steps):
            # P0-6 hard budget (SK 四維硬預算), checked at the loop HEAD so an
            # over-budget run stops BEFORE spending another LLM call or action;
            # the final verdict below still comes from the verifier, never from
            # the budget stop itself.
            if budget is not None:
                over = budget.exceeded(steps=step_i, tokens=llm_tokens,
                                       usd=llm_cost,
                                       wall_clock_s=time.perf_counter() - t0)
                if over:
                    trace.append(StepTrace(step="budget", action="stop", ok=False,
                                           mode="agent",
                                           detail=f"budget exceeded: {over}"))
                    _emit(f"⛔ 預算用盡:{over}")
                    break
            # A popup/interstitial can appear AFTER any navigation on ANY site
            # (this is the "跳出一個頁面 agent 點不掉" failure). Detect it by
            # geometry — not a class allow-list — and clear it every step, so the
            # next action is never eaten by an overlay the planner can't see.
            if self._dismiss_overlay(trace):
                _emit("🧹 偵測到彈出視窗,已清除")
                self.page.wait_for_timeout(200)
            obs = self.observer.observe()
            # P0-4 env-change evidence (AE change observation as precedent, done
            # as an identity-key diff of consecutive observations — no 100ms
            # race, catches disappearances too): mark elements that APPEARED
            # since the last turn ('*' in the planner's candidate list) and
            # append what the last action actually changed to its history
            # entry. An empty diff after a click/press that reported ok is the
            # silent-failure signal — recorded in that step's diagnosis.
            env = diff_observations(prev_obs, obs)
            prev_obs = obs
            if env and history and history[-1].endswith((":ok", ":fail")):
                if env == "page unchanged" and history[-1].startswith(("click:ok", "press:ok")):
                    env += " — the action may have silently failed"
                    for s in reversed(trace):
                        if s.step == "planner" and s.action in ("click", "press"):
                            s.diagnosis = s.diagnosis or "silent_failure_suspected"
                            break
                history[-1] += f" | env: {env}"
            page_hashes.append(sha256_text(obs.url + "|" + obs.visible_text))
            # P0-5 latch: rescan every not-yet-banked success condition against
            # THIS observation (WC per-step rescan, score=max(old,new)); one
            # observed pass is banked permanently with its step number.
            _tv = time.perf_counter()
            for key, st in check_conditions(contract, obs, _extracted()).items():
                if st == "pass" and key not in latched:
                    latched[key] = step_i
            # the loop verdict sees the SAME evidence surface as the final one
            # (answer + download + latch ledger), so a satisfied deliverable
            # ends the run here instead of waiting for the model to claim done
            verdict = verify_contract(contract, obs, _extracted(), latched=latched)
            phase["verify_ms"] += (time.perf_counter() - _tv) * 1000
            if verdict.status == "pass":
                break
            # P0-10 replay fast path: execute the next banked action directly —
            # no LLM call. Any resolution/execution failure abandons the cache
            # for this run and invalidates the entry (WC scheduled-replay
            # failure loop); the SAME turn then goes to the planner, and the
            # verifier still owns the verdict either way.
            if replay_i < len(replay_steps):
                rs = replay_steps[replay_i]
                r_action = action_from_step(rs, obs)
                r_out = None
                if r_action is not None and screen_action(r_action).allowed:
                    r_out = self.executor.execute(r_action)
                    phase["action_ms"] += r_out.latency_ms
                if r_out is not None and r_out.ok:
                    replay_i += 1
                    self._bump("replay_hits")   # one planner LLM call saved
                    if r_out.followed_url:
                        self.page = self.executor.page
                        self.observer.page = self.page
                    history.append(f"{r_action.type}:ok")
                    if r_action.type == "extract_text" and r_out.extracted_text:
                        answers.append(r_out.extracted_text.strip())
                    recorded.append(rs)
                    trace.append(_stamp_obs(StepTrace(
                        step="replay", action=r_action.type, ok=True, mode="cache",
                        detail=f"replayed from cache: {rs.label or rs.action}",
                        selector_used=getattr(getattr(r_action, "target", None),
                                              "selector", "") or "",
                        latency_ms=r_out.latency_ms)))
                    _emit(f"⚡ 重放快取步驟:{r_action.type}({rs.label or rs.selector or rs.value})")
                    if r_action.type in ("goto", "click", "press"):
                        try:
                            self.page.wait_for_load_state("networkidle", timeout=4000)
                        except Exception:  # noqa: BLE001
                            pass
                    self.page.wait_for_timeout(300)
                    continue
                # divergence: the cached step no longer matches this page
                self._bump("replay_aborted")
                self.replay.invalidate(self.site, self.task_type,
                                       contract.natural_language_task)
                self.replay.save()
                replay_steps = []
                history.append(f"replay_abort({rs.action})")
                trace.append(StepTrace(
                    step="replay", action=rs.action, ok=False, mode="cache",
                    diagnosis="cache_divergence",
                    detail="cached step no longer resolves/executes — entry "
                           "invalidated, planner takes over"))
                _emit("⚡ 快取失效(頁面已漂移),改問 LLM")
            # P3 auto-vision escalation: when the text channel is going nowhere
            # (repeated failures/noops or a page that never changes), switch the
            # SoM screenshot on for the REST of the run. Perception only — the
            # action space and the verifier are untouched.
            if not vision_on and self._vision_auto and vision_capable:
                why = vision_escalation_reason(history, page_hashes)
                if why:
                    vision_on = True
                    trace.append(StepTrace(
                        step="vision", action="escalate", ok=True, mode="agent",
                        detail=f"偵測到卡住({why}),自動切換視覺模式:"
                               "後續每步附 Set-of-Marks 截圖"))
                    _emit(f"🔍 切換視覺模式({why})")
            # P0-1 in-loop stagnation: repetition_report + the page-hash
            # counter now feed a MID-RUN nudge (tone escalating along the
            # 5/8/12 ladder) or, on consecutive no-progress turns, a REPLAN
            # prompt restating the route and remaining budget. Injected as a
            # transient extra history entry so it lands in ACTIONS SO FAR
            # without touching the planner signature.
            nudge = stagnation_nudge([s for s in trace if s.step == "planner"],
                                     page_hashes, history, step_i, max_steps,
                                     plan_steps)
            if nudge:
                trace.append(StepTrace(step="stagnation", action="nudge", ok=True,
                                       mode="agent", detail=nudge))
                _emit(f"🧭 {nudge}")
            _emit("💭 看畫面、決定下一步…")
            # Vision channel: render a Set-of-Marks screenshot so a multimodal
            # model can SEE the page and ground a coordinate click. On when
            # AGENT_VISION=1, or after auto-escalation; needs an artifact dir.
            image_path = None
            if vision_on and self.artifact_dir:
                somp = self.artifact_dir / f"som-{len(trace)}.png"
                if set_of_marks(self.page, str(somp)):
                    image_path = str(somp)
            _tp = time.perf_counter()
            decision = planner.next_action(
                contract.natural_language_task,
                [f"{c.type}:{c.value}" for c in contract.success_conditions], obs,
                history + [nudge] if nudge else history,
                plan_steps=plan_steps, image_path=image_path)
            phase["planner_ms"] += (time.perf_counter() - _tp) * 1000
            if decision.llm is not None:
                llm_cost += decision.llm.cost_usd
                llm_tokens += decision.llm.input_tokens + decision.llm.output_tokens
            # a malformed/unusable action is recoverable — give the model another
            # turn instead of ending the whole run (the old give_up was too brittle)
            if decision.kind == "noop":
                history.append(f"noop({decision.reason})")
                trace.append(_stamp_obs(StepTrace(step="planner", action="noop", ok=False,
                                                  mode="agent", detail=decision.reason)))
                _emit(f"↻ 重試:{decision.reason}")
                continue
            # BUCKET 3a early-give_up gate: honour a give_up at once only when it
            # names a HARD block / impossibility (a fast, honest refusal — the
            # impossible-task path stays fast). Otherwise, while AMPLE step
            # budget remains (< ~40%) OR it is the first give_up, reject it with
            # a concrete strategy nudge — the observed failure was quitting a
            # hard/multi-step task 2-3 steps in with the budget barely touched.
            # A real dead-end must survive a genuinely different approach first;
            # past the budget floor an already-nudged give_up is honoured.
            if decision.kind == "give_up":
                ample = step_i < max(2, int(max_steps * 0.4))
                if not _hard_giveup(decision.reason) and (ample or give_ups < 1):
                    give_ups += 1
                    history.append(f"give_up_rejected({decision.reason})")
                    trace.append(_stamp_obs(StepTrace(step="planner", action="give_up_rejected",
                                                      ok=False, mode="agent", detail=decision.reason)))
                    _emit("↻ 先別放棄——換一個具體做法再試(直接 goto 目標檔案的 href / 用 download / 關掉彈窗)")
                    self.page.wait_for_timeout(200)
                    continue
            # P0-3 done-rejection front gate (BU pre_done_verification, SV 終止
            # 雙閘門): the loop verdict above already judged THIS state — a
            # "done" while it is not pass is finishing on expectation and
            # throws away the remaining steps. Reject one done with the
            # verifier's concrete gap so those steps go to making the
            # conditions true; a second done (or one on the last step) is
            # honoured — the final verdict still comes from verify_contract,
            # never from the claim.
            if (decision.kind == "done" and dones < 1 and verdict.status != "pass"
                    and step_i < max_steps - 1):
                dones += 1
                missing = "; ".join(verdict.missing_evidence) or verdict.reason
                history.append(f"done_rejected(not verified yet: {missing})")
                trace.append(_stamp_obs(StepTrace(step="planner", action="done_rejected", ok=False,
                                                  mode="agent",
                                                  detail=f"{decision.reason} → 驗證未通過:{missing}")))
                _emit(f"↻ done 被駁回——成功條件尚未全部成立({missing}),先讓條件成立再結束")
                self.page.wait_for_timeout(200)
                continue
            if decision.kind in ("done", "give_up"):
                history.append(f"{decision.kind}({decision.reason})")
                trace.append(_stamp_obs(StepTrace(step="planner", action=decision.kind,
                                                  ok=decision.kind == "done",
                                                  mode="agent", detail=decision.reason)))
                _emit(f"✅ {decision.kind}:{decision.reason}")
                break
            action = decision.action
            ascreen = screen_action(action)
            if not ascreen.allowed:
                trace.append(_stamp_obs(StepTrace(step="planner", action=action.type, ok=False,
                                                  mode="agent", diagnosis="capability_refused",
                                                  detail=ascreen.reason)))
                _emit(f"🛑 拒絕(責任邊界):{ascreen.reason}")
                break
            out = self.executor.execute(action)
            phase["action_ms"] += out.latency_ms
            if out.followed_url:
                # F12: the click's effect lives in a NEW tab — repoint the agent
                # and observer so the loop keeps seeing where the journey went.
                self.page = self.executor.page
                self.observer.page = self.page
                trace.append(StepTrace(step="follow_tab", action="switch", ok=True, mode="agent",
                                       detail=f"↪ 跟隨新分頁:{out.followed_url}"))
                _emit(f"↪ 跟隨新分頁:{out.followed_url}")
            history.append(f"{action.type}:{'ok' if out.ok else 'fail'}")
            detail = decision.reason
            if action.type == "download" and out.ok:
                detail = f"下載完成 → {self.executor.last_download_path}"
            if action.type == "extract_text" and out.ok and out.extracted_text:
                # append semantics: a task may need several extractions; all of
                # them together are the delivered answer
                answers.append(out.extracted_text.strip())
                detail = f"📋 擷取內容({len(out.extracted_text)} 字):{out.extracted_text[:120]}"
            # P0-10: a successful action is recorded for the replay cache; one
            # that cannot be replayed faithfully (mouse coordinates) poisons
            # banking for this run rather than banking a broken sequence.
            if out.ok:
                rs_rec = step_from_action(action, obs, label=decision.reason[:80])
                if rs_rec is not None:
                    recorded.append(rs_rec)
                else:
                    replay_bankable = False
            trace.append(_stamp_obs(StepTrace(step="planner", action=action.type, ok=out.ok,
                                              mode="agent",
                                              detail=detail, selector_used=getattr(
                                                  getattr(action, "target", None), "selector", ""),
                                              latency_ms=out.latency_ms,
                                              screenshot=self._screenshot(f"agent-{len(trace)}"))))
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
        extracted = _extracted()
        obs = self.observer.observe()
        # P0-5: the final verdict merges the latch ledger — a condition that
        # genuinely held mid-run counts even if the last page no longer shows
        # it (revocable conditions excluded inside verify_contract). The
        # ledger itself is persisted as a trace entry for audit.
        if latched:
            trace.append(StepTrace(
                step="latch", action="ledger", ok=True, mode="agent",
                detail="satisfied-at-step ledger: "
                       + "; ".join(f"{k} @step{v}" for k, v in latched.items())))
        # Open-ended arming (HOLE A wire-up): a ZERO-condition contract routes
        # through the evidence-grounded WebJudge scorer at VERDICT time — but
        # only when the planner actually has a live LLM client (same client,
        # no second credential path). Offline / mock planners pass None and the
        # behaviour is the unchanged honest unknown. The quotable evidence is
        # the final page's text at a raised, bounded budget (the observer's
        # 5k obs cap is too truncated to quote from) plus the P0-5 per-step
        # obs excerpts, so mid-run evidence a navigation swept away can still
        # ground a quote. Non-empty contracts never reach this path.
        oe_extractor = None
        oe_evidence = None
        if not contract.success_conditions:
            _avail = getattr(getattr(planner, "client", None), "available", None)
            if callable(_avail) and _avail():
                from browser_agent.second_judge import LLMExtractor
                oe_extractor = LLMExtractor(planner.client)
                try:
                    final_text = self.page.inner_text("body")[:_OPEN_ENDED_FINAL_TEXT_CAP]
                except Exception:  # noqa: BLE001 — fall back to the capped obs text
                    final_text = obs.visible_text
                oe_evidence = {
                    "url": obs.url,
                    "visible_text": final_text or obs.visible_text,
                    "step_excerpts": [s.obs_excerpt for s in trace if s.obs_excerpt],
                }
        _tv = time.perf_counter()
        verdict = verify_contract(contract, obs, extracted, latched=latched,
                                  open_ended_extractor=oe_extractor,
                                  open_ended_evidence=oe_evidence)
        phase["verify_ms"] += (time.perf_counter() - _tv) * 1000
        # P0-10 write-back: only a VERIFIER-passed run banks its sequence —
        # the cache can never contain an unverified trajectory.
        if verdict.status == "pass" and recorded and replay_bankable:
            self.replay.bank(self.site, self.task_type,
                             contract.natural_language_task, recorded,
                             timestamp=self._now())
            self.replay.save()
        base = {"pass": 1.0, "unknown": 0.4, "fail": 0.0}[verdict.status]
        run = TaskRun(task_id=task_id, site=self.site, status=verdict.status, verifier=verdict,
                      steps=trace, repairs=0, confidence=base,
                      answer=extracted.get("answer", ""),
                      llm_cost_usd=llm_cost, llm_tokens=llm_tokens,
                      phase_timings=phase, cache_stats=dict(self.cache_stats),
                      total_latency_ms=(time.perf_counter() - t0) * 1000)
        self._emit_evidence(f"agent-{self.site}-{task_id}", task_id, run)
        return run

    def run(self, task_id: str, steps: list[Step], contract: BrowserTaskContract) -> TaskRun:
        t0 = time.perf_counter()
        self.cache_stats = {}      # P0-10 per-run shadow/cache telemetry
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
        # same premature-landmark guard as run_agentic: a t0-true condition is
        # vacuous evidence and must not be able to carry the final verdict
        contract, baseline_dropped = subtract_baseline(contract, self.observer.observe())
        if baseline_dropped:
            trace.append(StepTrace(
                step="baseline", action="subtract", ok=True, mode="script",
                detail="開場即成立、已剔除的條件(不能作為完成證據):" + "; ".join(baseline_dropped)))
        repairs = 0
        for step in steps:
            self._resolve_and_run(step, trace)
            if trace and trace[-1].mode == "repair" and trace[-1].diagnosis:
                repairs += 1
            if self.executor.page is not self.page:
                # F12: a script-mode click opened a new tab and the executor
                # followed it — keep observer/verifier on the same page.
                self.page = self.executor.page
                self.observer.page = self.page
                trace.append(StepTrace(step="follow_tab", action="switch", ok=True, mode="script",
                                       detail=f"↪ 跟隨新分頁:{self.page.url}"))
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
            cache_stats=dict(self.cache_stats),
            total_latency_ms=(time.perf_counter() - t0) * 1000,
        )
        self._emit_evidence(f"browser-{self.site}-{task_id}", task_id, run)
        return run
