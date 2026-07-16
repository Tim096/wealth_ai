"""Open-ended task tests (FIX-1): zero success conditions is a LEGAL, honest
contract — the run completes, the trace is recorded, and the only correct
verdict is `unknown` (never a crash, never a vacuous pass).

Origin bug: the honest preflight answer (empty conditions) hit the contract
schema's min_length=1 → ValidationError → the whole run became ERROR. The
system punished honesty; these tests lock the fixed behaviour."""

import json
from pathlib import Path

import pytest

import tools.impossible_tasks as it
import tools.open_ended_tasks as ot

ROOT = Path(__file__).resolve().parents[1]


# --- pure logic: the builder accepts the honest empty-condition task ---
def test_build_accepts_zero_success_conditions():
    """修復前:it.build() 對空 success_conditions 會在 BrowserTaskContract
    拋 ValidationError(min_length=1)。修復後:合法建構,零條件、forbidden 保留。"""
    task = {
        "task_id": "open-t", "site": "v1", "kind": "open_ended", "query": "widget",
        "natural_language_task": "Browse and see what looks interesting",
        "success_conditions": [],
        "forbidden_conditions": [{"type": "error_text_visible", "value": "server error"}],
    }
    steps, contract = it.build(task)
    assert contract.success_conditions == []
    assert contract.forbidden_conditions[0].type == "error_text_visible"
    assert [s.kind for s in steps] == ["fill", "click"]


# --- pure logic: honesty accounting ---
def _row(task_id, status, crashed=False, steps=2):
    return {"task_id": task_id, "site": "v1", "expected": "unknown", "status": status,
            "crashed": crashed, "matches_expected": status == "unknown",
            "vacuous_pass": status == "pass", "steps_executed": steps}


def test_summarize_counts_honest_unknown():
    m = ot.summarize([_row("a", "unknown"), _row("b", "unknown"), _row("c", "unknown")])
    assert m["n_open_ended"] == 3
    assert m["crashes"] == 0
    assert m["vacuous_passes"] == 0
    assert m["honest_unknown"] == 3
    assert m["honest_unknown_rate"] == 1.0
    assert m["traces_recorded"] == 3


def test_summarize_flags_vacuous_pass_and_crash():
    m = ot.summarize([_row("a", "pass"),                       # vacuous pass
                      _row("b", "error", crashed=True, steps=0)])
    assert m["vacuous_passes"] == 1
    assert m["crashes"] == 1
    assert m["honest_unknown"] == 0


# --- committed artifact stays honest ---
def test_committed_artifact_all_unknown_zero_crash_zero_vacuous_pass():
    art = ROOT / "data" / "browser_eval" / "open_ended" / "open_ended_results.json"
    if not art.exists():
        pytest.skip("artifact not generated")
    d = json.loads(art.read_text(encoding="utf-8"))
    m = d["metrics"]
    assert m["n_open_ended"] >= 3
    assert m["crashes"] == 0
    assert m["vacuous_passes"] == 0
    assert m["honest_unknown"] == m["n_open_ended"]
    for r in d["tasks"]:
        assert r["status"] == "unknown"
        assert r["steps_executed"] > 0        # unknown 不是不做事:trace 有步驟


# --- integration: drive the real agent on one open-ended task ---
@pytest.mark.integration
def test_open_ended_task_end_to_end_unknown_not_error():
    pytest.importorskip("playwright.sync_api")
    if not (ROOT / "data" / "mock_sites" / "v1" / "index.html").exists():
        pytest.skip("mock sites not present")
    spec = json.loads((ROOT / "data" / "browser_eval" / "tasks.json").read_text(encoding="utf-8"))
    tasks = [t for t in spec["open_ended_tasks"] if t["task_id"] == "open-browse-interesting"]
    rows = ot.run_all(tasks)
    r = rows[0]
    assert r["crashed"] is False
    assert r["status"] == "unknown"
    assert r["vacuous_pass"] is False
    assert r["steps_executed"] > 0
    assert "open-ended" in r["verifier_reason"]
