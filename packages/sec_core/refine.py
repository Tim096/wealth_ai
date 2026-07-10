"""Span refinement — the fixes for the silent failures the 11-company
adversarial audit surfaced (docs/failure_gallery.md FG-SEC-002..004):

1. trim_trailing_furniture: strip PART dividers, page numbers, running
   headers, and TOC back-links that leak into a span because the raw end
   offset is the next item's heading with document furniture in between.
2. classify_reference_stub: broadly detect short bodies that are pointers
   ("refer to Note 14", "reference is made to the Financial Section",
   proxy incorporation with any word order) rather than substantive content.
3. detect_appended_section_cut: stop the terminal item from swallowing an
   appended, non-item Financial Section / annual-report body (the JPM/XOM
   "wrapper 10-K" pattern — the Intel/Citi-style corner case).

Every refinement is explainable: callers record what was trimmed / why a
body was reclassified, so nothing is silently altered.
"""

from __future__ import annotations

import re

from sec_core.normalize import NormalizedDocument

# --- 1. trailing furniture -------------------------------------------------
_PART_RE = re.compile(r"^part\s+[ivxlcdm]+\.?$", re.IGNORECASE)
_PAGE_RE = re.compile(r"^\d{1,4}\.?$")  # bare page number, optionally "24."
_TOC_RE = re.compile(r"^table of contents$", re.IGNORECASE)
_STRAY_ITEM_RE = re.compile(r"^item\s+\d{1,2}[a-c]?\.?$", re.IGNORECASE)
_FORM10K_RE = re.compile(r"form\s+10-?k", re.IGNORECASE)
# a running header/footer with a page number at either end, e.g.
# "The Procter & Gamble Company 71"  or  "66 The Procter & Gamble Company"
_RUNNING_HEADER_NUM_RE = re.compile(
    r"^[A-Z0-9].{0,55}?[A-Za-z)]\s+\d{1,4}$|^\d{1,4}\s+[A-Z][A-Za-z0-9 .,&'()\-]{0,54}$")
_ENTITY_WORD_RE = re.compile(r"\b(company|corporation|inc|corp|incorporated|report|"
                             r"form\s?10-?k|subsidiaries|holdings|group|l\.?p\.?)\b", re.IGNORECASE)
# financial-statement / table captions that precede a table (not item prose)
_CAPTION_RE = re.compile(r"^\(?\s*(amounts?\s+(are\s+)?in|dollars?\s+in|in)\s+"
                         r"(millions|thousands|billions)\b", re.IGNORECASE)
# a bare company-name running header (any case), e.g. "AT&T Inc." / "Apple Inc."
_COMPANY_LINE_RE = re.compile(
    r"^[A-Z0-9][A-Za-z0-9 &.,'()\-]{0,45}\b"
    r"(inc|corp|corporation|company|co|plc|ltd|limited|l\.?p\.?|holdings|group|n\.?v\.?)\.?$",
    re.IGNORECASE)


def _is_furniture(line: str) -> bool:
    if (_PART_RE.match(line) or _PAGE_RE.match(line) or _TOC_RE.match(line)
            or _STRAY_ITEM_RE.match(line)):
        return True
    if len(line) < 80 and _FORM10K_RE.search(line):
        return True
    letters = [c for c in line if c.isalpha()]
    if (letters and len(line) < 70
            and sum(c.isupper() for c in letters) / len(letters) > 0.9
            and (line.rstrip(".").endswith(("SUBSIDIARIES", "INC", "CORP", "COMPANY"))
                 or "|" in line)):
        return True  # company running-header banner, e.g. 'THE GOLDMAN SACHS GROUP, INC. AND SUBSIDIARIES'
    # mixed-case running header ending in a page number: short, ≤7 words, no
    # sentence punctuation, and looks like an entity/report line — e.g.
    # "The Procter & Gamble Company 71". Requires an entity cue so we never eat
    # a real sentence that happens to end in a number.
    if (len(line) < 60 and _RUNNING_HEADER_NUM_RE.match(line)
            and len(line.split()) <= 7 and "," not in line
            and "." not in line[:-3] and _ENTITY_WORD_RE.search(line)):
        return True
    if len(line) < 120 and _CAPTION_RE.match(line):
        return True  # table caption ("Amounts in millions of dollars ...")
    if (len(line) < 45 and len(line.split()) <= 5 and "," not in line
            and _COMPANY_LINE_RE.match(line)):
        return True  # bare company-name running header, e.g. "AT&T Inc."
    return False


def trim_trailing_furniture(doc: NormalizedDocument, start: int, end: int) -> tuple[int, list[str]]:
    """Move `end` back past trailing page furniture. Never trims the heading
    line (the loop stops at the first substantive line)."""
    lines_in = [ln for ln in doc.lines if ln.start >= start and ln.end <= end]
    new_end = end
    trimmed: list[str] = []
    for ln in reversed(lines_in):
        txt = ln.text.strip()
        if not txt:
            new_end = ln.start
            continue
        if _is_furniture(txt):
            trimmed.append(txt[:60])
            new_end = ln.start
            continue
        break
    return new_end, list(reversed(trimmed))


