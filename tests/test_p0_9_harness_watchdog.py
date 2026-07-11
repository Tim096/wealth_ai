"""P0-9 harness persistence + watchdog tests.

Pure-logic tests cover the guard trichotomy (done/error/incomplete), relaunch
masking, the >30% error-rate abort, and the metrics/harness axis separation.
Two integration tests drive the real Script-Mode runner: one proves per-task
summary.json persistence + resume masking (a masked task is NOT re-executed),
one proves a crashing task set aborts with the partial rows persisted."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import browser_eval as be  # noqa: E402 — same import style as test_passk.py

import tools.eval_worker as ew  # noqa: E402
import tools.impossible_tasks as it  # noqa: E402
import tools.open_ended_tasks as ot  # noqa: E402


# --- run_guarded: the done/error/incomplete trichotomy ---
def test_run_guarded_done_persists_row(tmp_path):
    s = ew.run_guarded("t-done", lambda: {"status": "pass"}, out_root=tmp_path)
    assert s["harness_status"] == "done"
    assert s["row"] == {"status": "pass"}
    assert s["error"] is None
    disk = json.loads((tmp_path / "t-done" / "summary.json").read_text(encoding="utf-8"))
    assert disk["harness_status"] == "done"
    assert disk["row"] == {"status": "pass"}


def test_run_guarded_error_is_captured_not_reraised(tmp_path):
    def boom():
        raise ValueError("kaput")
    s = ew.run_guarded("t-err", boom, out_root=tmp_path)   # must NOT raise
    assert s["harness_status"] == "error"
    assert s["row"] is None
    assert "ValueError: kaput" in s["error"]
    disk = json.loads((tmp_path / "t-err" / "summary.json").read_text(encoding="utf-8"))
    assert disk["harness_status"] == "error"


def test_run_guarded_pre_marker_written_before_fn(tmp_path):
    # a hard crash mid-task leaves the `incomplete` pre-marker as the only
    # surviving evidence — prove it is on disk BEFORE the task fn runs
    seen = {}

    def fn():
        seen["marker"] = json.loads(
            (tmp_path / "t-pre" / "summary.json").read_text(encoding="utf-8"))
        return {"ok": 1}

    ew.run_guarded("t-pre", fn, out_root=tmp_path)
    assert seen["marker"]["harness_status"] == "incomplete"
    assert seen["marker"]["row"] is None


# --- relaunch masking ---
def test_load_done_summary_masks_only_done(tmp_path):
    ew.run_guarded("ok", lambda: {"status": "pass"}, out_root=tmp_path)
    ew.run_guarded("bad", lambda: 1 / 0, out_root=tmp_path)
    assert ew.load_done_summary("ok", out_root=tmp_path)["row"] == {"status": "pass"}
    assert ew.load_done_summary("bad", out_root=tmp_path) is None      # error: rerun it
    assert ew.load_done_summary("missing", out_root=tmp_path) is None  # never ran


def test_scan_incomplete_finds_only_pre_markers(tmp_path):
    ew.run_guarded("fin", lambda: {"status": "pass"}, out_root=tmp_path)
    (tmp_path / "died").mkdir()
    (tmp_path / "died" / "summary.json").write_text(json.dumps(
        {"task_id": "died", "harness_status": "incomplete", "row": None, "error": None}),
        encoding="utf-8")
    assert ew.scan_incomplete(["fin", "died", "never-ran"], out_root=tmp_path) == ["died"]


# --- abort guard ---
def test_should_abort_thresholds():
    assert ew.should_abort(1, 1) is False   # below ERROR_ABORT_MIN: never trips
    assert ew.should_abort(2, 2) is False
    assert ew.should_abort(3, 3) is True    # 100% > 30% at min attempts
    assert ew.should_abort(1, 3) is False   # a single error never aborts (order-independent)
    assert ew.should_abort(1, 4) is False   # 25% <= 30%
    assert ew.should_abort(3, 10) is False  # exactly 30% is NOT > 30%
    assert ew.should_abort(4, 10) is True


def test_harness_abort_carries_partial_rows():
    rows = [{"task_id": "a", "harness_status": "error"}]
    ab = ew.HarnessAbort(rows, 3, 4)
    assert ab.rows is rows
    assert "3/4" in str(ab)


# --- harness axis separate from verdict metrics ---
def test_harness_report_counts():
    rows = [
        {"task_id": "a", "harness_status": "done"},
        {"task_id": "b", "harness_status": "done", "resumed": True},
        {"task_id": "c", "harness_status": "error"},
        {"task_id": "d"},   # legacy row without the key counts as done
    ]
    h = ew.harness_report(rows, n_planned=6, aborted=True)
    assert h["planned"] == 6
    assert h["done"] == 3
    assert h["error"] == 1
    assert h["resumed"] == 1
    assert h["not_run"] == 2
    assert h["aborted"] is True
    assert h["error_task_ids"] == ["c"]
    assert h["error_rate"] == 0.25


def _done_row(task_id, status="pass", expected="pass"):
    return {"task_id": task_id, "layer": "l", "site": "v1", "status": status,
            "expected": expected, "correct": status == expected, "confidence": 1.0,
            "repairs": 0, "false_positive": False, "trace_complete": True,
            "latency_ms": 10.0, "verifier_reason": "", "harness_status": "done"}


def test_compute_metrics_excludes_harness_error_rows():
    rows = [_done_row("a"), _done_row("b"),
            {"task_id": "c", "layer": "l", "site": "v1", "expected": "pass",
             "harness_status": "error", "harness_error": "TimeoutError: hang"}]
    m = be.compute_metrics(rows)
    assert m["tasks"] == 2                      # error row never enters metrics
    assert m["verdict_accuracy"] == 1.0
    assert be.compute_metrics([rows[2]]) == {"tasks": 0}


def test_impossible_summarize_excludes_harness_error_rows():
    rows = [
        {"task_id": "a", "kind": "product_absent", "expected": "fail", "status": "fail",
         "matches_expected": True, "silent_failure": False, "harness_status": "done"},
        {"task_id": "b", "kind": "product_absent", "expected": "fail",
         "harness_status": "error", "harness_error": "boom"},
    ]
    m = it.summarize(rows)
    assert m["n_impossible"] == 1               # harness error is not a verdict
    assert m["silent_failures"] == 0


def test_open_ended_crash_row_stays_a_measured_crash():
    # design decision: for open-ended tasks a raise IS the measured failure
    # mode (FIX-1), so the harness-error row still counts in the crash metric
    row = {"task_id": "a", "site": "v1", "expected": "unknown", "status": "error",
           "crashed": True, "matches_expected": False, "vacuous_pass": False,
           "steps_executed": 0, "harness_status": "error", "harness_error": "boom"}
    m = ot.summarize([row])
    assert m["crashes"] == 1


def test_arm_watchdog_sets_both_timeouts():
    class Page:
        def __init__(self):
            self.calls = {}

        def set_default_timeout(self, ms):
            self.calls["action"] = ms

        def set_default_navigation_timeout(self, ms):
            self.calls["nav"] = ms

    page = Page()
    ew.arm_watchdog(page)
    assert page.calls == {"action": ew.TASK_TIMEOUT_MS, "nav": ew.TASK_TIMEOUT_MS}


# --- integration: real runner, persistence + resume masking ---
@pytest.mark.integration
def test_script_pass_persists_summaries_and_resume_masks(tmp_path, monkeypatch):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    if not (ROOT / "data" / "mock_sites" / "v1" / "index.html").exists():
        pytest.skip("mock sites missing")
    monkeypatch.setattr(be, "OUT", tmp_path / "runs")
    spec = json.loads(be.TASKS.read_text(encoding="utf-8"))
    tasks = spec["tasks"][:2]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1000, "height": 800})
        rows = be.run_script_pass(page, tasks, tmp_path / "mem.json")
        # every task persisted its own summary.json with harness_status done
        for t in tasks:
            disk = json.loads(
                (tmp_path / "runs" / t["task_id"] / "summary.json").read_text(encoding="utf-8"))
            assert disk["harness_status"] == "done"
            assert disk["row"]["task_id"] == t["task_id"]
        assert all(r["harness_status"] == "done" for r in rows)

        # tamper a persisted row; a resumed run must return the tampered copy
        # (proof the task was masked, not re-executed)
        sp = tmp_path / "runs" / tasks[0]["task_id"] / "summary.json"
        s = json.loads(sp.read_text(encoding="utf-8"))
        s["row"]["tamper_marker"] = True
        sp.write_text(json.dumps(s), encoding="utf-8")

        rows2 = be.run_script_pass(page, tasks, tmp_path / "mem.json", resume=True)
        browser.close()

    assert rows2[0]["tamper_marker"] is True
    assert all(r.get("resumed") for r in rows2)


# --- integration: >30% harness errors abort with partial rows persisted ---
@pytest.mark.integration
def test_script_pass_aborts_on_error_burst(tmp_path, monkeypatch):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    monkeypatch.setattr(be, "OUT", tmp_path / "runs")
    # nonexistent mock site -> page.goto raises -> harness error per task
    bad = [{"task_id": f"bad-{i}", "layer": "l", "site": "no_such_site",
            "query": "x", "success_text": ["x"], "expect_status": "pass"}
           for i in range(4)]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1000, "height": 800})
        with pytest.raises(ew.HarnessAbort) as exc:
            be.run_script_pass(page, bad, tmp_path / "mem.json")
        browser.close()

    ab = exc.value
    assert ab.n_error == ab.n_attempted == ew.ERROR_ABORT_MIN   # stopped at the guard
    assert len(ab.rows) == ew.ERROR_ABORT_MIN                   # partial rows carried out
    for r in ab.rows:
        assert r["harness_status"] == "error"
        disk = json.loads(
            (tmp_path / "runs" / r["task_id"] / "summary.json").read_text(encoding="utf-8"))
        assert disk["harness_status"] == "error"                # persisted, not lost
