"""P1-2 per-run reproducibility manifest tests.

Covers: manifest content (git commit, dirty flag, model id + gateway mode,
seeds, task-set hash, package versions, OS, timestamp, budget caps), the
--strict-repro dirty-tree refusal (raised BEFORE anything is written;
untracked files never block), porcelain parsing, and the live-runner wiring.
"""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import tools.run_manifest as rm  # noqa: E402
from tools.run_manifest import (  # noqa: E402
    DirtyTreeError, build_manifest, file_sha256, git_state,
    package_versions, write_manifest,
)

TASKS = ROOT / "data" / "browser_eval" / "tasks.json"


# --- manifest content ---

def test_manifest_has_every_required_field():
    m = build_manifest(task_set=TASKS, seeds={"run_seed": 7},
                       budget_caps={"max_steps": 8})
    for key in ("schema", "created_at", "git", "llm", "seeds", "task_set",
                "packages", "os", "budget_caps", "argv"):
        assert key in m, key
    assert m["schema"] == "repro-manifest/1"
    # git commit matches the repo's actual HEAD
    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    assert m["git"]["commit"] == head
    assert isinstance(m["git"]["dirty"], bool)
    # model id + gateway mode present
    assert m["llm"]["model"]
    assert m["llm"]["mode"] in ("gateway", "direct", "mock")
    assert m["seeds"] == {"run_seed": 7}
    assert m["budget_caps"] == {"max_steps": 8}
    assert m["packages"]["python"]
    assert m["os"]["platform"]


def test_task_set_hash_matches_file_bytes():
    m = build_manifest(task_set=TASKS)
    assert m["task_set"]["path"] == str(Path("data/browser_eval/tasks.json"))
    assert m["task_set"]["sha256"] == hashlib.sha256(TASKS.read_bytes()).hexdigest()


def test_manifest_never_leaks_api_key():
    blob = json.dumps(build_manifest(task_set=TASKS)).lower()
    assert "api_key" not in blob


def test_budget_caps_accepts_dataclass():
    from browser_core import Budget
    m = build_manifest(budget_caps=Budget(max_steps=3, max_usd=0.5))
    assert m["budget_caps"]["max_steps"] == 3
    assert m["budget_caps"]["max_usd"] == 0.5


def test_package_versions_playwright_pinned_and_unknown_is_none():
    v = package_versions()
    assert v["playwright"]            # installed — the version we pin
    assert package_versions(("no-such-package-xyz",))["no-such-package-xyz"] is None


def test_file_sha256_missing_file_is_none():
    assert file_sha256(ROOT / "does-not-exist.bin") is None


# --- git state parsing ---

def test_git_state_splits_tracked_dirty_from_untracked(monkeypatch):
    def fake_git(*args):
        if args[0] == "rev-parse":
            return "abc123"
        return " M tools/foo.py\nA  tools/bar.py\n?? scratch.md"
    monkeypatch.setattr(rm, "_git", fake_git)
    s = git_state()
    assert s == {"commit": "abc123", "dirty": True,
                 "dirty_files": ["tools/foo.py", "tools/bar.py"],
                 "untracked": ["scratch.md"]}


def test_git_state_first_porcelain_line_not_clipped(monkeypatch):
    """Regression: _git must NOT strip the whole porcelain output — the
    leading space of line 1 (' M path') is significant, and stripping it
    clipped the first character off the first dirty file's path."""
    class FakeCompleted:
        returncode = 0
        stdout = " M apps/x.py\n?? y.md\n"
    monkeypatch.setattr(rm.subprocess, "run", lambda *a, **kw: FakeCompleted())
    s = git_state()
    assert s["dirty_files"] == ["apps/x.py"]     # not 'pps/x.py'
    assert s["untracked"] == ["y.md"]


def test_git_state_clean_tree(monkeypatch):
    monkeypatch.setattr(rm, "_git",
                        lambda *a: "abc123" if a[0] == "rev-parse" else "")
    s = git_state()
    assert s["dirty"] is False and s["dirty_files"] == [] and s["untracked"] == []


# --- write_manifest + --strict-repro contract ---

def _fake_state(dirty_files, untracked=()):
    return {"commit": "abc123", "dirty": bool(dirty_files),
            "dirty_files": list(dirty_files), "untracked": list(untracked)}


def test_write_manifest_roundtrip(tmp_path):
    path = write_manifest(tmp_path / "myset", task_set=TASKS)
    assert path == tmp_path / "myset" / "manifest.json"
    m = json.loads(path.read_text(encoding="utf-8"))
    assert m["schema"] == "repro-manifest/1"
    assert m["task_set"]["sha256"]


def test_strict_repro_refuses_dirty_tree_and_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(rm, "git_state", lambda: _fake_state(["tools/foo.py"]))
    with pytest.raises(DirtyTreeError, match="strict-repro refused"):
        write_manifest(tmp_path, strict=True)
    assert not (tmp_path / "manifest.json").exists()


def test_strict_repro_allows_clean_tree(tmp_path, monkeypatch):
    monkeypatch.setattr(rm, "git_state", lambda: _fake_state([]))
    assert write_manifest(tmp_path, strict=True).exists()


def test_strict_repro_untracked_files_do_not_block(tmp_path, monkeypatch):
    monkeypatch.setattr(rm, "git_state",
                        lambda: _fake_state([], untracked=["scratch.md"]))
    path = write_manifest(tmp_path, strict=True)
    m = json.loads(path.read_text(encoding="utf-8"))
    assert m["git"]["untracked"] == ["scratch.md"]


def test_non_strict_writes_even_when_dirty(tmp_path, monkeypatch):
    monkeypatch.setattr(rm, "git_state", lambda: _fake_state(["tools/foo.py"]))
    m = json.loads(write_manifest(tmp_path).read_text(encoding="utf-8"))
    assert m["git"]["dirty"] is True


# --- call-site wiring ---

def test_live_runner_imports_the_shared_manifest_writer():
    import tools.browser_agent_live as live
    assert live.write_manifest is rm.write_manifest
    assert live.DirtyTreeError is rm.DirtyTreeError


def test_eval_runner_imports_the_shared_manifest_writer():
    import tools.browser_eval as be
    assert be.write_manifest is rm.write_manifest
    assert be.DirtyTreeError is rm.DirtyTreeError


def test_eval_strict_repro_refuses_before_any_browser_starts(monkeypatch):
    """browser_eval.main(strict_repro=True) on a dirty tree must raise the
    DirtyTreeError refusal from the manifest step — BEFORE sync_playwright
    (or the worker pool) is ever touched."""
    import tools.browser_eval as be

    def boom(*a, **kw):
        raise AssertionError("browser started despite strict-repro refusal")
    monkeypatch.setattr(be, "sync_playwright", boom)
    monkeypatch.setattr(be, "run_pool", boom)

    def fake_write(out_dir, task_set=None, strict=False, **kw):
        assert strict is True                    # flag reaches the writer
        raise DirtyTreeError("--strict-repro refused: 1 tracked file(s) modified")
    monkeypatch.setattr(be, "write_manifest", fake_write)
    with pytest.raises(DirtyTreeError, match="strict-repro refused"):
        be.main(strict_repro=True)
