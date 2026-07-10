"""Mutation-site matrix + degradation-curve tests (T1-2).

Pure logic (generator determinism / matrix shape / perturbation markers /
aggregation math / checkpoint-through-verifier) runs without a browser; one
integration test drives four representative cells end-to-end headless.
"""

import sys
from pathlib import Path

import pytest

from browser_agent.observer import ElementCandidate, Observation
from browser_agent.repair import repair_target
from browser_agent.verifier import verify_contract

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import degradation_curve as dc  # noqa: E402
import gen_mutation_sites as gen  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def cand(**kw):
    base = dict(index=0, tag="input", type="text", id="", name="", role="", aria_label="",
                placeholder="", text="", href="", visible=True, x=0, y=0)
    base.update(kw)
    return ElementCandidate(**base)


def obs(cands=(), text=""):
    return Observation(url="file:///mock", title="t", visible_text=text,
                       candidates=list(cands), modal_present=False)


# --- matrix shape & determinism ---
def test_matrix_is_clean_plus_three_axes_by_three_levels():
    assert set(gen.CELLS) == {"clean"} | {
        f"{axis}-{lv}" for axis in ("perception", "action", "execution")
        for lv in ("light", "medium", "heavy")}
    assert gen.CELLS["clean"]["level"] == 0
    for axis in ("perception", "action", "execution"):
        levels = [gen.CELLS[f"{axis}-{lv}"]["level"] for lv in ("light", "medium", "heavy")]
        assert levels == [1, 2, 3]


def test_render_is_deterministic():
    for cid in gen.CELLS:
        assert gen.render_site(cid) == gen.render_site(cid)


def test_committed_sites_match_generator():
    # drift lock: the committed HTML must be exactly what the generator renders;
    # if this fails, rerun tools/gen_mutation_sites.py and recommit.
    for cid in gen.CELLS:
        committed = (gen.OUT / cid / "index.html").read_text(encoding="utf-8")
        assert committed == gen.render_site(cid), f"cell {cid} drifted from generator"


def test_no_randomness_in_any_cell():
    for cid in gen.CELLS:
        assert "Math.random" not in gen.render_site(cid)


def test_heldout_discipline_generator_never_references_heldout_site():
    src = (ROOT / "tools" / "gen_mutation_sites.py").read_text(encoding="utf-8")
    assert "v3" not in src


# --- perturbation markers per cell ---
def test_clean_keeps_v1_identities():
    html = gen.render_site("clean")
    assert 'id="search-box"' in html and 'id="search-btn"' in html
    assert "const FAIL_FIRST = false" in html and "const DELAY_MS = 0" in html


def test_perception_light_renames_ids_but_keeps_semantics():
    html = gen.render_site("perception-light")
    assert 'id="search-box"' not in html and 'id="search-btn"' not in html
    assert 'aria-label="Search products"' in html


def test_perception_medium_has_decoy_and_icon_button():
    html = gen.render_site("perception-medium")
    assert 'id="fake-search"' in html
    assert "🔍" in html


def test_perception_heavy_has_modal_bait_and_div_button():
    html = gen.render_site("perception-heavy")
    assert 'class="cookie-modal"' in html
    assert 'id="promo"' in html                      # bait field
    assert '<div role="button"' in html              # submit is not a real button
    assert 'id="term-entry"' in html
    # the REAL field must carry no search semantics (that is the trap)
    real = next(line for line in html.splitlines() if "term-entry" in line)
    assert "aria-label" not in real and "Search products" not in real


def test_action_heavy_submit_is_not_enumerable():
    # a11y omission: no <button>, no role=button anywhere -> the observer's
    # candidate enumeration cannot contain the submit control
    html = gen.render_site("action-heavy")
    assert "<button" not in html
    assert 'role="button"' not in html
    assert "<span" in html and "onclick" in html


def test_execution_cells_keep_clean_identities_and_flags():
    for lv in ("light", "medium", "heavy"):
        html = gen.render_site(f"execution-{lv}")
        assert 'id="search-box"' in html and 'id="search-btn"' in html
        assert "const DELAY_MS = 250" in html
    assert "const FAIL_FIRST = true" in gen.render_site("execution-heavy")
    assert "const SWAP_BUTTON_ON_INPUT = true" in gen.render_site("execution-medium")
    assert "const SWAP_BUTTON_ON_INPUT = false" in gen.render_site("execution-light")


# --- checkpoint goes through the real verifier, not a runner shortcut ---
def test_checkpoint_contract_verified_by_verify_contract():
    c = dc.checkpoint_contract("widget")
    assert verify_contract(c, obs(), {"search_box": "widget"}).status == "pass"
    assert verify_contract(c, obs(), {"search_box": ""}).status == "fail"
    assert verify_contract(c, obs(), {"search_box": "wrong"}).status == "fail"


