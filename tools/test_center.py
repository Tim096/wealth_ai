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
from sec_core.coverage import compute_gaps, coverage_ratio, partition_document, region_at  # noqa: E402
from sec_core.fetcher import EdgarFetcher               # noqa: E402
from sec_core.main_doc import pick_main_document        # noqa: E402
from sec_core.normalize import normalize_html           # noqa: E402
from sec_core.pipeline import extract_from_html         # noqa: E402
from sec_core.resolver import FilingResolver            # noqa: E402
from sec_core.xbrl import certify_item8                 # noqa: E402

# ---------------------------------------------------------------- SEC side
import re                                                # noqa: E402
_SEC_LOCK = threading.Lock()
_SEC_STATE: dict = {"result": None, "meta": None, "exhibits": []}

# A 10-K FILING is more than its main document: the real exhibits (21.1 List
# of Subsidiaries, 23.1 Consent, 31/32 Certifications, 97.1 Clawback) are
# SEPARATE files. The user is right that "everything must be there" — so we
# fetch those exhibit documents too and expose them as searchable regions,
# instead of silently limiting the tool to the main htm.
_EXHIBIT_RE = re.compile(r"-ex(\d+)\.htm?l?$", re.I)
_EXHIBIT_NAMES = {"21": "List of Subsidiaries", "23": "Consent of Accountants",
                  "31": "Certification (Sec. 302)", "32": "Certification (Sec. 906)",
                  "24": "Power of Attorney", "97": "Clawback Policy", "10": "Material Contract",
                  "4": "Instrument Defining Rights", "3": "Bylaws / Charter"}
_MAX_EXHIBITS = 20


def _exhibit_meta(name: str) -> tuple[str, str]:
    m = _EXHIBIT_RE.search(name)
    d = m.group(1) if m else ""
    num = f"{d[:-1]}.{d[-1]}" if len(d) >= 3 else d      # 211 -> 21.1
    friendly = _EXHIBIT_NAMES.get(d[:2], "") or _EXHIBIT_NAMES.get(d[:1], "")
    title = f"Exhibit {num}" + (f" · {friendly}" if friendly else "")
    return f"ex:{d}", title


def _fetch_exhibits(fetcher, ref) -> list[dict]:
    """Fetch + normalize the filing's real exhibit .htm files (not the R*.htm
    XBRL render fragments), so their text is viewable and searchable."""
    out = []
    for fl in ref.files:
        if len(out) >= _MAX_EXHIBITS:
            break
        if not _EXHIBIT_RE.search(fl.name) or re.match(r"R\d+\.htm", fl.name, re.I):
            continue
        try:
            raw = fetcher.get(ref.file_url(fl.name)).content.decode("utf-8", errors="replace")
            text = normalize_html(raw).text
        except Exception:  # noqa: BLE001 — one bad exhibit must not fail the filing
            continue
        if text.strip():
            code, title = _exhibit_meta(fl.name)
            out.append({"code": code, "title": title, "file": fl.name, "text": text})
    out.sort(key=lambda e: e["code"])
    return out


def _items_payload(result, meta: dict, exhibits: list[dict] | None = None) -> dict:
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
    # Completeness guarantee: expose every uncovered gap so nothing is dropped.
    gaps = []
    for g in compute_gaps(result.doc.text, result.segments):
        where = (f"Item {g.after_code} → {g.before_code}" if g.after_code and g.before_code
                 else (f"Item {g.after_code} 之後" if g.after_code else f"Item {g.before_code} 之前"))
        gaps.append({"code": f"gap:{g.start}-{g.end}", "title": f"未分類內容 ({where})",
                     "chars": g.chars, "preview": g.preview,
                     # document position, so the UI can slot this row BETWEEN the
                     # items it falls between (Item 2→3) instead of at the bottom
                     "after": g.after_code, "before": g.before_code, "start": g.start})
    exs = [{"code": e["code"], "title": e["title"], "file": e["file"], "chars": len(e["text"])}
           for e in (exhibits or [])]
    meta = {**meta, "coverage": round(coverage_ratio(result.doc.text, result.segments), 4)}
    return {"ok": True, "meta": meta, "items": items, "gaps": gaps, "exhibits": exs}


