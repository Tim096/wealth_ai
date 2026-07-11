"""P0-7 element structural hash + cascade rebinding (MatchLevel telemetry).

Pure tests cover the cleaned two-level hash (EXACT/STABLE), the exactly-1
rebind rule, memory persistence of the hashes, and the MatchLevel counts in
TaskRun.as_dict; one integration test drives the full cascade — a script-mode
success banks the hashes, then an id rename is rebound deterministically via
the STABLE hash without purpose scoring.
"""

import pytest

from browser_core import BrowserTaskContract, SuccessCondition
from browser_agent.memory_store import MemoryStore
from browser_agent.observer import (
    DYNAMIC_CLASS_PATTERNS, ElementCandidate, Observation, _clean_classes,
    structural_hashes,
)
from browser_agent.repair import MATCH_LEVELS, rebind_by_hash


def cand(**kw):
    base = dict(index=0, tag="input", type="text", id="", name="", role="", aria_label="",
                placeholder="", text="", href="", visible=True, x=0, y=0)
    base.update(kw)
    return ElementCandidate(**base)


def obs(cands):
    return Observation(url="u", title="t", visible_text="", candidates=cands)


# --- cleaned class filter ---
def test_clean_classes_filters_dynamic_keeps_static():
    raw = "btn primary css-1a2b3c active ng-star-inserted jsx-392 is-open uid-45821"
    assert _clean_classes(raw) == "btn primary"
    assert _clean_classes("") == ""
    assert DYNAMIC_CLASS_PATTERNS  # the spec-named constant exists and is non-empty


# --- two-level structural hash ---
def test_structural_hashes_exact_vs_stable():
    a = cand(id="search", name="q", placeholder="Search products", text="",
             classes="box", parent_path="form")
    same = cand(id="search", name="q", placeholder="Search products", text="",
                classes="box", parent_path="form")
    assert structural_hashes(a) == structural_hashes(same)
    # id rename / text change break EXACT but survive STABLE
    for drift in (cand(id="search-v2", name="q", placeholder="Search products",
                       classes="box", parent_path="form"),
                  cand(id="search", name="q", placeholder="Search products",
                       text="new copy", classes="box", parent_path="form")):
        assert structural_hashes(drift)[0] != structural_hashes(a)[0]
        assert structural_hashes(drift)[1] == structural_hashes(a)[1]
    # a transient class churn changes NEITHER (filtered before hashing)
    churned = cand(id="search", name="q", placeholder="Search products", text="",
                   classes="box active css-9f9f9f", parent_path="form")
    assert structural_hashes(churned) == structural_hashes(a)
    # position is identity-irrelevant at BOTH levels
    moved = cand(id="search", name="q", placeholder="Search products", text="",
                 classes="box", parent_path="form", x=500, y=900)
    assert structural_hashes(moved) == structural_hashes(a)
    # a tag change is a different element at both levels
    other = cand(tag="textarea", id="search", name="q",
                 placeholder="Search products", classes="box", parent_path="form")
    assert structural_hashes(other)[0] != structural_hashes(a)[0]
    assert structural_hashes(other)[1] != structural_hashes(a)[1]


def test_structural_hashes_accepts_raw_field_dict():
    c = cand(id="go", name="", classes="btn", parent_path="form")
    d = {"tag": "input", "type": "text", "id": "go", "name": "", "role": "",
         "aria_label": "", "placeholder": "", "text": "", "href": "",
         "classes": "btn", "parent_path": "form"}
    assert structural_hashes(c) == structural_hashes(d)


# --- exactly-1 rebind cascade ---
def test_rebind_by_hash_exact_then_stable_then_none():
    target = cand(index=1, id="search", name="q", parent_path="form")
    ex, st = structural_hashes(target)
    decoy = cand(index=2, tag="button", type="submit", text="Go", parent_path="form")
    # exact single hit wins at level "exact"
    got, level = rebind_by_hash(ex, st, obs([decoy, target]))
    assert got is target and level == "exact"
    # exact misses (id renamed) -> stable single hit
    renamed = cand(index=1, id="search-v2", name="q", parent_path="form")
    got, level = rebind_by_hash(ex, st, obs([decoy, renamed]))
    assert got is renamed and level == "stable"
    # >1 stable hits = ambiguous -> falls through to none (never a guess)
    twin = cand(index=3, id="other", name="q", parent_path="form")
    got, level = rebind_by_hash("", st, obs([renamed, twin]))
    assert got is None and level == "none"
    # invisible candidates never match; empty hashes never match
    hidden = cand(index=1, id="search", name="q", parent_path="form", visible=False)
    assert rebind_by_hash(ex, st, obs([hidden])) == (None, "none")
    assert rebind_by_hash("", "", obs([target])) == (None, "none")
    assert MATCH_LEVELS == ("script", "exact", "stable", "purpose", "none")