# --- aggregation math (pure, no browser) ---
def _row(status="pass", checkpoint="pass", repairs=0, fault=False, recovered=False):
    return {"status": status, "checkpoint": checkpoint, "repairs": repairs,
            "fault_encountered": fault, "recovered": recovered}


def test_summarize_cell_clean_has_unmeasurable_recovery():
    s = dc.summarize_cell([_row(), _row()])
    assert s["success_rate"] == 1.0
    assert s["fault_encountered_rate"] == 0.0
    assert s["recovery_rate"] is None       # no fault observed -> not a fake 1.0


def test_summarize_cell_recovery_is_over_faulted_runs_only():
    rows = [_row(fault=True, repairs=2, recovered=True),
            _row(status="fail", fault=True, repairs=2),
            _row()]                          # fault-free run must not dilute recovery
    s = dc.summarize_cell(rows)
    assert s["success_rate"] == round(2 / 3, 3)
    assert s["fault_encountered_rate"] == round(2 / 3, 3)
    assert s["recovery_rate"] == 0.5
    assert s["avg_repairs"] == round(4 / 3, 2)


def test_summarize_cell_checkpoint_dissociates_from_success():
    s = dc.summarize_cell([_row(status="fail", checkpoint="pass", fault=True, repairs=1)])
    assert s["success_rate"] == 0.0 and s["checkpoint_rate"] == 1.0


def test_build_curves_shares_clean_as_intensity_zero_and_flags_monotonicity():
    summaries = {"clean": {"success_rate": 1.0, "checkpoint_rate": 1.0,
                           "recovery_rate": None, "avg_repairs": 0.0}}
    for axis in ("perception", "action", "execution"):
        for lv, sr in (("light", 1.0), ("medium", 0.5), ("heavy", 0.0)):
            summaries[f"{axis}-{lv}"] = {"success_rate": sr, "checkpoint_rate": 1.0,
                                         "recovery_rate": 0.5, "avg_repairs": 1.0}
    curves = dc.build_curves(summaries)
    for axis in ("perception", "action", "execution"):
        pts = curves[axis]["points"]
        assert [p["cell"] for p in pts] == ["clean", f"{axis}-light",
                                            f"{axis}-medium", f"{axis}-heavy"]
        assert [p["intensity"] for p in pts] == [0, 1, 2, 3]
        assert curves[axis]["monotone_non_increasing_success"] is True
    # a non-monotone axis must be flagged, not silently averaged away
    summaries["action-medium"]["success_rate"] = 0.0
    summaries["action-heavy"]["success_rate"] = 1.0
    assert dc.build_curves(summaries)["action"]["monotone_non_increasing_success"] is False


# --- surfaced weaknesses (measure-first: locked, deliberately unfixed) ---
def test_known_weakness_submit_repair_falls_back_to_input():
    # action-heavy family: when NO clickable submit candidate exists (a11y
    # omission), repair_target still "repairs" onto the search input (weak
    # word-match score) and the click on it silently does nothing. Locked so a
    # future repair fix flips this test and forces a curve re-run.
    only_input = [cand(tag="input", id="entry", aria_label="Search products")]
    rr = repair_target("submit_button", obs(only_input))
    assert rr.ok                               # <- the weakness: no honest "not found"
    assert "entry" in rr.durable_selector


def test_known_weakness_bait_field_wins_tie_by_dom_order():
    # perception-heavy family: an unlabeled real search field scores the same
    # as a visible bait field; the tie breaks by DOM order, so the bait field
    # (earlier in the DOM) wins and the query lands in the wrong field.
    bait = cand(index=0, tag="input", id="promo", placeholder="Promo code")
    real = cand(index=1, tag="input", id="term-entry", placeholder="Type here...")
    rr = repair_target("search_box", obs([bait, real]), want_value="widget")
    assert rr.ok
    assert "promo" in rr.durable_selector      # <- the weakness: bait chosen


# --- integration: four representative cells, end-to-end headless ---
@pytest.mark.integration
def test_degradation_cells_end_to_end(tmp_path):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    if not (gen.OUT / "clean" / "index.html").exists():
        pytest.skip("mutation sites not generated")
    results = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1000, "height": 800})
        for cid in ("clean", "perception-light", "execution-medium", "execution-heavy"):
            results[cid] = dc.run_cell(page, cid, "widget", "Widget Pro 3000",
                                       tmp_path / "mem.json")
        browser.close()

    assert results["clean"]["status"] == "pass" and results["clean"]["repairs"] == 0
    assert results["perception-light"]["status"] == "pass"
    assert results["perception-light"]["repairs"] >= 2
    # mid-task removal recovered: fault hit, repair found the replacement, pass
    em = results["execution-medium"]
    assert em["status"] == "pass" and em["fault_encountered"] and em["recovered"]
    # deterministic 500: selector recovery succeeds but the run honestly fails
    eh = results["execution-heavy"]
    assert eh["status"] == "fail" and eh["checkpoint"] == "pass"
