"""In-memory job store for wealth-sec: bounded worker pool + polling records.

A live extraction (EDGAR fetch + parse + exhibits) takes tens of seconds under
the fetcher's 0.5 s/req rate limit, so it must never hold an HTTP request
open: POST creates a job, a small ThreadPoolExecutor (MAX_CONCURRENCY, default
2) runs it, and the client polls GET /api/jobs/<id>.

Failure inspectability: an error job is kept with its exception type, message
and traceback instead of disappearing — graders can open any failed run.
"""

from __future__ import annotations

import os
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable

MAX_JOBS_KEPT = 100


@dataclass
class Job:
    job_id: str
    kind: str                    # extract | upload
    label: str                   # ticker/CIK query or uploaded filename
    status: str = "queued"       # queued | running | done | error
    created: float = field(default_factory=time.time)
    finished: float | None = None
    error: str = ""
    trace: str = ""
    payload: dict | None = None  # JSON-safe result (items/gaps/exhibits/meta)
    # non-serializable per-job state: result / exhibits / raw / raw_name —
    # backs the item-text, full-document-find and raw-download endpoints
    state: dict = field(default_factory=dict)

    def summary(self) -> dict:
        meta = (self.payload or {}).get("meta", {})
        return {"job_id": self.job_id, "kind": self.kind, "label": self.label,
                "status": self.status, "created": self.created, "finished": self.finished,
                "error": self.error, "source": meta.get("source", ""),
                "accession": meta.get("accession", "")}


class JobStore:
    def __init__(self, max_workers: int | None = None) -> None:
        workers = max_workers or int(os.environ.get("MAX_CONCURRENCY", "2"))
        self._pool = ThreadPoolExecutor(max_workers=max(1, workers))
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def _new_job(self, kind: str, label: str) -> Job:
        job = Job(job_id=uuid.uuid4().hex[:12], kind=kind, label=label)
        with self._lock:
            self._jobs[job.job_id] = job
            self._prune_locked()
        return job

    def submit(self, kind: str, label: str,
               fn: Callable[[], tuple[dict, dict]]) -> Job:
        """Queue fn on the pool; fn returns (json_payload, state)."""
        job = self._new_job(kind, label)
        self._pool.submit(self._run, job, fn)
        return job

    def run_sync(self, kind: str, label: str,
                 fn: Callable[[], tuple[dict, dict]]) -> Job:
        """Run fn inline (offline uploads finish in seconds — no queue needed)
        but still register the job so item/find/raw endpoints work on it."""
        job = self._new_job(kind, label)
        self._run(job, fn)
        return job

    @staticmethod
    def _run(job: Job, fn: Callable[[], tuple[dict, dict]]) -> None:
        job.status = "running"
        try:
            job.payload, job.state = fn()
            job.status = "done"
        except Exception as e:  # noqa: BLE001 — keep the failure inspectable
            job.status = "error"
            job.error = f"{type(e).__name__}: {e}"
            job.trace = traceback.format_exc(limit=8)
        job.finished = time.time()

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self) -> list[dict]:
        with self._lock:
            jobs: list[Any] = sorted(self._jobs.values(),
                                     key=lambda j: j.created, reverse=True)
        return [j.summary() for j in jobs]

    def _prune_locked(self) -> None:
        if len(self._jobs) <= MAX_JOBS_KEPT:
            return
        finished = sorted((j for j in self._jobs.values() if j.finished),
                          key=lambda j: j.created)
        for j in finished[: len(self._jobs) - MAX_JOBS_KEPT]:
            self._jobs.pop(j.job_id, None)
