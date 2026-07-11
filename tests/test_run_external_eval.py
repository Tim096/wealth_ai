"""Tests for tools/run_external_eval.py — the productized external live-task
eval runner. Pure functions (classification, row shaping, success-rate rollup)
are unit-tested offline; the agent-driving path is exercised by a smoke test
that MOCKS the agent (no browser, no network), asserting the guard + row
assembly hold. Includes the mandated false-success regression: a genuinely
unmet condition must STILL count as a failure — no path flips it to pass."""

from __future__ import annotations

import types

import pytest

from tools import run_external_eval as m


# --- fakes (no browser / no LLM) -------------------------------------------

def fake_run(status="pass", reason="ok", *, answer="", steps=2, repairs=0,
             confidence=0.9, cost=0.001, tokens=100, latency=1234.5):
    return types.SimpleNamespace(
        status=status, verifier=types.SimpleNamespace(reason=reason),
        answer=answer, steps=[object()] * steps, repairs=repairs,
        confidence=confidence, llm_cost_usd=cost, llm_tokens=tokens,
        total_latency_ms=latency)


ENTRY = {"task_id": "t1", "difficulty": "easy",
         "website": "https://example.com/",
         "natural_language_task": "Find the 'baggage allowance' weight.",
         "expected_outcome": "conditions hold",
         "success_conditions": [{"type": "text_visible", "value": "Allowance"}]}


# --- classify_env_error -----------------------------------------------------

@pytest.mark.parametrize("hs,err,status,reason,expected", [
    ("done", None, "pass", "ok", None),                        # pass never env
    ("done", None, "fail", "violated: text_visible:X", None),  # genuine agent fail
    ("done", None, "fail", "captcha challenge shown", "anti_bot"),
    ("done", None, "fail", "please log in to continue", "auth_required"),
    ("done", None, "unknown", "net::ERR_NAME_NOT_RESOLVED", "site_unreachable"),
    ("error", "TimeoutError: goto timed out", None, None, "site_unreachable"),
    ("error", "PlaywrightError: net::ERR_ABORTED", None, None, "site_unreachable"),
    ("error", "ValueError: something odd", None, None, "site_unreachable"),  # unattributed crash
    ("error", "Error: 403 Forbidden", None, None, "anti_bot"),
])
def test_classify_env_error(hs, err, status, reason, expected):
    assert m.classify_env_error(hs, err, status, reason) == expected


def test_env_precedence_anti_bot_over_unreachable():
    # a message mentioning both a captcha and a timeout classifies as the wall,
    # not the timeout (anti_bot is checked first — most specific block).
    assert m.classify_env_error("done", None, "fail",
                                "captcha then request timeout") == "anti_bot"


# --- contract_from_entry ----------------------------------------------------

def test_contract_from_entry_conditions():
    c = m.contract_from_entry(ENTRY)
    assert c.task_id == "t1"
    assert [(s.type, s.value) for s in c.success_conditions] == [("text_visible", "Allowance")]


def test_contract_from_entry_open_ended():
    e = {**ENTRY, "success_conditions": []}
    c = m.contract_from_entry(e)
    assert c.success_conditions == []          # legal open-ended task


# --- build_row --------------------------------------------------------------

def test_build_row_shape():
    row = m.build_row(fake_run(status="pass"), ENTRY, budget=8, wall_s=5.04)
    assert row["task_id"] == "t1"
    assert row["status"] == "pass"
    assert row["step_budget"] == 8
    assert row["steps_taken"] == 2
    assert row["wall_s"] == 5.0
    assert row["llm_tokens"] == 100


def test_build_row_preserves_fail_status():
    # a fail TaskRun yields a fail row — build_row never rewrites the verdict.
    row = m.build_row(fake_run(status="fail", reason="violated: text_visible:Allowance"),
                      ENTRY, budget=8, wall_s=1.0)
    assert row["status"] == "fail"
    assert "violated" in row["verifier_reason"]


# --- summarize --------------------------------------------------------------

