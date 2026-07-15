"""Non-discriminative success conditions: the OTHER half of the vacuous pass.

Real failure (deployed build, contract compiled by the LLM preflight):

    task:       "Go to https://news.ycombinator.com and report the exact title
                 of the current #1 story"
    contract:   verification_conditions = ["answer_matches:.+"]
                (conditions_source: llm)
    verdict:    pass, confidence 1.0

`.+` is satisfied by ANY non-empty answer. The verifier certified the SHAPE of
the deliverable and never its correctness, then stamped confidence 1.0 on it —
a vacuous pass, the most dangerous failure this project defines. The same hole
swallows `answer_matches:[0-9]+`: return any number at all and the run passes.

This is the second axis of a discipline the verifier already has on one axis.
Baseline-subtraction (P1 premature-landmark) drops a condition that is ALREADY
true at t0, because something true before any action cannot be evidence of
completion. `answer_matches:.+` walks straight through that guard: at t0 there
is no answer, so it is legitimately false — and then true for every answer that
could ever follow. Same disease, second half:

    satisfied at t0        -> not evidence of completion  (subtract_baseline)
    satisfied by anything  -> not evidence of completion  (THIS FILE)

Rule under test: probe an `answer_matches` regex against a fixed corpus of
DECOY answers — garbage a correct run would never deliver (whitespace, site
chrome, "undefined", arbitrary numbers). A regex that accepts >= _MAX_DECOY_HIT
of them has no discriminative power, so it cannot count as satisfied evidence
and the verdict is capped at `unknown`.

What is deliberately NOT done: the answer is still delivered (TaskRun.answer is
untouched). The honest posture is "here is the answer, I will not claim I
verified it", never "I found nothing".
"""

import re


from browser_core import BrowserTaskContract, SuccessCondition
from browser_agent.observer import Observation
from browser_agent.verifier import (
    _DECOY_ANSWERS, _MAX_DECOY_HIT_RATIO, check_conditions, decoy_hit_ratio,
    is_non_discriminative, subtract_baseline, verify_contract,
)

# the deployed repro: any non-empty answer satisfies it
VACUOUS_RE = ".+"
# a real shape condition that DOES discriminate (used by the calibration set
# and the answer-channel eval) — must keep passing
DISCRIMINATIVE_RE = r"[\$][0-9][0-9,\.]+\s*(billion|million)?"

HN_ANSWER = "Show HN: I built a tiny CAD kernel in Rust"


def obs(text="", url="https://news.ycombinator.com/"):
    return Observation(url=url, title="Hacker News", visible_text=text, candidates=[])


def contract(pattern=VACUOUS_RE):
    return BrowserTaskContract(
        task_id="hn", natural_language_task=(
            "Go to https://news.ycombinator.com and report the exact title of "
            "the current #1 story"),
        expected_outcome="the exact title of the #1 story",
        success_conditions=[SuccessCondition(type="answer_matches", value=pattern)])


# ---------- the decoy corpus itself ----------

def test_decoy_corpus_is_a_real_corpus():
    # a corpus this small is the whole basis of the judgement — keep it honest:
    # enough decoys to make a ratio meaningful, all distinct.
    assert len(_DECOY_ANSWERS) >= 10
    assert len(set(_DECOY_ANSWERS)) == len(_DECOY_ANSWERS)
    assert 0.0 < _MAX_DECOY_HIT_RATIO <= 1.0


def test_decoy_corpus_covers_both_vacuous_families():
    # the two shapes the planner actually emits are "any text" (.+) and "any
    # number" ([0-9]+); a corpus of only prose would never catch the second.
    numeric = [d for d in _DECOY_ANSWERS if re.search(r"[0-9]", d)]
    assert len(numeric) >= 4
    assert len(_DECOY_ANSWERS) - len(numeric) >= 4


# ---------- the guard ----------

def test_any_answer_regex_is_non_discriminative():
    hits, total = decoy_hit_ratio(VACUOUS_RE)
    assert hits == total                       # `.+` accepts every decoy
    assert is_non_discriminative(VACUOUS_RE)


def test_bare_number_regex_is_non_discriminative():
    # the second reported instance: answer_matches:[0-9]+ passes on any number
    assert is_non_discriminative("[0-9]+")


def test_discriminative_regex_is_kept():
    hits, _ = decoy_hit_ratio(DISCRIMINATIVE_RE)
    assert hits == 0
    assert not is_non_discriminative(DISCRIMINATIVE_RE)


def test_malformed_regex_is_not_called_non_discriminative():
    # an uncompilable pattern is already an honest `unknown` elsewhere; the
    # decoy probe must not crash or mislabel it
    assert not is_non_discriminative("[unclosed")


# ---------- the verdict ----------

def test_hn_repro_vacuous_condition_cannot_pass():
    """THE reported failure. Before: pass / confidence 1.0. After: unknown."""
    v = verify_contract(contract(), obs(), {"answer": HN_ANSWER})
    assert v.status == "unknown"


