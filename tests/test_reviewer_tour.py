"""5-minute reviewer tour — a static, dependency-free strip at the top of BOTH
frontends. Four stations, each「按這顆 → 看這裡 → 這證明了什麼」. These tests pin
the markup so the tour cannot silently drop a station or lose the anchors the
copy points at. No browser, no numbers — pure structure."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENT = ROOT / "apps" / "services" / "agent" / "static" / "index.html"
SEC = ROOT / "apps" / "services" / "sec" / "static" / "index.html"


def _agent() -> str:
    return AGENT.read_text(encoding="utf-8")


def _sec() -> str:
    return SEC.read_text(encoding="utf-8")


def test_tour_strip_present_on_both_frontends():
    for html in (_agent(), _sec()):
        assert 'id="reviewerTour"' in html
        assert 'class="tour-stations"' in html
        # exactly four stations
        assert html.count('class="tour-station"') == 4
        # every station carries the three-part line (the <b> label marks a station,
        # so the heading's plain-text copy of the phrase is not miscounted)
        assert html.count("按這顆</b>") == 4
        assert html.count("看這裡</b>") == 4
        assert "這證明了什麼" in html          # heading states the pattern


def test_tour_is_collapsible_and_dismissible_via_localstorage():
    for html in (_agent(), _sec()):
        assert 'id="tourToggle"' in html and 'id="tourDismiss"' in html
        assert "'wealth_tour'" in html and "localStorage.getItem(LS)" in html
        assert "'dismissed'" in html and "'collapsed'" in html
        assert "tour-flash" in html          # scroll-to-target highlight exists


def test_agent_stations_target_the_real_demo_buttons_and_verdict():
    html = _agent()
    # demo buttons get a stable id equal to their preset id
    assert "b.id=t.id;" in html
    for target in ("demo-v2-drift", "demo-open-unknown", "demo-refused"):
        assert f'data-target="#{target}"' in html
    # station 2 points at the verdict / three-state discipline
    assert "verdict" in html and "UNKNOWN" in html
    assert "three-state discipline" in html
    assert "capability guard boundary" in html
    assert "self-maintenance is a real mechanism" in html
    # single-worker expectation note (honest, number-free)
    assert "single worker" in html and "排隊不等於卡住" in html
    # station 4 crosses to the SEC service
    assert 'data-nav="sec"' in html and 'data-hash="tour=aapl"' in html


def test_sec_station_targets_aapl_and_item8_riskband():
    html = _sec()
    # local station points at the live AAPL suggestion chip (real extract, not canned)
    assert "data-target='.chip[data-q=\"AAPL\"]'" in html
    assert "Item 8" in html and "Risk band" in html
    assert "XBRL oracle" in html and "sha256" in html
    # first three stations cross back to the agent service with per-station hashes
    assert 'data-nav="agent"' in html
    for hid in ("tour=demo-v2-drift", "tour=demo-open-unknown", "tour=demo-refused"):
        assert f'data-hash="{hid}"' in html


def test_sec_frontend_shows_scoped_strong_and_unresolved_cases():
    html = _sec()
    assert 'id="task2Cases"' in html
    assert 'id="task2StrongCase"' in html
    assert 'id="task2BodyCase"' in html          # cross-reference body now resolved
    assert 'id="task2WeakCase"' in html
    assert "目前做得好（限定範圍）" in html
    assert "AAPL · Item 8 source span" in html
    assert "不代表整份 filing 全部正確" in html
    # cross-reference body is now a scoped positive (page-anchor resolution)
    assert "INTC / C · Cross-reference body via page anchors" in html
    assert "9 個 Item" in html
    # the genuine still-not-done case + the self-audited status fix
    assert "目前沒做好 / needs review" in html
    assert "維持誠實 pointer" in html
    assert "positive-evidence" in html            # the >900-char false-pass fix
    assert 'id="sQuery" value="AAPL"' in html
    assert "20-F" in html and "failure handling" in html


def test_cross_page_hash_handoff_is_wired_both_ways():
    # each page reads #tour=KEY on arrival and flashes the local target
    assert "match(/tour=([\\w-]+)/)" in _agent()
    assert "match(/tour=([\\w-]+)/)" in _sec()
    # agent maps the three demo keys; sec maps the aapl key
    assert "'demo-v2-drift':'#demo-v2-drift'" in _agent()
    assert "'aapl':'.chip[data-q=\"AAPL\"]'" in _sec()
