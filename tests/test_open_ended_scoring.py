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

HOLE A follow-up (live 18/18 abstain): run_agentic now ARMS the scorer at
verdict time when the planner has a live LLM client (same client), and the
quotable evidence is the final page's text at a raised bounded budget plus the
P0-5 per-step obs excerpts — a quote grounded in either passes the demotion; a
quote appearing NOWHERE still demotes to abstain (no hallucinated pass).
"""

import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest

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
# HOLE A grounding: richer evidence (final-page text + P0-5 step excerpts)
# ============================================================================
class _RecordingClient(_ScriptedClient):
    """_ScriptedClient that also records every user prompt it saw."""

    def __init__(self, key_points, judgments):
        super().__init__(key_points, judgments)
        self.prompts = []

    def complete_json(self, system, user, image_path=None):
        self.prompts.append(user)
        return super().complete_json(system, user, image_path)

    def available(self):
        return True


def test_supplied_open_ended_evidence_overrides_default_obs():
    # the span lives ONLY in the caller-supplied evidence (the run_agentic
    # final-page re-read), not in obs.visible_text → grounding must use it
    client = _ScriptedClient(
        key_points=["the order confirmation is shown"],
        judgments=[{"extracted": "Order #A123 confirmed", "judgment": "satisfied",
                    "reason": "confirmation visible"}])
    ev = {"url": _Obs().url,
          "visible_text": "MockShop\nThank you!\nOrder #A123 confirmed\n"}
    v = verify_contract(_open_contract("下單", "an order was placed"), _Obs(),
                        open_ended_extractor=_llm(client), open_ended_evidence=ev)
    assert v.status == "pass"


def test_final_text_beyond_old_4k_cap_is_quotable_and_grounds():
    # live-abstain root cause: a span past the old 4000-char prompt cap could
    # neither be quoted nor grounded. With the raised budget the extractor SEES
    # it (prompt carries it) and the demotion accepts it.
    span = "GROUND-TRUTH-TOKEN order shipped"
    ev = {"url": "https://shop.example/done",
          "visible_text": ("filler line\n" * 700) + span + "\n"}   # span at ~8.4k chars
    assert ev["visible_text"].find(span) > 4000
    client = _RecordingClient(
        key_points=["the order shipped notice is shown"],
        judgments=[{"extracted": span, "judgment": "satisfied", "reason": "seen"}])
    v = verify_contract(_open_contract("出貨了嗎", "order shipped"), _Obs(),
                        open_ended_extractor=_llm(client), open_ended_evidence=ev)
    assert v.status == "pass"
    assert any(span in p for p in client.prompts)     # extractor actually saw it


def test_step_excerpt_grounds_midrun_evidence():
    # the confirmation was visible mid-run (P0-5 persisted excerpt) and the
    # final page navigated away — the quote grounds against the excerpt
    client = _ScriptedClient(
        key_points=["a booking confirmation appeared"],
        judgments=[{"extracted": "Booking BK-77 confirmed", "judgment": "satisfied",
                    "reason": "was shown at step 3"}])
    ev = {"url": _Obs().url, "visible_text": "MockShop\nHome page\n",
          "step_excerpts": ["Search results", "Booking BK-77 confirmed — thank you"]}
    v = verify_contract(_open_contract("訂位", "a booking was made"), _Obs(),
                        open_ended_extractor=_llm(client), open_ended_evidence=ev)
    assert v.status == "pass"


def test_quote_nowhere_in_final_text_or_excerpts_still_demoted():
    # NO FALSE SUCCESS on the widened grounding surface: a quote absent from
    # BOTH the final-page text and every step excerpt demotes → unknown
    client = _ScriptedClient(
        key_points=["a refund was issued"],
        judgments=[{"extracted": "Refund of $999 issued", "judgment": "satisfied",
                    "reason": "hallucinated"}])
    ev = {"url": _Obs().url, "visible_text": "MockShop\nHome page\n",
          "step_excerpts": ["Search results", "Cart is empty"]}
    v = verify_contract(_open_contract("退款", "a refund was issued"), _Obs(),
                        open_ended_extractor=_llm(client), open_ended_evidence=ev)
    assert v.status == "unknown"


def test_step_excerpts_are_bounded():
    # only the most recent _STEP_EXCERPTS_MAX ride along, within the char cap
    ev = {"step_excerpts": [f"excerpt-{i}" for i in range(30)]}
    out = sj._step_excerpts(ev)
    assert len(out) == sj._STEP_EXCERPTS_MAX
    assert out[-1] == "excerpt-29" and out[0] == "excerpt-20"    # most recent kept
    big = {"step_excerpts": ["x" * 2_000, "y" * 2_000, "z" * 2_000]}
    assert sum(len(e) for e in sj._step_excerpts(big)) <= sj._STEP_EXCERPTS_CHAR_CAP


# ============================================================================
# run_agentic wiring (live-like, playwright): the extractor is armed at
# verdict time from the planner's own client; offline stays honest unknown
# ============================================================================
class _DoneWithClientPlanner:
    """Scripted planner that claims done and CARRIES an LLM client — the shape
    run_agentic's open-ended arming keys on (planner.client.available())."""

    def __init__(self, client):
        self.client = client

    def available(self):
        return True

    def next_action(self, task, success_conditions, obs, history,
                    plan_steps=None, image_path=None):
        from browser_agent.planner import PlannerDecision
        return PlannerDecision(kind="done", reason="looked around, finished")


