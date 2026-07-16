"""Browser agent tests. Pure logic (verifier / repair / diagnosis) runs without
a browser; one integration test drives the real v1->v2 killer-demo flow."""

import pytest

from browser_core import BrowserTaskContract, ElementTarget, ForbiddenCondition, SuccessCondition
from browser_core.actions import ClickAction, FillAction
from browser_agent.capability import screen_action, screen_task
from browser_agent.executor import ActionOutcome
from browser_agent.observer import ElementCandidate, Observation
from browser_agent.repair import diagnose_failure, repair_target
from browser_agent.verifier import verify_contract


def cand(**kw):
    base = dict(index=0, tag="input", type="text", id="", name="", role="", aria_label="",
                placeholder="", text="", href="", visible=True, x=0, y=0)
    base.update(kw)
    return ElementCandidate(**base)


def obs(cands, url="http://site/results", text="3 results for widget: Widget Pro", modal=False):
    return Observation(url=url, title="t", visible_text=text, candidates=cands, modal_present=modal)


# --- verifier three-state ---
def test_verifier_pass_when_conditions_met():
    c = BrowserTaskContract(task_id="t", natural_language_task="x", expected_outcome="x",
                            success_conditions=[SuccessCondition(type="text_visible", value="results for")])
    assert verify_contract(c, obs([])).status == "pass"


def test_verifier_fail_on_forbidden():
    c = BrowserTaskContract(task_id="t", natural_language_task="x", expected_outcome="x",
                            success_conditions=[SuccessCondition(type="text_visible", value="results for")],
                            forbidden_conditions=[ForbiddenCondition(type="error_text_visible", value="no results")])
    assert verify_contract(c, obs([], text="no results found")).status == "fail"


def test_verifier_unknown_when_unobservable():
    c = BrowserTaskContract(task_id="t", natural_language_task="x", expected_outcome="x",
                            success_conditions=[SuccessCondition(type="screenshot_region_changed", value="x")])
    assert verify_contract(c, obs([])).status == "unknown"


# --- FIX-1: open-ended tasks (zero success conditions) ---
def test_open_ended_empty_conditions_is_unknown_with_human_review_note():
    """FIX-1 前後對照。修復前:空 success_conditions 根本到不了 verifier ——
    contract schema (min_length=1) 先炸 ValidationError,run 變 ERROR,懲罰了
    誠實回報「無可驗證條件」的 preflight。修復後:空條件合法,verifier 的
    結構性守門回 unknown,missing_evidence 明講需要人工檢視 trace。"""
    c = BrowserTaskContract(task_id="t", natural_language_task="逛逛有什麼有趣的",
                            expected_outcome="open-ended", success_conditions=[])
    r = verify_contract(c, obs([]))
    assert r.status == "unknown"
    assert "open-ended" in r.reason
    assert any("human review" in m for m in r.missing_evidence)


def test_open_ended_forbidden_satisfied_is_still_unknown_not_vacuous_pass():
    # With zero success conditions, combine_checks over forbidden-only checks
    # would report `pass` when nothing forbidden happened — a vacuous pass.
    # The verifier-level gate must keep the verdict at unknown.
    c = BrowserTaskContract(task_id="t", natural_language_task="逛逛", expected_outcome="x",
                            success_conditions=[],
                            forbidden_conditions=[ForbiddenCondition(
                                type="error_text_visible", value="internal server error")])
    assert verify_contract(c, obs([], text="a perfectly fine page")).status == "unknown"


def test_open_ended_forbidden_violation_still_fails():
    # unknown-by-default must NOT swallow a forbidden violation: an open-ended
    # task that lands on a login wall / error page still fails honestly.
    c = BrowserTaskContract(task_id="t", natural_language_task="逛逛", expected_outcome="x",
                            success_conditions=[],
                            forbidden_conditions=[ForbiddenCondition(
                                type="error_text_visible", value="no results")])
    r = verify_contract(c, obs([], text="no results found"))
    assert r.status == "fail"
    assert "forbidden" in r.reason


def _dl_contract(value):
    return BrowserTaskContract(task_id="t", natural_language_task="download it",
                               expected_outcome="file", success_conditions=[
                                   SuccessCondition(type="download_exists", value=value)])