def sec_filings(query: str) -> dict:
    """List a ticker/CIK's available 10-K filings (newest first) so the front
    end can offer a year picker instead of always forcing the latest."""
    with _SEC_LOCK:
        fetcher = EdgarFetcher(cache_dir=ROOT / "data" / "raw_filings")
        resolver = FilingResolver(fetcher)
        try:
            cik = int(query) if query.isdigit() else resolver.cik_for_ticker(query)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"{query}: {e}"}
        out = [{"accession": f.accession, "form": f.form,
                "filing_date": f.filing_date, "report_date": f.report_date,
                "year": (f.report_date or f.filing_date or "")[:4]}
               for f in resolver.annual_filings(cik) if not f.is_amendment]
        return {"ok": True, "source": query.upper(), "filings": out}


def sec_extract(query: str, accession: str = "") -> dict:
    """Fetch + extract a ticker/CIK's 10-K (a specific accession if given, else
    the latest); certify Item 8."""
    with _SEC_LOCK:
        fetcher = EdgarFetcher(cache_dir=ROOT / "data" / "raw_filings")
        resolver = FilingResolver(fetcher)
        cik = int(query) if query.isdigit() else resolver.cik_for_ticker(query)
        annual = [f for f in resolver.annual_filings(cik) if not f.is_amendment]
        if accession:
            ref = next((f for f in annual if f.accession == accession), None)
        else:
            ref = annual[0] if annual else None
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
        exhibits = _fetch_exhibits(fetcher, ref)
        meta = {"source": query.upper(), "form": ref.form, "report_date": ref.report_date,
                "accession": ref.accession, "filing_class": result.filing_class,
                "xbrl_item8": xbrl, "latency_ms": round(result.latency_ms)}
        _SEC_STATE.update(result=result, meta=meta, exhibits=exhibits)
        return _items_payload(result, meta, exhibits)


def sec_upload(text: str, name: str) -> dict:
    """Extract an operator-supplied 10-K (HTML/TXT). No CIK → XBRL skipped."""
    with _SEC_LOCK:
        result = extract_from_html(text, Path(name).stem or "upload")
        meta = {"source": name, "form": "upload", "report_date": "-", "accession": "-",
                "filing_class": result.filing_class, "xbrl_item8": "",
                "latency_ms": round(result.latency_ms)}
        _SEC_STATE.update(result=result, meta=meta, exhibits=[])
        return _items_payload(result, meta, [])


def _slice_body(text: str, full_chars: int) -> tuple[str, bool]:
    CAP = 600_000
    truncated = full_chars > CAP
    out = text[:CAP]
    if truncated:
        out += (f"\n\n──── 顯示前 {CAP:,} 字,共 {full_chars:,} 字;其餘未顯示"
                f"(完整內容仍在 offset span 內)────")
    return out, truncated


