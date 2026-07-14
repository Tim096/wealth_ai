"""wealth-sec service perf fixes: result memo (same click = instant, no
duplicate work), inline cache-hit payload, gzip on large JSON. All offline —
_run_extract is monkeypatched, prewarm disabled via PREWARM_TICKERS=""."""

from __future__ import annotations

import os
import threading
import types

os.environ["PREWARM_TICKERS"] = ""  # before app import: no EDGAR at startup

from fastapi.testclient import TestClient

import apps.services.sec.main as sec_main
from apps.services.sec.jobs import JobStore


# ----------------------------------------------------------- health provenance
def test_health_exposes_build_sha_and_pipeline_rev(monkeypatch):
    """Deployment traceability: /api/health surfaces the deployed commit and the
    pipeline output-contract revision, mirroring wealth-agent."""
    from sec_core import PIPELINE_REV

    monkeypatch.setenv("DEPLOY_COMMIT_SHA", "a" * 40)
    h = TestClient(sec_main.app).get("/api/health").json()
    assert h["ok"] is True and h["service"] == "wealth-sec"
    assert h["build_sha"] == "a" * 40 and h["build_attested"] is True
    assert h["pipeline_rev"] == PIPELINE_REV


def test_health_build_attested_false_for_bad_sha(monkeypatch):
    monkeypatch.setenv("DEPLOY_COMMIT_SHA", "not-a-real-sha")
    h = TestClient(sec_main.app).get("/api/health").json()
    assert h["build_attested"] is False


# --------------------------------------------------------------- JobStore memo
def test_memo_lookup_returns_done_job():
    store = JobStore(max_workers=1)
    job = store.run_sync("extract", "AAPL", lambda: ({"ok": True, "meta": {}}, {}),
                         memo_key="")
    assert job.status == "done"
    assert store.lookup("extract", "AAPL", "") is job
    assert store.lookup("extract", "MSFT", "") is None


def test_memo_registers_resolved_accession():
    store = JobStore(max_workers=1)
    payload = {"ok": True, "meta": {"accession": "0000320193-24-000123"}}
    job = store.run_sync("extract", "AAPL", lambda: (payload, {}), memo_key="")
    # explicit year pick matching the already-extracted "latest" also hits
    assert store.lookup("extract", "AAPL", "0000320193-24-000123") is job


def test_memo_never_returns_error_jobs():
    store = JobStore(max_workers=1)

    def boom():
        raise RuntimeError("edgar down")

    job = store.run_sync("extract", "AAPL", boom, memo_key="")
    assert job.status == "error"
    assert store.lookup("extract", "AAPL", "") is None  # error → retry allowed


def test_memo_dedupes_inflight_job():
    store = JobStore(max_workers=1)
    release = threading.Event()

    def slow():
        release.wait(timeout=5)
        return {"ok": True, "meta": {}}, {}

    j1 = store.submit("extract", "AAPL", slow, memo_key="")
    j2 = store.lookup("extract", "AAPL", "")
    assert j2 is j1 and j2.status in ("queued", "running")
    release.set()


def test_prune_drops_dangling_memo_entries():
    store = JobStore(max_workers=1)
    import apps.services.sec.jobs as jobs_mod
    old = jobs_mod.MAX_JOBS_KEPT
    jobs_mod.MAX_JOBS_KEPT = 2
    try:
        first = store.run_sync("extract", "T0", lambda: ({"ok": True, "meta": {}}, {}),
                               memo_key="")
        for i in range(1, 4):
            store.run_sync("extract", f"T{i}", lambda: ({"ok": True, "meta": {}}, {}),
                           memo_key="")
        assert store.get(first.job_id) is None          # pruned
        assert store.lookup("extract", "T0", "") is None  # memo cleaned too
    finally:
        jobs_mod.MAX_JOBS_KEPT = old


