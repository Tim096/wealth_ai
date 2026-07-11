"""Post-hoc aggregator: build a results.json from a run dir's per-task summary.json files.

Some runs (e.g. runs/browser_eval/m2w_rerun/, the pre-bucket-fix baseline) were
interrupted before the harness wrote its final results.json, but every task dir
contains an atomically-written summary.json. This tool reconstructs results.json
in the same schema as the harness output (see runs/browser_eval/m2w_rerun_20260710/
results.json), with `aggregated_post_hoc: true` and provenance of the timestamps
(each summary.json's `written_at`) so it is never mistaken for a harness-written file.

Usage:
    python tools/aggregate_run.py <run_dir> [--task-set <task_set.json>] [--out <results.json>]
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def classify_env_error(error: str | None) -> str | None:
    if error and "Page.goto" in error:
        return "site_unreachable"
    return None


def aggregate(run_dir: Path, task_set: Path | None) -> dict:
    meta: dict[str, dict] = {}
    if task_set and task_set.exists():
        ts = json.loads(task_set.read_text(encoding="utf-8"))
        meta = {t["task_id"]: t for t in ts.get("tasks", [])}

    summaries = sorted(run_dir.glob("m2w-*/summary.json"))
    if not summaries:
        raise SystemExit(f"no m2w-*/summary.json under {run_dir}")

    rows: list[dict] = []
    written_ats: list[str] = []
    for sp in summaries:
        s = json.loads(sp.read_text(encoding="utf-8"))
        if s.get("written_at"):
            written_ats.append(s["written_at"])
        tid = s["task_id"]
        m = meta.get(tid, {})
        if s.get("harness_status") == "error" or s.get("row") is None:
            rows.append({
                "task_id": tid,
                "difficulty": m.get("difficulty"),
                "website": m.get("website"),
                "harness_status": "error",
                "harness_error": s.get("error"),
                "env_error": classify_env_error(s.get("error")),
            })
        else:
            row = dict(s["row"])
            row["harness_status"] = s.get("harness_status", "done")
            row["env_error"] = None
            row.setdefault("difficulty", m.get("difficulty"))
            row.setdefault("website", m.get("website"))
            rows.append(row)

    def bucket(sel: list[dict]) -> dict:
        done = [r for r in sel if r.get("harness_status") == "done"]
        err = [r for r in sel if r.get("harness_status") == "error"]
        n = {st: sum(1 for r in done if r.get("status") == st)
             for st in ("pass", "fail", "unknown")}
        env_blocked = sum(1 for r in done if r.get("status") == "env_blocked")
        return {
            "tasks": len(sel),
            "done": len(done),
            "error": len(err),
            "pass": n["pass"],
            "fail": n["fail"],
            "unknown": n["unknown"],
            "env_blocked": env_blocked,
            "success_rate": round(n["pass"] / len(done), 3) if done else 0.0,
        }

    diffs = sorted({r.get("difficulty") for r in rows if r.get("difficulty")})
    env_errors: dict[str, int] = {}
    for r in rows:
        if r.get("env_error"):
            env_errors[r["env_error"]] = env_errors.get(r["env_error"], 0) + 1

    return {
        "aggregated_post_hoc": True,
        "aggregation": {
            "tool": "tools/aggregate_run.py",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": f"{len(summaries)} per-task summary.json files under {run_dir.as_posix()}",
            "timestamps_from": "each summary.json 'written_at' field (harness-written, atomic)",
            "written_at_min": min(written_ats) if written_ats else None,
            "written_at_max": max(written_ats) if written_ats else None,
        },
        "metrics": {
            "overall": bucket(rows),
            "per_difficulty": {d: bucket([r for r in rows if r.get("difficulty") == d])
                               for d in diffs},
            "env_errors": env_errors,
        },
        "judge_source": "llm",
        "tasks": rows,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--task-set", type=Path,
                    default=Path("data/browser_eval/external/mind2web_subset.json"))
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args()
    out = a.out or (a.run_dir / "results.json")
    res = aggregate(a.run_dir, a.task_set)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    o = res["metrics"]["overall"]
    print(f"wrote {out}")
    print(f"overall: tasks={o['tasks']} done={o['done']} error={o['error']} "
          f"pass={o['pass']} fail={o['fail']} unknown={o['unknown']} "
          f"success_rate={o['success_rate']}")


if __name__ == "__main__":
    main()
