"""Task verifier (SPEC 6.7): checks a BrowserTaskContract against observed page
state and returns a three-state VerifierResult. If a condition cannot be
observed, the verdict is `unknown` — never a disguised pass.
"""

from __future__ import annotations

from browser_core import BrowserTaskContract
from browser_agent.observer import Observation
from eval_core import ConditionCheck, combine_checks
from observability_core import VerifierResult


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
        path = extracted.get("__download__", "")
        if not path:
            return "unknown"          # no download observed
        # Trust the CONTENT, not the mere existence of a file. The reported failure
        # was a run that saved *something* (a wrong page) and called it success. So
        # a value is checked against the downloaded file's TEXT (did we save the
        # RIGHT document — one that actually contains "Risk Factors"?), and an empty
        # value still requires a real, non-trivial document, not a stub/error page.
        body = extracted.get("__download_text__", "")
        if not v:
            return "pass" if len(body.strip()) >= 200 else "unknown"
        return "pass" if v.lower() in body.lower() else "fail"
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
