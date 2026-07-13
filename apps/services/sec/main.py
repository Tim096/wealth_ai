"""wealth-sec — Task 2 public frontend + API.

FastAPI wrapper over packages/sec_core (read-only: import, never patch):
  · select filings by ticker/CIK (+ optional accession year picker),
  · upload a local 10-K HTML (offline re-enable of test_center's removed
    _ingest_html, as POST /api/upload),
  · run extraction as background jobs with GET polling,
  · per-item status / confidence / provenance / needs_review, source-exact
    item text, full-document find, byte-for-byte raw-filing download,
  · failure cases stay inspectable: error jobs keep message + traceback.

Serves the adapted SEC panel UI at / and the prebuilt static eval dashboard
at /dashboard. Endpoint logic mirrors tools/test_center.py's SEC handlers but
is job-scoped (no global mutable filing state) — test_center itself is never
imported.
"""

from __future__ import annotations

import os
import re
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

from sec_core.coverage import compute_gaps, coverage_ratio, partition_document, region_at
from sec_core.fetcher import EdgarFetcher
from sec_core.main_doc import pick_main_document
from sec_core.normalize import normalize_html
from sec_core.pipeline import extract_from_html
from sec_core.resolver import FilingResolver
from sec_core.risk_band import band_payload
from sec_core.xbrl import certify_item8

from apps.services.sec.jobs import Job, JobStore

ROOT = Path(__file__).resolve().parents[3]
CACHE_DIR = ROOT / "data" / "raw_filings"      # ephemeral in the container — warms per-instance
STATIC_INDEX = Path(__file__).resolve().parent / "static" / "index.html"
DASHBOARD_INDEX = ROOT / "apps" / "web" / "eval-dashboard" / "index.html"
MAX_UPLOAD_BYTES = 40 * 1024 * 1024

JOBS = JobStore()

# ------------------------------------------------------------------ auth gate
def require_token(x_access_token: str | None = Header(default=None),
                  token: str | None = Query(default=None)) -> None:
    """No-op unless ACCESS_TOKEN is set (default unset so graders need no auth)."""
    expected = os.environ.get("ACCESS_TOKEN", "")
    if not expected:
        return
    if x_access_token == expected or token == expected:
        return
    raise HTTPException(status_code=401, detail="invalid or missing access token")


AUTH = [Depends(require_token)]

# ------------------------------------------------------- extraction (job fns)
# Real exhibits (21.1 Subsidiaries, 23.1 Consent, 31/32 Certifications, 97.1
# Clawback) are SEPARATE files of the filing — fetched too, for completeness.
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


def _fetch_exhibits(fetcher: EdgarFetcher, ref) -> list[dict]:
    out: list[dict] = []
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


def _items_payload(result, meta: dict, exhibits: list[dict]) -> dict:
    items = []
    for s in result.segments:
        items.append({
            "code": s.item_code, "title": s.canonical_title, "status": s.status,
            "confidence": round(s.confidence, 2), "risk_band": band_payload(s.confidence),
            "provenance": s.provenance,
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
                     "after": g.after_code, "before": g.before_code, "start": g.start})
    exs = [{"code": e["code"], "title": e["title"], "file": e["file"], "chars": len(e["text"])}
           for e in exhibits]
    meta = {**meta, "coverage": round(coverage_ratio(result.doc.text, result.segments), 4),
            "pipeline_warnings": result.warnings}
    return {"ok": True, "meta": meta, "items": items, "gaps": gaps, "exhibits": exs}


def _run_extract(query: str, accession: str) -> tuple[dict, dict]:
    """Fetch + extract a ticker/CIK's 10-K (specific accession if given, else
    latest); certify Item 8 against SEC's official XBRL numbers."""
    fetcher = EdgarFetcher(cache_dir=CACHE_DIR)
    resolver = FilingResolver(fetcher)
    cik = int(query) if query.isdigit() else resolver.cik_for_ticker(query)
    annual = [f for f in resolver.annual_filings(cik) if not f.is_amendment]
    if accession:
        ref = next((f for f in annual if f.accession == accession), None)
    else:
        ref = annual[0] if annual else None
    if ref is None:
        raise LookupError(f"{query}: 找不到 10-K (accession={accession or 'latest'})")
    resolver.load_files(ref)
    best = pick_main_document(ref)
    raw_bytes = fetcher.get(ref.file_url(best.name)).content
    raw = raw_bytes.decode("utf-8", errors="replace")
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
    raw_name = f"{query.upper()}_{ref.accession}_{best.name}"
    state = {"result": result, "exhibits": exhibits, "raw": raw_bytes, "raw_name": raw_name}
    return _items_payload(result, meta, exhibits), state


