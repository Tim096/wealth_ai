"""Per-(form,schema,item) empirical size bands (P0-11).

The pipeline's only length sanity was one global 50..3,000,000-char band.
size_bands.py derives per-item bands (p50/5..p50*8) from agree-and-pass
entries and hard-flags substantive out-of-band pass spans as needs_review.
The committed artifact also carries the SRAF whole-filing upper-bound
invariant measurement (Loughran-McDonald 10X Summaries; fetch-on-demand,
never committed) and the guardrail's measured clean-corpus false-alarm rate.
"""

import json
from pathlib import Path

from sec_core.normalize import normalize_html
from sec_core.pipeline import extract_from_html
from sec_core.size_bands import (
    BANDS_PATH,
    MIN_DOC_CHARS,
    MIN_SAMPLES,
    SizeBand,
    apply_size_bands,
    build_bands,
    check_size_band,
    count_lm_words,
    in_band_fraction,
    load_size_bands,
    sraf_whole_filing_check,
)

FILLER = (
    "The company manufactures precision widgets and distributes them through "
    "regional partners under long-term supply agreements reviewed annually. "
)


# --- band math ---------------------------------------------------------------

def _samples(item: str, spans: list[int]) -> list[dict]:
    return [{"form": "10-K", "schema": "MODERN", "item": item, "span_chars": s,
             "source": "test"} for s in spans]


class TestBuildBands:
    def test_band_is_p50_over_5_to_p50_times_8(self):
        bands = build_bands(_samples("1", [900, 1000, 1100, 1000, 1000]))
        b = bands["10-K"]["MODERN"]["1"]
        assert b["p50"] == 1000
        assert b["lo"] == 200
        assert b["hi"] == 8000
        assert b["n"] == 5

    def test_below_min_samples_emits_no_band(self):
        bands = build_bands(_samples("1", [1000] * (MIN_SAMPLES - 1)))
        assert bands == {}

    def test_schemas_never_pool(self):
        # pre-2003 item 14 (=Exhibits) must not pollute the modern 14 (=Fees)
        mixed = _samples("14", [2000] * 5)
        for s in _samples("14", [90000] * 5):
            mixed.append({**s, "schema": "PRE2003"})
        bands = build_bands(mixed)
        assert bands["10-K"]["MODERN"]["14"]["p50"] == 2000
        assert bands["10-K"]["PRE2003"]["14"]["p50"] == 90000

    def test_in_band_fraction_counts_only_banded_samples(self):
        samples = _samples("1", [1000] * 5) + _samples("1", [999999])
        bands = build_bands(samples[:5])
        assert in_band_fraction(samples, bands) == 5 / 6


class TestCheckSizeBand:
    BANDS = {("10-K", "MODERN", "1"): SizeBand("10-K", "MODERN", "1", 5, 1000, 200, 8000)}

    def test_in_band_returns_none(self):
        assert check_size_band(1000, "1", bands=self.BANDS) is None
        assert check_size_band(200, "1", bands=self.BANDS) is None  # inclusive lo
        assert check_size_band(8000, "1", bands=self.BANDS) is None  # inclusive hi

    def test_out_of_band_returns_the_band(self):
        assert check_size_band(199, "1", bands=self.BANDS).p50 == 1000
        assert check_size_band(8001, "1", bands=self.BANDS) is not None

    def test_unbanded_item_or_schema_is_never_flagged(self):
        assert check_size_band(5, "7A", bands=self.BANDS) is None
        assert check_size_band(5, "1", schema="PRE2003", bands=self.BANDS) is None

    def test_missing_artifact_is_inert(self, tmp_path):
        assert load_size_bands(tmp_path / "absent.json") == {}


# --- enforcement -------------------------------------------------------------

