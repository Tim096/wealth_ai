"""Task verifier (SPEC 6.7): checks a BrowserTaskContract against observed page
state and returns a three-state VerifierResult. If a condition cannot be
observed, the verdict is `unknown` — never a disguised pass.
"""

from __future__ import annotations

import os
import re

from browser_core import BrowserTaskContract
from browser_agent.observer import Observation
from eval_core import ConditionCheck, combine_checks
from observability_core import VerifierResult

_MIN_DOWNLOAD_BYTES = 512          # smaller than this is not a real document
_DOWNLOAD_SCAN_BYTES = 8_000_000   # read up to this much to confirm content
_BINARY_REPLACEMENT_RATIO = 0.05   # more undecodable bytes than this -> not readable text

# Zero/none-result status lines that ECHO the query back at the user
# ('0 results for "teleporter"'). A needle inside such a line is the agent's
# own query reflected, never page evidence (FG-BROWSER-003). Generic patterns,
# not mock-site strings.
_QUERY_ECHO_RE = re.compile(
    r"\b(?:0|no|zero)\s+(?:results?|matches?|items?|hits?|products?)\b"
    r"|\bnot(?:hing)?\s+found\b|\bdid\s+not\s+match\b"
    r"|找不到|查無|沒有(?:結果|符合)|无结果|没有结果",
    re.IGNORECASE)


def _text_visible_hit(needle: str, visible_text: str) -> bool:
    """True only when the needle appears OUTSIDE zero-result echo lines."""
    kept = "\n".join(line for line in visible_text.splitlines()
                     if not _QUERY_ECHO_RE.search(line))
    return needle.lower() in kept.lower()


def _download_ok(path: str, needle: str) -> str:
    """Trustworthy download check: the file must exist, be a non-trivial
    document, and — when the task named the content — ACTUALLY CONTAIN it.
    Content-first (FG-BROWSER-002): readable bytes are the only proof strong
    enough to pass. Readable content without the needle fails no matter how
    right the filename looks; unreadable (binary) bytes plus a filename hit is
    a weak signal → honest unknown, never a pass."""
    if not path or not os.path.exists(path):
        return "unknown"          # nothing downloaded → not observable
    try:
        size = os.path.getsize(path)
    except OSError:
        return "unknown"
    if size < _MIN_DOWNLOAD_BYTES:
        return "fail"             # a tiny file is not the document that was asked for
    if not needle:
        return "pass"             # download-only task: a real file is enough
    try:
        with open(path, "rb") as fh:
            raw = fh.read(_DOWNLOAD_SCAN_BYTES)
    except OSError:
        return "unknown"
    n = needle.lower()
    content = raw.decode("utf-8", errors="replace").lower()
    if content.count("�") > len(content) * _BINARY_REPLACEMENT_RATIO:
        # binary/undecodable bytes can neither prove nor disprove the content
        return "unknown" if n in os.path.basename(path).lower() else "fail"
    return "pass" if n in content else "fail"


def _check_success(cond, obs: Observation, extracted: dict[str, str]) -> str:
    t, v = cond.type, cond.value
    if t == "url_contains":
        return "pass" if v in obs.url else "fail"
    if t == "text_visible":
        return "pass" if _text_visible_hit(v, obs.visible_text) else "fail"
    if t == "table_extracted":
        return "pass" if any(v.lower() in x.lower() for x in extracted.values()) else "unknown"
    if t == "field_value_equals":
        return "pass" if any(v == x for x in extracted.values()) else "fail"
    if t == "download_exists":
        return _download_ok(extracted.get("__download__", ""), v)
    if t == "screenshot_region_changed":
        return "unknown"  # not observable without a baseline; honest unknown
    return "unknown"


def _check_forbidden(cond, obs: Observation) -> str:
    t, v = cond.type, cond.value
    if t == "error_text_visible":
        return "fail" if v.lower() in obs.visible_text.lower() else "pass"
    if t == "captcha_visible":
        return "fail" if "captcha" in obs.visible_text.lower() or "captcha" in obs.url.lower() else "pass"
    if t == "login_required":
        low = obs.visible_text.lower()
        return "fail" if ("sign in" in low or "log in" in low) and "password" in low else "pass"
    if t == "wrong_domain":
        return "fail" if v not in obs.url else "pass"
    return "unknown"


def subtract_baseline(contract: BrowserTaskContract, obs: Observation,
                      ) -> tuple[BrowserTaskContract, list[str]]:
    """Baseline-subtraction (premature-landmark guard). A success condition that
    is ALREADY satisfied at t0 — start page loaded, before ANY action — cannot
    be evidence the task was completed: it was true when nothing had been done
    (the observed INTC failure: condition text_visible:intc, a token of the task
    sentence, was true on the very first EDGAR search page → false PASS).
    Such conditions are vacuous; drop them and report what was dropped so the
    trace shows it. If everything is dropped, the emptied contract flows into
    the open-ended gate in verify_contract: honest unknown, never a vacuous
    pass. download_exists is untouched (nothing is downloaded at t0 → unknown,
    not pass). Returns (effective contract, dropped ["type:value", ...])."""
    kept, dropped = [], []
    for c in contract.success_conditions:
        if _check_success(c, obs, {}) == "pass":
            dropped.append(f"{c.type}:{c.value}")
        else:
            kept.append(c)
    if not dropped:
        return contract, []
    return contract.model_copy(update={"success_conditions": kept}), dropped


def verify_contract(contract: BrowserTaskContract, obs: Observation,
                    extracted: dict[str, str] | None = None) -> VerifierResult:
    extracted = extracted or {}
    checks: list[ConditionCheck] = []
    for c in contract.success_conditions:
        checks.append(ConditionCheck(condition=f"{c.type}:{c.value}", required=True,
                                     observed=_check_success(c, obs, extracted)))
    for c in contract.forbidden_conditions:
        checks.append(ConditionCheck(condition=f"forbidden:{c.type}:{c.value}", required=False,
                                     observed=_check_forbidden(c, obs)))
    if not contract.success_conditions:
        # Structural gate for open-ended tasks: with ZERO success conditions,
        # combine_checks over the forbidden checks alone would report `pass`
        # whenever nothing forbidden happened — a vacuous pass. A forbidden
        # violation still fails; anything else is an honest `unknown`.
        result = combine_checks(checks)
        if result.status == "fail":
            return result
        return VerifierResult(
            status="unknown",
            reason="open-ended task: no machine-checkable success condition",
            required_evidence=[c.condition for c in checks],
            observed_evidence=result.observed_evidence,
            missing_evidence=["open-ended task: no machine-checkable success condition; "
                              "trace attached for human review"],
        )
    return combine_checks(checks)
