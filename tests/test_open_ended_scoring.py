"""BUCKET 1 — make open-ended (zero-condition) tasks scorable.

Before this change verify_contract returned a blanket `unknown` for any task
with no machine-checkable success condition and second_judge abstained → zero
signal. Now an evidence-grounded WebJudge scorer (second_judge.score_open_ended)
decomposes the task into observable key points, judges each against the final
page with the Extractor/Verifier demotion (a 'satisfied' whose span is absent
from the evidence is demoted to abstain), and produces a REAL pass/fail — while
keeping the abstain fallback so no unmet task is ever fabricated into a pass.

verifier.py stays the SOLE judge: scoring is opt-in (an extractor must be
injected). With no extractor the behaviour is unchanged (honest unknown), which
is what every existing eval relies on. Offline (no LLM key) always abstains.
"""

import sys
from dataclasses import dataclass, field
from pathlib import Path

from browser_core import BrowserTaskContract, ForbiddenCondition, SuccessCondition
from browser_agent import second_judge as sj
from browser_agent.verifier import verify_contract

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))


# --- minimal Observation stand-in (verifier only reads url + visible_text here) ---
@dataclass
class _Obs:
    url: str = "file:///mock/v1/index.html?q=laptop"
    title: str = "MockShop"
    visible_text: str = ("MockShop\nSearch results\nUltraBook Pro 14 in stock\n"
                         "Gaming Rig X — $1299\nFree shipping over $50\n")
    candidates: list = field(default_factory=list)
    modal_present: bool = False


EVIDENCE = {"url": _Obs().url, "visible_text": _Obs().visible_text}


def _open_contract(nl="逛逛商店看有什麼筆電", outcome="user browsed laptops in the catalog"):
    return BrowserTaskContract(
        task_id="open-1", natural_language_task=nl, expected_outcome=outcome,
        success_conditions=[], forbidden_conditions=[])


# --- LLM extractor plumbing (fake client, no key) ---
class _FakeResp:
    cost_usd = 0.001


class _ScriptedClient:
    """Returns key-point extraction first, then one scripted payload per
    judge_condition call, in order. Carries a temperature check: WebJudge must
    run deterministic."""

    def __init__(self, key_points, judgments):
        self._kp = {"key_points": list(key_points)}
        self._judgments = list(judgments)
        self.calls = 0

    def complete_json(self, system, user, image_path=None):
        self.calls += 1
        if "decompose" in system:                 # key-point extraction call
            return self._kp, _FakeResp()
        return self._judgments.pop(0), _FakeResp()


def _llm(client):
    return sj.LLMExtractor(client)


# ============================================================================
# second_judge.score_open_ended
# ============================================================================
def test_key_points_all_satisfied_scores_yes():
    client = _ScriptedClient(
        key_points=["a laptop product is listed", "prices are shown"],
        judgments=[
            {"extracted": "UltraBook Pro 14 in stock", "judgment": "satisfied",
             "reason": "laptop listed"},
            {"extracted": "Gaming Rig X — $1299", "judgment": "satisfied",
             "reason": "price shown"}])
    r = sj.score_open_ended("逛逛筆電", "user saw laptops", EVIDENCE, _llm(client))
    assert r["verdict"] == "yes" and r["score"] == 1.0
    assert r["key_points"] == ["a laptop product is listed", "prices are shown"]
    assert r["cost_usd"] > 0                       # extraction + 2 judgments billed


def test_one_key_point_refuted_scores_no():
    client = _ScriptedClient(
        key_points=["a laptop is listed", "checkout was completed"],
        judgments=[
            {"extracted": "UltraBook Pro 14 in stock", "judgment": "satisfied",
             "reason": "listed"},
            {"extracted": None, "judgment": "not_satisfied",
             "reason": "no order confirmation on the page"}])
    r = sj.score_open_ended("買一台筆電", "an order was placed", EVIDENCE, _llm(client))
    assert r["verdict"] == "no" and r["score"] == 0.0


def test_hallucinated_span_is_demoted_so_unconfirmed_task_abstains():
    # the LLM claims satisfied but quotes a span that is NOT in the evidence:
    # the demotion turns it to abstain → the whole task abstains, never a pass
    client = _ScriptedClient(
        key_points=["a discount coupon is displayed"],
        judgments=[{"extracted": "SAVE20 coupon applied", "judgment": "satisfied",
                    "reason": "trust me"}])
    r = sj.score_open_ended("找優惠券", "a coupon is shown", EVIDENCE, _llm(client))
    assert r["verdict"] == "abstain" and r["score"] is None
    assert "not supported" in r["judgments"][0].reason


def test_offline_extractor_abstains_never_fabricates_a_pass():
    r = sj.score_open_ended("逛商店", "user browsed", EVIDENCE, sj.OfflineExtractor())
    assert r["verdict"] == "abstain" and r["score"] is None
    assert r["cost_usd"] == 0.0


