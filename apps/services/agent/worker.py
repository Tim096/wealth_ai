"""wealth-agent worker — single Playwright thread + in-memory job store.

Mirrors tools/test_center.py's serialized agent worker, with the deploy-time
differences kept HERE (never patched into existing modules):
  * Chromium is launched headless=True (no display in the container),
  * the codex gateway is never touched — llm_core.config decides the backend
    from env (AGENT_LLM_MODE=direct + OPENAI_BASE_URL/OPENAI_API_KEY/OPENAI_MODEL),
  * every task gets its own artifact dir under runs/agent_service/<task_id>
    (shots / evidence / downloads / run.json) so failures are inspectable
    per-task over HTTP.

One worker thread == natural concurrency cap for Playwright's sync API; the
bounded queue returns "queue full" beyond AGENT_QUEUE_LIMIT (default 10).
"""

from __future__ import annotations

import json
import os
import queue
import re
import threading
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RUNS = ROOT / "runs" / "agent_service"

# friendlier default than Google/Bing: no CAPTCHA gate on the HTML endpoint
DEFAULT_START = "https://duckduckgo.com/html/"

# bundled offline demo sites — shorthand URLs so a grader (or the smoke test)
# can exercise the full loop without leaving the container
MOCK_SITES = {
    "mock:v1": ROOT / "data" / "mock_sites" / "v1" / "index.html",
    "mock:v2": ROOT / "data" / "mock_sites" / "v2" / "index.html",
    "mock:v3": ROOT / "data" / "mock_sites" / "v3_heldout" / "index.html",
}

MAX_QUEUE = int(os.environ.get("AGENT_QUEUE_LIMIT", "10"))
MAX_STEPS_CAP = 30

_TASKS: dict[str, dict] = {}
_ORDER: list[str] = []                      # insertion order for listing
_JOBS: queue.Queue = queue.Queue(maxsize=MAX_QUEUE)
INFO = {"planner": "starting…", "ready": False, "mode": ""}


class QueueFull(Exception):
    pass


def queue_depth() -> int:
    return _JOBS.qsize()


def task_dir(task_id: str) -> Path:
    return RUNS / task_id


