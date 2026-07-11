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

# Annual-report forms filed by foreign private issuers instead of a 10-K.
_FOREIGN_ANNUAL_FORMS = ("20-F", "40-F")


class NotA10KFilerError(LookupError):
    """The company files with SEC EDGAR but has NO 10-K / 10-K/A at all.

    Honest refusal (SPEC 三態誠實): instead of a bare "not found" we report
    what the company ACTUALLY files (e.g. TSM/SONY/BABA file 20-F + 6-K as
    foreign private issuers) and state plainly that only 10-K item extraction
    is supported. Subclasses LookupError so existing handlers keep working.
    """

    def __init__(self, cik: int, company: str, tickers: list[str],
                 form_counts: dict[str, int]) -> None:
        self.cik = cik
        self.company = company
        self.tickers = tickers
        self.form_counts = form_counts
        ident = "/".join(tickers) or company or f"CIK {cik}"
        if company and tickers:
            ident = f"{ident}({company})"
        dist = ", ".join(
            f"{form}×{n}" for form, n in
            sorted(form_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:6])
        foreign = next((f for f in _FOREIGN_ANNUAL_FORMS if f in form_counts), "")
        if foreign:
            msg = (f"{ident} 未申報 10-K;該公司以 {foreign}(外國私人發行人年報)申報。"
                   f"實際 form 分布:{dist}。"
                   f"本系統僅支援 10-K item 抽取,誠實拒絕而非硬抽。")
        elif form_counts:
            msg = (f"{ident} 未申報 10-K;實際 form 分布:{dist}。"
                   f"本系統僅支援 10-K item 抽取,誠實拒絕而非硬抽。")
        else:
            msg = (f"{ident} 在 SEC EDGAR 查無任何申報紀錄。"
                   f"本系統僅支援 10-K item 抽取,誠實拒絕而非硬抽。")
        super().__init__(msg)


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
        filings = data.get("filings", {})
        refs: list[FilingRef] = []
        form_counts: dict[str, int] = {}
        self._collect_10k(cik, filings.get("recent", {}), refs, form_counts)
        # The submissions API keeps only the most recent ~1000 filings inline;
        # a prolific filer's older 10-Ks live in separate paginated files. Pull
        # those too so EVERY historical 10-K is selectable (the year picker must
        # not silently stop at whatever fits in "recent").
        for page in filings.get("files", []):
            name = page.get("name")
            if not name:
                continue
            try:
                older = json.loads(self.fetcher.get(
                    f"https://data.sec.gov/submissions/{name}").content)
            except Exception:  # noqa: BLE001 — one bad page must not drop the rest
                continue
            self._collect_10k(cik, older, refs, form_counts)
        # Honest refusal: the company files with EDGAR, just never a 10-K
        # (foreign private issuers file 20-F/40-F instead). Report the ACTUAL
        # form mix instead of a bare "not found".
        if not refs:
            raise NotA10KFilerError(
                cik=cik,
                company=data.get("name", "") or "",
                tickers=[t for t in (data.get("tickers") or []) if t],
                form_counts=form_counts,
            )
        # newest first, de-duplicated by accession
        seen: set[str] = set()
        out: list[FilingRef] = []
        for r in sorted(refs, key=lambda r: (r.report_date or r.filing_date or ""), reverse=True):
            if r.accession in seen:
                continue
            seen.add(r.accession)
            out.append(r)
        return out

    @staticmethod
    def _collect_10k(cik: int, block: dict, refs: list[FilingRef],
                     form_counts: dict[str, int] | None = None) -> None:
        forms = block.get("form", [])
        for i, form in enumerate(forms):
            if form_counts is not None and form:
                form_counts[form] = form_counts.get(form, 0) + 1
            if form not in ("10-K", "10-K/A"):
                continue
            refs.append(FilingRef(
                cik=cik,
                accession=block["accessionNumber"][i],
                form=form,
                filing_date=block.get("filingDate", [""] * len(forms))[i],
                report_date=block.get("reportDate", [""] * len(forms))[i],
                primary_document=block.get("primaryDocument", [""] * len(forms))[i],
                is_amendment=form == "10-K/A",
            ))

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
