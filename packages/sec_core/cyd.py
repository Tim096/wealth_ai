"""CYD iXBRL ground truth — the ONLY official machine-readable item span
(TODO T2-3). iXBRL tags numbers, not item boundaries, so XBRL is useless as an
item-span oracle — with one exception: for fiscal years ending on or after
2024-12-15 the SEC mandates block-tagging the Item 1C cybersecurity disclosure
with the CYD taxonomy (ix:nonNumeric name="cyd:*TextBlock"). Those tags are an
official, filer-asserted answer to "where is Item 1C?" — the one place we can
compare our segmentation against SEC-mandated ground truth instead of another
heuristic engine.

Offline and deterministic: everything is parsed from the SAME raw HTML the
pipeline consumed (no extra fetch). Like xbrl_check / third_engine this is an
opt-in pass run at the call site (tools/certify_cyd.py), never inside
extract_from_html. The tags never manufacture our filing text; they only vote
on where the official span lies.
"""

from __future__ import annotations

import re
from bisect import bisect_left
from dataclasses import dataclass, field
from html.parser import HTMLParser

MANDATORY_FROM = "2024-12-15"  # fiscal years ending on/after this must block-tag
_COVERAGE_MIN = 0.85  # fraction of the official span our segment must cover
_TEXTBLOCK_RE = re.compile(r"TextBlock$")
_CYD_XMLNS_RE = re.compile(r'xmlns:([\w.-]+)\s*=\s*["\'][^"\']*xbrl\.sec\.gov/cyd[^"\']*["\']')


@dataclass
class IxFragment:
    """One ix element's content span in RAW html offsets."""
    name: str            # 'cyd:...TextBlock' for facts, '' for continuations
    frag_id: str
    continued_at: str
    raw_start: int       # content start (after the start tag)
    raw_end: int         # content end (at the closing tag)
    hidden: bool = False # inside ix:hidden — tagged but not displayed


@dataclass
class CydCheck:
    available: bool                # were CYD text-block tags found?
    mandatory: bool                # fiscal year end >= 2024-12-15?
    verdict: str                   # agree | disagree | unavailable | not_required
    detail: str = ""
    n_text_blocks: int = 0
    n_fragments: int = 0
    n_hidden: int = 0
    official_intervals: list[tuple[int, int]] = field(default_factory=list)  # normalized offsets
    official_chars: int = 0
    our_chars: int = 0
    coverage: float = 0.0          # |ours ∩ official| / |official|
    containment: float = 0.0       # |ours ∩ official| / |ours|


class _IxScanner(HTMLParser):
    """Locate ix:nonNumeric CYD text blocks + ix:continuation elements with
    exact raw offsets. Same offset bookkeeping as normalize._Normalizer so the
    two views of the document agree character-for-character.
    """

    def __init__(self, cyd_prefixes: set[str]) -> None:
        super().__init__(convert_charrefs=False)
        self.cyd_prefixes = {p.lower() for p in cyd_prefixes}
        self.text_blocks: list[IxFragment] = []
        self.continuations: dict[str, IxFragment] = {}
        self._open: list[tuple[str, IxFragment | None]] = []  # (tag, fragment-or-None)
        self._hidden_depth = 0
        self._line_starts: list[int] = [0]

    def feed_document(self, raw: str) -> None:
        pos = 0
        while True:
            nl = raw.find("\n", pos)
            if nl == -1:
                break
            self._line_starts.append(nl + 1)
            pos = nl + 1
        self.feed(raw)
        self.close()

    def _abs_pos(self) -> int:
        line, col = self.getpos()
        return self._line_starts[line - 1] + col

    def _is_cyd_textblock(self, name: str) -> bool:
        if ":" not in name:
            return False
        prefix, local = name.split(":", 1)
        return prefix.lower() in self.cyd_prefixes and bool(_TEXTBLOCK_RE.search(local))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "ix:hidden":
            self._hidden_depth += 1
            return
        if tag not in ("ix:nonnumeric", "ix:continuation"):
            return
        attrs_d = {k: (v or "") for k, v in attrs}
        content_start = self._abs_pos() + len(self.get_starttag_text() or "")
        frag: IxFragment | None = None
        if tag == "ix:nonnumeric" and self._is_cyd_textblock(attrs_d.get("name", "")):
            frag = IxFragment(
                name=attrs_d.get("name", ""), frag_id=attrs_d.get("id", ""),
                continued_at=attrs_d.get("continuedat", ""),
                raw_start=content_start, raw_end=content_start,
                hidden=self._hidden_depth > 0)
        elif tag == "ix:continuation" and attrs_d.get("id"):
            frag = IxFragment(
                name="", frag_id=attrs_d["id"],
                continued_at=attrs_d.get("continuedat", ""),
                raw_start=content_start, raw_end=content_start,
                hidden=self._hidden_depth > 0)
        self._open.append((tag, frag))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag == "ix:hidden":
            self._hidden_depth = max(0, self._hidden_depth - 1)
            return
        if tag not in ("ix:nonnumeric", "ix:continuation"):
            return
        # pop the innermost matching open element (ix elements can nest)
        for i in range(len(self._open) - 1, -1, -1):
            if self._open[i][0] == tag:
                _, frag = self._open.pop(i)
                if frag is not None:
                    frag.raw_end = self._abs_pos()
                    if frag.name:
                        self.text_blocks.append(frag)
                    else:
                        self.continuations.setdefault(frag.frag_id, frag)
                return


