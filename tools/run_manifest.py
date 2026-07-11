"""Per-run reproducibility manifest (P1-2).

Every eval/live run writes `<out_dir>/manifest.json` pinning what produced
the numbers: git commit + dirty-tree state, LLM model id + gateway mode,
seed(s), task-set file hash, package versions (playwright et al.), OS,
timestamp, budget caps. The repo's recent commits were fixing stale doc
numbers — the disease is metrics with no manifest tying them back to code.

strict=True (the --strict-repro path) refuses to run when TRACKED files are
modified: DirtyTreeError is raised before anything is written. Untracked
files are recorded in the manifest but do not block (they cannot silently
change committed code the way an uncommitted edit can).

Integration for tools/browser_eval.py (owned by P1-15) — three lines:

    from tools.run_manifest import write_manifest             # imports block
    manifest_path = write_manifest(OUT, task_set=TASKS,
                                   strict=strict_repro)       # top of main()
    payload["manifest"] = str(manifest_path)                  # results payload

plus an argparse flag `--strict-repro` passed through to main(). A
DirtyTreeError there is a refusal, not a crash — let it propagate.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# packages whose exact version changes eval behavior (browser binary protocol,
# HTTP client for the gateway, contract validation)
TRACKED_PACKAGES = ("playwright", "httpx", "pydantic")


class DirtyTreeError(RuntimeError):
    """--strict-repro refused: uncommitted tracked changes in the working tree."""


def _git(*args: str) -> str:
    # raw stdout, NOT stripped: porcelain lines start with a significant
    # space (" M path") and a whole-output strip would clip line 1's path
    try:
        out = subprocess.run(["git", "-C", str(ROOT), *args],
                             capture_output=True, text=True, timeout=15)
        return out.stdout if out.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def git_state() -> dict:
    """Commit hash + dirty flag. `dirty` covers TRACKED modifications only
    (those change committed code); untracked paths are listed separately."""
    commit = _git("rev-parse", "HEAD").strip() or None
    lines = [ln for ln in _git("status", "--porcelain").splitlines() if ln.strip()]
    dirty_files = [ln[3:] for ln in lines if not ln.startswith("??")]
    untracked = [ln[3:] for ln in lines if ln.startswith("??")]
    return {"commit": commit, "dirty": bool(dirty_files),
            "dirty_files": dirty_files, "untracked": untracked}


def file_sha256(path: Path | str) -> str | None:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def package_versions(names: tuple[str, ...] = TRACKED_PACKAGES) -> dict:
    out: dict = {"python": platform.python_version()}
    for name in names:
        try:
            out[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            out[name] = None
    return out


def _caps_dict(budget_caps) -> dict | None:
    if budget_caps is None:
        return None
    if dataclasses.is_dataclass(budget_caps):
        return dataclasses.asdict(budget_caps)
    return dict(budget_caps)


def build_manifest(task_set: Path | str | None = None, seeds=None,
                   budget_caps=None, extra: dict | None = None) -> dict:
    from llm_core.config import load_llm_config
    cfg = load_llm_config()
    task_block = None
    if task_set is not None:
        p = Path(task_set)
        try:
            rel = str(p.resolve().relative_to(ROOT))
        except ValueError:
            rel = str(p)
        task_block = {"path": rel, "sha256": file_sha256(p)}
    manifest = {
        "schema": "repro-manifest/1",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git": git_state(),
        # model id + gateway mode — NEVER the api key
        "llm": {"model": cfg.model, "mode": cfg.mode, "base_url": cfg.base_url},
        "seeds": seeds if seeds is not None
        else {"PYTHONHASHSEED": os.environ.get("PYTHONHASHSEED")},
        "task_set": task_block,
        "packages": package_versions(),
        "os": {"platform": platform.platform(), "machine": platform.machine()},
        "budget_caps": _caps_dict(budget_caps),
        "argv": list(sys.argv),
    }
    if extra:
        manifest.update(extra)
    return manifest


def write_manifest(out_dir: Path | str, task_set: Path | str | None = None,
                   seeds=None, budget_caps=None, extra: dict | None = None,
                   strict: bool = False) -> Path:
    """Build and write `<out_dir>/manifest.json`; returns its path.

    strict=True refuses a dirty tree (tracked modifications) BEFORE writing —
    the --strict-repro contract: no run artifacts from unpinnable code."""
    manifest = build_manifest(task_set=task_set, seeds=seeds,
                              budget_caps=budget_caps, extra=extra)
    if strict and manifest["git"]["dirty"]:
        files = manifest["git"]["dirty_files"]
        raise DirtyTreeError(
            f"--strict-repro refused: {len(files)} tracked file(s) modified "
            f"({', '.join(files[:5])}{', ...' if len(files) > 5 else ''}); "
            "commit or stash before a strict-repro run")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False),
                    encoding="utf-8")
    return path