# ------------------------------------------------------------ /api/extract API
def _fake_extract_factory(calls: list):
    def fake(query: str, accession: str):
        calls.append((query, accession))
        payload = {"ok": True,
                   "meta": {"source": query.upper(), "form": "10-K",
                            "report_date": "2024-01-01", "accession": "acc-1",
                            "filing_class": "modern", "xbrl_item8": "",
                            "latency_ms": 1, "coverage": 1.0, "pipeline_warnings": []},
                   "items": [{"code": "1", "title": "Business", "status": "pass",
                              "confidence": 1.0, "provenance": "t", "needs_review": False,
                              "chars": 5, "xbrl": "", "topic": "", "warnings": 0}],
                   "gaps": [], "exhibits": []}
        return payload, {"raw": b"x", "raw_name": "f.htm"}
    return fake


def test_extract_cache_hit_is_inline_and_runs_once(monkeypatch):
    calls: list = []
    monkeypatch.setattr(sec_main, "_run_extract", _fake_extract_factory(calls))
    monkeypatch.setattr(sec_main, "JOBS", sec_main.JobStore(max_workers=1))
    client = TestClient(sec_main.app)

    r1 = client.post("/api/extract", json={"ticker": "aapl"}).json()
    # wait for the background job (pool of 1: a follow-up status poll suffices)
    for _ in range(100):
        d = client.get(f"/api/jobs/{r1['job_id']}").json()
        if d["status"] != "queued" and d["status"] != "running":
            break
    assert d["status"] == "done"

    r2 = client.post("/api/extract", json={"ticker": "AAPL"}).json()
    assert r2["job_id"] == r1["job_id"]          # same job reused
    assert r2["status"] == "done"
    assert r2["items"]                           # payload inline — zero polling
    assert len(calls) == 1                       # parse ran exactly once

    # resolved-accession key hits the same job too
    r3 = client.post("/api/extract", json={"ticker": "AAPL", "accession": "acc-1"}).json()
    assert r3["job_id"] == r1["job_id"] and len(calls) == 1


def test_large_json_is_gzipped(monkeypatch):
    calls: list = []
    monkeypatch.setattr(sec_main, "_run_extract", _fake_extract_factory(calls))
    monkeypatch.setattr(sec_main, "JOBS", sec_main.JobStore(max_workers=1))
    client = TestClient(sec_main.app)
    jid = client.post("/api/extract", json={"ticker": "BIG"}).json()["job_id"]
    for _ in range(100):
        if client.get(f"/api/jobs/{jid}").json()["status"] == "done":
            break
    job = sec_main.JOBS.get(jid)
    job.payload["items"] = job.payload["items"] * 500   # >minimum_size body
    r = client.get(f"/api/jobs/{jid}", headers={"Accept-Encoding": "gzip"})
    assert r.headers.get("content-encoding") == "gzip"


# ------------------------------------------------- honest display boundary flag
def _seg(**kw):
    base = dict(item_code="1", canonical_title="Business", status="pass",
                confidence=0.9, provenance="offset_exact_span", needs_review=False,
                source_ranges=[], start_offset=0, end_offset=50,
                text_sha256="0" * 64, xbrl_check="", topic_check="", warnings=[])
    base.update(kw)
    return types.SimpleNamespace(**base)


def _result(filing_class, segments, text):
    return types.SimpleNamespace(filing_class=filing_class, segments=segments,
                                 doc=types.SimpleNamespace(text=text), warnings=[])


def test_items_payload_flags_unsupported_filing_not_supported():
    """Fake-PDF path: 0 items over an empty body makes coverage_ratio == 1.0. The
    honest boundary must expose meta.supported=False so the UI never renders that
    empty result as a 100%-complete success."""
    payload = sec_main._items_payload(
        _result("unsupported_scanned_or_binary", [], ""), {"source": "f.pdf"}, [])
    assert payload["items"] == []
    assert payload["meta"]["supported"] is False     # explicit machine-readable gate
    assert payload["meta"]["coverage"] is None       # vacuous 1.0 dropped from payload


def test_items_payload_flags_standard_filing_supported():
    payload = sec_main._items_payload(
        _result("standard", [_seg()], "x" * 100), {"source": "AAPL"}, [])
    assert payload["items"]
    assert payload["meta"]["supported"] is True