def test_no_key_points_falls_back_to_expected_outcome_judgment():
    # extraction returns [] → single expected_outcome judgment path
    client = _ScriptedClient(
        key_points=[],
        judgments=[{"extracted": "Search results", "judgment": "satisfied",
                    "reason": "catalog visible"}])
    r = sj.score_open_ended("逛商店", "the catalog is visible", EVIDENCE, _llm(client))
    assert r["verdict"] == "yes" and r["score"] == 1.0
    assert r["key_points"] == []
    assert "no key points extracted" in r["reason"]


def test_extract_key_points_malformed_output_yields_empty():
    class _Bad:
        def complete_json(self, s, u, image_path=None):
            return {"_parse_error": True, "_raw": "junk"}, _FakeResp()

    kps, cost = sj.extract_key_points("t", "o", _Bad())
    assert kps == [] and cost == 0.001


# ============================================================================
# verify_contract routing (verifier stays the sole judge)
# ============================================================================
def test_verify_no_extractor_is_unchanged_honest_unknown():
    # default call (no extractor) MUST behave exactly as before: honest unknown
    v = verify_contract(_open_contract(), _Obs())
    assert v.status == "unknown"
    assert "open-ended task: no machine-checkable success condition" in v.reason


def test_verify_open_ended_with_evidence_scores_pass():
    client = _ScriptedClient(
        key_points=["a laptop product is listed"],
        judgments=[{"extracted": "UltraBook Pro 14 in stock",
                    "judgment": "satisfied", "reason": "listed"}])
    v = verify_contract(_open_contract(), _Obs(), open_ended_extractor=_llm(client))
    assert v.status == "pass"
    assert "open-ended scoring" in v.reason
    assert "UltraBook Pro 14 in stock" in v.observed_evidence


def test_verify_open_ended_without_evidence_scores_fail():
    client = _ScriptedClient(
        key_points=["an order confirmation number is shown"],
        judgments=[{"extracted": None, "judgment": "not_satisfied",
                    "reason": "no confirmation on the page"}])
    v = verify_contract(_open_contract("下單買筆電", "an order was placed"),
                        _Obs(), open_ended_extractor=_llm(client))
    assert v.status == "fail"
    assert v.missing_evidence                      # carries the unmet reason


def test_verify_open_ended_abstain_falls_through_to_unknown():
    # NO FALSE SUCCESS: an unconfirmable task must NOT become a pass — it stays
    # the honest unknown (offline extractor abstains)
    v = verify_contract(_open_contract(), _Obs(),
                        open_ended_extractor=sj.OfflineExtractor())
    assert v.status == "unknown"
    assert "open-ended task: no machine-checkable success condition" in v.reason


def test_verify_open_ended_hallucinated_pass_still_unknown_not_pass():
    # the LLM tries to pass on an invented span; demotion → abstain → unknown.
    # This is the genuinely-unmet condition that MUST still fail to pass.
    client = _ScriptedClient(
        key_points=["a refund was issued"],
        judgments=[{"extracted": "Refund of $999 issued", "judgment": "satisfied",
                    "reason": "hallucinated"}])
    v = verify_contract(_open_contract("退款", "a refund was issued"), _Obs(),
                        open_ended_extractor=_llm(client))
    assert v.status != "pass"
    assert v.status == "unknown"


def test_verify_forbidden_violation_beats_scoring():
    # a forbidden violation short-circuits to fail BEFORE any scoring runs; the
    # scorer client is never called
    client = _ScriptedClient(key_points=["x"], judgments=[])
    contract = BrowserTaskContract(
        task_id="open-f", natural_language_task="逛商店", expected_outcome="browsed",
        success_conditions=[],
        forbidden_conditions=[ForbiddenCondition(type="error_text_visible",
                                                 value="server error")])
    obs = _Obs(visible_text="MockShop\nInternal server error occurred\n")
    v = verify_contract(contract, obs, open_ended_extractor=_llm(client))
    assert v.status == "fail"
    assert client.calls == 0                       # scoring never reached


# ============================================================================
# non-open-ended tasks are untouched by the new parameter
# ============================================================================
def test_extractor_ignored_when_conditions_present():
    client = _ScriptedClient(key_points=["x"], judgments=[])
    contract = BrowserTaskContract(
        task_id="c1", natural_language_task="find UltraBook",
        expected_outcome="UltraBook visible",
        success_conditions=[SuccessCondition(type="text_visible", value="UltraBook")],
        forbidden_conditions=[])
    v = verify_contract(contract, _Obs(), open_ended_extractor=_llm(client))
    assert v.status == "pass"                       # normal condition path
    assert client.calls == 0                        # open-ended scorer not invoked