def submit(task: str, url: str = "", success: list[str] | None = None,
           max_steps: int = 18) -> dict:
    task_id = f"t{int(time.time() * 1000) % 10**10}"
    rec = {
        "task_id": task_id, "status": "queued", "task": task,
        "url": url or "(開場由 LLM 規畫)",
        "success": success or ["(開場由 LLM 規畫)"],
        "steps": [], "verifier": "", "confidence": None,
        "answer": "", "download": "", "trace": None,
        "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    try:
        _JOBS.put_nowait((task_id, task, url.strip(),
                          success, max(1, min(int(max_steps), MAX_STEPS_CAP))))
    except queue.Full:
        raise QueueFull(f"queue full ({MAX_QUEUE} pending tasks)") from None
    _TASKS[task_id] = rec
    _ORDER.append(task_id)
    return rec


def get(task_id: str) -> dict | None:
    rec = _TASKS.get(task_id)
    if rec is None:
        return None
    out = dict(rec)
    out["steps"] = list(rec["steps"])
    out["queue_depth"] = queue_depth()
    return out


def list_tasks(limit: int = 50) -> list[dict]:
    out = []
    for tid in reversed(_ORDER[-limit:]):
        r = _TASKS[tid]
        out.append({"task_id": tid, "status": r["status"], "task": r["task"],
                    "created": r["created"], "confidence": r["confidence"]})
    return out


def list_artifacts(task_id: str) -> list[dict]:
    base = task_dir(task_id)
    if not base.exists():
        return []
    out = []
    for p in sorted(base.rglob("*")):
        if p.is_file():
            out.append({"path": p.relative_to(base).as_posix(),
                        "bytes": p.stat().st_size})
    return out


def artifact_file(task_id: str, rel: str) -> Path | None:
    base = task_dir(task_id).resolve()
    p = (base / rel).resolve()
    if not str(p).startswith(str(base)) or not p.is_file():
        return None
    return p


def _resolve_url(url: str) -> str:
    if url in MOCK_SITES:
        return MOCK_SITES[url].resolve().as_uri()
    return url


def _mock_query(task: str) -> str:
    m = re.search(r"['\"“「『]([^'\"”「』]{1,40})['\"”」』]", task)
    return m.group(1) if m else "widget"


def _relativize(rec: dict, run_dict: dict, base: Path) -> dict:
    """Rewrite absolute artifact paths in a TaskRun dict to task-relative
    posix paths so the UI can build /api/tasks/<id>/artifacts/<path> URLs."""
    def rel(p: str) -> str:
        if not p:
            return ""
        try:
            return Path(p).resolve().relative_to(base.resolve()).as_posix()
        except ValueError:
            return Path(p).name
    for s in run_dict.get("steps", []):
        s["screenshot"] = rel(s.get("screenshot", ""))
    rec["download"] = rel(rec.get("download", ""))
    return run_dict


def _worker() -> None:
    from playwright.sync_api import sync_playwright

    from browser_core import BrowserTaskContract, SuccessCondition
    from browser_agent.agent import BrowserAgent
    from browser_agent.memory_store import MemoryStore
    from browser_agent.nl import derive_success
    from browser_agent.planner import LLMPlanner, MockPlanner
    from llm_core.config import load_llm_config
    from llm_core.openai_client import OpenAIClient
    from observability_core import EvidenceStore

    cfg = load_llm_config()
    INFO["mode"] = cfg.mode
    client = OpenAIClient(api_key=cfg.api_key, base_url=cfg.base_url, model=cfg.model)
    llm_ok = cfg.mode != "mock" and client.available()
    if llm_ok:
        INFO["planner"] = f"LLM ({cfg.mode}) · {cfg.model}"
    else:
        INFO["planner"] = ("MockPlanner — 未設定 OPENAI_API_KEY(或 AGENT_LLM_MODE=mock),"
                           "僅內建 mock 站可完整跑通")
    RUNS.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        # container: no sandbox user namespaces, small /dev/shm
        browser = p.chromium.launch(
            headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        INFO["ready"] = True
        while True:
            task_id, task, url, conds, max_steps = _JOBS.get()
            rec = _TASKS[task_id]
            rec["status"] = "running"
            base = task_dir(task_id)
            ctx = None
            try:
                planner = LLMPlanner(client) if llm_ok else MockPlanner(_mock_query(task))
                url = _resolve_url(url)
                plan_steps: list[str] = []
                if llm_ok and (not url or conds is None):
                    # preflight: the model plans start URL + verifiable success
                    # conditions + a step route BEFORE any browsing
                    p_url, p_conds, p_plan = "", [], {}
                    try:
                        p_url, p_conds, p_plan = planner.plan_preflight(task)
                    except Exception:  # noqa: BLE001 — model unavailable → heuristics
                        pass
                    plan_steps = p_plan.get("steps", [])
                    if p_plan.get("analysis"):
                        rec["steps"].append(f"🎯 目標分析:{p_plan['analysis']}")
                    if p_plan.get("obstacles"):
                        rec["steps"].append("⚠ 預判困難:" + " · ".join(p_plan["obstacles"]))
                    if plan_steps:
                        rec["steps"].append("📋 規畫步驟:" + " → ".join(
                            f"{i+1}) {s}" for i, s in enumerate(plan_steps)))
                    if not url:
                        url = p_url or DEFAULT_START
                    if conds is None:
                        conds = p_conds or derive_success(task)
                if not url:
                    url = MOCK_SITES["mock:v2"].resolve().as_uri() if not llm_ok else DEFAULT_START
                if conds is None:
                    conds = derive_success(task)
                # open-ended tasks are legal: no condition → honest UNKNOWN, never a fake pass
                rec["url"] = url
                rec["success"] = conds or ["(無可驗證條件 → 結果 UNKNOWN,請人工檢視 trace)"]
                rec["steps"].append(f"🧭 規畫:起點 {url}" + (
                    f" · 成功條件 {' / '.join(conds)}" if conds else " · 無可驗證條件 → 誠實 UNKNOWN"))

                ctx = browser.new_context(
                    viewport={"width": 1200, "height": 820}, accept_downloads=True,
                    user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"))
                page = ctx.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                contract = BrowserTaskContract(
                    task_id=task_id, natural_language_task=task,
                    expected_outcome="success conditions visibly satisfied",
                    success_conditions=[SuccessCondition(type=c.split(":", 1)[0],
                                                         value=c.split(":", 1)[1])
                                        for c in conds if ":" in c])
                agent = BrowserAgent(page, MemoryStore(RUNS / "mem.json"), "web", "agentic",
                                     artifact_dir=base / "shots",
                                     evidence_store=EvidenceStore(base / "evidence"),
                                     downloads_dir=base / "downloads")
                run = agent.run_agentic(task_id, contract, planner, max_steps=max_steps,
                                        on_step=lambda t: rec["steps"].append(t),
                                        plan_steps=plan_steps)
                rec["download"] = agent.executor.last_download_path
                run_dict = _relativize(rec, run.as_dict(), base)
                base.mkdir(parents=True, exist_ok=True)
                (base / "run.json").write_text(
                    json.dumps(run_dict, ensure_ascii=False, indent=2), encoding="utf-8")
                rec.update(status=run.status, confidence=run.confidence,
                           verifier=run.verifier.reason, answer=run.answer,
                           trace=run_dict)
            except Exception as e:  # noqa: BLE001 — a bad task must not kill the worker
                rec.update(status="error", verifier=f"{type(e).__name__}: {e}")
                base.mkdir(parents=True, exist_ok=True)
                (base / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
            finally:
                if ctx is not None:
                    try:
                        ctx.close()
                    except Exception:  # noqa: BLE001
                        pass


def start() -> None:
    threading.Thread(target=_worker, daemon=True).start()
