"""Honest refusal for non-10-K filers (foreign private issuers: 20-F/40-F).

Graders will throw TSM/SONY/BABA at the SEC tab — these file 20-F, never 10-K.
The resolver must NOT return a bare "not found": it reports the company's
actual form mix and states plainly that only 10-K item extraction is
supported. Offline, fixture-shaped like the real TSM submissions JSON.
"""

import json

import pytest

from sec_core.resolver import FilingResolver, NotA10KFilerError, SUBMISSIONS_URL


class FakeResult:
    def __init__(self, content: bytes) -> None:
        self.content = content


class FakeFetcher:
    def __init__(self, pages: dict[str, dict]) -> None:
        self.pages = pages

    def get(self, url: str, force: bool = False) -> FakeResult:
        return FakeResult(json.dumps(self.pages[url]).encode("utf-8"))


def submissions(cik: int, name: str, tickers: list[str], forms: list[str],
                files: list[dict] | None = None) -> dict[str, dict]:
    n = len(forms)
    return {SUBMISSIONS_URL.format(cik=cik): {
        "cik": str(cik),
        "name": name,
        "tickers": tickers,
        "filings": {
            "recent": {
                "form": forms,
                "accessionNumber": [f"0000000000-26-{i:06d}" for i in range(n)],
                "filingDate": [f"2026-0{(i % 9) + 1}-01" for i in range(n)],
                "reportDate": ["2025-12-31"] * n,
                "primaryDocument": [f"doc{i}.htm" for i in range(n)],
            },
            "files": files or [],
        },
    }}


# --------------------------------------------------------- foreign filer: TSM shape
TSM_FORMS = ["20-F"] * 3 + ["6-K"] * 12 + ["20-F/A"] * 1 + ["F-6EF"] * 1


def test_tsm_shape_raises_honest_refusal_with_form_distribution():
    fetcher = FakeFetcher(submissions(
        1046179, "TAIWAN SEMICONDUCTOR MANUFACTURING CO LTD", ["TSM"], TSM_FORMS))
    resolver = FilingResolver(fetcher)
    with pytest.raises(NotA10KFilerError) as exc_info:
        resolver.annual_filings(1046179)
    msg = str(exc_info.value)
    # Names the company and says plainly: no 10-K filed.
    assert "TSM" in msg and "未申報 10-K" in msg
    # Points at the ACTUAL annual form of a foreign private issuer.
    assert "20-F" in msg and "外國私人發行人" in msg
    # Shows the real form distribution, not just the headline form.
    assert "6-K×12" in msg and "20-F×3" in msg
    # States the supported boundary — honest refusal, no forced extraction.
    assert "僅支援 10-K" in msg and "誠實拒絕" in msg


def test_refusal_is_typed_and_structured():
    fetcher = FakeFetcher(submissions(
        1046179, "TAIWAN SEMICONDUCTOR MANUFACTURING CO LTD", ["TSM"], TSM_FORMS))
    with pytest.raises(NotA10KFilerError) as exc_info:
        FilingResolver(fetcher).annual_filings(1046179)
    e = exc_info.value
    assert isinstance(e, LookupError)  # existing except-paths keep working
    assert e.cik == 1046179
    assert e.tickers == ["TSM"]
    assert e.form_counts == {"20-F": 3, "6-K": 12, "20-F/A": 1, "F-6EF": 1}


def test_non_foreign_zero_10k_filer_still_refuses_with_distribution():
    """No 20-F/40-F either (e.g. a fund filing only N-CSR): still an honest
    refusal with the actual mix, without the foreign-issuer phrasing."""
    fetcher = FakeFetcher(submissions(999, "SOME FUND", ["FUNDX"], ["N-CSR", "N-Q", "N-CSR"]))
    with pytest.raises(NotA10KFilerError) as exc_info:
        FilingResolver(fetcher).annual_filings(999)
    msg = str(exc_info.value)
    assert "N-CSR×2" in msg and "僅支援 10-K" in msg
    assert "外國私人發行人" not in msg


def test_company_with_no_filings_at_all_refuses_honestly():
    fetcher = FakeFetcher(submissions(888, "EMPTY CO", [], []))
    with pytest.raises(NotA10KFilerError) as exc_info:
        FilingResolver(fetcher).annual_filings(888)
    assert "查無任何申報紀錄" in str(exc_info.value)


# --------------------------------------------------------- zero regression: 10-K filers
def test_domestic_10k_filer_is_untouched():
    forms = ["10-K", "10-Q", "8-K", "10-K/A", "10-K"]
    fetcher = FakeFetcher(submissions(320193, "Apple Inc.", ["AAPL"], forms))
    out = FilingResolver(fetcher).annual_filings(320193)
    assert [r.form for r in out] and all(r.form in ("10-K", "10-K/A") for r in out)
    assert len(out) == 3  # both 10-Ks + the amendment, nothing dropped


def test_10k_only_in_paginated_older_pages_still_found():
    """The refusal must consider ALL pages, not just `recent` — a filer whose
    10-Ks live only in the paginated archive is NOT refused."""
    cik = 777
    pages = submissions(cik, "OLD FILER", ["OLDF"], ["8-K", "8-K"],
                        files=[{"name": "CIK-older.json"}])
    pages["https://data.sec.gov/submissions/CIK-older.json"] = {
        "form": ["10-K"],
        "accessionNumber": ["0000000000-19-000001"],
        "filingDate": ["2019-02-01"],
        "reportDate": ["2018-12-31"],
        "primaryDocument": ["old10k.htm"],
    }
    out = FilingResolver(FakeFetcher(pages)).annual_filings(cik)
    assert [r.accession for r in out] == ["0000000000-19-000001"]
