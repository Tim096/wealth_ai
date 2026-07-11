"""P0-8 advisory second judge tests: per-condition micro-judgments, the
Extractor/Verifier split (hallucinated evidence demoted to abstain),
gate-then-average aggregation, sequential short-circuit, the stub-pass smoke
test, evidence caching (replayable), the per-condition diff vs the primary
(disagree -> needs_review), the open-ended score channel, and the harness
adjudication rollup. Offline and deterministic — no browser, no LLM key; the
LLM path is exercised through a fake client.
"""

import json
import sys
from pathlib import Path

import pytest

from browser_core import BrowserTaskContract, SuccessCondition
from browser_agent import second_judge as sj

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import browser_eval as be  # noqa: E402 — same import style as test_p0_9


EVIDENCE = {
    "url": "file:///mock/v1/index.html?q=laptop",
    "visible_text": "MockShop\nSearch results\nUltraBook Pro 14 in stock\n"
                    '0 results for "teleporter"\n',
    "sha256": "x", "cached_at": "t",
}


def _cond(type_, value):
    return SuccessCondition(type=type_, value=value)


# --- OfflineExtractor + deterministic verifier stage ---
def test_offline_text_visible_yes_quotes_the_line():
    j = sj.judge_condition("text_visible", "UltraBook", EVIDENCE, sj.OfflineExtractor())
    assert j.verdict == "yes"
    assert j.extracted == "UltraBook Pro 14 in stock"
    assert j.source == "offline"


def test_offline_text_visible_no():
    j = sj.judge_condition("text_visible", "quantum", EVIDENCE, sj.OfflineExtractor())
    assert j.verdict == "no"
    assert j.extracted is None


def test_offline_url_contains():
    yes = sj.judge_condition("url_contains", "q=laptop", EVIDENCE, sj.OfflineExtractor())
    no = sj.judge_condition("url_contains", "checkout", EVIDENCE, sj.OfflineExtractor())
    assert yes.verdict == "yes" and yes.extracted == EVIDENCE["url"]
    assert no.verdict == "no"


def test_offline_unjudgeable_type_abstains():
    j = sj.judge_condition("download_exists", "report.pdf", EVIDENCE, sj.OfflineExtractor())
    assert j.verdict == "abstain"          # explicit abstain, never a silent no


def test_offline_no_query_echo_masking_is_the_independent_reading():
    # the primary masks zero-result echo lines (FG-BROWSER-003); the naive
    # offline judge deliberately does NOT — the divergence is the signal
    j = sj.judge_condition("text_visible", "teleporter", EVIDENCE, sj.OfflineExtractor())
    assert j.verdict == "yes"


class _FakeExtractor:
    """Scripted extractor: returns the given payloads in order."""
    source = "fake"

    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = 0

    def extract(self, cond_type, value, evidence):
        self.calls += 1
        return self.payloads.pop(0)


def test_hallucinated_evidence_demoted_to_abstain():
    # extractor claims satisfied on a span that is NOT in the cached evidence
    fake = _FakeExtractor([{"extracted": "totally invented span",
                            "judgment": "satisfied", "reason": "trust me"}])
    j = sj.judge_condition("text_visible", "UltraBook", EVIDENCE, fake)
    assert j.verdict == "abstain"
    assert "not supported" in j.reason


def test_satisfied_without_extraction_cannot_pass():
    fake = _FakeExtractor([{"extracted": None, "judgment": "satisfied", "reason": ""}])
    j = sj.judge_condition("text_visible", "UltraBook", EVIDENCE, fake)
    assert j.verdict == "abstain"


def test_extractor_crash_is_an_abstain_not_a_raise():
    class Boom:
        source = "fake"

        def extract(self, *a):
            raise RuntimeError("kaput")

    j = sj.judge_condition("text_visible", "x", EVIDENCE, Boom())
    assert j.verdict == "abstain"
    assert "extractor error" in j.reason


# --- LLMExtractor normalization (fake client, no key) ---
class _FakeResp:
    cost_usd = 0.001
    input_tokens = output_tokens = 1


class _FakeClient:
    def __init__(self, parsed):
        self.parsed = parsed

    def complete_json(self, system, user, image_path=None):
        return self.parsed, _FakeResp()


def test_llm_extractor_valid_satisfied_passes_and_carries_cost():
    client = _FakeClient({"extracted": "UltraBook Pro 14 in stock",
                          "judgment": "satisfied", "reason": "seen"})
    j = sj.judge_condition("text_visible", "UltraBook", EVIDENCE, sj.LLMExtractor(client))
    assert j.verdict == "yes"
    assert j.cost_usd == 0.001
    assert j.source == "llm"


