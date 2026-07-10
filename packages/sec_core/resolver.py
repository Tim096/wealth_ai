"""Filing resolver (SPEC 7.4): ticker / CIK / accession / URL -> a concrete
filing package (CIK + accession + file list) ready for main-document scoring.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from sec_core.fetcher import EdgarFetcher

TICKER_INDEX_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
ARCHIVE_BASE = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc_nodash}"

_ACCESSION_RE = re.compile(r"^(\d{10})-?(\d{2})-?(\d{6})$")


@dataclass
class FilingFile:
    name: str
    doc_type: str = ""
    size: int = 0


@dataclass
class FilingRef:
    cik: int
    accession: str  # dashed form 0000000000-00-000000
    form: str = ""
    filing_date: str = ""
    report_date: str = ""
    primary_document: str = ""
    files: list[FilingFile] = field(default_factory=list)
    is_amendment: bool = False

    @property
    def acc_nodash(self) -> str:
        return self.accession.replace("-", "")

    def file_url(self, name: str) -> str:
        return ARCHIVE_BASE.format(cik=self.cik, acc_nodash=self.acc_nodash) + "/" + name


class FilingResolver:
    def __init__(self, fetcher: EdgarFetcher) -> None:
        self.fetcher = fetcher

    def cik_for_ticker(self, ticker: str) -> int:
        data = json.loads(self.fetcher.get(TICKER_INDEX_URL).content)
        ticker_uc = ticker.strip().upper()
        for entry in data.values():
            if entry["ticker"].upper() == ticker_uc:
                return int(entry["cik_str"])
        raise LookupError(f"ticker {ticker!r} not found in SEC company index")

    def annual_filings(self, cik: int) -> list[FilingRef]:
        data = json.loads(self.fetcher.get(SUBMISSIONS_URL.format(cik=cik)).content)
        recent = data.get("filings", {}).get("recent", {})
        refs: list[FilingRef] = []
        forms = recent.get("form", [])
        for i, form in enumerate(forms):
            if form not in ("10-K", "10-K/A"):
                continue
            refs.append(FilingRef(
                cik=cik,
                accession=recent["accessionNumber"][i],
                form=form,
                filing_date=recent.get("filingDate", [""] * len(forms))[i],
                report_date=recent.get("reportDate", [""] * len(forms))[i],
                primary_document=recent.get("primaryDocument", [""] * len(forms))[i],
                is_amendment=form == "10-K/A",
            ))
        return refs

    def find_10k(self, cik: int, year: int) -> FilingRef:
        """10-K whose report (fiscal) year matches; falls back to filing year."""
        candidates = self.annual_filings(cik)
        by_report = [r for r in candidates if r.report_date.startswith(str(year))]
        by_filing = [r for r in candidates if r.filing_date.startswith(str(year))]
        pool = by_report or by_filing
        if not pool:
            raise LookupError(f"no 10-K found for CIK {cik}, year {year}")
        originals = [r for r in pool if not r.is_amendment]
        return (originals or pool)[0]

    def resolve_accession(self, cik: int, accession: str) -> FilingRef:
        m = _ACCESSION_RE.match(accession.replace("-", ""))
        if not m:
            raise ValueError(f"invalid accession number: {accession!r}")
        dashed = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        ref = FilingRef(cik=cik, accession=dashed)
        self.load_files(ref)
        return ref

    def load_files(self, ref: FilingRef) -> None:
        url = ARCHIVE_BASE.format(cik=ref.cik, acc_nodash=ref.acc_nodash) + "/index.json"
        data = json.loads(self.fetcher.get(url).content)
        ref.files = [
            FilingFile(
                name=item["name"],
                doc_type=item.get("type", ""),
                size=int(item.get("size") or 0),
            )
            for item in data.get("directory", {}).get("item", [])
        ]
