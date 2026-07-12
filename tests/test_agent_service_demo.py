"""wealth-agent service — 示範任務 (keyless demo) presets + endpoints.

The demo section's contract: every preset resolves to a bundled mock site,
runs through the normal /api/tasks pipeline with MockPlanner FORCED
(planner_mode="mock"), so a grader gets a full live run without any LLM key.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SVC = ROOT / "apps" / "services" / "agent"
sys.path.insert(0, str(SVC))

import worker  # noqa: E402  (service module, path-injected)


def test_demo_presets_resolve_to_bundled_mock_sites():
    assert 3 <= len(worker.DEMO_TASKS) <= 5
    ids = [d["id"] for d in worker.DEMO_TASKS]
    assert len(ids) == len(set(ids))
    for d in worker.DEMO_TASKS:
        assert d["url"] in worker.MOCK_SITES, d["id"]
        page = worker.MOCK_SITES[d["url"]]
        assert page.exists(), f"{d['id']}: missing mock site {page}"
        assert worker._resolve_url(d["url"]).startswith("file://")
        for cond in d["success"]:  # text_visible:value | forbidden:type:value
            if cond.startswith("forbidden:"):
                _, t, v = cond.split(":", 2)
                assert t == "error_text_visible" and v, cond
            else:
                t, v = cond.split(":", 1)
                assert t == "text_visible" and v, cond
        assert d["title"] and d["desc"] and d["task"]


def test_demo_covers_drift_injection_and_refusal():
    urls = {d["url"] for d in worker.DEMO_TASKS}
    assert "mock:v2" in urls          # UI-drift self-repair demo
    assert "mock:adv" in urls         # injection-defense demo
    # refusal demo must trip the capability guard in code, keyless
    from browser_agent.capability import screen_task
    refused = [d for d in worker.DEMO_TASKS if not d["success"]]
    assert refused and all(not screen_task(d["task"]).allowed for d in refused)


def test_submit_demo_forces_mock_planner():
    rec = worker.submit_demo("demo-v1")
    assert rec is not None and rec["status"] == "queued"
    job = worker._JOBS.get_nowait()   # (task_id, task, url, conds, max_steps, planner_mode)
    assert job[0] == rec["task_id"]
    assert job[2] == "mock:v1"
    assert job[5] == "mock"
    assert worker.submit_demo("nope") is None


def test_task_contract_snapshot_is_write_once_and_copied():
    rec = worker.submit("Find the result", "https://example.com",
                        ["text_visible:Result"])
    worker._JOBS.get_nowait()
    assert rec["contract"] == {
        "frozen": False,
        "start_url": "https://example.com",
        "start_url_source": "user",
        "verification_conditions": ["text_visible:Result"],
        "conditions_source": "user",
    }

    conditions = ["text_visible:Final"]
    worker._freeze_contract(rec, "https://final.example", conditions, "llm", "llm")
    conditions.append("text_visible:must-not-leak")
    worker._freeze_contract(rec, "https://overwrite.example", [], "fallback", "fallback")
    assert rec["contract"] == {
        "frozen": True,
        "start_url": "https://final.example",
        "start_url_source": "llm",
        "verification_conditions": ["text_visible:Final"],
        "conditions_source": "llm",
    }

    public = worker.get(rec["task_id"])
    public["contract"]["verification_conditions"].append("client mutation")
    assert worker.get(rec["task_id"])["contract"]["verification_conditions"] == [
        "text_visible:Final"]


def test_agent_ui_renders_and_locks_frozen_contract():
    html = (SVC / "static" / "index.html").read_text(encoding="utf-8")
    assert 'id="aContract"' in html
    assert "renderContract(s.contract)" in html
    assert "Frozen task contract" in html
    assert "user-supplied" in html and "LLM-derived" in html
    assert "lockInputs(true)" in html and "lockInputs(false)" in html
    for label in ("Task / 任務", "Start URL / 起始 URL",
                  "Success condition / 成功條件", "Run / 派工",
                  "Demo tasks / 示範任務", "Execution status / 執行過程"):
        assert label in html


def test_demo_endpoints():
    from fastapi.testclient import TestClient
    import main
    client = TestClient(main.app)     # no lifespan: endpoints only, no browser
    d = client.get("/api/demo").json()
    assert d["ok"] and len(d["demo_tasks"]) == len(worker.DEMO_TASKS)
    assert client.post("/api/demo/nope").status_code == 404
    r = client.post("/api/demo/demo-injection")
    assert r.status_code == 202 and r.json()["task_id"]
    worker._JOBS.get_nowait()         # drain what we queued
    h = client.get("/api/health").json()
    assert h["demo_tasks"] == len(worker.DEMO_TASKS)
    if not h.get("llm_ok"):
        assert set(h["llm_env_required"]) == {
            "AGENT_LLM_MODE", "OPENAI_BASE_URL", "OPENAI_API_KEY", "OPENAI_MODEL"}
