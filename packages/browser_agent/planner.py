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
  "aid":    integer aid from the candidate list, or null (only goto/done/give_up may omit it)
  "value":  fill text / key like "Enter" / goto URL; else ""
  "reason": one short sentence in the task's language

CHOOSING ELEMENTS
- Use ONLY listed aids. Each candidate shows tag, role, type, id and label — weigh ALL of them.
- Prefer semantically-right controls: a real submit (type=submit / role=button with a search/submit label) over a random clickable; an input/textarea/searchbox for typing.
- AVOID traps: ids/labels containing decoy/fake/ad/promo/sponsor, login/sign-in prompts, cookie-notice links. If a consent/cookie dialog blocks the page, dismiss it first (accept/agree/close button), then continue the task.

PLAYBOOK
- Prefer going straight to the target site over a web search. If the task names a site or brand with an obvious domain (finlab -> finlab.tw, wikipedia -> en.wikipedia.org, a company's SEC 10-K -> sec.gov EDGAR), use "goto" with that URL instead of searching. Search engines often block automation with a CAPTCHA.
- If you DO land on a search-results page, click the most relevant organic result to leave it; don't keep searching.
- Search flows (when needed): fill the search box first, then click the submit control — or "press" Enter on the box if no reliable submit exists or a click had no effect.
- Downloads: use "download" with the aid of the download link/button (the file is saved and verified on disk). If a download control isn't visible yet, navigate to it first.
- Navigation: "goto" with a URL you can see on the page, one given in the task, or an obvious well-known domain for a named site. Never invent a deep/guessed path — go to the site root and navigate from there.
- Reading: "extract_text" on the element that holds the answer when the task asks for information.

WHEN BLOCKED
- If a CAPTCHA / "unusual traffic" / "are you a robot" page appears, do NOT try to solve it. Prefer "goto" to reach the target site by URL directly, bypassing the search engine. Only if there is genuinely no way forward, "give_up" with the reason — this is honest and correct, not a failure of effort.

PROGRESS DISCIPLINE
- Check ACTIONS SO FAR before deciding: never repeat an action that already failed the same way — change strategy instead (different element, press instead of click, dismiss a modal).
- Modern sites are SPAs: the URL/content may have changed after your last action even without a full reload. Re-read the CURRENT state before acting.
- One action per turn; keep steps minimal — do not add exploratory clicks that don't serve the task.

HONESTY & BOUNDARIES
- "done" ONLY when the success conditions are actually satisfied in the current state (visible text / URL / a completed download) — not because you expect them to become true.
- "give_up" honestly when no candidate can advance the task, the page requires login/CAPTCHA/payment, or you are looping. Say why.
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
        out.append(f'aid={c.index} <{c.tag}{" role="+c.role if c.role else ""}> '
                   f'type={c.type or "-"} id="{c.id[:30]}" label="{label[:50]}"')
    return "\n".join(out[:40]) or "(no visible interactive elements)"


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
    if action == "download" and target:
        return DownloadAction(target=target)
    if action == "goto" and value:
        return GotoAction(url=value)
    return None


class LLMPlanner:
    """Agent Mode planner backed by an OpenAI/Codex-compatible model."""

    def __init__(self, client: OpenAIClient | None = None) -> None:
        self.client = client or OpenAIClient()

    def available(self) -> bool:
        return self.client.available()

    def next_action(self, task: str, success_conditions: list[str],
                    obs: Observation, history: list[str]) -> PlannerDecision:
        user = (
            f"TASK: {task}\n"
            f"SUCCESS WHEN: {'; '.join(success_conditions)}\n"
            f"CURRENT URL: {obs.url}\nTITLE: {obs.title}\n"
            f"VISIBLE TEXT (excerpt): {obs.visible_text[:600]}\n"
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
            return PlannerDecision(kind="give_up", reason="model returned an unusable action",
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
