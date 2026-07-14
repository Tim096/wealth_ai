"""Executable provenance contract for `prompts/`."""

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import verify_prompt_provenance  # noqa: E402


def test_current_prompt_records_and_verbatim_bodies_match_history():
    assert verify_prompt_provenance.verify() == []


def test_tampered_verbatim_hash_is_rejected(tmp_path):
    manifest = json.loads(
        verify_prompt_provenance.DEFAULT_MANIFEST.read_text(encoding="utf-8"))
    first = next(iter(manifest["transcript_body_sha256"]))
    manifest["transcript_body_sha256"][first] = "0" * 64
    path = tmp_path / "provenance_manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    errors = verify_prompt_provenance.verify(path)
    assert any("body hash" in error for error in errors)
