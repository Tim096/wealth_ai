"""P1-1 Online-Mind2Web subset import + naive baseline.

Pure-logic tests cover the importer (level rule, exclusion filter,
deterministic stratified sampling, contract-validated conversion, provenance)
and the naive baseline's keyword/contract/summary logic — no network, no
browser. The committed subset artifact is schema-checked as data. One
integration test drives the naive agent against the local mock sites and locks
the value-add delta: trivial pass on the clean v1, honest fail on the drifted
v2 that our real agent self-repairs through."""

import json
from pathlib import Path

import pytest

from browser_core import BrowserTaskContract, SuccessCondition
import tools.import_mind2web as im
import tools.naive_baseline as nb

ROOT = Path(__file__).resolve().parents[1]
SUBSET = ROOT / "data" / "browser_eval" / "external" / "mind2web_subset.json"


def raw(tid="a" * 32, task="Find the Widget Pro on MockShop", site="https://example.com/",
        ref=4, **kw):
    return {"task_id": tid, "confirmed_task": task, "website": site,
            "reference_length": ref, **kw}


# --- level rule (paper §2.2) ---
def test_level_rule_thresholds():
    assert im.level_for(1) == "easy"
    assert im.level_for(5) == "easy"
    assert im.level_for(6) == "medium"
    assert im.level_for(10) == "medium"
    assert im.level_for(11) == "hard"


def test_normalize_prefers_official_level_over_derived():
    assert im.normalize(raw(ref=4, level="Medium"))["level"] == "medium"
    assert im.normalize(raw(ref=12))["level"] == "hard"


# --- exclusion filter ---
def test_domain_of_strips_subdomains():
    assert im.domain_of("https://careers.walmart.com/jobs") == "walmart.com"
    assert im.domain_of("https://www.gov.uk/") == "gov.uk"
    assert im.domain_of("https://store.steampowered.com/") == "steampowered.com"


def test_exclude_blocked_domain_and_login_task_text():
    assert "amazon.com" in im.exclude_reason(im.normalize(raw(site="https://www.amazon.com/")))
    assert "account" in im.exclude_reason(
        im.normalize(raw(task="Sign in and check my account balance")))
    assert im.exclude_reason(im.normalize(raw())) is None


# --- stratified sampling: deterministic, counted, domain-capped ---
def _pool():
    tasks = []
    for i in range(30):
        tasks.append(im.normalize(raw(tid=f"{i:032x}", ref=3, site=f"https://e{i}.com/")))
        tasks.append(im.normalize(raw(tid=f"{i + 100:032x}", ref=8, site=f"https://m{i}.com/")))
        tasks.append(im.normalize(raw(tid=f"{i + 200:032x}", ref=12, site=f"https://h{i}.com/")))
    return tasks


def test_stratified_sample_counts_and_determinism():
    counts = {"easy": 4, "medium": 3, "hard": 2}
    a = im.stratified_sample(_pool(), counts)
    b = im.stratified_sample(list(reversed(_pool())), counts)  # order-insensitive
    assert [t["source_task_id"] for t in a] == [t["source_task_id"] for t in b]
    levels = [t["level"] for t in a]
    assert levels.count("easy") == 4 and levels.count("medium") == 3 and levels.count("hard") == 2


def test_stratified_sample_respects_per_domain_cap():
    pool = [im.normalize(raw(tid=f"{i:032x}", ref=3, site="https://same.com/"))
            for i in range(10)]
    picked = im.stratified_sample(pool, {"easy": 5}, per_domain_cap=2)
    assert len(picked) == 2  # cap binds before the requested count


# --- conversion: contract-validated, attributed, maintenance fields ---
def test_to_subset_entry_fields_and_contract_roundtrip():
    e = im.to_subset_entry(im.normalize(raw(ref=8)), added="2026-07-10")
    assert e["task_id"] == "m2w-" + "a" * 12
    assert e["layer"] == "external_live_tasks"
    assert e["source_task_id"] == "a" * 32
    assert "arXiv:2504.01382" in e["attribution"]
    assert e["difficulty"] == "medium"          # feeds resolve_max_steps (P1-15)
    assert e["status"] == "active" and e["replaced_by"] is None and e["update_history"] == []
    assert e["success_conditions"], "a Latin proper noun must derive a condition"
    BrowserTaskContract(task_id=e["task_id"], natural_language_task=e["natural_language_task"],
                        expected_outcome=e["expected_outcome"],
                        success_conditions=[SuccessCondition(**c)
                                            for c in e["success_conditions"]])