def test_verdict_reason_names_the_condition_and_the_hit_rate():
    v = verify_contract(contract(), obs(), {"answer": HN_ANSWER})
    blob = v.reason + " " + " ".join(v.missing_evidence)
    assert "non-discriminative" in blob
    assert f"answer_matches:{VACUOUS_RE}" in blob
    assert f"/{len(_DECOY_ANSWERS)} decoys" in blob     # the measured number, not an adjective


def test_discriminative_condition_still_passes():
    # regression guard: the calibration set + answer-channel eval depend on this
    v = verify_contract(contract(DISCRIMINATIVE_RE), obs(),
                        {"answer": "Total revenue: $53.1 billion"})
    assert v.status == "pass"


def test_a_real_violation_still_fails_and_is_not_softened_to_unknown():
    # capping at `unknown` must never LAUNDER a fail into an unknown: the
    # answer does not match at all -> fail stays fail
    c = BrowserTaskContract(
        task_id="hn", natural_language_task="t", expected_outcome="o",
        success_conditions=[
            SuccessCondition(type="answer_matches", value=VACUOUS_RE),
            SuccessCondition(type="text_visible", value="NEVER_ON_THIS_PAGE_XYZ"),
        ])
    v = verify_contract(c, obs("nothing here"), {"answer": HN_ANSWER})
    assert v.status == "fail"


def test_no_answer_still_fails_not_unknown():
    # unchanged semantics: no delivery move = not done, and that is a fail.
    # The non-discriminative cap must not upgrade a fail into an unknown.
    v = verify_contract(contract(), obs(), {})
    assert v.status == "fail"


# ---------- it must not leak into the latch / baseline machinery ----------

def test_non_discriminative_condition_never_latches():
    # check_conditions feeds the P0-5 latch ledger; a vacuous condition that
    # latched would be banked as "satisfied at step N" and then promoted to
    # pass by verify_contract — the same vacuous pass by another door.
    st = check_conditions(contract(), obs(), {"answer": HN_ANSWER})
    assert st[f"answer_matches:{VACUOUS_RE}"] == "unknown"


def test_latch_cannot_promote_a_non_discriminative_condition():
    key = f"answer_matches:{VACUOUS_RE}"
    v = verify_contract(contract(), obs(), {"answer": HN_ANSWER}, latched={key: 1})
    assert v.status == "unknown"


def test_baseline_subtraction_is_unchanged():
    # at t0 there is no answer -> fail -> never dropped as a t0 landmark
    c = contract()
    filtered, dropped = subtract_baseline(c, obs("Show HN: something"))
    assert dropped == [] and filtered is c


# ---------- end to end: the answer is still delivered ----------

class _ExtractThenDonePlanner:
    """Extracts the #1 title, then reports done — the deployed HN trajectory."""

    def __init__(self, answer):
        self.answer = answer
        self.calls = 0

    def available(self):
        return True

    def next_action(self, task, success_conditions, obs, history,
                    plan_steps=None, image_path=None):
        from browser_agent.planner import PlannerDecision
        from browser_core.actions import ExtractTextAction, ElementTarget
        self.calls += 1
        if self.calls == 1:
            return PlannerDecision(
                kind="action", reason="read the #1 story title",
                action=ExtractTextAction(target=ElementTarget(
                    selector='[data-aid="1"]', selector_type="css")))
        return PlannerDecision(kind="done", reason=f"the #1 story is {self.answer}")


def test_agentic_run_delivers_the_answer_but_refuses_to_certify_it(tmp_path):
    """The full deployed shape: pass/1.0 becomes unknown/<1.0, and the user
    still gets the answer. 'Here is the answer, I will not claim I verified
    it' — not 'I found nothing'."""
    from tests.fakes_browser import fake_agent

    agent = fake_agent(tmp_path, site="news.ycombinator.com",
                       url="https://news.ycombinator.com/",
                       extract_text=HN_ANSWER)
    run = agent.run_agentic("hn-1", contract(),
                            _ExtractThenDonePlanner(HN_ANSWER), max_steps=5)

    assert run.status == "unknown"          # was: pass
    assert run.confidence != 1.0            # was: 1.0
    assert run.answer == HN_ANSWER          # still delivered
    assert run.as_dict()["answer"] == HN_ANSWER
    assert "non-discriminative" in run.verifier.reason


def test_agentic_run_with_a_discriminative_condition_still_passes(tmp_path):
    from tests.fakes_browser import fake_agent

    answer = "Total revenue: $53.1 billion"
    agent = fake_agent(tmp_path, site="answer", url="https://example.com/",
                       extract_text=answer)
    run = agent.run_agentic("ans-ok", contract(DISCRIMINATIVE_RE),
                            _ExtractThenDonePlanner(answer), max_steps=5)
    assert run.status == "pass"
    assert run.answer == answer
