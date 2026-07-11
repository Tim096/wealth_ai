"""Browser Agent eval runner (SPEC 6.11).

Runs the layered task set (data/browser_eval/tasks.json) against the local
mock sites and computes real metrics: task success rate, verifier false-positive
rate (claimed pass that the eval's own ground truth says should fail),
silent-failure rate, repair success rate, avg steps/latency, trace completeness.
Offline, deterministic — no network, no LLM.

T1-5 pass@k & flakiness: `--repeat N` runs every task N times (fresh selector
memory each pass = independent samples) and aggregates pass@1 vs pass@k plus a
verdict-consistency / flaky-rate signal. Script Mode is deterministic by
construction (each pass clears memory, no LLM), so pass@1 == pass@k and
flaky_rate == 0 is itself the reportable property — flakiness only becomes
non-trivial in Agent Mode with a live LLM planner. `--agentic` additionally
runs a small Agent Mode subset (MockPlanner offline, still deterministic) to
show the same pass@k machinery drives the LLM path. Basis: pass@k as the
stability axis for stochastic agents (agent-eval literature; live LLM only).

P0-9 harness persistence + watchdog: every task runs under tools/eval_worker's
guard — per-task try/finally summary.json, Playwright-level timeout, a
done/error/incomplete harness axis SEPARATE from the verdict layer (metrics
count done only), `--resume` relaunch masking, and a >30% error-rate abort
that still persists the partial rows.

P0-11 scalability: `--workers N` runs the single-pass Script-Mode set on a
subprocess worker pool (tools/eval_worker.run_pool) — each worker holds ONE
persistent browser session (cold start amortized; fresh context per task), a
wall-clock watchdog in the parent terminates hung workers (the process-level
carrier P0-9 deferred), and results.json gains a `scalability` block: the
multi-session cost model (concurrency x per-session cold-start/busy/
utilization, throughput, speedup vs the serial estimate).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from browser_core import BrowserTaskContract, ForbiddenCondition, SuccessCondition
from browser_agent.agent import BrowserAgent, Step
from browser_agent.memory_store import MemoryStore
from observability_core import EvidenceStore

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))                    # `tools.` imports when run as a script
from tools.eval_worker import (                  # noqa: E402
    HarnessAbort, arm_watchdog, harness_report, load_done_summary,
    run_guarded, run_pool, scan_incomplete, session_cost_model, should_abort,
)
TASKS = ROOT / "data" / "browser_eval" / "tasks.json"
OUT = ROOT / "runs" / "browser_eval"
EVIDENCE = ROOT / "data" / "browser_eval" / "evidence"
# committed pass@k artifact lives in this track's own data dir (not the
# gitignored runs/ output) so the flakiness numbers are reproducible in-repo.
PASSK = ROOT / "data" / "browser_eval" / "passk"


def uri(version: str) -> str:
    return (ROOT / "data" / "mock_sites" / version / "index.html").resolve().as_uri()


def build(task: dict):
    steps = [
        Step(purpose="search_box", kind="fill", value=task["query"], fallback_selector="#search-box"),
        Step(purpose="submit_button", kind="click", fallback_selector="#search-btn"),
    ]
    contract = BrowserTaskContract(
        task_id=task["task_id"],
        natural_language_task=f"Search MockShop for '{task['query']}'",
        expected_outcome="Results containing the queried product are shown",
        success_conditions=[SuccessCondition(type="text_visible", value=v) for v in task["success_text"]],
        forbidden_conditions=[ForbiddenCondition(type="captcha_visible", value="captcha")],
    )
    return steps, contract


def _row(run, task) -> dict:
    """One eval row from a finished TaskRun (shared by every pass)."""
    expected = task["expect_status"]
    return {
        "task_id": task["task_id"], "layer": task["layer"], "site": task["site"],
        "status": run.status, "expected": expected, "correct": run.status == expected,
        "confidence": round(run.confidence, 3),
        # verifier false positive = claimed pass when ground truth says fail
        "repairs": run.repairs, "false_positive": run.status == "pass" and expected == "fail",
        "trace_complete": bool(run.steps), "latency_ms": round(run.total_latency_ms, 1),
        "verifier_reason": run.verifier.reason,
    }


def _error_row(task: dict, summary: dict) -> dict:
    """Harness-error stub row — carries NO verdict-layer fields (the two axes
    stay separate); excluded from metrics/pass@k, reported in the harness block."""
    return {"task_id": task["task_id"], "layer": task["layer"], "site": task["site"],
            "expected": task["expect_status"], "harness_status": "error",
            "harness_error": summary["error"]}


def run_script_pass(page, tasks: list[dict], mem_path: Path, evidence=None,
                    resume: bool = False) -> list[dict]:
    """One full Script-Mode pass over the task set with FRESH selector memory.
    Clearing memory per pass makes each pass an independent, reproducible sample
    (memory accumulation would make repair counts drift across passes).

    P0-9: every task runs under the harness guard (per-task summary.json via
    try/finally + Playwright-level watchdog); a crashing task yields an error
    row instead of killing the pass, and >30% harness errors raise HarnessAbort
    with the partial rows. resume=True masks tasks a prior launch finished."""
    if mem_path.exists():
        mem_path.unlink()
    mem = MemoryStore(mem_path)
    arm_watchdog(page)
    rows: list[dict] = []
    n_error = n_attempted = 0
    for task in tasks:
        if resume:
            prior = load_done_summary(task["task_id"], out_root=OUT)
            if prior:
                row = prior["row"]
                row["harness_status"] = "done"
                row["resumed"] = True
                rows.append(row)
                continue

        def _one(task=task):
            page.goto(uri(task["site"]))
            agent = BrowserAgent(page, mem, site="mockshop", task_type="search",
                                 artifact_dir=OUT / task["task_id"], evidence_store=evidence)
            steps, contract = build(task)
            return _row(agent.run(task["task_id"], steps, contract), task)

        summary = run_guarded(task["task_id"], _one, out_root=OUT)
        n_attempted += 1
        if summary["harness_status"] == "done":
            row = summary["row"]
            row["harness_status"] = "done"
        else:
            n_error += 1
            row = _error_row(task, summary)
        rows.append(row)
        if should_abort(n_error, n_attempted):
            raise HarnessAbort(rows, n_error, n_attempted)
    return rows


def run_agentic_pass(page, tasks: list[dict], mem_path: Path) -> list[dict]:
    """One Agent-Mode pass using the offline deterministic MockPlanner (no key).
    Demonstrates the pass@k machinery on the LLM path; MockPlanner is still
    deterministic, so real flakiness only shows with a live planner.
    Guarded like the script pass; summaries live under <task_id>--agentic so
    they never mask/overwrite the Script-Mode summary for the same task."""
    from browser_agent.planner import MockPlanner
    if mem_path.exists():
        mem_path.unlink()
    mem = MemoryStore(mem_path)
    arm_watchdog(page)
    rows: list[dict] = []
    n_error = n_attempted = 0
    for task in tasks:
        def _one(task=task):
            page.goto(uri(task["site"]))
            agent = BrowserAgent(page, mem, site="mockshop", task_type="search")
            _, contract = build(task)
            run = agent.run_agentic(task["task_id"], contract, MockPlanner(task["query"]),
                                    max_steps=6)
            return _row(run, task)

        summary = run_guarded(f"{task['task_id']}--agentic", _one, out_root=OUT)
        n_attempted += 1
        if summary["harness_status"] == "done":
            row = summary["row"]
            row["harness_status"] = "done"
        else:
            n_error += 1
            row = _error_row(task, summary)
        rows.append(row)
        if should_abort(n_error, n_attempted):
            raise HarnessAbort(rows, n_error, n_attempted)
    return rows


def run_parallel_pass(tasks: list[dict], workers: int, resume: bool = False):
    """P0-11: one Script-Mode pass over the task set on the subprocess worker
    pool (tools/eval_worker.run_pool). Each worker keeps one browser session
    across its tasks (session pool — cold start amortized) with a fresh context
    per task; selector memory is per-worker so repair counts stay independent
    of scheduling order, and the shared evidence log is skipped (single-writer
    artifact). resume=True masks tasks a prior launch finished, exactly like
    the sequential path. Returns (rows in task order, scalability block)."""
    by_id = {t["task_id"]: t for t in tasks}

    def to_row(summary):
        if summary["harness_status"] == "done":
            row = summary["row"]
            row["harness_status"] = "done"
            return row
        return _error_row(by_id[summary["task_id"]], summary)

    resumed: dict[str, dict] = {}
    to_run: list[dict] = []
    for task in tasks:
        if resume:
            prior = load_done_summary(task["task_id"], out_root=OUT)
            if prior:
                row = prior["row"]
                row["harness_status"] = "done"
                row["resumed"] = True
                resumed[task["task_id"]] = row
                continue
        to_run.append(task)

    try:
        summaries, pool_stats = run_pool(to_run, workers=workers, out_root=OUT, mem_dir=OUT)
    except HarnessAbort as ab:
        # re-raise with row-shaped partials so main() persists them as usual
        raise HarnessAbort([to_row(s) for s in ab.rows], ab.n_error, ab.n_attempted) from None

    by_run = {s["task_id"]: to_row(s) for s in summaries}
    rows = [resumed.get(t["task_id"]) or by_run[t["task_id"]] for t in tasks]
    n_done = sum(s["harness_status"] == "done" for s in summaries)
    return rows, session_cost_model(pool_stats, n_done)


def compute_metrics(rows: list[dict]) -> dict:
    """Single-pass VERDICT metrics — computed over harness-done rows ONLY;
    error/incomplete rows are reported in the separate harness block (P0-9).
    Rows without a harness_status key (legacy callers) count as done."""
    rows = [r for r in rows if r.get("harness_status", "done") == "done"]
    if not rows:
        return {"tasks": 0}
    n = len(rows)
    return {
        "tasks": n,
        "verdict_accuracy": round(sum(r["correct"] for r in rows) / n, 3),
        "task_success_rate": round(sum(r["status"] == "pass" and r["expected"] == "pass" for r in rows)
                                   / max(1, sum(r["expected"] == "pass" for r in rows)), 3),
        "verifier_false_positive_rate": round(sum(r["false_positive"] for r in rows) / n, 3),
        "repair_success_rate": round(sum(r["repairs"] > 0 and r["status"] == "pass" for r in rows)
                                     / max(1, sum(r["repairs"] > 0 for r in rows)), 3),
        "trace_completeness": round(sum(r["trace_complete"] for r in rows) / n, 3),
        "avg_latency_ms": round(sum(r["latency_ms"] for r in rows) / n, 1),
    }


def collate(passes: list[list[dict]]) -> dict:
    """Fold N passes of rows into {task_id: {expected, statuses[]}}."""
    by: dict[str, dict] = {}
    for rows in passes:
        for r in rows:
            e = by.setdefault(r["task_id"], {"expected": r["expected"], "statuses": []})
            e["statuses"].append(r["status"])
    return by


def aggregate_passk(rows_by_task: dict, k: int) -> dict:
    """Pure pass@k / flakiness aggregation (no browser — unit-testable).

    - pass@1 / pass@k are computed ONLY over solvable tasks (expected == 'pass'),
      where a success is status == 'pass'. pass@1 = mean per-task success rate
      (expected value of a single attempt); pass@k = fraction of solvable tasks
      solved at least once in k attempts. Mixing adversarial (expected fail)
      tasks into pass@k would be meaningless, so they are excluded there.
    - verdict_consistency / flaky_rate cover ALL tasks: a task is flaky iff its
      status is not identical across every pass. This is the mode-agnostic
      stability signal; deterministic == no flaky task.
    """
    per_task = []
    for tid, d in rows_by_task.items():
        statuses = d["statuses"]
        n = len(statuses)
        expected = d["expected"]
        consistent = len(set(statuses)) == 1
        entry = {
            "task_id": tid, "expected": expected, "statuses": statuses,
            "n": n, "consistent": consistent, "distinct_statuses": sorted(set(statuses)),
        }
        if expected == "pass":
            succ = sum(s == "pass" for s in statuses)
            entry["success_count"] = succ
            entry["pass_at_1"] = round(succ / n, 3)
            entry["solved_at_k"] = succ > 0
        per_task.append(entry)

    n_tasks = len(per_task)
    solvable = [t for t in per_task if t["expected"] == "pass"]
    flaky = [t for t in per_task if not t["consistent"]]
    summary = {
        "k": k, "n_tasks": n_tasks, "n_solvable": len(solvable),
        "pass_at_1": round(sum(t["pass_at_1"] for t in solvable) / len(solvable), 3) if solvable else None,
        "pass_at_k": round(sum(t["solved_at_k"] for t in solvable) / len(solvable), 3) if solvable else None,
        "verdict_consistency": round(sum(t["consistent"] for t in per_task) / n_tasks, 3) if n_tasks else None,
        "flaky_rate": round(len(flaky) / n_tasks, 3) if n_tasks else None,
        "flaky_tasks": [t["task_id"] for t in flaky],
        "deterministic": len(flaky) == 0,
    }
    return {"summary": summary, "per_task": per_task}


def main(repeat: int = 1, agentic: bool = False, resume: bool = False,
         workers: int = 1) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    spec = json.loads(TASKS.read_text(encoding="utf-8"))
    tasks = spec["tasks"]
    # Agent Mode subset: the solvable (expected-pass) tasks, capped, so the
    # offline MockPlanner run stays small and fast.
    agentic_subset = [t for t in tasks if t["expect_status"] == "pass"][:3]
    evidence = EvidenceStore(EVIDENCE)

    # incomplete-from-prior-run (harness died mid-task) — reported, never in metrics
    incomplete_prior = scan_incomplete([t["task_id"] for t in tasks], out_root=OUT)

    script_passes: list[list[dict]] = []
    agentic_passes: list[list[dict]] = []
    aborted = False
    scalability = None
    if workers > 1:
        # P0-11 parallel path: single Script-Mode pass on the subprocess pool
        # (no browser in this process — every session lives in a worker)
        try:
            rows, scalability = run_parallel_pass(tasks, workers, resume=resume)
            script_passes.append(rows)
        except HarnessAbort as ab:
            script_passes.append(ab.rows)
            aborted = True
            print(f"\n{ab}")
    else:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1000, "height": 800})
            for rep in range(repeat):
                # evidence only on the first pass — appending N copies would just
                # bloat the shared evidence log without adding signal.
                ev = evidence if rep == 0 else None
                try:
                    script_passes.append(run_script_pass(
                        page, tasks, OUT / "selector_memory.json", ev, resume=resume))
                    if agentic:
                        agentic_passes.append(run_agentic_pass(
                            page, agentic_subset, OUT / "selector_memory_agentic.json"))
                except HarnessAbort as ab:
                    # persist the partial rows instead of losing the whole set
                    target = script_passes if len(script_passes) == rep else agentic_passes
                    target.append(ab.rows)
                    aborted = True
                    print(f"\n{ab}")
                    break
            browser.close()

    # backward-compatible single-pass results.json (pass 0) — plus the P0-9
    # harness block (done/error/incomplete axis, separate from verdicts)
    rows0 = script_passes[0]
    metrics = compute_metrics(rows0)
    harness = harness_report(rows0, n_planned=len(tasks), aborted=aborted)
    harness["incomplete_from_prior_run"] = incomplete_prior
    payload = {"metrics": metrics, "harness": harness, "tasks": rows0}
    if scalability:
        payload["scalability"] = scalability   # P0-11 multi-session cost model
    (OUT / "results.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8")

    print("browser eval metrics (pass 1):")
    for k, v in metrics.items():
        print(f"  {k}: {v}")
    print(f"  harness: done={harness['done']} error={harness['error']} "
          f"not_run={harness['not_run']} resumed={harness['resumed']} "
          f"aborted={harness['aborted']}")
    if scalability:
        print(f"  scalability: workers={scalability['concurrency']} "
              f"sessions={scalability['sessions_launched']} "
              f"wall={scalability['wall_clock_s']}s "
              f"speedup~{scalability['speedup_vs_serial_estimate']}x "
              f"(vs serial estimate {scalability['serial_estimate_s']}s)")
    print()
    for r in rows0:
        if r.get("harness_status", "done") != "done":
            print(f"  ERR {r['task_id']:<28} harness=error  {r['harness_error']}")
            continue
        mark = "OK " if r["correct"] else "XX "
        print(f"  {mark}{r['task_id']:<28} status={r['status']:<8} expected={r['expected']:<8} "
              f"repairs={r['repairs']} fp={r['false_positive']}")
    print(f"\nwrote {OUT / 'results.json'}")

    if aborted:
        # partial results are persisted above; the committed pass@k artifact
        # must never be rebuilt from an aborted (partial) run
        raise SystemExit(2)

    if repeat > 1 or agentic:
        PASSK.mkdir(parents=True, exist_ok=True)
        # pass@k is a VERDICT-layer aggregation: only harness-done rows have a
        # verdict, so error stubs are excluded before collation.
        done_only = [[r for r in rows if r.get("harness_status", "done") == "done"]
                     for rows in script_passes]
        agentic_done = [[r for r in rows if r.get("harness_status", "done") == "done"]
                        for rows in agentic_passes]
        result = {
            "repeat": repeat,
            "note": ("Script Mode is deterministic by construction (memory cleared "
                     "each pass, no LLM), so pass@1 == pass@k and flaky_rate == 0 is "
                     "the expected, reportable property. Non-trivial flakiness needs a "
                     "live LLM planner (Agent Mode, gateway); the offline MockPlanner "
                     "shown here is also deterministic."),
            "script_mode": aggregate_passk(collate(done_only), repeat),
        }
        if agentic:
            result["agent_mode_mock"] = aggregate_passk(collate(agentic_done), repeat)
        (PASSK / "passk_results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")

        s = result["script_mode"]["summary"]
        print(f"\npass@k (Script Mode, k={repeat}): pass@1={s['pass_at_1']} pass@k={s['pass_at_k']} "
              f"flaky_rate={s['flaky_rate']} deterministic={s['deterministic']}")
        if agentic:
            a = result["agent_mode_mock"]["summary"]
            print(f"pass@k (Agent Mode/MockPlanner, k={repeat}): pass@1={a['pass_at_1']} "
                  f"pass@k={a['pass_at_k']} flaky_rate={a['flaky_rate']} deterministic={a['deterministic']}")
        print(f"wrote {PASSK / 'passk_results.json'}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Browser Agent eval + pass@k / flakiness (T1-5)")
    ap.add_argument("--repeat", type=int, default=1,
                    help="run every task N times and aggregate pass@1 vs pass@k + flaky_rate")
    ap.add_argument("--agentic", action="store_true",
                    help="also run a small Agent Mode subset (offline MockPlanner) through pass@k")
    ap.add_argument("--resume", action="store_true",
                    help="relaunch masking: skip tasks whose runs/browser_eval/<task_id>/"
                         "summary.json says a prior launch already finished them")
    ap.add_argument("--workers", type=int, default=1,
                    help="P0-11: run the task set on N parallel subprocess workers, "
                         "each with its own persistent browser session")
    args = ap.parse_args()
    if args.repeat < 1:
        ap.error("--repeat must be >= 1")
    if args.resume and args.repeat != 1:
        ap.error("--resume only makes sense for a single-pass relaunch (--repeat 1)")
    if args.workers < 1:
        ap.error("--workers must be >= 1")
    if args.workers > 1 and (args.repeat != 1 or args.agentic):
        ap.error("--workers applies to the single-pass Script-Mode run only")
    main(repeat=args.repeat, agentic=args.agentic, resume=args.resume, workers=args.workers)
