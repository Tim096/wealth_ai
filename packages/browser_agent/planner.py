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
    ClickAction, DownloadAction, ExtractTextAction, FillAction, GotoAction,
    KeyboardAction, MouseAction, PressAction,
)
from browser_agent.observer import Observation
from llm_core.openai_client import LLMConfigError, LLMResponse, OpenAIClient

_SYSTEM = """You are the planner of a verified browser agent. Each turn you see the current page state (URL, title, visible text excerpt, candidate elements) and must return EXACTLY ONE JSON object choosing the next action. You never write code and never invent CSS selectors — you target an element ONLY by its numeric "aid" from the candidate list. An external verifier — not you — decides task success, so be truthful.

OUTPUT (one JSON object, nothing else):
  "action": "fill" | "click" | "press" | "goto" | "extract_text" | "download" | "mouse" | "keyboard" | "done" | "give_up"
  "aid":    integer aid from the candidate list, or null (goto/done/give_up/mouse/keyboard, and download, may omit it)
  "value":  fill text / key like "Enter" / goto URL / a URL to download / text to type for keyboard; else ""
  "x","y":  integers — required ONLY for "mouse" (the click coordinate, taken from a candidate's at=(x,y))
  "keys":   for "keyboard" only — a key/chord to press ("Enter","Tab","Escape","Control+A") instead of typing value
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
- CHOICE QUESTIONS (radio / checkbox / a Google Form's multiple-choice options): these are NOT text inputs — you cannot "fill" them. Each option is its own candidate with role=radio/checkbox and the option text as its label; "click" the option whose label matches the intended answer. A candidate showing checked=true is ALREADY selected — do NOT click it again (that unselects it). On a form, fill every text field AND select every required choice FIRST, and only submit once nothing required is left unanswered.
- SITE-SEARCH SEMANTICS: type what the site indexes, not the kind of document you want. A company/registry/database search wants the ENTITY name or ticker (e.g. "Intel" or "INTC"), NOT a document-type label like "10-K risk factor" — stuffing the type into the free-text box returns nothing. Enter the entity to reach its page, then use the site's own filters/facets/links (a form-type filter, a document list, a section link) to narrow to the specific document or section.
- IF A SEARCH RETURNS NOTHING: do not give up — the query was likely wrong for this site. Re-read the results state, then either simplify the query to the bare entity name, switch to the site's filter/browse UI, or "goto" the entity's page directly.
- Downloads: three forms — (a) "download" with the aid of a download link/button; (b) "download" with aid=null and value=<a document URL you can see> to save that file directly; (c) "download" with aid=null and value="" to save the CURRENT page. A document that renders INLINE (e.g. an SEC .htm opened in the viewer) has NO download button — do NOT hunt for one and do NOT give up: just emit download with the file's URL, or download the current page. The file is saved and verified on disk.
- Navigation: "goto" with a URL you can see on the page, one given in the task, or an obvious well-known domain for a named site. Never invent a deep/guessed path — go to the site root and navigate from there.
- USE LINK HREFS: on a list/results/index page, candidates that are links show their href=. To reach a specific row (a filing, a document, an article), "goto" that row's href directly, or "click" that exact aid — do NOT go back to a search box. On EDGAR you land on the company's filing list: goto the newest 10-K's ...-index.htm href, then on that index page goto/click the primary document (the .htm), then "download" it.
- Reading: "extract_text" on the element that holds the answer when the task asks for information.
- OFF-SCREEN TARGETS: a ranked-list entry, a footer contact, or a section deep in a long page may be OUTSIDE the current viewport — missing from the candidates and the visible text. Scroll with "keyboard" keys="PageDown" (repeat as needed; keys="End" jumps to the page bottom) and re-read the NEW state next turn. A first-screen miss is a reason to scroll, not to give_up.
- ANSWER TASKS (find a number / look up a price / answer a question): the extracted text IS the deliverable — the verifier judges what you extracted, never what you say in "reason". Once the answer is on screen you MUST "extract_text" the element containing it (do this BEFORE "done"); a run that never extracts the answer cannot pass, no matter how visible the answer was.
- SCREEN-LEVEL FALLBACK (mouse / keyboard): prefer aid-based click/fill/press — they are precise and verifiable. Use "mouse" (with x,y copied from a candidate's at=(x,y)) ONLY when no aid can address the thing you must click: a custom widget, a canvas/image hit-area, an option the DOM doesn't expose as its own element. Use "keyboard" to type at the current focus (value) or press a key/chord (keys: "Enter"/"Tab"/"Escape") when a widget took focus from a click but offers no fillable target — e.g. Tab between fields, Enter to confirm. Do NOT invent coordinates; only use an at=(x,y) shown in the candidate list.

WHEN BLOCKED
- If a CAPTCHA / "unusual traffic" / "are you a robot" page appears, do NOT try to solve it. Prefer "goto" to reach the target site by URL directly, bypassing the search engine. Only if there is genuinely no way forward, "give_up" with the reason — this is honest and correct, not a failure of effort.

PROGRESS DISCIPLINE
- Check ACTIONS SO FAR before deciding: never repeat an action that already failed the same way — change strategy instead (different element, press instead of click, dismiss a modal).
- Modern sites are SPAs: the URL/content may have changed after your last action even without a full reload. Re-read the CURRENT state before acting.
- One action per turn; keep steps minimal — do not add exploratory clicks that don't serve the task.

BEFORE "done" — MANDATORY SELF-CHECK (P0-3 front gate; if ANY line fails, your next action is whatever FIXES it, not "done")
- Re-read SUCCESS WHEN and check EVERY condition against the CURRENT state literally: the exact text is on screen NOW / the URL contains the fragment NOW / the download completed / the answer was delivered with "extract_text".
- If the task asks for a number of items, COUNT them on the page — "looks about right" is not a count.
- If the task specifies filters/options/fields, confirm EVERY one is applied or filled — one missed required field or filter means NOT done.
- A premature "done" is rejected by the harness and only burns a step; with steps remaining, spend them making the conditions true instead.

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
                    obs: Observation, history: list[str],
                    plan_steps: list[str] | None = None,
                    image_path: str | None = None) -> PlannerDecision: ...


def _candidate_lines(obs: Observation) -> str:
    out = []
    for c in obs.candidates:
        if not c.visible:
            continue
        label = c.aria_label or c.placeholder or c.text or c.name or c.id
        line = (f'aid={c.index} <{c.tag}{" role="+c.role if c.role else ""}> '
                f'type={c.type or "-"} id="{c.id[:30]}" label="{label[:50]}"')
        # selection state of a choice control: tells the planner an option is
        # ALREADY chosen so it won't click it again and toggle it back off.
        if c.checked in ("true", "false", "mixed"):
            line += f' checked={c.checked}'
        # the element's on-screen centre: a REAL observed coordinate the planner
        # can hand to a "mouse" action to click a widget the aid path can't drive
        # (no hallucinated pixels — these come from the live layout).
        if c.visible:
            line += f' at=({c.x + 4},{c.y + 4})'
        # a link's href is the target: showing it lets the planner navigate a
        # list/results page deterministically (goto the exact filing/document)
        # instead of clicking blindly — crucial on link-dense pages like EDGAR.
        if c.tag == "a" and c.href and not c.href.startswith(("javascript:", "#")):
            line += f' href="{c.href[:80]}"'
        out.append(line)
    return "\n".join(out[:50]) or "(no visible interactive elements)"


# P0-2 mouse-coordinate grounding margin: candidate x,y are top-left corners,
# so a legitimate click (an element's centre, a SoM box centre read off the
# screenshot) can land somewhat beyond the furthest observed corner — but a
# coordinate FAR outside every observed element is invented, not observed.
_MOUSE_MARGIN = 300


def _build_action(decision: dict, obs: Observation):
    """Validate the model's decision into a BrowserAction. Returns the action,
    None (malformed — generic re-plan), or an error STRING when the model
    referenced a target that does not exist in the observation (P0-2
    pre-execution grounding gate, SG EncodedId contract): a hallucinated aid /
    off-page mouse coordinate becomes a noop with a precise reason instead of
    burning an executor step and being misdiagnosed as selector_not_found."""
    action = decision.get("action")
    aid = decision.get("aid")
    value = decision.get("value", "") or ""
    target = None
    aid_error = ""
    if aid is not None:
        known = {c.index for c in obs.candidates}
        if (isinstance(aid, (int, float)) and not isinstance(aid, bool)
                and int(aid) in known):
            target = ElementTarget(selector=f'[data-aid="{int(aid)}"]', selector_type="css",
                                   description=f"aid {int(aid)}")
        else:
            aid_error = f"hallucinated aid: {aid!r} is not in the observed candidate list"
    # only actions that CONSUME the target are gated; a spurious aid on e.g.
    # goto is ignored (the navigation itself is still well-grounded).
    if aid_error and action in ("fill", "click", "press", "extract_text", "download"):
        return aid_error
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
    if action == "mouse":
        x, y = decision.get("x"), decision.get("y")
        if isinstance(x, (int, float)) and isinstance(y, (int, float)):
            # P0-2: ground the coordinate against the observed layout — negative
            # or far-beyond-every-candidate pixels were invented, not read from
            # an at=(x,y) or a SoM box. No visible candidates -> nothing to
            # ground against, don't false-block the only escape hatch.
            vis = [c for c in obs.candidates if c.visible]
            if x < 0 or y < 0 or (vis and (
                    x > max(c.x for c in vis) + _MOUSE_MARGIN
                    or y > max(c.y for c in vis) + _MOUSE_MARGIN)):
                return (f"hallucinated coordinates: ({int(x)},{int(y)}) is outside "
                        "every observed element — use an at=(x,y) from the candidate list")
            clicks = decision.get("clicks") or 1
            button = decision.get("button") if decision.get("button") in ("left", "right") else "left"
            return MouseAction(x=int(x), y=int(y), button=button, clicks=int(clicks))
        return None
    if action == "keyboard":
        keys = str(decision.get("keys", "") or "")
        return KeyboardAction(text="" if keys else value, keys=keys)
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
  "success_conditions": 0-3 objects proving completion, each:
       {"type":"text_visible","value":"<short exact substring that appears on the page only when done>"}
       {"type":"url_contains","value":"<url fragment true only when done>"}
       {"type":"download_exists","value":"<distinctive text the SAVED FILE must contain, or \"\">"}
       {"type":"answer_matches","value":"<regex the EXTRACTED answer text must match>"}
     answer_matches is for ANSWER-TYPE tasks — the user wants a piece of information back (find a number, look up a price/date, answer a question). The agent must deliver the answer with an extract_text action; the verifier matches your regex against that extracted text, and a run that never extracts anything FAILS. Write the regex for the SHAPE of the deliverable, not its unknown value: a revenue/price figure -> "[\\$€¥]?[0-9][0-9,\\.]+\\s*(billion|million|億|兆)?", a duration -> "[0-9]+\\s*(hr|hours?|小時|分鐘|min)", a date -> "20[0-9]{2}". Prefer answer_matches over text_visible for these tasks: a text_visible landmark can be true before the answer was ever delivered.
     download_exists is verified against the file's BYTES on disk, not its name: if the task says to download a document AND locate a section in it (e.g. "download the 10-K and find Risk Factors"), set value to that section's exact heading ("Risk Factors") so a wrong or blocked page saved to disk cannot count as success. Use "" only when any file is acceptable.
     Prefer a distinctive phrase in the language the target page will render (English site -> English phrase). Keep each value short and literal (a title, a heading, a ticker, a section name) — not a whole sentence, not vague words that appear everywhere.
     NEVER use an id/slug/token taken from a URL as a text_visible value — it does not appear as text on the page and would fail even when the task succeeded.
     NEVER echo the task sentence: a condition must describe the state of the DELIVERABLE (the answer text, the destination page's landmark, the downloaded content), not repeat an entity name/ticker/word the task itself contains. A token like "intc" from the task is visible on any search/results page long before anything is done, so it proves nothing — such short task-echo text_visible values are rejected by a code guard. For submitting a form, the completion landmark is the POST-SUBMIT page: use url_contains of the response URL (a Google Form lands on ".../formResponse") or the confirmation text the form shows after submit ("已送出" / "response has been recorded"), never a value copied from the form's link.

Rules: pick conditions that are SUFFICIENT (met => task genuinely done) and NECESSARY (task done => met). If the task is a search/read, the condition is the answer text or a landmark of the destination page. If it downloads a document to inspect, prefer download_exists carrying the section/heading to confirm. For an open-ended task ("find the most popular X", "找找有什麼有趣的商品", "播放某首歌"), still TRY a best-effort weak condition — text_visible of a query keyword, or a landmark of the destination page (its title/section). But if nothing observable would truthfully prove completion, return an empty array [] — the run then ends as an honest `unknown` for human review. NEVER invent a condition just to have one: a fabricated condition that fails on a genuinely-completed task is worse than none. Do not require login/CAPTCHA text. Never fabricate a value you don't expect to literally appear."""


