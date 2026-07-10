"""Agent Mode live runner — drive the browser agent with an LLM on any site.

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
from pathlib import Path

from playwright.sync_api import sync_playwright

from browser_core import BrowserTaskContract, SuccessCondition
from browser_agent.agent import BrowserAgent
from browser_agent.memory_store import MemoryStore
from browser_agent.planner import LLMPlanner, MockPlanner
from llm_core.openai_client import OpenAIClient
from observability_core import EvidenceStore

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs" / "agent_live"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=None, help="start URL (default: bundled mock site v2)")
    ap.add_argument("--task", default="Search MockShop for 'widget' and see the results")
    ap.add_argument("--success", action="append", default=[],
                    help="success condition 'type:value', e.g. text_visible:Widget (repeatable)")
    ap.add_argument("--mock", action="store_true", help="use the deterministic MockPlanner (no key)")
    ap.add_argument("--query", default="widget", help="query for MockPlanner")
    ap.add_argument("--headed", action="store_true", help="show the browser window")
    ap.add_argument("--max-steps", type=int, default=8)
    args = ap.parse_args()

    url = args.url or (ROOT / "data" / "mock_sites" / "v2" / "index.html").resolve().as_uri()
    conds = args.success or ["text_visible:results for", "text_visible:Widget"]
    contract = BrowserTaskContract(
        task_id="live", natural_language_task=args.task,
        expected_outcome="The task's success conditions are visibly satisfied",
        success_conditions=[SuccessCondition(type=c.split(":", 1)[0], value=c.split(":", 1)[1])
                            for c in conds],
    )

    if args.mock:
        planner = MockPlanner(args.query)
        print("[planner] MockPlanner (deterministic, no LLM)")
    else:
        client = OpenAIClient()
        if not client.available():
            raise SystemExit(
                "No OPENAI_API_KEY set. Set it (and OPENAI_BASE_URL for a gateway) or pass --mock.")
        planner = LLMPlanner(client)
        print(f"[planner] LLMPlanner model={client.model} base={client.base_url}")

    OUT.mkdir(parents=True, exist_ok=True)
    mem_path = OUT / "selector_memory.json"
    if mem_path.exists():
        mem_path.unlink()
    mem = MemoryStore(mem_path)
    evidence = EvidenceStore(OUT / "evidence")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed)
        page = browser.new_page(viewport={"width": 1100, "height": 850})
        page.goto(url, wait_until="domcontentloaded")
        agent = BrowserAgent(page, mem, site="live", task_type="agentic",
                             artifact_dir=OUT / "shots", evidence_store=evidence)
        run = agent.run_agentic("live", contract, planner, max_steps=args.max_steps)
        browser.close()

    print(f"\nSTATUS: {run.status.upper()}  confidence={run.confidence:.2f}  "
          f"latency={run.total_latency_ms:.0f}ms")
    print(f"verifier: {run.verifier.reason}")
    for s in run.steps:
        print(f"  [{s.mode}] {s.action} -> {'ok' if s.ok else 'FAIL'}  {s.detail[:70]}")
    (OUT / "run.json").write_text(json.dumps(run.as_dict(), indent=2), encoding="utf-8")
    print(f"\ntrace: {OUT / 'run.json'}  evidence: {OUT / 'evidence'}")


if __name__ == "__main__":
    main()