def _doc_and_segments(item1_body: str, pad_to_min_doc: bool = True):
    parts = [f"<p><b>Item 1. Business</b></p><p>{item1_body}</p>",
             "<p><b>Item 1B. Unresolved Staff Comments</b></p><p>None.</p>"]
    if pad_to_min_doc:
        # a terminal MD&A absorbs the padding that lifts the document to
        # complete-filing scale (in-band for the committed item 7 band)
        parts.append("<p><b>Item 7. Management's Discussion and Analysis of Financial "
                     "Condition and Results of Operations</b></p>")
        parts.append("<p>" + FILLER * (MIN_DOC_CHARS // len(FILLER) + 2) + "</p>")
    html = "".join(parts)
    result = extract_from_html(html, "size-band-test")
    return result


class TestApplySizeBands:
    BANDS = {
        ("10-K", "MODERN", "1"): SizeBand("10-K", "MODERN", "1", 5, 50000, 10000, 400000),
        ("10-K", "MODERN", "1B"): SizeBand("10-K", "MODERN", "1B", 5, 41, 8, 328),
    }

    def test_out_of_band_substantive_pass_item_is_hard_flagged(self):
        result = _doc_and_segments(FILLER * 5)  # ~640 chars << lo 10000
        seg = result.segment("1")
        seg.needs_review = False  # isolate from the pipeline's own default run
        seg.warnings.clear()
        n = apply_size_bands(result.segments, result.doc, bands=self.BANDS)
        assert n == 1
        assert seg.needs_review is True
        assert any("size-band guardrail" in w for w in seg.warnings)

    def test_boilerplate_none_short_answer_is_never_flagged(self):
        result = _doc_and_segments(FILLER * 5)
        bands = dict(self.BANDS)
        # force 1B's "None." (out-of-band low) against a substantive band
        bands[("10-K", "MODERN", "1B")] = SizeBand("10-K", "MODERN", "1B", 5, 5000, 1000, 40000)
        seg = result.segment("1B")
        apply_size_bands(result.segments, result.doc, bands=bands)
        assert seg.needs_review is False
        assert not any("size-band guardrail" in w for w in seg.warnings)

    def test_non_pass_and_non_offset_exact_items_are_skipped(self):
        result = _doc_and_segments(FILLER * 5)
        seg = result.segment("1")
        seg.needs_review = False
        seg.status = "partial"
        n = apply_size_bands(result.segments, result.doc, bands=self.BANDS)
        assert n == 0
        assert seg.needs_review is False

    def test_excerpt_scale_documents_are_out_of_distribution(self):
        # bands were learned from complete filings — a small fixture/excerpt
        # must not be sprayed with review flags
        result = _doc_and_segments(FILLER * 5, pad_to_min_doc=False)
        assert len(result.doc.text) < MIN_DOC_CHARS
        n = apply_size_bands(result.segments, result.doc, bands=self.BANDS)
        assert n == 0

    def test_pipeline_wires_the_guardrail(self):
        # end-to-end: the live pipeline (default committed bands: item 1
        # lo is in the thousands) flags a tiny substantive Item 1 in a
        # full-scale document
        result = _doc_and_segments(FILLER * 5)
        seg = result.segment("1")
        assert seg.needs_review is True
        assert any("size-band guardrail" in w for w in seg.warnings)


# --- SRAF whole-filing invariant ----------------------------------------------

class TestSrafInvariant:
    def test_within_tolerance_passes(self):
        ok, ratio = sraf_whole_filing_check(9000, 10000)
        assert ok and ratio == 0.9

    def test_exceeding_tolerance_fails(self):
        ok, ratio = sraf_whole_filing_check(20000, 10000, tolerance=1.25)
        assert not ok and ratio == 2.0

    def test_no_independent_count_is_not_applicable(self):
        assert sraf_whole_filing_check(9000, 0) == (True, 0.0)

    def test_count_lm_words_ignores_numbers_and_markup(self):
        assert count_lm_words("Revenue was 1,234 dollars — up 5%") == 4


# --- committed artifact ------------------------------------------------------

class TestArtifact:
    ART = json.loads(BANDS_PATH.read_text(encoding="utf-8"))

    def test_core_modern_items_have_bands(self):
        modern = self.ART["bands"]["10-K"]["MODERN"]
        for code in ("1", "1A", "7", "8"):
            assert modern[code]["n"] >= MIN_SAMPLES
            assert modern[code]["lo"] < modern[code]["p50"] < modern[code]["hi"]

    def test_measured_clean_corpus_false_alarm_rate_under_p04_gate(self):
        rs = self.ART["runtime_specificity"]
        assert rs["clean_pass_items"] > 100
        assert rs["false_alarm_rate"] <= 0.05  # P0-4 specificity gate

    def test_sraf_invariant_is_measured_or_honestly_skipped(self):
        sraf = self.ART["sraf_invariant"]
        assert sraf["status"] in ("measured", "skipped")
        if sraf["status"] == "measured":
            assert sraf["violations"] == 0
            assert sraf["max_ratio"] <= sraf["tolerance"]
        else:
            assert "reason" in sraf  # skipped-with-reason, never silent

    def test_loader_reads_committed_artifact(self):
        bands = load_size_bands()
        assert ("10-K", "MODERN", "1A") in bands
        b = bands[("10-K", "MODERN", "1A")]
        assert b.lo == b.p50 // 5 and b.hi == b.p50 * 8