def test_download_verified_by_file_content_not_path(tmp_path):
    # The saved file must actually contain the asked-for section — a wrong page
    # written to disk (right name, wrong bytes) must NOT pass. This is the
    # "you said success but never checked the contents" fix.
    good = tmp_path / "intc-10k.htm"
    good.write_text("<h1>Item 1A. Risk Factors</h1>" + "x" * 1000, encoding="utf-8")
    wrong = tmp_path / "risk-factors.htm"   # right-looking NAME, wrong CONTENT
    wrong.write_text("<h1>Are you a robot?</h1>" + "x" * 1000, encoding="utf-8")

    c = _dl_contract("Risk Factors")
    assert verify_contract(c, obs([]), {"__download__": str(good)}).status == "pass"
    assert verify_contract(c, obs([]), {"__download__": str(wrong)}).status == "fail"


def test_download_binary_with_filename_hit_is_unknown_not_pass(tmp_path):
    """FIX-2 (FG-BROWSER-002)。不可讀 binary bytes 無法證明也無法否證內容:
    檔名命中 needle 只是弱訊號 → unknown(修復前:檔名命中單獨就 pass);
    檔名也不中 → fail。"""
    blob = bytes(range(256)) * 20
    hit = tmp_path / "risk factors.pdf"
    hit.write_bytes(blob)
    miss = tmp_path / "blob.pdf"
    miss.write_bytes(blob)
    c = _dl_contract("risk factors")
    assert verify_contract(c, obs([]), {"__download__": str(hit)}).status == "unknown"
    assert verify_contract(c, obs([]), {"__download__": str(miss)}).status == "fail"


def test_text_visible_ignores_query_echo_lines():
    """FIX-2 (FG-BROWSER-003)。修復前:'0 results for "teleporter"' 的查詢
    回顯就能滿足 text_visible "Teleporter" → 假 pass。修復後:zero-result
    回顯行被遮罩,needle 僅出現在回顯行內 → fail;出現在回顯行外照常 pass。"""
    c = BrowserTaskContract(task_id="t", natural_language_task="x", expected_outcome="x",
                            success_conditions=[SuccessCondition(type="text_visible", value="Teleporter")])
    # needle only inside the zero-results echo -> not evidence
    assert verify_contract(c, obs([], text='0 results for "teleporter"')).status == "fail"
    assert verify_contract(c, obs([], text='找不到 "Teleporter" 的結果')).status == "fail"
    # needle outside the echo line -> real evidence, still passes
    assert verify_contract(
        c, obs([], text='0 results for "teleporter"\nRelated: Teleporter Mini')).status == "pass"
    # a NON-zero results echo is not masked (legit pages keep passing)
    assert verify_contract(
        c, obs([], text='2 results for "teleporter": Teleporter Mini')).status == "pass"


def test_download_exists_states(tmp_path):
    real = tmp_path / "doc.htm"
    real.write_text("y" * 2000, encoding="utf-8")
    tiny = tmp_path / "stub.htm"
    tiny.write_text("no", encoding="utf-8")
    # no download observed -> unknown, not a disguised pass
    assert verify_contract(_dl_contract(""), obs([]), {}).status == "unknown"
    # a real file with no required content -> pass
    assert verify_contract(_dl_contract(""), obs([]), {"__download__": str(real)}).status == "pass"
    # a trivially small file is not a real document -> fail
    assert verify_contract(_dl_contract(""), obs([]), {"__download__": str(tiny)}).status == "fail"


# --- repair ---
def test_repair_finds_search_box_by_aria_label():
    cands = [cand(tag="input", name="query", aria_label="Search products", placeholder="Search products")]
    rr = repair_target("search_box", obs(cands), want_value="widget")
    assert rr.ok
    assert "query" in rr.durable_selector          # durable selector for memory
    assert rr.new_target.selector.startswith("[data-aid=")  # exact handle for the action


def test_repair_avoids_decoy_button():
    cands = [
        cand(tag="button", id="fake-search", type="button", text="Search"),  # decoy
        cand(tag="button", id="go", type="submit", aria_label="Search", text="🔍"),  # real
    ]
    rr = repair_target("submit_button", obs(cands))
    assert rr.ok
    assert "go" in rr.durable_selector
    assert "fake-search" not in rr.durable_selector


