"""wealth-agent service — 示範任務 (keyless demo) presets + endpoints.

The demo section's contract: every preset resolves to a bundled mock site,
runs through the normal /api/tasks pipeline with MockPlanner FORCED
(planner_mode="mock"), so a grader gets a full live run without any LLM key.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SVC = ROOT / "apps" / "services" / "agent"
sys.path.insert(0, str(SVC))

import worker  # noqa: E402  (service module, path-injected)

# verdict-area telemetry fields the task record / GET /api/tasks/{id} gained
_TELEMETRY_FIELDS = ("observed_evidence", "missing_evidence",
                     "llm_cost_usd", "llm_tokens", "llm_calls", "latency_ms")


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


def test_demo_covers_drift_injection_refusal_and_open_ended():
    urls = {d["url"] for d in worker.DEMO_TASKS}
    assert "mock:v2" in urls          # UI-drift self-repair demo
    assert "mock:adv" in urls         # injection-defense demo
    from browser_agent.capability import screen_task
    # a zero-condition demo is EITHER a capability-guard refusal (login/buy) OR
    # an honest-unknown open-ended task (allowed, but nothing machine-checkable);
    # both are keyless. The two must not be conflated.
    empty = [d for d in worker.DEMO_TASKS if not d["success"]]
    refused = [d for d in empty if not screen_task(d["task"]).allowed]
    open_ended = [d for d in empty if screen_task(d["task"]).allowed]
    assert refused                    # capability-boundary refusal demo present
    assert open_ended                 # honest-UNKNOWN open-ended demo present


def test_open_ended_demo_is_honest_unknown_by_construction():
    """Demo #5: allowed by the capability guard (so NOT a refusal), zero
    verifiable conditions (so it routes through the open-ended gate → unknown).
    The button copy makes the point that the verdict — not a PASS — is the win."""
    from browser_agent.capability import screen_task
    d = next((x for x in worker.DEMO_TASKS if x["id"] == "demo-open-unknown"), None)
    assert d is not None, "demo-open-unknown preset missing"
    assert d["success"] == []                       # zero conditions → open-ended
    assert d["url"] in worker.MOCK_SITES            # deterministic mock site
    assert screen_task(d["task"]).allowed           # NOT refused (unlike demo-refused)
    assert "UNKNOWN" in d["title"]                  # verdict-forward button copy
    assert "PASS" in d["desc"] or "不是" in d["desc"]


def test_submit_demo_forces_mock_planner():
    rec = worker.submit_demo("demo-v1")
    assert rec is not None and rec["status"] == "queued"
    job = worker._JOBS.get_nowait()   # (task_id, task, url, conds, max_steps, planner_mode)
    assert job[0] == rec["task_id"]
    assert job[2] == "mock:v1"
    assert job[5] == "mock"
    assert worker.submit_demo("nope") is None


def test_refused_task_never_reaches_planner_or_browser_queue(monkeypatch):
    def fail_if_queued(*_args, **_kwargs):
        raise AssertionError("refused task crossed the service boundary")

    monkeypatch.setattr(worker._JOBS, "put_nowait", fail_if_queued)
    rec = worker.submit("登入我的帳戶並購買商品", "https://example.com", [])
    assert rec["status"] == "refused"
    assert rec["confidence"] == 0.0
    assert rec["contract"]["frozen"] is True
    assert "login" in rec["verifier"] or "purchase" in rec["verifier"]


def test_task_record_is_published_before_worker_is_notified(monkeypatch):
    def inspect_before_enqueue(job):
        task_id = job[0]
        assert task_id in worker._TASKS
        assert task_id in worker._ORDER

    monkeypatch.setattr(worker._JOBS, "put_nowait", inspect_before_enqueue)
    rec = worker.submit("Read the public result", "https://example.com",
                        ["text_visible:Result"])
    worker._TASKS.pop(rec["task_id"], None)
    worker._ORDER.remove(rec["task_id"])


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


def test_demo_endpoints(monkeypatch):
    from fastapi.testclient import TestClient
    import main
    client = TestClient(main.app)     # no lifespan: endpoints only, no browser
    d = client.get("/api/demo").json()
    assert d["ok"] and len(d["demo_tasks"]) == len(worker.DEMO_TASKS)
    assert client.post("/api/demo/nope").status_code == 404
    r = client.post("/api/demo/demo-injection")
    assert r.status_code == 202 and r.json()["task_id"]
    worker._JOBS.get_nowait()         # drain what we queued
    monkeypatch.setenv("DEPLOY_COMMIT_SHA", "a" * 40)
    h = client.get("/api/health").json()
    assert h["demo_tasks"] == len(worker.DEMO_TASKS)
    assert h["build_sha"] == "a" * 40 and h["build_attested"] is True
    if not h.get("llm_ok"):
        assert set(h["llm_env_required"]) == {
            "AGENT_LLM_MODE", "OPENAI_BASE_URL", "OPENAI_API_KEY", "OPENAI_MODEL"}


def test_task_record_exposes_verdict_telemetry_fields():
    """The task record carries the verdict-area fields from the moment it is
    queued (stable schema), defaulting to empty / zero — deterministic demos
    must report $0.0000 with 0 calls / 0 tokens, never an invented cost."""
    rec = worker.submit("Find something", "https://example.com", ["text_visible:X"])
    worker._JOBS.get_nowait()          # nothing runs it; just inspect the record
    for f in _TELEMETRY_FIELDS:
        assert f in rec, f
    assert rec["observed_evidence"] == [] and rec["missing_evidence"] == []
    assert rec["llm_cost_usd"] == 0.0 and rec["llm_tokens"] == 0
    assert rec["llm_calls"] == 0 and rec["latency_ms"] == 0.0
    # the public copy also carries them and copies the evidence lists (no leak)
    pub = worker.get(rec["task_id"])
    for f in _TELEMETRY_FIELDS:
        assert f in pub, f
    pub["observed_evidence"].append("client mutation")
    assert worker.get(rec["task_id"])["observed_evidence"] == []


def test_task_status_response_includes_cost_chip_fields():
    """GET /api/tasks/{id} surfaces the cost-chip inputs; for a keyless demo
    they are present and zero (the chip renders $0.0000 · 0 calls · 0 tok)."""
    from fastapi.testclient import TestClient
    import main
    client = TestClient(main.app)     # no lifespan → no worker thread, job stays queued
    tid = client.post("/api/demo/demo-open-unknown").json()["task_id"]
    body = client.get(f"/api/tasks/{tid}").json()
    for f in _TELEMETRY_FIELDS:
        assert f in body, f
    assert body["llm_cost_usd"] == 0.0 and body["llm_calls"] == 0 and body["llm_tokens"] == 0
    worker._JOBS.get_nowait()          # drain what we queued


def test_ui_renders_verdict_area_upgrade():
    html = (SVC / "static" / "index.html").read_text(encoding="utf-8")
    for anchor in ('id="aCostChip"', 'id="aChecklist"', 'id="aTriage"',
                   "renderCostChip(s)", "renderChecklist(s)", "renderTriage(id,s)",
                   "Per-condition checklist", "const DIAG=", "capability_refused"):
        assert anchor in html, anchor


# --- integration: drive the real worker for demo #5 in an isolated process ---
_DEMO5_DRIVER = r"""
import json, sys, time
from pathlib import Path
REPO = Path(r"__REPO__")
sys.path.insert(0, str(REPO / "apps" / "services" / "agent"))
sys.path.insert(0, str(REPO / "packages"))
import worker
worker.start()
for _ in range(300):
    if worker.INFO.get("ready"):
        break
    time.sleep(0.1)
