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
from observability_core import sha256_bytes
from sec_core.normalize import normalize_html
from sec_core.resolver import FilingFile, FilingRef


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
    assert "servable" in payload["meta"] and "servability" in payload


def test_short_gap_is_hidden_from_ui_but_present_in_audit():
    text = "A" * 50 + "short gap" + "B" * 50
    payload = sec_main._items_payload(
        _result("standard", [
            _seg(start_offset=0, end_offset=50),
            _seg(item_code="2", start_offset=59, end_offset=len(text)),
        ], text), {"source": "SHORT"}, [])

    assert payload["gaps"] == []  # UI keeps the existing 120-char folding threshold
    ranges = payload["audit"]["partition"]["unclassified_ranges"]
    assert ranges == [{"start": 50, "end": 59, "chars": 9, "preview": "short gap",
                       "after": "1", "before": "2"}]


def test_upload_raw_replays_non_utf8_bytes_exactly(monkeypatch):
    monkeypatch.setattr(sec_main, "JOBS", sec_main.JobStore(max_workers=1))
    client = TestClient(sec_main.app)
    blob = b"<html><body><p>legacy byte: \x96</p></body></html>"

    uploaded = client.post(
        "/api/upload", files={"file": ("legacy.htm", blob, "text/html")}).json()
    raw = client.get(f"/api/jobs/{uploaded['job_id']}/raw")

    assert uploaded["status"] == "done"
    assert raw.content == blob
    assert raw.headers["x-raw-sha256"] == sha256_bytes(blob)
    assert uploaded["audit"]["raw"] == {
        "replayable": True,
        "sha256": sha256_bytes(blob),
        "bytes": len(blob),
        "decode": {"encoding": "utf-8", "errors": "replace"},
        "decode_replacement_chars": 1,
    }
    assert uploaded["meta"]["servable"] is False
    assert "DECODE_REPLACEMENT" in uploaded["servability"]["blocking_reason_codes"]


def test_decode_replacement_count_excludes_literal_replacement_character():
    text, replacements = sec_main._decode_utf8("literal �".encode() + b"\x96")
    assert text == "literal ��"
    assert replacements == 1


def test_low_coverage_supported_filing_is_not_servable_clean():
    payload = sec_main._items_payload(
        _result("standard", [_seg(start_offset=0, end_offset=50)], "x" * 1000),
        {"source": "PLD-LIKE"}, [], raw_bytes=b"source",
        audit_context={"xbrl": {"status": "certified", "detail": "fixture"}},
    )

    assert payload["meta"]["supported"] is True  # compatibility field is unchanged
    assert payload["meta"]["servable"] is False
    assert payload["servability"]["level"] == "blocked"
    assert "LOW_ITEM_COVERAGE" in payload["servability"]["blocking_reason_codes"]


def test_audit_omissions_are_reason_coded():
    raw = b"<html><script>excluded source text</script><p>body text</p></html>"
    doc = normalize_html(raw.decode("utf-8"))
    result = types.SimpleNamespace(
        filing_class="standard", segments=[_seg(end_offset=len(doc.text))],
        doc=doc, warnings=[],
    )
    payload = sec_main._items_payload(
        result, {"source": "AUDIT"}, [], raw_bytes=raw,
        audit_context={"xbrl": {"status": "unavailable",
                                "reason_code": "XBRL_UNAVAILABLE", "detail": "fixture"}},
    )

    omissions = payload["audit"]["omissions"]
    assert omissions and all(row.get("reason_code") for row in omissions)
    assert {row["reason_code"] for row in omissions} >= {
        "NORMALIZATION_EXCLUDED_CONTENT", "XBRL_UNAVAILABLE",
    }
    assert payload["servability"]["level"] == "degraded"


