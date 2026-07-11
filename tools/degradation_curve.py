"""Degradation-curve runner — mutation matrix x success/recovery (T1-2).

Drives the REAL BrowserAgent (Script Mode) across the generated mutation matrix
(tools/gen_mutation_sites.py: 1 clean reference + perception/action/execution
axes x light/medium/heavy) with N queries per cell, and measures — not asserts:

- success_rate        final verify_contract pass on the full contract (full
                      product name required, so a query echo cannot fake it)
- checkpoint_rate     mid-task checkpoint: after the fill phase, the query is
                      in the REAL search field. The real field is identified by
                      the site's `data-sb` ground-truth instrumentation (the
                      agent's observer never enumerates that attribute); the
                      runner collects the field value and feeds it to
                      verify_contract(field_value_equals) — the SAME
                      three-state verifier mechanism as the final verdict.
- fault_encountered   any repair-mode step in the trace (incl. modal dismissal)
- recovery_rate       among fault-encountering runs: final verdict pass
                      (= mid-task recovery)
- avg_repairs         repair cost even where success holds

Offline, deterministic, no LLM (fault schedules are attempt-counter/event
anchored; fresh selector memory per run). Basis: StressWeb (arxiv 2604.16385)
degradation curves over a clean reference.

Usage:  .venv/Scripts/python tools/degradation_curve.py
Reads   data/mock_sites/mutations/<cell>/index.html
Writes  data/browser_eval/artifacts/degradation_curve.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from browser_core import BrowserTaskContract, ForbiddenCondition, SuccessCondition
from browser_agent.agent import BrowserAgent, Step
from browser_agent.memory_store import MemoryStore
from browser_agent.verifier import verify_contract

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gen_mutation_sites as gen  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SITES = ROOT / "data" / "mock_sites" / "mutations"
OUT = ROOT / "data" / "browser_eval" / "artifacts"
SCRATCH = ROOT / "runs" / "browser_eval"          # gitignored scratch for memory files

AXES = ("perception", "action", "execution")
LEVELS = ("light", "medium", "heavy")
# full product names: the success needle must be a real result row, not the
# `N results for "query"` echo (see FG query-echo failure family, T1-3)
QUERIES = [("widget", "Widget Pro 3000"), ("gizmo", "Gizmo Deluxe"),
           ("sprocket", "Sprocket XL")]

_SB_VALUE_JS = "() => { const b = document.querySelector('[data-sb]'); return b ? b.value : ''; }"


def uri(cell_id: str) -> str:
    return (SITES / cell_id / "index.html").resolve().as_uri()


def contract(cell_id: str, query: str, product: str) -> BrowserTaskContract:
    return BrowserTaskContract(
        task_id=f"{cell_id}-{query}",
        natural_language_task=f"Search MockShop for '{query}'",
        expected_outcome=f"Results listing {product} are shown",
        success_conditions=[SuccessCondition(type="text_visible", value="results for"),
                            SuccessCondition(type="text_visible", value=product)],
        forbidden_conditions=[ForbiddenCondition(type="captcha_visible", value="captcha")],
    )


def checkpoint_contract(query: str) -> BrowserTaskContract:
    """Mid-task checkpoint as a first-class verifier contract: the query string
    sits in the real search field. Evidence (the field value) is collected by
    the runner; the judgement is verify_contract's, not the runner's."""
    return BrowserTaskContract(
        task_id=f"checkpoint-{query}",
        natural_language_task=f"mid-task checkpoint: '{query}' typed into the search field",
        expected_outcome="query present in the real search field",
        success_conditions=[SuccessCondition(type="field_value_equals", value=query)],
    )


def run_cell(page, cell_id: str, query: str, product: str, mem_path: Path) -> dict:
    """One (cell, query) probe: fill phase -> checkpoint -> submit phase.
    Fresh memory per probe keeps every probe independent and reproducible."""
    if mem_path.exists():
        mem_path.unlink()
    mem = MemoryStore(mem_path)
    page.goto(uri(cell_id))
    agent = BrowserAgent(page, mem, site=f"mutation-{cell_id}", task_type="search")
    full = contract(cell_id, query, product)

    # phase 1: reach the mid-task state (query typed). run()'s own verdict here
    # is discarded — the checkpoint below re-verifies through verify_contract
    # with the runner-collected field evidence.
    r1 = agent.run(f"{cell_id}-{query}-mid",
                   [Step(purpose="search_box", kind="fill", value=query,
                         fallback_selector="#search-box")], full)
    obs = agent.observer.observe()
    sb_value = page.evaluate(_SB_VALUE_JS)   # ground-truth field, invisible to the agent
    ck = verify_contract(checkpoint_contract(query), obs, {"search_box": sb_value})

    # phase 2: submit + final verdict on the full contract
    r2 = agent.run(f"{cell_id}-{query}",
                   [Step(purpose="submit_button", kind="click",
                         fallback_selector="#search-btn")], full)

    steps = r1.steps + r2.steps
    fault = any(s.mode == "repair" for s in steps)
    repairs = r1.repairs + r2.repairs
    # FIX-3 honesty marker: a repair that finds NO feasible candidate refuses
    # ("no viable candidate") instead of clicking an infeasible element; that
    # distinction belongs in the committed artifact, not just the trace.
    honest_refusals = sum(1 for s in steps
                          if s.mode == "repair" and s.detail == "no viable candidate")
    return {
        "cell": cell_id, "query": query, "status": r2.status,
        "checkpoint": ck.status, "repairs": repairs,
        "honest_refusals": honest_refusals,
        "fault_encountered": fault,
        "recovered": bool(fault and r2.status == "pass"),
        "verifier_reason": r2.verifier.reason,
        "latency_ms": round(r1.total_latency_ms + r2.total_latency_ms, 1),
    }


def summarize_cell(rows: list[dict]) -> dict:
    """Pure aggregation over one cell's probe rows (unit-testable, no browser)."""
    n = len(rows)
    faults = [r for r in rows if r["fault_encountered"]]
    return {
        "n": n,
        "success_rate": round(sum(r["status"] == "pass" for r in rows) / n, 3),
        "checkpoint_rate": round(sum(r["checkpoint"] == "pass" for r in rows) / n, 3),
        "fault_encountered_rate": round(len(faults) / n, 3),
        # no fault observed -> recovery is not measurable; None, never a fake 1.0
        "recovery_rate": round(sum(r["recovered"] for r in faults) / len(faults), 3)
        if faults else None,
        "avg_repairs": round(sum(r["repairs"] for r in rows) / n, 2),
        "statuses": sorted({r["status"] for r in rows}),
    }


