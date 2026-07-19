"""Main document detector (SPEC 7.6): scores every file in a filing package
and picks the primary 10-K HTML. Every score is itemized so the choice is
explainable and debuggable when it goes wrong.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from sec_core.resolver import FilingFile, FilingRef

_ITEM_SIGNAL_RE = re.compile(r"item\s*(?:1a|7|8)\b", re.IGNORECASE)


@dataclass
class DocScore:
    name: str
    score: float
    reasons: list[str] = field(default_factory=list)


def _score_file(f: FilingFile, max_size: int, content_peek: str | None,
                primary_document: str) -> DocScore:
    s = DocScore(name=f.name, score=0.0)
    lname = f.name.lower()

    def add(points: float, reason: str) -> None:
        s.score += points
        s.reasons.append(f"{'+' if points >= 0 else ''}{points}: {reason}")

    if not lname.endswith((".htm", ".html", ".txt")):
        add(-5.0, "not an HTML/TXT document")
    if f.doc_type.upper() in ("10-K", "10-K/A"):
        add(4.0, f"document type is {f.doc_type}")
    if primary_document and f.name == primary_document:
        add(3.0, "listed as primaryDocument in submissions index")
    if re.search(r"10-?k", lname) and "ex" not in lname.split(".")[0][:2]:
        add(2.0, "filename suggests form 10-K")
    if max_size > 0 and f.size == max_size:
        add(2.0, "largest document in package")
    if re.match(r"^ex[-_.\d]", lname) or "exhibit" in lname:
        add(-4.0, "exhibit")
    if lname.endswith((".xml", ".xsd", ".jpg", ".png", ".gif", ".css", ".js")):
        add(-6.0, "XML/XSD/asset file")
    if "xbrl" in lname or lname.endswith("_htm.xml"):
        add(-3.0, "XBRL artifact")
    if content_peek is not None:
        hits = len(_ITEM_SIGNAL_RE.findall(content_peek))
        if hits >= 2:
            add(3.0, f"content contains {hits} of Item 1A/7/8 signals")
        elif hits == 0 and len(content_peek) < 20_000:
            add(-2.0, "short content without any item signals (cover page?)")
    return s


def score_files(ref: FilingRef, content_peeks: dict[str, str] | None = None) -> list[DocScore]:
    peeks = content_peeks or {}
    max_size = max((f.size for f in ref.files), default=0)
    scores = [
        _score_file(f, max_size, peeks.get(f.name), ref.primary_document)
        for f in ref.files
    ]
    scores.sort(key=lambda s: s.score, reverse=True)
    return scores


def pick_main_document(ref: FilingRef, content_peeks: dict[str, str] | None = None,
                       *, scores: list[DocScore] | None = None) -> DocScore:
    scores = scores if scores is not None else score_files(ref, content_peeks)
    if not scores:
        raise LookupError(f"filing {ref.accession} has no files to score")
    best = scores[0]
    if best.score <= 0:
        raise LookupError(
            f"no plausible main document in {ref.accession}; "
            f"best candidate {best.name} scored {best.score} ({'; '.join(best.reasons)})"
        )
    return best
