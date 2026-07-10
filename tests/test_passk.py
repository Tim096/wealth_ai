"""pass@k / flakiness aggregation tests (T1-5).

The aggregation is a pure function over per-task status lists, so the core
contract is tested with NO browser. One integration test drives the real
Script-Mode runner with --repeat to confirm the measured determinism claim.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import browser_eval as be  # noqa: E402


def _by(**tasks):
    """{task_id: {expected, statuses}} builder for aggregate_passk."""
    return {tid: {"expected": exp, "statuses": st} for tid, (exp, st) in tasks.items()}


# --- deterministic Script-Mode property: pass@1 == pass@k, flaky_rate 0 ---
def test_deterministic_all_pass_pass1_equals_passk():
    agg = be.aggregate_passk(
        _by(a=("pass", ["pass", "pass", "pass"]),
            b=("pass", ["pass", "pass", "pass"])), k=3)
    s = agg["summary"]
    assert s["pass_at_1"] == 1.0
    assert s["pass_at_k"] == 1.0
    assert s["pass_at_1"] == s["pass_at_k"]
    assert s["flaky_rate"] == 0.0
    assert s["deterministic"] is True
    assert s["flaky_tasks"] == []


def test_adversarial_expected_fail_excluded_from_passk_but_counts_consistency():
    # a consistently-correct FAIL task must not drag pass@k (excluded) yet must
    # count as consistent (not flaky) in the all-task stability signal.
    agg = be.aggregate_passk(
        _by(good=("pass", ["pass", "pass"]),
            adv=("fail", ["fail", "fail"])), k=2)
    s = agg["summary"]
    assert s["n_tasks"] == 2
    assert s["n_solvable"] == 1          # only the expected-pass task
    assert s["pass_at_1"] == 1.0
    assert s["pass_at_k"] == 1.0
    assert s["flaky_rate"] == 0.0        # adversarial task is consistent
    adv = next(t for t in agg["per_task"] if t["task_id"] == "adv")
    assert "pass_at_1" not in adv        # not scored for pass@k
    assert adv["consistent"] is True


# --- flakiness: a task whose verdict differs across passes ---
def test_flaky_task_lifts_passk_above_pass1_and_flags_it():
    # one solvable task passes on only 2 of 3 attempts -> pass@1 < pass@k,
    # and it is surfaced as flaky.
    agg = be.aggregate_passk(
        _by(flaky=("pass", ["pass", "fail", "pass"]),
            solid=("pass", ["pass", "pass", "pass"])), k=3)
    s = agg["summary"]
    # pass@1 = mean(round(2/3,3)=0.667, 1.0) ; pass@k = mean(solved, solved) = 1.0
    assert s["pass_at_1"] == round((0.667 + 1) / 2, 3)
    assert s["pass_at_k"] == 1.0
    assert s["pass_at_k"] > s["pass_at_1"]
    assert s["flaky_rate"] == 0.5
    assert s["flaky_tasks"] == ["flaky"]
    assert s["deterministic"] is False


def test_never_solved_task_zero_passk():
    agg = be.aggregate_passk(_by(a=("pass", ["fail", "fail"])), k=2)
    s = agg["summary"]
    assert s["pass_at_1"] == 0.0
    assert s["pass_at_k"] == 0.0
    assert s["flaky_rate"] == 0.0        # consistently wrong is not flaky


def test_no_solvable_tasks_yields_none_passk():
    agg = be.aggregate_passk(_by(adv=("fail", ["fail", "fail"])), k=2)
    s = agg["summary"]
    assert s["n_solvable"] == 0
    assert s["pass_at_1"] is None
    assert s["pass_at_k"] is None
    assert s["verdict_consistency"] == 1.0


def test_collate_folds_passes_by_task():
    p1 = [{"task_id": "a", "expected": "pass", "status": "pass"},
          {"task_id": "b", "expected": "fail", "status": "fail"}]
    p2 = [{"task_id": "a", "expected": "pass", "status": "fail"},
          {"task_id": "b", "expected": "fail", "status": "fail"}]
    by = be.collate([p1, p2])
    assert by["a"] == {"expected": "pass", "statuses": ["pass", "fail"]}
    assert by["b"] == {"expected": "fail", "statuses": ["fail", "fail"]}


# --- integration: the measured determinism claim on the real runner ---
@pytest.mark.integration
def test_script_mode_repeat_is_deterministic(tmp_path):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    if not (be.ROOT / "data" / "mock_sites" / "v1" / "index.html").exists():
        pytest.skip("mock sites missing")
    spec = __import__("json").loads(be.TASKS.read_text(encoding="utf-8"))
    tasks = spec["tasks"]
    mem = tmp_path / "mem.json"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1000, "height": 800})
        passes = [be.run_script_pass(page, tasks, mem) for _ in range(3)]
        browser.close()
    agg = be.aggregate_passk(be.collate(passes), k=3)
    s = agg["summary"]
    assert s["deterministic"] is True            # measured, not asserted a priori
    assert s["flaky_rate"] == 0.0
    assert s["pass_at_1"] == s["pass_at_k"]
