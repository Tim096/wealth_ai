r"""P1-1 external live-task eval runner — the productized, reproducible path.

`tools/browser_eval.py` runs the LAYERED MOCK set offline; the live m2w numbers
in docs/research/giants_task1.md were produced by a throwaway scratchpad script.
This runner is that path made a committed, CI-able tool: it reads the external
live-task file (data/browser_eval/external/*.json), drives the REAL agent
(BrowserAgent.run_agentic + LLMPlanner over the Codex gateway) at the P1-15
per-difficulty step budget, runs the advisory second judge, persists one P0-9
guarded summary.json per task under a run dir, and prints a success-rate summary
(overall + per difficulty + env-error classification per
data/browser_eval/external/README.md).

The verifier stays the SOLE judge (verify_contract, inside run_agentic). The
second judge is advisory only — it never changes a verdict. Env-error
classification separates a site blocking us (CAPTCHA / login wall / unreachable
— NOT the agent's fault, excluded from the success denominator) from a genuine
agent failure, so the reported rate is honest.

Usage:
  # 1) Codex gateway (reuse a running one — never kill it):
  #      python tools/codex_gateway.py --model gpt-5.3-codex
  .venv\Scripts\python tools\run_external_eval.py                     # full m2w subset
  .venv\Scripts\python tools\run_external_eval.py --limit 3 --headed  # first 3, watch
  .venv\Scripts\python tools\run_external_eval.py --resume            # skip finished tasks
  .venv\Scripts\python tools\run_external_eval.py --direct            # OpenAI via OPENAI_API_KEY
  .venv\Scripts\python tools\run_external_eval.py --no-second-judge   # verdicts only
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

from browser_core import BrowserTaskContract, ForbiddenCondition, SuccessCondition
from browser_agent.agent import BrowserAgent, DEFAULT_MAX_STEPS, resolve_max_steps
from browser_agent.memory_store import MemoryStore
from browser_agent.observer import PageObserver
from browser_agent.planner import LLMPlanner, MockPlanner
from browser_agent.second_judge import (
    LLMExtractor, OfflineExtractor, SecondJudgeSmokeError, cache_evidence,
    diff_with_primary, judge_open_ended, judge_task, load_evidence, smoke_test,
)
from browser_agent.verifier import check_conditions
from llm_core.config import load_llm_config
from llm_core.openai_client import OpenAIClient
from observability_core import EvidenceStore

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))                    # `tools.` imports when run as a script
from tools.eval_worker import (                  # noqa: E402
    HarnessAbort, arm_watchdog, harness_report, load_done_summary,
    run_guarded, scan_incomplete, should_abort,
)
from tools.run_manifest import DirtyTreeError, write_manifest  # noqa: E402

TASKS_DEFAULT = ROOT / "data" / "browser_eval" / "external" / "mind2web_subset.json"
OUT_DEFAULT = ROOT / "runs" / "browser_eval" / "external_run"

# Env-error taxonomy (data/browser_eval/external/README.md): a live site blocking
# us is NOT an agent failure. Ordered most-specific first; the first matching
# pattern wins. A row that matches none is a genuine verdict (agent's own result).
_ENV_ERROR_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("anti_bot", re.compile(
        r"captcha|recaptcha|are you (a )?human|bot detect|cloudflare|"
        r"access denied|forbidden|\b403\b|\b429\b|perimeterx|blocked", re.I)),
    ("auth_required", re.compile(
        r"\blog ?in\b|\bsign ?in\b|please sign|authenticat|credentials|"
        r"account required", re.I)),
    ("site_unreachable", re.compile(
        r"timeout|timed out|net::|err_|dns|connection|unreachable|"
        r"navigation failed|goto:fail|522|503|502", re.I)),
]


def classify_env_error(harness_status: str, error: str | None,
                       status: str | None, verifier_reason: str | None) -> str | None:
    """Classify an environmental block (site's fault) vs a real agent failure.

    A harness error (the guard caught a crash — usually an unreachable site or a
    navigation timeout) or a forbidden-condition violation on a live wall
    (captcha/login) is environmental: excluded from the success denominator and
    reported separately. A plain `violated:`/`fail` verdict with no wall signal
    is a genuine agent failure and returns None. A `pass` is never an env error.
    """
    if status == "pass":
        return None
    text = " ".join(t for t in (error, verifier_reason) if t)
    if harness_status == "error" and not any(p.search(text) for _, p in _ENV_ERROR_PATTERNS):
        # a crash we could not attribute is still environmental (the run never
        # produced a verdict) — bucket it as unreachable rather than penalize.
        return "site_unreachable"
    for label, pat in _ENV_ERROR_PATTERNS:
        if pat.search(text):
            return label
    return None


def contract_from_entry(e: dict) -> BrowserTaskContract:
    """Build the contract straight from the task file (same shape naive_baseline
    uses): success + forbidden conditions verbatim. An entry with no
    success_conditions is a legal open-ended task → the verifier reports an
    honest `unknown` and the second judge attaches an advisory score."""
    return BrowserTaskContract(
        task_id=e["task_id"],
        natural_language_task=e["natural_language_task"],
        expected_outcome=e.get("expected_outcome", "The task's success conditions hold"),
        success_conditions=[SuccessCondition(**c) for c in e.get("success_conditions", [])],
        forbidden_conditions=[ForbiddenCondition(**c) for c in e.get("forbidden_conditions", [])])


def _query_hint(task: str) -> str:
    """Cheap keyword hint for the offline MockPlanner (--mock only). Never used
    on the LLM path — the planner reads the whole task text there."""
    quoted = re.findall(r"['\"“」『]([^'\"”」』]{2,60})['\"”」』]", task)
    if quoted:
        return quoted[0]
    words = re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", task)
    return words[0] if words else task[:20]


def make_planner(mode: str, query_hint: str = "widget"):
    """Resolve the planner. gateway (default) preflights the Codex gateway and
    refuses with an actionable message if it is down; direct uses OPENAI_API_KEY;
    mock is the deterministic no-LLM planner (offline smoke / plumbing check)."""
    if mode == "mock":
        return MockPlanner(query_hint), "MockPlanner (deterministic, no LLM)"
    if mode == "direct":
        client = OpenAIClient()
        if not client.available():
            raise SystemExit("--direct needs OPENAI_API_KEY set.")
        return LLMPlanner(client), f"direct OpenAI model={client.model} base={client.base_url}"
    cfg = load_llm_config()
    import httpx
    try:
        r = httpx.get(f"{cfg.base_url.rstrip('/')}/models", timeout=5)
        ok, why = r.status_code == 200, f"HTTP {r.status_code}"
    except Exception as e:  # noqa: BLE001
        ok, why = False, f"{type(e).__name__}: {e}"
    if not ok:
        raise SystemExit(
            f"Codex gateway not reachable at {cfg.base_url} ({why}).\n"
            "Start it first (one-time: `codex login`):\n"
            "    python tools/codex_gateway.py --model gpt-5.3-codex\n"
            "Or run with --mock (offline) / --direct (OPENAI_API_KEY).")
    client = OpenAIClient(api_key=cfg.api_key, base_url=cfg.base_url, model=cfg.model)
    return LLMPlanner(client), f"Codex gateway model={cfg.model} base={cfg.base_url}"


def second_judge_live(page, contract: BrowserTaskContract, task_id: str,
                      extractor, run_dir: Path) -> dict:
    """Advisory second judgment of one FINISHED live task (P0-8), mirroring
    tools/browser_eval.second_judge_task but writing evidence into THIS run dir.
    The final snapshot is cached and the judge rules strictly from that cache;
    the per-condition diff runs against the primary verifier on the SAME
    snapshot. Never touches the verdict."""
    obs = PageObserver(page).observe()
    ev_path = run_dir / task_id / "second_judge_evidence.json"
    cache_evidence(obs.url, obs.visible_text, ev_path)
    ev = load_evidence(ev_path)
    record: dict = {"task_id": task_id, "evidence_sha256": ev["sha256"]}
    try:
        smoke_test(contract.success_conditions, ev)
    except SecondJudgeSmokeError as e:
        record["smoke_ok"] = False
        record["error"] = str(e)
        return record
    if not contract.success_conditions:
        oj = judge_open_ended(contract.natural_language_task,
                              contract.expected_outcome, ev, extractor)
        record["open_ended"] = {**oj["judgment"].as_dict(), "score": oj["score"]}
        return record
    result = judge_task(contract.success_conditions, ev, extractor)
    diff = diff_with_primary(result["judgments"], check_conditions(contract, obs))
    record.update({
        "aggregate": result["aggregate"],
        "disagreements": [d["condition"] for d in diff if d["agree"] is False],
        "llm_cost_usd": round(sum(j.cost_usd for j in result["judgments"]), 6),
    })
    return record


def execute_task(page, entry: dict, planner, budget: int,
                 evidence, run_dir: Path):
    """Drive ONE live task: goto the site, then BrowserAgent.run_agentic at the
    resolved step budget. Returns the TaskRun. Kept separate so tests can inject
    a fake TaskRun without a browser (the smoke-test seam)."""
    page.goto(entry["website"], wait_until="domcontentloaded")
    contract = contract_from_entry(entry)
    agent = BrowserAgent(page, MemoryStore(run_dir / "selector_memory.json"),
                         site="live", task_type="agentic",
                         artifact_dir=run_dir / entry["task_id"],
                         evidence_store=evidence,
                         downloads_dir=run_dir / entry["task_id"] / "downloads")
    return agent.run_agentic(entry["task_id"], contract, planner, max_steps=budget)


def build_row(run, entry: dict, budget: int, wall_s: float) -> dict:
    """Shape one eval row from a finished TaskRun (matches the m2w_rerun
    summary schema). env_error is filled in later by the summarizer once the
    harness status is known."""
    return {
        "task_id": entry["task_id"],
        "difficulty": entry.get("difficulty", ""),
        "website": entry.get("website", ""),
        "status": run.status,
        "verifier_reason": run.verifier.reason,
        "answer": run.answer,
        "steps_taken": len(run.steps),
        "step_budget": budget,
        "repairs": run.repairs,
        "confidence": round(run.confidence, 3),
        "llm_cost_usd": round(run.llm_cost_usd, 6),
        "llm_tokens": run.llm_tokens,
        "latency_ms": round(run.total_latency_ms, 1),
        "wall_s": round(wall_s, 1),
    }


def run_task(page, entry: dict, planner, run_dir: Path, evidence,
             extractor, max_steps: int | None) -> dict:
    """One task end to end: run the agent, build its row, attach the advisory
    second judge (if an extractor is armed). Raises on a real failure so the
    surrounding run_guarded records a harness error — the two axes stay
    separate (P0-9)."""
    budget = resolve_max_steps(entry, max_steps)
    t0 = time.monotonic()
    run = execute_task(page, entry, planner, budget, evidence, run_dir)
    row = build_row(run, entry, budget, time.monotonic() - t0)
    if extractor is not None:
        try:
            rec = second_judge_live(page, contract_from_entry(entry),
                                    entry["task_id"], extractor, run_dir)
        except Exception as e:  # noqa: BLE001 — advisory judge never fails the task
            rec = {"task_id": entry["task_id"], "error": f"{type(e).__name__}: {e}"}
        row["second_judge"] = {
            "verdict": rec.get("aggregate", {}).get("verdict"),
            "score": rec.get("aggregate", {}).get("score",
                                                  rec.get("open_ended", {}).get("score")),
            "disagreements": len(rec.get("disagreements", [])),
            "llm_cost_usd": rec.get("llm_cost_usd", rec.get("open_ended", {}).get("cost_usd", 0.0)),
        }
    return row


def _error_row(entry: dict, summary: dict) -> dict:
    """Harness-error stub — no verdict-layer fields (the axes stay separate)."""
    return {"task_id": entry["task_id"], "difficulty": entry.get("difficulty", ""),
            "website": entry.get("website", ""), "harness_status": "error",
            "harness_error": summary["error"]}


def summarize(rows: list[dict]) -> dict:
    """Success-rate rollup (P0-9 done rows only): overall + per difficulty, with
    env-error tasks excluded from the denominator and counted separately.

    success_rate = pass / (done tasks that are NOT an environmental block). A
    task the site blocked (captcha/login/unreachable) is not evidence the agent
    failed, so it does not drag the rate down — it is reported in env_errors.
    """
    def _bucket(subset: list[dict]) -> dict:
        done = [r for r in subset if r.get("harness_status", "done") == "done"]
        env = [r for r in done if r.get("env_error")]
        effective = [r for r in done if not r.get("env_error")]
        passes = sum(r["status"] == "pass" for r in effective)
        return {
            "tasks": len(subset),
            "done": len(done),
            "error": sum(r.get("harness_status") == "error" for r in subset),
            "pass": passes,
            "fail": sum(r["status"] == "fail" for r in effective),
            "unknown": sum(r["status"] == "unknown" for r in effective),
            "env_blocked": len(env),
            "success_rate": round(passes / len(effective), 3) if effective else None,
        }

    # attach env classification to every row (harness error stubs included)
    for r in rows:
        r["env_error"] = classify_env_error(
            r.get("harness_status", "done"), r.get("harness_error"),
            r.get("status"), r.get("verifier_reason"))

    difficulties = sorted({r.get("difficulty", "") for r in rows})
    env_counts: dict[str, int] = {}
    for r in rows:
        if r.get("env_error"):
            env_counts[r["env_error"]] = env_counts.get(r["env_error"], 0) + 1
    return {
        "overall": _bucket(rows),
        "per_difficulty": {d: _bucket([r for r in rows if r.get("difficulty", "") == d])
                           for d in difficulties},
        "env_errors": env_counts,
    }


def run_eval(entries: list[dict], planner, run_dir: Path, *, extractor,
             max_steps: int | None, resume: bool, headed: bool) -> dict:
    """Full run: guarded per-task execution over a single browser but a FRESH
    context+page PER TASK (a hard navigation failure in task N — e.g. an
    ERR_HTTP2 poisoned page cascading 'interrupted by another navigation' —
    must never bleed into task N+1), one summary.json per task, then the
    success-rate rollup. Returns the payload written to results.json."""
    from playwright.sync_api import sync_playwright

    task_ids = [e["task_id"] for e in entries]
    incomplete_prior = scan_incomplete(task_ids, out_root=run_dir)
    rows: list[dict] = []
    aborted = False
    n_error = n_attempted = 0
    evidence = EvidenceStore(run_dir / "evidence")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed)
        try:
            for entry in entries:
                if resume:
                    prior = load_done_summary(entry["task_id"], out_root=run_dir)
                    if prior:
                        row = prior["row"]
                        row["harness_status"] = "done"
                        row["resumed"] = True
                        rows.append(row)
                        continue
                if isinstance(planner, MockPlanner):
                    planner = MockPlanner(_query_hint(entry["natural_language_task"]))

                context = browser.new_context(viewport={"width": 1100, "height": 850},
                                              accept_downloads=True)
                page = context.new_page()
                arm_watchdog(page)
                try:
                    summary = run_guarded(
                        entry["task_id"],
                        lambda e=entry: run_task(page, e, planner, run_dir, evidence,
                                                 extractor, max_steps),
                        out_root=run_dir)
                finally:
                    try:
                        context.close()
                    except Exception:  # noqa: BLE001 — a dead context must not mask the row
                        pass
                n_attempted += 1
                if summary["harness_status"] == "done":
                    row = summary["row"]
                    row["harness_status"] = "done"
                else:
                    n_error += 1
                    row = _error_row(entry, summary)
                rows.append(row)
                if should_abort(n_error, n_attempted):
                    aborted = True
                    print(f"\n{HarnessAbort(rows, n_error, n_attempted)}")
                    break
        finally:
            browser.close()

    metrics = summarize(rows)
    harness = harness_report(rows, n_planned=len(entries), aborted=aborted)
    harness["incomplete_from_prior_run"] = incomplete_prior
    payload = {"metrics": metrics, "harness": harness,
               "judge_source": extractor.source if extractor is not None else None,
               "tasks": rows}
    (run_dir / "results.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload


def _print_summary(payload: dict, run_dir: Path) -> None:
    m = payload["metrics"]
    o = m["overall"]
    print("\nexternal live-task eval:")
    print(f"  overall: success_rate={o['success_rate']} "
          f"(pass={o['pass']} / effective={o['done'] - o['env_blocked']})  "
          f"done={o['done']} error={o['error']} env_blocked={o['env_blocked']}")
    for d, b in m["per_difficulty"].items():
        print(f"    {d or '(none)':<8} success_rate={b['success_rate']} "
              f"pass={b['pass']} fail={b['fail']} unknown={b['unknown']} "
              f"env_blocked={b['env_blocked']} done={b['done']}")
    if m["env_errors"]:
        print(f"  env_errors: {m['env_errors']}")
    h = payload["harness"]
    print(f"  harness: done={h['done']} error={h['error']} "
          f"not_run={h['not_run']} aborted={h['aborted']}")
    print(f"wrote {run_dir / 'results.json'}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tasks", type=Path, default=TASKS_DEFAULT)
    ap.add_argument("--out", type=Path, default=OUT_DEFAULT, help="run dir for summaries")
    ap.add_argument("--limit", type=int, default=0, help="run only the first N active tasks")
    ap.add_argument("--mock", action="store_true", help="deterministic MockPlanner, no LLM")
    ap.add_argument("--direct", action="store_true", help="OpenAI directly via OPENAI_API_KEY")
    ap.add_argument("--headed", action="store_true", help="show the browser window")
    ap.add_argument("--resume", action="store_true",
                    help="skip tasks whose summary.json in --out says a prior launch finished")
    ap.add_argument("--no-second-judge", action="store_true",
                    help="skip the advisory second judge (verdicts only)")
    ap.add_argument("--max-steps", type=int, default=None,
                    help="P1-15: override the per-task step budget (else difficulty tier)")
    ap.add_argument("--strict-repro", action="store_true",
                    help="P1-2: refuse to run on a dirty git tree (tracked changes)")
    args = ap.parse_args()
    if args.mock and args.direct:
        ap.error("--mock and --direct are mutually exclusive")
    if args.max_steps is not None and args.max_steps < 1:
        ap.error("--max-steps must be >= 1")

    run_dir = args.out
    run_dir.mkdir(parents=True, exist_ok=True)
    try:
        write_manifest(run_dir, task_set=args.tasks, strict=args.strict_repro)
    except DirtyTreeError as e:
        raise SystemExit(str(e)) from None

    spec = json.loads(args.tasks.read_text(encoding="utf-8"))
    # only active tasks count (stale/replaced are excluded per the README protocol)
    entries = [e for e in spec["tasks"] if e.get("status", "active") == "active"]
    if args.limit:
        entries = entries[:args.limit]
    if not entries:
        raise SystemExit("no active tasks to run")

    mode = "mock" if args.mock else "direct" if args.direct else "gateway"
    planner, desc = make_planner(mode)
    print(f"[planner] {desc}")

    extractor = None
    if not args.no_second_judge:
        client = OpenAIClient()
        extractor = LLMExtractor(client) if client.available() else OfflineExtractor()
        print(f"[second-judge] {extractor.source}")

    payload = run_eval(entries, planner, run_dir, extractor=extractor,
                       max_steps=args.max_steps, resume=args.resume, headed=args.headed)
    _print_summary(payload, run_dir)
    if payload["harness"]["aborted"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
