"""Freeze offset-level golden labels from an eval record + triangulation (T2-2).

Semi-automatic gold protocol (also recorded in each gold file's `labeling`
field) — an item's offsets are frozen ONLY when every mechanical rule passes:
  1. status is pass/partial and needs_review is false;
  2. the independent third engine agrees (triangulation verdict == "agree");
  3. the span is non-empty and carries text_sha256.
reserved / incorporated_by_reference freeze as state=null (legitimately
absent, no span). missing without a TOC claim freezes as state=null; missing
WITH a TOC claim freezes as state=unverified (we refuse to bless ground truth
we do not have). Items failing rule 2 stay state=present but carry
offsets_excluded — they count in the tri-state confusion, never in offset F1.
A human spot-check of frozen spans happens before commit; this tool only
enforces the mechanical rules.

Usage:
  .venv/Scripts/python tools/freeze_offset_gold.py data/sec_eval/records/sweep3/AAPL.json
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRIANGULATION = ROOT / "data" / "sec_eval" / "triangulation" / "triangulation.json"
OUT_DIR = ROOT / "data" / "golden_labels" / "offsets"

LABELING = (
    "semi-automatic: pipeline offsets frozen only where the independent third engine "
    "(edgartools triangulation, data/sec_eval/triangulation/triangulation.json) returned "
    "verdict=agree AND needs_review=false; disagree/unavailable items keep state=present "
    "but are excluded from offset F1; missing-with-TOC-claim items are state=unverified. "
    "Frozen spans were human spot-checked before commit. Offsets address "
    "NormalizedDocument.text (map to raw HTML via doc.raw_offset)."
)


def freeze(record: dict, triangulation: dict) -> dict:
    ticker = record["ticker"]
    trirec = next((r for r in triangulation.get("records", [])
                   if r["ticker"] == ticker), None)
    items: dict[str, dict] = {}
    for code, v in record["items"].items():
        status = v["status"]
        if status in ("pass", "partial"):
            entry: dict = {"state": "present", "status_frozen": status}
            verdict = ""
            if trirec is not None:
                verdict = trirec.get("items", {}).get(code, {}).get("verdict", "")
            if v.get("needs_review"):
                entry["offsets_excluded"] = (
                    "needs_review flagged — no gold without human adjudication")
            elif verdict != "agree":
                entry["offsets_excluded"] = (
                    f"third-engine verdict={verdict or 'unavailable'} — "
                    f"offsets not independently confirmed")
            elif not v.get("text_sha256") or v["end_offset"] <= v["start_offset"]:
                entry["offsets_excluded"] = "empty span"
            else:
                entry["start_offset"] = v["start_offset"]
                entry["end_offset"] = v["end_offset"]
                entry["text_sha256"] = v["text_sha256"]
        elif status in ("reserved", "incorporated_by_reference"):
            entry = {"state": "null", "reason": status}
        elif status == "missing":
            if v.get("toc_listed"):
                entry = {"state": "unverified", "reason":
                         "TOC advertises the item but extractor found nothing — needs human gold"}
            else:
                entry = {"state": "null", "reason": "absent from filing (no TOC claim)"}
        else:
            entry = {"state": "unverified", "reason": f"status={status}"}
        items[code] = entry

    return {
        "ticker": ticker,
        "cik": record.get("cik"),
        "accession": record.get("accession"),
        "form": record.get("form"),
        "report_date": record.get("report_date"),
        "normalized_chars": record.get("normalized_chars"),
        "labeling": LABELING,
        "frozen_at": time.strftime("%Y-%m-%d"),
        "items": items,
    }


def main() -> None:
    record_path = Path(sys.argv[1])
    record = json.loads(record_path.read_text(encoding="utf-8-sig"))
    triangulation = json.loads(TRIANGULATION.read_text(encoding="utf-8-sig"))
    gold = freeze(record, triangulation)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{gold['ticker']}.json"
    out.write_text(json.dumps(gold, indent=1), encoding="utf-8")
    frozen = sum(1 for v in gold["items"].values() if "start_offset" in v)
    print(f"{gold['ticker']}: {frozen} offset-gold items, "
          f"{sum(1 for v in gold['items'].values() if v['state'] == 'present')} present, "
          f"{sum(1 for v in gold['items'].values() if v['state'] == 'null')} null -> {out}")


if __name__ == "__main__":
    main()
