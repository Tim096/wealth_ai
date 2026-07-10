"""T1-6: lightweight false-success detector (heuristic triage).

Pure-logic tests over hand-built trajectory records — the repo paradigm (build
the input dict directly, assert the detector output). No browser. Plus a
determinism/shape check on the committed-corpus eval.
"""

from __future__ import annotations

from packages.browser_agent.false_success import detect_false_success
from tools.false_success_detector import build_corpus, evaluate


# --- invariant: triage never touches the verdict, and only claimed passes apply ---

def test_verdict_never_changed():
    det = detect_false_success({"status": "pass", "confidence": 1.0})
    assert det["verdict_unchanged"] is True


def test_honest_fail_is_not_applicable():
    # an honest FAIL is not a false success; triage does not apply -> score 0, no flag
    det = detect_false_success({"status": "fail",
                                "verifier": {"status": "fail", "missing": ["x"]}})
    assert det["applicable"] is False
    assert det["flag"] is False
    assert det["score"] == 0.0


def test_legit_clean_success_not_flagged():
    det = detect_false_success({
        "status": "pass", "confidence": 1.0, "repairs": 0,
        "steps": [{"step": "search_box", "action": "fill", "selector_used": "#s", "ok": True},
                  {"step": "submit", "action": "click", "selector_used": "#b", "ok": True}],
        "verifier": {"status": "pass", "missing": []},
        "visible_text": "3 results for widget: Widget Pro in stock",
        "success_needles": ["Widget", "results for"],
    })
    assert det["applicable"] is True
    assert det["flag"] is False
    assert det["score"] == 0.0


# --- feature: claim_evidence_gap (query-echo, the strong contradiction) ---

def test_query_echo_needle_in_negative_line_flagged():
    # success needle "Teleporter" appears only inside a "0 results" line -> echo
    det = detect_false_success({
        "status": "pass",
        "verifier": {"status": "pass", "missing": []},
        "visible_text": '0 results for "teleporter"',
        "success_needles": ["Teleporter"],
    })
    assert det["features"]["claim_evidence_gap"] == 1.0
    assert det["flag"] is True
    assert det["score"] >= 0.5


def test_verifier_pass_but_missing_evidence_flagged():
    det = detect_false_success({
        "status": "pass",
        "verifier": {"status": "pass", "missing": ["text_visible:confirmed"]},
    })
    assert det["features"]["claim_evidence_gap"] == 1.0
    assert det["flag"] is True


# --- feature: hallucinated_claim (self-report asserts absent needle) ---

def test_hallucinated_self_report_flagged():
    det = detect_false_success({
        "status": "pass",
        "verifier": {"status": "pass", "missing": []},
        "claim": "I found the Teleporter and added it to the cart.",
        "visible_text": "Search results page. No Teleporter here.",  # needle absent as real hit
        "success_needles": ["added it to the cart"],  # asserted in claim, not in visible_text
    })
    # "added it to the cart" is in claim but not visible_text -> hallucinated
    assert det["features"]["hallucinated_claim"] == 1.0
    assert det["flag"] is True


# --- surface proxies are individually too weak to flag (paper's caution) ---

def test_confident_closing_alone_does_not_flag():
    det = detect_false_success({
        "status": "pass", "confidence": 1.0, "repairs": 3,
        "steps": [{"step": "a", "action": "click", "selector_used": "#x", "ok": True}],
    })
    assert det["features"]["confident_closing"] == 1.0
    assert det["score"] < 0.5  # weak proxy: 0.25 < threshold
    assert det["flag"] is False


def test_length_anomaly_alone_does_not_flag():
    steps = [{"step": f"s{i}", "action": "click", "selector_used": f"#e{i}", "ok": True}
             for i in range(20)]
    det = detect_false_success({"status": "pass", "confidence": 0.5, "repairs": 0, "steps": steps})
    assert det["features"]["length_anomaly"] == 1.0
    assert det["flag"] is False


def test_two_proxies_accumulate_to_flag():
    # confident_closing (0.25) + repetition loop (0.25) = 0.5 -> flags
    steps = [{"step": "p", "action": "click", "selector_used": "#same", "ok": True},
             {"step": "p", "action": "click", "selector_used": "#same", "ok": True},
             {"step": "p", "action": "click", "selector_used": "#same", "ok": True}]
    det = detect_false_success({"status": "pass", "confidence": 1.0, "repairs": 2, "steps": steps})
    assert det["features"]["repetition"] == 1.0
    assert det["features"]["confident_closing"] == 1.0
    assert det["flag"] is True


# --- committed-corpus eval: shape + honest known catch/miss ---

def test_corpus_eval_is_deterministic_and_honest():
    corpus = build_corpus()
    m1 = evaluate(corpus)
    m2 = evaluate(corpus)
    assert m1 == m2  # pure function, reproducible
    # zero false positives on legit claimed passes (no over-flagging)
    assert m1["confusion"]["fp"] == 0
    # catches at least the query-echo silent failure; the download-content bypass
    # is an honest out-of-scope miss (fn>=1)
    assert m1["confusion"]["tp"] >= 1
    assert m1["confusion"]["fn"] >= 1


def test_known_miss_download_content_bypass_is_surfaced():
    """The filename-bypass FP (download bytes are a captcha, filename matches the
    needle) is OUT of the visible-text/trajectory feature scope -> the detector
    does not flag it. Locking this documents the limitation; extending the
    detector to a download-content channel will flip this test."""
    corpus = build_corpus()
    rows = {r["id"]: r for r in evaluate(corpus)["per_record"]}
    r = rows["cal-bad-dlname-annual-report"]
    assert r["ground_truth_false_success"] is True
    assert r["applicable"] is True
    assert r["flag"] is False  # honest miss, by feature scope


def test_known_catch_teleporter_query_echo():
    corpus = build_corpus()
    rows = {r["id"]: r for r in evaluate(corpus)["per_record"]}
    r = rows["imp-product-teleporter"]
    assert r["ground_truth_false_success"] is True
    assert r["evidence_reconstructed"] is True
    assert r["flag"] is True
    assert r["features"]["claim_evidence_gap"] == 1.0
