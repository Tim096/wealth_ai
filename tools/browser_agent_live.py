r"""Agent Mode live runner — drive the browser agent with an LLM on any site.

MANUAL TEST (you supply your own credentials — this tool never stores a key):

  # 1) OpenAI API key:
  set OPENAI_API_KEY=sk-...
  set OPENAI_MODEL=gpt-5-codex-mini          # or gpt-5.3-codex on Plus
  .venv\Scripts\python tools\browser_agent_live.py --headed ^
     --url "https://en.wikipedia.org/wiki/Main_Page" ^
     --task "Search Wikipedia for 'Reliability engineering' and open the article" ^
     --success "text_visible:Reliability engineering"

  # 2) Codex via a gateway (OAuth token can't hit api.openai.com directly):
  set OPENAI_BASE_URL=http://localhost:18789/v1   # your OpenClaw/proxy gateway
  set OPENAI_API_KEY=<gateway-token>
  ...

  # 3) No key — deterministic mock planner against the bundled mock site:
  .venv\Scripts\python tools\browser_agent_live.py --mock --query widget

Every action is capability-screened and the verifier (not the LLM) decides
pass/fail/unknown. A full trace + EvidenceRecords are written under runs/.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

from browser_core import BrowserTaskContract, SuccessCondition
from browser_agent.agent import BrowserAgent
from browser_agent.memory_store import MemoryStore
from browser_agent.planner import LLMPlanner, MockPlanner
from llm_core.config import load_llm_config
from llm_core.openai_client import OpenAIClient
from observability_core import EvidenceStore

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs" / "agent_live"


def _preflight_gateway(base_url: str) -> tuple[bool, str]:
    import httpx
    try:
        r = httpx.get(f"{base_url.rstrip('/')}/models", timeout=5)
        return (r.status_code == 200, f"HTTP {r.status_code}")
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


_STOP = {"the", "a", "an", "for", "to", "and", "of", "in", "on", "open", "search",
         "find", "go", "click", "read", "article", "page", "this", "that", "with"}


def derive_success(task: str) -> list[str]:
    """Turn a natural-language task into a verifier condition when the user
    didn't give one: prefer a quoted phrase, else the most salient long word."""
    q = re.findall(r"['\"]([^'\"]{2,60})['\"]", task)
    if q:
        return [f"text_visible:{q[0]}"]
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z0-9\-]{3,}", task) if w.lower() not in _STOP]
    words.sort(key=len, reverse=True)
    return [f"text_visible:{words[0]}"] if words else ["url_contains:."]


def make_planner(args):
    if args.mock:
        print("[planner] MockPlanner (deterministic, no LLM)")
        return MockPlanner(args.query)
    if args.direct:
        client = OpenAIClient()
        if not client.available():
            raise SystemExit("--direct needs OPENAI_API_KEY set.")
        print(f"[planner] direct OpenAI model={client.model} base={client.base_url}")
        return LLMPlanner(client)
    cfg = load_llm_config()
    ok, why = _preflight_gateway(cfg.base_url)
    if not ok:
        raise SystemExit(
            f"Codex gateway not reachable at {cfg.base_url} ({why}).\n"
            "Start it first (one-time: `codex login`):\n"
            "    python tools/codex_gateway.py --model gpt-5.3-codex\n"
            "Or verify the whole path with no codex:\n"
            "    python tools/codex_gateway.py --backend mock\n"
            "Guide: docs/setup_codex_gateway.md.  Or run with --mock / --direct.")
    print(f"[planner] Codex gateway model={cfg.model} base={cfg.base_url}")
    return LLMPlanner(OpenAIClient(api_key=cfg.api_key, base_url=cfg.base_url, model=cfg.model))


def run_task(page, args, task: str, url: str | None, conds: list[str]):
    if url:
        page.goto(url, wait_until="domcontentloaded")
    contract = BrowserTaskContract(
        task_id="live", natural_language_task=task,
        expected_outcome="The task's success conditions are visibly satisfied",
        success_conditions=[SuccessCondition(type=c.split(":", 1)[0], value=c.split(":", 1)[1])
                            for c in conds])
    mem = MemoryStore(OUT / "selector_memory.json")
    agent = BrowserAgent(page, mem, site="live", task_type="agentic",
                         artifact_dir=OUT / "shots", evidence_store=EvidenceStore(OUT / "evidence"))
    # reset step state for the deterministic mock; LLM planner is stateless per call
    if isinstance(args._planner, MockPlanner):
        args._planner = MockPlanner(args.query)
    run = agent.run_agentic("live", contract, args._planner, max_steps=args.max_steps)
    print(f"\nSTATUS: {run.status.upper()}  confidence={run.confidence:.2f}  "
          f"latency={run.total_latency_ms:.0f}ms")
    print(f"verifier: {run.verifier.reason}")
    for s in run.steps:
        print(f"  [{s.mode}] {s.action} -> {'ok' if s.ok else 'FAIL'}  {s.detail[:70]}")
    (OUT / "run.json").write_text(json.dumps(run.as_dict(), indent=2), encoding="utf-8")
    print(f"trace: {OUT / 'run.json'}")
    return run


def interactive_loop(page, args):
    print("\n=== Agent Mode · 互動模式 ===")
    print("直接用自然語言輸入任務。留空 URL 沿用目前頁面。輸入 'quit' 離開。\n")
    last_url = args.url
    while True:
        try:
            task = input("任務 (自然語言) > ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not task or task.lower() in ("quit", "exit", "q"):
            break
        url = input(f"起始 URL [{last_url or '目前頁面'}] > ").strip() or last_url
        last_url = url
        succ = input("成功條件 (看到什麼文字算成功,可留空自動推斷) > ").strip()
        conds = [f"text_visible:{succ}"] if succ else derive_success(task)
        print(f"[success] {conds}")
        run_task(page, args, task, url, conds)
        print()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=None, help="start URL (interactive: initial page)")
    ap.add_argument("--task", default=None, help="one-shot task (omit for interactive mode)")
    ap.add_argument("--success", action="append", default=[],
                    help="success 'type:value', e.g. text_visible:Widget (repeatable)")
    ap.add_argument("-i", "--interactive", action="store_true", help="type tasks in natural language")
    ap.add_argument("--mock", action="store_true", help="deterministic MockPlanner, no LLM")
    ap.add_argument("--direct", action="store_true", help="OpenAI directly via OPENAI_API_KEY")
    ap.add_argument("--query", default="widget", help="query for MockPlanner")
    ap.add_argument("--headed", action="store_true", help="show the browser window")
    ap.add_argument("--max-steps", type=int, default=8)
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    mp = OUT / "selector_memory.json"
    if mp.exists():
        mp.unlink()
    args._planner = make_planner(args)

    # interactive when asked, or when no one-shot task was given
    interactive = args.interactive or (args.task is None and not args.mock)
    headed = args.headed or interactive  # watch it in interactive mode

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed)
        page = browser.new_page(viewport={"width": 1100, "height": 850})
        if interactive:
            interactive_loop(page, args)
        else:
            task = args.task or "Search MockShop for 'widget' and see the results"
            url = args.url or (ROOT / "data" / "mock_sites" / "v2" / "index.html").resolve().as_uri()
            conds = args.success or derive_success(task)
            run_task(page, args, task, url, conds)
        browser.close()
    print(f"\nevidence: {OUT / 'evidence'}   shots: {OUT / 'shots'}")


if __name__ == "__main__":
    main()
