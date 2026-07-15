"""In-process browser fakes: drive run_agentic without Playwright.

Every existing test that drives the agent loop is marked `integration` because
it needs a real browser, so the loop's own wiring (does a failure reach the
repair cascade? does the verdict cap correctly?) was only ever covered by tests
the default `-m "not integration"` run deselects. These fakes give the loop a
page/observer/executor triple with no browser, so that wiring is checked on
every run.

They fake the BOUNDARY (page, observation, action outcome) and nothing else:
the agent, verifier, repair cascade and selector memory under test are the real
ones.
"""

from __future__ import annotations

from pathlib import Path

from browser_agent.agent import BrowserAgent
from browser_agent.executor import ActionOutcome
from browser_agent.memory_store import MemoryStore
from browser_agent.observer import ElementCandidate, Observation
from browser_agent.replay_cache import ReplayCache


def candidate(**kw) -> ElementCandidate:
    """An ElementCandidate with sane defaults; override only what matters."""
    base = dict(index=0, tag="a", type="", id="", name="", role="", aria_label="",
                placeholder="", text="", href="", visible=True, x=0, y=0,
                checked="", form="", classes="", parent_path="")
    base.update(kw)
    return ElementCandidate(**base)


class FakePage:
    """The handful of page methods run_agentic actually touches."""

    def __init__(self, url: str = "https://example.com/") -> None:
        self.url = url
        self.evaluate_calls = 0

    def evaluate(self, js, arg=None):
        # {} satisfies both callers: no blocking overlay (_dismiss_overlay) and
        # no element fields (_element_hashes -> ('', '')).
        self.evaluate_calls += 1
        return {}

    def wait_for_timeout(self, ms):
        return None

    def wait_for_load_state(self, state, timeout=None):
        return None

    def content(self):
        return "<html><body>fake</body></html>"

    def inner_text(self, selector):
        return ""


class FakeObserver:
    """Returns the same scripted observation every turn."""

    def __init__(self, page, candidates, visible_text="", title="t") -> None:
        self.page = page
        self.candidates = list(candidates)
        self.visible_text = visible_text
        self.title = title
        self.observations = 0

    def observe(self) -> Observation:
        self.observations += 1
        return Observation(url=self.page.url, title=self.title,
                           visible_text=self.visible_text,
                           candidates=list(self.candidates))


class FakeExecutor:
    """Succeeds on `ok_selectors`, fails everything else with a
    selector-not-found outcome (matched_count=0) — the shape diagnose_failure
    classifies as `selector_not_found`, i.e. the repairable case.

    ok_selectors=None means every action succeeds.
    """

    def __init__(self, page, ok_selectors=None, extract_text="") -> None:
        self.page = page
        self.ok_selectors = None if ok_selectors is None else set(ok_selectors)
        self.extract_text = extract_text
        self.last_download_path = ""
        self.calls: list[tuple[str, str]] = []

    def _ok(self, selector: str) -> bool:
        return True if self.ok_selectors is None else selector in self.ok_selectors

    def selectors_tried(self) -> list[str]:
        return [sel for _, sel in self.calls]

    def execute(self, action) -> ActionOutcome:
        selector = getattr(getattr(action, "target", None), "selector", "") or ""
        self.calls.append((action.type, selector))
        ok = self._ok(selector)
        return ActionOutcome(
            ok=ok,
            action_type=action.type,
            matched_count=1 if ok else 0,
            error="" if ok else "no element matched the selector",
            detail="acted" if ok else "",
            latency_ms=1.0,
            extracted_text=(self.extract_text
                            if ok and action.type == "extract_text" else ""),
        )


def fake_agent(tmp_path: Path, site: str = "example.com", task_type: str = "agentic",
               url: str = "https://example.com/", candidates=(), visible_text: str = "",
               extract_text: str = "", ok_selectors=None,
               memory: MemoryStore | None = None) -> BrowserAgent:
    """A real BrowserAgent wired to fake page/observer/executor."""
    page = FakePage(url)
    agent = BrowserAgent(
        page, memory or MemoryStore(tmp_path / "memory.json"), site, task_type,
        replay_cache=ReplayCache(tmp_path / "replay_cache.json"))
    agent.executor = FakeExecutor(page, ok_selectors, extract_text)
    agent.observer = FakeObserver(page, candidates, visible_text)
    return agent
