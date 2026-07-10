"""Web test-center handlers (no network, no GUI): the SEC upload path, the
item-text endpoint contract, and the page asset itself."""

from pathlib import Path

import tools.test_center as tc

ROOT = Path(__file__).resolve().parents[1]


def test_sec_upload_extracts_fixture():
    raw = (ROOT / "data" / "sec_eval" / "fixtures" / "alpha_10k.html").read_text(encoding="utf-8")
    d = tc.sec_upload(raw, "alpha_10k.html")
    assert d["ok"] and d["meta"]["filing_class"] == "standard"
    by = {i["code"]: i for i in d["items"]}
    assert by["1"]["status"] == "pass"
    assert by["7"]["chars"] > 1000


def test_sec_item_text_after_upload():
    raw = (ROOT / "data" / "sec_eval" / "fixtures" / "alpha_10k.html").read_text(encoding="utf-8")
    tc.sec_upload(raw, "alpha_10k.html")
    d = tc.sec_item_text("7")
    assert d["ok"] and d["status"] == "pass"
    assert d["sha256"] and d["offsets"][1] > d["offsets"][0]


def test_upload_exposes_gaps_and_coverage():
    raw = (ROOT / "data" / "sec_eval" / "fixtures" / "alpha_10k.html").read_text(encoding="utf-8")
    d = tc.sec_upload(raw, "alpha_10k.html")
    assert "gaps" in d and 0.0 < d["meta"]["coverage"] <= 1.0
    for g in d["gaps"]:                       # gap rows are readable, source-exact
        assert g["code"].startswith("gap:")
        assert tc.sec_item_text(g["code"])["ok"]


def test_full_document_find_returns_ordered_hits():
    raw = (ROOT / "data" / "sec_eval" / "fixtures" / "alpha_10k.html").read_text(encoding="utf-8")
    tc.sec_upload(raw, "alpha_10k.html")
    d = tc.sec_item_text("1")           # a word that certainly appears in Item 1
    word = next(w for w in d["text"].split() if len(w) > 6 and w.isalpha())
    r = tc.sec_find(word)
    assert r["ok"] and r["found"] and r["count"] >= 1
    assert len(r["hits"]) == min(r["count"], 500)
    # every hit names a real region (item or gap) and a within-region index
    assert all(h["code"] and h["k"] >= 0 for h in r["hits"])


def test_sec_start_url_only_fires_for_ticker_filings():
    u = tc._sec_start_url("請幫我下載 INTC 最新的 10-K")
    assert "CIK=INTC" in u and "browse-edgar" in u
    assert tc._sec_start_url("看 finlab 訂閱價格") == ""
    assert tc._sec_start_url("搜尋 33號遠征隊 播放") == ""


def test_agent_submit_explicit_success_used_verbatim():
    d = tc.agent_submit("搜尋 'widget' 然後看結果", "about:blank", "widget")
    assert d["ok"] and d["run_id"] in tc._RUNS
    assert d["success"] == ["text_visible:widget"]
    st = tc._RUNS[d["run_id"]]
    assert st["status"] == "queued"
    tc._JOBS.get_nowait()


def test_agent_submit_blank_defers_planning_to_worker():
    # No hard-fail on prose any more: a blank start/success is queued for the
    # worker's LLM preflight (conds sentinel is None), never rejected.
    d = tc.agent_submit("幫我看一下他訂閱價格不同怎麼算", "", "")
    assert d["ok"] and d["run_id"] in tc._RUNS
    assert d["success"] == ["auto-plan"]
    run_id, task, url, conds = tc._JOBS.get_nowait()
    assert run_id == d["run_id"] and url == "" and conds is None


def test_page_has_both_panels():
    html = (ROOT / "apps" / "web" / "test-center" / "index.html").read_text(encoding="utf-8")
    assert "tab-agent" in html and "tab-sec" in html
    assert "/api/agent/run" in html and "/api/sec/extract" in html and "/api/sec/upload" in html
