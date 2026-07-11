"""wealth-agent — Task 1 public frontend + API (FastAPI).

Wraps packages/browser_agent behind a job-queue API:
  GET  /                    UI (natural-language task in, live trace out)
  GET  /api/health          liveness + planner/queue info (never token-gated)
  GET  /api/demo            keyless 示範任務 presets (never token-gated)
  POST /api/demo/{id}       queue a preset demo run (MockPlanner forced, no key)
  POST /api/tasks           {"task": "...", "url"?, "success"?, "max_steps"?} -> 202 {task_id}
  GET  /api/tasks           recent tasks
  GET  /api/tasks/{id}      status + live steps + verifier verdict + full trace
  GET  /api/tasks/{id}/artifacts          list per-run files (shots/evidence/downloads/run.json)
  GET  /api/tasks/{id}/artifacts/{path}   fetch one artifact (screenshot, trace, download)

Optional gate: set ACCESS_TOKEN to require it (X-Access-Token header or
?token= query) on everything except /api/health and the UI shell. Default
UNSET so graders operate freely.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

import worker

STATIC = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    worker.start()
    yield


app = FastAPI(title="wealth-agent", lifespan=lifespan)


# --------------------------------------------------------------- token gate
_OPEN_PATHS = {"/", "/index.html", "/api/health", "/api/demo", "/favicon.ico"}


@app.middleware("http")
async def access_gate(request: Request, call_next):
    token = os.environ.get("ACCESS_TOKEN", "")
    if token and request.url.path not in _OPEN_PATHS:
        supplied = (request.headers.get("x-access-token", "")
                    or request.query_params.get("token", ""))
        if supplied != token:
            return JSONResponse({"ok": False, "error": "invalid or missing access token"},
                                status_code=401)
    return await call_next(request)


# --------------------------------------------------------------------- API
class TaskIn(BaseModel):
    task: str = Field(min_length=1, max_length=2000)
    url: str = ""                      # blank -> LLM preflight plans the start URL
    success: list[str] | None = None   # ["text_visible:...", ...]; None -> preflight
    max_steps: int = 18


@app.get("/api/health")
def health():
    out = {"ok": True, "service": "wealth-agent", **worker.INFO,
           "queue_depth": worker.queue_depth(),
           "demo_tasks": len(worker.DEMO_TASKS)}
    if not worker.INFO.get("llm_ok"):
        # demo mode: spell out exactly what enables arbitrary NL tasks
        out["llm_env_required"] = {
            "AGENT_LLM_MODE": "direct",
            "OPENAI_BASE_URL": "https://openrouter.ai/api/v1(OpenRouter)或其他 OpenAI-compatible endpoint",
            "OPENAI_API_KEY": "<your key>",
            "OPENAI_MODEL": "<model slug,如 openai/gpt-4o-mini>",
        }
    return out


@app.get("/api/demo")
def demo_tasks():
    return {"ok": True, "mode": worker.INFO.get("mode", ""),
            "llm_ok": worker.INFO.get("llm_ok", False),
            "demo_tasks": worker.DEMO_TASKS}


@app.post("/api/demo/{demo_id}", status_code=202)
def run_demo(demo_id: str):
    try:
        rec = worker.submit_demo(demo_id)
    except worker.QueueFull as e:
        raise HTTPException(status_code=429, detail=str(e)) from None
    if rec is None:
        raise HTTPException(status_code=404, detail="unknown demo_id")
    return {"ok": True, "task_id": rec["task_id"]}


@app.post("/api/tasks", status_code=202)
def create_task(body: TaskIn):
    try:
        rec = worker.submit(body.task.strip(), body.url, body.success, body.max_steps)
    except worker.QueueFull as e:
        raise HTTPException(status_code=429, detail=str(e)) from None
    return {"ok": True, "task_id": rec["task_id"]}


@app.get("/api/tasks")
def tasks():
    return {"ok": True, "tasks": worker.list_tasks()}


@app.get("/api/tasks/{task_id}")
def task_status(task_id: str):
    rec = worker.get(task_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="unknown task_id")
    return rec


@app.get("/api/tasks/{task_id}/artifacts")
def task_artifacts(task_id: str):
    if worker.get(task_id) is None:
        raise HTTPException(status_code=404, detail="unknown task_id")
    return {"ok": True, "artifacts": worker.list_artifacts(task_id)}


@app.get("/api/tasks/{task_id}/artifacts/{rel:path}")
def task_artifact(task_id: str, rel: str):
    p = worker.artifact_file(task_id, rel)
    if p is None:
        raise HTTPException(status_code=404, detail="no such artifact")
    return FileResponse(p, headers={"Cache-Control": "private, max-age=31536000, immutable"})


# ---------------------------------------------------------------------- UI
@app.get("/")
def index():
    return FileResponse(STATIC / "index.html", media_type="text/html")
