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
    assert "Management" in d["text"][:120]
    assert d["sha256"] and d["offsets"][1] > d["offsets"][0]


def test_agent_submit_queues_and_derives_success():
    d = tc.agent_submit("搜尋 'widget' 然後看結果", "about:blank", "")
    assert d["ok"] and d["run_id"] in tc._RUNS
    assert d["success"] == ["text_visible:widget"]
    st = tc._RUNS[d["run_id"]]
    assert st["status"] == "queued"
    # drain the job so a later-started worker never actually runs it
    tc._JOBS.get_nowait()


def test_page_has_both_panels():
    html = (ROOT / "apps" / "web" / "test-center" / "index.html").read_text(encoding="utf-8")
    assert "tab-agent" in html and "tab-sec" in html
    assert "/api/agent/run" in html and "/api/sec/extract" in html and "/api/sec/upload" in html
