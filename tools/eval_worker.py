"""Per-task harness isolation layer (P0-9): persistence + watchdog + abort guard.

Harness-level status is a SEPARATE axis from the verdict layer
(pass/fail/unknown/refused):

  done       — the task fn returned a row; ONLY these rows enter verdict metrics
  error      — the task fn raised; captured and reported, never re-raised
  incomplete — the process died mid-task: the pre-execution marker written by
               run_guarded is the only thing that survives a hard crash

Every task runs under try/finally that writes
`runs/browser_eval/<task_id>/summary.json`, so a mid-set crash can no longer
throw away every finished row without artifact (BG silent-failure trichotomy).
The watchdog is Playwright-level — win32 has no signal.alarm, so every page
action/navigation gets a hard timeout and a hung page raises instead of
stalling the whole set. Relaunch masking (load_done_summary) lets a rerun skip
tasks a previous launch already finished, and should_abort stops a run whose
harness error rate exceeds 30% (BG relaunch guard). P0-11's subprocess-per-task
driver shares this same isolation boundary.

P0-11 adds the scalability layer on top: run_pool schedules the task set over
N child-process workers (each owning ONE persistent browser session — the
session pool that amortizes cold start — with a fresh context per task), the
parent enforces a WALL-CLOCK per-task deadline by terminating a hung worker
(the process-level watchdog carrier P0-9 deferred here; Playwright timeouts
cannot fire when the hang is outside a page call), and session_cost_model
turns the per-session stats into the multi-session cost model
(concurrency x per-session cold-start/busy/utilization, speedup vs a serial
estimate) reported in results.json.
"""

from __future__ import annotations

import json
import multiprocessing as mp
import queue
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS_ROOT = ROOT / "runs" / "browser_eval"

TASK_TIMEOUT_MS = 30_000   # Playwright-level per-action/navigation watchdog
ERROR_ABORT_RATE = 0.30    # >30% harness errors -> stop the run
ERROR_ABORT_MIN = 3        # guard arms only after this many attempts (no 1/1 trips)


class HarnessAbort(RuntimeError):
    """Raised when the mid-run error-rate guard trips; carries the partial rows
    so the caller can persist them instead of losing the whole set."""

    def __init__(self, rows: list[dict], n_error: int, n_attempted: int):
        super().__init__(f"harness abort: {n_error}/{n_attempted} tasks errored "
                         f"(> {ERROR_ABORT_RATE:.0%} threshold)")
        self.rows = rows
        self.n_error = n_error
        self.n_attempted = n_attempted


def arm_watchdog(page, timeout_ms: int = TASK_TIMEOUT_MS) -> None:
    """Bound every Playwright action AND navigation: a hung page raises
    TimeoutError (-> harness error row) instead of hanging the whole eval."""
    page.set_default_timeout(timeout_ms)
    page.set_default_navigation_timeout(timeout_ms)


def _summary_path(task_id: str, out_root: Path) -> Path:
    return out_root / task_id / "summary.json"


