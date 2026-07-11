"""Third-engine triangulation — edgartools as an INDEPENDENT second codebase
(TODO T2-1). Rule-based item segmentation leaves ~10% error on hard items
(GPT4ItemSeg, arxiv 2502.08875), and our own detectors share one codebase's
blind spots. edgartools (MIT, independently maintained) extracts the same
items from the same raw HTML with a different parser; where the two engines
disagree, the span cannot be trusted at full confidence.

This is an opt-in pass like xbrl_check / topic_check: it runs at the call
site (tools/triangulate.py), never inside extract_from_html — the core
pipeline stays deterministic and dependency-light. edgartools never
manufactures our filing text; it only votes on agreement. Verdicts:

  agree              — the engines extracted the same content
  disagree           — content or boundary mismatch -> confidence deduction
                       + needs_review
  engine_suspect     — disagreement inside edgartools' KNOWN blind class
                       (items 10-16 rescued from the TOC because its
                       _ITEM_TITLE_PATTERNS stop at 9C in the pinned 5.42.0;
                       FG-SEC-006) where the engine text itself looks like
                       TOC junk; recorded, but NOT a penalty against our span
  engine_unavailable — edgartools could not parse the filing / lacks the
                       item; NOT evidence against our extraction

compare_item also has a source-aware mode (source="corpus") for EDGAR-CORPUS
teacher votes: the corpus was built by edgar-crawler with remove_tables=True,
so our span legitimately contains far more words (tables). Corpus votes are
content-level only — containment of the table-stripped corpus text in our
span — never a length-ratio boundary vote (that would systematically flag
Item 8 as disagree).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sec_core.confidence import ConfidenceComponent
from sec_core.headings import VALID_CODES

_WORD_RE = re.compile(r"[a-z0-9]+")
_SHINGLE = 8          # words per shingle
_OVERLAP_MIN = 0.6    # shorter-in-longer shingle containment to count as same content
_RATIO_MIN = 0.35     # min/max word-count ratio below which boundaries diverge
_FURNITURE_SLACK = 40  # word-count delta edgartools' untrimmed page furniture may add
COMPONENT_NAME = "third_engine_agreement"

# --- engine-blind class (P0-5) ----------------------------------------------
# edgartools 5.42.0 (pinned in pyproject) has _ITEM_TITLE_PATTERNS ending at
# 9C; items 10-16 go through a TOC-based rescue path that misattributes
# sections (FG-SEC-006: NEM/NVDA/WMT item 16 filled with Item 1 TOC lines /
# unrelated body text). A disagreement there, when the ENGINE text looks like
# TOC junk, is evidence against the engine, not against our span. The gate is
# version-pinned: on an edgartools upgrade the down-weighting rationale must
# be re-verified, so an unexpected version disables the gate (falls back to
# plain disagree).
_ENGINE_BLIND_ITEMS = {"10", "11", "12", "13", "14", "15", "16"}
_ENGINE_BLIND_VERSION_PREFIX = "5.42"
_ITEM_REF_RE = re.compile(r"\bitem\s{0,3}(\d{1,2}[a-c]?)\b", re.IGNORECASE)
_TOC_REF_DENSITY = 0.02  # item-heading references per word to call it TOC junk
# TOC rendering glues page numbers to the next heading ('BUSINESS6Introduction6
# Segment Information6Products6...'); prose never does. Second junk signal.
_TOC_GLUE_RE = re.compile(r"[A-Za-z]\d{1,3}[A-Z]")
_TOC_GLUE_DENSITY = 0.1  # glued heading<page#>Heading transitions per word
_engine_version_cache: str | None = None


def _edgartools_version() -> str:
    global _engine_version_cache
    if _engine_version_cache is None:
        try:
            import edgar
            _engine_version_cache = str(getattr(edgar, "__version__", ""))
        except Exception:  # noqa: BLE001 — no engine, no blind-class gate
            _engine_version_cache = ""
    return _engine_version_cache


def _looks_like_toc_junk(text: str) -> bool:
    """TOC junk = a span that is mostly a table of contents: it references
    several OTHER items ('ITEM 1.BUSINESS6Introduction6...') at high density.
    Ordinary prose cross-references ('see Item 7A') never reach the density.

    Second signal: the real FG-SEC-006 fragments (NEM item 16 = Item 1 TOC
    lines) may reference only ONE other item, but carry the TOC rendering
    signature of page numbers glued between headings
    ('BUSINESS6Introduction6Segment Information6Products6...')."""
    n_words = max(len(_words(text)), 1)
    refs = _ITEM_REF_RE.findall(text)
    if (len({r.upper() for r in refs}) >= 3
            and len(refs) / n_words >= _TOC_REF_DENSITY):
        return True
    glued = _TOC_GLUE_RE.findall(text)
    return len(glued) >= 3 and len(glued) / n_words >= _TOC_GLUE_DENSITY


def _blind_class_suspect(code: str, engine_text: str, source: str,
                         engine_version: str | None) -> bool:
    if source != "edgartools" or code not in _ENGINE_BLIND_ITEMS:
        return False
    version = engine_version if engine_version is not None else _edgartools_version()
    if not version.startswith(_ENGINE_BLIND_VERSION_PREFIX):
        return False
    return _looks_like_toc_junk(engine_text)


@dataclass
class EngineComparison:
    item_code: str
    verdict: str  # agree | disagree | engine_suspect | engine_unavailable
    detail: str
    our_words: int = 0
    engine_words: int = 0
    overlap: float = 0.0


def extract_items_edgartools(raw_html: str) -> dict[str, str] | None:
    """Run edgartools' offline HTML parser on the SAME raw bytes our pipeline
    consumed. Returns item_code -> text, or None when the engine cannot parse
    the filing at all (engine_unavailable, not our failure). No network.
    """
    try:
        from edgar.documents import ParserConfig, parse_html

        doc = parse_html(raw_html, ParserConfig(form="10-K"))
        items: dict[str, str] = {}
        for _, sec in doc.sections.items():
            code = (sec.item or "").upper()
            if code not in VALID_CODES:
                continue
            text = sec.text() if callable(sec.text) else sec.text
            if not text or not text.strip():
                continue
            # Part I/II item-number collisions (edgartools issue #454): keep
            # the longer body rather than silently overwriting.
            if code in items and len(items[code]) >= len(text):
                continue
            items[code] = text
        return items or None
    except Exception:  # noqa: BLE001 — a third-party crash is engine_unavailable
        return None


def _words(text: str) -> list[str]:
    """Alphanumeric-only words: robust to whitespace, &nbsp;, curly quotes and
    encoding mojibake that differ between the two engines' text serializers."""
    return _WORD_RE.findall(text.lower())