def _run_open_ended_live(tmp_path, page_html, client):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    from browser_agent.agent import BrowserAgent
    from browser_agent.memory_store import MemoryStore

    contract = BrowserTaskContract(
        task_id="open-live", natural_language_task="找找 MockShop 有什麼有趣的商品",
        expected_outcome="user browsed the catalog", success_conditions=[])
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        page = b.new_page()
        page.set_content(page_html)
        agent = BrowserAgent(page, MemoryStore(tmp_path / "m.json"), "live", "agentic")
        run = agent.run_agentic("open-live", contract,
                                _DoneWithClientPlanner(client), max_steps=4)
        b.close()
    return run


@pytest.mark.integration
def test_run_agentic_open_ended_evidence_on_final_page_passes(tmp_path):
    # HOLE A wired end-to-end: completion evidence IS in the final page text →
    # the armed scorer grounds the quote and the verdict is a REAL pass
    client = _RecordingClient(
        key_points=["a laptop product is visible in the catalog"],
        judgments=[{"extracted": "UltraBook Pro 14 in stock",
                    "judgment": "satisfied", "reason": "laptop visible"}])
    run = _run_open_ended_live(
        tmp_path, "<h1>MockShop</h1><p>UltraBook Pro 14 in stock</p>", client)
    assert run.status == "pass"
    assert "open-ended scoring" in run.verifier.reason
    assert client.calls >= 2                        # key points + >=1 judgment


@pytest.mark.integration
def test_run_agentic_open_ended_hallucinated_quote_stays_unknown(tmp_path):
    # NO FALSE SUCCESS at the wiring level: the LLM claims satisfied with a
    # span the page never showed → demoted → honest unknown, never pass
    client = _RecordingClient(
        key_points=["a discount coupon is displayed"],
        judgments=[{"extracted": "SAVE20 coupon applied",
                    "judgment": "satisfied", "reason": "trust me"}])
    run = _run_open_ended_live(tmp_path, "<h1>MockShop</h1><p>plain page</p>", client)
    assert run.status == "unknown"
    assert "open-ended task: no machine-checkable success condition" in run.verifier.reason