def test_extract_audit_explains_main_document_selection(monkeypatch):
    ref = FilingRef(cik=123, accession="0000000123-26-000001", form="10-K",
                    report_date="2025-12-31", primary_document="acme-10k.htm")
    ref.files = [
        FilingFile(name="acme-10k.htm", doc_type="10-K", size=1000),
        FilingFile(name="cover.htm", size=100),
    ]
    amendment = FilingRef(cik=123, accession="0000000123-26-000002", form="10-K/A",
                          report_date="2025-12-31", is_amendment=True)
    raw = b"<html><body><p>annual filing body</p></body></html>"

    class Fetcher:
        def __init__(self, **_):
            pass

        def get(self, _url):
            return types.SimpleNamespace(content=raw, sha256=sha256_bytes(raw))

    class Resolver:
        def __init__(self, _fetcher):
            pass

        def cik_for_ticker(self, _ticker):
            return 123

        def annual_filings(self, _cik):
            return [amendment, ref]

        def load_files(self, _ref):
            pass

    monkeypatch.setattr(sec_main, "EdgarFetcher", Fetcher)
    monkeypatch.setattr(sec_main, "FilingResolver", Resolver)
    payload, state = sec_main._run_extract("ACME", "")

    selection = payload["audit"]["selection"]
    main = selection["main_document"]
    assert main["selected"]["name"] == "acme-10k.htm"
    rejected = next(row for row in main["candidates"] if not row["selected"])
    assert "reasons" in rejected and rejected["rejection_reasons"]
    assert selection["package_files"] == [
        {"name": "acme-10k.htm", "doc_type": "10-K", "size": 1000,
         "listed_primary_document": True, "selected_main_document": True},
        {"name": "cover.htm", "doc_type": "", "size": 100,
         "listed_primary_document": False, "selected_main_document": False},
    ]
    assert selection["amendments_excluded"][0]["accession"] == amendment.accession
    assert selection["history_fetch_observability"]["reason_code"] == (
        "HISTORY_FETCH_NOT_OBSERVABLE")
    assert {"AMENDMENT_EXCLUDED", "HISTORY_FETCH_NOT_OBSERVABLE"} <= set(
        payload["servability"]["reason_codes"])
    assert payload["servability"]["level"] != "clean"
    assert state["raw"] == raw

    filings = TestClient(sec_main.app).get("/api/filings?query=ACME").json()
    assert filings["audit"]["history_fetch_observability"] == {
        "status": "not_observable",
        "reason_code": "HISTORY_FETCH_NOT_OBSERVABLE",
        "detail": "resolver does not expose per-page historical submissions fetch failures",
    }


def test_exhibit_audit_records_cap_fetch_parse_and_skips(monkeypatch):
    files = [
        FilingFile(name="bad-ex231.htm"),
        FilingFile(name="parse-ex241.htm"),
        FilingFile(name="good-ex211.htm"),
        FilingFile(name="capped-ex311.htm"),
    ]
    ref = types.SimpleNamespace(files=files, file_url=lambda name: f"https://example/{name}")

    class Fetcher:
        def get(self, url):
            if "bad-ex231" in url:
                raise RuntimeError("fetch failed")
            content = b"<p>PARSE</p>" if "parse-ex241" in url else b"<p>exhibit body</p>"
            return types.SimpleNamespace(content=content, sha256=sha256_bytes(content))

    real_normalize = sec_main.normalize_html

    def parse(raw):
        if "PARSE" in raw:
            raise ValueError("parse failed")
        return real_normalize(raw)

    monkeypatch.setattr(sec_main, "normalize_html", parse)
    monkeypatch.setattr(sec_main, "_MAX_EXHIBITS", 1)
    exhibits, audit = sec_main._fetch_exhibits(Fetcher(), ref)

    assert len(exhibits) == 1 and audit["eligible"] == 4
    assert audit["fetch_errors"][0]["reason_code"] == "EXHIBIT_FETCH_ERROR"
    assert audit["parse_errors"][0]["reason_code"] == "EXHIBIT_PARSE_ERROR"
    assert audit["skipped"] == [{"file": "capped-ex311.htm",
                                 "reason_code": "EXHIBIT_CAP_REACHED"}]