# --- 2. reference-stub bodies ----------------------------------------------
_REF_CUE = re.compile(
    r"incorporat\w*\b[\w,'&\-.\s]{0,40}?\bby\s+reference"
    r"|reference\s+is\s+made\b"
    r"|refer\s+to\s+(?:the|note|item|part|section|our|page)\b"
    r"|(?:see|set\s+forth\s+in|appears?\s+in|appear\s+on|included\s+in|contained\s+in|"
    r"described\s+in|discussed\s+in|are\s+set\s+forth\s+in|is\s+set\s+forth\s+in)\b"
    r"[\w,'&\-.\s\"“”]{0,90}?\b(?:note\s+\d|item\s+\d|part\s+[ivx]|financial\s+section|"
    r"consolidated\s+financial|index\s+to|proxy\s+statement|annual\s+report|"
    r"management['’]s\s+discussion|pages?\s+\d)",
    re.IGNORECASE,
)

_STUB_MAX_BODY = 900  # substantive Item 1A/7 run tens of thousands of chars


def classify_reference_stub(body: str) -> str | None:
    """If `body` (text after the heading, stripped) is a short pointer rather
    than real content, return a description of its target; else None."""
    if not body or len(body) > _STUB_MAX_BODY:
        return None
    if not _REF_CUE.search(body):
        return None
    return _describe_target(body)


def _describe_target(body: str) -> str:
    if re.search(r"proxy\s+statement", body, re.IGNORECASE):
        return "the definitive proxy statement (external document, not fetched)"
    if re.search(r"financial\s+section", body, re.IGNORECASE):
        return "the appended Financial Section of this filing"
    if re.search(r"annual\s+report", body, re.IGNORECASE):
        return "the annual report / financial statements bound in this filing"
    m = re.search(r"note\s+\d+", body, re.IGNORECASE)
    if m:
        return f"a financial-statement note ({m.group(0)}) elsewhere in this filing"
    m = re.search(r"item\s+\d+[a-c]?", body, re.IGNORECASE)
    if m:
        return f"another item ({m.group(0)}) in this filing"
    m = re.search(r"pages?\s+\d+\s*[-–]\s*\d+", body, re.IGNORECASE)
    if m:
        return f"a page range ({m.group(0)}) of this filing"
    return "content located elsewhere in this filing"


_NONE_RE = re.compile(r"^(none|not\s+applicable|not\s+applicable\.|none\.|reserved)\.?$", re.IGNORECASE)


def is_boilerplate_none(body: str) -> bool:
    return bool(_NONE_RE.match(body.strip()))


# --- 3. appended non-item section (terminal runaway) -----------------------
# Hard section break: a new document section starts here — cut as soon as it
# appears (XOM binds a "FINANCIAL SECTION" right after Item 16's "None.").
_HARD_BREAK_RE = re.compile(r"^\s*financial\s+section\s*$", re.IGNORECASE | re.MULTILINE)
# Financial-statement body markers: keep a plausible item body (e.g. a real
# Item 15 exhibit list) before cutting (JPM binds the annual report after
# Item 15's exhibit list).
_SOFT_BREAK_RE = re.compile(
    r"^\s*(?:index\s+to\s+financial\s+statements"
    r"|report\s+of\s+independent\s+registered\s+public\s+accounting\s+firm"
    r"|management['’]s\s+discussion\s+and\s+analysis\s+of\s+financial\s+condition"
    r"|consolidated\s+(?:statements?|balance\s+sheets?|statement)\s+of"
    r"|glossary\s+of\s+terms)\b",
    re.IGNORECASE | re.MULTILINE,
)

_RUNAWAY_THRESHOLD = 20_000   # a terminal item this large is swallowing appended content
_SOFT_MIN_BODY = 1000


def detect_appended_section_cut(doc: NormalizedDocument, start: int, end: int) -> int | None:
    """For the terminal item only: if an appended non-item section (the bound
    financial report / annual report) begins after the item's real body,
    return the offset to cut at so the item does not swallow it. Only fires on
    a runaway-sized terminal span, so a normal short 'None.' Item 16 or a
    modest Item 15 exhibit list is never touched."""
    if end - start < _RUNAWAY_THRESHOLD:
        return None
    region = doc.text[start:end]
    hard = _HARD_BREAK_RE.search(region)
    if hard and hard.start() >= 20:
        return start + hard.start()
    for m in _SOFT_BREAK_RE.finditer(region):
        if m.start() >= _SOFT_MIN_BODY:
            return start + m.start()
    return None