def build_curves(cell_summaries: dict) -> dict:
    """Degradation curve per axis: [clean, light, medium, heavy] with the clean
    reference shared as intensity 0 (StressWeb layout)."""
    curves: dict[str, dict] = {}
    for axis in AXES:
        pts = []
        for intensity, cell_id in enumerate(["clean"] + [f"{axis}-{lv}" for lv in LEVELS]):
            s = cell_summaries[cell_id]
            pts.append({"intensity": intensity, "cell": cell_id,
                        "success_rate": s["success_rate"],
                        "checkpoint_rate": s["checkpoint_rate"],
                        "recovery_rate": s["recovery_rate"],
                        "avg_repairs": s["avg_repairs"]})
        curves[axis] = {
            "points": pts,
            "monotone_non_increasing_success": all(
                pts[i]["success_rate"] >= pts[i + 1]["success_rate"]
                for i in range(len(pts) - 1)),
        }
    return curves


def main() -> None:
    missing = [c for c in gen.CELLS if not (SITES / c / "index.html").exists()]
    if missing:
        raise SystemExit(f"mutation sites missing: {missing} — run tools/gen_mutation_sites.py")
    OUT.mkdir(parents=True, exist_ok=True)
    SCRATCH.mkdir(parents=True, exist_ok=True)
    mem_path = SCRATCH / "_mem_degradation.json"

    rows_by_cell: dict[str, list[dict]] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1000, "height": 800})
        for cell_id in gen.CELLS:
            rows_by_cell[cell_id] = [run_cell(page, cell_id, q, prod, mem_path)
                                     for q, prod in QUERIES]
        browser.close()
    mem_path.unlink(missing_ok=True)

    summaries = {
        cid: {**{k: gen.CELLS[cid][k] for k in ("axis", "level", "level_name")},
              **summarize_cell(rows)}
        for cid, rows in rows_by_cell.items()
    }
    curves = build_curves(summaries)
    out = {
        "generated_by": "tools/degradation_curve.py",
        "sites_from": "tools/gen_mutation_sites.py -> data/mock_sites/mutations/",
        "queries": [q for q, _ in QUERIES],
        "definitions": {
            "success": "final verify_contract pass on the full contract (text_visible "
                       "'results for' + full product name; forbidden captcha)",
            "checkpoint": "mid-task: query present in the REAL search field ([data-sb] "
                          "ground-truth instrumentation, invisible to the agent's observer), "
                          "verified via verify_contract(field_value_equals) with "
                          "runner-collected evidence",
            "fault_encountered": "any repair-mode step in the trace (incl. modal dismissal)",
            "recovered": "fault_encountered AND final verdict pass (mid-task recovery)",
            "honest_refusals": "repair steps that returned 'no viable candidate' (feasibility "
                               "gate, FIX-3) instead of acting on an infeasible element — a "
                               "fail with refusals is an honest fail, not a silent wrong click",
            "determinism": "attempt-counter + input-event-anchored faults, no Math.random; "
                           "fresh selector memory per probe",
        },
        "cells": summaries,
        "curves": curves,
        "runs": [r for rows in rows_by_cell.values() for r in rows],
    }
    dest = OUT / "degradation_curve.json"
    dest.write_text(json.dumps(out, indent=2), encoding="utf-8")

    print("degradation curve (success / checkpoint / recovery / avg repairs):")
    for cid, s in summaries.items():
        rec = "n/a " if s["recovery_rate"] is None else f"{s['recovery_rate']:<4}"
        print(f"  {cid:<18} success={s['success_rate']:<6} ckpt={s['checkpoint_rate']:<6} "
              f"recovery={rec} repairs={s['avg_repairs']}")
    for axis, c in curves.items():
        print(f"  curve[{axis}]: "
              f"{' -> '.join(str(p['success_rate']) for p in c['points'])} "
              f"(monotone_non_increasing={c['monotone_non_increasing_success']})")
    print(f"wrote {dest}")


if __name__ == "__main__":
    main()
