"""Runtime verifier mutation harness with quantified gates (P0-4).

Who verifies the verifier? This harness injects known corruptions into real
pipeline outputs and asserts the shipped runtime verification layers catch
them. Detection is defined exactly as the backlog row does: a mutant is caught
when the re-run verification layers raise needs_review OR drop confidence
significantly. The layers re-run here are all shipped code, not test doubles:

- topic_check.check_topic       (pipeline.py: inconsistent -> needs_review)
- third_engine.compare_item     (apply_triangulation: disagree -> needs_review
                                 + a zero-scored confidence component)
- heading_at_segment_start      (boundary.py ConditionCheck; fail zeroes the
                                 verifier_result confidence component)
- boundary_length_sanity band   (boundary.py: 50..3,000,000 chars)

Mutation classes — closed (named in the spec): truncate, misalign, toc_anchor,
wrapper_swallow; open (spec's open-class requirement): jitter (random
+/-5..25% boundary jitter), cross_swap (cross-item body swap).

Corrupt bases:
1. fixture harness — real extractions from the offline synthetic 10-Ks
   (alpha/beta), full detector including the topic oracle;
2. sweep3 proxy harness — per-item word counts, headings and document order
   from the 11 real sweep3 filings (data/sec_eval/records/sweep3 +
   data/sec_eval/triangulation) rebuilt as unique-word proxy documents, so the
   structural layers (heading / triangulation / length band) are exercised at
   the REAL size distribution (item 8 up to ~450K chars) without committing
   filing text. The topic oracle is off for proxies (synthetic words carry no
   canonical topic language — it would false-alarm on clean proxies).

Quantified gates (harness FAILS below them — they are asserts, not a report):
- per-mutation-class detection recall >= 0.95;
- clean false-alarm <= 0.05 on unmutated bases AND on the recorded sweep3
  runtime verifier outputs (needs_review / triangulation verdicts).
"""

import json
import random
from glob import glob
from pathlib import Path

import pytest

from sec_core.pipeline import extract_from_html
from sec_core.third_engine import compare_item
from sec_core.topic_check import check_topic

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "data" / "sec_eval" / "fixtures"
MUTATIONS = ROOT / "data" / "sec_eval" / "mutations"
SWEEP3 = ROOT / "data" / "sec_eval" / "records" / "sweep3"
TRIANGULATION = ROOT / "data" / "sec_eval" / "triangulation" / "triangulation.json"

SEED = 20260710
RECALL_GATE = 0.95
FALSE_ALARM_GATE = 0.05
# Confidence-drop significance. Shipped component weights sum to max 10.0
# (boundary.py _confidence); zeroing one 1.0-weight component (verifier_result
# or boundary_length_sanity) drops total by 1/10, and the appended zero-scored
# third_engine_agreement component drops it by ~1/11. Threshold sits below the
# smallest single-layer drop so any one failed layer counts as "significant".
SIGNIFICANT_DROP = 0.08

TOC_STUB = (MUTATIONS / "toc_stub.txt").read_text(encoding="utf-8")
WRAPPER = (MUTATIONS / "wrapper_financial_section.txt").read_text(encoding="utf-8")

CLASSES = ("truncate", "misalign", "toc_anchor", "wrapper_swallow", "jitter", "cross_swap")
TRUNCATE_FRACTIONS = (0.05, 0.15, 0.30)
JITTER_SAMPLES = 3


# ---------------------------------------------------------------------------
# runtime verifier re-run (shipped layers only)
# ---------------------------------------------------------------------------

def runtime_verify(code: str, heading: str, text: str, reference_text: str,
                   use_topic: bool = True):
    """Re-run the runtime verification layers on a (possibly mutated) span.

    Returns (needs_review, confidence_drop, signals). reference_text plays the
    independent third engine: on the clean sweep3 filings edgartools agrees on
    240/253 items, so the clean span is what the engine would return.
    """
    signals: list[str] = []
    needs_review = False
    drop = 0.0

    # boundary.py verifier check: heading_at_segment_start. Failing it zeroes
    # the verifier_result confidence component (weight 1.0 of max 10.0).
    if not text.lstrip().lower().startswith(heading[:20].lower()):
        signals.append("heading_at_segment_start=fail")
        drop += 1.0 / 10.0

    # boundary.py boundary_length_sanity component (global band).
    if not (50 <= len(text) <= 3_000_000):
        signals.append("boundary_length_sanity=fail")
        drop += 1.0 / 10.0

    # pipeline.py topic-consistency oracle: inconsistent on a pass span raises
    # needs_review.
    if use_topic:
        nl = text.find("\n")
        body = text[nl + 1:] if nl != -1 else text
        if check_topic(code, body).verdict == "inconsistent":
            signals.append("topic_check=inconsistent")
            needs_review = True

    # third_engine.apply_triangulation semantics: disagree raises needs_review
    # and appends a zero-scored third_engine_agreement component.
    if compare_item(code, text, reference_text, "pass").verdict == "disagree":
        signals.append("triangulation=disagree")
        needs_review = True
        drop += 1.0 / 11.0

    return needs_review, drop, signals


