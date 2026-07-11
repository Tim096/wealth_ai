"""Fifth arbitration vote — datamule (P0-7c). MIT, plain pip dependency
(pinned datamule==5.0.1 in pyproject; rationale survey pinned upstream commit
122fc54, 2026-06-25 — see docs/ATTRIBUTION.md).

Independence: datamule's parsing backend is doc2dict — style-driven header
detection (bold / font-size hierarchy) with per-form mapping dicts — a
different implementation family from our regex-driven pipeline, from
edgartools, and from edgar-crawler's regex core. It has NO public accuracy
benchmark: it is a triangulation VOTE, never gold.

Unavailability (not installed, parse crash, no items) degrades to None ->
engine_unavailable; never evidence against our span.
"""

from __future__ import annotations

import re

from sec_core.headings import VALID_CODES

_STD_TITLE_RE = re.compile(r"item(\d{1,2}[abc]?)\Z")


def std_title_to_code(standardized_title: str) -> str | None:
    """doc2dict standardized_title ('item1a') -> our item code ('1A');
    None for parts / unknown codes."""
    m = _STD_TITLE_RE.match(str(standardized_title).strip().lower())
    if not m:
        return None
    code = m.group(1).upper()
    return code if code in VALID_CODES else None


def extract_items_datamule(raw_html: str, form: str = "10-K") -> dict[str, str] | None:
    """Parse the SAME raw HTML our pipeline consumed with datamule/doc2dict.
    Returns item_code -> text, or None (engine unavailable). No network."""
    try:
        from datamule import Document
    except ImportError:
        return None
    try:
        doc = Document(type=form, content=raw_html, filename="filing.htm",
                       accession="triangulation", filing_date=None)
        doc.parse()
        sections = doc.get_section(title_class="item", format="text", simplify=False)
        items: dict[str, str] = {}
        for sec in sections or []:
            code = std_title_to_code(sec.get("standardized_title", ""))
            text = sec.get("text", "")
            if code is None or not isinstance(text, str) or not text.strip():
                continue
            # duplicate item numbers (e.g. TOC + body): keep the longer body
            if code in items and len(items[code]) >= len(text):
                continue
            items[code] = text
        return items or None
    except Exception:  # noqa: BLE001 — third-party crash is engine_unavailable
        return None
