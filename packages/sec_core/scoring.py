"""Scoring layer (T2-2): char-offset span F1 against frozen offset gold, plus
the ExtractBench-style present/null/MISSING tri-state mapping that separates
omission (gold present, nothing extracted) from hallucination (gold null,
content extracted). Pure functions over eval-record dicts + gold dicts —
no network, no LLM, deterministic.

Offsets are NormalizedDocument.text char offsets (the same address space as
ItemSegment.start_offset/end_offset). Gold spans carry text_sha256 so the
scorer can tell a moved boundary from normalization drift.
"""

from __future__ import annotations

from collections import Counter

TRI_PRESENT = "present"
TRI_NULL = "null"
TRI_MISSING = "MISSING"
TRI_UNSUPPORTED = "unsupported"


def tristate(status: str, toc_listed: bool) -> str:
    """Map the 7-state ItemStatus to the scoring tri-state.

    present  — content was extracted (pass / partial / ambiguous)
    null     — legitimately absent (reserved, incorporated_by_reference,
               or missing with no TOC claim that the item should exist)
    MISSING  — the filing's TOC advertises the item but nothing was
               extracted (omission alarm — the worst extractor failure mode)
    """
    if status in ("pass", "partial", "ambiguous"):
        return TRI_PRESENT
    if status in ("reserved", "incorporated_by_reference"):
        return TRI_NULL
    if status == "missing":
        return TRI_MISSING if toc_listed else TRI_NULL
    return TRI_UNSUPPORTED


def span_prf(pred_start: int, pred_end: int,
             gold_start: int, gold_end: int) -> tuple[float, float, float]:
    """Char-overlap precision / recall / F1 between a predicted and gold span."""
    pred_len = max(0, pred_end - pred_start)
    gold_len = max(0, gold_end - gold_start)
    overlap = max(0, min(pred_end, gold_end) - max(pred_start, gold_start))
    precision = overlap / pred_len if pred_len else 0.0
    recall = overlap / gold_len if gold_len else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def score_filing(record: dict, gold: dict) -> dict:
    """Score one eval record (tools/eval_one.py JSON) against one gold file.

    Outcomes (gold state x predicted tri-state):
      matched             gold present, pred present (F1 measures the boundary)
      omission            gold present, pred null/MISSING  — leakage OUT
      hallucination       gold null,    pred present       — leakage IN
      false_missing_alarm gold null,    pred MISSING
      correct_null        gold null,    pred null
      excluded            gold state unverified/unsupported — not scored

    F1 is computed only for gold items that carry frozen offsets; an omission
    on such an item scores 0.0 (it stays in the macro average — honesty over
    flattery). Hallucinated items have no gold span, so they are counted in
    the confusion, never in F1.
    """
    rows: list[dict] = []
    f1s: list[float] = []
    precisions: list[float] = []
    recalls: list[float] = []
    outcomes: Counter[str] = Counter()

    for code, g in gold["items"].items():
        gold_state = g.get("state", "")
        r = record.get("items", {}).get(code)
        if r is None:
            pred_state = TRI_MISSING
            status = "absent_from_record"
        else:
            status = r["status"]
            pred_state = tristate(status, bool(r.get("toc_listed", False)))

        if gold_state not in (TRI_PRESENT, TRI_NULL):
            outcome = "excluded"
        elif gold_state == TRI_PRESENT and pred_state == TRI_PRESENT:
            outcome = "matched"
        elif gold_state == TRI_PRESENT:
            outcome = "omission"
        elif pred_state == TRI_PRESENT:
            outcome = "hallucination"
        elif pred_state == TRI_MISSING:
            outcome = "false_missing_alarm"
        else:
            outcome = "correct_null"
        outcomes[outcome] += 1

        row = {"item": code, "gold_state": gold_state, "pred_status": status,
               "pred_state": pred_state, "outcome": outcome}

        has_gold_span = gold_state == TRI_PRESENT and "start_offset" in g
        if has_gold_span:
            if outcome == "matched" and r is not None:
                p, rc, f1 = span_prf(r["start_offset"], r["end_offset"],
                                     g["start_offset"], g["end_offset"])
                if g.get("text_sha256") and r.get("text_sha256"):
                    if r["text_sha256"] == g["text_sha256"]:
                        row["sha_check"] = "sha_exact"
                    elif (r["start_offset"], r["end_offset"]) == (
                            g["start_offset"], g["end_offset"]):
                        row["sha_check"] = "normalization_drift"
                    else:
                        row["sha_check"] = "boundary_moved"
            else:  # omission on an offset-gold item scores zero
                p = rc = f1 = 0.0
            row.update(precision=round(p, 4), recall=round(rc, 4), f1=round(f1, 4))
            precisions.append(p)
            recalls.append(rc)
            f1s.append(f1)
        rows.append(row)

    n = len(f1s)
    return {
        "ticker": record.get("ticker", gold.get("ticker", "")),
        "accession": gold.get("accession", ""),
        "accession_match": record.get("accession") == gold.get("accession"),
        "gold_items": len(gold["items"]),
        "offset_items": n,
        "macro_precision": round(sum(precisions) / n, 4) if n else None,
        "macro_recall": round(sum(recalls) / n, 4) if n else None,
        "macro_f1": round(sum(f1s) / n, 4) if n else None,
        "outcome_counts": dict(outcomes),
        "items": rows,
    }