def _task_echo(value: str, task: str) -> bool:
    """Task-echo guard (premature-landmark source reduction): a SHORT
    text_visible value lifted verbatim from the task sentence — an entity
    name/ticker like "intc" — is rendered by any search/results page the moment
    the agent types it, i.e. it can be true before the task has done anything
    (the observed INTC 10-K false PASS). Normalised (lowercase, collapsed
    whitespace) substring match, ≤3 whitespace tokens; longer quoted phrases
    usually describe the real deliverable and are kept."""
    v = " ".join(value.lower().split())
    return bool(v) and len(v.split()) <= 3 and v in " ".join(task.lower().split())


class LLMPlanner:
    """Agent Mode planner backed by an OpenAI/Codex-compatible model."""

    def __init__(self, client: OpenAIClient | None = None) -> None:
        self.client = client or OpenAIClient()

    def available(self) -> bool:
        return self.client.available()

    def supports_vision(self) -> bool:
        """The OpenAI-compatible channel carries images (complete_json's
        image_path -> multimodal content) and the default codex gateway hands
        them to the account's multimodal model via `codex exec --image`, so
        auto vision escalation (P3) may switch the SoM screenshot on when the
        run is stuck. Planners without this method (mock/scripted) answer
        False via the agent's getattr default; an operator on a text-only
        backend disables escalation with AGENT_VISION=0."""
        return True

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
            if t not in ("text_visible", "url_contains", "download_exists", "answer_matches"):
                continue
            if t != "download_exists" and not (0 < len(v) <= 120):
                continue
            if t == "text_visible" and _task_echo(v, task):
                continue   # premature landmark: a task-sentence token proves nothing
            if t == "answer_matches":
                import re as _re
                try:
                    _re.compile(v)
                except _re.error:
                    continue   # an uncompilable pattern can never be evidence
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
                    obs: Observation, history: list[str],
                    plan_steps: list[str] | None = None,
                    image_path: str | None = None) -> PlannerDecision:
        route = ("PLANNED ROUTE (your own preflight plan — follow it, but adapt to "
                 "the live page and re-plan if a step is blocked or already done):\n"
                 + "\n".join(f"  {i+1}. {s}" for i, s in enumerate(plan_steps)) + "\n"
                 if plan_steps else "")
        shot = ("SCREENSHOT: attached — a Set-of-Marks image where each interactive "
                "element is boxed and labelled with its aid number. Use it to see "
                "the layout and pick the right aid; for a widget with no usable aid, "
                'read its box centre and emit "mouse" with those x,y.\n'
                if image_path else "")
        user = (
            f"TASK: {task}\n"
            f"{route}"
            f"SUCCESS WHEN: {'; '.join(success_conditions)}\n"
            f"CURRENT URL: {obs.url}\nTITLE: {obs.title}\n"
            f"{shot}"
            f"VISIBLE TEXT (excerpt): {obs.visible_text[:1600]}\n"
            f"CANDIDATE ELEMENTS:\n{_candidate_lines(obs)}\n"
            f"ACTIONS SO FAR: {', '.join(history[-6:]) or '(none)'}\n"
            "Return the next single action as JSON."
        )
        import httpx  # local: only browser Agent Mode pays for this import
        try:
            decision, rec = self.client.complete_json(_SYSTEM, user, image_path=image_path)
        except LLMConfigError:
            raise
        except httpx.HTTPError as e:
            # A transient timeout / 5xx / dropped connection on ONE turn must not
            # crash a run that has already made progress (this is the observed
            # "ERROR — ReadTimeout"). Re-plan next turn, exactly like a malformed
            # action; the loop is still bounded by max_steps.
            return PlannerDecision(kind="noop",
                                   reason=f"LLM 連線逾時或失敗({type(e).__name__}),重試")
        kind = decision.get("action", "give_up")
        if kind in ("done", "give_up"):
            return PlannerDecision(kind=kind, reason=decision.get("reason", ""), llm=rec, raw=decision)
        act = _build_action(decision, obs)
        if isinstance(act, str):
            # P0-2 grounding gate fired: the target was hallucinated. Noop with
            # the precise reason — never reaches the executor, and the reason
            # lands in ACTIONS SO FAR so the model picks a real aid next turn.
            return PlannerDecision(kind="noop", reason=act, llm=rec, raw=decision)
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
                    obs: Observation, history: list[str],
                    plan_steps: list[str] | None = None,
                    image_path: str | None = None) -> PlannerDecision:
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
