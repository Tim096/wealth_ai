"""Gold-free per-item whole-filing length-ratio prior (sec_core/length_prior.py).

Scale-invariant complement to the absolute size bands: a substantive pass
span whose share of the whole filing falls outside the corpus-derived
[p05, p95] per-item ratio band is flagged needs_review with a capped
confidence (zero-scored heavy component), in BOTH directions (overshoot =
boundary bleed, undershoot = fragment). Thresholds come from corpus-only
agree-and-pass samples — NTU human labels are held-out measurement, never
parameters.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from sec_core.confidence import OVERSHOOT_COMPONENT_MAX
from sec_core.length_prior import (
    MIN_DOC_CHARS,
    MIN_SAMPLES,
    OVERSHOOT_PRIOR_COMPONENT,
    PRIOR_PATH,
    UNDERSHOOT_PRIOR_COMPONENT,
    LengthPrior,
    apply_length_prior,
    build_priors,
    in_band_fraction,
    load_length_priors,
    percentile,
)
from sec_core.pipeline import extract_from_html

FILLER = (
    "The company manufactures precision widgets and distributes them through "
    "regional partners under long-term supply agreements reviewed annually. "
)


def _prior(code: str, p05: float, p95: float, p50: float | None = None) -> dict:
    return {("10-K", "MODERN", code): LengthPrior(
        "10-K", "MODERN", code, n=10, p05=p05,
        p50=p50 if p50 is not None else (p05 + p95) / 2, p95=p95)}


def _result(item1_body: str, pad: bool = True):
    parts = [f"<p><b>Item 1. Business</b></p><p>{item1_body}</p>",
             "<p><b>Item 1B. Unresolved Staff Comments</b></p><p>None.</p>"]
    if pad:
        parts.append("<p><b>Item 7. Management's Discussion and Analysis of Financial "
                     "Condition and Results of Operations</b></p>")
        parts.append("<p>" + FILLER * (MIN_DOC_CHARS // len(FILLER) + 2) + "</p>")
    return extract_from_html("".join(parts), "length-prior-test")


# --- prior math ---------------------------------------------------------------

class TestBuildPriors:
    def _samples(self, item, ratios, schema="MODERN"):
        return [{"form": "10-K", "schema": schema, "item": item, "ratio": r,
                 "source": "test"} for r in ratios]

    def test_percentile_interpolates(self):
        assert percentile([0.0, 1.0], 0.5) == 0.5
        assert percentile([1.0, 2.0, 3.0, 4.0, 5.0], 0.95) == 4.8
        assert percentile([7.0], 0.95) == 7.0

    def test_priors_carry_p05_p50_p95(self):
        pri = build_priors(self._samples("1", [0.1, 0.2, 0.3, 0.4, 0.5]))
        b = pri["10-K"]["MODERN"]["1"]
        assert b["n"] == 5
        assert b["p50"] == 0.3
        assert abs(b["p05"] - 0.12) < 1e-9
        assert abs(b["p95"] - 0.48) < 1e-9

    def test_below_min_samples_emits_no_prior(self):
        assert build_priors(self._samples("1", [0.1] * (MIN_SAMPLES - 1))) == {}

    def test_schemas_never_pool(self):
        mixed = (self._samples("14", [0.01] * 5)
                 + self._samples("14", [0.30] * 5, schema="PRE2003"))
        pri = build_priors(mixed)
        assert pri["10-K"]["MODERN"]["14"]["p50"] == 0.01
        assert pri["10-K"]["PRE2003"]["14"]["p50"] == 0.30

    def test_in_band_fraction_counts_only_covered_samples(self):
        samples = self._samples("1", [0.1, 0.2, 0.3, 0.4, 0.5]) + self._samples("1", [0.9])
        pri = build_priors(samples[:5])
        # 0.1 and 0.5 sit outside [p05, p95] of their own build set; 0.9 too
        assert in_band_fraction(samples, pri) == 3 / 6

    def test_missing_artifact_is_inert(self, tmp_path):
        assert load_length_priors(tmp_path / "absent.json") == {}


# --- enforcement ---------------------------------------------------------------

class TestApplyLengthPrior:
    def test_overshoot_is_flagged_and_confidence_capped(self):
        result = _result(FILLER * 5)
        seg = result.segment("1")
        seg.needs_review = False
        ratio = (seg.end_offset - seg.start_offset) / len(result.doc.text)
        priors = _prior("1", p05=ratio / 100, p95=ratio / 2)  # span far above p95
        conf_before = seg.confidence
        n = apply_length_prior(result.segments, result.doc, priors=priors,
                               breakdowns=result.confidence)
        assert n == 1
        assert seg.needs_review is True
        assert any("length-prior guardrail (overshoot)" in w for w in seg.warnings)
        bd = result.confidence["1"]
        comp = next(c for c in bd.components if c.name == OVERSHOOT_PRIOR_COMPONENT)
        assert comp.score == 0.0 and comp.max_score == OVERSHOOT_COMPONENT_MAX
        assert seg.confidence == bd.total < conf_before

    def test_undershoot_is_flagged_with_its_own_component(self):
        result = _result(FILLER * 5)
        seg = result.segment("1")
        seg.needs_review = False
        ratio = (seg.end_offset - seg.start_offset) / len(result.doc.text)
        priors = _prior("1", p05=ratio * 2, p95=ratio * 100)  # span far below p05
        n = apply_length_prior(result.segments, result.doc, priors=priors,
                               breakdowns=result.confidence)
        assert n == 1
        assert seg.needs_review is True
        assert any("length-prior guardrail (undershoot)" in w for w in seg.warnings)
        assert any(c.name == UNDERSHOOT_PRIOR_COMPONENT
                   for c in result.confidence["1"].components)

    def test_component_is_never_appended_twice(self):
        result = _result(FILLER * 5)
        seg = result.segment("1")
        ratio = (seg.end_offset - seg.start_offset) / len(result.doc.text)
        priors = _prior("1", p05=ratio / 100, p95=ratio / 2)
        apply_length_prior(result.segments, result.doc, priors=priors,
                           breakdowns=result.confidence)
        apply_length_prior(result.segments, result.doc, priors=priors,
                           breakdowns=result.confidence)
        comps = [c for c in result.confidence["1"].components
                 if c.name == OVERSHOOT_PRIOR_COMPONENT]
        assert len(comps) == 1

    def test_in_band_span_is_untouched(self):
        result = _result(FILLER * 5)
        seg = result.segment("1")
        seg.needs_review = False
        ratio = (seg.end_offset - seg.start_offset) / len(result.doc.text)
        priors = _prior("1", p05=ratio / 2, p95=ratio * 2)
        assert apply_length_prior(result.segments, result.doc, priors=priors) == 0
        assert seg.needs_review is False

    def test_boilerplate_none_answer_is_never_flagged(self):
        result = _result(FILLER * 5)
        seg = result.segment("1B")  # "None." body
        ratio = (seg.end_offset - seg.start_offset) / len(result.doc.text)
        priors = _prior("1B", p05=ratio * 10, p95=ratio * 100)
        assert apply_length_prior(result.segments, result.doc, priors=priors) == 0
        assert not any("length-prior" in w for w in seg.warnings)

    def test_non_pass_items_are_skipped(self):
        result = _result(FILLER * 5)
        seg = result.segment("1")
        seg.status = "partial"
        seg.needs_review = False
        ratio = (seg.end_offset - seg.start_offset) / len(result.doc.text)
        priors = _prior("1", p05=ratio / 100, p95=ratio / 2)
        assert apply_length_prior(result.segments, result.doc, priors=priors) == 0

    def test_excerpt_scale_documents_are_out_of_distribution(self):
        result = _result(FILLER * 5, pad=False)
        assert len(result.doc.text) < MIN_DOC_CHARS
        seg = result.segment("1")
        ratio = (seg.end_offset - seg.start_offset) / len(result.doc.text)
        priors = _prior("1", p05=ratio / 100, p95=ratio / 2)
        assert apply_length_prior(result.segments, result.doc, priors=priors) == 0

    def test_unknown_item_is_never_flagged(self):
        result = _result(FILLER * 5)
        priors = _prior("7A", p05=0.4, p95=0.5)  # no prior for items present
        assert apply_length_prior(result.segments, result.doc, priors=priors) == 0

    def test_span_offsets_are_never_changed(self):
        result = _result(FILLER * 5)
        seg = result.segment("1")
        before = (seg.start_offset, seg.end_offset, seg.text_sha256)
        ratio = (seg.end_offset - seg.start_offset) / len(result.doc.text)
        priors = _prior("1", p05=ratio / 100, p95=ratio / 2)
        apply_length_prior(result.segments, result.doc, priors=priors,
                           breakdowns=result.confidence)
        assert (seg.start_offset, seg.end_offset, seg.text_sha256) == before


# --- pipeline wiring + kill-switch ---------------------------------------------

class TestPipelineWiring:
    def test_kill_switch_disables_the_signal(self):
        code = (
            "import os, sys; sys.path.insert(0, 'packages')\n"
            "os.environ['SEC_LENGTH_PRIOR'] = '0'\n"
            "from sec_core.pipeline import extract_from_html\n"
            f"FILLER = {FILLER!r}\n"
            "html = ('<p><b>Item 1. Business</b></p><p>' + FILLER * 2 + '</p>'\n"
            "        \"<p><b>Item 7. Management's Discussion and Analysis of Financial \"\n"
            "        'Condition and Results of Operations</b></p>'\n"
            f"        '<p>' + FILLER * ({MIN_DOC_CHARS} // len(FILLER) + 2) + '</p>')\n"
            "r = extract_from_html(html, 'kill-switch-test')\n"
            "assert not any('length-prior' in w for s in r.segments for w in s.warnings)\n"
            "print('ok')\n"
        )
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True,
                              text=True, cwd=Path(__file__).resolve().parents[1])
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.strip() == "ok"

    def test_default_pipeline_applies_committed_priors(self):
        # a tiny substantive Item 1 inside a full-scale filing is far below
        # the committed item-1 p05 share -> undershoot flag on the live path
        if os.environ.get("SEC_LENGTH_PRIOR") == "0":
            return  # environment explicitly disabled the signal
        result = _result(FILLER)
        seg = result.segment("1")
        assert any("length-prior guardrail (undershoot)" in w for w in seg.warnings)
        assert seg.needs_review is True


# --- committed artifact ----------------------------------------------------------

class TestArtifact:
    ART = json.loads(PRIOR_PATH.read_text(encoding="utf-8"))

    def test_core_modern_items_have_priors(self):
        modern = self.ART["priors"]["10-K"]["MODERN"]
        for code in ("1", "1A", "7", "8"):
            assert modern[code]["n"] >= MIN_SAMPLES
            assert 0 < modern[code]["p05"] <= modern[code]["p50"] <= modern[code]["p95"] < 1

    def test_gold_free_provenance_is_declared(self):
        assert "NTU" in self.ART["gold_free"]
        assert self.ART["samples_total"] >= 100

    def test_loader_reads_committed_artifact(self):
        priors = load_length_priors()
        assert ("10-K", "MODERN", "1A") in priors
        p = priors[("10-K", "MODERN", "1A")]
        assert p.p05 < p.p95
