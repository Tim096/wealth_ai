"""T2-5: the 10-K landmine catalogue turned into executable eval cases.

Each landmine from the eval-upgrade TODO (§T2-5) is a documented way a real
10-K breaks a naive extractor. This file pins the pipeline's behaviour on each
one so a regression that silently re-introduces the failure is caught. Every
case is either (a) a synthetic fixture that is ground truth by construction, or
(b) an offline unit on the resolver / main-document scorer. No network, no LLM.

The bar for a landmine is not "we extract it perfectly" — it is "we never fake
a pass": the correct outcome is an honest status (reserved / missing /
incorporated_by_reference / partial + needs_review), never a fabricated body.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from observability_core import sha256_text
from sec_core.headings import detect_candidates
from sec_core.main_doc import pick_main_document, score_files
from sec_core.normalize import normalize_html
from sec_core.pipeline import extract_from_html
from sec_core.resolver import FilingFile, FilingRef, FilingResolver
from sec_core.toc import assess_toc

# --- synthetic-filing builders (padded to realistic item lengths) ----------

_FILLER = (
    "The Company continues to evaluate developments in its markets and adjusts its "
    "operating plans accordingly, and management believes the factors described above "
    "are the material considerations relevant to this item. "
)


def _pad(text: str, target: int = 1400) -> str:
    while len(text) < target:
        text += " " + _FILLER
    return text


def _sec(heading: str, body: str, target: int = 1400) -> str:
    return f"<p><b>{heading}</b></p>\n<p>{_pad(body, target)}</p>\n"


def _doc(*parts: str) -> str:
    return "<html><body>" + "".join(parts) + "</body></html>"


# ===========================================================================
# Landmine 1 — Item 6 was abolished 2021-02-10: three legitimate era writings
# ===========================================================================

def test_item6_bracket_reserved_is_reserved_not_pass():
    """Post-2021 form 1: the filer writes 'Item 6. [Reserved]'."""
    html = _doc(
        "<div>PART II</div>",
        _sec("Item 5. Market for Registrant's Common Equity", "Common stock trades on Nasdaq under ALPH."),
        "<p><b>Item 6. [Reserved]</b></p>\n<p>Reserved.</p>\n",
        _sec("Item 7. Management's Discussion and Analysis of Financial Condition and Results of Operations",
             "Net revenue increased 11 percent."),
    )
    seg = extract_from_html(html, "item6-reserved").segment("6")
    assert seg.status == "reserved"


def test_item6_omitted_entirely_is_reserved_not_missing_failure():
    """Post-2021 form 2: the filer drops Item 6 with no heading at all. Because
    the item was abolished, absence is the reserved state, never a hard miss."""
    html = _doc(
        "<div>PART II</div>",
        _sec("Item 5. Market for Registrant's Common Equity", "Common stock trades on Nasdaq under ALPH."),
        _sec("Item 7. Management's Discussion and Analysis of Financial Condition and Results of Operations",
             "Net revenue increased."),
    )
    seg = extract_from_html(html, "item6-omitted").segment("6")
    assert seg.status == "reserved"  # not "missing" — abolished item, not a failure


def test_item6_pre2021_selected_financial_data_is_substantive_pass():
    """Pre-2021 form: Item 6 carried real 'Selected Financial Data' content."""
    html = _doc(
        "<div>PART II</div>",
        _sec("Item 5. Market for Registrant's Common Equity", "Common stock trades on Nasdaq under ALPH."),
        _sec("Item 6. Selected Financial Data",
             "The following selected financial data for the five years ended December 31, 2019 "
             "is derived from our audited consolidated financial statements. Net revenue was "
             "$4.2 billion and total assets were $8.4 billion."),
        _sec("Item 7. Management's Discussion and Analysis of Financial Condition and Results of Operations",
             "Net revenue increased 11 percent driven by cloud."),
    )
    result = extract_from_html(html, "item6-selected")
    seg = result.segment("6")
    assert seg.status == "pass"
    assert "Selected Financial Data" in result.text_of("6")


# ===========================================================================
# Landmine 2 — Item 9C (HFCAA) and Item 16 are conditional/optional items
# ===========================================================================

def test_item9c_hfcaa_present_is_source_exact_pass():
    html = _doc(
        "<div>PART II</div>",
        _sec("Item 9B. Other Information", "No director adopted a Rule 10b5-1 trading arrangement."),
        _sec("Item 9C. Disclosure Regarding Foreign Jurisdictions that Prevent Inspections",
             "Not applicable. We are not headquartered in a foreign jurisdiction identified under the HFCAA."),
        "<p><b>Item 10. Directors, Executive Officers and Corporate Governance</b></p>"
        "<p>Incorporated by reference to our definitive proxy statement.</p>",
    )
    result = extract_from_html(html, "item9c")
    seg = result.segment("9C")
    assert seg.status == "pass"
    span = result.doc.slice(seg.start_offset, seg.end_offset)
    assert sha256_text(span) == seg.text_sha256  # source-exact, LLM never wrote it


def test_item9c_absent_is_honest_missing_not_crash():
    """Most filers have no Item 9C (it is conditional on the HFCAA). Absence is
    an honest 'missing' status, never a fabricated body — the tri-state scorer
    (T2-2) then maps a not-TOC-listed missing to null, not a real omission."""
    html = _doc(
        "<div>PART II</div>",
        _sec("Item 9B. Other Information", "No director adopted a trading arrangement."),
        "<p><b>Item 10. Directors, Executive Officers and Corporate Governance</b></p>"
        "<p>Incorporated by reference to our definitive proxy statement.</p>",
    )
    seg = extract_from_html(html, "no-9c").segment("9C")
    assert seg.status == "missing"
    assert seg.text_sha256 == ""


def test_item16_optional_present_is_pass_absent_is_missing():
    present = _doc(
        "<div>PART IV</div>",
        _sec("Item 15. Exhibits, Financial Statement Schedules", "Documents filed as part of this report."),
        "<p><b>Item 16. Form 10-K Summary</b></p>\n<p>None.</p>\n",
    )
    assert extract_from_html(present, "item16-present").segment("16").status == "pass"

    absent = _doc(
        "<div>PART IV</div>",
        _sec("Item 15. Exhibits, Financial Statement Schedules", "Documents filed as part of this report."),
    )
    seg = extract_from_html(absent, "item16-absent").segment("16")
    assert seg.status == "missing"  # optional summary omitted — not a bug
    assert seg.text_sha256 == ""


# ===========================================================================
# Landmine 3 — "Items 7 and 7A" combined heading (like "Items 1 and 2")
# ===========================================================================

def test_items_7_and_7a_combined_share_one_span():
    html = _doc(
        "<div>PART II</div>",
        _sec("Item 5. Market for Registrant's Common Equity", "Nasdaq ALPH."),
        _sec("Items 7 and 7A. Management's Discussion and Analysis and Quantitative and "
             "Qualitative Disclosures About Market Risk",
             "Net revenue grew. We are also exposed to interest-rate and currency risk."),
        _sec("Item 8. Financial Statements and Supplementary Data",
             "Report of Independent Registered Public Accounting Firm. Consolidated balance sheets."),
    )
    result = extract_from_html(html, "items-7-7a")
    s7, s7a = result.segment("7"), result.segment("7A")
    assert s7.status == "partial" and s7a.status == "partial"
    assert (s7.start_offset, s7.end_offset) == (s7a.start_offset, s7a.end_offset)
    assert any("combined" in w for w in s7.warnings)
    assert any("combined" in w for w in s7a.warnings)


# ===========================================================================
# Landmine 4 — EDGAR formTypes is exact-match: '10-K' excludes '10-K/A'
# ===========================================================================

def test_collect_10k_includes_amendments_excludes_other_forms():
    """Our resolver must NOT reproduce the efts formTypes exact-match trap: it
    has to collect both 10-K and 10-K/A while rejecting 10-Q / 8-K / NT 10-K."""
    block = {
        "form": ["10-K", "10-K/A", "10-Q", "8-K", "NT 10-K"],
        "accessionNumber": ["a-1", "a-2", "a-3", "a-4", "a-5"],
        "filingDate": ["2025-02-01", "2025-05-01", "2025-08-01", "2025-03-01", "2025-01-15"],
        "reportDate": ["2024-12-31", "2024-12-31", "2025-03-31", "", "2024-12-31"],
        "primaryDocument": ["x.htm", "xa.htm", "q.htm", "k.htm", "nt.htm"],
    }
    refs: list[FilingRef] = []
    FilingResolver._collect_10k(123, block, refs)
    collected = {(r.form, r.accession) for r in refs}
    assert collected == {("10-K", "a-1"), ("10-K/A", "a-2")}
    amendment = next(r for r in refs if r.form == "10-K/A")
    assert amendment.is_amendment is True


# ===========================================================================
# Landmine 5 — TOC must be excluded BEFORE anchoring, not only compared after
# ===========================================================================

def test_toc_only_item_is_never_emitted_as_a_fake_body():
    """Item 3 appears ONLY in the anchored TOC — there is no Item 3 body heading
    downstream. A naive extractor anchors the TOC line and emits it as the body.
    We must not: the TOC candidate is document-order-excluded, so Item 3 comes
    back 'missing' with an empty span, never the dotted TOC line as content."""
    toc_rows = [
        ("item1", "Item 1. Business", 3),
        ("item1a", "Item 1A. Risk Factors", 12),
        ("item3", "Item 3. Legal Proceedings", 27),
        ("item7", "Item 7. Management's Discussion and Analysis", 31),
    ]
    toc = "\n".join(f'<div><a href="#{a}">{t}</a> .......... {p}</div>' for a, t, p in toc_rows)
    html = _doc(
        "<div>TABLE OF CONTENTS</div>", toc, "<div>PART I</div>",
        _sec("Item 1. Business", "Alpha designs widgets. Incorporated in Delaware."),
        _sec("Item 1A. Risk Factors", "Investing involves risk. Supply-chain disruption."),
        # deliberately NO Item 3 body heading
        _sec("Item 7. Management's Discussion and Analysis of Financial Condition and Results of Operations",
             "Revenue grew 11 percent."),
    )
    result = extract_from_html(html, "toc-only-item3")
    seg = result.segment("3")
    assert seg.status == "missing"
    assert seg.end_offset == seg.start_offset  # empty span, no TOC line leaked
    assert "Legal Proceedings" not in result.text_of("3")

    # and the TOC candidate was never silently dropped — it carries its reasons
    doc = normalize_html(html)
    cands = detect_candidates(doc)
    assess_toc(doc, cands)
    item3_cands = [c for c in cands if c.code == "3"]
    assert item3_cands and all(c.toc_reasons for c in item3_cands)


# ===========================================================================
# Landmine 6 — Part III incorporated by reference to the proxy (DEF 14A)
# ===========================================================================

def test_part_iii_incorporated_by_reference_is_not_faked_pass():
    """Item 10/11 that only point to the proxy statement must be classified
    incorporated_by_reference — marking a pointer 'pass' is a silent failure."""
    html = _doc(
        "<div>PART III</div>",
        "<p><b>Item 10. Directors, Executive Officers and Corporate Governance</b></p>"
        "<p>The information required by this Item 10 is incorporated by reference to our "
        "definitive proxy statement for the 2026 Annual Meeting of Stockholders to be filed "
        "within 120 days after fiscal year end.</p>",
        "<p><b>Item 11. Executive Compensation</b></p>"
        "<p>The information required by this Item 11 is incorporated by reference to our "
        "definitive proxy statement.</p>",
    )
    result = extract_from_html(html, "part-iii-ibr")
    assert result.segment("10").status == "incorporated_by_reference"
    assert result.segment("11").status == "incorporated_by_reference"


# ===========================================================================
# Landmine 7 — edgartools issue #454: Part I/II item-number collision
# ===========================================================================

def test_duplicate_item1_heading_does_not_steal_the_real_body():
    """edgartools #454: 'Item 1' resolves to the wrong section when the same code
    appears more than once. Our canonical-code + document-order resolver must
    keep the real Part I body and reject a later stray 'Item 1.' running header."""
    html = _doc(
        "<div>PART I</div>",
        _sec("Item 1. Business", "REAL_BODY_MARKER Alpha makes widgets in Delaware."),
        _sec("Item 1A. Risk Factors", "Risks include supply chain."),
        _sec("Item 2. Properties", "We own facilities."),
        "<p><b>Item 1.</b></p>\n<p>Business (continued) DUPLICATE_MARKER see above.</p>",
        _sec("Item 3. Legal Proceedings", "Ordinary-course litigation."),
    )
    result = extract_from_html(html, "collision-454")
    body = result.text_of("1")
    assert result.segment("1").status == "pass"
    assert "REAL_BODY_MARKER" in body
    assert "DUPLICATE_MARKER" not in body


# ===========================================================================
# Landmine 8 — Glossy ARS wrap: the 10-K is bundled with a glossy annual report
# ===========================================================================

def test_glossy_ars_wrap_picks_the_10k_not_the_larger_ex13():
    """A glossy annual report (EX-13) is often the LARGEST file in the package.
    The main-document scorer must still pick the real 10-K, not the exhibit."""
    ref = FilingRef(cik=123, accession="0000123456-26-000001", primary_document="acme-10k-20251231.htm")
    ref.files = [
        FilingFile(name="acme-10k-20251231.htm", doc_type="10-K", size=4_000_000),
        FilingFile(name="ex13-annualreport.htm", doc_type="EX-13", size=12_000_000),
        FilingFile(name="ex13-cover.jpg", size=800_000),
    ]
    peeks = {
        "acme-10k-20251231.htm": "Item 1A. Risk Factors ... Item 7. MD&A ... Item 8. Financials",
        "ex13-annualreport.htm": "To our shareholders, this was a great year. Letter from the CEO.",
    }
    best = pick_main_document(ref, peeks)
    assert best.name == "acme-10k-20251231.htm"
    ex13 = next(s for s in score_files(ref, peeks) if s.name == "ex13-annualreport.htm")
    assert ex13.score < best.score  # exhibit penalised despite being larger


def test_wrapper_terminal_item_does_not_swallow_appended_financial_section():
    """The Glossy/wrapper 10-K binds a 'FINANCIAL SECTION' after the last item.
    The terminal item's span must be cut at that break, not run away into it."""
    appended = "<div>FINANCIAL SECTION</div><p>" + _pad(
        "Report of Independent Registered Public Accounting Firm. Consolidated Balance Sheets. "
        "Total assets were $8.4 billion.", 30_000) + "</p>"
    html = _doc(
        "<div>PART IV</div>",
        _sec("Item 15. Exhibits, Financial Statement Schedules", "Exhibits listed in the index below."),
        "<p><b>Item 16. Form 10-K Summary</b></p>\n<p>None.</p>\n",
        appended,
    )
    result = extract_from_html(html, "wrapper-10k")
    seg = result.segment("16")
    assert "Report of Independent" not in result.text_of("16")
    assert any("appended" in w for w in seg.warnings)