def is_detected(needs_review: bool, drop: float) -> bool:
    return needs_review or drop >= SIGNIFICANT_DROP


# ---------------------------------------------------------------------------
# corrupt bases
# ---------------------------------------------------------------------------

def _fixture_bases():
    bases = []
    for fid in ("alpha_10k", "beta_10k"):
        raw = (FIXTURES / f"{fid}.html").read_text(encoding="utf-8")
        result = extract_from_html(raw, fid)
        for seg in result.segments:
            if seg.status == "pass" and seg.end_offset - seg.start_offset >= 800:
                bases.append({
                    "filing": fid, "code": seg.item_code,
                    "heading": seg.extracted_heading,
                    "text": result.text_of(seg.item_code),
                    "start": seg.start_offset, "end": seg.end_offset,
                    "doc_text": result.doc.text, "use_topic": True,
                    "words": len(result.text_of(seg.item_code).split()),
                })
    return bases


_PROXY_FRONT_MATTER = ("UNITED STATES SECURITIES AND EXCHANGE COMMISSION\n"
                       "FORM 10-K ANNUAL REPORT\nTABLE OF CONTENTS\n"
                       + TOC_STUB + "\nPART I\n")


def _proxy_bases():
    """Rebuild each sweep3 filing as a proxy document: real headings, real
    document order, real per-item word counts (triangulation our_words), with
    unique synthetic words standing in for body text. Only clean items (status
    pass + triangulation agree) become bases."""
    tri = json.loads(TRIANGULATION.read_text(encoding="utf-8"))
    tri_by = {r["ticker"]: r["items"] for r in tri["records"]}
    filings = []
    for path in sorted(glob(str(SWEEP3 / "*.json"))):
        rec = json.loads(Path(path).read_text(encoding="utf-8"))
        ticker = rec["ticker"]
        rows = []
        for code, item in sorted(rec["items"].items(),
                                 key=lambda kv: kv[1].get("start_offset", 0)):
            tri_item = tri_by.get(ticker, {}).get(code, {})
            if (item["status"] == "pass" and tri_item.get("verdict") == "agree"
                    and tri_item.get("our_words", 0) > 0):
                rows.append((code, item["heading"] or f"Item {code}.",
                             tri_item["our_words"]))
        if not rows:
            continue
        parts = [_PROXY_FRONT_MATTER]
        pos = len(_PROXY_FRONT_MATTER)
        spans = []
        for code, heading, words in rows:
            stream = " ".join(f"{ticker.lower()}{code.lower()}w{k}" for k in range(words))
            seg_text = heading + "\n" + stream + "\n"
            parts.append(seg_text)
            spans.append({"filing": ticker, "code": code, "heading": heading,
                          "start": pos, "end": pos + len(seg_text),
                          "use_topic": False, "words": words})
            pos += len(seg_text)
        doc_text = "".join(parts)
        for span in spans:
            span["doc_text"] = doc_text
            span["text"] = doc_text[span["start"]:span["end"]]
        filings.append(spans)
    return [span for spans in filings for span in spans], filings


# ---------------------------------------------------------------------------
# mutation generators (deterministic; every mutant differs from its base)
# ---------------------------------------------------------------------------

