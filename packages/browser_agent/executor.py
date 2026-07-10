"""Action executor (SPEC 6.5): executes a controlled BrowserAction against a
Playwright page. The LLM never runs code — it emits an action object, this
resolves it to a locator and runs it, returning a structured outcome (never
raising into the agent loop).
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from browser_core import ElementTarget


@dataclass
class ActionOutcome:
    ok: bool
    action_type: str
    detail: str = ""
    error: str = ""
    matched_count: int = 0
    latency_ms: float = 0.0
    extracted_text: str = ""
    url_before: str = ""
    url_after: str = ""


def _locator(page, target: ElementTarget):
    st = target.selector_type
    if st == "css":
        return page.locator(target.selector)
    if st == "xpath":
        return page.locator(f"xpath={target.selector}")
    if st == "text":
        return page.get_by_text(target.selector, exact=False)
    if st == "role":
        # selector encodes "role=name", e.g. "button=Search"
        if "=" in target.selector:
            role, name = target.selector.split("=", 1)
            return page.get_by_role(role.strip(), name=name.strip())
        return page.get_by_role(target.selector.strip())
    if st == "semantic":
        # semantic targets are resolved by repair into a concrete css selector
        return page.locator(target.selector)
    return page.locator(target.selector)


class ActionExecutor:
    def __init__(self, page, default_timeout_ms: int = 5000, downloads_dir=None) -> None:
        self.page = page
        self.timeout = default_timeout_ms
        self.downloads_dir = downloads_dir
        self.last_download_path = ""

    def execute(self, action) -> ActionOutcome:
        t0 = time.perf_counter()
        url_before = self.page.url
        try:
            outcome = self._dispatch(action, url_before)
        except Exception as e:  # noqa: BLE001 — surfaced as a structured outcome, not raised
            outcome = ActionOutcome(
                ok=False, action_type=getattr(action, "type", "?"),
                error=f"{type(e).__name__}: {str(e)[:200]}", url_before=url_before,
                url_after=self.page.url,
            )
        outcome.latency_ms = (time.perf_counter() - t0) * 1000
        return outcome

    def _count(self, target: ElementTarget) -> int:
        try:
            return _locator(self.page, target).count()
        except Exception:
            return 0

    def _dispatch(self, action, url_before: str) -> ActionOutcome:
        at = action.type
        if at == "goto":
            self.page.goto(action.url, wait_until="domcontentloaded", timeout=self.timeout * 3)
            return ActionOutcome(ok=True, action_type=at, url_before=url_before,
                                 url_after=self.page.url, detail=f"navigated to {action.url}")

        if at in ("click", "fill", "press", "select", "extract_text", "download"):
            n = self._count(action.target)
            if n == 0:
                return ActionOutcome(ok=False, action_type=at, matched_count=0,
                                     error="selector matched no element",
                                     url_before=url_before, url_after=self.page.url)
            loc = _locator(self.page, action.target).first
            if at == "click":
                loc.click(timeout=self.timeout)
            elif at == "fill":
                loc.fill(action.value, timeout=self.timeout)
            elif at == "press":
                loc.press(action.key, timeout=self.timeout)
            elif at == "select":
                loc.select_option(action.value, timeout=self.timeout)
            elif at == "extract_text":
                txt = loc.inner_text(timeout=self.timeout)
                return ActionOutcome(ok=True, action_type=at, matched_count=n,
                                     extracted_text=txt, url_before=url_before,
                                     url_after=self.page.url)
            elif at == "download":
                import os as _os
                with self.page.expect_download(timeout=self.timeout * 2) as di:
                    loc.click()
                dl = di.value
                name = dl.suggested_filename or "download.bin"
                dest = _os.path.join(str(self.downloads_dir), name) if self.downloads_dir else None
                if dest:
                    dl.save_as(dest)
                    self.last_download_path = dest
                return ActionOutcome(ok=True, action_type=at, matched_count=n,
                                     detail=dest or name, extracted_text=dest or name,
                                     url_before=url_before, url_after=self.page.url)
            return ActionOutcome(ok=True, action_type=at, matched_count=n,
                                 url_before=url_before, url_after=self.page.url)

        if at == "wait_for":
            c = action.condition
            try:
                if c.kind == "url_contains":
                    self.page.wait_for_url(f"**{c.value}**", timeout=c.timeout_ms)
                elif c.kind == "text_visible":
                    self.page.get_by_text(c.value, exact=False).first.wait_for(timeout=c.timeout_ms)
                elif c.kind == "selector_visible":
                    self.page.locator(c.value).first.wait_for(timeout=c.timeout_ms)
                elif c.kind == "network_idle":
                    self.page.wait_for_load_state("networkidle", timeout=c.timeout_ms)
                return ActionOutcome(ok=True, action_type=at, detail=f"{c.kind}:{c.value}",
                                     url_before=url_before, url_after=self.page.url)
            except Exception as e:  # noqa: BLE001
                return ActionOutcome(ok=False, action_type=at, error=f"timeout: {c.kind}:{c.value}",
                                     url_before=url_before, url_after=self.page.url)

        if at == "scroll":
            self.page.mouse.wheel(0, action.amount if action.direction == "down" else -action.amount)
            return ActionOutcome(ok=True, action_type=at, url_before=url_before, url_after=self.page.url)
        if at == "back":
            self.page.go_back()
            return ActionOutcome(ok=True, action_type=at, url_before=url_before, url_after=self.page.url)
        if at == "snapshot":
            return ActionOutcome(ok=True, action_type=at, url_before=url_before, url_after=self.page.url)

        return ActionOutcome(ok=False, action_type=at, error=f"unknown action {at}")