def cyd_prefixes(raw_html: str) -> set[str]:
    """The namespace prefix bound to the CYD taxonomy (almost always 'cyd',
    but the prefix is filer-chosen — resolve it from the xmlns declarations)."""
    return set(_CYD_XMLNS_RE.findall(raw_html)) or {"cyd"}


def parse_cyd_fragments(raw_html: str) -> tuple[list[IxFragment], dict[str, IxFragment]]:
    scanner = _IxScanner(cyd_prefixes(raw_html))
    scanner.feed_document(raw_html)
    return scanner.text_blocks, scanner.continuations


def assemble_raw_intervals(
    text_blocks: list[IxFragment], continuations: dict[str, IxFragment],
) -> tuple[list[tuple[int, int]], int, int]:
    """Follow continuedAt chains, drop ix:hidden fragments (tagged but not
    displayed — they are not part of the visible Item 1C span), merge into
    sorted disjoint RAW intervals. Returns (intervals, n_fragments, n_hidden).
    """
    intervals: list[tuple[int, int]] = []
    n_fragments = 0
    n_hidden = 0
    for block in text_blocks:
        frag: IxFragment | None = block
        seen: set[int] = set()
        while frag is not None and id(frag) not in seen:
            seen.add(id(frag))
            n_fragments += 1
            if frag.hidden:
                n_hidden += 1
            elif frag.raw_end > frag.raw_start:
                intervals.append((frag.raw_start, frag.raw_end))
            frag = continuations.get(frag.continued_at) if frag.continued_at else None
    intervals.sort()
    merged: list[tuple[int, int]] = []
    for s, e in intervals:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged, n_fragments, n_hidden


def raw_to_norm(doc, raw_offset: int) -> int:
    """Map a raw-HTML offset to a normalized-text offset. norm_to_raw is
    nondecreasing (emission follows document order), so this is a bisect."""
    return bisect_left(doc.norm_to_raw, raw_offset)


def _overlap(a: tuple[int, int], intervals: list[tuple[int, int]]) -> int:
    return sum(max(0, min(a[1], e) - max(a[0], s)) for s, e in intervals)


def certify_item1c(result, raw_html: str, report_date: str = "") -> CydCheck:
    """Compare the official CYD-tagged span against our Item 1C segment and
    WRITE the verdict back (segment.cyd_check, mirroring xbrl_check). A
    disagree on a `pass` segment flags needs_review. Opt-in pass — run at the
    call site on the SAME raw HTML the pipeline consumed; no network.
    """
    mandatory = bool(report_date) and report_date >= MANDATORY_FROM
    text_blocks, continuations = parse_cyd_fragments(raw_html)
    seg = next((s for s in result.segments if s.item_code == "1C"), None)

    if not text_blocks:
        verdict = "unavailable" if mandatory else "not_required"
        detail = ("no CYD text-block tags found despite mandatory tagging "
                  f"(fiscal year end {report_date} >= {MANDATORY_FROM}) — filer anomaly, "
                  "not evidence against our extraction" if mandatory else
                  f"CYD block-tagging not yet mandatory for fiscal year end {report_date!r}")
        chk = CydCheck(available=False, mandatory=mandatory, verdict=verdict, detail=detail)
        if seg is not None:
            seg.cyd_check = f"{chk.verdict}: {chk.detail}"
        return chk

    raw_intervals, n_fragments, n_hidden = assemble_raw_intervals(text_blocks, continuations)
    norm_intervals = [(raw_to_norm(result.doc, s), raw_to_norm(result.doc, e))
                      for s, e in raw_intervals]
    norm_intervals = [(s, e) for s, e in norm_intervals if e > s]
    official_chars = sum(e - s for s, e in norm_intervals)

    ours = (seg.start_offset, seg.end_offset) if seg is not None else (0, 0)
    our_chars = max(0, ours[1] - ours[0])
    inter = _overlap(ours, norm_intervals) if our_chars else 0
    coverage = inter / official_chars if official_chars else 0.0
    containment = inter / our_chars if our_chars else 0.0

    if coverage >= _COVERAGE_MIN:
        verdict = "agree"
        detail = (f"our segment covers {coverage:.0%} of the official CYD-tagged span "
                  f"({official_chars:,} chars, {len(text_blocks)} text blocks)")
    else:
        verdict = "disagree"
        detail = (f"our segment covers only {coverage:.0%} of the official CYD-tagged span "
                  f"({official_chars:,} chars, {len(text_blocks)} text blocks) — the "
                  f"SEC-mandated Item 1C content lies outside our boundaries")

    chk = CydCheck(
        available=True, mandatory=mandatory, verdict=verdict, detail=detail,
        n_text_blocks=len(text_blocks), n_fragments=n_fragments, n_hidden=n_hidden,
        official_intervals=norm_intervals, official_chars=official_chars,
        our_chars=our_chars, coverage=round(coverage, 4), containment=round(containment, 4))

    if seg is not None:
        seg.cyd_check = f"{chk.verdict}: {chk.detail}"
        if verdict == "disagree" and seg.status == "pass":
            seg.needs_review = True
            seg.warnings.append(
                "CYD iXBRL oracle disagrees with this pass: the officially block-tagged "
                "cybersecurity disclosure is not inside the extracted Item 1C span — "
                "likely a boundary error. Flagged needs_review.")
    return chk
