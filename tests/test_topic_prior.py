"""Gold-free span content-attribution prior (sec_core/topic_prior.py).

Covers: lexicon build (distinctiveness, generic-token exclusion, min-sample
rule), the corpus-derived margin threshold, the two runtime sub-signals
(misattribution margin / IBR pointer trust cap), their individual
kill-switches, and the invariants shared with length_prior: offsets never
change, confidence is capped through a zero-scored component, missing
artifact leaves the signal inert.
"""

from __future__ import annotations

import json

import pytest

from sec_core.confidence import ConfidenceBreakdown, ConfidenceComponent
from sec_core.items import CANONICAL_ITEM_TITLES, ItemSegment
from sec_core.normalize import normalize_html
from sec_core.topic_prior import (
    MIN_DOC_CHARS,
    MISATTRIBUTION_COMPONENT,
    POINTER_COMPONENT,
    TopicPriors,
    apply_topic_prior,
    attribution,
    build_lexicon,
    build_thresholds,
    coverage,
    load_topic_priors,
    tokenize,
)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

# three item classes so no class token reaches the generic-df fraction, and
# enough distinct tokens per span to clear the MIN_SPAN_TOKENS runtime guard.
# tokenize() keeps alphabetic runs only, so suffixes must be letters.
_SUFFIXES = [a + b for a in "abcdefghij" for b in "abcdefgh"]  # 80 distinct
RISK_WORDS = [f"riskword{s}" for s in _SUFFIXES]
LEGAL_WORDS = [f"legalword{s}" for s in _SUFFIXES]
PROP_WORDS = [f"propword{s}" for s in _SUFFIXES]


def _alien(n: int) -> str:
    """n distinct alphabetic tokens that match no lexicon."""
    suf = [a + b + c for a in "abcdefghij" for b in "abcdefghij" for c in "abcdefghij"]
    return " ".join(f"alien{s}" for s in suf[:n])
COMMON = ["company", "business", "operations", "year", "annual"]


def _span_text(words: list[str], reps: int = 3) -> str:
    return " ".join(words * reps)


def _sample(item: str, words: list[str]) -> dict:
    return {"item": item, "tokens": tokenize(_span_text(words + COMMON)),
            "source": f"test:{item}"}


def _build_samples() -> list[dict]:
    return ([_sample("1A", RISK_WORDS) for _ in range(6)]
            + [_sample("3", LEGAL_WORDS) for _ in range(6)]
            + [_sample("2", PROP_WORDS) for _ in range(6)])


def _priors() -> TopicPriors:
    samples = _build_samples()
    lexicon = build_lexicon(samples)
    tau, _ = build_thresholds(samples, lexicon)
    return TopicPriors(lexicon=lexicon, margin_tau=tau)


def _doc(body_1a: str, body_3: str):
    filler = " ".join(f"pad{i}" for i in range(4000))  # push doc over MIN_DOC_CHARS
    html = (f"<html><body><p>Item 1A. Risk Factors</p><p>{body_1a}</p>"
            f"<p>Item 3. Legal Proceedings</p><p>{body_3}</p>"
            f"<p>APPENDIX</p><p>{filler}</p></body></html>")
    return normalize_html(html)


def _segment(doc, code: str, needle: str, status: str = "pass",
             end: int | None = None) -> ItemSegment:
    start = doc.text.index(needle)
    return ItemSegment(
        filing_id="t", item_code=code,
        canonical_title=CANONICAL_ITEM_TITLES[code],
        extracted_heading=needle, start_offset=start,
        end_offset=end if end is not None else doc.text.index("APPENDIX"),
        text_sha256="x", status=status, confidence=0.9)


def _breakdown() -> ConfidenceBreakdown:
    return ConfidenceBreakdown(components=[
        ConfidenceComponent(name="heading_strength", score=9.0, max_score=10.0,
                            reason="test")])


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------

def test_build_lexicon_is_distinctive_and_drops_generic_tokens():
    lexicon = build_lexicon(_build_samples())
    assert set(lexicon) == {"1A", "3", "2"}
    assert all(t.startswith("legalword") for t in lexicon["3"])
    assert all(t.startswith("riskword") for t in lexicon["1A"])
    for lex in lexicon.values():  # COMMON words appear in every span -> generic
        assert not set(COMMON) & set(lex)


