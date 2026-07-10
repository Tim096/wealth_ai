"""Browser Agent killer demo (SPEC 15): prove self-correction + self-maintenance.

1. Run a search task on mock site v1 (Script Mode, known selectors) -> pass.
2. Switch to mock site v2 (id removed, button->icon, cookie modal, decoy
   button, lazy render) -> the remembered selectors fail.
3. Agent detects selector_not_found / modal_blocking, searches the
   accessibility tree, avoids the decoy, repairs, small-step verifies.
4. Verifier confirms real results; selector memory is updated.
5. Emit the full evidence trace (JSON) + screenshots.

Runs fully offline against local static HTML. No network, no LLM required.
"""

from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from browser_core import BrowserTaskContract, ForbiddenCondition, SuccessCondition
from browser_agent.agent import BrowserAgent, Step
from browser_agent.memory_store import MemoryStore
from observability_core import EvidenceStore

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "runs" / "browser_demo"
EVIDENCE = ROOT / "data" / "browser_eval" / "evidence"


def site_uri(version: str) -> str:
    return (ROOT / "data" / "mock_sites" / version / "index.html").resolve().as_uri()


def search_task(site: str):
    steps = [
        Step(purpose="search_box", kind="fill", value="widget", fallback_selector="#search-box"),
        Step(purpose="submit_button", kind="click", fallback_selector="#search-btn"),
    ]
    contract = BrowserTaskContract(
        task_id=f"search-{site}",
        natural_language_task="Search MockShop for 'widget' and see the results",
        expected_outcome="A results list containing widget products is shown",
        success_conditions=[
            SuccessCondition(type="text_visible", value="results for"),
            SuccessCondition(type="text_visible", value="Widget"),
        ],
        forbidden_conditions=[
            ForbiddenCondition(type="error_text_visible", value="no results"),
            ForbiddenCondition(type="captcha_visible", value="captcha"),
        ],
    )
    return steps, contract


def main() -> None:
    ART.mkdir(parents=True, exist_ok=True)
    mem = MemoryStore(ART / "selector_memory.json")
    evidence = EvidenceStore(EVIDENCE)
    runs = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1000, "height": 800})

        # --- v1: learn the selectors (Script Mode) ---
        page.goto(site_uri("v1"))
        agent = BrowserAgent(page, mem, site="mockshop", task_type="search",
                             artifact_dir=ART / "v1", evidence_store=evidence)
        steps, contract = search_task("v1")
        r1 = agent.run("search-v1", steps, contract)
        runs.append(("v1 (baseline, script mode)", r1))

        # --- v2: UI drifted; remembered selectors fail -> repair ---
        page.goto(site_uri("v2"))
        agent2 = BrowserAgent(page, mem, site="mockshop", task_type="search",
                              artifact_dir=ART / "v2", evidence_store=evidence)
        steps2, contract2 = search_task("v2")
        r2 = agent2.run("search-v2", steps2, contract2)
        runs.append(("v2 (UI drift, repair mode)", r2))

        browser.close()

    out = {"runs": [{"label": label, **run.as_dict()} for label, run in runs]}
    (ART / "trace.json").write_text(json.dumps(out, indent=2), encoding="utf-8")

    for label, run in runs:
        print(f"\n=== {label} ===")
        print(f"status: {run.status.upper()}  repairs: {run.repairs}  "
              f"latency: {run.total_latency_ms:.0f}ms")
        print(f"verifier: {run.verifier.reason}")
        for s in run.steps:
            line = f"  [{s.mode}] {s.step}.{s.action} -> {'ok' if s.ok else 'FAIL'}"
            if s.diagnosis:
                line += f"  diagnosed={s.diagnosis}"
            if s.repair_chosen:
                line += f"  repaired_to={s.repair_chosen}"
            print(line)
    print(f"\ntrace: {ART / 'trace.json'}")
    print(f"selector memory: {ART / 'selector_memory.json'}")


if __name__ == "__main__":
    main()
