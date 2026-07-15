"""HTML -> normalized text with exact raw-offset mapping (SPEC 7.7).

Every character of normalized text knows its raw HTML offset, so any span we
extract is provably a source exact span. Built on html.parser with
convert_charrefs=False so data chunks are verbatim raw substrings and the
mapping stays exact even through entity references.
"""

from __future__ import annotations

import re
from array import array
from dataclasses import dataclass, field
from html import unescape
from html.parser import HTMLParser

NORMALIZATION_VERSION = "1.1"
"""Contract version for normalize_html's output. Item offsets and sha256 are only
independently verifiable against a KNOWN normalizer revision, so this is stamped
on the /normalized download and each item's normalized_sha. Bump whenever the
normalized output for the SAME raw HTML could change (char map, block/cell tags,
entity handling, TOC-backlink stripping).

1.1 — added text mode (see looks_like_plain_text): a document with no meaningful
HTML block structure keeps the newlines of its TEXT nodes instead of having them
collapsed to spaces. Changes normalized output for plain-text/SGML filings ONLY;
HTML-era output is byte-identical to 1.0."""

BLOCK_TAGS = {
    "p", "div", "br", "tr", "li", "table", "section", "article",
    "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "hr", "center",
}
BOLD_TAGS = {"b", "strong"}
HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
CELL_TAGS = {"td", "th"}  # table cells — separate so labels don't glue to values
SKIP_TAGS = {"script", "style"}

FLAG_BOLD = 1
FLAG_HEADING = 2
FLAG_TOC_LINK = 4  # inside <a href="#..."> — an internal anchor link

_CHAR_MAP = {
    "\xa0": " ",
    "–": "-",  # en dash
    "—": "-",  # em dash
    "−": "-",  # minus
    "‘": "'",
    "’": "'",
    "“": '"',
    "”": '"',
}


_ALNUM_RE = re.compile(r"[^a-z0-9]+")

# --- plain-text / SGML detection (the pre-2001 era) -------------------------
# A pre-2001 EDGAR filing is plain text inside a thin SGML envelope
# (<SEC-DOCUMENT>, <TYPE>, <TEXT>): ALL of its structure — headings, paragraphs,
# tables — lives in its NEWLINES. An HTML filing carries structure in block tags
# instead and its raw newlines are meaningless minifier artifacts. Emitting
# newlines for text-node "\n" is therefore right for the first class and wrong
# for the second, so we must tell them apart before parsing.
#
# The discriminator is block tags per raw newline. Measured over the whole
# fixture corpus the two classes are separated by ~250x, with no middle ground:
#   plain text : AAPL_FY1996 0.004, KO_FY1997 0.003, strats_trust 0.004
#   html       : corts 0.50, beta 0.44, alpha 0.61, MSFT 0.95, KO/AAPL/NEM/JPM >275
# The 0.1 cut sits in the empty gap: >25x margin above the text class, >4x below
# the closest HTML document. The newline floor keeps tiny synthetic snippets
# (which have neither structure) on the unchanged HTML path.
_BLOCK_TAG_SCAN_RE = re.compile(r"<\s*(?:p|div|br|tr|table|li|h[1-6])\b", re.IGNORECASE)
_TEXT_MODE_MIN_NEWLINES = 50
_TEXT_MODE_MAX_BLOCK_RATIO = 0.1


def looks_like_plain_text(raw: str) -> bool:
    """True when `raw` is substantially plain text / SGML rather than HTML —
    i.e. it has no meaningful HTML block structure, so its line structure is the
    only structure it has and must be preserved verbatim."""
    newlines = raw.count("\n")
    if newlines < _TEXT_MODE_MIN_NEWLINES:
        return False
    blocks = len(_BLOCK_TAG_SCAN_RE.findall(raw))
    return blocks < newlines * _TEXT_MODE_MAX_BLOCK_RATIO

