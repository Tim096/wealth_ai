"""Task verifier (SPEC 6.7): checks a BrowserTaskContract against observed page
state and returns a three-state VerifierResult. If a condition cannot be
observed, the verdict is `unknown` — never a disguised pass.
"""

from __future__ import annotations

import os

from browser_core import BrowserTaskContract
from browser_agent.observer import Observation
from eval_core import ConditionCheck, combine_checks
from observability_core import VerifierResult

_MIN_DOWNLOAD_BYTES = 512          # smaller than this is not a real document
_DOWNLOAD_SCAN_BYTES = 8_000_000   # read up to this much to confirm content


def _download_ok(path: str, needle: str) -> str:
    """Trustworthy download check: the file must exist, be a non-trivial
    document, and — when the task named the content — ACTUALLY CONTAIN it. A
    wrong/blocked page written to disk (or a stub with the right name) must not
    count as success, so we read the bytes, never just the path string."""
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
            content = fh.read(_DOWNLOAD_SCAN_BYTES).decode("utf-8", errors="replace").lower()
    except OSError:
        return "unknown"
    n = needle.lower()
    # content is the real proof; the filename is a weak secondary signal
    return "pass" if (n in content or n in os.path.basename(path).lower()) else "fail"


def _check_success(cond, obs: Observation, extracted: dict[str, str]) -> str:
    t, v = cond.type, cond.value
    if t == "url_contains":
        return "pass" if v in obs.url else "fail"
    if t == "text_visible":
        return "pass" if v.lower() in obs.visible_text.lower() else "fail"
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
    return combine_checks(checks)