def test_to_subset_entry_open_ended_zero_conditions_is_legal():
    e = im.to_subset_entry(im.normalize(raw(task="逛逛看有什麼")), added="2026-07-10")
    assert e["success_conditions"] == []        # honest unknown at eval time, not a crash


def test_build_subset_provenance_and_unique_ids():
    rows = [raw(tid=f"{i:x}".ljust(32, "0"), ref=r, site=f"https://s{i}.com/")
            for i, r in enumerate([3, 4, 8, 9, 12, 13])]
    rows.append(raw(tid="f" * 32, site="https://www.amazon.com/"))  # must be excluded
    subset = im.build_subset(rows, {"easy": 2, "medium": 2, "hard": 2},
                             fetched_from="unit-test", added="2026-07-10")
    src = subset["source"]
    assert src["license"] == "CC-BY-4.0" and src["dataset"] == "osunlp/Online-Mind2Web"
    assert src["sampling"]["excluded_count"] == 1
    assert src["total_upstream_tasks"] == 7
    ids = [t["task_id"] for t in subset["tasks"]]
    assert len(ids) == len(set(ids)) == 6


# --- the committed artifact is valid data ---
def test_committed_subset_schema_attribution_and_no_blocked_domains():
    subset = json.loads(SUBSET.read_text(encoding="utf-8"))
    assert subset["source"]["license"] == "CC-BY-4.0"
    tasks = subset["tasks"]
    assert len(tasks) == sum(subset["source"]["sampling"]["counts"].values())
    for t in tasks:
        assert "arXiv:2504.01382" in t["attribution"]
        assert t["layer"] == "external_live_tasks"
        assert t["difficulty"] == im.level_for(t["reference_length"])
        assert im.domain_of(t["website"]) not in im.EXCLUDED_DOMAINS
        assert t["status"] == "active" and "update_history" in t
        BrowserTaskContract(task_id=t["task_id"],
                            natural_language_task=t["natural_language_task"],
                            expected_outcome=t["expected_outcome"],
                            success_conditions=[SuccessCondition(**c)
                                                for c in t["success_conditions"]])


# --- naive baseline: pure logic ---
def test_keywords_quoted_phrase_wins_and_stopwords_drop():
    assert nb.keywords("Search MockShop for 'widget' and see results") == ["widget"]
    kws = nb.keywords("Find the cheapest apartment in Detroit for a student")
    assert "the" not in kws and "Detroit" in kws and len(kws) <= 4


def test_contract_from_entry_and_summarize():
    entry = {"task_id": "t", "natural_language_task": "x",
             "success_conditions": [{"type": "text_visible", "value": "Widget"}]}
    c = nb.contract_from_entry(entry)
    assert c.success_conditions[0].value == "Widget"
    s = nb.summarize([{"status": "pass"}, {"status": "fail"}, {"status": "unknown"},
                      {"status": "pass"}])
    assert s["trivial_pass_rate"] == 0.5 and s["unknown"] == 1
    assert "verify_contract" in s["judge"]


# --- integration: naive passes clean v1, honestly fails drifted v2 ---
def _mock_entry(site: str) -> dict:
    return {
        "task_id": f"naive-{site}",
        "natural_language_task": "Search MockShop for 'widget' and see the results",
        "website": (ROOT / "data" / "mock_sites" / site / "index.html").resolve().as_uri(),
        "success_conditions": [{"type": "text_visible", "value": "results for"},
                               {"type": "text_visible", "value": "Widget"}],
    }


@pytest.mark.integration
def test_naive_baseline_v1_trivial_pass_v2_drift_fail():
    """The value-add delta P1-1 exists to measure: the shortcut agent passes
    the clean site (so the harness is not rigged against it) but fails the
    drifted site whose cookie modal / renamed controls our real agent
    self-repairs through. No repair => the drift is fatal to the baseline."""
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    if not (ROOT / "data" / "mock_sites" / "v2" / "index.html").exists():
        pytest.skip("mock sites not present")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        clean = nb.run_naive(page, _mock_entry("v1"))
        drift = nb.run_naive(page, _mock_entry("v2"))
        browser.close()
    assert clean["status"] == "pass", clean
    assert drift["status"] == "fail", drift
    assert not any("repair" in a for a in clean["actions"] + drift["actions"])
