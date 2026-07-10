"""Assemble the eval dashboard's data.json from real run artifacts:
SEC sweep records, XBRL certification (from cache), Intel/Citi classification,
and the browser killer-demo trace. No fabricated numbers.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from sec_core.fetcher import EdgarFetcher
from sec_core.resolver import FilingRef
from sec_core.pipeline import extract_from_html
from sec_core.xbrl import fetch_company_facts, key_facts_for_accession, validate_span

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "apps" / "web" / "eval-dashboard" / "data.json"

SWEEP = ROOT / "data" / "sec_eval" / "records" / "sweep2"
LAYER = {"AAPL": "big tech", "MSFT": "big tech", "NVDA": "big tech", "JPM": "financial",
         "GS": "financial", "WMT": "retail/mfg", "CAT": "retail/mfg", "XOM": "energy/mining",
         "NEM": "energy/mining", "MRNA": "biotech", "KO": "consumer"}
HELD_OUT = {"MSFT", "NVDA", "GS", "WMT", "CAT", "NEM", "MRNA", "KO"}
XBRL_CIK = {"AAPL": 320193, "MSFT": 789019, "NVDA": 1045810, "JPM": 19617, "GS": 886982,
            "WMT": 104169, "CAT": 18230, "XOM": 34088, "NEM": 1164727, "MRNA": 1682852,
            "KO": 21344}
WRAPPER = {"INTC": ("50863", "0000050863-26-000011", "intc-20251227.htm"),
           "CITI": ("831001", "0000831001-26-000011", "c-20251231.htm")}


def sec_section() -> dict:
    fetcher = EdgarFetcher(cache_dir=ROOT / "data" / "raw_filings")
    records = {p.stem: json.loads(p.read_text(encoding="utf-8-sig")) for p in sorted(SWEEP.glob("*.json"))}
    status_counts: Counter[str] = Counter()
    conf_pass, conf_stub = [], []
    tickers = []
    for t, rec in records.items():
        items = rec["items"]
        c = Counter(v["status"] for v in items.values())
        status_counts.update(c)
        conf_pass += [v["confidence"] for v in items.values() if v["status"] == "pass"]
        conf_stub += [v["confidence"] for v in items.values() if v["status"] == "incorporated_by_reference"]
        # XBRL certify item 8
        cert = None
        try:
            facts = key_facts_for_accession(fetch_company_facts(fetcher, XBRL_CIK[t]), rec["accession"])
            ref = FilingRef(cik=XBRL_CIK[t], accession=rec["accession"], primary_document=rec["main_document"])
            raw = fetcher.get(ref.file_url(rec["main_document"])).content.decode("utf-8", errors="replace")
            res = extract_from_html(raw, t)
            cert = validate_span(res.text_of("8"), facts).verdict
        except Exception as e:  # noqa: BLE001
            cert = f"error:{type(e).__name__}"
        tickers.append({
            "ticker": t, "layer": LAYER.get(t, "?"), "held_out": t in HELD_OUT,
            "report_date": rec["report_date"], "raw_chars": rec["raw_chars"],
            "latency_ms": rec["latency_ms"], "pass": c["pass"],
            "incorporated_by_reference": c["incorporated_by_reference"],
            "missing": c["missing"], "reserved": c["reserved"],
            "item8_status": items["8"]["status"], "item8_xbrl": cert,
        })

    # wrapper / cross-reference-index filings (Intel/Citi)
    wrappers = []
    for t, (cik, acc, doc) in WRAPPER.items():
        try:
            ref = FilingRef(cik=int(cik), accession=acc, primary_document=doc)
            raw = fetcher.get(ref.file_url(doc)).content.decode("utf-8", errors="replace")
            res = extract_from_html(raw, t)
            nr = [s.item_code for s in res.segments if s.needs_review]
            wrappers.append({
                "ticker": t, "filing_class": res.filing_class,
                "item14_status": res.segment("14").status,
                "item14_provenance": res.segment("14").provenance,
                "needs_review_count": len(nr),
                "reason": (res.warnings[0] if res.warnings else "")[:200],
            })
        except Exception as e:  # noqa: BLE001
            wrappers.append({"ticker": t, "filing_class": f"error:{type(e).__name__}"})

    total = sum(status_counts.values())
    return {
        "filings": len(records), "total_items": total,
        "status_distribution": [{"status": s, "count": n, "share": round(n / total, 4)}
                                for s, n in status_counts.most_common()],
        "confidence": {
            "substantive_pass_mean": round(sum(conf_pass) / len(conf_pass), 3),
            "substantive_pass_min": round(min(conf_pass), 3),
            "stub_mean": round(sum(conf_stub) / len(conf_stub), 3),
            "stub_max": round(max(conf_stub), 3),
        },
        "tickers": tickers,
        "wrappers": wrappers,
        "xbrl_summary": dict(Counter(t["item8_xbrl"] for t in tickers)),
    }


def audit_section() -> dict:
    # read the committed audit artifact — no hardcoded numbers
    a = json.loads((ROOT / "data" / "audit" / "adversarial_audit_2026-07-10.json").read_text(encoding="utf-8"))
    return {"agents": a["agents"], "anomalies_confirmed": a["anomalies_confirmed"],
            "anomalies_refuted": a["anomalies_refuted"],
            "silent_failures_before": a["silent_failures_before"],
            "silent_failures_after": a["silent_failures_after"],
            "pass_before": a["pass_rate_before"], "pass_after": a["pass_rate_after"]}


def browser_section() -> dict:
    trace_path = ROOT / "runs" / "browser_demo" / "trace.json"
    if trace_path.exists():
        return json.loads(trace_path.read_text(encoding="utf-8"))
    return {"runs": []}


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "generated_note": "assembled from real run artifacts by tools/build_dashboard_data.py",
        "sec": sec_section(),
        "audit": audit_section(),
        "browser": browser_section(),
    }
    OUT.write_text(json.dumps(data, indent=1), encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes)")
    print("xbrl summary:", data["sec"]["xbrl_summary"])
    print("wrappers:", [(w["ticker"], w["filing_class"]) for w in data["sec"]["wrappers"]])


if __name__ == "__main__":
    main()
