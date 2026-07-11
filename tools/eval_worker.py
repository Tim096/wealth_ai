"""Per-task harness isolation layer (P0-9): persistence + watchdog + abort guard.

Harness-level status is a SEPARATE axis from the verdict layer
(pass/fail/unknown/refused):

  done       — the task fn returned a row; ONLY these rows enter verdict metrics
  error      — the task fn raised; captured and reported, never re-raised
  incomplete — the process died mid-task: the pre-execution marker written by
               run_guarded is the only thing that survives a hard crash

Every task runs under try/finally that writes
`runs/browser_eval/<task_id>/summary.json`, so a mid-set crash can no longer
throw away every finished row without artifact (BG silent-failure trichotomy).
The watchdog is Playwright-level — win32 has no signal.alarm, so every page
action/navigation gets a hard timeout and a hung page raises instead of
stalling the whole set. Relaunch masking (load_done_summary) lets a rerun skip
tasks a previous launch already finished, and should_abort stops a run whose
harness error rate exceeds 30% (BG relaunch guard). P0-11's subprocess-per-task
driver shares this same isolation boundary.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS_ROOT = ROOT / "runs" / "browser_eval"

TASK_TIMEOUT_MS = 30_000   # Playwright-level per-action/navigation watchdog
ERROR_ABORT_RATE = 0.30    # >30% harness errors -> stop the run
ERROR_ABORT_MIN = 3        # guard arms only after this many attempts (no 1/1 trips)


class HarnessAbort(RuntimeError):
    """Raised when the mid-run error-rate guard trips; carries the partial rows
    so the caller can persist them instead of losing the whole set."""

    def __init__(self, rows: list[dict], n_error: int, n_attempted: int):
        super().__init__(f"harness abort: {n_error}/{n_attempted} tasks errored "
                         f"(> {ERROR_ABORT_RATE:.0%} threshold)")
        self.rows = rows
        self.n_error = n_error
        self.n_attempted = n_attempted


def arm_watchdog(page, timeout_ms: int = TASK_TIMEOUT_MS) -> None:
    """Bound every Playwright action AND navigation: a hung page raises
    TimeoutError (-> harness error row) instead of hanging the whole eval."""
    page.set_default_timeout(timeout_ms)
    page.set_default_navigation_timeout(timeout_ms)


def _summary_path(task_id: str, out_root: Path) -> Path:
    return out_root / task_id / "summary.json"


def _write(path: Path, summary: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run_guarded(task_id: str, fn, out_root: Path = RUNS_ROOT) -> dict:
    """Run one task under the harness guard and ALWAYS persist its summary.

    An `incomplete` pre-marker is written BEFORE fn runs — if the process dies
    mid-task, that marker is the surviving evidence. try/finally then rewrites
    the terminal state: done (fn returned a row) or error (fn raised; captured,
    never re-raised). Returns the summary dict."""
    path = _summary_path(task_id, out_root)
    summary = {"task_id": task_id, "harness_status": "incomplete", "row": None,
               "error": None, "written_at": _now()}
    _write(path, summary)  # pre-marker: a hard crash leaves this behind
    try:
        summary["row"] = fn()
        summary["harness_status"] = "done"
    except Exception as e:  # noqa: BLE001 — the harness must outlive any task crash
        summary["harness_status"] = "error"
        summary["error"] = f"{type(e).__name__}: {e}"
    finally:
        summary["written_at"] = _now()
        _write(path, summary)
    return summary


def load_done_summary(task_id: str, out_root: Path = RUNS_ROOT) -> dict | None:
    """Relaunch masking: a prior launch's summary iff it finished (done + row)."""
    path = _summary_path(task_id, out_root)
    if not path.exists():
        return None
    try:
        summary = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if summary.get("harness_status") == "done" and summary.get("row"):
        return summary
    return None


def should_abort(n_error: int, n_attempted: int) -> bool:
    """True once >ERROR_ABORT_RATE of attempted tasks errored, after at least
    ERROR_ABORT_MIN attempts (so a single early error cannot kill the run)."""
    return n_attempted >= ERROR_ABORT_MIN and n_error / n_attempted > ERROR_ABORT_RATE


def scan_incomplete(task_ids: list[str], out_root: Path = RUNS_ROOT) -> list[str]:
    """Tasks whose last persisted summary is still the pre-marker — the harness
    died mid-task on a previous launch. Reported separately, never in metrics."""
    out: list[str] = []
    for tid in task_ids:
        path = _summary_path(tid, out_root)
        if not path.exists():
            continue
        try:
            summary = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if summary.get("harness_status") == "incomplete":
            out.append(tid)
    return out


def harness_report(rows: list[dict], n_planned: int, aborted: bool = False) -> dict:
    """Harness-layer accounting block, separate from the verdict metrics.
    Rows without a harness_status key (legacy/pure-logic rows) count as done."""
    done = [r for r in rows if r.get("harness_status", "done") == "done"]
    error = [r for r in rows if r.get("harness_status") == "error"]
    return {
        "planned": n_planned,
        "done": len(done),
        "error": len(error),
        "resumed": sum(bool(r.get("resumed")) for r in done),
        "not_run": n_planned - len(rows),
        "aborted": aborted,
        "error_rate": round(len(error) / len(rows), 3) if rows else 0.0,
        "error_task_ids": [r["task_id"] for r in error],
    }
