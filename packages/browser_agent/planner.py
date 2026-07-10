"""LLM planner for Agent Mode (SPEC 6.2 F->I->J: Page Observer -> Planner ->
Action Selector).

The LLM never runs code and never invents selectors. It is shown the current
page's candidate elements (each with a stable data-aid) and must return ONE
controlled action as JSON, choosing a target only by aid. The result is
validated into a BrowserAction, screened by the capability guard, executed,
and the verifier — not the LLM — decides success. This is how Agent Mode adds
LLM generality for unknown sites without giving up the reliability spine.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Protocol

from browser_core import ElementTarget
from browser_core.actions import (
    ClickAction, DownloadAction, ExtractTextAction, FillAction, GotoAction, PressAction,
)
from browser_agent.observer import Observation
from llm_core.openai_client import LLMConfigError, LLMResponse, OpenAIClient

_SYSTEM = """You are the planner of a verified browser agent. Each turn you see the current page state (URL, title, visible text excerpt, candidate elements) and must return EXACTLY ONE JSON object choosing the next action. You never write code and never invent CSS selectors — you target an element ONLY by its numeric "aid" from the candidate list. An external verifier — not you — decides task success, so be truthful.

OUTPUT (one JSON object, nothing else):
  "action": "fill" | "click" | "press" | "goto" | "extract_text" | "download" | "done" | "give_up"
  "aid":    integer aid from the candidate list, or null (goto/done/give_up, and download, may omit it)
  "value":  fill text / key like "Enter" / goto URL / a URL to download; else ""
  "reason": one short sentence in the task's language

CHOOSING ELEMENTS
- Use ONLY listed aids. Each candidate shows tag, role, type, id and label — weigh ALL of them.
- Prefer semantically-right controls: a real submit (type=submit / role=button with a search/submit label) over a random clickable; an input/textarea/searchbox for typing.
- AVOID traps: ids/labels containing decoy/fake/ad/promo/sponsor, login/sign-in prompts, cookie-notice links.
- DISMISS OVERLAYS FIRST: any modal, popup, cookie/consent banner, newsletter, "unusual traffic" notice, or interstitial that covers the page must be closed before the task can proceed — click its close/×/dismiss/accept/agree/"no thanks"/"not now" control. A blocking popup is a step to clear, not a reason to stop.

