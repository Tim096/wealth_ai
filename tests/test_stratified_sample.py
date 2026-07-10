"""T2-4 stratified-sampling tests — tools.stratified_sample.

The pure classification/invariant logic is tested offline (no network): filing
agent detection from the doc-head generator comment, accession-year derivation,
era/format classification, and the partition/coverage invariant — including the
degraded pre-2001 plain-text case where classification fails but the invariant
must still hold (nothing silently dropped)."""

from dataclasses import dataclass

from tools.stratified_sample import (
    accession_year,
    check_invariants,
    classify_format,
    detect_agent,
)


@dataclass
class Seg:
    start_offset: int
    end_offset: int
    item_code: str
    status: str = "pass"
    needs_review: bool = False


# --- detect_agent: real generator-comment signatures -----------------------
def test_detect_agent_workiva():
    assert detect_agent("<!--XBRL Document Created with the Workiva Platform-->") == "Workiva"


def test_detect_agent_dfin():
    head = "<!-- DFIN New ActiveDisclosure (SM) ... Copyright (c) 2025 Donnelley Financial Solutions -->"
    assert detect_agent(head) == "DFIN (Donnelley)"


def test_detect_agent_toppan():
    assert detect_agent("<!-- created by Toppan Merrill -->") == "Toppan Merrill"


def test_detect_agent_unknown_ignores_body_company_name():
    # a company literally named "Merrill" must NOT be read as the agent — but the
    # detector is only ever fed the HEAD, so a plain document head is unknown.
    assert detect_agent("<html><head><title>Form 10-K</title></head>") == "unknown/in-house"


# --- accession_year ---------------------------------------------------------
def test_accession_year():
    assert accession_year("0001047469-04-035975") == 2004
    assert accession_year("0000320193-96-000023") == 1996
    assert accession_year("0000320193-25-000079") == 2025
    assert accession_year("garbage") == 0


# --- classify_format --------------------------------------------------------
def test_classify_text_pre2001_by_txt_name():
    era, _ = classify_format("", "0000320193-96-000023.txt", "<SEC-DOCUMENT>...",
                             [], accession="0000320193-96-000023")
    assert era == "text_pre2001"


def test_classify_ixbrl_by_inline_tags():
    head = "<html xmlns:ix='http://www.xbrl.org/2013/inlineXBRL'><ix:header/>"
    era, _ = classify_format("", "aapl-20250927.htm", head, [], accession="0000320193-25-000079")
    assert era == "ixbrl_2019plus"


def test_classify_xbrl_era_by_exhibits():
    files = [Seg(0, 0, "aapl-20130928.xsd"), Seg(0, 0, "aapl-20130928_cal.xml")]
    # give the file objects a .name attribute the classifier reads
    files = [type("F", (), {"name": n})() for n in ("d10k.htm", "aapl_cal.xml", "aapl.xsd")]
    era, _ = classify_format("", "d590790d10k.htm", "<html><body>", files,
                             accession="0001193125-13-416534")
    assert era == "xbrl_2009_2018"


def test_classify_html_pre_xbrl():
    files = [type("F", (), {"name": n})() for n in ("a10k.htm",)]
    era, _ = classify_format("", "a2147337z10-k.htm", "<html><body><font>", files,
                             accession="0001047469-04-035975")
    assert era == "html_2001_2008"


# --- partition / coverage invariant ----------------------------------------
def test_invariant_tiles_on_clean_extraction():
    text = "x" * 1000
    segs = [Seg(0, 400, "1"), Seg(400, 900, "1A"), Seg(900, 1000, "2")]
    inv = check_invariants(text, segs)
    assert inv["partition_tiles_whole_document"] is True
    assert inv["coverage_ratio"] == 1.0
    assert inv["pass_items"] == 3


def test_invariant_holds_when_classification_fails():
    # the pre-2001 degradation: heading detection found nothing, every span is
    # zero-width. The partition must still tile the whole body as one
    # unclassified block (capture-first) — nothing may be silently dropped.
    text = "y" * 5000
    segs = [Seg(0, 0, code, status="missing") for code in ("1", "1A", "2", "3")]
    inv = check_invariants(text, segs)
    assert inv["partition_tiles_whole_document"] is True
    assert inv["coverage_ratio"] == 0.0
    assert inv["pass_items"] == 0
    assert inv["statuses"] == {"missing": 4}


def test_invariant_tiles_with_overlapping_wrapper_spans():
    # wrapper filings nest spans (Item 2 inside Item 1); partition_document must
    # still produce a gap-free, overlap-free tiling.
    text = "z" * 2000
    segs = [Seg(0, 2000, "1"), Seg(500, 800, "2")]
    inv = check_invariants(text, segs)
    assert inv["partition_tiles_whole_document"] is True
    assert inv["coverage_ratio"] == 1.0
