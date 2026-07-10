r"""Local web test center — one page to exercise BOTH tasks.

Launch: double-click 啟動測試中心.bat, or:
  .venv\Scripts\python tools\test_center.py

Opens http://127.0.0.1:8765 with two panels:
  · Browser Agent — dispatch a natural-language task; a HEADED browser opens
    and the page streams every step (plan → action → verifier verdict).
  · SEC Extractor — type a ticker or upload a 10-K; inspect every item's
    status / confidence / provenance / XBRL / topic checks and read the
    source-exact extracted text.

Design notes: stdlib http.server only (no new deps); the browser agent runs
in one dedicated Playwright thread (jobs are queued); SEC extraction is
serialized by a lock; the Codex gateway is auto-started (codex backend if
`codex login` was done, otherwise the mock backend so the demo site works).
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
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs" / "test_center"
HTML = ROOT / "apps" / "web" / "test-center" / "index.html"
os.environ.setdefault("SEC_EDGAR_USER_AGENT", "ai-coding-test-2026 test-center contact@example.com")

from browser_agent.nl import derive_success            # noqa: E402
from llm_core.config import load_llm_config             # noqa: E402
from sec_core.fetcher import EdgarFetcher               # noqa: E402
from sec_core.main_doc import pick_main_document        # noqa: E402
from sec_core.pipeline import extract_from_html         # noqa: E402
from sec_core.resolver import FilingResolver            # noqa: E402
from sec_core.xbrl import certify_item8                 # noqa: E402

# ---------------------------------------------------------------- SEC side
_SEC_LOCK = threading.Lock()
_SEC_STATE: dict = {"result": None, "meta": None}


def _items_payload(result, meta: dict) -> dict:
    items = []
    for s in result.segments:
        items.append({
            "code": s.item_code, "title": s.canonical_title, "status": s.status,
            "confidence": round(s.confidence, 2), "provenance": s.provenance,
            "needs_review": s.needs_review, "chars": max(0, s.end_offset - s.start_offset),
            "xbrl": (s.xbrl_check.split(":")[0] if s.xbrl_check else ""),
            "topic": (s.topic_check.split(":")[0] if s.topic_check else ""),
            "warnings": len(s.warnings),
        })
    return {"ok": True, "meta": meta, "items": items}


def sec_extract(query: str) -> dict:
    """Fetch + extract the latest 10-K for a ticker/CIK; certify Item 8."""
    with _SEC_LOCK:
        fetcher = EdgarFetcher(cache_dir=ROOT / "data" / "raw_filings")
        resolver = FilingResolver(fetcher)
        cik = int(query) if query.isdigit() else resolver.cik_for_ticker(query)
        ref = next((f for f in resolver.annual_filings(cik) if not f.is_amendment), None)
        if ref is None:
            return {"ok": False, "error": f"{query}: 找不到 10-K"}
        resolver.load_files(ref)
        best = pick_main_document(ref)
        raw = fetcher.get(ref.file_url(best.name)).content.decode("utf-8", errors="replace")
        result = extract_from_html(raw, f"{query}-{ref.accession}")
        xbrl = ""
        item8 = next((s for s in result.segments if s.item_code == "8"), None)
        if item8 is not None and item8.end_offset > item8.start_offset:
            try:
                xbrl = certify_item8(result, fetcher, cik, ref.accession).verdict
            except Exception:  # noqa: BLE001 — certification is best-effort enrichment
                xbrl = ""
        meta = {"source": query.upper(), "form": ref.form, "report_date": ref.report_date,
                "accession": ref.accession, "filing_class": result.filing_class,
                "xbrl_item8": xbrl, "latency_ms": round(result.latency_ms)}
        _SEC_STATE.update(result=result, meta=meta)
        return _items_payload(result, meta)


def sec_upload(text: str, name: str) -> dict:
    """Extract an operator-supplied 10-K (HTML/TXT). No CIK → XBRL skipped."""
    with _SEC_LOCK:
        result = extract_from_html(text, Path(name).stem or "upload")
        meta = {"source": name, "form": "upload", "report_date": "-", "accession": "-",
                "filing_class": result.filing_class, "xbrl_item8": "",
                "latency_ms": round(result.latency_ms)}
        _SEC_STATE.update(result=result, meta=meta)
        return _items_payload(result, meta)


def sec_item_text(code: str) -> dict:
    result = _SEC_STATE["result"]
    if result is None:
        return {"ok": False, "error": "尚未抽取任何 filing"}
    seg = next((s for s in result.segments if s.item_code == code), None)
    if seg is None:
        return {"ok": False, "error": f"無 Item {code}"}
    body = result.text_of(code) if seg.end_offset > seg.start_offset else "(無正文 span)"
    # Never silently drop content: show the whole span. Cap only as an anti-DoS
    # guard well above the largest real item (Item 8/15 ≈ 200K chars), and when
    # it fires, say so explicitly rather than truncating in silence.
    full_chars = len(body)
    CAP = 600_000
    truncated = full_chars > CAP
    text = body[:CAP]
    if truncated:
        text += (f"\n\n──── 顯示前 {CAP:,} 字,共 {full_chars:,} 字;其餘未顯示"
                 f"(完整內容仍在 offset span 內)────")
    return {"ok": True, "code": code, "title": seg.canonical_title, "status": seg.status,
            "confidence": round(seg.confidence, 2), "provenance": seg.provenance,
            "needs_review": seg.needs_review, "sha256": seg.text_sha256[:16],
            "offsets": [seg.start_offset, seg.end_offset],
            "full_chars": full_chars, "truncated": truncated,
            "xbrl": seg.xbrl_check, "topic": seg.topic_check,
            "warnings": seg.warnings, "text": text}


# ---------------------------------------------------------------- Agent side
_RUNS: dict[str, dict] = {}
_JOBS: queue.Queue = queue.Queue()
_AGENT_INFO = {"planner": "starting…", "ready": False}


def _gateway_backend(base_url: str) -> str:
    """Ask the gateway what backend it runs ('' if unreachable). The client
    must never guess from its own PATH — an Explorer-launched process may not
    see codex even though the gateway (or a fresh spawn of it) can."""
    import httpx
    try:
        r = httpx.get(f"{base_url.rstrip('/')}/models", timeout=3)
        if r.status_code == 200:
            return r.json().get("backend", "unknown")
    except Exception:  # noqa: BLE001
        pass
    return ""


def _ensure_gateway(base_url: str) -> str:
    """Return the running gateway's backend name, starting it (backend=auto,
    which resolves codex via find_codex) if needed."""
    backend = _gateway_backend(base_url)
    if backend:
        return backend
    port = base_url.rstrip("/").split(":")[-1].split("/")[0]
    subprocess.Popen([str(ROOT / ".venv" / "Scripts" / "python.exe"),
                      str(ROOT / "tools" / "codex_gateway.py"),
                      "--backend", "auto", "--model", "default", "--port", port],
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    for _ in range(20):
        backend = _gateway_backend(base_url)
        if backend:
            return backend
        time.sleep(0.5)
    return ""


# DuckDuckGo's HTML endpoint doesn't gate automation with a CAPTCHA the way
# Google/Bing do — a friendlier default when the task needs a web search.
DEFAULT_START = "https://duckduckgo.com/html/"


def agent_submit(task: str, url: str, success: str) -> dict:
    # The user may leave start URL and/or success condition blank: an LLM
    # preflight plans them from the task at the start of the run (in the
    # worker, where the model is ready). Explicit values always win; blanks
    # are the sentinel that asks for planning. No more hard-fail on Chinese
    # prose — the model, not a word-splitter, writes the condition.
    url = url.strip()
    conds = [f"text_visible:{success.strip()}"] if success.strip() else None
    run_id = f"run{int(time.time() * 1000) % 10**9}"
    _RUNS[run_id] = {"status": "queued", "steps": [], "task": task,
                     "url": url or "(開場由 LLM 規畫)",
                     "success": conds or ["(開場由 LLM 規畫)"],
                     "verifier": "", "confidence": None, "download": ""}
    _JOBS.put((run_id, task, url, conds))
    return {"ok": True, "run_id": run_id, "success": conds or ["auto-plan"]}


def _agent_worker() -> None:
    from playwright.sync_api import sync_playwright

    from browser_core import BrowserTaskContract, SuccessCondition
    from browser_agent.agent import BrowserAgent
    from browser_agent.memory_store import MemoryStore
    from browser_agent.planner import LLMPlanner, MockPlanner
    from llm_core.openai_client import OpenAIClient
    from observability_core import EvidenceStore

    cfg = load_llm_config()
    backend = _ensure_gateway(cfg.base_url)
    if backend == "codex":
        _AGENT_INFO["planner"] = "Codex(你的 ChatGPT OAuth)✓"
    elif backend:
        _AGENT_INFO["planner"] = f"⚠ {backend} 後端 — 未找到 codex,僅適合內建 demo;請先 codex login"
    else:
        _AGENT_INFO["planner"] = "✗ gateway 起不來"
    client = OpenAIClient(api_key=cfg.api_key, base_url=cfg.base_url, model=cfg.model)
    OUT.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = None
        page = None

        def fresh_page():
            nonlocal browser, page
            if browser is not None:
                try:
                    browser.close()
                except Exception:  # noqa: BLE001
                    pass
            browser = p.chromium.launch(headless=False)
            ctx = browser.new_context(viewport={"width": 1200, "height": 820},
                                      accept_downloads=True)
            page = ctx.new_page()

        fresh_page()
        _AGENT_INFO["ready"] = True
        while True:
            run_id, task, url, conds = _JOBS.get()
            rec = _RUNS[run_id]
            rec["status"] = "running"
            try:
                # always go through the gateway — its backend (codex/mock)
                # decides behaviour; a local MockPlanner is only for tests
                planner = LLMPlanner(client)
                # Preflight: when the user left the start URL or success
                # conditions blank, have the LLM plan them from the task before
                # any browsing. Heuristics (DuckDuckGo start, word-split
                # derive_success) are only the offline fallback.
                if not url or conds is None:
                    p_url, p_conds = "", []
                    try:
                        p_url, p_conds = planner.plan_preflight(task)
                    except Exception:  # noqa: BLE001 — model unavailable → fall back
                        pass
                    if not url:
                        url = p_url or DEFAULT_START
                    if conds is None:
                        conds = p_conds or derive_success(task)
                    if not conds:
                        rec.update(status="error", url=url,
                                   verifier="無法規畫可驗證的成功條件——請在「成功條件」欄填一小段完成時會出現的文字。")
                        continue
                    rec["url"], rec["success"] = url, conds
                    rec["steps"].append(f"🧭 規畫:起點 {url} · 成功條件 {' / '.join(conds)}")
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=30000)
                except Exception:
                    fresh_page()  # user may have closed the window — recover
                    page.goto(url, wait_until="domcontentloaded", timeout=30000)
                contract = BrowserTaskContract(
                    task_id=run_id, natural_language_task=task,
                    expected_outcome="success conditions visibly satisfied",
                    success_conditions=[SuccessCondition(type=c.split(":", 1)[0],
                                                         value=c.split(":", 1)[1])
                                        for c in conds])
                agent = BrowserAgent(page, MemoryStore(OUT / "mem.json"), "web", "agentic",
                                     artifact_dir=OUT / "shots",
                                     evidence_store=EvidenceStore(OUT / "evidence"),
                                     downloads_dir=OUT / "downloads")
                run = agent.run_agentic(run_id, contract, planner, max_steps=8,
                                        on_step=lambda t: rec["steps"].append(t))
                rec.update(status=run.status, confidence=run.confidence,
                           verifier=run.verifier.reason,
                           download=agent.executor.last_download_path)
            except Exception as e:  # noqa: BLE001
                rec.update(status="error", verifier=f"{type(e).__name__}: {e}")


# ---------------------------------------------------------------- HTTP layer
class Handler(BaseHTTPRequestHandler):
    def _json(self, obj: dict, code: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> bytes:
        return self.rfile.read(int(self.headers.get("Content-Length", 0)))

    def do_GET(self):  # noqa: N802
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            body = HTML.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif u.path == "/api/agent/info":
            self._json({"ok": True, **_AGENT_INFO})
        elif u.path == "/api/agent/status":
            rid = parse_qs(u.query).get("id", [""])[0]
            self._json(_RUNS.get(rid) or {"status": "unknown_run"})
        elif u.path == "/api/sec/item":
            code = parse_qs(u.query).get("code", [""])[0]
            self._json(sec_item_text(code))
        else:
            self._json({"ok": False, "error": "not found"}, 404)

    def do_POST(self):  # noqa: N802
        u = urlparse(self.path)
        try:
            if u.path == "/api/agent/run":
                req = json.loads(self._read_body() or b"{}")
                self._json(agent_submit(req.get("task", ""), req.get("url", ""),
                                        req.get("success", "")))
            elif u.path == "/api/sec/extract":
                req = json.loads(self._read_body() or b"{}")
                self._json(sec_extract(req.get("query", "").strip()))
            elif u.path == "/api/sec/upload":
                name = parse_qs(u.query).get("name", ["upload.htm"])[0]
                self._json(sec_upload(self._read_body().decode("utf-8", errors="replace"), name))
            else:
                self._json({"ok": False, "error": "not found"}, 404)
        except Exception as e:  # noqa: BLE001 — return errors to the page, never crash
            self._json({"ok": False, "error": f"{type(e).__name__}: {e}"}, 500)

    def log_message(self, *a):  # quiet console
        pass


def main() -> None:
    threading.Thread(target=_agent_worker, daemon=True).start()
    server = ThreadingHTTPServer(("127.0.0.1", 8765), Handler)
    print("Test center ready:  http://127.0.0.1:8765   (Ctrl+C to stop)")
    threading.Timer(0.8, lambda: webbrowser.open("http://127.0.0.1:8765")).start()
    server.serve_forever()


if __name__ == "__main__":
    main()