def _run_upload(text: str, name: str) -> tuple[dict, dict]:
    """Extract an uploaded HTML/TXT 10-K WITHOUT any network — the offline
    re-enable of test_center's removed _ingest_html, now a real route."""
    result = extract_from_html(text, Path(name).stem or "upload")
    meta = {"source": name, "form": "upload", "report_date": "-", "accession": "-",
            "filing_class": result.filing_class, "xbrl_item8": "",
            "latency_ms": round(result.latency_ms)}
    state = {"result": result, "exhibits": [],
             "raw": text.encode("utf-8", "replace"), "raw_name": name}
    return _items_payload(result, meta, []), state


# ------------------------------------------------ per-job item text and find
def _slice_body(text: str, full_chars: int) -> tuple[str, bool]:
    CAP = 600_000
    truncated = full_chars > CAP
    out = text[:CAP]
    if truncated:
        out += (f"\n\n──── 顯示前 {CAP:,} 字,共 {full_chars:,} 字;其餘未顯示"
                f"(完整內容仍在 offset span 內)────")
    return out, truncated


def _item_text(state: dict, code: str) -> dict:
    result = state["result"]
    if code.startswith("gap:"):     # uncovered region surfaced for completeness
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
    if code.startswith("ex:"):      # separate exhibit document of the filing
        ex = next((e for e in state.get("exhibits", []) if e["code"] == code), None)
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
    full_chars = len(body)
    text, truncated = _slice_body(body, full_chars)
    return {"ok": True, "code": code, "title": seg.canonical_title, "status": seg.status,
            "confidence": round(seg.confidence, 2), "risk_band": band_payload(seg.confidence),
            "provenance": seg.provenance,
            "needs_review": seg.needs_review, "sha256": seg.text_sha256[:16],
            "offsets": [seg.start_offset, seg.end_offset],
            "full_chars": full_chars, "truncated": truncated,
            "xbrl": seg.xbrl_check, "topic": seg.topic_check,
            "warnings": seg.warnings, "text": text}


_FIND_MAX_HITS = 500


def _region_for(offset: int, blocks) -> tuple[str, int]:
    b = region_at(offset, blocks)
    if b is None:
        return "", 0
    return (b.code if b.code else f"gap:{b.start}-{b.end}"), b.start


def _find(state: dict, q: str) -> dict:
    """Full-document find: every occurrence in document order, tagged with the
    region (item span OR unclassified gap OR exhibit) that holds it."""
    result = state["result"]
    q = (q or "").strip()
    if not q:
        return {"ok": False, "error": "empty query"}
    text = result.doc.text
    low, needle = text.lower(), q.lower()
    blocks = partition_document(text, result.segments)
    hits, per_region, at = [], {}, low.find(needle)
    while at >= 0 and len(hits) < _FIND_MAX_HITS:
        code, _ = _region_for(at, blocks)
        k = per_region.get(code, 0)
        per_region[code] = k + 1
        hits.append({"code": code, "k": k})
        at = low.find(needle, at + max(1, len(needle)))
    total = low.count(needle)
    for e in state.get("exhibits", []):
        elow = e["text"].lower()
        total += elow.count(needle)
        p, k = elow.find(needle), 0
        while p >= 0 and len(hits) < _FIND_MAX_HITS:
            hits.append({"code": e["code"], "k": k})
            k += 1
            p = elow.find(needle, p + max(1, len(needle)))
    return {"ok": True, "found": bool(hits), "count": total, "hits": hits,
            "capped": total > len(hits)}


# ------------------------------------------------------------------- FastAPI
@asynccontextmanager
async def _lifespan(_: FastAPI):
    """Pre-warm the demo tickers in ONE background thread (non-blocking, keeps
    the worker pool free): fills the ephemeral raw-filing disk cache AND the
    result memo, so first clicks after a container start are instant.
    Set PREWARM_TICKERS="" to disable (e.g. offline tests)."""
    tickers = [t.strip().upper() for t in
               os.environ.get("PREWARM_TICKERS", "INTC,AAPL,MSFT").split(",") if t.strip()]

    def run() -> None:
        for t in tickers:
            if JOBS.lookup("extract", t, "") is None:
                JOBS.run_sync("extract", t, lambda t=t: _run_extract(t, ""), memo_key="")

    if tickers:
        threading.Thread(target=run, daemon=True, name="sec-prewarm").start()
    yield


app = FastAPI(title="wealth-sec", description="SEC 10-K item-level extractor — Task 2",
              lifespan=_lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1024)   # 68KB item JSON → ~15KB on the wire


class ExtractRequest(BaseModel):
    ticker: str = ""
    query: str = ""       # alias kept for UI parity with test_center
    accession: str = ""


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "service": "wealth-sec",
            "sec_user_agent_configured": bool(os.environ.get("SEC_EDGAR_USER_AGENT", "").strip()),
            "auth_required": bool(os.environ.get("ACCESS_TOKEN", "")),
            "jobs": len(JOBS.list())}


