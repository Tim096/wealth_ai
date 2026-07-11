"""Fourth/fifth arbitration engines (P0-7) — sec_core.engines.

edgar_crawler_vote: GPLv3 upstream driven as an UNMODIFIED subprocess on a
local checkout (never vendored/imported); datamule_vote: MIT pip dependency.
Mapping logic is unit-tested without the engines; smoke tests run offline on
the synthetic alpha fixture and skip when the engine is not provisioned.
"""

from pathlib import Path

import pytest

from sec_core.engines.datamule_vote import extract_items_datamule, std_title_to_code
from sec_core.engines.edgar_crawler_vote import (
    PINNED_COMMIT,
    ensure_checkout,
    extract_items_edgar_crawler,
    map_output_items,
)
from sec_core.headings import VALID_CODES

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "data" / "sec_eval" / "fixtures"


@pytest.fixture(scope="module")
def alpha_raw() -> str:
    return (FIXTURES / "alpha_10k.html").read_text(encoding="utf-8")


# --- datamule (fifth vote) ----------------------------------------------------

def test_std_title_maps_items_and_rejects_parts():
    assert std_title_to_code("item1a") == "1A"
    assert std_title_to_code("item9c") == "9C"
    assert std_title_to_code("item16") == "16"
    assert std_title_to_code("ITEM7A") == "7A"
    assert std_title_to_code("parti") is None
    assert std_title_to_code("item99") is None  # not a valid 10-K item
    assert std_title_to_code("") is None


def test_datamule_offline_extraction_on_alpha(alpha_raw):
    items = extract_items_datamule(alpha_raw)
    if items is None:  # datamule not installed: unavailability, not failure
        pytest.skip("datamule not installed")
    assert set(items) <= set(VALID_CODES)
    assert "1A" in items and "risk" in items["1A"].lower()
    assert all(v.strip() for v in items.values())


def test_datamule_garbage_input_degrades_to_none_not_raise():
    assert extract_items_datamule("") in (None,)  # never an exception


# --- edgar-crawler (fourth vote, arms-length subprocess) -----------------------

def test_map_output_items_filters_metadata_signature_and_empties():
    json_content = {
        "cik": "0", "company": "x", "SIGNATURE": "s",
        "item_1": "Business text", "item_1A": "Risk factors",
        "item_16": "   ",            # empty -> dropped
        "item_99": "not a 10-K item",  # invalid code -> dropped
    }
    items = map_output_items(json_content)
    assert items == {"1": "Business text", "1A": "Risk factors"}


def test_map_output_items_all_empty_is_none():
    assert map_output_items({"cik": "0", "item_1": " "}) is None


def test_missing_checkout_is_engine_unavailable(tmp_path):
    assert extract_items_edgar_crawler("<html></html>",
                                       checkout=tmp_path / "nope") is None


def test_ensure_checkout_without_fetch_never_clones(tmp_path, monkeypatch):
    monkeypatch.setenv("EDGAR_CRAWLER_HOME", str(tmp_path / "absent"))
    assert ensure_checkout(fetch=False) is None


def test_pinned_commit_is_the_gplv3_verified_revision():
    # LICENSE was re-verified GPLv3 at exactly this commit (docs/ATTRIBUTION.md);
    # a pin change requires re-running the license check.
    assert PINNED_COMMIT == "84a8d0c5dd7dd6769526e5ccec534c4e0880d56f"


@pytest.mark.skipif(ensure_checkout() is None,
                    reason="edgar-crawler checkout not provisioned "
                           "(tools/triangulate.py clones it on first run)")
def test_edgar_crawler_subprocess_extraction_on_alpha(alpha_raw):
    items = extract_items_edgar_crawler(alpha_raw)
    assert items is not None
    assert set(items) <= set(VALID_CODES)
    assert "1A" in items and "risk" in items["1A"].lower()