def test_build_lexicon_min_samples_rule():
    samples = _build_samples() + [_sample("5", ["acres", "warehouse"])] * 2
    assert "5" not in build_lexicon(samples)


def test_build_thresholds_shape():
    samples = _build_samples()
    lexicon = build_lexicon(samples)
    tau, rows = build_thresholds(samples, lexicon)
    assert tau >= 0.0
    assert len(rows) == len(samples)
    assert all(0.0 <= r["own"] <= 1.0 and r["tokens"] > 0 for r in rows)


def test_coverage_and_attribution():
    priors = _priors()
    risk_tokens = tokenize(_span_text(RISK_WORDS))
    assert coverage(risk_tokens, priors.lexicon["1A"]) > 0.9
    own, best_code, best_cov = attribution(risk_tokens, priors, "3")
    assert best_code == "1A" and best_cov > own


# ---------------------------------------------------------------------------
# runtime sub-signal (a): misattribution margin
# ---------------------------------------------------------------------------

def test_misattributed_span_is_flagged_and_capped():
    priors = _priors()
    # item 3 span whose body is pure risk-factor language -> reads like 1A
    doc = _doc(_span_text(LEGAL_WORDS), _span_text(RISK_WORDS))
    seg = _segment(doc, "3", "Item 3. Legal Proceedings")
    bd = _breakdown()
    before = (seg.start_offset, seg.end_offset)
    n = apply_topic_prior([seg], doc, priors=priors, breakdowns={"3": bd})
    assert n == 1
    assert seg.needs_review is True
    assert (seg.start_offset, seg.end_offset) == before  # offsets never change
    assert any(c.name == MISATTRIBUTION_COMPONENT and c.score == 0.0
               for c in bd.components)
    assert seg.confidence == pytest.approx(bd.total) and seg.confidence < 0.75


def test_on_topic_span_is_not_flagged():
    priors = _priors()
    doc = _doc(_span_text(RISK_WORDS), _span_text(LEGAL_WORDS))
    segs = [_segment(doc, "1A", "Item 1A. Risk Factors",
                     end=doc.text.index("Item 3.")),
            _segment(doc, "3", "Item 3. Legal Proceedings")]
    assert apply_topic_prior(segs, doc, priors=priors, breakdowns={}) == 0
    assert not segs[0].needs_review and not segs[1].needs_review


def test_margin_kill_switch(monkeypatch):
    monkeypatch.setenv("SEC_TOPIC_PRIOR_MARGIN", "0")
    priors = _priors()
    doc = _doc(_span_text(LEGAL_WORDS), _span_text(RISK_WORDS))
    seg = _segment(doc, "3", "Item 3. Legal Proceedings")
    assert apply_topic_prior([seg], doc, priors=priors, breakdowns={}) == 0
    assert seg.needs_review is False


def test_non_pass_and_small_doc_are_skipped():
    priors = _priors()
    doc = _doc(_span_text(LEGAL_WORDS), _span_text(RISK_WORDS))
    seg = _segment(doc, "3", "Item 3. Legal Proceedings", status="partial")
    assert apply_topic_prior([seg], doc, priors=priors, breakdowns={}) == 0
    small = normalize_html("<p>Item 3. Legal Proceedings</p><p>"
                           + _span_text(RISK_WORDS) + "</p>")
    assert len(small.text) < MIN_DOC_CHARS
    seg2 = ItemSegment(
        filing_id="t", item_code="3", canonical_title=CANONICAL_ITEM_TITLES["3"],
        extracted_heading="Item 3.", start_offset=0, end_offset=len(small.text),
        text_sha256="x", status="pass", confidence=0.9)
    assert apply_topic_prior([seg2], small, priors=priors, breakdowns={}) == 0


# ---------------------------------------------------------------------------
# no off-topic floor: an own-coverage floor variant was measured on the
# held-out fold and killed (18/20 fires hit correct items) — an alien-content
# span must NOT be flagged by the shipped margin signal alone, because low
# own-coverage without a decisive other-item winner is not misattribution
# ---------------------------------------------------------------------------