def test_llm_extractor_malformed_output_abstains():
    for parsed in ({"_raw": "garbage", "_parse_error": True},
                   {"judgment": "definitely"}, {"nope": 1}):
        j = sj.judge_condition("text_visible", "UltraBook", EVIDENCE,
                               sj.LLMExtractor(_FakeClient(parsed)))
        assert j.verdict == "abstain"


# --- gate-then-average aggregation ---
def _J(cond, verdict):
    return sj.MicroJudgment(cond, verdict, None, "", "fake")


def test_gate_failure_gates_score_to_zero():
    agg = sj.gate_then_average([_J("g", "no"), _J("a", "yes"), _J("b", "yes")],
                               critical={"g"})
    assert agg["verdict"] == "no" and agg["score"] == 0.0
    assert agg["gate_failed"] == ["g"]


def test_gate_abstain_makes_the_whole_task_abstain():
    agg = sj.gate_then_average([_J("g", "abstain"), _J("a", "yes")], critical={"g"})
    assert agg["verdict"] == "abstain" and agg["score"] is None


def test_noncritical_average_gives_partial_credit_gates_excluded():
    agg = sj.gate_then_average(
        [_J("g", "yes"), _J("a", "yes"), _J("b", "yes"), _J("c", "no")],
        critical={"g"})
    assert agg["verdict"] == "partial"
    assert agg["score"] == 0.667            # gate NOT in the average (2/3, not 3/4)
    assert agg["n_averaged"] == 3


def test_all_yes_is_yes_and_all_no_is_no():
    assert sj.gate_then_average([_J("a", "yes"), _J("b", "yes")])["verdict"] == "yes"
    assert sj.gate_then_average([_J("a", "no"), _J("b", "no")])["verdict"] == "no"


def test_abstain_blocks_a_full_yes():
    agg = sj.gate_then_average([_J("a", "yes"), _J("b", "abstain")])
    assert agg["verdict"] == "partial" and agg["score"] == 1.0


def test_empty_judgments_abstain_never_a_vacuous_yes():
    agg = sj.gate_then_average([])
    assert agg["verdict"] == "abstain" and agg["score"] is None


def test_all_nongate_abstain_is_abstain():
    agg = sj.gate_then_average([_J("g", "yes"), _J("a", "abstain")], critical={"g"})
    assert agg["verdict"] == "abstain"


def test_skipped_counts_as_zero_in_the_average():
    agg = sj.gate_then_average([_J("a", "yes"), _J("b", "skipped")])
    assert agg["score"] == 0.5


# --- judge_task: sequential short-circuit ---
def test_sequential_short_circuit_skips_after_first_no():
    fake = _FakeExtractor([
        {"extracted": None, "judgment": "not_satisfied", "reason": "missing"}])
    conds = [_cond("text_visible", "step1"), _cond("text_visible", "step2"),
             _cond("text_visible", "step3")]
    result = sj.judge_task(conds, EVIDENCE, fake, sequential=True)
    verdicts = [j.verdict for j in result["judgments"]]
    assert verdicts == ["no", "skipped", "skipped"]
    assert fake.calls == 1                  # short-circuit: no extractor call after the no
    assert result["aggregate"]["score"] == 0.0


# --- stub-pass smoke test ---
def test_smoke_test_passes_on_real_evidence():
    result = sj.smoke_test([_cond("text_visible", "UltraBook")], EVIDENCE)
    assert all(j.verdict == "yes" for j in result["judgments"])


def test_smoke_test_raises_on_empty_evidence():
    with pytest.raises(sj.SecondJudgeSmokeError):
        sj.smoke_test([_cond("text_visible", "x")], {"url": "", "visible_text": ""})


# --- evidence caching: replayable ---
def test_cache_evidence_roundtrip_and_replay(tmp_path):
    p = tmp_path / "ev.json"
    ev = sj.cache_evidence(EVIDENCE["url"], EVIDENCE["visible_text"], p)
    loaded = sj.load_evidence(p)
    assert loaded["url"] == EVIDENCE["url"]
    assert loaded["sha256"] == ev["sha256"]
    # judging from the cache reproduces the live judgment (replayability)
    live = sj.judge_condition("text_visible", "UltraBook", ev, sj.OfflineExtractor())
    replay = sj.judge_condition("text_visible", "UltraBook", loaded, sj.OfflineExtractor())
    assert (live.verdict, live.extracted) == (replay.verdict, replay.extracted)


