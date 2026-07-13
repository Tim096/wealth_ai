"""Re-derive every registered headline number from its tracked artifact — fail on drift.

The claims registry (data/claims_registry.json) pins each load-bearing number
quoted in the docs (source of truth: docs/eval_report.md) to the tracked
artifact it came from plus a named extraction rule. This tool re-runs every
extraction and prints a PASS/DRIFT table: a doc can therefore never silently
diverge from its evidence — any drift (artifact regenerated, number edited,
artifact missing) exits non-zero and turns CI red.

Rules (built-in, stdlib only):
  json_field:<dot.path>          — field extraction from a JSON artifact
  json_ratio_pair:<pathA>|<pathB> — "A/B" count pair from one JSON artifact
  sweep3_clean_false_alarm       — recompute clean false-alarm rate over the
                                   recorded sweep3 verifier outputs + the
                                   triangulation verdicts (same definition as
                                   tests/test_verifier_mutations.py)
  pytest_mutation_min_recall     — run the mutation harness itself and parse
                                   the measured per-class recalls; returns the
                                   minimum across all six mutation classes

Usage:
  .venv/Scripts/python tools/verify_claims.py [--registry data/claims_registry.json]

Exit 0 = every claim PASS; exit 1 = any DRIFT or ERROR.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "data" / "claims_registry.json"
TRIANGULATION = ROOT / "data" / "sec_eval" / "triangulation" / "triangulation.json"

MUTATION_CLASSES = (
    "truncate", "misalign", "toc_anchor", "wrapper_swallow", "jitter", "cross_swap",
)
_RECALL_LINE = re.compile(r"^\s*(\w+): recall ([0-9.]+) \(n=\d+\)", re.MULTILINE)

REQUIRED_KEYS = ("claim_id", "description", "doc_locations", "expected", "artifact", "rule")


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _walk(obj: Any, dot_path: str) -> Any:
    """Follow a dot-separated key path through nested JSON dicts."""
    for key in dot_path.split("."):
        if not isinstance(obj, dict) or key not in obj:
            raise KeyError(f"path segment {key!r} not found (full path: {dot_path})")
        obj = obj[key]
    return obj


def _rule_json_field(artifact: Path, arg: str) -> Any:
    return _walk(_load_json(artifact), arg)


def _rule_json_ratio_pair(artifact: Path, arg: str) -> str:
    num_path, den_path = arg.split("|", 1)
    data = _load_json(artifact)
    return f"{_walk(data, num_path)}/{_walk(data, den_path)}"


def _rule_sweep3_clean_false_alarm(artifact: Path, arg: str) -> float:
    """Same computation as tests/test_verifier_mutations.py::_sweep3_recorded_false_alarm:
    over all items the pipeline passed in the recorded sweep3 runs, the rate at
    which the recorded verifier outputs (needs_review flag or a triangulation
    disagree verdict) alarmed anyway. `artifact` is the sweep3 records dir; the
    triangulation verdicts are the fixed companion artifact."""
    tri = _load_json(TRIANGULATION)
    tri_by = {r["ticker"]: r["items"] for r in tri["records"]}
    total = alarms = 0
    for path in sorted(artifact.glob("*.json")):
        rec = _load_json(path)
        for code, item in rec["items"].items():
            if item["status"] != "pass":
                continue
            total += 1
            verdict = tri_by.get(rec["ticker"], {}).get(code, {}).get("verdict")
            if item["needs_review"] or verdict == "disagree":
                alarms += 1
    if total == 0:
        raise ValueError(f"no passed items found under {artifact}")
    return round(alarms / total, 4)


def _rule_pytest_mutation_min_recall(artifact: Path, arg: str) -> float:
    """Re-run the mutation harness and parse the measured per-class recall lines
    printed by test_report_measured_numbers. Returns the minimum recall across
    all six mutation classes, so the claim only holds if every class holds."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(artifact), "-q", "-s", "-p", "no:cacheprovider"],
        capture_output=True, text=True, cwd=ROOT,
    )
    if proc.returncode != 0:
        tail = (proc.stdout or proc.stderr)[-800:]
        raise RuntimeError(f"mutation harness pytest exited {proc.returncode}:\n{tail}")
    recalls = {m.group(1): float(m.group(2)) for m in _RECALL_LINE.finditer(proc.stdout)}
    missing = [cls for cls in MUTATION_CLASSES if cls not in recalls]
    if missing:
        raise RuntimeError(f"harness output missing recall lines for classes: {missing}")
    return min(recalls[cls] for cls in MUTATION_CLASSES)


