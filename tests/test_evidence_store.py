from observability_core import EvidenceRecord, EvidenceStore, VerifierResult, sha256_text


def make_record(run_id: str, step_id: str) -> EvidenceRecord:
    return EvidenceRecord(
        run_id=run_id,
        app="browser_agent",
        step_id=step_id,
        timestamp="2026-07-10T01:00:00Z",
        input_hash=sha256_text("input"),
        output_hash=sha256_text("output"),
        tool_used="playwright.click",
        latency_ms=12.5,
        status="pass",
        evidence_type="screenshot",
        artifact_path="artifacts/step1.png",
        verifier_result=VerifierResult(
            status="pass",
            reason="url matched",
            required_evidence=["url_contains:results"],
            observed_evidence=["url_contains:results"],
        ),
    )


def test_append_and_read_round_trip(tmp_path):
    store = EvidenceStore(tmp_path)
    r1 = make_record("run-1", "step-1")
    r2 = make_record("run-1", "step-2")
    store.append(r1)
    store.append(r2)

    records = store.read_run("run-1")
    assert [r.step_id for r in records] == ["step-1", "step-2"]
    assert records[0] == r1


def test_missing_run_returns_empty(tmp_path):
    store = EvidenceStore(tmp_path)
    assert store.read_run("nope") == []


def test_corrupt_record_fails_loudly(tmp_path):
    store = EvidenceStore(tmp_path)
    store.append(make_record("run-2", "step-1"))
    (tmp_path / "run-2.jsonl").open("a", encoding="utf-8").write('{"not": "a record"}\n')

    import pytest

    with pytest.raises(ValueError, match="corrupt evidence record"):
        store.read_run("run-2")


def test_run_id_path_traversal_rejected(tmp_path):
    store = EvidenceStore(tmp_path)
    import pytest

    with pytest.raises(ValueError, match="invalid run_id"):
        store.read_run("../escape")
