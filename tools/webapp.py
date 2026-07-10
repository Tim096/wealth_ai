r"""Local web control panel — test BOTH tasks from one HTML page.

Launch: double-click 啟動控制台.bat, or:  .venv\Scripts\python tools\webapp.py
Then open http://127.0.0.1:8800 (it opens automatically).

- Task 1 (Browser Agent): type a URL + a natural-language task; a visible
  browser opens and the Codex-driven agent does it; the step trace + verifier
  verdict stream back. Auto-starts the Codex gateway (your `codex login`), or
  falls back to a deterministic mock planner if codex isn't installed.
- Task 2 (SEC 10-K): type a ticker; see every item's status / confidence /
  provenance / XBRL / topic checks; click an item to read the source-exact
  extracted text.

Dependency-light: Python stdlib http.server + our own packages. No Flask.
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "apps" / "web" / "console" / "index.html"
OUT = ROOT / "runs" / "console"
os.environ.setdefault("SEC_EDGAR_USER_AGENT", "ai-coding-test-2026 console contact@example.com")

from sec_core.fetcher import EdgarFetcher            # noqa: E402
from sec_core.main_doc import pick_main_document      # noqa: E402
from sec_core.pipeline import extract_from_html       # noqa: E402
from sec_core.resolver import FilingResolver          # noqa: E402
from sec_core.xbrl import certify_item8               # noqa: E402

_SEC_LOCK = threading.Lock()
_LAST_SEC: dict = {}  # {"key": str, "result": ExtractionResult}


# ---------- SEC (synchronous) ----------
def sec_extract(ticker: str) -> dict:
    fetcher = EdgarFetcher(cache_dir=ROOT / "data" / "raw_filings")
    resolver = FilingResolver(fetcher)
    cik = int(ticker) if ticker.isdigit() else resolver.cik_for_ticker(ticker)
    ref = next((f for f in resolver.annual_filings(cik) if not f.is_amendment), None)
    if ref is None:
        raise ValueError(f"{ticker}: no 10-K found")
    resolver.load_files(ref)
    best = pick_main_document(ref)
    raw = fetcher.get(ref.file_url(best.name)).content.decode("utf-8", errors="replace")
    result = extract_from_html(raw, f"{ticker}-{ref.accession}")
    xbrl = ""
    item8 = next((s for s in result.segments if s.item_code == "8"), None)
    if item8 is not None and item8.end_offset > item8.start_offset:
        try:
            xbrl = certify_item8(result, fetcher, cik, ref.accession).verdict
        except Exception:  # noqa: BLE001
            pass
    with _SEC_LOCK:
        _LAST_SEC["key"] = ticker.upper()
        _LAST_SEC["result"] = result
    return {
        "ticker": ticker.upper(), "form": ref.form, "report_date": ref.report_date,
        "accession": ref.accession, "filing_class": result.filing_class, "item8_xbrl": xbrl,
        "items": [{
            "code": s.item_code, "title": s.canonical_title, "status": s.status,
            "confidence": round(s.confidence, 3), "provenance": s.provenance,
            "needs_review": s.needs_review, "xbrl": s.xbrl_check.split(":")[0] if s.xbrl_check else "",
            "topic": s.topic_check.split(":")[0] if s.topic_check else "",
            "chars": (s.end_offset - s.start_offset) if s.end_offset > s.start_offset else 0,
        } for s in result.segments],
    }


def sec_item_text(code: str) -> dict:
    with _SEC_LOCK:
        result = _LAST_SEC.get("result")
    if result is None:
        raise ValueError("no filing extracted yet")
    seg = next((s for s in result.segments if s.item_code == code), None)
    if seg is None:
        raise ValueError(f"item {code} not found")
    body = result.text_of(code) if seg.end_offset > seg.start_offset else "(no addressable span)"
    return {
        "code": seg.item_code, "title": seg.canonical_title, "status": seg.status,
        "confidence": round(seg.confidence, 3), "provenance": seg.provenance,
        "needs_review": seg.needs_review, "offset": [seg.start_offset, seg.end_offset],
        "sha256": seg.text_sha256[:16], "xbrl_check": seg.xbrl_check, "topic_check": seg.topic_check,
        "warnings": seg.warnings, "text": body[:60000],
    }


# ---------- Browser (persistent worker) ----------
class BrowserService:
    def __init__(self) -> None:
        self.tasks: queue.Queue = queue.Queue()
        self.ready = threading.Event()
        self.mode = "idle"          # not started until the first browser task
        self._started = False
        self._lock = threading.Lock()

    def _ensure_started(self) -> None:
        with self._lock:
            if self._started:
                return
            self._started = True
            self.mode = "starting"
            threading.Thread(target=self._worker, daemon=True).start()

    def _ensure_gateway(self, base_url: str) -> bool:
        import httpx

        def up() -> bool:
            try:
                return httpx.get(f"{base_url.rstrip('/')}/models", timeout=3).status_code == 200
            except Exception:  # noqa: BLE001
                return False
        if up():
            return shutil.which("codex") is not None
        backend = "codex" if shutil.which("codex") else "mock"
        port = base_url.rstrip("/").split(":")[-1].split("/")[0]
        subprocess.Popen(
            [str(ROOT / ".venv" / "Scripts" / "python.exe"), str(ROOT / "tools" / "codex_gateway.py"),
             "--backend", backend, "--model", "default", "--port", port],
            creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
        for _ in range(20):
            if up():
                return backend == "codex"
            time.sleep(0.5)
        return False

    def _worker(self) -> None:
        from playwright.sync_api import sync_playwright

        from browser_agent.agent import BrowserAgent
        from browser_agent.memory_store import MemoryStore
        from browser_agent.planner import LLMPlanner, MockPlanner
        from browser_core import BrowserTaskContract, SuccessCondition
        from llm_core.config import load_llm_config
        from llm_core.openai_client import OpenAIClient
        from observability_core import EvidenceStore
        import re

        cfg = load_llm_config()
        real = self._ensure_gateway(cfg.base_url)
        self.mode = "codex" if real else "mock"
        client = OpenAIClient(api_key=cfg.api_key, base_url=cfg.base_url, model=cfg.model)
        OUT.mkdir(parents=True, exist_ok=True)

        def derive(task: str):
            if re.search(r"download|下載|下载", task, re.I):
                return ["download_exists:"]
            q = re.findall(r"['\"“」]([^'\"”」]{2,60})['\"”」]", task)
            if q:
                return [f"text_visible:{q[0]}"]
            w = [x for x in re.findall(r"[A-Za-z0-9一-鿿]{3,}", task)]
            w.sort(key=len, reverse=True)
            return [f"text_visible:{w[0]}"] if w else ["url_contains:."]

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            ctx = browser.new_context(viewport={"width": 1200, "height": 820}, accept_downloads=True)
            page = ctx.new_page()
            self.ready.set()
            while True:
                job = self.tasks.get()
                url, task, resq = job["url"], job["task"], job["resq"]
                try:
                    if url:
                        page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    conds = derive(task)
                    contract = BrowserTaskContract(
                        task_id="web", natural_language_task=task, expected_outcome="ok",
                        success_conditions=[SuccessCondition(type=c.split(":", 1)[0], value=c.split(":", 1)[1])
                                            for c in conds])
                    planner = LLMPlanner(client) if self.mode == "codex" else MockPlanner(
                        (re.findall(r"['\"“]([^'\"”]+)['\"”]", task) or ["widget"])[0])
                    agent = BrowserAgent(page, MemoryStore(OUT / "mem.json"), "web", "agentic",
                                         artifact_dir=OUT / "shots",
                                         evidence_store=EvidenceStore(OUT / "evidence"),
                                         downloads_dir=OUT / "downloads")
                    steps_live = []
                    run = agent.run_agentic("web", contract, planner, max_steps=8,
                                            on_step=lambda t: steps_live.append(t))
                    resq.put({"ok": True, "status": run.status, "confidence": round(run.confidence, 2),
                              "verifier": run.verifier.reason, "success": conds,
                              "steps": [{"mode": s.mode, "action": s.action, "ok": s.ok,
                                         "detail": s.detail} for s in run.steps],
                              "narration": steps_live,
                              "download": agent.executor.last_download_path})
                except Exception as e:  # noqa: BLE001
                    resq.put({"ok": False, "error": f"{type(e).__name__}: {e}"})

    def run(self, url: str, task: str) -> dict:
        self._ensure_started()
        self.ready.wait(timeout=60)
        resq: queue.Queue = queue.Queue()
        self.tasks.put({"url": url, "task": task, "resq": resq})
        return resq.get()


BROWSER = BrowserService()


# ---------- HTTP ----------
class Handler(BaseHTTPRequestHandler):
    def _json(self, code: int, obj) -> None:
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):  # noqa: N802
        if self.path in ("/", "/index.html"):
            html = HTML.read_text(encoding="utf-8")
            b = html.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)
        elif self.path.startswith("/api/status"):
            self._json(200, {"browser_mode": BROWSER.mode, "browser_ready": BROWSER.ready.is_set()})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):  # noqa: N802
        try:
            if self.path == "/api/sec/extract":
                self._json(200, sec_extract(self._body().get("ticker", "").strip()))
            elif self.path == "/api/sec/item":
                self._json(200, sec_item_text(self._body().get("code", "").strip()))
            elif self.path == "/api/browser/run":
                b = self._body()
                self._json(200, BROWSER.run(b.get("url", "").strip() or None, b.get("task", "").strip()))
            else:
                self._json(404, {"error": "not found"})
        except Exception as e:  # noqa: BLE001
            self._json(500, {"error": f"{type(e).__name__}: {e}"})

    def log_message(self, *a):  # quiet
        pass


def main() -> None:
    port = 8800
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}"
    print(f"[console] serving {url}  (browser agent starting in background…)")
    try:
        webbrowser.open(url)
    except Exception:  # noqa: BLE001
        pass
    server.serve_forever()


if __name__ == "__main__":
    main()
