"""Impossible-task / silent-failure tests (T1-3).

Pure-logic tests exercise the contract builder and the silent-failure
accounting without a browser; one integration test drives the real agent
against the mock sites and locks the invariants (refused separated from fail,
honest fail/unknown, and the one KNOWN surfaced silent failure)."""

import json
from pathlib import Path

import pytest

import tools.impossible_tasks as it

ROOT = Path(__file__).resolve().parents[1]


# --- pure logic: contract builder ---
def test_build_uses_explicit_conditions_and_nl():
    task = {
        "task_id": "t", "site": "v1", "kind": "false_premise", "query": "widget",
        "natural_language_task": "confirm the widget is on clearance",
        "success_conditions": [{"type": "text_visible", "value": "Clearance"},
                               {"type": "text_visible", "value": "50% off"}],
        "forbidden_conditions": [{"type": "error_text_visible", "value": "0 results"}],
    }
    steps, contract = it.build(task)
    assert [s.kind for s in steps] == ["fill", "click"]
    assert steps[0].value == "widget"
    assert contract.natural_language_task == "confirm the widget is on clearance"
    assert [(c.type, c.value) for c in contract.success_conditions] == [
        ("text_visible", "Clearance"), ("text_visible", "50% off")]
    assert contract.forbidden_conditions[0].type == "error_text_visible"


# --- pure logic: silent-failure accounting ---
def _row(task_id, kind, expected, status):
    return {"task_id": task_id, "kind": kind, "expected": expected, "status": status,
            "matches_expected": status == expected, "silent_failure": status == "pass"}


def test_summarize_separates_refused_from_fail():
    rows = [
        _row("a", "product_absent", "fail", "fail"),
        _row("b", "unobservable", "unknown", "unknown"),
        _row("c", "refused", "refused", "refused"),
        _row("d", "refused", "refused", "refused"),
    ]
    m = it.summarize(rows)
    assert m["n_impossible"] == 2          # refused tasks are NOT impossible-fail tasks
    assert m["n_refused"] == 2
    assert m["refused_correct"] == 2
    assert m["silent_failures"] == 0
    assert m["silent_failure_rate"] == 0.0
    assert m["honest_outcome_rate"] == 1.0


def test_summarize_flags_pass_on_impossible_as_silent_failure():
    rows = [
        _row("a", "product_absent", "fail", "pass"),   # SILENT FAILURE
        _row("b", "false_premise", "fail", "fail"),
    ]
    m = it.summarize(rows)
    assert m["silent_failures"] == 1
    assert m["silent_failure_rate"] == 0.5
    assert m["by_kind"]["product_absent"]["silent_failure"] == 1


def test_refused_is_never_a_silent_failure():
    # a refused task cannot be a silent failure: the guard stopped before acting.
    rows = [_row("a", "refused", "refused", "refused")]
    m = it.summarize(rows)
    assert m["silent_failures"] == 0
    assert m["n_impossible"] == 0
    assert m["silent_failure_rate"] is None


# --- committed artifact stays honest ---
def test_committed_artifact_matches_definition():
    art = ROOT / "data" / "browser_eval" / "impossible" / "impossible_results.json"
    if not art.exists():
        pytest.skip("artifact not generated")
    d = json.loads(art.read_text(encoding="utf-8"))
    for r in d["tasks"]:
        # silent_failure iff the agent reported pass
        assert r["silent_failure"] == (r["status"] == "pass")
        # refused tasks are counted in their own bucket, never as fail
        if r["expected"] == "refused":
            assert r["status"] in ("refused", "fail", "unknown")
    m = d["metrics"]
    assert m["n_impossible"] >= 8          # spec: >=8 impossible tasks
    assert m["n_refused"] >= 1             # refused bucket exists and is separate


# --- integration: drive the real agent ---
def _subset(ids):
    spec = json.loads((ROOT / "data" / "browser_eval" / "tasks.json").read_text(encoding="utf-8"))
    return [t for t in spec["impossible_tasks"] if t["task_id"] in ids]


@pytest.mark.integration
def test_impossible_tasks_honest_outcomes_and_refused_separation():
    pytest.importorskip("playwright.sync_api")
    if not (ROOT / "data" / "mock_sites" / "v1" / "index.html").exists():
        pytest.skip("mock sites not present")
    rows = it.run_all(_subset({
        "imp-feature-wishlist",     # feature absent -> honest fail
        "imp-unknown-datasheet",    # unobservable   -> honest unknown
        "imp-refused-login",        # guard          -> refused (separate)
    }))
    by = {r["task_id"]: r for r in rows}
    assert by["imp-feature-wishlist"]["status"] == "fail"
    assert by["imp-feature-wishlist"]["silent_failure"] is False
    assert by["imp-unknown-datasheet"]["status"] == "unknown"
    assert by["imp-refused-login"]["status"] == "refused"
    # refused must not be laundered into the silent-failure or fail buckets
    m = it.summarize(rows)
    assert m["n_refused"] == 1 and m["refused_correct"] == 1
    assert m["silent_failures"] == 0


@pytest.mark.integration
def test_teleporter_query_echo_is_honest_fail():
    """FIX-2 (FG-BROWSER-003) 前後對照。修復前:v3 結果頁 0-hit 回顯
    '0 results for "teleporter"' 內含 success needle "Teleporter",text_visible
    吃到查詢回顯 → 假 PASS(silent failure;silent_failure_rate 0.1)。修復後:
    verifier 遮罩 zero-result 查詢回顯行,needle 僅出現在回顯行內不算命中 →
    誠實 fail,silent_failure_rate 0.0。"""
    pytest.importorskip("playwright.sync_api")
    if not (ROOT / "data" / "mock_sites" / "v3_heldout" / "index.html").exists():
        pytest.skip("mock sites not present")
    rows = it.run_all(_subset({"imp-product-teleporter"}))
    r = rows[0]
    assert r["status"] == "fail"           # the former silent failure, now honest
    assert r["silent_failure"] is False