# --- memory persistence ---
def test_selector_version_hashes_roundtrip(tmp_path):
    mem = MemoryStore(tmp_path / "m.json")
    # a failure must NOT bank an identity
    mem.record("s", "t", "search_box", "#q", "2026-01-01", success=False,
               element_hash="EX", element_hash_stable="ST")
    assert mem.hashes("s", "t", "search_box") == ("", "")
    mem.record("s", "t", "search_box", "#q", "2026-01-02", success=True,
               element_hash="EX", element_hash_stable="ST")
    assert mem.hashes("s", "t", "search_box") == ("EX", "ST")
    mem.save()
    reloaded = MemoryStore(tmp_path / "m.json")
    assert reloaded.hashes("s", "t", "search_box") == ("EX", "ST")
    # a success WITHOUT hashes keeps the previously banked identity
    reloaded.record("s", "t", "search_box", "#q", "2026-01-03", success=True)
    assert reloaded.hashes("s", "t", "search_box") == ("EX", "ST")
    # nothing remembered -> empty, never a KeyError
    assert reloaded.hashes("s", "t", "submit_button") == ("", "")


# --- MatchLevel telemetry in the eval row ---
def test_taskrun_as_dict_counts_match_levels():
    from browser_agent.agent import StepTrace, TaskRun
    from observability_core import VerifierResult

    steps = [StepTrace(step="a", action="fill", ok=True, mode="script", match_level="script"),
             StepTrace(step="b", action="click", ok=True, mode="repair", match_level="stable"),
             StepTrace(step="c", action="click", ok=True, mode="repair", match_level="purpose"),
             StepTrace(step="d", action="click", ok=True, mode="repair", match_level="stable"),
             StepTrace(step="latch", action="ledger", ok=True, mode="agent")]  # no level
    run = TaskRun(task_id="t", site="s", status="pass",
                  verifier=VerifierResult(status="pass", reason="ok"), steps=steps)
    d = run.as_dict()
    assert d["match_levels"] == {"script": 1, "stable": 2, "purpose": 1}
    assert d["steps"][0]["match_level"] == "script"
    assert d["steps"][4]["match_level"] == ""


# --- integration: the full cascade over real drift ---
@pytest.mark.integration
def test_hash_rebind_repairs_id_rename_without_scoring(tmp_path):
    # run 1: the selector works (script) -> the element's identity is banked.
    # run 2: the id was renamed, the remembered selector finds nothing — the
    # STABLE hash matches exactly one candidate, so the rebind is
    # deterministic (match_level=stable) and the durable selector + fresh
    # hashes land back in memory.
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    from browser_agent.agent import BrowserAgent, Step

    contract = BrowserTaskContract(
        task_id="t", natural_language_task="search for widgets",
        expected_outcome="query filled",
        success_conditions=[SuccessCondition(type="text_visible", value="NEVER_THERE_XYZ")])
    steps = [Step(purpose="search_box", kind="fill", value="widget",
                  fallback_selector="#search")]
    v1 = ("<form><input id='search' name='q' placeholder='Search products'>"
          "<button id='go' type='submit'>Search</button></form>")
    v2 = ("<form><input id='search-v2' name='q' placeholder='Search products'>"
          "<button id='go' type='submit'>Search</button></form>")
    mem = MemoryStore(tmp_path / "m.json")
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        page = b.new_page()
        page.set_content(v1)
        r1 = BrowserAgent(page, mem, "mock", "search").run("v1", steps, contract)
        assert mem.hashes("mock", "search", "search_box") != ("", "")
        s1 = next(s for s in r1.steps if s.step == "search_box")
        assert s1.ok and s1.match_level == "script"

        page.set_content(v2)
        r2 = BrowserAgent(page, mem, "mock", "search").run("v2", steps, contract)
        filled = page.eval_on_selector("#search-v2", "el => el.value")
        b.close()
    s2 = next(s for s in r2.steps if s.step == "search_box")
    assert s2.ok and s2.mode == "repair" and s2.match_level == "stable"
    assert "hash-stable rebind" in s2.detail
    assert filled == "widget"                        # the action really landed
    assert mem.preferred("mock", "search", "search_box") == "#search-v2"
    assert r2.as_dict()["match_levels"].get("stable") == 1
