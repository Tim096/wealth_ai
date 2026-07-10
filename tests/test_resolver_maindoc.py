"""Offline tests for resolver parsing and main-document scoring.
Network integration is exercised separately (marked `network`)."""

import pytest

from sec_core.main_doc import pick_main_document, score_files
from sec_core.resolver import FilingFile, FilingRef


def make_ref(files, primary=""):
    ref = FilingRef(cik=123, accession="0000123456-26-000001", primary_document=primary)
    ref.files = files
    return ref


def test_main_doc_prefers_10k_over_exhibits():
    ref = make_ref([
        FilingFile(name="alph-20251231.htm", doc_type="10-K", size=5_000_000),
        FilingFile(name="ex-211.htm", doc_type="EX-21.1", size=20_000),
        FilingFile(name="alph-20251231_htm.xml", doc_type="XML", size=9_000_000),
        FilingFile(name="logo.jpg", size=50_000),
    ], primary="alph-20251231.htm")
    best = pick_main_document(ref)
    assert best.name == "alph-20251231.htm"
    assert any("document type is 10-K" in r for r in best.reasons)


def test_main_doc_content_peek_beats_cover_page():
    ref = make_ref([
        FilingFile(name="cover.htm", doc_type="10-K", size=8_000),
        FilingFile(name="form10-k.htm", doc_type="", size=8_000),
    ])
    peeks = {
        "cover.htm": "<p>Cover page only.</p>",
        "form10-k.htm": "Item 1A. Risk Factors ... Item 7. MD&A ... Item 8. Financials",
    }
    best = pick_main_document(ref, peeks)
    assert best.name == "form10-k.htm"


def test_main_doc_refuses_when_nothing_plausible():
    ref = make_ref([FilingFile(name="graph.jpg", size=1000)])
    with pytest.raises(LookupError, match="no plausible main document"):
        pick_main_document(ref)


def test_scores_are_explained():
    ref = make_ref([FilingFile(name="a10k.htm", doc_type="10-K", size=100)])
    for s in score_files(ref):
        assert s.reasons


def test_accession_normalization():
    from sec_core.resolver import _ACCESSION_RE

    m = _ACCESSION_RE.match("000032019326000008")
    assert m
    assert f"{m.group(1)}-{m.group(2)}-{m.group(3)}" == "0000320193-26-000008"
    assert _ACCESSION_RE.match("junk") is None
