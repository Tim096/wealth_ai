"""Failure diagnosis + selector repair (SPEC 6.8, 6.9).

Self-correction is diagnosis-driven, not retry-driven: classify the failure,
then apply the matching strategy. Repair searches the accessibility-tree
candidates (role / aria-label / placeholder / text / position) for the element
that matches the target's *purpose*, avoiding decoys, and returns a new
ElementTarget that is verified in a small step before the task resumes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from browser_core import ElementTarget
from browser_core.failures import FAILURE_TAXONOMY, FailureType
from browser_agent.executor import ActionOutcome
from browser_agent.observer import ElementCandidate, Observation

# purpose -> what a matching element looks like
_PURPOSE_HINTS = {
    "search_box": {"tags": {"input", "textarea"}, "types": {"text", "search", ""},
                   "roles": {"searchbox", "textbox"}, "words": {"search", "query", "find", "lookup"}},
    "submit_button": {"tags": {"button"}, "types": {"submit", ""}, "roles": {"button"},
                      "words": {"search", "submit", "go", "find"}},
    "result_link": {"tags": {"a"}, "types": {""}, "roles": {"link"}, "words": set()},
    "download_button": {"tags": {"button", "a"}, "types": {""}, "roles": {"button", "link"},
                        "words": {"download", "csv", "pdf", "export"}},
    "filter_dropdown": {"tags": {"select"}, "types": {""}, "roles": {"listbox", "combobox"},
                        "words": {"filter", "sort", "category"}},
}


@dataclass
class Diagnosis:
    failure_type: FailureType
    repairable: bool
    detail: str


_RESULT_CONTAINER_HINT = re.compile(r"\b0\s+results?\b|no results|nothing found", re.I)


def diagnose_failure(outcome: ActionOutcome, obs: Observation,
                     url_changed: bool, expected_url_fragment: str = "") -> Diagnosis:
    spec = FAILURE_TAXONOMY
    if obs.modal_present and not outcome.ok:
        return Diagnosis("modal_blocking", spec["modal_blocking"].repairable,
                         "a modal/cookie banner is intercepting interaction")
    if outcome.matched_count == 0 or "no element" in outcome.error:
        return Diagnosis("selector_not_found", spec["selector_not_found"].repairable,
                         "selector matched no element")
    if outcome.matched_count > 1:
        return Diagnosis("multiple_candidates", spec["multiple_candidates"].repairable,
                         f"selector matched {outcome.matched_count} elements")
    if "timeout" in outcome.error.lower():
        return Diagnosis("timeout", spec["timeout"].repairable, outcome.error)
    if expected_url_fragment and expected_url_fragment not in obs.url:
        return Diagnosis("wrong_page", spec["wrong_page"].repairable,
                         f"URL {obs.url} does not contain expected fragment {expected_url_fragment!r}")
    if outcome.action_type == "click" and outcome.ok and not url_changed:
        return Diagnosis("click_no_effect", spec["click_no_effect"].repairable,
                         "click succeeded but URL/DOM did not change")
    if _RESULT_CONTAINER_HINT.search(obs.visible_text):
        return Diagnosis("empty_result", spec["empty_result"].repairable,
                         "result container present but reports zero results")
    return Diagnosis("silent_failure_risk", spec["silent_failure_risk"].repairable,
                     "insufficient evidence to classify — refuse to claim success")


def _is_decoy(cand: ElementCandidate) -> bool:
    blob = f"{cand.id} {cand.aria_label} {cand.text}".lower()
    return "decoy" in blob or "fake" in blob


def _score_candidate(cand: ElementCandidate, purpose: str, want_value: str) -> tuple[float, str]:
    hints = _PURPOSE_HINTS.get(purpose, _PURPOSE_HINTS["submit_button"])
    reasons: list[str] = []
    score = 0.0
    if not cand.visible:
        return -1.0, "not visible"
    if _is_decoy(cand):
        return -1.0, "looks like a decoy element"
    if cand.tag in hints["tags"]:
        score += 2.0; reasons.append(f"tag={cand.tag}")
    if cand.type in hints["types"]:
        score += 0.5
    if cand.role in hints["roles"]:
        score += 1.5; reasons.append(f"role={cand.role}")
    blob = f"{cand.aria_label} {cand.placeholder} {cand.name} {cand.text} {cand.id}".lower()
    if any(w in blob for w in hints["words"]):
        score += 2.0; reasons.append("purpose word match")
    # for a submit button, a real form button beats a bare icon with no semantics
    if purpose == "submit_button" and cand.type == "submit":
        score += 1.0; reasons.append("type=submit")
    if want_value and want_value.lower() in blob:
        score += 1.0; reasons.append("value hint match")
    return score, ", ".join(reasons) or "weak match"


@dataclass
class RepairResult:
    ok: bool
    new_target: ElementTarget | None
    chosen_reason: str
    considered: list[str]


def repair_target(purpose: str, obs: Observation, want_value: str = "") -> RepairResult:
    """Find the best candidate for `purpose` in the current observation."""
    scored = []
    for c in obs.candidates:
        s, why = _score_candidate(c, purpose, want_value)
        scored.append((s, why, c))
    scored.sort(key=lambda x: x[0], reverse=True)
    considered = [f"{c.tag}#{c.id or '-'}[{c.aria_label or c.placeholder or c.text[:20]}] "
                  f"score={s:.1f} ({why})" for s, why, c in scored[:6]]
    if not scored or scored[0][0] <= 0:
        return RepairResult(False, None, "no viable candidate", considered)
    best_s, best_why, best_c = scored[0]
    return RepairResult(
        ok=True,
        new_target=ElementTarget(selector=best_c.css(), selector_type="css",
                                 description=f"repaired {purpose}"),
        chosen_reason=f"{best_c.css()} score={best_s:.1f}: {best_why}",
        considered=considered,
    )
