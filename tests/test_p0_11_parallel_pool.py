"""P0-11 scalability tests: worker pool + session pool + subprocess isolation.

Pure-logic tests cover the multi-session cost model math. Pool tests drive
run_pool with lightweight stub workers (no browser): full-set completion with
input-order results, harness-error capture inside a worker, the wall-clock
watchdog kill + respawn path, and the >30% abort guard. One integration test
runs the real parallel Script-Mode pass (2 workers, real Playwright sessions)
end to end, including resume masking on relaunch.

Stub workers must be module-level so the spawn context can pickle them.
"""

import json
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import browser_eval as be  # noqa: E402 — same import style as test_p0_9

import tools.eval_worker as ew  # noqa: E402


# --- stub workers (top-level: spawn pickles them by qualified name) ---
def stub_worker(worker_id, task_q, result_q, out_root, mem_dir):
    """Browser-free pool worker honoring the run_pool message protocol.
    Task flags: {'boom': True} raises inside the guard (harness error row);
    {'hang': True} sleeps far past the watchdog deadline (parent must kill)."""
    result_q.put({"kind": "session", "worker": worker_id, "cold_start_ms": 5.0})
    while True:
        task = task_q.get()
        if task is None:
            return
        result_q.put({"kind": "start", "worker": worker_id, "task_id": task["task_id"]})

        def _one(task=task):
            if task.get("hang"):
                time.sleep(60)
            if task.get("boom"):
                raise ValueError("kaput")
            return {"task_id": task["task_id"], "status": "pass"}

        t0 = time.perf_counter()
        summary = ew.run_guarded(task["task_id"], _one, out_root=Path(out_root))
        result_q.put({"kind": "done", "worker": worker_id, "task_id": task["task_id"],
                      "summary": summary,
                      "busy_ms": round((time.perf_counter() - t0) * 1000, 1)})


def _tasks(n, **flags):
    return [{"task_id": f"t-{i}", **flags} for i in range(n)]


# --- session_cost_model: pure math ---
def test_session_cost_model_math():
    pool_stats = {
        "workers": 2, "wall_clock_s": 5.0, "watchdog_kills": [], "spawned": 2,
        "sessions": [
            {"worker": 0, "cold_start_ms": 1000.0, "tasks": 4, "busy_ms": 4000.0},
            {"worker": 1, "cold_start_ms": 1000.0, "tasks": 4, "busy_ms": 4000.0},
        ],
    }
    m = ew.session_cost_model(pool_stats, n_done=8)
    assert m["concurrency"] == 2
    assert m["sessions_launched"] == 2
    assert m["tasks_done"] == 8
    assert m["throughput_tasks_per_min"] == 96.0          # 8 tasks / 5s
    assert m["cold_start_ms_per_session_mean"] == 1000.0
    assert m["cold_start_ms_total"] == 2000.0
    assert m["cold_start_amortized_ms_per_task"] == 250.0  # 2000 / 8
    assert m["busy_s_total"] == 8.0
    assert m["serial_estimate_s"] == 9.0                   # 1s cold + 8s busy
    assert m["speedup_vs_serial_estimate"] == 1.8          # 9 / 5
    assert m["per_session"][0]["utilization"] == 0.8       # 4000 / 5000


def test_session_cost_model_empty_run_has_no_divisions_by_zero():
    m = ew.session_cost_model(
        {"workers": 2, "wall_clock_s": 0.0, "sessions": [], "watchdog_kills": []},
        n_done=0)
    assert m["throughput_tasks_per_min"] is None
    assert m["cold_start_amortized_ms_per_task"] is None
    assert m["speedup_vs_serial_estimate"] is None
    assert m["sessions_launched"] == 0


def test_run_pool_empty_task_list_short_circuits():
    summaries, stats = ew.run_pool([], workers=2, worker_target=stub_worker)
    assert summaries == []
    assert stats["sessions"] == [] and stats["spawned"] == 0


# --- pool scheduling with stub workers ---
def test_pool_runs_all_tasks_in_input_order(tmp_path):
    tasks = _tasks(5)
    summaries, stats = ew.run_pool(tasks, workers=2, out_root=tmp_path,
                                   worker_target=stub_worker)
    assert [s["task_id"] for s in summaries] == [t["task_id"] for t in tasks]
    assert all(s["harness_status"] == "done" for s in summaries)
    for t in tasks:  # per-task summary.json persisted by the guard in the child
        disk = json.loads((tmp_path / t["task_id"] / "summary.json").read_text(encoding="utf-8"))
        assert disk["harness_status"] == "done"
    # sessions are reused (5 tasks never spawn 5 sessions); at most one per
    # worker, but a fast worker may drain the queue before the second spawns
    assert 1 <= len(stats["sessions"]) <= 2
    assert sum(s["tasks"] for s in stats["sessions"]) == 5
    assert stats["watchdog_kills"] == []