def test_alien_content_without_other_item_winner_is_not_flagged():
    priors = _priors()
    alien = _alien(400)  # matches no lexicon at all
    doc = _doc(_span_text(RISK_WORDS), alien)
    seg = _segment(doc, "3", "Item 3. Legal Proceedings")
    assert apply_topic_prior([seg], doc, priors=priors, breakdowns={}) == 0
    assert seg.needs_review is False


# ---------------------------------------------------------------------------
# runtime sub-signal (b): IBR pointer trust cap
# ---------------------------------------------------------------------------

def test_ibr_stub_is_capped_and_routed_to_review():
    doc = _doc(_span_text(RISK_WORDS), _span_text(LEGAL_WORDS))
    seg = _segment(doc, "3", "Item 3. Legal Proceedings",
                   status="incorporated_by_reference")
    bd = _breakdown()
    n = apply_topic_prior([seg], doc, priors=TopicPriors({}, 1.0),
                          breakdowns={"3": bd})
    assert n == 1 and seg.needs_review
    assert any(c.name == POINTER_COMPONENT and c.score == 0.0
               for c in bd.components)
    assert seg.confidence < 0.75


def test_ibr_already_flagged_is_left_alone():
    doc = _doc(_span_text(RISK_WORDS), _span_text(LEGAL_WORDS))
    seg = _segment(doc, "3", "Item 3. Legal Proceedings",
                   status="incorporated_by_reference")
    seg.needs_review = True
    bd = _breakdown()
    assert apply_topic_prior([seg], doc, priors=TopicPriors({}, 1.0),
                             breakdowns={"3": bd}) == 0
    assert not any(c.name == POINTER_COMPONENT for c in bd.components)


def test_ibr_kill_switch(monkeypatch):
    monkeypatch.setenv("SEC_TOPIC_PRIOR_IBR", "0")
    doc = _doc(_span_text(RISK_WORDS), _span_text(LEGAL_WORDS))
    seg = _segment(doc, "3", "Item 3. Legal Proceedings",
                   status="incorporated_by_reference")
    assert apply_topic_prior([seg], doc, priors=TopicPriors({}, 1.0),
                             breakdowns={}) == 0
    assert seg.needs_review is False


# ---------------------------------------------------------------------------
# artifact loading + component dedup
# ---------------------------------------------------------------------------

def test_missing_artifact_is_inert(tmp_path, monkeypatch):
    import sec_core.topic_prior as tp
    assert load_topic_priors(tmp_path / "nope.json") is None
    # priors=None falls back to the artifact path — point it at a missing file
    monkeypatch.setattr(tp, "LEXICON_PATH", tmp_path / "nope.json")
    doc = _doc(_span_text(LEGAL_WORDS), _span_text(RISK_WORDS))
    seg = _segment(doc, "3", "Item 3. Legal Proceedings")
    assert apply_topic_prior([seg], doc, priors=None, breakdowns={}) == 0
    assert seg.needs_review is False


def test_load_topic_priors_roundtrip(tmp_path):
    art = {"lexicon": {"1A": {"adversely": 1.5}},
           "thresholds": {"margin_tau": 0.4}}
    p = tmp_path / "lex.json"
    p.write_text(json.dumps(art), encoding="utf-8")
    priors = load_topic_priors(p)
    assert priors.margin_tau == 0.4
    assert priors.lexicon["1A"]["adversely"] == 1.5


def test_component_not_duplicated_on_reapply():
    priors = _priors()
    doc = _doc(_span_text(LEGAL_WORDS), _span_text(RISK_WORDS))
    seg = _segment(doc, "3", "Item 3. Legal Proceedings")
    bd = _breakdown()
    apply_topic_prior([seg], doc, priors=priors, breakdowns={"3": bd})
    apply_topic_prior([seg], doc, priors=priors, breakdowns={"3": bd})
    assert sum(1 for c in bd.components
               if c.name == MISATTRIBUTION_COMPONENT) == 1


def test_shipped_artifact_loads_if_present():
    priors = load_topic_priors()
    if priors is None:
        pytest.skip("shipped artifact not built in this checkout")
    assert len(priors.lexicon) >= 3
    assert priors.margin_tau >= 0.0
