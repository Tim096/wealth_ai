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
  engine_unavailable — edgartools could not parse the filing / lacks the
                       item; NOT evidence against our extraction
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


@dataclass
class EngineComparison:
    item_code: str
    verdict: str  # agree | disagree | engine_unavailable
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
                 our_status: str, combined: bool = False) -> EngineComparison:
    ours, theirs = _words(our_text), _words(engine_text)

    if not theirs:
        if not ours:
            return EngineComparison(code, "agree", "both engines find no content for this item")
        return EngineComparison(
            code, "engine_unavailable",
            f"edgartools produced no item {code}; absence there is not evidence against our span",
            our_words=len(ours))

    if not ours:
        if our_status == "reserved" and len(theirs) < 30:
            return EngineComparison(code, "agree",
                                    "both engines treat this item as reserved/absent",
                                    engine_words=len(theirs))
        return EngineComparison(
            code, "disagree",
            f"we extracted nothing (status={our_status}) but edgartools extracted "
            f"{len(theirs)} words — possible missed item",
            engine_words=len(theirs))

    shorter, longer = (ours, theirs) if len(ours) <= len(theirs) else (theirs, ours)
    overlap = _containment(shorter, longer)
    ratio = len(shorter) / len(longer)

    if overlap < _OVERLAP_MIN:
        return EngineComparison(
            code, "disagree",
            f"content mismatch: only {overlap:.0%} of the shorter span's text appears in the "
            f"longer one (ours {len(ours)}w vs edgartools {len(theirs)}w)",
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
    flags needs_review. engine_unavailable never penalises our extraction.
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
        if cmp.verdict == "disagree":
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