# ===========================================================================
# Landmine 9 — cross-reference-index 10-K (Intel / Citi class): pointers only
# ===========================================================================

def test_cross_reference_index_items_are_pointers_not_bodies():
    """A cross-reference-index main document lists items with page ranges into a
    bound annual report. Every item must be an honest pointer (needs_review),
    never a fabricated body, and the filing class must be flagged."""
    html = "<html><body><div>Cross-Reference Index</div>" + "".join(
        f"<p><b>Item {code}. {title}</b></p><div>Pages {30 + i}-{40 + i}</div>"
        for i, (code, title) in enumerate([
            ("1", "Business"), ("1A", "Risk Factors"), ("1B", "Unresolved Staff Comments"),
            ("2", "Properties"), ("3", "Legal Proceedings"), ("5", "Market for Common Equity"),
            ("7", "Management's Discussion and Analysis"), ("7A", "Market Risk"),
            ("8", "Financial Statements"), ("9A", "Controls and Procedures"),
        ])
    ) + "</body></html>"
    result = extract_from_html(html, "xref-index")
    assert result.filing_class == "cross_reference_index"
    seg = result.segment("7")
    assert seg.status == "incorporated_by_reference"
    assert seg.provenance == "cross_reference_pointer"
    assert seg.needs_review is True
    assert seg.text_sha256 == ""  # never a fabricated body