def sec_item_text(code: str) -> dict:
    result = _SEC_STATE["result"]
    if result is None:
        return {"ok": False, "error": "尚未抽取任何 filing"}
    # gap:<start>-<end> — an uncovered region surfaced for completeness. It has
    # no item classification, but the source-exact text is still shown so
    # nothing in the filing is unreachable.
    if code.startswith("gap:"):
        try:
            a, b = (int(x) for x in code[4:].split("-"))
        except ValueError:
            return {"ok": False, "error": f"bad gap ref {code}"}
        body = result.doc.slice(a, b)
        text, truncated = _slice_body(body, len(body))
        return {"ok": True, "code": code, "title": "未分類內容(保底,無 Item 歸屬)",
                "status": "unclassified", "confidence": 0.0, "provenance": "gap_fill",
                "needs_review": True, "sha256": "", "offsets": [a, b],
                "full_chars": len(body), "truncated": truncated,
                "xbrl": "", "topic": "", "warnings": [], "text": text}
    # ex:<digits> — a real exhibit document fetched from the filing (List of
    # Subsidiaries, Certifications…), which lives in a SEPARATE file.
    if code.startswith("ex:"):
        ex = next((e for e in _SEC_STATE.get("exhibits", []) if e["code"] == code), None)
        if ex is None:
            return {"ok": False, "error": f"無 {code}"}
        text, truncated = _slice_body(ex["text"], len(ex["text"]))
        return {"ok": True, "code": code, "title": ex["title"], "status": "exhibit",
                "confidence": 0.0, "provenance": "filing_exhibit", "needs_review": False,
                "sha256": "", "offsets": [0, len(ex["text"])], "full_chars": len(ex["text"]),
                "truncated": truncated, "xbrl": "", "topic": "",
                "warnings": [f"獨立 exhibit 檔:{ex['file']}"], "text": text}
    seg = next((s for s in result.segments if s.item_code == code), None)
    if seg is None:
        return {"ok": False, "error": f"無 Item {code}"}
    body = result.text_of(code) if seg.end_offset > seg.start_offset else "(無正文 span)"
    # Never silently drop content: show the whole span. Cap only as an anti-DoS
    # guard well above the largest real item (Item 8/15 ≈ 200K chars), and when
    # it fires, say so explicitly rather than truncating in silence.
    full_chars = len(body)
    text, truncated = _slice_body(body, full_chars)
    return {"ok": True, "code": code, "title": seg.canonical_title, "status": seg.status,
            "confidence": round(seg.confidence, 2), "provenance": seg.provenance,
            "needs_review": seg.needs_review, "sha256": seg.text_sha256[:16],
            "offsets": [seg.start_offset, seg.end_offset],
            "full_chars": full_chars, "truncated": truncated,
            "xbrl": seg.xbrl_check, "topic": seg.topic_check,
            "warnings": seg.warnings, "text": text}


_FIND_MAX_HITS = 500


def _region_for(offset: int, blocks) -> tuple[str, int]:
    """Return (region_code, region_start) that contains a document offset, using
    the clean non-overlapping partition. An item block yields its item code; an
    unclassified block yields the matching gap:<a>-<b> code the viewer renders —
    so a hit is attributed to the TIGHTEST region that actually holds it, never
    to whichever overlapping item happened to sort first."""
    b = region_at(offset, blocks)
    if b is None:
        return "", 0
    return (b.code if b.code else f"gap:{b.start}-{b.end}"), b.start


def sec_find(q: str) -> dict:
    """Full-document find for Ctrl+F. Searches the ENTIRE normalized text and
    returns EVERY occurrence in document order, each tagged with the region
    (item span OR unclassified gap) that holds it and its occurrence index
    WITHIN that region — so the viewer can step prev/next across all hits,
    jumping between items/gaps, not just the one currently shown."""
    result = _SEC_STATE["result"]
    if result is None:
        return {"ok": False, "error": "尚未抽取任何 filing"}
    q = (q or "").strip()
    if not q:
        return {"ok": False, "error": "empty query"}
    text = result.doc.text
    low, needle = text.lower(), q.lower()
    blocks = partition_document(text, result.segments)
    hits, per_region, at = [], {}, low.find(needle)
    while at >= 0 and len(hits) < _FIND_MAX_HITS:
        code, rstart = _region_for(at, blocks)
        k = per_region.get(code, 0)
        per_region[code] = k + 1
        hits.append({"code": code, "k": k})   # k-th occurrence within that region
        at = low.find(needle, at + max(1, len(needle)))
    total = low.count(needle)
    # also search the filing's separate exhibit documents (subsidiaries etc.)
    for e in _SEC_STATE.get("exhibits", []):
        elow = e["text"].lower()
        total += elow.count(needle)
        p, k = elow.find(needle), 0
        while p >= 0 and len(hits) < _FIND_MAX_HITS:
            hits.append({"code": e["code"], "k": k})
            k += 1
            p = elow.find(needle, p + max(1, len(needle)))
    return {"ok": True, "found": bool(hits), "count": total, "hits": hits,
            "capped": total > len(hits)}


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


