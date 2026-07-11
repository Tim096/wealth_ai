"""10-K family census from EDGAR full-index form.idx (giants_task2.md §2.1/§4).

Promoted from the scratchpad script that produced the §2.1 evidence: per-year
counts of every 10-K-family form-type string as it ACTUALLY appears in the
index. The §2.1-1 string traps this census demonstrates:
  * `10KSB` / `10KSB40` / `10KT405` have NO hyphen — `startswith("10-K")`
    silently drops the whole KSB family;
  * `== "10-K"` drops every variant (10-K405 is ~1/3 of the standard family
    1995-2002, zero from 2003 on — Release 33-8230).
Counts are grouped by the same normalize_form used for the pseudo-gold join,
so the census and the join can never drift apart. /A amendments are counted
separately per guardrail g7 (they are ~17-25% of 10-K volume — not rare).

Usage:
  .venv/Scripts/python tools/count_forms.py [--years 1994,1996,...]
Requires SEC_EDGAR_USER_AGENT. Writes data/sec_eval/pseudo_gold/form_census.json
(a downloaded-data artifact — never committed).
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.mine_pseudo_gold import normalize_form  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "sec_eval" / "pseudo_gold" / "form_census.json"
IDX_URL = "https://www.sec.gov/Archives/edgar/full-index/{year}/QTR{q}/form.idx"
DEFAULT_YEARS = [1994, 1996, 1998, 2000, 2002, 2004, 2006, 2008]


def census_year(year: int, user_agent: str) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for q in (1, 2, 3, 4):
        req = urllib.request.Request(IDX_URL.format(year=year, q=q),
                                     headers={"User-Agent": user_agent})
        try:
            data = urllib.request.urlopen(req, timeout=60).read().decode("latin-1")
        except Exception as e:  # noqa: BLE001 — a missing quarter is recorded, not fatal
            print(f"{year} QTR{q} ERROR {type(e).__name__}: {e}")
            continue
        for line in data.splitlines():
            form = line[:12].strip()
            # full enumeration via normalize_form — NOT startswith (see module doc)
            family, _ = normalize_form(form)
            if family != "other":
                counts[form] += 1
        time.sleep(0.3)  # SEC fair-access
    return dict(counts.most_common())


def main() -> None:
    user_agent = os.environ.get("SEC_EDGAR_USER_AGENT", "")
    if not user_agent:
        sys.exit("set SEC_EDGAR_USER_AGENT (SEC fair-access policy requires a contact)")
    years = DEFAULT_YEARS
    args = sys.argv[1:]
    if "--years" in args:
        years = [int(y) for y in args[args.index("--years") + 1].split(",")]

    census: dict[str, dict] = {}
    for year in years:
        raw = census_year(year, user_agent)
        by_family: dict[str, dict[str, int]] = {}
        for form, n in raw.items():
            family, is_a = normalize_form(form)
            key = f"{family}/A" if is_a else family
            by_family.setdefault(key, {})[form] = n
        census[str(year)] = {"raw": raw, "by_family": by_family}
        print(year, json.dumps(raw))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": "SEC EDGAR full-index form.idx (public data)",
        "spec": "docs/research/giants_task2.md §2.1-1 form-string enumeration evidence",
        "census": census,
    }, indent=1), encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
