"""Dashboard render pipeline tests (no browser): the committed index.html must
embed exactly the committed data.json — the hand-pasted snapshot can no longer
go silently stale — and data.json must carry the eval-hardening sections read
from committed artifacts, error-free."""

import json
from pathlib import Path

import pytest

from tools.render_dashboard import extract_data, render

ROOT = Path(__file__).resolve().parents[1]
DASH = ROOT / "apps" / "web" / "eval-dashboard"


def _data() -> dict:
    return json.loads((DASH / "data.json").read_text(encoding="utf-8"))


def test_index_embeds_current_data_json():
    embedded = extract_data((DASH / "index.html").read_text(encoding="utf-8"))
    assert embedded == _data(), (
        "index.html DATA is stale — rerun tools/render_dashboard.py")


def test_render_roundtrip_and_script_safety():
    template = (DASH / "template.html").read_text(encoding="utf-8")
    data = {"x": "</script><b>evil</b>", "n": 1.5, "u": "中文"}
    html = render(template, data)
    assert "</script><b>" not in html  # blob cannot close the <script> tag
    assert extract_data(html) == data


def test_render_rejects_missing_or_duplicate_placeholder():
    with pytest.raises(ValueError):
        render("no placeholder here", {})
    with pytest.raises(ValueError):
        render("__DATA__ twice __DATA__", {})


def test_extract_rejects_html_without_data():
    with pytest.raises(ValueError):
        extract_data("<p>nothing embedded</p>")


def test_data_schema_sections_present_and_error_free():
    data = _data()
    be, se = data["browser_evals"], data["sec_evals"]
    assert set(be) == {"calibration", "impossible", "passk", "degradation",
                       "trajectory", "false_success"}
    assert set(se) == {"triangulation", "offset_f1", "cyd", "stratification", "landmines"}
    errs = {k: v["error"] for d in (be, se) for k, v in d.items() if "error" in v}
    assert errs == {}


def test_data_matches_source_artifacts():
    data = _data()
    cal = json.loads((ROOT / "data" / "browser_eval" / "calibration" /
                      "calibration_results.json").read_text(encoding="utf-8"))
    assert data["browser_evals"]["calibration"]["rates"] == cal["rates"]
    tri = json.loads((ROOT / "data" / "sec_eval" / "triangulation" /
                      "triangulation.json").read_text(encoding="utf-8"))
    assert data["sec_evals"]["triangulation"]["verdict_totals"] == tri["verdict_totals"]
    assert data["sec"]["sweep"] == "sweep3"
    dg = data["browser_evals"]["degradation"]
    assert set(dg) == {"perception", "action", "execution"}
    assert all(len(points) == 4 for points in dg.values())
    shift = data["status_reclassification"]
    assert shift["before"]["pass"] == 192
    assert shift["after"]["pass"] == 177
