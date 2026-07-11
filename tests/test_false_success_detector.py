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
    """FIX-2 前後對照。修復前 corpus 有 2 個 ground-truth false success
    (teleporter query-echo → tp=1;dlname filename-bypass → fn=1)。修復後
    verifier 端已消滅這兩個假 pass(誠實 fail),corpus 內 detector 可套用的
    false success 歸零 — tp=fn=0 是上游修好的好消息,不是 detector 退步;
    fp=0(不過度舉報)不變。"""
    corpus = build_corpus()
    m1 = evaluate(corpus)
    m2 = evaluate(corpus)
    assert m1 == m2  # pure function, reproducible
    # zero false positives on legit claimed passes (no over-flagging)
    assert m1["confusion"]["fp"] == 0
    # the verifier fixes removed every ground-truth false success from the corpus
    assert m1["n_ground_truth_false_success_applicable"] == 0
    assert m1["confusion"]["tp"] == 0
    assert m1["confusion"]["fn"] == 0


def test_download_content_bypass_fixed_upstream_no_longer_false_success():
    """FIX-2 (FG-BROWSER-002) 前後對照。修復前:cal-bad-dlname-annual-report
    是 verifier 假 pass(gt false success),且 detector 的 visible-text 特徵
    掃不到 download bytes → 誠實 miss(fn)。修復後:verifier content-first
    直接判 fail → 不再是 claimed pass,detector 不適用(applicable False),
    gt false success 為 False — 弱點在上游被消滅,不需要 detector 撈。"""
    corpus = build_corpus()
    rows = {r["id"]: r for r in evaluate(corpus)["per_record"]}
    r = rows["cal-bad-dlname-annual-report"]
    assert r["ground_truth_false_success"] is False
    assert r["applicable"] is False   # verifier now says fail -> not a claimed pass
    assert r["flag"] is False


def test_teleporter_query_echo_fixed_upstream_not_applicable():
    """FIX-2 (FG-BROWSER-003) 前後對照。修復前:teleporter 是 verifier 假 pass,
    detector 靠 claim_evidence_gap(query-echo)成功撈到(tp)。修復後:
    verifier 遮罩查詢回顯行 → 任務誠實 fail → 不是 claimed pass,detector
    不適用、gt false success 為 False。detector 的 query-echo 特徵本身仍有效
    (見 test_query_echo_needle_in_negative_line_flagged 的手工 record)。"""
    corpus = build_corpus()
    rows = {r["id"]: r for r in evaluate(corpus)["per_record"]}
    r = rows["imp-product-teleporter"]
    assert r["ground_truth_false_success"] is False
    assert r["evidence_reconstructed"] is True
    assert r["applicable"] is False   # honest fail -> triage does not apply
    assert r["flag"] is False