# Table-of-contents navigation backlink phrases (delivery-layer furniture). A
# whole line whose text is one of these AND sits entirely inside an internal
# anchor (<a href="#...">, FLAG_TOC_LINK) is the "Table of Contents" backlink
# that filings repeat at every page break to jump back to the index. This is
# pagination navigation, not item content — edgar_crawler strips the same class
# in its clean_text (TABLE OF CONTENTS | BACK TO CONTENTS | ...). We strip ONLY
# this anchor-backed navigation class, never arbitrary recurring lines or
# financial boilerplate (broad recurring-line stripping eats real content).
_TOC_BACKLINK_PHRASES = frozenset({
    "tableofcontents",
    "backtocontents",
    "backtotableofcontents",
    "returntocontents",
    "returntotableofcontents",
})


@dataclass
class Line:
    start: int
    end: int
    text: str


@dataclass
class NormalizedDocument:
    raw_html: str
    text: str
    norm_to_raw: array  # raw offset for each normalized char
    flags: bytearray  # FLAG_* bits per normalized char
    anchor_targets: dict[str, int]  # element id/name -> normalized offset
    lines: list[Line] = field(default_factory=list)

    def raw_offset(self, norm_offset: int) -> int:
        if norm_offset >= len(self.norm_to_raw):
            return len(self.raw_html)
        return self.norm_to_raw[norm_offset]

    def slice(self, start: int, end: int) -> str:
        """Source-exact span [start, end): the provenance record. Offsets,
        sha256 and coverage are computed against this — never against clean_slice."""
        return self.text[start:end]

    def _is_toc_backlink_line(self, line: Line) -> bool:
        """A table-of-contents navigation backlink line (see _TOC_BACKLINK_PHRASES):
        its whole text is a TOC nav phrase and every non-space char is inside an
        internal anchor. Genuine 'TABLE OF CONTENTS' section headings (not anchors)
        and item headings ('Item 1.') are excluded by construction."""
        if _ALNUM_RE.sub("", line.text.lower()) not in _TOC_BACKLINK_PHRASES:
            return False
        anchored = False
        for offset in range(line.start, line.end):
            if self.text[offset].isspace():
                continue
            if not (self.flags[offset] & FLAG_TOC_LINK):
                return False
            anchored = True
        return anchored

    def clean_slice(self, start: int, end: int) -> str:
        """Delivery-layer materialization of [start, end): the source-exact slice
        with table-of-contents navigation backlink lines removed. This is a
        derived clean view for downstream consumption — slice() remains the raw
        provenance span (offsets / sha256 / coverage are unchanged)."""
        if start >= end:
            return self.text[start:end]
        drops: list[tuple[int, int]] = []  # absolute [ln.start, drop_end) to remove
        for ln in self.lines:
            if ln.end <= start:
                continue
            if ln.start >= end:
                break
            if ln.start >= start and ln.end <= end and self._is_toc_backlink_line(ln):
                # also drop the trailing newline so neighbours don't gain a blank line
                drop_end = ln.end + 1 if ln.end < end and self.text[ln.end] == "\n" else ln.end
                drops.append((ln.start, drop_end))
        if not drops:
            return self.text[start:end]
        out: list[str] = []
        cur = start
        for ds, de in drops:
            out.append(self.text[cur:ds])
            cur = de
        out.append(self.text[cur:end])
        return "".join(out)


