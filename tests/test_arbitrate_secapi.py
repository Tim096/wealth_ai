"""sec-api.io arbitration protocol (P0-7b) — tools/arbitrate_secapi.py.

Everything network-shaped is exercised through injected fetch_fn: the tests
must be runnable forever without an account, without spending any of the
100-lifetime-call free tier, and without sec-api payload text on disk beyond
the gitignored cache dir.
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from arbitrate_secapi import (  # noqa: E402
    SUPPORTED_ITEMS,
    adjudicate,
    cache_path,
    get_secapi_text,
    load_targets,
    render_readme,
)

TRIANGULATION = {
    "records": [
        {"ticker": "AAPL", "cik": 320193, "accession": "0000320193-25-000079",
         "doc_url": "https://www.sec.gov/Archives/x/aapl.htm",
         "items": {
             "11": {"verdict": "disagree",
                    "votes": {"edgartools": {"verdict": "disagree",
                                             "detail": "boundary mismatch"}}},
             "16": {"verdict": "disagree",
                    "votes": {"edgartools": {"verdict": "disagree",
                                             "detail": "content mismatch"}}},
             "1": {"verdict": "agree",
                   "votes": {"edgartools": {"verdict": "agree", "detail": "ok"}}},
             # outvoted: aggregate agree, but datamule dissented -> spot-check tier
             "7A": {"verdict": "agree",
                    "votes": {"edgartools": {"verdict": "agree", "detail": "ok"},
                              "datamule": {"verdict": "disagree",
                                           "detail": "content mismatch"}}},
         }},
        # pre-P0-7 single-engine schema (no votes/doc_url) must still load
        {"ticker": "XOM", "cik": 34088, "accession": "0000034088-25-000001",
         "items": {"7": {"verdict": "disagree", "detail": "content mismatch"}}},
    ]
}


def test_load_targets_tiers_disagrees_before_outvoted():
    targets = load_targets(TRIANGULATION)
    assert [(t["ticker"], t["item"], t["tier"]) for t in targets] == [
        ("AAPL", "11", "disagree"), ("AAPL", "16", "disagree"),
        ("XOM", "7", "disagree"), ("AAPL", "7A", "outvoted")]
    by_item = {t["item"]: t for t in targets}
    assert by_item["11"]["supported"] is True
    assert by_item["16"]["supported"] is False  # sec-api lacks item 16
    assert by_item["7"]["doc_url"] is None      # old schema tolerated
    assert by_item["11"]["detail"] == "boundary mismatch"
    assert by_item["7A"]["dissenting"] == ["datamule"]
    # plain agreements without dissent are never arbitration targets
    assert "1" not in by_item


def test_secapi_item_coverage_gap_is_exactly_1c_9c_16():
    from sec_core.headings import VALID_CODES
    assert set(VALID_CODES) - SUPPORTED_ITEMS == {"1C", "9C", "16"}


# --- cache-first + budget guard (100 lifetime calls) ---------------------------

def _target(item="11", accession="0000320193-25-000079"):
    return {"ticker": "AAPL", "accession": accession, "item": item,
            "doc_url": "https://www.sec.gov/Archives/x/aapl.htm", "supported": True}


def test_fetch_writes_cache_immediately_and_spends_budget(tmp_path):
    budget = {"calls_made": 0, "max_calls": 1}
    text, status = get_secapi_text(_target(), "k", tmp_path, budget,
                                   fetch_fn=lambda url, item, key: "ITEM TEXT")
    assert (text, status) == ("ITEM TEXT", "fetched")
    assert budget["calls_made"] == 1
    cached = json.loads(cache_path(tmp_path, "0000320193-25-000079", "11")
                        .read_text(encoding="utf-8"))
    assert cached["text"] == "ITEM TEXT" and cached["item"] == "11"


def test_cache_hit_never_calls_the_api(tmp_path):
    def _forbidden(url, item, key):
        raise AssertionError("API called despite cache hit")
    budget = {"calls_made": 0, "max_calls": 5}
    get_secapi_text(_target(), "k", tmp_path, budget,
                    fetch_fn=lambda url, item, key: "FIRST")
    text, status = get_secapi_text(_target(), "k", tmp_path, budget,
                                   fetch_fn=_forbidden)
    assert (text, status) == ("FIRST", "cached")
    assert budget["calls_made"] == 1


def test_budget_exhausted_blocks_the_call(tmp_path):
    def _forbidden(url, item, key):
        raise AssertionError("API called beyond --max-calls")
    budget = {"calls_made": 0, "max_calls": 0}  # default: plan only
    text, status = get_secapi_text(_target(), "k", tmp_path, budget,
                                   fetch_fn=_forbidden)
    assert text is None and status == "budget_exhausted"


def test_missing_doc_url_is_reported_not_fetched(tmp_path):
    t = _target()
    t["doc_url"] = None
    text, status = get_secapi_text(t, "k", tmp_path,
                                   {"calls_made": 0, "max_calls": 5})
    assert text is None and status == "no_doc_url"


def test_fetch_error_is_recorded_without_spending_budget(tmp_path):
    def _boom(url, item, key):
        raise RuntimeError("503")
    budget = {"calls_made": 0, "max_calls": 5}
    text, status = get_secapi_text(_target(), "k", tmp_path, budget, fetch_fn=_boom)
    assert text is None and status.startswith("fetch_error")
    assert budget["calls_made"] == 0
    assert not cache_path(tmp_path, "0000320193-25-000079", "11").is_file()


# --- adjudication ---------------------------------------------------------------

OURS = ("Executive compensation is described in the proxy statement and "
        "incorporated by reference into this report for all named officers. " * 20)
THEIRS = ("Completely different narrative about mine safety citations and "
          "environmental remediation liabilities across mining segments. " * 20)


def test_ruling_ours_when_secapi_matches_our_span():
    v = adjudicate("11", OURS, OURS, {"edgartools": THEIRS})
    assert v["ruling"] == "ours"
    assert v["secapi_vs_ours"] == "agree"


def test_ruling_engine_when_secapi_matches_engine_span():
    v = adjudicate("11", THEIRS, OURS, {"edgartools": THEIRS})
    assert v["ruling"] == "engine"


def test_ruling_neither_when_secapi_matches_no_side():
    other = ("Quarterly dividend policy and share repurchase authorizations "
             "approved by the board of directors during fiscal 2025. " * 20)
    assert adjudicate("11", other, OURS, {"edgartools": THEIRS})["ruling"] == "neither"


def test_table_sentinels_are_masked_before_comparison():
    secapi = OURS.replace(". ", ". ##TABLE_START revenue 1 2 3 ##TABLE_END ")
    assert adjudicate("11", secapi, OURS, {})["secapi_vs_ours"] == "agree"


# --- state doc -------------------------------------------------------------------

def test_readme_lists_items_budget_and_run_command(tmp_path):
    targets = load_targets(TRIANGULATION)
    doc = render_readme(targets, tmp_path)
    assert "100" in doc and "--max-calls" in doc
    assert ("| AAPL | 0000320193-25-000079 | 11 | disagree | edgartools | yes "
            "| pending (needs 1 call) |") in doc
    assert "no (sec-api lacks item)" in doc      # item 16 unadjudicable
    assert "SECAPI_KEY" in doc


def test_readme_reflects_cache_and_rulings(tmp_path):
    targets = load_targets(TRIANGULATION)
    get_secapi_text(_target(), "k", tmp_path, {"calls_made": 0, "max_calls": 1},
                    fetch_fn=lambda url, item, key: "TEXT")
    doc = render_readme(targets, tmp_path,
                        results={"0000320193-25-000079:11":
                                 {"status": "cached", "ruling": "ours"}},
                        calls_made_this_run=0)
    assert "ruling=ours" in doc