PLAYBOOK
- Prefer going straight to the target site over a web search. If the task names a site or brand with an obvious domain (finlab -> finlab.tw, wikipedia -> en.wikipedia.org, a company's SEC 10-K -> sec.gov EDGAR), use "goto" with that URL instead of searching. Search engines often block automation with a CAPTCHA.
- If you DO land on a search-results page, click the most relevant organic result to leave it; don't keep searching.
- Search flows (when needed): fill the search box first, then click the submit control — or "press" Enter on the box if no reliable submit exists or a click had no effect.
- SITE-SEARCH SEMANTICS: type what the site indexes, not the kind of document you want. A company/registry/database search wants the ENTITY name or ticker (e.g. "Intel" or "INTC"), NOT a document-type label like "10-K risk factor" — stuffing the type into the free-text box returns nothing. Enter the entity to reach its page, then use the site's own filters/facets/links (a form-type filter, a document list, a section link) to narrow to the specific document or section.
- IF A SEARCH RETURNS NOTHING: do not give up — the query was likely wrong for this site. Re-read the results state, then either simplify the query to the bare entity name, switch to the site's filter/browse UI, or "goto" the entity's page directly.
- Downloads: three forms — (a) "download" with the aid of a download link/button; (b) "download" with aid=null and value=<a document URL you can see> to save that file directly; (c) "download" with aid=null and value="" to save the CURRENT page. A document that renders INLINE (e.g. an SEC .htm opened in the viewer) has NO download button — do NOT hunt for one and do NOT give up: just emit download with the file's URL, or download the current page. The file is saved and verified on disk.
- Navigation: "goto" with a URL you can see on the page, one given in the task, or an obvious well-known domain for a named site. Never invent a deep/guessed path — go to the site root and navigate from there.
- USE LINK HREFS: on a list/results/index page, candidates that are links show their href=. To reach a specific row (a filing, a document, an article), "goto" that row's href directly, or "click" that exact aid — do NOT go back to a search box. On EDGAR you land on the company's filing list: goto the newest 10-K's ...-index.htm href, then on that index page goto/click the primary document (the .htm), then "download" it.
- Reading: "extract_text" on the element that holds the answer when the task asks for information.

WHEN BLOCKED
- If a CAPTCHA / "unusual traffic" / "are you a robot" page appears, do NOT try to solve it. Prefer "goto" to reach the target site by URL directly, bypassing the search engine. Only if there is genuinely no way forward, "give_up" with the reason — this is honest and correct, not a failure of effort.

PROGRESS DISCIPLINE
- Check ACTIONS SO FAR before deciding: never repeat an action that already failed the same way — change strategy instead (different element, press instead of click, dismiss a modal).
- Modern sites are SPAs: the URL/content may have changed after your last action even without a full reload. Re-read the CURRENT state before acting.
- One action per turn; keep steps minimal — do not add exploratory clicks that don't serve the task.

HONESTY & BOUNDARIES
- "done" ONLY when the success conditions are actually satisfied in the current state (visible text / URL / a completed download) — not because you expect them to become true.
- Don't give up on the FIRST setback. A single failed action (empty search, a click with no effect, one blocked page) is not a dead end — change strategy: dismiss an overlay, simplify the query, use a filter/browse UI, or "goto" the target URL directly. Only after a genuinely different approach has also failed is give_up warranted.
- "give_up" honestly when every reasonable approach is exhausted — no candidate can advance the task, the page hard-requires login/CAPTCHA/payment with no bypass, or you are looping. Say why, and name what you already tried. This honest stop is correct; giving up prematurely (before trying an alternative) is not.
- Never enter credentials, personal or payment data; never buy, subscribe, or submit consequential forms. A capability guard will refuse these anyway — do not attempt them.
- Tasks may be in any language (中文/English); match your "reason" to it, and type fill values exactly as the task specifies."""


@dataclass
class PlannerDecision:
    kind: str                      # action | done | give_up
    action: object | None = None   # a BrowserAction when kind == action
    reason: str = ""
    llm: LLMResponse | None = None
    raw: dict = field(default_factory=dict)


class Planner(Protocol):
    def next_action(self, task: str, success_conditions: list[str],
                    obs: Observation, history: list[str]) -> PlannerDecision: ...


def _candidate_lines(obs: Observation) -> str:
    out = []
    for c in obs.candidates:
        if not c.visible:
            continue
        label = c.aria_label or c.placeholder or c.text or c.name or c.id
        line = (f'aid={c.index} <{c.tag}{" role="+c.role if c.role else ""}> '
                f'type={c.type or "-"} id="{c.id[:30]}" label="{label[:50]}"')
        # a link's href is the target: showing it lets the planner navigate a
        # list/results page deterministically (goto the exact filing/document)
        # instead of clicking blindly — crucial on link-dense pages like EDGAR.
        if c.tag == "a" and c.href and not c.href.startswith(("javascript:", "#")):
            line += f' href="{c.href[:80]}"'
        out.append(line)
    return "\n".join(out[:50]) or "(no visible interactive elements)"


def _build_action(decision: dict, obs: Observation):
    action = decision.get("action")
    aid = decision.get("aid")
    value = decision.get("value", "") or ""
    target = None
    if aid is not None:
        target = ElementTarget(selector=f'[data-aid="{aid}"]', selector_type="css",
                               description=f"aid {aid}")
    if action == "fill" and target:
        return FillAction(target=target, value=value)
    if action == "click" and target:
        return ClickAction(target=target)
    if action == "press" and target:
        return PressAction(target=target, key=value or "Enter")
    if action == "extract_text" and target:
        return ExtractTextAction(target=target)
    if action == "download":
        # download a URL (value), a clicked element (aid), or — with neither —
        # the CURRENT page. An inline-rendered document (SEC .htm) has no
        # download control, so this is how "save what I'm viewing" works.
        url = value if value.startswith(("http://", "https://")) else ""
        return DownloadAction(target=target, url=url)
    if action == "goto" and value:
        return GotoAction(url=value)
    return None


_PREFLIGHT_SYSTEM = """You plan the opening of a verified browser task. Given ONE natural-language task (any language), FIRST think it through like a dynamic workflow — what is the real goal, what obstacles are likely, what is the step-by-step route — THEN decide the best page to start on and the conditions that will prove success. All BEFORE any browsing. An external verifier checks the conditions literally, so make them observable and true only when the task is actually done.

Return EXACTLY ONE JSON object, nothing else:
  "analysis": one short sentence naming the concrete goal (what the user actually wants to reach/obtain), in the task's language.
  "obstacles": 1-3 short strings of anticipated difficulties for THIS task (e.g. "搜尋引擎可能出現 CAPTCHA","SEC 對自動化會回 403 封鎖頁,需用宣告 UA 下載","目標文件是 inline 開啟、沒有下載鈕"). Be specific to the task, not generic.
  "steps": 2-5 short imperative strings — the planned route from the start page to done (e.g. "goto EDGAR 依 ticker 列出 10-K","開最新一份的 index 再開主文件","download 目前頁面","確認含 Risk Factors"). These guide the agent; it still re-plans per live page.
  "start_url": a full https:// URL to open first. Go STRAIGHT to the target and land as DEEP as a URL you can construct reliably lets you, so the agent has the fewest hops left:
     - A US company's SEC filing: use the plain-HTML EDGAR browse endpoint keyed by the ticker, which lists that one company's filings of a type directly — https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=<TICKER>&type=10-K&dateb=&owner=include&count=10 (e.g. CIK=INTC&type=10-K). Do NOT use the efts.sec.gov full-text search SPA — it renders results via JavaScript and is unreliable to drive.
     - A named site/brand: its real domain (finlab -> https://finlab.tw, Wikipedia article -> https://en.wikipedia.org/wiki/<Topic>).
     - Only if the target is genuinely unknown, start at https://duckduckgo.com/html/ .
     Never invent a deep path you cannot know exists (a guessed accession number, a made-up article slug) — construct only URLs whose shape the site guarantees (a ticker-keyed EDGAR query, a domain root, a Wikipedia /wiki/Title).
  "success_conditions": 1-3 objects proving completion, each:
       {"type":"text_visible","value":"<short exact substring that appears on the page only when done>"}
       {"type":"url_contains","value":"<url fragment true only when done>"}
       {"type":"download_exists","value":"<distinctive text the SAVED FILE must contain, or \"\">"}
     download_exists is verified against the file's BYTES on disk, not its name: if the task says to download a document AND locate a section in it (e.g. "download the 10-K and find Risk Factors"), set value to that section's exact heading ("Risk Factors") so a wrong or blocked page saved to disk cannot count as success. Use "" only when any file is acceptable.
     Prefer a distinctive phrase in the language the target page will render (English site -> English phrase). Keep each value short and literal (a title, a heading, a ticker, a section name) — not a whole sentence, not vague words that appear everywhere.

Rules: pick conditions that are SUFFICIENT (met => task genuinely done) and NECESSARY (task done => met). If the task is a search/read, the condition is the answer text or a landmark of the destination page. If it downloads a document to inspect, prefer download_exists carrying the section/heading to confirm. Always return at least one condition — for an open-ended task ("find the most popular X"), use a landmark of the destination page (its title/section). Do not require login/CAPTCHA text. Never fabricate a value you don't expect to literally appear."""


class LLMPlanner:
    """Agent Mode planner backed by an OpenAI/Codex-compatible model."""

    def __init__(self, client: OpenAIClient | None = None) -> None:
        self.client = client or OpenAIClient()

    def available(self) -> bool:
        return self.client.available()

    def plan_preflight(self, task: str) -> tuple[str, list[str], dict]:
        """Ask the model, once, to think the task through (goal / obstacles /
        steps — a dynamic workflow) and pick a start URL plus verifiable success
        conditions. Returns (start_url, ["type:value"…], plan) where plan =
        {analysis, obstacles:[…], steps:[…]}. Raises LLMConfigError if the model
        is unavailable so the caller can fall back to heuristics. Every value is
        validated, never trusted blindly: a non-http start_url or an
        empty/oversized condition is dropped, plan strings are bounded."""
        user = (f"TASK: {task}\nThink it through, then return the JSON "
                "(analysis, obstacles, steps, start_url, success_conditions).")
        decision, _ = self.client.complete_json(_PREFLIGHT_SYSTEM, user)
        start = str(decision.get("start_url", "") or "").strip()
        if not start.lower().startswith(("http://", "https://")):
            start = ""
        conds: list[str] = []
        for c in decision.get("success_conditions", []) or []:
            if not isinstance(c, dict):
                continue
            t = str(c.get("type", "")).strip()
            v = str(c.get("value", "")).strip()
            if t not in ("text_visible", "url_contains", "download_exists"):
                continue
            if t != "download_exists" and not (0 < len(v) <= 120):
                continue
            conds.append(f"{t}:{v}")

        def _clean_list(key: str, cap: int) -> list[str]:
            out = []
            for s in decision.get(key, []) or []:
                s = str(s).strip()
                if s:
                    out.append(s[:160])
                if len(out) >= cap:
                    break
            return out
        plan = {"analysis": str(decision.get("analysis", "") or "").strip()[:200],
                "obstacles": _clean_list("obstacles", 3),
                "steps": _clean_list("steps", 5)}
        return start, conds[:3], plan

    def next_action(self, task: str, success_conditions: list[str],
                    obs: Observation, history: list[str]) -> PlannerDecision:
        user = (
            f"TASK: {task}\n"
            f"SUCCESS WHEN: {'; '.join(success_conditions)}\n"
            f"CURRENT URL: {obs.url}\nTITLE: {obs.title}\n"
            f"VISIBLE TEXT (excerpt): {obs.visible_text[:1600]}\n"
            f"CANDIDATE ELEMENTS:\n{_candidate_lines(obs)}\n"
            f"ACTIONS SO FAR: {', '.join(history[-6:]) or '(none)'}\n"
            "Return the next single action as JSON."
        )
        try:
            decision, rec = self.client.complete_json(_SYSTEM, user)
        except LLMConfigError:
            raise
        kind = decision.get("action", "give_up")
        if kind in ("done", "give_up"):
            return PlannerDecision(kind=kind, reason=decision.get("reason", ""), llm=rec, raw=decision)
        act = _build_action(decision, obs)
        if act is None:
            # recoverable: the model emitted a malformed action (e.g. click with
            # no aid). Signal a noop so the loop re-plans rather than ending.
            return PlannerDecision(kind="noop", reason="model returned an unusable action; re-planning",
                                   llm=rec, raw=decision)
        return PlannerDecision(kind="action", action=act, reason=decision.get("reason", ""),
                               llm=rec, raw=decision)


class MockPlanner:
    """Deterministic planner for offline tests/demos (no key). Emulates a
    reasonable model: fill the search box, submit, then declare done."""

    def __init__(self, query: str) -> None:
        self.query = query
        self._step = 0

    def available(self) -> bool:
        return True

    def _find(self, obs: Observation, kinds, words):
        # only elements whose tag/role matches the kind; among those, prefer a
        # word match (so the submit step never grabs the search input just
        # because its label contains "search").
        pool = []
        for c in obs.candidates:
            if not c.visible:
                continue
            blob = f"{c.aria_label} {c.placeholder} {c.name} {c.text} {c.id}".lower()
            if "decoy" in blob or "fake" in blob:
                continue
            if c.tag in kinds or c.role in kinds:
                pool.append((c, blob))
        if not pool:
            return None
        for c, blob in pool:
            if any(w in blob for w in words):
                return c
        return pool[0][0]

    def next_action(self, task: str, success_conditions: list[str],
                    obs: Observation, history: list[str]) -> PlannerDecision:
        self._step += 1
        if self._step == 1:
            box = self._find(obs, {"input", "textarea", "searchbox", "textbox"},
                             {"search", "query", "find"})
            if box:
                t = ElementTarget(selector=box.aid_selector(), selector_type="css")
                return PlannerDecision(kind="action", action=FillAction(target=t, value=self.query),
                                       reason="fill the search box")
        if self._step == 2:
            btn = self._find(obs, {"button"}, {"search", "submit", "go", "find"})
            if btn:
                t = ElementTarget(selector=btn.aid_selector(), selector_type="css")
                return PlannerDecision(kind="action", action=ClickAction(target=t),
                                       reason="click submit")
        return PlannerDecision(kind="done", reason="results should be visible")