class _Normalizer(HTMLParser):
    def __init__(self, text_mode: bool = False) -> None:
        super().__init__(convert_charrefs=False)
        # text mode: a "\n" inside a TEXT node is a real line break, not
        # collapsible whitespace (see looks_like_plain_text)
        self._text_mode = text_mode
        self.chars: list[str] = []
        self.offsets = array("q")
        self.flags = bytearray()
        self.anchor_targets: dict[str, int] = {}
        self._line_starts: list[int] = []
        self._raw = ""
        self._skip_depth = 0
        self._bold_depth = 0
        self._heading_depth = 0
        self._anchor_href_stack: list[str] = []
        self._pending_space = False
        self._at_line_start = True

    # -- offset bookkeeping -------------------------------------------------
    def feed_document(self, raw: str) -> None:
        self._raw = raw
        pos = 0
        self._line_starts = [0]
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

    # -- emission -----------------------------------------------------------
    def _current_flags(self) -> int:
        f = 0
        if self._bold_depth:
            f |= FLAG_BOLD
        if self._heading_depth:
            f |= FLAG_HEADING
        if any(h.startswith("#") for h in self._anchor_href_stack):
            f |= FLAG_TOC_LINK
        return f

    def _emit(self, char: str, raw_offset: int) -> None:
        self.chars.append(char)
        self.offsets.append(raw_offset)
        self.flags.append(self._current_flags())

    def _emit_text(self, decoded: str, raw_offset: int) -> None:
        if self._skip_depth:
            return
        for i, c in enumerate(decoded):
            # In text mode the document's structure IS its newlines: emit the
            # line break and address it by the raw offset of the newline it came
            # from, so norm_to_raw stays exact (an HTML-mode newline is emitted
            # by a tag and addressed by that tag's position instead).
            if c == "\n" and self._text_mode:
                self._emit_newline_at(raw_offset + i)
                continue
            c = _CHAR_MAP.get(c, c)
            if c.isspace():
                self._pending_space = True
                continue
            if self._pending_space and not self._at_line_start:
                self._emit(" ", raw_offset + i)
            self._pending_space = False
            self._at_line_start = False
            self._emit(c, raw_offset + i)

    def _emit_newline_at(self, raw_offset: int) -> None:
        if not self._at_line_start:
            self._emit("\n", raw_offset)
            self._at_line_start = True
        self._pending_space = False

    def _emit_newline(self) -> None:
        self._emit_newline_at(self._abs_pos())

    # -- parser hooks ---------------------------------------------------------
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_d = {k: (v or "") for k, v in attrs}
        anchor_id = attrs_d.get("id") or (attrs_d.get("name") if tag == "a" else None)
        if anchor_id:
            self.anchor_targets.setdefault(anchor_id, len(self.chars))
        if tag in SKIP_TAGS:
            self._skip_depth += 1
        elif tag in BLOCK_TAGS:
            self._emit_newline()
        if tag in BOLD_TAGS:
            self._bold_depth += 1
        if tag in HEADING_TAGS:
            self._heading_depth += 1
        if tag == "a":
            self._anchor_href_stack.append(attrs_d.get("href", ""))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag in BLOCK_TAGS:
            self._emit_newline()
        elif tag in CELL_TAGS:
            # separate this cell from the next so "Cost of revenue$261" -> "... $261"
            self._pending_space = True
        if tag in BOLD_TAGS:
            self._bold_depth = max(0, self._bold_depth - 1)
        if tag in HEADING_TAGS:
            self._heading_depth = max(0, self._heading_depth - 1)
        if tag == "a" and self._anchor_href_stack:
            self._anchor_href_stack.pop()

    def handle_data(self, data: str) -> None:
        self._emit_text(data, self._abs_pos())

    def handle_entityref(self, name: str) -> None:
        self._emit_text(unescape(f"&{name};"), self._abs_pos())

    def handle_charref(self, name: str) -> None:
        self._emit_text(unescape(f"&#{name};"), self._abs_pos())


def normalize_html(raw_html: str) -> NormalizedDocument:
    parser = _Normalizer(text_mode=looks_like_plain_text(raw_html))
    parser.feed_document(raw_html)
    text = "".join(parser.chars)

    doc = NormalizedDocument(
        raw_html=raw_html,
        text=text,
        norm_to_raw=parser.offsets,
        flags=parser.flags,
        anchor_targets=parser.anchor_targets,
    )
    start = 0
    for i, c in enumerate(text):
        if c == "\n":
            doc.lines.append(Line(start=start, end=i, text=text[start:i]))
            start = i + 1
    if start < len(text):
        doc.lines.append(Line(start=start, end=len(text), text=text[start:]))
    return doc
