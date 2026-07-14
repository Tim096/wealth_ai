"""Run the frozen cross-domain information-retrieval suite on the live agent."""

from __future__ import annotations

import argparse
import hashlib
import json
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
        poll_timeout_s: int) -> dict:
    taskset = json.loads(tasks_path.read_text(encoding="utf-8"))
    started = datetime.now(UTC)
    rows = []
    with httpx.Client(base_url=base_url.rstrip("/"), timeout=30.0) as client:
        health = client.get("/api/health").json()
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
            deadline = time.monotonic() + poll_timeout_s
            state = {}
            while time.monotonic() < deadline:
                response = client.get(f"/api/tasks/{task_id}")
                response.raise_for_status()
                state = response.json()
                if state["status"] not in {"queued", "running"}:
                    break
                time.sleep(2)
            else:
                state = {"status": "timeout", "verifier": "poll timeout"}
            trace = state.get("trace") or {}
            rows.append({
                "id": task["id"],
                "domain": task["domain"],
                "task_id": task_id,
                "status": state.get("status"),
                "confidence": state.get("confidence"),
                "answer": state.get("answer", ""),
                "verifier": state.get("verifier", ""),
                "planner_steps": trace.get("repetition", {}).get("n_steps"),
                "llm_calls": state.get("llm_calls"),
                "llm_tokens": state.get("llm_tokens"),
                "llm_cost_usd": state.get("llm_cost_usd"),
                "total_latency_ms": trace.get("total_latency_ms"),
            })
            print(f"{task['id']}: {rows[-1]['status']} ({task_id})", flush=True)
    passed = sum(row["status"] == "pass" for row in rows)
    result = {
        "suite": taskset["suite"],
        "taskset_sha256": _sha256(tasks_path),
        "source_commit": _head(),
        "base_url": base_url.rstrip("/"),
        "started_at": started.isoformat().replace("+00:00", "Z"),
        "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "service_health": health,
        "protocol": taskset["protocol"],
        "summary": {"passed": passed, "total": len(rows), "pass_rate": passed / len(rows)},
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
    parser.add_argument("--poll-timeout", type=int, default=180)
    args = parser.parse_args()
    result = run(args.base_url, args.tasks, args.output, args.poll_timeout)
    print(json.dumps(result["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