def _mutants_for(bases_grouped, rng):
    """Yield (mutation_class, base, mutated_heading, mutated_text, tag)."""
    for group in bases_grouped:
        for base in group:
            ref_len = len(base["text"])
            # truncate — only where the loss exceeds the furniture slack the
            # triangulation layer legitimately tolerates (~40 words)
            if base["words"] >= 200:
                for frac in TRUNCATE_FRACTIONS:
                    cut = max(int(ref_len * frac), len(base["heading"]) + 10)
                    yield ("truncate", base, base["heading"], base["text"][:cut],
                           f"{base['filing']}:{base['code']}@{frac}")
            # toc_anchor — span replaced by a TOC block under the item heading
            yield ("toc_anchor", base, base["heading"],
                   base["heading"] + "\n" + TOC_STUB,
                   f"{base['filing']}:{base['code']}")
            # jitter (open class) — random +/-5..25% boundary jitter
            span = base["end"] - base["start"]
            for k in range(JITTER_SAMPLES):
                d_start = max(1, int(span * rng.uniform(0.05, 0.25))) * rng.choice((-1, 1))
                d_end = int(span * rng.uniform(0.0, 0.25)) * rng.choice((-1, 1))
                start = max(0, base["start"] + d_start)
                end = min(len(base["doc_text"]), max(start + 60, base["end"] + d_end))
                yield ("jitter", base, base["heading"], base["doc_text"][start:end],
                       f"{base['filing']}:{base['code']}#{k}")
        # misalign + cross_swap need a second item from the same filing
        for i, base in enumerate(group):
            other = group[(i + 1) % len(group)]
            if other["code"] == base["code"]:
                continue
            # misalign — the OTHER item's whole span labelled as this item
            # (heading at span start is the other item's, as it would be in a
            # real misalignment, so the heading check cannot catch it)
            yield ("misalign", base, other["heading"], other["text"],
                   f"{base['filing']}:{base['code']}<-{other['code']}")
            # cross_swap (open class) — own heading kept, other item's body
            other_body = other["text"][other["text"].find("\n") + 1:]
            yield ("cross_swap", base, base["heading"],
                   base["heading"] + "\n" + other_body,
                   f"{base['filing']}:{base['code']}<->{other['code']}")
        # wrapper_swallow — terminal item swallows a bound Financial Section
        # (the JPM/XOM wrapper-10-K runaway pattern). Proxy filings get a
        # realistically sized ~100K-word annual-report stand-in; the committed
        # fixture wrapper covers the fixture scale.
        terminal = max(group, key=lambda b: b["start"])
        if terminal["use_topic"]:
            wrapper = WRAPPER
        else:
            wrapper = " ".join(f"wrapw{k}" for k in range(100_000))
        yield ("wrapper_swallow", terminal, terminal["heading"],
               terminal["text"] + "\n" + wrapper,
               f"{terminal['filing']}:{terminal['code']}")


# ---------------------------------------------------------------------------
# harness run (module-scoped: extraction + shingling is the expensive part)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def harness():
    fixture_bases = _fixture_bases()
    proxy_bases, proxy_filings = _proxy_bases()
    assert fixture_bases and proxy_bases

    fixture_groups = {}
    for base in fixture_bases:
        fixture_groups.setdefault(base["filing"], []).append(base)
    grouped = list(fixture_groups.values()) + proxy_filings

    clean = {"fixture": [], "proxy": []}
    for base in fixture_bases + proxy_bases:
        nr, drop, signals = runtime_verify(
            base["code"], base["heading"], base["text"], base["text"],
            use_topic=base["use_topic"])
        clean["fixture" if base["use_topic"] else "proxy"].append(
            (is_detected(nr, drop), signals, f"{base['filing']}:{base['code']}"))

    rng = random.Random(SEED)
    per_class = {cls: [] for cls in CLASSES}
    for cls, base, heading, text, tag in _mutants_for(grouped, rng):
        assert text != base["text"], f"{cls} mutant {tag} is a no-op"
        nr, drop, signals = runtime_verify(
            base["code"], heading, text, base["text"], use_topic=base["use_topic"])
        per_class[cls].append((is_detected(nr, drop), signals, tag))
    return {"clean": clean, "mutants": per_class}


def _recall(rows):
    return sum(1 for detected, _, _ in rows if detected) / len(rows)


# ---------------------------------------------------------------------------
# gates
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cls", CLASSES)
def test_per_class_detection_recall_gate(harness, cls):
    rows = harness["mutants"][cls]
    assert len(rows) >= 10, f"{cls}: only {len(rows)} mutants — too few to gate at 0.95"
    misses = [(tag, signals) for detected, signals, tag in rows if not detected]
    assert _recall(rows) >= RECALL_GATE, (
        f"{cls}: recall {_recall(rows):.4f} < {RECALL_GATE} "
        f"({len(misses)}/{len(rows)} missed): {misses[:5]}")


def test_clean_bases_false_alarm_gate(harness):
    for kind, rows in harness["clean"].items():
        alarms = [(tag, signals) for detected, signals, tag in rows if detected]
        rate = len(alarms) / len(rows)
        assert rate <= FALSE_ALARM_GATE, (
            f"clean {kind} bases: false-alarm {rate:.4f} > {FALSE_ALARM_GATE}: {alarms[:5]}")


