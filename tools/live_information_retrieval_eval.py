"""Run the frozen cross-domain information-retrieval suite on the live agent."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TASKS = ROOT / "data/browser_eval/live_information_retrieval/tasks.json"
DEFAULT_OUTPUT = ROOT / "data/browser_eval/live_information_retrieval/results.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def run(base_url: str, tasks_path: Path, output_path: Path,
        slow_threshold_s: int, require_build_sha: bool = False) -> dict:
    taskset = json.loads(tasks_path.read_text(encoding="utf-8"))
    started = datetime.now(UTC)
    rows = []
    source_commit = _head()
    with httpx.Client(base_url=base_url.rstrip("/"), timeout=30.0) as client:
        health = client.get("/api/health").json()
        deployment_attested = health.get("build_sha") == source_commit
        if require_build_sha and not deployment_attested:
            raise RuntimeError(
                "deployed build SHA does not match runner HEAD: "
                f"health={health.get('build_sha')!r}, head={source_commit!r}"
            )
        for task in taskset["tasks"]:
            submitted = client.post(
                "/api/tasks",
                json={
                    "task": task["task"],
                    "url": task["url"],
                    "success": task["success"],
                    "max_steps": task["max_steps"],
                },
            )
            submitted.raise_for_status()
            task_id = submitted.json()["task_id"]
            task_started = time.monotonic()
            state = {}
            while True:
                response = client.get(f"/api/tasks/{task_id}")
                response.raise_for_status()
                state = response.json()
                if state["status"] not in {"queued", "running"}:
                    break
                time.sleep(2)
            trace = state.get("trace") or {}
            answer = state.get("answer", "")
            expected_answer_regex = task.get("expected_answer_regex")
            gold_match = (bool(re.search(expected_answer_regex, answer or ""))
                          if expected_answer_regex else None)
            # Two axes, never collapsed into one number: gold_match answers "is
            # the delivered answer right", the agent's own status answers "does
            # the agent know it". Scoring on `status == "pass" and gold_match`
            # made the external gold subordinate to the agent's self-verdict —
            # so an honest `unknown` on a demonstrably CORRECT answer scored the
            # same as a wrong answer. Gold decides correctness; self-verdict is
            # reported beside it (self_certified) and never gates it.
            scored_pass = (gold_match if expected_answer_regex is not None
                           else state.get("status") == "pass")
            self_certified = state.get("status") == "pass"
            rows.append({
                "id": task["id"],
                "domain": task["domain"],
                "task_type": task.get("task_type"),
                "task_id": task_id,
                "status": state.get("status"),
                "confidence": state.get("confidence"),
                "answer": answer,
                "verifier": state.get("verifier", ""),
                "expected_answer_regex": expected_answer_regex,
                "gold_match": gold_match,
                "gold_pass": scored_pass if expected_answer_regex else None,
                "scored_pass": scored_pass,
                "self_certified": self_certified,
                "slow": time.monotonic() - task_started > slow_threshold_s,
                "planner_steps": trace.get("repetition", {}).get("n_steps"),
                "llm_calls": state.get("llm_calls"),
                "llm_tokens": state.get("llm_tokens"),
                "llm_cost_usd": state.get("llm_cost_usd"),
                "total_latency_ms": trace.get("total_latency_ms"),
            })
            print(f"{task['id']}: {rows[-1]['status']} ({task_id})", flush=True)
    passed = sum(row["scored_pass"] for row in rows)
    latencies = [row["total_latency_ms"] for row in rows
                 if row["total_latency_ms"] is not None]
    calls = [row["llm_calls"] for row in rows if row["llm_calls"] is not None]
    tokens = [row["llm_tokens"] for row in rows if row["llm_tokens"] is not None]
    costs = [row["llm_cost_usd"] for row in rows if row["llm_cost_usd"] is not None]
    self_certified = sum(row["self_certified"] for row in rows)
    summary = {
        "passed": passed,
        "total": len(rows),
        "pass_rate": passed / len(rows),
        # The gap between these two and pass_rate is the point, not a defect:
        # answers the agent got right but honestly declined to certify.
        "self_certified": self_certified,
        "self_certified_rate": self_certified / len(rows),
        "domains": len({row["domain"] for row in rows}),
        "task_types": sorted({row["task_type"] for row in rows if row["task_type"]}),
        "slow_count": sum(row["slow"] for row in rows),
        "llm_calls_total": sum(calls),
        "llm_calls_median": statistics.median(calls) if calls else 0,
        "llm_calls_max": max(calls, default=0),
        "llm_tokens_total": sum(tokens),
        "llm_tokens_median": statistics.median(tokens) if tokens else 0,
        "llm_tokens_max": max(tokens, default=0),
        "llm_cost_usd_total": sum(costs),
        "latency_ms_median": statistics.median(latencies) if latencies else None,
        "latency_ms_p95_inclusive": (statistics.quantiles(
            latencies, n=20, method="inclusive"
        )[18] if len(latencies) > 1 else (latencies[0] if latencies else None)),
        "latency_ms_max": max(latencies, default=None),
    }
    result = {
        "suite": taskset["suite"],
        "taskset_sha256": _sha256(tasks_path),
        "source_commit": source_commit,
        "deployment_attested": deployment_attested,
        "base_url": base_url.rstrip("/"),
        "started_at": started.isoformat().replace("+00:00", "Z"),
        "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "service_health": health,
        "protocol": taskset["protocol"],
        "summary": summary,
        "results": rows,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="https://wealth-agent-ncku.zeabur.app")
    parser.add_argument("--tasks", type=Path, default=DEFAULT_TASKS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--slow-threshold", type=int, default=60)
    parser.add_argument("--require-build-sha", action="store_true")
    args = parser.parse_args()
    result = run(
        args.base_url, args.tasks, args.output, args.slow_threshold,
        require_build_sha=args.require_build_sha,
    )
    print(json.dumps(result["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