def _shingle_set(words: list[str]) -> set[tuple[str, ...]]:
    if len(words) <= _SHINGLE:
        return {tuple(words)} if words else set()
    return {tuple(words[i:i + _SHINGLE]) for i in range(len(words) - _SHINGLE + 1)}


def _containment(inner: list[str], outer: list[str]) -> float:
    """Fraction of `inner`'s shingles found verbatim in `outer`. A text shorter
    than one shingle ("Not applicable.") falls back to substring containment —
    otherwise it could never match any full-length shingle of `outer`."""
    if not inner:
        return 0.0
    if len(inner) < _SHINGLE:
        return 1.0 if " ".join(inner) in " ".join(outer) else 0.0
    inner_sh = _shingle_set(inner)
    outer_sh = _shingle_set(outer)
    return sum(1 for s in inner_sh if s in outer_sh) / len(inner_sh)


def compare_item(code: str, our_text: str, engine_text: str,
                 our_status: str, combined: bool = False,
                 source: str = "edgartools",
                 engine_version: str | None = None) -> EngineComparison:
    """source="edgartools" (default): full content+boundary comparison with the
    engine-blind-class gate (P0-5). source="corpus": EDGAR-CORPUS teacher vote
    — table-stripped text, content-level containment only (see module doc).
    engine_version overrides the installed edgartools version (tests)."""
    ours, theirs = _words(our_text), _words(engine_text)

    if not theirs:
        if not ours:
            return EngineComparison(code, "agree", "both engines find no content for this item")
        return EngineComparison(
            code, "engine_unavailable",
            f"{source} produced no item {code}; absence there is not evidence against our span",
            our_words=len(ours))

    if not ours:
        if our_status == "reserved" and len(theirs) < 30:
            return EngineComparison(code, "agree",
                                    "both engines treat this item as reserved/absent",
                                    engine_words=len(theirs))
        if _blind_class_suspect(code, engine_text, source, engine_version):
            return EngineComparison(
                code, "engine_suspect",
                f"edgartools ({_ENGINE_BLIND_VERSION_PREFIX}.x pinned) filled item {code} with "
                f"TOC-junk text ({len(theirs)}w) — its _ITEM_TITLE_PATTERNS end at 9C and "
                f"items 10-16 are rescued from the TOC (FG-SEC-006); not evidence against our "
                f"status={our_status}; re-verify on engine upgrade",
                engine_words=len(theirs))
        return EngineComparison(
            code, "disagree",
            f"we extracted nothing (status={our_status}) but {source} extracted "
            f"{len(theirs)} words — possible missed item",
            engine_words=len(theirs))

    if source == "corpus":
        # corpus text has tables removed at build time (edgar-crawler
        # remove_tables=True): only containment of THEIR text in OURS is
        # meaningful; a length-ratio check would systematically flag
        # table-heavy items (Item 8) as boundary disagreements.
        containment = _containment(theirs, ours)
        if len(theirs) - len(ours) > _FURNITURE_SLACK:
            # table removal only ever SHRINKS text: a corpus section longer
            # than our span (beyond furniture slack) means we truncated.
            return EngineComparison(
                code, "disagree",
                f"our span ({len(ours)}w) is shorter than the corpus (table-stripped) text "
                f"({len(theirs)}w) — table removal only shrinks text, so we truncated",
                our_words=len(ours), engine_words=len(theirs), overlap=containment)
        if containment >= _OVERLAP_MIN:
            return EngineComparison(
                code, "agree",
                f"corpus (table-stripped) text is contained in our span "
                f"({containment:.0%} containment; length delta attributed to tables)",
                our_words=len(ours), engine_words=len(theirs), overlap=containment)
        return EngineComparison(
            code, "disagree",
            f"content mismatch: only {containment:.0%} of the corpus (table-stripped) text "
            f"appears in our span (ours {len(ours)}w vs corpus {len(theirs)}w)",
            our_words=len(ours), engine_words=len(theirs), overlap=containment)

    shorter, longer = (ours, theirs) if len(ours) <= len(theirs) else (theirs, ours)
    overlap = _containment(shorter, longer)
    ratio = len(shorter) / len(longer)

    if overlap < _OVERLAP_MIN:
        if _blind_class_suspect(code, engine_text, source, engine_version):
            return EngineComparison(
                code, "engine_suspect",
                f"edgartools ({_ENGINE_BLIND_VERSION_PREFIX}.x pinned) item {code} is TOC-junk "
                f"text ({overlap:.0%} containment vs our {len(ours)}w span) — its "
                f"_ITEM_TITLE_PATTERNS end at 9C and items 10-16 are rescued from the TOC "
                f"(FG-SEC-006); engine-side misattribution, not counted against our span; "
                f"re-verify on engine upgrade",
                our_words=len(ours), engine_words=len(theirs), overlap=overlap)
        return EngineComparison(
            code, "disagree",
            f"content mismatch: only {overlap:.0%} of the shorter span's text appears in the "
            f"longer one (ours {len(ours)}w vs {source} {len(theirs)}w)",
            our_words=len(ours), engine_words=len(theirs), overlap=overlap)

    if combined and _containment(theirs, ours) >= _OVERLAP_MIN:
        return EngineComparison(
            code, "agree",
            f"combined span contains edgartools' item body ({overlap:.0%} containment)",
            our_words=len(ours), engine_words=len(theirs), overlap=overlap)

    if ratio < _RATIO_MIN:
        # edgartools does not trim trailing page furniture (running headers,
        # page numbers), so a tiny "Not applicable." item legitimately differs
        # by a few dozen words. Only a delta beyond that slack is a boundary
        # dispute.
        if len(longer) - len(shorter) <= _FURNITURE_SLACK:
            return EngineComparison(
                code, "agree",
                f"same content; length delta {len(longer) - len(shorter)}w is within "
                f"page-furniture slack",
                our_words=len(ours), engine_words=len(theirs), overlap=overlap)
        return EngineComparison(
            code, "disagree",
            f"boundary mismatch: same content but ours {len(ours)}w vs edgartools "
            f"{len(theirs)}w (ratio {ratio:.2f}) — one engine's span runs long or cuts short",
            our_words=len(ours), engine_words=len(theirs), overlap=overlap)

    return EngineComparison(
        code, "agree",
        f"{overlap:.0%} shingle containment, length ratio {ratio:.2f}",
        our_words=len(ours), engine_words=len(theirs), overlap=overlap)


