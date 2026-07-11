r"""P1-1 naive baseline — the shortcut detector.

A deliberately trivial agent: goto the task's website, fill the FIRST fillable
element with keywords from the task text (press Enter), then click the FIRST
link/button whose text shares a keyword. No repair, no vision, no planner, no
retries, no modal dismissal. The SAME verifier (verify_contract) is the only
judge — the baseline gets no benefit of the doubt.

Why it exists: if a task set can be passed by this, the task set is shortcut-
table and a high score proves nothing (Online-Mind2Web paper: a naive search
agent scores 22% vs 51% SOTA — arXiv:2504.01382). We report the trivial-pass
rate on the same task files the real agent runs, so "our mechanisms add value"
is a measured delta, not a claim.

Task file schema = the P1-1 subset format (data/browser_eval/external/
mind2web_subset.json): entries with website / natural_language_task /
success_conditions. Works on any file with that shape, including local
file:// mock-site tasks (used by the offline tests).

Usage:
  .venv\Scripts\python tools\naive_baseline.py                  # the m2w subset (live web)
  .venv\Scripts\python tools\naive_baseline.py --tasks path.json --limit 5 --headed
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

from browser_core import BrowserTaskContract, ForbiddenCondition, SuccessCondition
from browser_agent.nl import _STOP
from browser_agent.observer import PageObserver
from browser_agent.verifier import verify_contract

ROOT = Path(__file__).resolve().parents[1]
TASKS_DEFAULT = ROOT / "data" / "browser_eval" / "external" / "mind2web_subset.json"
OUT = ROOT / "runs" / "naive_baseline"

_FILLABLE = ("input[type=text], input[type=search], input:not([type]), "
             "textarea, [role=searchbox]")
_SUBMITTABLE = "button, [role=button], input[type=submit]"
_SUBMIT_RE = re.compile(r"search|submit|go|find|apply", re.IGNORECASE)
_CLICKABLE = "a, button, [role=button]"
_ACTION_TIMEOUT_MS = 5_000


def keywords(task: str) -> list[str]:
    """Naive keyword pick: a quoted phrase wins, else the first few content
    words (Latin tokens minus stopwords, original order). This is the whole
    'planning' of the baseline — deliberately dumb."""
    quoted = re.findall(r"['\"“」『]([^'\"”」』]{2,60})['\"”」』]", task)
    if quoted:
        return [quoted[0]]
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", task)
             if w.lower() not in _STOP]
    return words[:4]


def contract_from_entry(e: dict) -> BrowserTaskContract:
    return BrowserTaskContract(
        task_id=e["task_id"],
        natural_language_task=e["natural_language_task"],
        expected_outcome=e.get("expected_outcome", "success conditions hold"),
        success_conditions=[SuccessCondition(**c) for c in e.get("success_conditions", [])],
        forbidden_conditions=[ForbiddenCondition(**c) for c in e.get("forbidden_conditions", [])])


def naive_actions(page, kws: list[str]) -> list[str]:
    """The baseline's ENTIRE repertoire, first match only, every failure
    swallowed — a naive agent doesn't diagnose, it shrugs:
      1. fill the first fillable element with the query
      2. click the first submit-looking control (this is where drift kills it:
         a decoy 'Search' button or a blocking cookie modal is taken at face
         value — no modal dismissal, no second candidate, no repair)
      3. only if (2) landed nothing: click the first link matching a keyword
    Returns the log of what happened."""
    log: list[str] = []
    query = " ".join(kws)
    try:
        box = page.locator(_FILLABLE).first
        box.fill(query, timeout=_ACTION_TIMEOUT_MS)
        log.append(f"fill({query!r}):ok")
    except Exception as exc:  # noqa: BLE001 — no repair, by design
        log.append(f"fill({query!r}):fail {type(exc).__name__}")
    submitted = False
    try:
        btn = page.locator(_SUBMITTABLE, has_text=_SUBMIT_RE).first
        btn.click(timeout=_ACTION_TIMEOUT_MS)
        submitted = True
        log.append("click(submit-ish):ok")
    except Exception as exc:  # noqa: BLE001
        log.append(f"click(submit-ish):fail {type(exc).__name__}")
    try:
        page.wait_for_load_state("networkidle", timeout=_ACTION_TIMEOUT_MS)
    except Exception:  # noqa: BLE001
        pass
    if not submitted:
        for kw in kws:
            try:
                el = page.locator(_CLICKABLE,
                                  has_text=re.compile(re.escape(kw), re.I)).first
                el.click(timeout=_ACTION_TIMEOUT_MS)
                log.append(f"click({kw!r}):ok")
                break
            except Exception as exc:  # noqa: BLE001
                log.append(f"click({kw!r}):fail {type(exc).__name__}")
    return log


def run_naive(page, entry: dict) -> dict:
    """One task, one shot: goto -> naive actions -> verifier verdict."""
    contract = contract_from_entry(entry)
    t0 = time.monotonic()
    log: list[str] = []
    try:
        page.goto(entry["website"], wait_until="domcontentloaded", timeout=30_000)
        log.append("goto:ok")
        log += naive_actions(page, keywords(entry["natural_language_task"]))
        verdict = verify_contract(contract, PageObserver(page).observe())
        status, reason = verdict.status, verdict.reason
    except Exception as exc:  # noqa: BLE001 — site unreachable etc.
        log.append(f"goto:fail {type(exc).__name__}")
        status, reason = "fail", f"naive run crashed: {type(exc).__name__}: {exc}"
    return {
        "task_id": entry["task_id"],
        "difficulty": entry.get("difficulty", ""),
        "website": entry["website"],
        "status": status,
        "verifier_reason": reason,
        "actions": log,
        "latency_ms": round((time.monotonic() - t0) * 1000, 1),
    }


def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    passes = sum(r["status"] == "pass" for r in rows)
    return {
        "agent": "naive_baseline (goto + first-match fill/click; no repair, "
                 "no vision, no planner)",
        "judge": "verify_contract — same verifier as the real agent",
        "tasks": n,
        "pass": passes,
        "fail": sum(r["status"] == "fail" for r in rows),
        "unknown": sum(r["status"] == "unknown" for r in rows),
        "trivial_pass_rate": round(passes / n, 3) if n else 0.0,
        "rows": rows,
    }


def main() -> None:
    from playwright.sync_api import sync_playwright

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tasks", type=Path, default=TASKS_DEFAULT)
    ap.add_argument("--limit", type=int, default=0, help="run only the first N tasks")
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()

    entries = json.loads(args.tasks.read_text(encoding="utf-8"))["tasks"]
    if args.limit:
        entries = entries[:args.limit]

    rows = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed)
        for e in entries:
            context = browser.new_context(viewport={"width": 1100, "height": 850})
            page = context.new_page()
            row = run_naive(page, e)
            rows.append(row)
            print(f"  {row['task_id']:<24} {row['status']:<8} {row['verifier_reason'][:60]}")
            context.close()
        browser.close()

    summary = summarize(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / "results.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\ntrivial-pass rate: {summary['trivial_pass_rate']:.1%} "
          f"({summary['pass']}/{summary['tasks']})  -> {out}")


if __name__ == "__main__":
    main()