def _write(path: Path, summary: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run_guarded(task_id: str, fn, out_root: Path = RUNS_ROOT) -> dict:
    """Run one task under the harness guard and ALWAYS persist its summary.

    An `incomplete` pre-marker is written BEFORE fn runs — if the process dies
    mid-task, that marker is the surviving evidence. try/finally then rewrites
    the terminal state: done (fn returned a row) or error (fn raised; captured,
    never re-raised). Returns the summary dict."""
    path = _summary_path(task_id, out_root)
    summary = {"task_id": task_id, "harness_status": "incomplete", "row": None,
               "error": None, "written_at": _now()}
    _write(path, summary)  # pre-marker: a hard crash leaves this behind
    try:
        summary["row"] = fn()
        summary["harness_status"] = "done"
    except Exception as e:  # noqa: BLE001 — the harness must outlive any task crash
        summary["harness_status"] = "error"
        summary["error"] = f"{type(e).__name__}: {e}"
    finally:
        summary["written_at"] = _now()
        _write(path, summary)
    return summary


def load_done_summary(task_id: str, out_root: Path = RUNS_ROOT) -> dict | None:
    """Relaunch masking: a prior launch's summary iff it finished (done + row)."""
    path = _summary_path(task_id, out_root)
    if not path.exists():
        return None
    try:
        summary = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if summary.get("harness_status") == "done" and summary.get("row"):
        return summary
    return None


def should_abort(n_error: int, n_attempted: int) -> bool:
    """True once >ERROR_ABORT_RATE of attempted tasks errored, after at least
    ERROR_ABORT_MIN attempts. A single error can never abort, regardless of
    when it is accounted — without the n_error >= 2 clause, 1 error among 3
    attempts (33% > 30%) aborted or not depending on result-arrival order,
    which made the pool guard flaky on slow runners."""
    return (n_attempted >= ERROR_ABORT_MIN and n_error >= 2
            and n_error / n_attempted > ERROR_ABORT_RATE)


def scan_incomplete(task_ids: list[str], out_root: Path = RUNS_ROOT) -> list[str]:
    """Tasks whose last persisted summary is still the pre-marker — the harness
    died mid-task on a previous launch. Reported separately, never in metrics."""
    out: list[str] = []
    for tid in task_ids:
        path = _summary_path(tid, out_root)
        if not path.exists():
            continue
        try:
            summary = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if summary.get("harness_status") == "incomplete":
            out.append(tid)
    return out


# --- P0-11: parallel worker pool + session pool + subprocess-per-task isolation ---

WORKER_TASK_TIMEOUT_S = 90.0   # wall-clock per task; the parent kills the worker on breach
_POOL_POLL_S = 0.25            # parent scheduling-loop tick


def _pool_worker(worker_id: int, task_q, result_q, out_root: str, mem_dir: str) -> None:
    """Worker-pool child process: ONE persistent browser session (cold start
    paid once, amortized over every task this worker runs) with a FRESH
    context per task (no cross-task page state). Because every task executes
    in this subprocess, the parent watchdog can terminate a hung task without
    touching the harness process or sibling workers. Selector memory is
    per-worker (fresh file at session start) so repair counts stay independent
    of scheduling order."""
    from playwright.sync_api import sync_playwright

    from browser_agent.agent import BrowserAgent
    from browser_agent.memory_store import MemoryStore
    from tools.browser_eval import _row, build, uri

    out = Path(out_root)
    t0 = time.perf_counter()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        result_q.put({"kind": "session", "worker": worker_id,
                      "cold_start_ms": round((time.perf_counter() - t0) * 1000, 1)})
        mem_path = Path(mem_dir) / f"selector_memory_w{worker_id}.json"
        if mem_path.exists():
            mem_path.unlink()
        mem = MemoryStore(mem_path)
        while True:
            task = task_q.get()
            if task is None:
                break
            result_q.put({"kind": "start", "worker": worker_id, "task_id": task["task_id"]})
            context = browser.new_context(viewport={"width": 1000, "height": 800})
            page = context.new_page()
            arm_watchdog(page)

            def _one(task=task, page=page):
                page.goto(uri(task["site"]))
                agent = BrowserAgent(page, mem, site="mockshop", task_type="search",
                                     artifact_dir=out / task["task_id"])
                steps, contract = build(task)
                return _row(agent.run(task["task_id"], steps, contract), task)

            t1 = time.perf_counter()
            summary = run_guarded(task["task_id"], _one, out_root=out)
            context.close()
            result_q.put({"kind": "done", "worker": worker_id, "task_id": task["task_id"],
                          "summary": summary,
                          "busy_ms": round((time.perf_counter() - t1) * 1000, 1)})
        browser.close()


def run_pool(tasks: list[dict], workers: int, out_root: Path = RUNS_ROOT,
             mem_dir: Path | None = None, task_timeout_s: float = WORKER_TASK_TIMEOUT_S,
             worker_target=None) -> tuple[list[dict], dict]:
    """P0-11 harness worker pool: run `tasks` across `workers` child processes.

    Each worker owns one persistent browser session (session pool: cold start
    amortized across its tasks) and every task executes inside a subprocess,
    so the parent enforces a WALL-CLOCK per-task deadline by terminating the
    worker — the process-level watchdog Playwright timeouts (P0-9) cannot
    provide when the hang is outside a page call. A killed/crashed worker
    yields a terminal harness-error summary (persisted over the child's
    `incomplete` pre-marker) and is replaced by a fresh worker; the killed
    task is NOT retried (same semantics as a sequential harness error). The
    >30% error-rate abort guard applies exactly as in the sequential path.

    Returns (summaries in input task order, pool_stats for session_cost_model).
    Raises HarnessAbort carrying the partial summaries when the guard trips."""
    if worker_target is None:
        worker_target = _pool_worker
    if mem_dir is None:
        mem_dir = out_root
    if not tasks:
        return [], {"workers": workers, "wall_clock_s": 0.0, "sessions": [],
                    "watchdog_kills": [], "spawned": 0}

    ctx = mp.get_context("spawn")   # win32-safe; also the isolation boundary
    task_q = ctx.Queue()
    result_q = ctx.Queue()
    for t in tasks:
        task_q.put(t)

    procs: dict[int, mp.Process] = {}
    in_flight: dict[int, tuple[str, float]] = {}   # worker -> (task_id, deadline)
    sessions: dict[int, dict] = {}
    by_id: dict[str, dict] = {}                    # task_id -> terminal summary
    watchdog_kills: list[str] = []
    n_spawned = 0
    n_error = 0

    def _spawn():
        nonlocal n_spawned
        wid = n_spawned
        n_spawned += 1
        proc = ctx.Process(target=worker_target,
                           args=(wid, task_q, result_q, str(out_root), str(mem_dir)),
                           daemon=True)
        proc.start()
        procs[wid] = proc

    def _account_error(task_id: str, err: str):
        nonlocal n_error
        summary = {"task_id": task_id, "harness_status": "error", "row": None,
                   "error": err, "written_at": _now()}
        # terminal state written over the child's surviving `incomplete` pre-marker
        _write(_summary_path(task_id, Path(out_root)), summary)
        by_id[task_id] = summary
        n_error += 1

    def _unclaimed() -> int:
        return len(tasks) - len(by_id) - len(in_flight)

    t_wall = time.perf_counter()
    for _ in range(min(workers, len(tasks))):
        _spawn()

    try:
        while len(by_id) < len(tasks):
            # 1) drain every queued message BEFORE liveness/deadline checks, so
            #    a task that finished just under the wire is never killed late
            try:
                msg = result_q.get(timeout=_POOL_POLL_S)
            except queue.Empty:
                msg = None
            while msg is not None:
                wid = msg["worker"]
                if msg["kind"] == "session":
                    sessions[wid] = {"worker": wid, "cold_start_ms": msg["cold_start_ms"],
                                     "tasks": 0, "busy_ms": 0.0}
                elif msg["kind"] == "start":
                    in_flight[wid] = (msg["task_id"], time.monotonic() + task_timeout_s)
                elif msg["kind"] == "done":
                    in_flight.pop(wid, None)
                    if msg["task_id"] not in by_id:    # ignore a late done after a kill
                        by_id[msg["task_id"]] = msg["summary"]
                        if msg["summary"]["harness_status"] == "error":
                            n_error += 1
                        s = sessions.setdefault(wid, {"worker": wid, "cold_start_ms": 0.0,
                                                      "tasks": 0, "busy_ms": 0.0})
                        s["tasks"] += 1
                        s["busy_ms"] += msg.get("busy_ms", 0.0)
                try:
                    msg = result_q.get_nowait()
                except queue.Empty:
                    msg = None

            # 2) watchdog: wall-clock deadline breached -> kill worker, error row
            now = time.monotonic()
            for wid in [w for w, (_, dl) in list(in_flight.items()) if now > dl]:
                task_id, _ = in_flight.pop(wid)
                procs[wid].terminate()
                procs[wid].join(timeout=5)
                del procs[wid]
                watchdog_kills.append(task_id)
                _account_error(task_id, f"WatchdogTimeout: task exceeded "
                                        f"{task_timeout_s:.0f}s wall clock; worker terminated")

            # 3) crashed workers: died without a done message
            for wid in [w for w, p in procs.items() if not p.is_alive()]:
                if wid in in_flight:
                    task_id, _ = in_flight.pop(wid)
                    _account_error(task_id, "WorkerCrash: worker process died mid-task")
                del procs[wid]

            if should_abort(n_error, len(by_id)):
                raise HarnessAbort([by_id[t["task_id"]] for t in tasks if t["task_id"] in by_id],
                                   n_error, len(by_id))

            # 4) keep concurrency: respawn while unclaimed tasks remain
            while _unclaimed() > 0 and len(procs) < workers:
                if n_spawned > workers + len(tasks):
                    raise RuntimeError("worker pool respawn budget exhausted "
                                       "(workers keep dying before finishing a task)")
                _spawn()
    except BaseException:
        for proc in procs.values():
            if proc.is_alive():
                proc.terminate()
        for proc in procs.values():
            proc.join(timeout=5)
        raise

    # graceful shutdown: one sentinel per alive worker, then join
    alive = [p for p in procs.values() if p.is_alive()]
    for _ in alive:
        task_q.put(None)
    for proc in alive:
        proc.join(timeout=10)
        if proc.is_alive():
            proc.terminate()

    pool_stats = {"workers": workers,
                  "wall_clock_s": round(time.perf_counter() - t_wall, 2),
                  "sessions": sorted(sessions.values(), key=lambda s: s["worker"]),
                  "watchdog_kills": watchdog_kills,
                  "spawned": n_spawned}
    return [by_id[t["task_id"]] for t in tasks], pool_stats


def session_cost_model(pool_stats: dict, n_done: int) -> dict:
    """Multi-session cost model (P0-11): concurrency x per-session cost/latency.

    serial_estimate_s = one (mean) cold start + every task's busy time back to
    back — what the pre-P0-11 single-session loop would have paid — so the
    speedup number is honest about pool overhead (process spawn + import +
    per-worker cold start), not a theoretical workers-x claim. sessions_launched
    includes watchdog respawns: a kill re-pays a cold start and the model shows it."""
    sessions = pool_stats["sessions"]
    wall = pool_stats["wall_clock_s"]
    cold = [s["cold_start_ms"] for s in sessions]
    mean_cold_ms = sum(cold) / len(cold) if cold else 0.0
    busy_s = sum(s["busy_ms"] for s in sessions) / 1000
    serial_estimate_s = mean_cold_ms / 1000 + busy_s
    return {
        "concurrency": pool_stats["workers"],
        "sessions_launched": len(sessions),
        "watchdog_kills": len(pool_stats["watchdog_kills"]),
        "tasks_done": n_done,
        "wall_clock_s": wall,
        "throughput_tasks_per_min": round(n_done / wall * 60, 2) if wall else None,
        "cold_start_ms_per_session_mean": round(mean_cold_ms, 1),
        "cold_start_ms_total": round(sum(cold), 1),
        "cold_start_amortized_ms_per_task": round(sum(cold) / n_done, 1) if n_done else None,
        "busy_s_total": round(busy_s, 2),
        "serial_estimate_s": round(serial_estimate_s, 2),
        "speedup_vs_serial_estimate": round(serial_estimate_s / wall, 2) if wall else None,
        "per_session": [{"worker": s["worker"], "tasks": s["tasks"],
                         "busy_ms": round(s["busy_ms"], 1),
                         "utilization": round(s["busy_ms"] / (wall * 1000), 3) if wall else None}
                        for s in sessions],
    }


def harness_report(rows: list[dict], n_planned: int, aborted: bool = False) -> dict:
    """Harness-layer accounting block, separate from the verdict metrics.
    Rows without a harness_status key (legacy/pure-logic rows) count as done."""
    done = [r for r in rows if r.get("harness_status", "done") == "done"]
    error = [r for r in rows if r.get("harness_status") == "error"]
    return {
        "planned": n_planned,
        "done": len(done),
        "error": len(error),
        "resumed": sum(bool(r.get("resumed")) for r in done),
        "not_run": n_planned - len(rows),
        "aborted": aborted,
        "error_rate": round(len(error) / len(rows), 3) if rows else 0.0,
        "error_task_ids": [r["task_id"] for r in error],
    }