# ===========================================================================
# Landmine 10 — large filing: offsets stay source-exact (we never chunk)
# ===========================================================================

def test_large_filing_offsets_stay_source_exact():
    """edgartools chunks filings past a ~50MB threshold and offsets can drift
    across chunk boundaries. Our pipeline normalises the whole document once, so
    every span stays a provable source-exact span regardless of size. Guard the
    invariant on a ~1.2MB doc (fast) — the property is size-independent."""
    html = _doc(
        "<div>PART I</div>",
        _sec("Item 1. Business", "Alpha makes widgets.", target=400_000),
        _sec("Item 1A. Risk Factors", "Risks abound.", target=400_000),
        _sec("Item 7. Management's Discussion and Analysis of Financial Condition and Results of Operations",
             "Revenue grew.", target=400_000),
    )
    assert len(html) > 1_000_000
    result = extract_from_html(html, "large-filing")
    checked = 0
    for seg in result.segments:
        if seg.end_offset <= seg.start_offset:
            continue
        span = result.doc.slice(seg.start_offset, seg.end_offset)
        assert sha256_text(span) == seg.text_sha256
        raw_start = result.doc.raw_offset(seg.start_offset)
        assert result.doc.raw_html[raw_start] == result.doc.text[seg.start_offset]
        checked += 1
    assert checked >= 3  # all three large items round-tripped
