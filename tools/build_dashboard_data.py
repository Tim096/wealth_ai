"""Assemble the eval dashboard's data.json from real run artifacts:
SEC sweep records, XBRL certification (from cache), Intel/Citi classification,
and the browser killer-demo trace. No fabricated numbers.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from sec_core.scoring import tristate

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "apps" / "web" / "eval-dashboard" / "data.json"

SWEEP = ROOT / "data" / "sec_eval" / "records" / "sweep3"
LAYER = {"AAPL": "big tech", "MSFT": "big tech", "NVDA": "big tech", "JPM": "financial",
         "GS": "financial", "WMT": "retail/mfg", "CAT": "retail/mfg", "XOM": "energy/mining",
         "NEM": "energy/mining", "MRNA": "biotech", "KO": "consumer"}
CERTIFICATION = ROOT / "data" / "sec_eval" / "certification" / "item8_certification.json"
CURRENT = ROOT / "data" / "sec_eval" / "records" / "current"
BROWSER_TRACE = ROOT / "data" / "browser_eval" / "artifacts" / "killer_demo_trace.json"
_JSON_INPUTS: dict[Path, object] = {}


def _read_json(path: Path, encoding: str = "utf-8"):
    if path not in _JSON_INPUTS:
        _JSON_INPUTS[path] = json.loads(path.read_text(encoding=encoding))
    return _JSON_INPUTS[path]


def artifact_manifest() -> dict:
    entries = []
    for path, value in sorted(_JSON_INPUTS.items()):
        canonical = json.dumps(
            value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
        entries.append({"path": path.relative_to(ROOT).as_posix(),
                        "sha256": hashlib.sha256(canonical).hexdigest()})
    canonical = json.dumps(entries, separators=(",", ":"), sort_keys=True).encode()
    return {"generator": "tools/build_dashboard_data.py",
            "input_manifest_sha256": hashlib.sha256(canonical).hexdigest(),
            "inputs": entries}


def sec_section() -> dict:
    records = {p.stem: _read_json(p, encoding="utf-8-sig")
               for p in sorted(SWEEP.glob("*.json"))}
    certification = _read_json(CERTIFICATION)
    cert_by_ticker = {r["ticker"]: r for r in certification["records"]}
    status_counts: Counter[str] = Counter()
    tri_counts: Counter[str] = Counter()
    conf_pass, conf_stub = [], []
    tickers = []
    for ticker, rec in records.items():
        items = rec["items"]
        counts = Counter(v["status"] for v in items.values())
        status_counts.update(counts)
        tri_counts.update(tristate(v["status"], bool(v.get("toc_listed", False)))
                          for v in items.values())
        conf_pass += [v["confidence"] for v in items.values() if v["status"] == "pass"]
        conf_stub += [v["confidence"] for v in items.values()
                      if v["status"] == "incorporated_by_reference"]
        item8_status = items["8"]["status"]
        cert = cert_by_ticker.get(ticker)
        cert_matches = (cert is not None and cert["accession"] == rec["accession"]
                        and cert["item8_status"] == item8_status)
        tickers.append({
            "ticker": ticker, "layer": LAYER.get(ticker, "?"),
            "report_date": rec["report_date"], "raw_chars": rec["raw_chars"],
            "latency_ms": rec["latency_ms"], "pass": counts["pass"],
            "incorporated_by_reference": counts["incorporated_by_reference"],
            "missing": counts["missing"], "reserved": counts["reserved"],
            "item8_status": item8_status,
            "item8_xbrl": cert["verdict"] if cert_matches else "unavailable",
        })

    wrappers = []
    for ticker in ("INTC", "CITI"):
        rec = _read_json(CURRENT / f"{ticker}.json")
        item14 = rec["items"]["14"]
        wrappers.append({
            "ticker": ticker, "filing_class": rec["filing_class"],
            "item14_status": item14["status"],
            "item14_provenance": item14["provenance"],
            "needs_review_count": len(rec["needs_review_items"]),
            "reason": (rec["pipeline_warnings"][0] if rec["pipeline_warnings"] else "")[:200],
        })

    total = sum(status_counts.values())
    return {
        "filings": len(records), "total_items": total,
        "status_distribution": [{"status": status, "count": count,
                                 "share": round(count / total, 4)}
                                for status, count in status_counts.most_common()],
        "confidence": {
            "substantive_pass_mean": round(sum(conf_pass) / len(conf_pass), 3),
            "substantive_pass_min": round(min(conf_pass), 3),
            "stub_mean": round(sum(conf_stub) / len(conf_stub), 3),
            "stub_max": round(max(conf_stub), 3),
        },
        "tickers": tickers,
        "wrappers": wrappers,
        "xbrl_summary": dict(Counter(t["item8_xbrl"] for t in tickers)),
        "tri_state": dict(tri_counts.most_common()),
        "sweep": SWEEP.name,
    }


def _load(rel: str) -> dict:
    return _read_json(ROOT / rel)


def _guarded(builder) -> dict:
    """Read a committed artifact; on failure surface the error, never invent numbers."""
    try:
        return builder()
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}


def browser_evals_section() -> dict:
    def calibration() -> dict:
        a = _load("data/browser_eval/calibration/calibration_results.json")
        return {
            "n_success": a["dataset"]["n_success"],
            "n_corrupted": a["dataset"]["n_corrupted"],
            "three_state_table": a["three_state_table"],
            "per_corruption_class": a["per_corruption_class"],
            "confusion": a["confusion"],
            "rates": a["rates"],
            "apparent_success_rate": a["apparent"]["apparent_success_rate"],
            "corrected": a["rogan_gladen_corrected_success_rate"],
        }

    def impossible() -> dict:
        return _load("data/browser_eval/impossible/impossible_results.json")["metrics"]

    def passk() -> dict:
        a = _load("data/browser_eval/passk/passk_results.json")
        return {"script_mode": a["script_mode"]["summary"],
                "agent_mode_mock": a["agent_mode_mock"]["summary"]}

    def degradation() -> dict:
        a = _load("data/browser_eval/artifacts/degradation_curve.json")
        return {axis: c["points"] for axis, c in a["curves"].items()}

    def trajectory() -> dict:
        return _load("data/browser_eval/trajectory/trajectory_results.json")["metrics"]

    def false_success() -> dict:
        a = _load("data/browser_eval/false_success/detector_results.json")
        m = a["metrics"]
        return {"route": a["route"], "n_applicable": m["n_applicable_claimed_success"],
                "confusion": m["confusion"], "precision": m["precision"],
                "recall": m["recall"], "flag_rate": m["flag_rate"]}

    return {"calibration": _guarded(calibration), "impossible": _guarded(impossible),
            "passk": _guarded(passk), "degradation": _guarded(degradation),
            "trajectory": _guarded(trajectory), "false_success": _guarded(false_success)}


def sec_evals_section() -> dict:
    def triangulation() -> dict:
        a = _load("data/sec_eval/triangulation/triangulation.json")
        return {"engine": a["engine"], "filings": a["filings"],
                "verdict_totals": a["verdict_totals"], "disagreements": a["disagreements"]}

    def offset_f1() -> dict:
        a = _load("data/sec_eval/scoring/offset_f1.json")
        return {"records_dir": a["records_dir"], **a["totals"]}

    def cyd() -> dict:
        a = _load("data/sec_eval/cyd_groundtruth/cyd_agreement.json")
        return {"verdicts": a["verdicts"], "disagreements": a["disagreements"],
                "coverage_mean_over_available": a["coverage_mean_over_available"],
                "records": [{"ticker": r["ticker"], "our_status": r["our_status"],
                             "coverage": r["coverage"], "containment": r["containment"],
                             "verdict": r["verdict"]} for r in a["records"]]}

    def stratification() -> dict:
        a = _load("data/sec_eval/stratification/stratification.json")
        runs = a["era_strata_runs"] + [a["agent_gap_run"]]
        return {"coverage_matrix": a["coverage_matrix"],
                "unsupported_strata": [u["stratum"] for u in a["unsupported"]],
                "runs": [{"ticker": r["ticker"], "era": r["era"],
                          "agent": r["detected_agent"], "supported": r["supported"],
                          "coverage_ratio": r["invariants"]["coverage_ratio"],
                          "pass_items": r["invariants"]["pass_items"]} for r in runs],
                "agent_survey": a["agent_survey"]["distribution"]}

    def landmines() -> dict:
        a = _load("data/sec_eval/landmines/landmines.json")
        mines = a["landmines"]
        return {"n_landmines": len(mines),
                "n_handled": sum(1 for m in mines if m["handled"]),
                "ids": [m["id"] for m in mines], "rerun": a["rerun"]}

    return {"triangulation": _guarded(triangulation), "offset_f1": _guarded(offset_f1),
            "cyd": _guarded(cyd), "stratification": _guarded(stratification),
            "landmines": _guarded(landmines)}


def status_reclassification_section() -> dict:
    def counts(sweep: str) -> dict:
        folder = ROOT / "data" / "sec_eval" / "records" / sweep
        status: Counter[str] = Counter()
        filings = 0
        for path in sorted(folder.glob("*.json")):
            record = _read_json(path, encoding="utf-8-sig")
            status.update(item["status"] for item in record["items"].values())
            filings += 1
        return {"filings": filings, "items": sum(status.values()), **dict(status)}

    return {"before": counts("sweep1"), "after": counts("sweep2")}


def browser_section() -> dict:
    return _read_json(BROWSER_TRACE)


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    _JSON_INPUTS.clear()
    sec = sec_section()
    status_reclassification = status_reclassification_section()
    browser = browser_section()
    browser_evals = browser_evals_section()
    sec_evals = sec_evals_section()
    data = {
        "generated_note": "deterministically assembled from tracked run artifacts",
        "provenance": artifact_manifest(),
        "sec": sec,
        "status_reclassification": status_reclassification,
        "browser": browser,
        "browser_evals": browser_evals,
        "sec_evals": sec_evals,
    }
    OUT.write_text(json.dumps(data, indent=1), encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes)")
    print("xbrl summary:", data["sec"]["xbrl_summary"])
    print("wrappers:", [(w["ticker"], w["filing_class"]) for w in data["sec"]["wrappers"]])


if __name__ == "__main__":
    main()
