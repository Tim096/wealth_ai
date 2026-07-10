"""Multi-detector heading candidate detection (SPEC 7.8).

Candidates come from line regexes; independent detectors (strict regex, loose
regex, DOM emphasis, visual layout) attach agreeing signals. No single
detector decides — cross-detector agreement feeds confidence scoring.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from sec_core.items import CANONICAL_ITEM_TITLES
from sec_core.normalize import FLAG_BOLD, FLAG_HEADING, FLAG_TOC_LINK, NormalizedDocument

VALID_CODES = list(CANONICAL_ITEM_TITLES.keys())

_STRICT_RE = re.compile(
    r"^\s*item\s+(\d{1,2})\s*([a-cA-C])?\s*[.:\-]?\s*(.*)$", re.IGNORECASE
)
_LOOSE_RE = re.compile(
    r"^\s*(?:part\s+[ivx]+[.,]?\s*[-:]?\s*)?item\s*(\d{1,2})\s*([a-cA-C])?\b[\s.:\-]*(.*)$",
    re.IGNORECASE,
)
_COMBINED_RE = re.compile(
    r"^\s*items\s+(\d{1,2})\s*([a-cA-C])?\s+and\s+(\d{1,2})\s*([a-cA-C])?\b[\s.:\-]*(.*)$",
    re.IGNORECASE,
)
_PAGE_NUMBER_RE = re.compile(r"(?:\.{3,}|·{3,}|\s)\s*\d{1,4}\s*$")


@dataclass
class HeadingCandidate:
    code: str
    line_index: int
    start: int  # normalized offset of line start
    end: int  # normalized offset of line end
    heading_text: str
    title_text: str
    detectors: set[str] = field(default_factory=set)
    title_similarity: float = 0.0
    in_toc_link: bool = False
    trailing_page_number: bool = False
    combined_with: str | None = None  # e.g. "2" when heading is 'Items 1 and 2'
    toc_rejected: bool = False
    toc_reasons: list[str] = field(default_factory=list)

    @property
    def is_uppercase(self) -> bool:
        letters = [c for c in self.heading_text if c.isalpha()]
        return bool(letters) and sum(c.isupper() for c in letters) / len(letters) > 0.8


def _canonical_similarity(code: str, title: str) -> float:
    canonical = CANONICAL_ITEM_TITLES.get(code, "")
    if not title.strip():
        return 0.0
    return SequenceMatcher(
        None, canonical.casefold(), title.strip().casefold()
    ).ratio()


def _line_flag_ratio(doc: NormalizedDocument, start: int, end: int, mask: int) -> float:
    chars = [i for i in range(start, min(end, len(doc.flags))) if not doc.text[i].isspace()]
    if not chars:
        return 0.0
    return sum(1 for i in chars if doc.flags[i] & mask) / len(chars)


def _make_code(num: str, letter: str | None) -> str | None:
    code = num + (letter or "").upper()
    return code if code in CANONICAL_ITEM_TITLES else None


def detect_candidates(doc: NormalizedDocument) -> list[HeadingCandidate]:
    candidates: list[HeadingCandidate] = []

    for idx, line in enumerate(doc.lines):
        if not line.text.strip() or len(line.text) > 200:
            continue

        matches: list[tuple[str, str, str | None]] = []  # (code, title, combined_with)
        m = _COMBINED_RE.match(line.text)
        if m:
            code_a = _make_code(m.group(1), m.group(2))
            code_b = _make_code(m.group(3), m.group(4))
            if code_a and code_b:
                matches.append((code_a, m.group(5), code_b))
                matches.append((code_b, m.group(5), code_a))
        else:
            m = _LOOSE_RE.match(line.text)
            if m:
                code = _make_code(m.group(1), m.group(2))
                if code:
                    matches.append((code, m.group(3), None))

        for code, title, combined in matches:
            cand = HeadingCandidate(
                code=code,
                line_index=idx,
                start=line.start,
                end=line.end,
                heading_text=line.text.strip(),
                title_text=title.strip(),
                combined_with=combined,
            )
            cand.detectors.add("loose_regex")
            if _STRICT_RE.match(line.text) and len(line.text.strip()) <= 120:
                cand.detectors.add("strict_regex")
            if _line_flag_ratio(doc, line.start, line.end, FLAG_BOLD | FLAG_HEADING) >= 0.7:
                cand.detectors.add("dom_heading")
            prev_blank = idx == 0 or not doc.lines[idx - 1].text.strip()
            next_blank = idx + 1 >= len(doc.lines) or not doc.lines[idx + 1].text.strip()
            if len(line.text.strip()) <= 120 and (prev_blank or next_blank or cand.is_uppercase):
                cand.detectors.add("visual_layout")
            cand.title_similarity = _canonical_similarity(code, title)
            cand.in_toc_link = _line_flag_ratio(doc, line.start, line.end, FLAG_TOC_LINK) >= 0.5
            cand.trailing_page_number = bool(_PAGE_NUMBER_RE.search(line.text))
            candidates.append(cand)

    return candidates
