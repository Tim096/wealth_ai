"""Scalability bench for the P0-11 browser-eval worker pool (measurement only).

Runs the FIXED Script-Mode task set (data/browser_eval/tasks.json `tasks`,
replicated with unique task_ids to >= --instances task instances) through
tools/eval_worker.run_pool at each requested worker count, N reps each, and
records wall-clock / throughput / speedup / per-task latency plus machine info.

Deterministic, offline, $0: file:// mock sites, Script Mode, no LLM.

Isolation: every config writes ONLY under runs/browser_eval/scalability/
(out_root AND mem_dir per config) — it never touches runs/browser_eval/
results.json, the per-task summary dirs of real eval runs, the shared
evidence log (the pool path never wires an EvidenceStore), or
data/browser_eval/passk/passk_results.json.

Usage:
  .venv/Scripts/python.exe tools/scalability_bench.py --workers 1 --rep 1
  .venv/Scripts/python.exe tools/scalability_bench.py --merge   # -> results.json
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.eval_worker import run_pool, session_cost_model  # noqa: E402

TASKS = ROOT / "data" / "browser_eval" / "tasks.json"
OUT = ROOT / "runs" / "browser_eval" / "scalability"


def machine_info() -> dict:
    import psutil
    vm = psutil.virtual_memory()
    return {
        "cpu_model": platform.processor(),
        "physical_cores": psutil.cpu_count(logical=False),
        "logical_cpus": psutil.cpu_count(logical=True),
        "ram_total_gb": round(vm.total / 2**30, 1),
        "ram_available_gb": round(vm.available / 2**30, 1),
        "os": f"{platform.system()} {platform.release()}",
        "python": platform.python_version(),
    }


def expand_tasks(n_instances: int) -> list[dict]:
    """Replicate the 5-task Script-Mode set to >= n_instances with unique
    task_ids (unique summary paths; contract/task semantics unchanged)."""
    base = json.loads(TASKS.read_text(encoding="utf-8"))["tasks"]
    out: list[dict] = []
    rep = 0
    while len(out) < n_instances:
        for t in base:
            if len(out) >= n_instances:
                break
            c = dict(t)
            c["task_id"] = f"{t['task_id']}--i{rep:02d}"
            out.append(c)
        rep += 1
    return out


def run_config(workers: int, rep: int, instances: int) -> dict:
    tasks = expand_tasks(instances)
    cfg_dir = OUT / f"w{workers}_rep{rep}"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    summaries, pool_stats = run_pool(tasks, workers=workers,
                                     out_root=cfg_dir, mem_dir=cfg_dir)
    wall_s = time.perf_counter() - t0  # includes spawn/import, unlike pool wall
    done = [s for s in summaries if s["harness_status"] == "done"]
    lat = [s["row"]["latency_ms"] for s in done]
    n_correct = sum(bool(s["row"]["correct"]) for s in done)
    model = session_cost_model(pool_stats, len(done))
    record = {
        "workers": workers,
        "rep": rep,
        "n_tasks": len(tasks),
        "n_done": len(done),
        "n_error": len(summaries) - len(done),
        "n_correct": n_correct,
        "wall_clock_s": round(wall_s, 2),
        "pool_wall_clock_s": pool_stats["wall_clock_s"],
        "throughput_tasks_per_min": round(len(done) / wall_s * 60, 2),
        "avg_task_latency_ms": round(sum(lat) / len(lat), 1) if lat else None,
        "cost_model": model,
        "measured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "machine": machine_info(),
    }
    (cfg_dir / "bench.json").write_text(
        json.dumps(record, indent=2), encoding="utf-8")
    return record


def merge() -> dict:
    records = sorted(
        (json.loads(p.read_text(encoding="utf-8"))
         for p in OUT.glob("w*_rep*/bench.json")),
        key=lambda r: (r["workers"], r["rep"]))
    if not records:
        raise SystemExit("no bench.json found under " + str(OUT))
    base = [r for r in records if r["workers"] == 1]
    base_thr = (sum(r["throughput_tasks_per_min"] for r in base) / len(base)
                if base else None)
    by_workers: dict[int, list[dict]] = {}
    for r in records:
        by_workers.setdefault(r["workers"], []).append(r)
    summary = []
    for w, rs in sorted(by_workers.items()):
        thr = [r["throughput_tasks_per_min"] for r in rs]
        walls = [r["wall_clock_s"] for r in rs]
        mean_thr = sum(thr) / len(thr)
        summary.append({
            "workers": w,
            "reps": len(rs),
            "wall_clock_s": walls,
            "throughput_tasks_per_min": thr,
            "throughput_mean": round(mean_thr, 2),
            "throughput_spread_pct": round(
                (max(thr) - min(thr)) / mean_thr * 100, 1) if mean_thr else None,
            "speedup_vs_w1": round(mean_thr / base_thr, 2) if base_thr else None,
            "avg_task_latency_ms": [r["avg_task_latency_ms"] for r in rs],
        })
    payload = {
        "note": ("P0-11 worker-pool scalability, measured on the fixed 20-instance "
                 "Script-Mode set (5 tasks x 4 replicas), file:// mock sites, no LLM. "
                 "wall_clock_s includes process spawn + import + browser cold start. "
                 "Repro: .venv/Scripts/python.exe tools/scalability_bench.py "
                 "--workers <N> --rep <r>; then --merge."),
        "machine": records[-1]["machine"],
        "summary": summary,
        "runs": records,
    }
    (OUT / "results.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="P0-11 worker-pool scalability bench")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--rep", type=int, default=1)
    ap.add_argument("--instances", type=int, default=20)
    ap.add_argument("--merge", action="store_true",
                    help="merge all w*_rep*/bench.json into results.json")
    args = ap.parse_args()
    if args.merge:
        payload = merge()
        for s in payload["summary"]:
            print(s)
        print("wrote", OUT / "results.json")
    else:
        rec = run_config(args.workers, args.rep, args.instances)
        print(json.dumps({k: rec[k] for k in
                          ("workers", "rep", "n_tasks", "n_done", "n_error",
                           "n_correct", "wall_clock_s",
                           "throughput_tasks_per_min", "avg_task_latency_ms")},
                         indent=2))