# --- diff vs primary ---
def test_diff_flags_disagreement_as_needs_review():
    judgments = [_J("text_visible:a", "yes"), _J("text_visible:b", "no"),
                 _J("text_visible:c", "abstain"), _J("text_visible:d", "skipped")]
    primary = {"text_visible:a": "pass", "text_visible:b": "pass",
               "text_visible:c": "unknown", "text_visible:d": "pass"}
    diff = sj.diff_with_primary(judgments, primary)
    by = {d["condition"]: d for d in diff}
    assert by["text_visible:a"]["agree"] is True
    assert by["text_visible:b"]["agree"] is False and by["text_visible:b"]["needs_review"]
    assert by["text_visible:c"]["agree"] is True       # abstain maps to unknown
    assert by["text_visible:d"]["agree"] is None       # skipped: no comparison


# --- open-ended score channel ---
def test_open_ended_offline_abstains_score_none():
    r = sj.judge_open_ended("browse the shop", "user saw the catalog",
                            EVIDENCE, sj.OfflineExtractor())
    assert r["judgment"].verdict == "abstain" and r["score"] is None


def test_open_ended_llm_yes_scores_one():
    client = _FakeClient({"extracted": "Search results",
                          "judgment": "satisfied", "reason": "catalog shown"})
    r = sj.judge_open_ended("browse the shop", "user saw the catalog",
                            EVIDENCE, sj.LLMExtractor(client))
    assert r["judgment"].verdict == "yes" and r["score"] == 1.0


# --- harness rollup (pure) ---
def test_adjudication_summary_rollup():
    records = [
        {"task_id": "t1", "llm_cost_usd": 0.002, "disagreements": ["text_visible:x"],
         "conditions": [
             {"condition": "text_visible:x", "agree": False, "second": "yes"},
             {"condition": "text_visible:y", "agree": True, "second": "no"}]},
        {"task_id": "t2", "conditions": [
            {"condition": "text_visible:z", "agree": None, "second": "abstain"}]},
        {"task_id": "t3", "error": "RuntimeError: page gone"},
    ]
    s = be.adjudication_summary(records)
    assert s["tasks_judged"] == 3
    assert s["conditions_judged"] == 3
    assert s["compared"] == 2 and s["agree"] == 1 and s["disagree"] == 1
    assert s["abstain"] == 1
    assert s["condition_agreement_rate"] == 0.5
    assert s["tasks_needing_review"] == ["t1"]
    assert s["judge_errors"] == ["t3"]
    assert s["llm_cost_usd"] == 0.002


def test_adjudication_summary_empty():
    s = be.adjudication_summary([])
    assert s["condition_agreement_rate"] is None
    assert s["tasks_needing_review"] == []


# --- integration: real eval pass with the second judge armed ---
@pytest.mark.integration
def test_script_pass_with_second_judge_writes_adjudication(tmp_path, monkeypatch):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    if not (ROOT / "data" / "mock_sites" / "v1" / "index.html").exists():
        pytest.skip("mock sites missing")
    monkeypatch.setattr(be, "OUT", tmp_path / "runs")
    spec = json.loads(be.TASKS.read_text(encoding="utf-8"))
    tasks = spec["tasks"][:2]
    judge_ctx = {"extractor": sj.OfflineExtractor(), "records": []}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1000, "height": 800})
        rows = be.run_script_pass(page, tasks, tmp_path / "mem.json",
                                  judge_ctx=judge_ctx)
        browser.close()

    assert all(r["harness_status"] == "done" for r in rows)
    assert len(judge_ctx["records"]) == len(tasks)
    for t, rec, row in zip(tasks, judge_ctx["records"], rows):
        assert rec["task_id"] == t["task_id"]
        assert rec["smoke_ok"] is True
        # evidence pre-cached to disk before judging (replayable artifact)
        ev = json.loads(Path(rec["evidence_path"]).read_text(encoding="utf-8"))
        assert ev["sha256"] == rec["evidence_sha256"]
        assert len(rec["conditions"]) == len(t["success_text"])
        # row carries the advisory block; the verdict fields are untouched
        assert row["second_judge"]["verdict"] in ("yes", "no", "partial", "abstain")
        assert row["status"] in ("pass", "fail", "unknown", "refused")
    s = be.adjudication_summary(judge_ctx["records"])
    assert s["conditions_judged"] > 0