def test_pool_captures_worker_task_error_without_killing(tmp_path):
    tasks = _tasks(3) + [{"task_id": "t-boom", "boom": True}]
    summaries, stats = ew.run_pool(tasks, workers=2, out_root=tmp_path,
                                   worker_target=stub_worker)
    by = {s["task_id"]: s for s in summaries}
    assert by["t-boom"]["harness_status"] == "error"
    assert "ValueError: kaput" in by["t-boom"]["error"]
    assert all(by[f"t-{i}"]["harness_status"] == "done" for i in range(3))
    assert stats["watchdog_kills"] == []        # a captured raise is not a hang


def test_pool_watchdog_kills_hung_worker_and_respawns(tmp_path):
    # workers=1 makes the respawn deterministic: the only worker hangs on the
    # 4th task (after 3 successes, so 1 error = 20% stays under the abort
    # guard), gets killed, and a replacement worker must finish the last task
    tasks = _tasks(3) + [{"task_id": "t-hang", "hang": True}, {"task_id": "t-last"}]
    summaries, stats = ew.run_pool(tasks, workers=1, out_root=tmp_path,
                                   task_timeout_s=2.0, worker_target=stub_worker)
    by = {s["task_id"]: s for s in summaries}
    assert by["t-hang"]["harness_status"] == "error"
    assert "WatchdogTimeout" in by["t-hang"]["error"]
    # the parent's terminal error summary overwrote the child's `incomplete` pre-marker
    disk = json.loads((tmp_path / "t-hang" / "summary.json").read_text(encoding="utf-8"))
    assert disk["harness_status"] == "error"
    assert "WatchdogTimeout" in disk["error"]
    assert all(by[f"t-{i}"]["harness_status"] == "done" for i in range(3))
    assert by["t-last"]["harness_status"] == "done"   # ran on the replacement worker
    assert stats["watchdog_kills"] == ["t-hang"]
    assert stats["spawned"] == 2                # replacement worker after the kill


def test_pool_abort_guard_raises_with_partial_summaries(tmp_path):
    tasks = [{"task_id": f"t-{i}", "boom": True} for i in range(4)]
    with pytest.raises(ew.HarnessAbort) as exc:
        ew.run_pool(tasks, workers=2, out_root=tmp_path, worker_target=stub_worker)
    ab = exc.value
    assert ab.n_error == ab.n_attempted >= ew.ERROR_ABORT_MIN
    assert all(s["harness_status"] == "error" for s in ab.rows)


# --- integration: real parallel Script-Mode pass (2 browser sessions) ---
@pytest.mark.integration
def test_parallel_pass_end_to_end_with_resume(tmp_path, monkeypatch):
    pytest.importorskip("playwright.sync_api")
    if not (ROOT / "data" / "mock_sites" / "v1" / "index.html").exists():
        pytest.skip("mock sites missing")
    monkeypatch.setattr(be, "OUT", tmp_path / "runs")
    (tmp_path / "runs").mkdir(parents=True)
    spec = json.loads(be.TASKS.read_text(encoding="utf-8"))
    tasks = spec["tasks"][:4]

    rows, scal = be.run_parallel_pass(tasks, workers=2)
    assert [r["task_id"] for r in rows] == [t["task_id"] for t in tasks]
    assert all(r["harness_status"] == "done" for r in rows)
    assert all(r["correct"] for r in rows)      # parallel run matches ground truth
    for t in tasks:
        disk = json.loads((tmp_path / "runs" / t["task_id"] / "summary.json")
                          .read_text(encoding="utf-8"))
        assert disk["harness_status"] == "done"
    assert scal["concurrency"] == 2
    assert scal["sessions_launched"] >= 2       # one persistent session per worker
    assert scal["tasks_done"] == 4
    assert scal["cold_start_ms_per_session_mean"] > 0

    # relaunch with resume: every task masked, no session launched at all
    rows2, scal2 = be.run_parallel_pass(tasks, workers=2, resume=True)
    assert all(r.get("resumed") for r in rows2)
    assert scal2["sessions_launched"] == 0 and scal2["tasks_done"] == 0
