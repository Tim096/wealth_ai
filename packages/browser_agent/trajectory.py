"""Trajectory-level observation metrics (T1-4, SPEC eval-upgrade).

Two run-level diagnostics that OBSERVE a trajectory without changing agent
behaviour, mirroring AgentRewardBench's non-success annotation axes
(arxiv 2504.08942: success / side-effects / repetitiveness):

  * repetitiveness — from the recorded steps alone (no browser): how much of the
    trajectory is the agent repeating the same (action, selector) or cycling
    through a repeated block. Pure function over StepTrace; wired into
    TaskRun.as_dict().
  * side effects — a pre/post snapshot diff of PERSISTENT page state
    (localStorage / sessionStorage / cookies / leftover form input). Requires a
    page, so it is captured by the runner around a run, NOT inside the agent.
    On a real (non-mock) site persistent state is not controllable, so the honest
    verdict is `unknown` — never a fabricated "clean".

Both are RUN-LEVEL. They are deliberately kept off the per-step EvidenceRecord
path: `agent._emit_evidence` uses each step's `s.ok` as the step status, which is
NOT the verifier verdict — mixing a trajectory metric into that stream would
conflate step-level success with the task verdict. These live on the TaskRun.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# --- repetitiveness (pure logic over recorded steps) ---

def _token(step: Any) -> str:
    """A step's identity for repetition: what was done, to which element. Two
    steps with the same action on the same selector are 'the same move'. The
    selector distinguishes agent-mode planner steps that all share step=='planner'."""
    action = getattr(step, "action", "")
    selector = getattr(step, "selector_used", "")
    purpose = getattr(step, "step", "")
    return f"{purpose}|{action}|{selector}"


def _max_consecutive(tokens: list[str]) -> int:
    """Longest run of identical adjacent tokens (A A A -> 3)."""
    if not tokens:
        return 0
    best = cur = 1
    for i in range(1, len(tokens)):
        cur = cur + 1 if tokens[i] == tokens[i - 1] else 1
        best = max(best, cur)
    return best


def _longest_adjacent_cycle(tokens: list[str]) -> tuple[int, int]:
    """Longest immediately-repeated block: the (period, repeats) whose covered
    length period*repeats is greatest, with repeats>=2. Detects A B A B (period 2,
    repeats 2) as well as single-token loops (period 1). (0, 0) if none.
    Trajectories are short (<= a few dozen steps) so the O(n^2) scan is fine."""
    n = len(tokens)
    best = (0, 0)
    for p in range(1, n // 2 + 1):
        start = 0
        while start + p <= n - p:
            block = tokens[start:start + p]
            reps = 1
            k = start + p
            while k + p <= n and tokens[k:k + p] == block:
                reps += 1
                k += p
            if reps >= 2 and p * reps > best[0] * best[1]:
                best = (p, reps)
            start += 1
    return best


def repetition_report(steps: list[Any]) -> dict[str, Any]:
    """Repetition diagnostics for one trajectory. `repetition_score` in [0,1] is
    the fraction of steps that are duplicate moves (0 = every move distinct,
    1 = every move after the first is a repeat). `loop_detected` flags an
    immediately-repeated block (a stuck agent), which the duplicate fraction
    alone can miss when a short cycle repeats only twice."""
    tokens = [_token(s) for s in steps]
    n = len(tokens)
    if n == 0:
        return {"n_steps": 0, "n_unique": 0, "unique_ratio": None,
                "repetition_score": 0.0, "max_consecutive_repeat": 0,
                "loop_period": 0, "loop_repeats": 0, "loop_detected": False}
    n_unique = len(set(tokens))
    period, reps = _longest_adjacent_cycle(tokens)
    max_consec = _max_consecutive(tokens)
    # duplicate fraction: how many steps are repeats of a move already made
    repetition_score = round(1.0 - n_unique / n, 6)
    # a loop = a block repeated back-to-back OR the same move >=3 times running
    loop = (period > 0 and reps >= 2) or max_consec >= 3
    return {
        "n_steps": n,
        "n_unique": n_unique,
        "unique_ratio": round(n_unique / n, 6),
        "repetition_score": repetition_score,
        "max_consecutive_repeat": max_consec,
        "loop_period": period,
        "loop_repeats": reps,
        "loop_detected": bool(loop),
    }


# --- side effects (pre/post persistent-state diff) ---

# Captures ONLY persistent / residual state, not page content (which legitimately
# changes as the agent navigates). Passwords are excluded on purpose.
_SNAPSHOT_JS = r"""
() => {
  const ls = {}; for (let i = 0; i < localStorage.length; i++) { const k = localStorage.key(i); ls[k] = localStorage.getItem(k); }
  const ss = {}; for (let i = 0; i < sessionStorage.length; i++) { const k = sessionStorage.key(i); ss[k] = sessionStorage.getItem(k); }
  const forms = {};
  for (const el of document.querySelectorAll('input,textarea,select')) {
    if ((el.getAttribute('type') || '') === 'password') continue;
    const key = el.id || el.getAttribute('name') || el.getAttribute('aria-label') || el.tagName.toLowerCase();
    const val = (el.value || '').slice(0, 200);
    if (val) forms[key] = val;
  }
  return { url: location.href, local_storage: ls, session_storage: ss,
           cookies: document.cookie || '', form_values: forms };
}
"""


@dataclass
class StateSnapshot:
    url: str = ""
    local_storage: dict[str, str] = field(default_factory=dict)
    session_storage: dict[str, str] = field(default_factory=dict)
    cookies: str = ""
    form_values: dict[str, str] = field(default_factory=dict)

    @classmethod
    def capture(cls, page: Any) -> "StateSnapshot":
        raw = page.evaluate(_SNAPSHOT_JS)
        return cls(url=raw.get("url", ""),
                   local_storage=dict(raw.get("local_storage") or {}),
                   session_storage=dict(raw.get("session_storage") or {}),
                   cookies=raw.get("cookies", "") or "",
                   form_values=dict(raw.get("form_values") or {}))


def _dict_diff(before: dict[str, str], after: dict[str, str]) -> dict[str, Any]:
    added = {k: after[k] for k in after if k not in before}
    removed = [k for k in before if k not in after]
    changed = {k: {"from": before[k], "to": after[k]}
               for k in after if k in before and after[k] != before[k]}
    return {"added": added, "removed": removed, "changed": changed}


def _cookie_keys(cookie: str) -> set[str]:
    return {p.split("=", 1)[0].strip() for p in cookie.split(";") if p.strip()}


def side_effect_report(pre: StateSnapshot | None, post: StateSnapshot | None,
                       environment: str) -> dict[str, Any]:
    """Diff persistent state across a run. `environment` must be 'mock' for a
    controlled local site whose state we own; any other value (a real site) is
    reported `unknown` because we cannot attribute or reset its state — the
    three-state rule, never a fabricated clean verdict."""
    if environment != "mock":
        return {"status": "unknown", "environment": environment,
                "reason": "persistent state is not controllable on a real site — "
                          "side effects unobservable"}
    if pre is None or post is None:
        return {"status": "unknown", "environment": environment,
                "reason": "missing pre/post snapshot"}
    ls = _dict_diff(pre.local_storage, post.local_storage)
    ss = _dict_diff(pre.session_storage, post.session_storage)
    forms = _dict_diff(pre.form_values, post.form_values)
    cookies_added = sorted(_cookie_keys(post.cookies) - _cookie_keys(pre.cookies))
    cookies_removed = sorted(_cookie_keys(pre.cookies) - _cookie_keys(post.cookies))
    n_changes = (len(ls["added"]) + len(ls["removed"]) + len(ls["changed"])
                 + len(ss["added"]) + len(ss["removed"]) + len(ss["changed"])
                 + len(forms["added"]) + len(forms["removed"]) + len(forms["changed"])
                 + len(cookies_added) + len(cookies_removed))
    return {
        "status": "side_effects" if n_changes else "clean",
        "environment": environment,
        "n_changes": n_changes,
        "local_storage": ls,
        "session_storage": ss,
        "cookies": {"added": cookies_added, "removed": cookies_removed},
        "form_residue": forms,
    }