tid = worker.submit_demo("demo-open-unknown")["task_id"]
for _ in range(600):
    s = worker.get(tid)
    if s["status"] not in ("queued", "running"):
        break
    time.sleep(0.1)
s = worker.get(tid)
print(json.dumps({
    "status": s["status"], "observed": s["observed_evidence"], "missing": s["missing_evidence"],
    "llm_cost_usd": s["llm_cost_usd"], "llm_tokens": s["llm_tokens"],
    "llm_calls": s["llm_calls"], "latency_ms": s["latency_ms"],
    "n_steps": len((s.get("trace") or {}).get("steps", [])),
}))
"""


@pytest.mark.integration
def test_demo5_open_ended_ends_unknown_end_to_end():
    """Full worker path (Playwright + MockPlanner) for demo #5: it must reach an
    honest `unknown` with a real trace, and the cost chip must be $0 / 0 calls /
    0 tokens (deterministic) with a non-zero measured latency. Run in a
    subprocess so the background worker thread never races the in-process tests
    that hand-drain the queue."""
    pytest.importorskip("playwright.sync_api")
    if not (ROOT / "data" / "mock_sites" / "v1" / "index.html").exists():
        pytest.skip("mock sites not present")
    import os
    env = {**os.environ, "AGENT_LLM_MODE": "mock"}   # force deterministic, no network probe
    driver = _DEMO5_DRIVER.replace("__REPO__", str(ROOT))
    proc = subprocess.run([sys.executable, "-c", driver],
                          capture_output=True, text=True, timeout=240, env=env)
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout.strip().splitlines()[-1])
    assert data["status"] == "unknown"               # honest UNKNOWN, never a fake pass
    assert data["n_steps"] > 0                        # unknown still leaves a full trace
    assert "open-ended" in " ".join(data["missing"])  # open-ended gate reason
    # cost chip: deterministic demo → zero everywhere except measured latency
    assert data["llm_cost_usd"] == 0.0
    assert data["llm_tokens"] == 0 and data["llm_calls"] == 0
    assert data["latency_ms"] > 0
