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

    def _download(self, action, url_before: str) -> ActionOutcome:
        """Save the target file. Three ways, in priority order: an explicit URL
        (action.url), a clickable element (action.target), or — with neither —
        the CURRENT page. Each element/URL path itself falls back to fetching
        bytes over the session and finally to saving the rendered document, so
        an inline-rendered SEC .htm (no download control) never dead-ends."""
        import os as _os
        from urllib.parse import urljoin as _urljoin

        def _dest(name: str) -> str:
            name = name.split("?")[0].rstrip("/").split("/")[-1] or "download.bin"
            return _os.path.join(str(self.downloads_dir), name) if self.downloads_dir else name

        # A short body carrying this signature is SEC's automation block page,
        # not the document — a naked page.request.get() sends no declared UA and
        # gets rejected even when the browser loaded the real file fine. Treat it
        # as a miss so we fall back to the browser-rendered content.
        def _is_block_page(body: bytes) -> bool:
            head = body[:4000].lower()
            return (b"undeclared automated" in head or b"request originates" in head
                    or (len(body) < 2048 and b"automated tool" in head))

        def _save_bytes(body: bytes, u: str, note: str) -> ActionOutcome:
            last = u.split("/")[-1]
            dest = _dest(u if "." in last else u.rstrip("/") + "/download.htm")
            with open(dest, "wb") as fh:
                fh.write(body)
            self.last_download_path = dest
            return ActionOutcome(ok=True, action_type="download", detail=f"{dest} ({note})",
                                 extracted_text=dest, url_before=url_before, url_after=self.page.url)

        def _save_content(u: str, note: str) -> ActionOutcome:
            """Save the document the BROWSER actually rendered (correct UA,
            cookies, JS) — the reliable source for a UA-gated site like SEC."""
            if u.endswith((".htm", ".html", ".txt", ".xml")):
                name = u
            else:
                import re as _re
                slug = _re.sub(r"[^A-Za-z0-9._-]+", "-", (self.page.title() or "").strip())[:60]
                name = f"{slug.strip('-') or 'page'}.html"
            dest = _dest(name)
            with open(dest, "w", encoding="utf-8") as fh:
                fh.write(self.page.content())
            self.last_download_path = dest
            return ActionOutcome(ok=True, action_type="download", detail=f"{dest} ({note})",
                                 extracted_text=dest, url_before=url_before, url_after=self.page.url)

        def _httpx_save(u: str, note: str) -> ActionOutcome | None:
            """Fetch bytes over a plain HTTP client with a proper User-Agent.
            Some hosts (SEC EDGAR) 403 Chromium's header/TLS fingerprint no
            matter the UA string, yet serve a declared client fine — so this is
            the reliable path when the browser is blocked. A declared contact UA
            is used for sec.gov (its documented requirement), a normal browser UA
            elsewhere."""
            import os as _os2
            from urllib.parse import urlsplit as _urlsplit
            host = (_urlsplit(u).hostname or "").lower()
            ua = _os2.environ.get("SEC_EDGAR_USER_AGENT", "") if host.endswith("sec.gov") else ""
            ua = ua or ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
            try:
                import httpx
                resp = httpx.get(u, headers={"User-Agent": ua}, timeout=30, follow_redirects=True)
            except Exception:  # noqa: BLE001
                return None
            if resp.status_code != 200 or _is_block_page(resp.content):
                return None
            return _save_bytes(resp.content, u, note + ", via http")

        def _save_url(u: str, note: str) -> ActionOutcome | None:
            """Fetch a DIFFERENT url's bytes. Try the browser session first (it
            carries cookies), then a declared HTTP client (bypasses fingerprint
            blocks), then a browser navigation — so a UA-gated document still
            downloads instead of a block page."""
            if not u.startswith(("http://", "https://")):
                return None
            try:
                resp = self.page.request.get(u)
                body = resp.body()
            except Exception:  # noqa: BLE001
                body = b""
            if body and resp.ok and not _is_block_page(body):
                return _save_bytes(body, u, note)
            viahttp = _httpx_save(u, note)
            if viahttp is not None:
                return viahttp
            try:                              # last resort: let the browser render it
                self.page.goto(u, wait_until="domcontentloaded", timeout=self.timeout * 3)
                if not _is_block_page(self.page.content().encode("utf-8", "replace")):
                    return _save_content(u, note + ", via browser")
            except Exception:  # noqa: BLE001
                pass
            return None

        def _save_current() -> ActionOutcome:
            try:
                self.page.wait_for_load_state("domcontentloaded", timeout=self.timeout)
            except Exception:  # noqa: BLE001
                pass
            # the current page is already loaded in the browser — normally just
            # save its rendered content. But if the browser is itself showing a
            # block page (SEC 403s Chromium), re-fetch the real bytes over the
            # declared HTTP client so we save the document, not the block notice.
            rendered = self.page.content()
            if _is_block_page(rendered.encode("utf-8", "replace")):
                r = _httpx_save(self.page.url, "refetched blocked document")
                if r is not None:
                    return r
            return _save_content(self.page.url, "saved rendered page")

        # 1) explicit URL to save — best for an inline document the model can see
        if getattr(action, "url", ""):
            r = _save_url(action.url, "fetched target url")
            if r is not None:
                return r

        # 2) a clickable element: real download event, else its href, else current
        if action.target is not None and self._count(action.target) > 0:
            loc = _locator(self.page, action.target).first
            href = None
            try:
                href = loc.get_attribute("href")
            except Exception:  # noqa: BLE001
                pass
            try:
                with self.page.expect_download(timeout=3000) as di:
                    loc.click()
                dl = di.value
                dest = _dest(dl.suggested_filename or "download.bin")
                dl.save_as(dest)
                self.last_download_path = dest
                return ActionOutcome(ok=True, action_type="download", detail=dest,
                                     extracted_text=dest, url_before=url_before, url_after=self.page.url)
            except Exception:  # noqa: BLE001 — no download event; try the href, then current page
                pass
            if href:
                r = _save_url(_urljoin(self.page.url, href), "fetched linked document")
                if r is not None:
                    return r

        # 3) no URL, no usable element → save the document currently on screen
        return _save_current()

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

        if at == "download":
            return self._download(action, url_before)

        if at in ("click", "fill", "press", "select", "extract_text"):
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
                return self._download(loc, n, url_before)
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
