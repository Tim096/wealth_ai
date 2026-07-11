"""P0-8 CI golden-drift harness.

Re-runs the LIVE pipeline against frozen raw-filing fixtures — fully offline
(network is blocked for the whole module) — and asserts:

  1. fixture integrity: gunzipped bytes hash-match the manifest;
  2. frozen offset gold (data/golden_labels/offsets/) reproduces EXACTLY
     (start/end/text_sha256) and tri-states do not drift (no new omission or
     hallucination on present/null items);
  3. every machine-checkable known-bad entry (failure gallery FG-SEC-001..009,
     typed in data/sec_eval/fixtures/manifest.json) stays fixed/honest.

Any assertion failing here means the pipeline drifted against frozen ground
truth: either fix the regression or consciously re-freeze the gold — never
edit the expectation to make CI green.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import socket
from pathlib import Path

import pytest

from sec_core.pipeline import extract_from_html
from sec_core.scoring import tristate

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "data" / "sec_eval" / "fixtures"
MANIFEST = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8-sig"))

GOLD_FIXTURE_IDS = [fid for fid, spec in MANIFEST["fixtures"].items() if spec["gold"]]
KNOWN_BAD_IDS = [e["failure_id"] for e in MANIFEST["known_bad"]]

_STATUS_ENUM = {"fixed", "fixed_detection_only", "engine_side", "open", "unsupported"}

# one extraction per fixture per session; parametrized tests share the cache
_extract_cache: dict[str, object] = {}


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """The drift harness must be offline-deterministic: any socket connect
    attempt from the live pipeline is a bug, not a flake."""
    def _blocked(self, *args, **kwargs):  # noqa: ANN001
        raise RuntimeError("golden-drift harness must run offline; network call attempted")
    monkeypatch.setattr(socket.socket, "connect", _blocked)


def _raw_bytes(fixture_id: str) -> bytes:
    spec = MANIFEST["fixtures"][fixture_id]
    raw = gzip.decompress((FIXTURES / spec["file"]).read_bytes())
    digest = hashlib.sha256(raw).hexdigest()
    assert digest == spec["raw_sha256"], (
        f"{fixture_id}: fixture bytes drifted (sha256 {digest} != manifest {spec['raw_sha256']})")
    return raw

def _extract(fixture_id: str):
    if fixture_id not in _extract_cache:
        # decode exactly as tools/eval_one.py does before extract_from_html
        text = _raw_bytes(fixture_id).decode("utf-8", errors="replace")
        _extract_cache[fixture_id] = extract_from_html(text, filing_id=f"drift-{fixture_id}")
    return _extract_cache[fixture_id]

def _segments(fixture_id: str) -> dict:
    return {s.item_code: s for s in _extract(fixture_id).segments}


# --- 1. manifest is typed + complete -----------------------------------------

def test_manifest_covers_full_failure_gallery():
    assert KNOWN_BAD_IDS == [f"FG-SEC-{i:03d}" for i in range(1, 10)]


@pytest.mark.parametrize("entry", MANIFEST["known_bad"], ids=KNOWN_BAD_IDS)
def test_known_bad_entry_typed_fields(entry):
    for field in ("failure_id", "app", "failure_type", "status", "summary",
                  "input", "gallery", "related_commits", "guarded_by", "checks"):
        assert field in entry, f"{entry.get('failure_id')}: missing typed field {field}"
    assert entry["status"] in _STATUS_ENUM
    assert entry["failure_type"]
    for check in entry["checks"]:
        assert check["type"] in MANIFEST["check_types"], f"untyped check: {check}"
        assert check["fixture"] in MANIFEST["fixtures"], f"check on unknown fixture: {check}"
    # entries with no executable check must name their guard or be unsupported-era
    if not entry["checks"]:
        assert entry["guarded_by"], f"{entry['failure_id']}: neither checks nor guarded_by"


@pytest.mark.parametrize("fixture_id", list(MANIFEST["fixtures"]))
def test_fixture_integrity(fixture_id):
    spec = MANIFEST["fixtures"][fixture_id]
    path = FIXTURES / spec["file"]
    assert path.exists(), f"fixture file missing: {path}"
    raw = _raw_bytes(fixture_id)
    assert len(raw) == spec["raw_bytes"]
    if spec["gold"]:
        gold_path = ROOT / spec["gold"]
        assert gold_path.exists(), f"gold file missing: {gold_path}"
        gold = json.loads(gold_path.read_text(encoding="utf-8-sig"))
        assert gold["accession"] == spec["accession"], (
            f"{fixture_id}: gold froze accession {gold['accession']} "
            f"but fixture is {spec['accession']} — never score against the wrong document")


# --- 2. frozen offset gold reproduces exactly, offline -----------------------

@pytest.mark.parametrize("fixture_id", GOLD_FIXTURE_IDS)
def test_golden_offsets_no_drift(fixture_id):
    spec = MANIFEST["fixtures"][fixture_id]
    gold = json.loads((ROOT / spec["gold"]).read_text(encoding="utf-8-sig"))
    result = _extract(fixture_id)
    assert len(result.doc.text) == gold["normalized_chars"], "normalizer output drifted"

    segs = {s.item_code: s for s in result.segments}
    toc_codes = {c.code for c in result.candidates if c.toc_rejected}
    frozen = 0
    for code, g in gold["items"].items():
        seg = segs.get(code)
        if g["state"] == "unverified":
            continue  # no blessed ground truth — nothing to drift against
        assert seg is not None, f"item {code} vanished from pipeline output"
        live_state = tristate(seg.status, code in toc_codes)
        if g["state"] == "present":
            assert live_state == "present", (
                f"item {code}: gold present, live {live_state} (status={seg.status}) — omission drift")
            if "start_offset" in g:
                frozen += 1
                assert (seg.start_offset, seg.end_offset) == (g["start_offset"], g["end_offset"]), (
                    f"item {code}: frozen span ({g['start_offset']},{g['end_offset']}) "
                    f"drifted to ({seg.start_offset},{seg.end_offset})")
                assert seg.text_sha256 == g["text_sha256"], f"item {code}: span text drifted"
        elif g["state"] == "null":
            assert live_state in ("null", "MISSING"), (
                f"item {code}: gold null, live {live_state} (status={seg.status}) — hallucination drift")
    assert frozen > 0, f"{fixture_id}: gold contains no frozen offsets"


# --- 3. known-bad regressions stay fixed/honest -------------------------------

_CHECK_PARAMS = [
    pytest.param(entry["failure_id"], check,
                 id=f"{entry['failure_id']}-{check['type']}-{check.get('item', check['fixture'])}")
    for entry in MANIFEST["known_bad"] for check in entry["checks"]
]


@pytest.mark.parametrize("failure_id,check", _CHECK_PARAMS)
def test_known_bad_stays_fixed(failure_id, check):
    kind = check["type"]
    if kind == "filing_class":
        assert _extract(check["fixture"]).filing_class == check["expected"], failure_id
        return
    if kind == "all_items_status_in":
        for seg in _extract(check["fixture"]).segments:
            assert seg.status in check["expected"], (
                f"{failure_id}: item {seg.item_code} status={seg.status} "
                f"not in {check['expected']}")
        return
    segs = _segments(check["fixture"])
    seg = segs.get(check["item"])
    assert seg is not None, f"{failure_id}: item {check['item']} missing from output"
    if kind == "item_status_in":
        assert seg.status in check["expected"], (
            f"{failure_id}: item {check['item']} status={seg.status}, "
            f"expected one of {check['expected']}")
    elif kind == "item_max_span_chars":
        span = seg.end_offset - seg.start_offset
        assert span <= check["max_chars"], (
            f"{failure_id}: item {check['item']} span {span} chars "
            f"exceeds {check['max_chars']} — boundary runaway regressed")
    elif kind == "item_span_excludes":
        text = _extract(check["fixture"]).doc.text[seg.start_offset:seg.end_offset]
        for bad in check["forbidden_substrings"]:
            assert bad not in text, (
                f"{failure_id}: furniture {bad!r} leaked back into item {check['item']} span")
    else:  # pragma: no cover — schema test already rejects unknown types
        pytest.fail(f"unknown check type {kind}")