@pytest.mark.integration
def test_run_agentic_open_ended_offline_client_unchanged_unknown(tmp_path):
    # planner carries a client that reports unavailable → the scorer is never
    # armed, no LLM call is made, and the verdict is the unchanged honest unknown
    class _OfflineClient(_RecordingClient):
        def available(self):
            return False

    client = _OfflineClient(key_points=["x"], judgments=[])
    run = _run_open_ended_live(
        tmp_path, "<h1>MockShop</h1><p>UltraBook Pro 14 in stock</p>", client)
    assert run.status == "unknown"
    assert client.calls == 0


# ============================================================================
# Codex-gateway wrapper body resolution: the gateway force-fits EVERY
# completion into the planner action schema, so the judge payload arrives as
# {"action": "done", "value": "<the actual JSON>", ...}. The unwrap recovers
# the body; the grounding demotion still rules on the recovered span.
# ============================================================================
def _wrap(payload: dict) -> dict:
    import json as _json
    return {"action": "done", "aid": None, "value": _json.dumps(payload),
            "x": None, "y": None, "keys": "", "reason": "gateway schema wrapper"}


def test_gateway_wrapped_key_points_are_recovered():
    client = _ScriptedClient(key_points=[], judgments=[])
    client._kp = _wrap({"key_points": ["a laptop product is listed"]})
    kps, _ = sj.extract_key_points("逛筆電", "laptops visible", client)
    assert kps == ["a laptop product is listed"]


def test_gateway_wrapped_grounded_judgment_scores_yes():
    client = _ScriptedClient(
        key_points=["a laptop product is listed"],
        judgments=[_wrap({"extracted": "UltraBook Pro 14 in stock",
                          "judgment": "satisfied", "reason": "laptop listed"})])
    r = sj.score_open_ended("逛筆電", "user saw laptops", EVIDENCE, _llm(client))
    assert r["verdict"] == "yes" and r["score"] == 1.0


def test_gateway_wrapped_hallucinated_span_still_demoted_no_false_success():
    # NO FALSE SUCCESS through the unwrap: a wrapped 'satisfied' quoting a span
    # absent from the evidence demotes to abstain exactly like an unwrapped one
    client = _ScriptedClient(
        key_points=["a refund was issued"],
        judgments=[_wrap({"extracted": "Refund of $999 issued",
                          "judgment": "satisfied", "reason": "hallucinated"})])
    r = sj.score_open_ended("退款", "a refund was issued", EVIDENCE, _llm(client))
    assert r["verdict"] == "abstain" and r["score"] is None
    assert "not supported" in r["judgments"][0].reason


def test_gateway_wrapped_not_satisfied_scores_no():
    client = _ScriptedClient(
        key_points=["checkout was completed"],
        judgments=[_wrap({"extracted": None, "judgment": "not_satisfied",
                          "reason": "no order confirmation on the page"})])
    r = sj.score_open_ended("買筆電", "an order was placed", EVIDENCE, _llm(client))
    assert r["verdict"] == "no" and r["score"] == 0.0


def test_wrapper_with_non_json_value_stays_malformed_abstain():
    # a genuine planner action ('value' is not JSON) must NOT be misread as a
    # judge payload — it stays the malformed→cannot_tell→abstain path
    client = _ScriptedClient(
        key_points=["a laptop is listed"],
        judgments=[{"action": "fill", "aid": "q", "value": "laptop",
                    "x": None, "y": None, "keys": "", "reason": "planner action"}])
    r = sj.score_open_ended("逛筆電", "laptops visible", EVIDENCE, _llm(client))
    assert r["verdict"] == "abstain"
    assert "malformed judge output" in r["judgments"][0].reason


def test_unwrap_leaves_direct_payloads_untouched():
    direct = {"extracted": "x", "judgment": "satisfied", "reason": "r"}
    assert sj._unwrap_gateway_action(direct) is direct
    kp = {"key_points": ["a"], "action": "irrelevant"}      # expected key wins
    assert sj._unwrap_gateway_action(kp) is kp
    err = {"_parse_error": True, "_raw": "junk"}
    assert sj._unwrap_gateway_action(err) is err


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
