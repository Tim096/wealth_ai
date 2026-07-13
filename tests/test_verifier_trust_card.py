"""Trust-card drift gate (tools/verifier_trust_card.py).

Pins the contract of the machine-generated Verifier Trust Card: the committed
docs/verifier_trust_card.md is byte-identical to a fresh in-memory render (no
hand edit survives), every artifact it cites exists, every displayed number
equals the value re-read from its artifact, and the AUROC row shows MISS. No
network, no LLM.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import verifier_trust_card as card  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def test_committed_card_matches_fresh_render():
    """The killer invariant: the doc on disk == a fresh render, byte for byte."""
    assert card.OUTPUT.exists(), "docs/verifier_trust_card.md missing — run the tool"
    assert card.OUTPUT.read_text(encoding="utf-8") == card.render()


def test_render_is_deterministic_and_timestamp_free():
    first = card.render()
    assert first == card.render()
    # a timestamp would break CI byte-comparison; assert none leaked in.
    for token in ("generated_at", "20260", "T0", "Z\n", "UTC"):
        assert token not in first, f"non-deterministic token {token!r} in card"


def test_all_artifact_paths_exist():
    for row in card.build_rows():
        for part in row.artifact.split(" + "):
            assert (ROOT / part.strip()).exists(), f"row {row.n}: missing {part}"
        assert card.REGISTRY.exists()


def test_values_equal_values_reread_from_artifacts():
    text = card.OUTPUT.read_text(encoding="utf-8")

    bcal = card._load_json(card.BROWSER_CAL)
    assert f"{card._walk(bcal, 'rates.sensitivity')} / " \
           f"{card._walk(bcal, 'rates.specificity')}" == "1.0 / 1.0"
    assert "1.0 / 1.0" in text
    assert str(card._walk(bcal, "rogan_gladen_corrected_success_rate.corrected")) == "0.8"

    auroc = card._walk(card._load_json(card.SEC_CAL), "strata.ntu_human_labeled.auroc")
    assert str(auroc) in text and auroc == 0.6667

    caught = card._walk(card._load_json(card.ATTRIBUTION),
                        "variants.margin_plus_ibr_SHIPPED.caught_errors")
    assert caught == "77/118" and f"({caught})" in text and "65.3%" in text

    cert = card._load_json(card.CERTIFICATION)
    assert f"{card._walk(cert, 'verdicts.certified')} certified / " \
           f"{card._walk(cert, 'verdicts.contradicted')} contradicted" in text
    assert "10 certified / 1 contradicted" in text

    cyd = card._load_json(card.CYD)
    assert f"{card._walk(cyd, 'verdicts.agree')} agree / " \
           f"{card._walk(cyd, 'verdicts.disagree')} disagree" in text
    assert "11 agree / 0 disagree" in text

    imp = card._load_json(card.IMPOSSIBLE)
    assert str(card._walk(imp, "metrics.silent_failure_rate")) == "0.0"
    assert str(card._walk(imp, "metrics.honest_outcome_rate")) == "1.0"

    tri = card._load_json(card.TRIANGULATION)
    assert f"{card._walk(tri, 'verdict_totals.agree')} agree / " \
           f"{card._walk(tri, 'verdict_totals.disagree')} disagree" in text
    assert "249 agree / 4 disagree" in text

    alarms, total, rate = card._sweep3_clean_false_alarm()
    assert (alarms, total, rate) == (1, 178, 0.0056)
    assert "0.0056 (1/178)" in text


def test_miss_appears_for_auroc_row():
    rows = card.build_rows()
    auroc_row = next(r for r in rows if "AUROC" in r.metric)
    assert auroc_row.gate == "MISS"
    assert auroc_row.value == "0.6667"

    text = card.OUTPUT.read_text(encoding="utf-8")
    # MISS is rendered with the same bold weight as PASS (parity, not downplayed).
    assert "**MISS** (≥ 0.75)" in text
    assert "**PASS**" in text
    assert "## 未過門檻" in text and "MISS · row 5" in text


def test_gate_is_computed_from_the_value_not_hardcoded(monkeypatch):
    """If the AUROC artifact regenerated above the gate, the card would flip to
    PASS — proving the gate is derived, not a literal. Patch the loader."""
    real_load = card._load_json

    def fake_load(path):
        data = real_load(path)
        if path == card.SEC_CAL:
            data["strata"]["ntu_human_labeled"]["auroc"] = 0.90
        return data

    monkeypatch.setattr(card, "_load_json", fake_load)
    auroc_row = next(r for r in card.build_rows() if "AUROC" in r.metric)
    assert auroc_row.gate == "PASS" and auroc_row.value == "0.9"


def test_check_mode_passes_on_committed_card():
    assert card.main(["--check"]) == 0
