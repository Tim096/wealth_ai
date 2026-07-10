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

_SYSTEM = """You drive a web browser to complete a task. You may ONLY return a single JSON object choosing the next action. You never write code and never invent CSS selectors — you target an element only by its numeric "aid" from the candidate list.

Return exactly one JSON object with keys:
  "action": one of "fill","click","press","goto","extract_text","download","done","give_up"
  "aid": integer id of the target element from the candidates (or null)
  "value": string (fill text, press key like "Enter", or goto url; else "")
  "reason": one short sentence

Rules:
- Pick "aid" ONLY from the listed candidates. If nothing fits, use give_up.
- Use "done" when the success conditions already appear satisfied on the page.
- Prefer filling the search box then clicking/ pressing Enter on the submit control.
- To download a file, use action "download" with the aid of the download link/button.
- Never choose an element whose text/label looks like a decoy, ad, or login."""


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