import re as _re
_SEC_CUE = _re.compile(r"10-?k|10-?q|\bsec\b|edgar|filing|財報|年報", _re.I)
_TICKER_STOP = {"SEC", "EDGAR", "AND", "THE", "USA", "PDF", "CEO", "CFO", "USD",
                "API", "URL", "HTML", "AI", "US", "UK", "NEW"}


def _sec_start_url(task: str) -> str:
    """Deterministic EDGAR entry for an obvious 'find company X's 10-K' task.
    The LLM preflight is unreliable at constructing this (it fell back to a
    search engine), so when the task clearly names a SEC filing AND a ticker,
    build the plain-HTML company-filing list URL directly — general enough
    (any ticker), and only the START point; extraction stays untouched."""
    if not _SEC_CUE.search(task):
        return ""
    for tok in _re.findall(r"\b[A-Z]{2,5}\b", task):
        if tok in _TICKER_STOP:
            continue
        return ("https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"
                f"&CIK={tok}&type=10-K&dateb=&owner=include&count=10")
    return ""


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
            # a real desktop UA: many sites (and SEC) reject the default
            # HeadlessChrome UA; the executor still has an httpx fallback for
            # hosts that fingerprint-block Chromium regardless.
            ctx = browser.new_context(
                viewport={"width": 1200, "height": 820}, accept_downloads=True,
                user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                            "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"))
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
                plan_steps: list[str] = []
                if not url or conds is None:
                    p_url, p_conds, p_plan = "", [], {}
                    try:
                        p_url, p_conds, p_plan = planner.plan_preflight(task)
                    except Exception:  # noqa: BLE001 — model unavailable → fall back
                        pass
                    plan_steps = p_plan.get("steps", [])
                    # Dynamic-workflow preamble: show the model's goal analysis,
                    # anticipated obstacles and planned steps BEFORE browsing, so
                    # the run opens with a thought-through route, not a blind hop.
                    if p_plan.get("analysis"):
                        rec["steps"].append(f"🎯 目標分析:{p_plan['analysis']}")
                    if p_plan.get("obstacles"):
                        rec["steps"].append("⚠ 預判困難:" + " · ".join(p_plan["obstacles"]))
                    if p_plan.get("steps"):
                        rec["steps"].append("📋 規畫步驟:" + " → ".join(
                            f"{i+1}) {s}" for i, s in enumerate(p_plan["steps"])))
                    if not url:
                        # a deterministic EDGAR deep-link (when the task clearly
                        # names a ticker + SEC filing) beats the LLM's guess
                        url = _sec_start_url(task) or p_url or DEFAULT_START
                    if conds is None:
                        conds = p_conds or derive_success(task)
                    # NEVER hard-fail for lack of a condition — that killed
                    # generality (an open-ended task like "找最熱門的財經節目"
                    # has no crisp success string). Run the task anyway; with no
                    # verifiable condition the verifier returns an honest
                    # `unknown`, never a disguised pass.
                    rec["url"], rec["success"] = url, conds or ["(無明確成功條件 → 結果以 unknown 誠實回報)"]
                    plan = f"起點 {url}" + (f" · 成功條件 {' / '.join(conds)}" if conds
                                           else " · 無可驗證條件,結果將誠實標示 unknown")
                    rec["steps"].append(f"🧭 規畫:{plan}")
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
                run = agent.run_agentic(run_id, contract, planner, max_steps=18,
                                        on_step=lambda t: rec["steps"].append(t),
                                        plan_steps=plan_steps)
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
        elif u.path == "/api/sec/find":
            self._json(sec_find(parse_qs(u.query).get("q", [""])[0]))
        elif u.path == "/api/sec/filings":
            self._json(sec_filings(parse_qs(u.query).get("query", [""])[0].strip()))
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
                self._json(sec_extract(req.get("query", "").strip(), req.get("accession", "").strip()))
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
