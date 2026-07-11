"""Verifier calibration harness tests (T1-1). Pure logic, no browser: cases are
hand-built (contract, Observation, extracted) triples fed straight to
verify_contract via the harness."""

from pathlib import Path

from tools.calibrate_verifier import (
    apparent_success_rate,
    build_cases,
    calibrate,
    rogan_gladen,
)


def _by_class(per_case, cls):
    return [r for r in per_case if r["corruption_class"] == cls]


def test_dataset_meets_spec_minimums():
    """前後對照:原本固定 4 個 corruption class(各 >=6)。P2 answer channel 讓
    answer_matches 有了 evidence 面,校準集加入第 5 類 answer_wrong(答案錯 /
    沒答案,2 例)——類別集合從嚴格等於 4 類改為包含 5 類,原 4 類門檻不變。"""
    cases = build_cases()
    n_success = sum(c["label"] == "success" for c in cases)
    n_corrupted = sum(c["label"] == "corrupted" for c in cases)
    assert n_success >= 20
    assert n_corrupted >= 20
    classes = {}
    for c in cases:
        if c["corruption_class"]:
            classes[c["corruption_class"]] = classes.get(c["corruption_class"], 0) + 1
    assert set(classes) == {"needle_removed", "wrong_url",
                            "download_wrong_content", "confident_false_claim",
                            "answer_wrong"}
    for k in ("needle_removed", "wrong_url", "download_wrong_content",
              "confident_false_claim"):
        assert classes[k] >= 5
    assert classes["answer_wrong"] >= 2
    # every case id unique — per_case rows must be attributable
    ids = [c["case_id"] for c in cases]
    assert len(ids) == len(set(ids))


def test_verifier_never_eats_confident_false_claims():
    # the claim text even contains the success needle; a single pass here would
    # mean the verifier consumes agent self-reports (the WebJudge failure mode)
    result = calibrate(build_cases())
    claims = _by_class(result["per_case"], "confident_false_claim")
    assert len(claims) >= 5
    assert all(r["verdict"] != "pass" for r in claims)


def test_needle_removed_and_wrong_url_all_caught():
    result = calibrate(build_cases())
    for cls in ("needle_removed", "wrong_url"):
        rows = _by_class(result["per_case"], cls)
        assert len(rows) >= 5
        assert all(r["verdict"] == "fail" for r in rows)


def test_filename_needle_bypass_fixed_content_first():
    """FIX-2 (FG-BROWSER-002) 前後對照。修復前:needle 只出現在檔名、bytes 是
    blocked page,_download_ok 接受 basename 當證據 → 假陽性 pass(FP=1,
    specificity 0.958333)。修復後 content-first:內容可讀且不含 needle →
    fail,檔名再像也不行;unknown 只留給不可讀 binary + 檔名命中的弱訊號。
    FP=0,specificity 1.0。"""
    result = calibrate(build_cases())
    row = next(r for r in result["per_case"] if r["case_id"] == "cal-bad-dlname-annual-report")
    assert row["verdict"] == "fail"
    assert result["confusion"]["fp"] == 0
    assert result["rates"]["specificity"] == 1.0


def test_missing_download_path_is_unknown_not_fail_not_pass():
    result = calibrate(build_cases())
    row = next(r for r in result["per_case"] if r["case_id"] == "cal-bad-dlmissing")
    assert row["verdict"] == "unknown"


def test_three_state_table_not_collapsed_into_binary():
    # unknown must stay its own column; binary mapping is declared, not implied
    result = calibrate(build_cases())
    for lab in ("success", "corrupted"):
        assert set(result["three_state_table"][lab]) == {"pass", "fail", "unknown"}
    t = result["three_state_table"]
    n_succ = sum(t["success"].values())
    n_corr = sum(t["corrupted"].values())
    c = result["confusion"]
    assert c["tp"] + c["fn_not_pass"] == n_succ
    assert c["fp"] + c["tn_not_pass"] == n_corr
    assert "unknown" in result["binary_mapping"]


def test_rogan_gladen_normal_case():
    rg = rogan_gladen(observed=0.8, sensitivity=1.0, specificity=0.9)
    assert rg["status"] == "ok"
    # output is rounded to 6 decimals
    assert abs(rg["corrected"] - (0.8 + 0.9 - 1) / (1.0 + 0.9 - 1)) < 1e-6


def test_rogan_gladen_degenerate_denominator_is_unknown():
    # sens + spec ~ 1 -> judge is a coin flip; corrected rate must be unknown
    rg = rogan_gladen(observed=0.8, sensitivity=0.55, specificity=0.5)
    assert rg["status"] == "unknown"
    assert rg["corrected"] is None


def test_rogan_gladen_out_of_range_is_clamped_and_labeled():
    # observed above what a perfect-spec judge could produce -> raw > 1
    rg = rogan_gladen(observed=0.99, sensitivity=0.8, specificity=1.0)
    assert rg["raw"] > 1.0
    assert rg["corrected"] == 1.0
    assert rg["status"] == "clamped"
    lo = rogan_gladen(observed=0.05, sensitivity=1.0, specificity=0.8)
    assert lo["raw"] < 0.0
    assert lo["corrected"] == 0.0
    assert lo["status"] == "clamped"


def test_apparent_rate_reads_verifier_verdicts_not_labels(tmp_path):
    # apparent layer counts what the verifier CLAIMED, not what the hand label
    # expected — the two layers must not be conflated
    art = tmp_path / "eval_results.json"
    art.write_text(
        '{"tasks": [{"status": "pass", "expected": "fail"},'
        ' {"status": "fail", "expected": "pass"},'
        ' {"status": "pass", "expected": "pass"},'
        ' {"status": "unknown", "expected": "pass"}]}', encoding="utf-8")
    ap = apparent_success_rate(art)
    # apparent = 2 claimed pass / 4, regardless of expected
    assert ap["claimed_pass"] == 2
    assert ap["apparent_success_rate"] == 0.5


def test_committed_artifacts_exist_and_agree_with_regeneration():
    import json
    root = Path(__file__).resolve().parents[1]
    cal = root / "data" / "browser_eval" / "calibration"
    cases_file = cal / "calibration_cases.json"
    results_file = cal / "calibration_results.json"
    assert cases_file.exists() and results_file.exists()
    committed = json.loads(results_file.read_text(encoding="utf-8"))
    fresh = calibrate(build_cases())
    assert committed["three_state_table"] == fresh["three_state_table"]
    assert committed["rates"] == fresh["rates"]
