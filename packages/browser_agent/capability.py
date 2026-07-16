"""Capability router / guard (SPEC 6.3, 6.4).

The "responsibility boundary" is enforced in code, not just documented: before
a task runs, classify it; before any action runs, screen it. Irreversible or
credentialed operations (login, purchase, checkout, payment, submitting a
formal form) are refused with an explicit reason — the agent returns
TaskRun.status == "refused", it does not attempt them. This is what makes
"not supported" a real limit rather than an unenforced policy.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# The task-level patterns below are English keyword matches. A task written in
# a non-Latin script matches none of them, so it used to pass unscreened — a
# fail-open on the exact boundary this module exists to hold, on a UI that
# accepts Chinese. Screen the script first and refuse what we cannot screen.
_UNSCREENABLE_SCRIPT = re.compile(
    r"[぀-ヿ㐀-䶿一-鿿가-힯Ѐ-ӿ֐-ۿ]"
)

# task-level: natural-language intents we refuse outright
_FORBIDDEN_INTENT = {
    "login": re.compile(r"\b(log\s?in|sign\s?in|authenticate|enter\s+password|credentials?)\b", re.I),
    "purchase": re.compile(r"\b(buy|purchase|checkout|add to cart|place (an )?order|pay(ment)?)\b", re.I),
    "post_submit": re.compile(r"\b(post|publish|submit (the )?(form|application|order|comment|review))\b", re.I),
    "captcha": re.compile(r"\bcaptcha\b", re.I),
    "paid_data": re.compile(r"\b(paywall|subscription required|premium data)\b", re.I),
}

# action-level: value/target hints that indicate a forbidden interaction
_FORBIDDEN_VALUE = re.compile(
    r"password|credit\s?card|cvv|card number|\bssn\b|routing number|place order|checkout|pay now",
    re.I,
)
_FORBIDDEN_TARGET_WORDS = re.compile(
    r"password|checkout|place[-_ ]?order|buy[-_ ]?now|add[-_ ]?to[-_ ]?cart|pay[-_ ]?now|submit[-_ ]?payment",
    re.I,
)


@dataclass
class CapabilityDecision:
    allowed: bool
    category: str  # 'ok' or the forbidden category
    reason: str


def screen_task(natural_language_task: str) -> CapabilityDecision:
    if _UNSCREENABLE_SCRIPT.search(natural_language_task):
        return CapabilityDecision(
            allowed=False, category="unscreenable_language",
            reason="task text is not in English; the capability guard screens English only, "
                   "so a non-English task cannot be checked against the login/purchase/"
                   "submit boundary (SPEC 6.4) and is refused rather than run unscreened. "
                   "Please restate the task in English.")
    for category, pat in _FORBIDDEN_INTENT.items():
        if pat.search(natural_language_task):
            return CapabilityDecision(
                allowed=False, category=category,
                reason=f"task requires a {category} operation, which is out of the supported "
                       f"capability set (SPEC 6.4: no login/CAPTCHA/purchase/formal submit/paid data)")
    return CapabilityDecision(allowed=True, category="ok", reason="task is within supported capabilities")


def screen_action(action) -> CapabilityDecision:
    at = getattr(action, "type", "")
    value = getattr(action, "value", "") or ""
    target = getattr(action, "target", None)
    target_blob = ""
    if target is not None:
        target_blob = f"{getattr(target, 'selector', '')} {getattr(target, 'description', '')}"
    if at in ("fill", "press") and _FORBIDDEN_VALUE.search(value):
        return CapabilityDecision(False, "sensitive_input",
                                  f"action would enter sensitive/credential data ('{value[:20]}...') — refused")
    # the raw keyboard channel must not become a hole in the credential boundary
    if at == "keyboard":
        typed = f"{getattr(action, 'text', '') or ''} {getattr(action, 'keys', '') or ''}"
        if _FORBIDDEN_VALUE.search(typed):
            return CapabilityDecision(False, "sensitive_input",
                                      f"keyboard would enter sensitive/credential data ('{typed.strip()[:20]}...') — refused")
    if at in ("click", "download") and _FORBIDDEN_TARGET_WORDS.search(target_blob):
        return CapabilityDecision(False, "irreversible_action",
                                  f"action targets an irreversible control ('{target_blob.strip()[:40]}') — refused")
    return CapabilityDecision(True, "ok", "action is reversible and within capabilities")