def apply_triangulation(result, engine_items: dict[str, str] | None) -> list[EngineComparison]:
    """Compare every segment against the third engine and WRITE verdicts back
    (segment.engine_check, mirroring xbrl_check/topic_check). A disagree
    deducts confidence through the explainable component framework — a zero-
    scored `third_engine_agreement` component appended to the breakdown — and
    flags needs_review. engine_unavailable never penalises our extraction, and
    neither does engine_suspect (edgartools' pinned-version blind class for
    items 10-16, FG-SEC-006): it is recorded as a warning for audit, without
    confidence deduction or needs_review.
    """
    comparisons: list[EngineComparison] = []
    for seg in result.segments:
        if engine_items is None:
            seg.engine_check = "engine_unavailable: edgartools could not parse this filing"
            comparisons.append(EngineComparison(
                seg.item_code, "engine_unavailable", "edgartools could not parse this filing"))
            continue
        our_text = (result.doc.slice(seg.start_offset, seg.end_offset)
                    if seg.end_offset > seg.start_offset else "")
        combined = any(w.startswith("combined heading") for w in seg.warnings)
        cmp = compare_item(seg.item_code, our_text, engine_items.get(seg.item_code, ""),
                           seg.status, combined=combined)
        seg.engine_check = f"{cmp.verdict}: {cmp.detail}"
        if cmp.verdict == "engine_suspect":
            note = f"third-engine triangulation: engine-blind class — {cmp.detail}"
            if note not in seg.warnings:
                seg.warnings.append(note)
        elif cmp.verdict == "disagree":
            seg.needs_review = True
            seg.warnings.append(
                f"third-engine triangulation: edgartools disagrees — {cmp.detail}; needs_review")
            breakdown = result.confidence.get(seg.item_code)
            if breakdown is not None:
                if not any(c.name == COMPONENT_NAME for c in breakdown.components):
                    breakdown.components.append(ConfidenceComponent(
                        name=COMPONENT_NAME, score=0.0, max_score=1.0,
                        reason=f"independent engine (edgartools) disagrees: {cmp.detail}"))
                seg.confidence = breakdown.total
            else:
                seg.confidence = max(0.0, seg.confidence - 0.15)
        comparisons.append(cmp)
    return comparisons