def test_summarize_excludes_env_blocked_from_denominator():
    rows = [
        {"task_id": "a", "difficulty": "easy", "status": "pass",
         "verifier_reason": "ok", "harness_status": "done"},
        {"task_id": "b", "difficulty": "easy", "status": "fail",
         "verifier_reason": "violated: text_visible:X", "harness_status": "done"},
        {"task_id": "c", "difficulty": "hard", "status": "fail",
         "verifier_reason": "captcha wall", "harness_status": "done"},   # env
        {"task_id": "d", "difficulty": "hard", "harness_status": "error",
         "harness_error": "TimeoutError: unreachable"},                  # env
    ]
    s = m.summarize(rows)
    o = s["overall"]
    # 4 tasks, 3 done, 2 env-blocked (c captcha, d timeout) -> effective = {a,b}
    assert o["done"] == 3
    assert o["env_blocked"] == 1        # only done rows count as env_blocked here
    assert o["pass"] == 1 and o["fail"] == 1
    assert o["success_rate"] == 0.5     # 1 pass / 2 effective (a,b); c excluded, d is error
    assert s["env_errors"] == {"anti_bot": 1, "site_unreachable": 1}


def test_summarize_false_success_regression():
    # THE guard: a genuinely-unmet condition (fail + honest 'violated') must
    # never be counted as a success. success_rate stays 0.0, pass stays 0.
    rows = [{"task_id": "x", "difficulty": "medium", "status": "fail",
             "verifier_reason": "violated: text_visible:Nonexistent",
             "harness_status": "done"}]
    s = m.summarize(rows)
    assert s["overall"]["pass"] == 0
    assert s["overall"]["success_rate"] == 0.0
    assert s["overall"]["env_blocked"] == 0   # a plain violated is NOT env-excused


def test_summarize_per_difficulty():
    rows = [
        {"task_id": "a", "difficulty": "easy", "status": "pass",
         "verifier_reason": "ok", "harness_status": "done"},
        {"task_id": "b", "difficulty": "hard", "status": "fail",
         "verifier_reason": "violated", "harness_status": "done"},
    ]
    s = m.summarize(rows)
    assert s["per_difficulty"]["easy"]["success_rate"] == 1.0
    assert s["per_difficulty"]["hard"]["success_rate"] == 0.0


def test_summarize_all_env_blocked_success_rate_none():
    rows = [{"task_id": "a", "difficulty": "easy", "status": "fail",
             "verifier_reason": "captcha", "harness_status": "done"}]
    s = m.summarize(rows)
    assert s["overall"]["success_rate"] is None    # no effective tasks -> undefined, not 0
    assert s["overall"]["env_blocked"] == 1


# --- _query_hint ------------------------------------------------------------

def test_query_hint_prefers_quoted():
    assert m._query_hint("Search for 'baggage allowance' now") == "baggage allowance"


def test_query_hint_first_content_word():
    assert m._query_hint("Find the weight limit") == "Find"


# --- smoke: run_task with the agent MOCKED (no browser, no network) ---------

def test_run_task_smoke_mocks_agent(monkeypatch, tmp_path):
    """One trivial task through run_task with execute_task stubbed to a canned
    TaskRun: exercises budget resolution + row assembly with no browser. Second
    judge off (extractor=None) so `page` is never touched."""
    captured = {}

    def fake_execute(page, entry, planner, budget, evidence, run_dir):
        captured["budget"] = budget
        return fake_run(status="pass", reason="text_visible:Allowance satisfied")

    monkeypatch.setattr(m, "execute_task", fake_execute)
    row = m.run_task(page=None, entry=ENTRY, planner=object(), run_dir=tmp_path,
                     evidence=None, extractor=None, max_steps=None)
    assert row["status"] == "pass"
    assert captured["budget"] == 8          # easy tier resolved via resolve_max_steps
    assert "second_judge" not in row        # extractor off


def test_run_task_smoke_respects_max_steps_override(monkeypatch, tmp_path):
    monkeypatch.setattr(m, "execute_task",
                        lambda *a, **k: fake_run(status="fail", reason="violated"))
    row = m.run_task(page=None, entry={**ENTRY, "difficulty": "hard"},
                     planner=object(), run_dir=tmp_path, evidence=None,
                     extractor=None, max_steps=3)
    assert row["step_budget"] == 3          # override wins over hard tier (25)
    assert row["status"] == "fail"          # a mocked failure stays a failure