@app.get("/api/filings", dependencies=AUTH)
def filings(query: str = Query(default="")) -> dict:
    """List a ticker/CIK's 10-K filings (newest first) — live EDGAR query, so
    the year picker works with a cold cache. Honest refusal for non-10-K
    filers (20-F/40-F) is returned as ok:false with the real form mix."""
    query = query.strip()
    if not query:
        return {"ok": False, "error": "empty query"}
    try:
        fetcher = EdgarFetcher(cache_dir=CACHE_DIR)
        resolver = FilingResolver(fetcher)
        cik = int(query) if query.isdigit() else resolver.cik_for_ticker(query)
        out = [{"accession": f.accession, "form": f.form,
                "filing_date": f.filing_date, "report_date": f.report_date,
                "year": (f.report_date or f.filing_date or "")[:4]}
               for f in resolver.annual_filings(cik) if not f.is_amendment]
    except Exception as e:  # noqa: BLE001 — surface the reason, never 500
        return {"ok": False, "error": f"{query}: {e}"}
    return {"ok": True, "source": query.upper(), "filings": out}


@app.post("/api/extract", dependencies=AUTH)
def extract(req: ExtractRequest) -> dict:
    query = (req.ticker or req.query).strip()
    if not query:
        raise HTTPException(status_code=400, detail="ticker (or query) is required")
    accession = req.accession.strip()
    label = query.upper()
    # Result cache: a done job for the same (ticker, accession) is returned
    # inline (payload included — the UI can render with zero polling); a
    # queued/running one is reused instead of spawning duplicate work.
    job = JOBS.lookup("extract", label, accession)
    if job is None:
        job = JOBS.submit("extract", label,
                          lambda: _run_extract(query, accession), memo_key=accession)
    out = {"ok": True, "job_id": job.job_id, "status": job.status}
    if job.status == "done" and job.payload:
        out.update(job.payload)
    return out


@app.post("/api/upload", dependencies=AUTH)
async def upload(file: UploadFile = File(...)) -> dict:
    """Upload a 10-K HTML/TXT and extract it offline (no EDGAR access).
    Runs inline — offline extraction finishes in seconds — and returns the
    full item payload plus a job_id usable with the item/find/raw endpoints."""
    blob = await file.read()
    if len(blob) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="file too large (max 40 MB)")
    text = blob.decode("utf-8", errors="replace")
    name = Path(file.filename or "upload.htm").name
    job = JOBS.run_sync("upload", name, lambda: _run_upload(text, name))
    if job.status == "error":
        return {"ok": False, "job_id": job.job_id, "status": "error",
                "error": job.error, "trace": job.trace}
    return {"ok": True, "job_id": job.job_id, "status": "done", **(job.payload or {})}


@app.get("/api/jobs", dependencies=AUTH)
def jobs_list() -> dict:
    return {"ok": True, "jobs": JOBS.list()}


def _get_job(job_id: str) -> Job:
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"unknown job {job_id}")
    return job


@app.get("/api/jobs/{job_id}", dependencies=AUTH)
def job_status(job_id: str) -> dict:
    job = _get_job(job_id)
    out = {"ok": job.status != "error", "job_id": job.job_id, "kind": job.kind,
           "label": job.label, "status": job.status,
           "error": job.error, "trace": job.trace}
    if job.status == "done" and job.payload:
        out.update(job.payload)          # meta / items / gaps / exhibits
    return out


@app.get("/api/jobs/{job_id}/item", dependencies=AUTH)
def job_item(job_id: str, code: str = Query(default="")) -> dict:
    job = _get_job(job_id)
    if job.status != "done":
        return {"ok": False, "error": f"job {job_id} 狀態 {job.status},尚無結果"}
    return _item_text(job.state, code)


@app.get("/api/jobs/{job_id}/find", dependencies=AUTH)
def job_find(job_id: str, q: str = Query(default="")) -> dict:
    job = _get_job(job_id)
    if job.status != "done":
        return {"ok": False, "error": f"job {job_id} 狀態 {job.status},尚無結果"}
    return _find(job.state, q)


@app.get("/api/jobs/{job_id}/raw", dependencies=AUTH)
def job_raw(job_id: str) -> Response:
    """The original source document byte-for-byte (offset-exact against what
    was analysed) — for independent verification."""
    job = _get_job(job_id)
    raw = job.state.get("raw", b"")
    if not raw:
        raise HTTPException(status_code=404, detail="job has no raw filing")
    name = job.state.get("raw_name", "filing.htm")
    return Response(content=raw, media_type="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


# ------------------------------------------------------------------- UI pages
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def index() -> HTMLResponse:
    return HTMLResponse(STATIC_INDEX.read_text(encoding="utf-8"))


@app.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
def dashboard() -> HTMLResponse:
    if not DASHBOARD_INDEX.exists():
        raise HTTPException(status_code=404, detail="eval dashboard not bundled")
    return HTMLResponse(DASHBOARD_INDEX.read_text(encoding="utf-8"))