RULES: dict[str, Callable[[Path, str], Any]] = {
    "json_field": _rule_json_field,
    "json_ratio_pair": _rule_json_ratio_pair,
    "sweep3_clean_false_alarm": _rule_sweep3_clean_false_alarm,
    "pytest_mutation_min_recall": _rule_pytest_mutation_min_recall,
}


def load_registry(path: Path) -> list[dict[str, Any]]:
    claims = _load_json(path)
    if not isinstance(claims, list) or not claims:
        raise ValueError(f"{path}: registry must be a non-empty JSON list")
    for claim in claims:
        missing = [k for k in REQUIRED_KEYS if k not in claim]
        if missing:
            raise ValueError(f"claim {claim.get('claim_id', '<no id>')!r} missing keys: {missing}")
        rule_name = str(claim["rule"]).split(":", 1)[0]
        if rule_name not in RULES:
            raise ValueError(f"claim {claim['claim_id']!r}: unknown rule {rule_name!r}")
    return claims


def apply_rule(rule: str, artifact: Path) -> Any:
    name, _, arg = rule.partition(":")
    return RULES[name](artifact, arg)


def values_match(expected: Any, actual: Any) -> bool:
    if isinstance(expected, bool) or isinstance(actual, bool):
        return expected is actual
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return abs(float(expected) - float(actual)) < 1e-9
    return expected == actual


def verify_claim(claim: dict[str, Any]) -> tuple[str, Any]:
    """Returns (status, actual): status in {PASS, DRIFT, ERROR}."""
    artifact = ROOT / str(claim["artifact"])
    if not artifact.exists():
        return "ERROR", f"artifact not found: {claim['artifact']}"
    try:
        actual = apply_rule(str(claim["rule"]), artifact)
    except Exception as exc:  # noqa: BLE001 — any extraction failure is a reportable ERROR
        return "ERROR", f"{type(exc).__name__}: {exc}"
    return ("PASS" if values_match(claim["expected"], actual) else "DRIFT"), actual


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY,
                        help="claims registry JSON (default: data/claims_registry.json)")
    args = parser.parse_args(argv)

    claims = load_registry(args.registry)
    rows: list[tuple[str, str, str, str]] = []
    statuses: list[str] = []
    for claim in claims:
        status, actual = verify_claim(claim)
        statuses.append(status)
        rows.append((claim["claim_id"], status, json.dumps(claim["expected"]),
                     actual if status == "ERROR" else json.dumps(actual)))

    id_w = max(len(r[0]) for r in rows)
    exp_w = max(len(r[2]) for r in rows)
    print(f"{'claim_id':<{id_w}}  {'status':<6}  {'expected':<{exp_w}}  actual")
    print(f"{'-' * id_w}  {'-' * 6}  {'-' * exp_w}  {'-' * 6}")
    for claim_id, status, expected, actual in rows:
        print(f"{claim_id:<{id_w}}  {status:<6}  {expected:<{exp_w}}  {actual}")

    n_pass = statuses.count("PASS")
    n_drift = statuses.count("DRIFT")
    n_error = statuses.count("ERROR")
    print(f"\n{len(statuses)} claims: {n_pass} PASS, {n_drift} DRIFT, {n_error} ERROR")
    return 0 if n_pass == len(statuses) else 1


if __name__ == "__main__":
    sys.exit(main())