def test_repair_skips_invisible_and_returns_reasons():
    cands = [cand(tag="input", aria_label="Search", visible=False)]
    rr = repair_target("search_box", obs(cands))
    assert not rr.ok
    assert rr.considered  # explainable even on failure


# --- diagnosis ---
def test_diagnose_selector_not_found():
    out = ActionOutcome(ok=False, action_type="fill", matched_count=0, error="selector matched no element")
    d = diagnose_failure(out, obs([]), url_changed=False)
    assert d.failure_type == "selector_not_found" and d.repairable


def test_diagnose_click_no_effect():
    out = ActionOutcome(ok=True, action_type="click", matched_count=1)
    d = diagnose_failure(out, obs([]), url_changed=False)
    assert d.failure_type == "click_no_effect"


def test_diagnose_silent_failure_is_not_repairable():
    out = ActionOutcome(ok=False, action_type="fill", matched_count=1, error="weird")
    d = diagnose_failure(out, obs([]), url_changed=False)
    assert d.failure_type == "silent_failure_risk" and not d.repairable


def test_diagnose_empty_result():
    out = ActionOutcome(ok=True, action_type="click", matched_count=1)
    d = diagnose_failure(out, obs([], text="0 results for zzz", url="http://site/results"), url_changed=True)
    assert d.failure_type == "empty_result"


def test_diagnose_wrong_page():
    out = ActionOutcome(ok=True, action_type="click", matched_count=1)
    d = diagnose_failure(out, obs([], url="http://site/error"), url_changed=True,
                         expected_url_fragment="/results")
    assert d.failure_type == "wrong_page"


# --- capability guard (honest boundary, code-enforced) ---
def test_screen_task_refuses_login_and_purchase():
    assert not screen_task("Log in to my bank account").allowed
    assert not screen_task("Buy the first product and checkout").allowed
    assert screen_task("Search for widgets and read the results").allowed


def test_screen_task_is_blind_to_non_english_intents():
    # Known, deliberately unfixed hole (TODO V-14): the intent patterns are
    # English keyword matches, so the same refusals sail through in Chinese on
    # a Chinese-language UI. Locked as a test so the boundary's real shape is
    # measured rather than asserted in prose — fail-open, not "code-enforced".
    for zh in ("登入我的銀行帳戶", "購買第一個商品並結帳", "幫我付款下單"):
        assert screen_task(zh).allowed          # NOT refused — this is the hole
    assert not screen_task("Log in to my bank account").allowed


def test_screen_action_refuses_password_and_checkout():
    pw = FillAction(target=ElementTarget(selector="#pw"), value="hunter2 password")
    assert not screen_action(pw).allowed
    buy = ClickAction(target=ElementTarget(selector="#place-order", description="checkout"))
    assert not screen_action(buy).allowed
    ok = FillAction(target=ElementTarget(selector="#q"), value="widget")
    assert screen_action(ok).allowed


# --- integration: the killer demo flow ---
@pytest.mark.integration
def test_killer_demo_v1_pass_v2_repairs_and_passes(tmp_path):
    pytest.importorskip("playwright.sync_api")
    from pathlib import Path

    from playwright.sync_api import sync_playwright

    from browser_agent.agent import BrowserAgent
    from browser_agent.memory_store import MemoryStore
    import tools.browser_killer_demo as demo  # noqa: E402

    root = Path(__file__).resolve().parents[1]
    if not (root / "data" / "mock_sites" / "v2" / "index.html").exists():
        pytest.skip("mock sites not present")
    mem = MemoryStore(tmp_path / "mem.json")
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        page = b.new_page()
        page.goto(demo.site_uri("v1"))
        steps, contract = demo.search_task("v1")
        r1 = BrowserAgent(page, mem, "mockshop", "search").run("v1", steps, contract)
        page.goto(demo.site_uri("v2"))
        steps2, contract2 = demo.search_task("v2")
        r2 = BrowserAgent(page, mem, "mockshop", "search").run("v2", steps2, contract2)
        b.close()
    assert r1.status == "pass"
    assert r2.status == "pass"
    assert r2.repairs >= 2  # both selectors drifted + modal
