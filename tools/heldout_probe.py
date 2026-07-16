"""Held-out probe: run tickers the pipeline was never tuned on, keep what breaks.

The tracked sweeps (AAPL/CAT/GS/INTC/JPM/KO/MRNA/MSFT/NEM/NVDA/WMT/XOM) are the
set FG-SEC-002/003/004 were *found on and fixed against*. A filing you have
repaired against is not held out. This probe hits the deployed service with
tickers outside that set — REITs first, because their Item 2/15/16 layout is the
one the terminal-runaway cutter was never shown — and writes the raw responses
plus a summary of every item that ships without a needs_review flag.

Usage:
    python tools/heldout_probe.py
    python tools/heldout_probe.py --tickers O,SPG,PLD --base-url http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "sec_eval" / "heldout_probe"

# Outside every tracked sweep. REIT-heavy on purpose: Item 16 "None."/"Not
# Applicable." followed by an appended exhibit or financial-statement index is
# exactly the shape _SOFT_BREAK_RE was fitted to JPM/XOM for.
DEFAULT_TICKERS = ["O", "SPG", "PLD", "BRK-B", "VTR", "SEB", "TSM"]


def probe(base_url: str, tickers: list[str]) -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    with httpx.Client(base_url=base_url.rstrip("/"), timeout=90.0) as client:
        for ticker in tickers:
            r = client.post("/api/extract", json={"ticker": ticker})
            body = r.json()
            # A cold ticker comes back as a queued job, not a result. Polling is
            # not optional: a probe that records {"status":"queued"} and calls it
            # a row is the silent failure this file exists to catch.
            for _ in range(45):
                if body.get("status") != "queued" and body.get("status") != "running":
                    break
                time.sleep(2)
                body = client.get(f"/api/jobs/{body['job_id']}").json()
            else:
                body = {"ok": False, "error": f"job never left {body.get('status')!r}"}
            (OUT / f"{ticker}.json").write_text(
                json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
            if not body.get("ok"):
                rows.append({"ticker": ticker, "ok": False,
                             "error": body.get("error") or body.get("detail")})
                continue
            meta = body.get("meta") or {}
            items = body.get("items") or []
            # An item that ships `pass` while its own topic oracle says the body
            # does not look like that item, and nothing asks a human to look, is
            # the failure this repo exists to prevent. Count those separately.
            unflagged_weak = [
                {"code": it["code"], "chars": it["chars"],
                 "confidence": it["confidence"], "topic": it.get("topic")}
                for it in items
                if it.get("status") == "pass"
                and it.get("topic") in ("weak", "inconsistent")
                and not it.get("needs_review")
            ]
            rows.append({
                "ticker": ticker,
                "ok": True,
                "filing_class": meta.get("filing_class"),
                "coverage": meta.get("coverage"),
                "supported": meta.get("supported"),
                "xbrl_item8": meta.get("xbrl_item8"),
                "latency_ms": meta.get("latency_ms"),
                "pipeline_warnings": len(meta.get("pipeline_warnings") or []),
                "items": len(items),
                "needs_review": sum(1 for it in items if it.get("needs_review")),
                "unflagged_weak": unflagged_weak,
            })
    summary = {
        "base_url": base_url,
        "note": "tickers outside every tracked sweep; no code was repaired against these",
        "probed": len(rows),
        "unflagged_weak_total": sum(len(r.get("unflagged_weak") or []) for r in rows),
        "min_coverage": min([r["coverage"] for r in rows
                             if r.get("ok") and r.get("coverage") is not None], default=None),
        "rows": rows,
    }
    (OUT / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base-url", default="https://wealth-sec-ncku.zeabur.app")
    p.add_argument("--tickers", default=",".join(DEFAULT_TICKERS))
    a = p.parse_args()
    s = probe(a.base_url, [t.strip() for t in a.tickers.split(",") if t.strip()])
    print(json.dumps({k: v for k, v in s.items() if k != "rows"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
