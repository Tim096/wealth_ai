"""Claims-registry drift gate (tools/verify_claims.py).

Pins the contract of the headline-number verifier: the registry is well-formed,
every referenced artifact is present in the repo, the tool exits 0 on the
current repo (docs and artifacts agree), and a synthetically tampered expected
value is reported as DRIFT with exit 1. No network, no LLM.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import verify_claims  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "data" / "claims_registry.json"


def test_registry_loads_and_is_well_formed():
    claims = verify_claims.load_registry(REGISTRY)
    assert len(claims) >= 6
    ids = [c["claim_id"] for c in claims]
    assert len(ids) == len(set(ids)), "claim_id values must be unique"
    for claim in claims:
        assert claim["doc_locations"], claim["claim_id"]
        for doc in claim["doc_locations"]:
            assert (ROOT / doc).exists(), f"{claim['claim_id']}: doc missing: {doc}"


def test_every_registered_artifact_exists():
    for claim in verify_claims.load_registry(REGISTRY):
        assert (ROOT / claim["artifact"]).exists(), (
            f"{claim['claim_id']}: artifact missing: {claim['artifact']}")


def test_current_repo_has_no_drift(capsys):
    """The killer invariant: every headline number re-derives from its artifact
    right now. Runs the full registry, including the mutation-harness rule."""
    assert verify_claims.main([]) == 0
    out = capsys.readouterr().out
    assert "0 DRIFT, 0 ERROR" in out


def test_tampered_expected_value_is_reported_as_drift(tmp_path, capsys):
    claims = json.loads(REGISTRY.read_text(encoding="utf-8"))
    tampered = next(c for c in claims if c["rule"].startswith("json_field:"))
    tampered = dict(tampered, expected=0.9999)
    bad_registry = tmp_path / "claims_registry.json"
    bad_registry.write_text(json.dumps([tampered]), encoding="utf-8")
    assert verify_claims.main(["--registry", str(bad_registry)]) == 1
    out = capsys.readouterr().out
    assert "DRIFT" in out and "0.9999" in out


def test_missing_artifact_is_reported_as_error(tmp_path, capsys):
    claims = json.loads(REGISTRY.read_text(encoding="utf-8"))
    broken = dict(claims[0], artifact="data/does_not_exist.json")
    bad_registry = tmp_path / "claims_registry.json"
    bad_registry.write_text(json.dumps([broken]), encoding="utf-8")
    assert verify_claims.main(["--registry", str(bad_registry)]) == 1
    assert "ERROR" in capsys.readouterr().out


def test_unknown_rule_is_rejected_at_load(tmp_path):
    claims = json.loads(REGISTRY.read_text(encoding="utf-8"))
    broken = dict(claims[0], rule="no_such_rule:x")
    bad_registry = tmp_path / "claims_registry.json"
    bad_registry.write_text(json.dumps([broken]), encoding="utf-8")
    try:
        verify_claims.load_registry(bad_registry)
    except ValueError as exc:
        assert "unknown rule" in str(exc)
    else:
        raise AssertionError("load_registry accepted an unknown rule")
