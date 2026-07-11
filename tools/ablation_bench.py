"""Component ablation bench (P1-10) — quantify each reliability component's
contribution on a deterministic mock/script environment ($0, no LLM).

Configurations
  script phase (Script Mode, real BrowserAgent.run on local mock sites):
    full                 production behaviour (baseline)
    no_selector_repair   diagnose_failure patched to the un-repairable
                         'empty_result' branch -> Repair Mode never rebinds
    no_overlay_dismiss   _dismiss_modal_if_present/_dismiss_overlay -> no-op
    no_selector_memory   MemoryStore.preferred/hashes/fingerprint/record -> inert
    no_capability_guard  screen_task/screen_action -> always allowed
    no_baseline_subtract subtract_baseline -> identity (t0-true conditions kept)
    minimal_agentoccam   ALL of the above off at once (AgentOccam-style
                         plain executor); reported two ways: verifier verdict
                         (minimal_verified) and naive self-report verdict
                         "all actions executed ok => pass" (minimal_selfreport)

  agent phase (Agent Mode, run_agentic with deterministic scripted planners):
    full                 production behaviour
    no_stagnation_nudge  stagnation_nudge patched to return ''
    no_giveup_gate       _hard_giveup patched to True (every give_up honoured)
    no_done_gate         EMULATED: the done-rejection gate is inline in
                         run_agentic (no module-level hook), so the gate-off
                         counterfactual is reproduced by a history-blind
                         planner that never sees 'done_rejected' feedback —
                         its second done is honoured, exactly the trajectory a
                         gate-less loop gives an adaptive planner (modulo one
                         burned rejection turn). Production code untouched.
    no_overlay_dismiss   overlay handling off in the agent loop
    minimal_agentoccam   nudge+giveup gate+guard+baseline+overlay off, all
                         probe planners history-blind, verdict = planner
                         self-report (pass iff the planner claimed done)

Monkeypatches are applied around each config run and restored after; no
production file is modified. Deterministic: local file:// mock sites, scripted
planners, no network, no LLM, $0.

Outputs
  runs/browser_eval/ablation/raw/<phase>-<config>.json   (per-config rows)
  runs/browser_eval/ablation/results.json                (--merge)

Reproduce
  .venv/Scripts/python tools/ablation_bench.py --phase script
  .venv/Scripts/python tools/ablation_bench.py --phase agent
  .venv/Scripts/python tools/ablation_bench.py --merge
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import browser_agent.agent as agent_mod                       # noqa: E402
from browser_agent.agent import BrowserAgent                  # noqa: E402
from browser_agent.capability import CapabilityDecision       # noqa: E402
from browser_agent.memory_store import MemoryStore            # noqa: E402
from browser_agent.planner import MockPlanner, PlannerDecision  # noqa: E402
from browser_agent.repair import Diagnosis                    # noqa: E402
from browser_agent.replay_cache import ReplayCache            # noqa: E402
from browser_core import (                                    # noqa: E402
    BrowserTaskContract, ElementTarget, ForbiddenCondition, SuccessCondition,
)
from browser_core.actions import (                            # noqa: E402
    ClickAction, FillAction, KeyboardAction,
)

from tools.browser_eval import build as build_suite           # noqa: E402
from tools.impossible_tasks import build as build_impossible  # noqa: E402

TASKS = ROOT / "data" / "browser_eval" / "tasks.json"
OUT = ROOT / "runs" / "browser_eval" / "ablation"
RAW = OUT / "raw"


def uri(site: str) -> str:
    return (ROOT / "data" / "mock_sites" / site / "index.html").resolve().as_uri()


# ---------------------------------------------------------------- patches ---

def _allow(*_a, **_k) -> CapabilityDecision:
    return CapabilityDecision(True, "ok", "ablation: capability guard disabled")


PATCHES: dict[str, list[tuple[object, str, object]]] = {
    # selector repair off: every script-mode failure is diagnosed into the
    # 'empty_result' branch, which by design returns without any repair
    # (no press-Enter fallback, no timeout retry, no hash rebind, no scoring)
    "repair_off": [(agent_mod, "diagnose_failure",
                    lambda outcome, obs, url_changed, expected_url_fragment="":
                    Diagnosis("empty_result", False, "ablation: selector repair disabled"))],
    "overlay_off": [(BrowserAgent, "_dismiss_modal_if_present", lambda self, trace: None),
                    (BrowserAgent, "_dismiss_overlay", lambda self, trace: False)],
    "memory_off": [(MemoryStore, "preferred", lambda self, *a: ""),
                   (MemoryStore, "hashes", lambda self, *a: ("", "")),
                   (MemoryStore, "fingerprint", lambda self, *a: ""),
                   (MemoryStore, "record", lambda self, *a, **k: None)],
    "guard_off": [(agent_mod, "screen_task", _allow),
                  (agent_mod, "screen_action", _allow)],
    "baseline_off": [(agent_mod, "subtract_baseline",
                      lambda contract, obs: (contract, []))],
    "nudge_off": [(agent_mod, "stagnation_nudge", lambda *a, **k: "")],
    "giveup_gate_off": [(agent_mod, "_hard_giveup", lambda reason: True)],
}


@contextlib.contextmanager
def applied(patch_names: list[str]):
    saved: list[tuple[object, str, object]] = []
    for name in patch_names:
        for obj, attr, new in PATCHES[name]:
            saved.append((obj, attr, getattr(obj, attr)))
            setattr(obj, attr, new)
    try:
        yield
    finally:
        for obj, attr, old in reversed(saved):
            setattr(obj, attr, old)


SCRIPT_CONFIGS: dict[str, list[str]] = {
    "full": [],
    "no_selector_repair": ["repair_off"],
    "no_overlay_dismiss": ["overlay_off"],
    "no_selector_memory": ["memory_off"],
    "no_capability_guard": ["guard_off"],
    "no_baseline_subtract": ["baseline_off"],
    "minimal_agentoccam": ["repair_off", "overlay_off", "memory_off",
                           "guard_off", "baseline_off"],
}

AGENT_CONFIGS: dict[str, list[str]] = {
    "full": [],
    "no_stagnation_nudge": ["nudge_off"],
    "no_giveup_gate": ["giveup_gate_off"],
    "no_done_gate": [],                       # emulated via history-blind planner
    "no_overlay_dismiss": ["overlay_off"],
    "minimal_agentoccam": ["overlay_off", "guard_off", "baseline_off",
                           "nudge_off", "giveup_gate_off"],
}

# probe: a task with a success condition ALREADY true on the opening page and
# no step that could earn it — production drops it at t0 (baseline subtraction)
# and ends in an honest unknown; with the guard off the t0-true condition
# carries a vacuous PASS (a silent failure).
BASELINE_PROBE = {
    "task_id": "abl-baseline-vacuous", "group": "probe", "site": "v1",
    "kind": "vacuous_landmark", "expect_status": "unknown",
    "natural_language_task": "Confirm the MockShop storefront shows a clearance sale banner",
    "success_conditions": [{"type": "text_visible", "value": "MockShop"}],
}


# --------------------------------------------------------- probe planners ---

def _visible(history: list[str], blind: bool) -> list[str]:
    """A history-blind planner never sees the reliability loop's feedback —
    the exact information a gate-less loop would not produce."""
    if not blind:
        return history
    drop = ("done_rejected", "give_up_rejected", "NUDGE", "REPLAN")
    return [h for h in history if not any(m in h for m in drop)]


class EagerDonePlanner(MockPlanner):
    """Hallucination probe: claims done IMMEDIATELY (nothing achieved). Only
    after seeing done_rejected does it actually run the search. Measures the
    P0-3 done-rejection front gate: gate on -> rejected once -> recovers ->
    pass; gate off (blind) -> second done honoured -> verifier fail."""

    def __init__(self, query: str, blind: bool = False) -> None:
        super().__init__(query)
        self.blind = blind

    def next_action(self, task, success_conditions, obs, history,
                    plan_steps=None, image_path=None) -> PlannerDecision:
        h = _visible(history, self.blind)
        if not any("done_rejected" in x for x in h):
            return PlannerDecision(kind="done", reason="looks complete already")
        if not any(x.startswith("fill:ok") for x in h):
            box = self._find(obs, {"input", "textarea", "searchbox", "textbox"},
                             {"search", "query", "find"})
            if box:
                t = ElementTarget(selector=box.aid_selector(), selector_type="css")
                return PlannerDecision(kind="action",
                                       action=FillAction(target=t, value=self.query),
                                       reason="fill the search box")
        if not any(x.startswith("click:ok") for x in h):
            btn = self._find(obs, {"button"}, {"search", "submit", "go", "find"})
            if btn:
                t = ElementTarget(selector=btn.aid_selector(), selector_type="css")
                return PlannerDecision(kind="action", action=ClickAction(target=t),
                                       reason="click submit")
        return PlannerDecision(kind="done", reason="search executed")


class SoftGiveupPlanner(MockPlanner):
    """give_up-gate probe: fills the box, then gives up SOFTLY ('cannot find
    the submit control'). Gate on -> soft give_up rejected with ample budget ->
    recovers -> pass; gate off (_hard_giveup->True) -> honoured at once -> fail."""

    def __init__(self, query: str, blind: bool = False) -> None:
        super().__init__(query)
        self.blind = blind

    def next_action(self, task, success_conditions, obs, history,
                    plan_steps=None, image_path=None) -> PlannerDecision:
        h = _visible(history, self.blind)
        if not any(x.startswith("fill:ok") for x in h):
            box = self._find(obs, {"input", "textarea", "searchbox", "textbox"},
                             {"search", "query", "find"})
            if box:
                t = ElementTarget(selector=box.aid_selector(), selector_type="css")
                return PlannerDecision(kind="action",
                                       action=FillAction(target=t, value=self.query),
                                       reason="fill the search box")
        if not any("give_up_rejected" in x for x in h):
            return PlannerDecision(kind="give_up",
                                   reason="cannot find the submit control on this page")
        if not any(x.startswith("click:ok") for x in h):
            btn = self._find(obs, {"button"}, {"search", "submit", "go", "find"})
            if btn:
                t = ElementTarget(selector=btn.aid_selector(), selector_type="css")
                return PlannerDecision(kind="action", action=ClickAction(target=t),
                                       reason="click submit")
        return PlannerDecision(kind="done", reason="search executed")


class StuckPlanner(MockPlanner):
    """stagnation-nudge probe: presses Escape every turn (page never changes)
    until a NUDGE/REPLAN appears in its history, then runs the search. Nudge
    on -> fires at the 5-step ladder rung -> recovers -> pass; nudge off ->
    loops to budget exhaustion -> verifier fail."""

    def __init__(self, query: str, blind: bool = False) -> None:
        super().__init__(query)
        self.blind = blind

    def next_action(self, task, success_conditions, obs, history,
                    plan_steps=None, image_path=None) -> PlannerDecision:
        h = _visible(history, self.blind)
        if any(("NUDGE" in x) or ("REPLAN" in x) for x in h):
            if not any(x.startswith("fill:ok") for x in h):
                box = self._find(obs, {"input", "textarea", "searchbox", "textbox"},
                                 {"search", "query", "find"})
                if box:
                    t = ElementTarget(selector=box.aid_selector(), selector_type="css")
                    return PlannerDecision(kind="action",
                                           action=FillAction(target=t, value=self.query),
                                           reason="fill the search box")
            if not any(x.startswith("click:ok") for x in h):
                btn = self._find(obs, {"button"}, {"search", "submit", "go", "find"})
                if btn:
                    t = ElementTarget(selector=btn.aid_selector(), selector_type="css")
                    return PlannerDecision(kind="action", action=ClickAction(target=t),
                                           reason="click submit")
            return PlannerDecision(kind="done", reason="search executed")
        return PlannerDecision(kind="action", action=KeyboardAction(keys="Escape"),
                               reason="hesitating (probe: deliberate no-op)")


# ------------------------------------------------------------- script run ---

_PURPOSES = {"search_box", "submit_button"}


def _naive_status(run) -> str:
    """AgentOccam-style self-report for Script Mode: 'my actions executed
    without error, therefore the task succeeded'. No verifier, no contract."""
    acted = [s for s in run.steps if s.step in _PURPOSES]
    return "pass" if all(s.ok for s in acted) else "fail"


def _script_row(run, task: dict, group: str, t0: float) -> dict:
    expected = task["expect_status"]
    return {
        "task_id": task["task_id"], "group": group, "site": task["site"],
        "expected": expected, "status": run.status,
        "correct": run.status == expected,
        "silent_failure": run.status == "pass" and expected != "pass",
        "naive_status": _naive_status(run),
        "naive_false_success": _naive_status(run) == "pass" and expected != "pass",
        "repairs": run.repairs, "n_trace": len(run.steps),
        "latency_ms": round(run.total_latency_ms, 1),
        "verifier_reason": run.verifier.reason,
        "wall_s": round(time.perf_counter() - t0, 2),
    }


def run_script_config(name: str, page, spec: dict) -> dict:
    patch_names = SCRIPT_CONFIGS[name]
    rows: list[dict] = []
    c0 = time.perf_counter()
    with applied(patch_names):
        # suite: SHARED memory across the 5 tasks (mirrors browser_eval) so the
        # memory component's cross-task effect (cheaper 2nd drift run) is visible
        mem_path = RAW / f"_mem-suite-{name}.json"
        mem_path.unlink(missing_ok=True)
        mem = MemoryStore(mem_path)
        for task in spec["tasks"]:
            t0 = time.perf_counter()
            page.goto(uri(task["site"]))
            agent = BrowserAgent(page, mem, site="mockshop", task_type="search")
            steps, contract = build_suite(task)
            run = agent.run(task["task_id"], steps, contract)
            rows.append(_script_row(run, task, "suite", t0))
        # impossible: fresh memory per task (mirrors impossible_tasks.py)
        for task in spec["impossible_tasks"]:
            t0 = time.perf_counter()
            m2p = RAW / f"_mem-{name}-{task['task_id']}.json"
            m2p.unlink(missing_ok=True)
            page.goto(uri(task["site"]))
            agent = BrowserAgent(page, MemoryStore(m2p), site="mockshop",
                                 task_type="search")
            steps, contract = build_impossible(task)
            run = agent.run(task["task_id"], steps, contract)
            rows.append(_script_row(run, task, "impossible", t0))
            m2p.unlink(missing_ok=True)
        # baseline-subtraction probe: zero steps, t0-true landmark condition
        t0 = time.perf_counter()
        m3p = RAW / f"_mem-{name}-baseline-probe.json"
        m3p.unlink(missing_ok=True)
        page.goto(uri(BASELINE_PROBE["site"]))
        agent = BrowserAgent(page, MemoryStore(m3p), site="mockshop",
                             task_type="search")
        contract = BrowserTaskContract(
            task_id=BASELINE_PROBE["task_id"],
            natural_language_task=BASELINE_PROBE["natural_language_task"],
            expected_outcome="honest unknown — the only condition is vacuously true at t0",
            success_conditions=[SuccessCondition(type=c["type"], value=c["value"])
                                for c in BASELINE_PROBE["success_conditions"]],
            forbidden_conditions=[])
        run = agent.run(BASELINE_PROBE["task_id"], [], contract)
        rows.append(_script_row(run, BASELINE_PROBE, "probe", t0))
        m3p.unlink(missing_ok=True)
        mem_path.unlink(missing_ok=True)
    return {"phase": "script", "config": name, "patches": patch_names,
            "wall_s": round(time.perf_counter() - c0, 1), "rows": rows}


# -------------------------------------------------------------- agent run ---

def _agent_tasks(spec: dict) -> list[dict]:
    """5 suite tasks (MockPlanner) + 3 gate probes. All deterministic."""
    out = []
    for task in spec["tasks"]:
        out.append({"task_id": f"{task['task_id']}--agentic", "site": task["site"],
                    "query": task["query"], "expected": task["expect_status"],
                    "success_text": task["success_text"], "planner": "mock",
                    "max_steps": 8, "group": "suite"})
    for tid, planner in (("probe-done-gate", "eager_done"),
                         ("probe-giveup-gate", "soft_giveup"),
                         ("probe-stagnation", "stuck")):
        out.append({"task_id": tid, "site": "v1", "query": "widget",
                    "expected": "pass", "success_text": ["results for", "Widget"],
                    "planner": planner, "max_steps": 10, "group": "probe"})
    return out


def _make_planner(kind: str, query: str, blind: bool):
    if kind == "mock":
        return MockPlanner(query)          # MockPlanner never reads history
    if kind == "eager_done":
        return EagerDonePlanner(query, blind=blind)
    if kind == "soft_giveup":
        return SoftGiveupPlanner(query, blind=blind)
    return StuckPlanner(query, blind=blind)


def run_agent_config(name: str, page, spec: dict) -> dict:
    patch_names = AGENT_CONFIGS[name]
    # blind planners: no_done_gate blinds ONLY the done probe (the emulation);
    # minimal blinds every probe (a gate-less loop produces no feedback at all)
    blind_kinds: set[str] = set()
    if name == "no_done_gate":
        blind_kinds = {"eager_done"}
    elif name == "minimal_agentoccam":
        blind_kinds = {"eager_done", "soft_giveup", "stuck"}
    rows: list[dict] = []
    c0 = time.perf_counter()
    with applied(patch_names):
        mem_path = RAW / f"_mem-agent-{name}.json"
        mem_path.unlink(missing_ok=True)
        for t in _agent_tasks(spec):
            t0 = time.perf_counter()
            # FRESH replay cache per task: several tasks share the same task
            # sentence (the ReplayCache key), so a shared cache would replay a
            # previously banked pass and the gates under test would never run
            replay_path = RAW / f"_replay-{name}.json"
            replay_path.unlink(missing_ok=True)
            page.goto(uri(t["site"]))
            agent = BrowserAgent(page, MemoryStore(mem_path), site="mockshop",
                                 task_type="search",
                                 replay_cache=ReplayCache(replay_path))
            contract = BrowserTaskContract(
                task_id=t["task_id"],
                natural_language_task=f"Search MockShop for '{t['query']}'",
                expected_outcome="Results containing the queried product are shown",
                success_conditions=[SuccessCondition(type="text_visible", value=v)
                                    for v in t["success_text"]],
                forbidden_conditions=[ForbiddenCondition(type="captcha_visible",
                                                         value="captcha")])
            planner = _make_planner(t["planner"], t["query"],
                                    blind=t["planner"] in blind_kinds)
            run = agent.run_agentic(t["task_id"], contract, planner,
                                    max_steps=t["max_steps"])
            claimed_done = any(s.step == "planner" and s.action == "done" and s.ok
                               for s in run.steps)
            gave_up = any(s.step == "planner" and s.action == "give_up"
                          for s in run.steps)
            planner_turns = sum(1 for s in run.steps if s.step == "planner")
            # Self-report (AgentOccam-style, no verifier): a run the planner
            # abandoned (give_up) or that exhausted its budget without a done
            # claim is a self-reported fail; anything else is a self-reported
            # pass. The optimistic branch covers the loop's early verdict-pass
            # break, which ends the run one turn before a scripted planner's
            # done claim — without it the self-report would be artificially
            # pessimistic on exactly the successful runs.
            exhausted = planner_turns >= t["max_steps"] and not claimed_done
            selfreport = "fail" if (gave_up or exhausted) else "pass"
            # minimal (AgentOccam-style) has no verifier: its reported verdict
            # is the self-report; every other config reports the verifier's
            status = selfreport if name == "minimal_agentoccam" else run.status
            rows.append({
                "task_id": t["task_id"], "group": t["group"], "site": t["site"],
                "planner": t["planner"], "expected": t["expected"],
                "status": status, "verifier_status": run.status,
                "selfreport_status": selfreport,
                "verdict_source": "self_report" if name == "minimal_agentoccam" else "verifier",
                "correct": status == t["expected"],
                "silent_failure": status == "pass" and t["expected"] != "pass",
                "false_success_vs_verifier": selfreport == "pass" and run.status != "pass",
                "claimed_done": claimed_done, "gave_up": gave_up,
                "planner_turns": planner_turns,
                "n_trace": len(run.steps),
                "latency_ms": round(run.total_latency_ms, 1),
                "verifier_reason": run.verifier.reason,
                "wall_s": round(time.perf_counter() - t0, 2),
            })
        mem_path.unlink(missing_ok=True)
        replay_path.unlink(missing_ok=True)
    return {"phase": "agent", "config": name, "patches": patch_names,
            "wall_s": round(time.perf_counter() - c0, 1), "rows": rows}


# ------------------------------------------------------------------ merge ---

def _metrics(rows: list[dict]) -> dict:
    n = len(rows)
    return {
        "tasks": n,
        "correct": sum(r["correct"] for r in rows),
        "correct_rate": round(sum(r["correct"] for r in rows) / n, 3),
        "silent_failures": sum(r["silent_failure"] for r in rows),
        "avg_repairs": round(sum(r.get("repairs", 0) for r in rows) / n, 2),
        "total_repairs": sum(r.get("repairs", 0) for r in rows),
        "avg_trace_steps": round(sum(r["n_trace"] for r in rows) / n, 1),
        "avg_latency_ms": round(sum(r["latency_ms"] for r in rows) / n, 1),
    }


def _delta(full_rows: list[dict], cfg_rows: list[dict]) -> dict:
    fb = {r["task_id"]: r for r in full_rows}
    flipped = [{"task_id": r["task_id"], "full": fb[r["task_id"]]["status"],
                "ablated": r["status"]}
               for r in cfg_rows
               if r["task_id"] in fb and r["status"] != fb[r["task_id"]]["status"]]
    mf, mc = _metrics(full_rows), _metrics(cfg_rows)
    return {
        "correct_delta": mc["correct"] - mf["correct"],
        "silent_failure_delta": mc["silent_failures"] - mf["silent_failures"],
        "repairs_delta": mc["total_repairs"] - mf["total_repairs"],
        "flipped_tasks": flipped,
    }


def merge() -> None:
    phases: dict[str, dict] = {"script": {}, "agent": {}}
    for f in sorted(RAW.glob("*.json")):
        if f.name.startswith("_"):
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        phases[d["phase"]][d["config"]] = d
    out: dict = {
        "generated_by": "tools/ablation_bench.py",
        "date": time.strftime("%Y-%m-%d"),
        "environment": {
            "deterministic": True, "llm_cost_usd": 0.0,
            "sites": "data/mock_sites/{v1,v2,v3_heldout} via file:// URIs",
            "task_sets": "data/browser_eval/tasks.json -> tasks(5) + "
                         "impossible_tasks(12) + 1 baseline probe (script); "
                         "5 suite + 3 gate probes (agent)",
            "planners": "MockPlanner + 3 scripted gate-probe planners (no LLM)",
        },
        "method": {
            "injection": "monkeypatch at module/class level around each config "
                         "run, restored after; production code unmodified",
            "repairs_semantics": "the repairs counter counts Repair-Mode trace "
                "entries (attempts). In repair-off configs the un-repairable "
                "'empty_result' stub still counts as an attempt, so total_repairs "
                "stays comparable but means 'diagnosed failures', not fixes — "
                "read pass/fail (correct) as the primary axis there",
            "no_done_gate_emulation": "the done gate is inline in run_agentic "
                "(no module-level hook); gate-off is emulated by a history-blind "
                "planner whose second done is honoured — the same final state a "
                "gate-less loop reaches, at the cost of one extra rejected turn",
            "not_ablated": {
                "second_judge": "advisory by design — it never changes a "
                    "verdict, so its pass/fail ablation delta is 0 by "
                    "construction; its contribution is adjudication coverage "
                    "(see runs/browser_eval/second_judge.json)",
                "replay_cache": "only fires on a REPEAT run of the same task; "
                    "every config here runs each task once with a fresh cache "
                    "file, so its delta is structurally 0 in this design "
                    "(measured elsewhere: tests/test_p0_10_replay_cache_shadow.py)",
                "vision/second-model paths": "require a live multimodal LLM; "
                    "out of scope for the $0 deterministic bench",
            },
        },
        "reproduce": [
            ".venv/Scripts/python tools/ablation_bench.py --phase script",
            ".venv/Scripts/python tools/ablation_bench.py --phase agent",
            ".venv/Scripts/python tools/ablation_bench.py --merge",
        ],
        "config_definitions": {
            "script": {k: v for k, v in SCRIPT_CONFIGS.items()},
            "agent": {k: v for k, v in AGENT_CONFIGS.items()},
            "patch_registry": {k: [f"{getattr(o, '__name__', o.__class__.__name__)}.{a}"
                                   for o, a, _ in v] for k, v in PATCHES.items()},
        },
    }
    for phase, cfgs in phases.items():
        if "full" not in cfgs:
            continue
        full_rows = cfgs["full"]["rows"]
        block: dict = {"configs": {}}
        for name, d in cfgs.items():
            entry = {"patches": d["patches"], "wall_s": d["wall_s"],
                     "metrics": _metrics(d["rows"]), "rows": d["rows"]}
            if name != "full":
                entry["delta_vs_full"] = _delta(full_rows, d["rows"])
            block["configs"][name] = entry
        if phase == "script" and "minimal_agentoccam" in cfgs:
            rows = cfgs["minimal_agentoccam"]["rows"]
            block["minimal_selfreport"] = {
                "note": "same minimal runs, verdict = naive self-report "
                        "('all actions executed ok => pass') — the no-verifier "
                        "AgentOccam-style reading",
                "naive_pass": sum(r["naive_status"] == "pass" for r in rows),
                "naive_false_successes": sum(r["naive_false_success"] for r in rows),
                "naive_correct": sum(r["naive_status"] == r["expected"] for r in rows),
                "tasks": len(rows),
            }
        out[phase] = block
    (OUT / "results.json").write_text(json.dumps(out, indent=2, ensure_ascii=False),
                                      encoding="utf-8")
    print(f"wrote {OUT / 'results.json'}")


# ------------------------------------------------------------------- main ---

def main() -> None:
    ap = argparse.ArgumentParser(description="P1-10 component ablation bench")
    ap.add_argument("--phase", choices=["script", "agent"])
    ap.add_argument("--config", default=None, help="run only this config")
    ap.add_argument("--merge", action="store_true",
                    help="fold raw per-config files into results.json")
    args = ap.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    if args.merge:
        merge()
        return
    if not args.phase:
        ap.error("--phase or --merge required")
    spec = json.loads(TASKS.read_text(encoding="utf-8"))
    configs = SCRIPT_CONFIGS if args.phase == "script" else AGENT_CONFIGS
    names = [args.config] if args.config else list(configs)
    for n in names:
        if n not in configs:
            ap.error(f"unknown config {n!r} for phase {args.phase}")

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1000, "height": 800})
        page.set_default_timeout(10_000)
        for name in names:
            runner = run_script_config if args.phase == "script" else run_agent_config
            d = runner(name, page, spec)
            (RAW / f"{args.phase}-{name}.json").write_text(
                json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
            m = _metrics(d["rows"])
            print(f"[{args.phase}/{name}] tasks={m['tasks']} "
                  f"correct={m['correct']} silent={m['silent_failures']} "
                  f"repairs={m['total_repairs']} wall={d['wall_s']}s")
        browser.close()


if __name__ == "__main__":
    main()