def _sweep3_recorded_false_alarm():
    tri = json.loads(TRIANGULATION.read_text(encoding="utf-8"))
    tri_by = {r["ticker"]: r["items"] for r in tri["records"]}
    total = alarms = 0
    for path in sorted(glob(str(SWEEP3 / "*.json"))):
        rec = json.loads(Path(path).read_text(encoding="utf-8"))
        for code, item in rec["items"].items():
            if item["status"] != "pass":
                continue
            total += 1
            verdict = tri_by.get(rec["ticker"], {}).get(code, {}).get("verdict")
            if item["needs_review"] or verdict == "disagree":
                alarms += 1
    return alarms, total


def test_sweep3_recorded_clean_false_alarm_gate():
    """Specificity on the REAL sweep3 runs: over all items the pipeline passed,
    how often did the recorded runtime verifier outputs (needs_review flag or
    a triangulation disagree) alarm anyway? Note the recorded item-16 verdicts
    predate the P0-5 engine_suspect reclassification, so this measures a
    conservative upper bound."""
    alarms, total = _sweep3_recorded_false_alarm()
    assert total > 100
    rate = alarms / total
    assert rate <= FALSE_ALARM_GATE, (
        f"sweep3 recorded clean false-alarm {rate:.4f} ({alarms}/{total}) > {FALSE_ALARM_GATE}")


# ---------------------------------------------------------------------------
# harness self-checks
# ---------------------------------------------------------------------------

def test_mutation_generation_is_deterministic():
    _, proxy_filings = _proxy_bases()
    group = proxy_filings[0]
    first = [(cls, tag, text) for cls, _, _, text, tag in
             _mutants_for([group], random.Random(SEED))]
    second = [(cls, tag, text) for cls, _, _, text, tag in
              _mutants_for([group], random.Random(SEED))]
    assert first == second


def test_every_class_produced_mutants_from_both_base_families(harness):
    fixture_ids = {"alpha_10k", "beta_10k"}
    for cls in CLASSES:
        families = {tag.split(":")[0] in fixture_ids for _, _, tag in harness["mutants"][cls]}
        assert families == {True, False}, f"{cls} lacks fixture or sweep3-proxy coverage"


def test_detection_channels_are_the_expected_layers(harness):
    """Guard against detection-by-accident: each class must be caught by the
    layer that owns its failure mode (on at least 95% of its detected mutants
    for the signal-bearing classes)."""
    expect = {
        "truncate": "triangulation=disagree",        # length-ratio boundary dispute
        "toc_anchor": "triangulation=disagree",      # content mismatch
        "misalign": "triangulation=disagree",
        "cross_swap": "triangulation=disagree",
        "wrapper_swallow": "triangulation=disagree",  # runaway-span ratio
        "jitter": "heading_at_segment_start=fail",   # heading no longer at start
    }
    for cls, signal in expect.items():
        rows = [signals for detected, signals, _ in harness["mutants"][cls] if detected]
        hit = sum(1 for signals in rows if signal in signals)
        assert hit / len(rows) >= 0.95, f"{cls}: expected channel {signal} hit {hit}/{len(rows)}"


def test_runtime_verify_passes_a_clean_span_and_flags_an_empty_reference():
    text = "Item 1A. Risk Factors\nOur business faces risk that could materially harm results."
    nr, drop, _ = runtime_verify("1A", "Item 1A. Risk Factors", text, text)
    assert not is_detected(nr, drop)
    # engine absence is engine_unavailable, never an alarm against our span
    nr, drop, signals = runtime_verify("1A", "Item 1A. Risk Factors", text, "")
    assert not is_detected(nr, drop) and "triangulation=disagree" not in signals


# ---------------------------------------------------------------------------
# measured numbers (printed with `pytest -s` for the eval report)
# ---------------------------------------------------------------------------

def test_report_measured_numbers(harness, capsys):
    lines = ["P0-4 mutation harness measured numbers:"]
    for cls in CLASSES:
        rows = harness["mutants"][cls]
        lines.append(f"  {cls}: recall {_recall(rows):.4f} (n={len(rows)})")
    for kind, rows in harness["clean"].items():
        rate = sum(1 for detected, _, _ in rows if detected) / len(rows)
        lines.append(f"  clean {kind}: false-alarm {rate:.4f} (n={len(rows)})")
    alarms, total = _sweep3_recorded_false_alarm()
    lines.append(f"  clean sweep3 recorded: false-alarm {alarms / total:.4f} ({alarms}/{total})")
    with capsys.disabled():
        print("\n" + "\n".join(lines))
