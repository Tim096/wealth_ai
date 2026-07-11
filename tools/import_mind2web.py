r"""P1-1 Online-Mind2Web subset importer (attributed external live tasks).

License check (2026-07-10, three-tier rule — docs/ATTRIBUTION.md):
  osunlp/Online-Mind2Web is **CC-BY-4.0** (HF dataset card tag `license:cc-by-4.0`
  + GitHub OSU-NLP-Group/Online-Mind2Web README "Licensing Information"), HF
  gate = "auto" (click-through, no extra terms beyond CC-BY). Tier 1
  permissive-with-attribution: the sampled TASK LIST (text + metadata) is
  committable with attribution. We commit ONLY the ~20-task subset — never the
  full dataset, never trajectories/screenshots.

Sources (network only in main / fetch_*; everything else is pure and tested):
  1. official (needs HF_TOKEN — gated file):
       https://huggingface.co/datasets/osunlp/Online-Mind2Web/resolve/main/Online_Mind2Web.json
  2. fallback mirror (no token): hud-evals/Online-Mind2Web via the public
     datasets-server rows API — an ungated CC-BY-licensed redistribution that
     carries the original task_id / confirmed_task / website / reference_length.
     Which source produced the file is recorded in `source.fetched_from`.

Difficulty: official `level` when present, else derived from reference_length
per the paper's rule (arXiv:2504.01382 §2.2): <=5 easy, 6-10 medium, >=11 hard.

Usage:
  .venv\Scripts\python tools\import_mind2web.py                # mirror fallback
  set HF_TOKEN=hf_xxx && .venv\Scripts\python tools\import_mind2web.py
  .venv\Scripts\python tools\import_mind2web.py --counts 8,8,4
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import urllib.request
from pathlib import Path

from browser_core import BrowserTaskContract, SuccessCondition
from browser_agent.nl import derive_success

ROOT = Path(__file__).resolve().parents[1]

OFFICIAL_URL = ("https://huggingface.co/datasets/osunlp/Online-Mind2Web/"
                "resolve/main/Online_Mind2Web.json")
MIRROR_ROWS_URL = ("https://datasets-server.huggingface.co/rows"
                   "?dataset=hud-evals%2FOnline-Mind2Web&config=default&split=train")
ATTRIBUTION = ("Online-Mind2Web, OSU-NLP-Group (CC-BY-4.0, COLM 2025, "
               "arXiv:2504.01382)")
OUT_DEFAULT = ROOT / "data" / "browser_eval" / "external" / "mind2web_subset.json"
RAW_CACHE = ROOT / "runs" / "mind2web_import" / "raw.json"   # gitignored, full list

# Login/paywall/CAPTCHA-gated sites are excluded up front: a live task that a
# headless agent cannot even reach measures the site's bot wall, not the agent.
# Reasons are committed with the subset so the exclusion is auditable.
EXCLUDED_DOMAINS: dict[str, str] = {
    "amazon.com": "CAPTCHA wall on datacenter/headless traffic",
    "google.com": "reCAPTCHA on automated search traffic",
    "bestbuy.com": "aggressive anti-bot interstitial (blocks headless)",
    "target.com": "Shape/anti-bot challenge on automation",
    "ticketmaster.com": "notorious anti-bot (queue + CAPTCHA)",
    "stubhub.com": "PerimeterX CAPTCHA",
    "craigslist.org": "aggressive IP/automation blocking",
    "chase.com": "banking login required",
    "americanexpress.com": "banking login required",
    "airbnb.com": "login prompts + bot detection on core flows",
    "instructure.com": "LMS login required",
    "statista.com": "paywall on most statistics",
    "4shared.com": "login-gated downloads",
}

# Tasks whose TEXT demands an authenticated session are excluded even on
# otherwise-open sites.
_LOGIN_TASK_RE = re.compile(
    r"\b(log ?in|sign ?in|sign ?up|register|my account|password|premium"
    r"|subscription|subscribe)\b", re.IGNORECASE)

LEVEL_RULE = "reference_length <=5 easy / 6-10 medium / >=11 hard (arXiv:2504.01382 §2.2)"


def level_for(reference_length: int) -> str:
    if reference_length <= 5:
        return "easy"
    if reference_length <= 10:
        return "medium"
    return "hard"


def domain_of(url: str) -> str:
    m = re.search(r"https?://(?:[^/]*?\.)?([^./]+\.[^/.]+)(?:/|$)", url or "")
    return m.group(1).lower() if m else (url or "").lower()


def exclude_reason(task: dict) -> str | None:
    """None when the task is usable; otherwise why it was dropped."""
    dom = domain_of(task.get("website", ""))
    if dom in EXCLUDED_DOMAINS:
        return f"domain {dom}: {EXCLUDED_DOMAINS[dom]}"
    m = _LOGIN_TASK_RE.search(task.get("confirmed_task", ""))
    if m:
        return f"task text requires an account ({m.group(0)!r})"
    return None


def normalize(raw: dict) -> dict:
    """One task from either source -> the common shape. Official rows carry
    `level`; mirror rows don't, so it is derived (rule committed alongside)."""
    ref = int(raw["reference_length"])
    return {
        "source_task_id": str(raw["task_id"]),
        "confirmed_task": str(raw["confirmed_task"]).strip(),
        "website": str(raw["website"]).strip(),
        "reference_length": ref,
        "level": str(raw.get("level") or level_for(ref)).lower(),
    }


def stratified_sample(tasks: list[dict], counts: dict[str, int],
                      per_domain_cap: int = 2) -> list[dict]:
    """Deterministic per-level even-spread over candidates sorted by
    source_task_id (no RNG: same input list -> same subset, reproducible).
    A per-domain cap keeps the subset site-diverse instead of letting one
    heavily-represented domain fill a stratum."""
    picked: list[dict] = []
    domain_seen: dict[str, int] = {}
    for level in ("easy", "medium", "hard"):
        want = counts.get(level, 0)
        pool = sorted((t for t in tasks if t["level"] == level),
                      key=lambda t: t["source_task_id"])
        if not pool or want <= 0:
            continue
        stride = max(1, len(pool) // want)
        chosen: list[dict] = []
        # even-spread first pass, then fill remaining slots in id order
        for cand in pool[::stride] + pool:
            if len(chosen) >= want:
                break
            dom = domain_of(cand["website"])
            if cand in chosen or domain_seen.get(dom, 0) >= per_domain_cap:
                continue
            chosen.append(cand)
            domain_seen[dom] = domain_seen.get(dom, 0) + 1
        picked.extend(chosen)
    return picked


def to_subset_entry(t: dict, added: str) -> dict:
    """One committed subset row. Success conditions are derived with the same
    CJK-aware helper the live runner uses; zero derivable conditions is LEGAL
    (open-ended -> the verifier reports an honest unknown, never a vacuous
    pass). The entry round-trips through BrowserTaskContract so a schema break
    fails at import time, not at eval time."""
    conds = []
    for c in derive_success(t["confirmed_task"]):
        ctype, _, cval = c.partition(":")
        conds.append({"type": ctype, "value": cval})
    entry = {
        "task_id": f"m2w-{t['source_task_id'][:12]}",
        "layer": "external_live_tasks",
        "site": "live",
        "source": "Online-Mind2Web",
        "source_task_id": t["source_task_id"],
        "attribution": ATTRIBUTION,
        "difficulty": t["level"],           # feeds resolve_max_steps (P1-15)
        "reference_length": t["reference_length"],
        "website": t["website"],
        "natural_language_task": t["confirmed_task"],
        "expected_outcome": "The task's derived success conditions hold on the live site",
        "success_conditions": conds,
        "expect_status": "pass",
        "added": added,
        "status": "active",
        "replaced_by": None,
        "update_history": [],
    }
    BrowserTaskContract(                      # schema gate — raises on breakage
        task_id=entry["task_id"],
        natural_language_task=entry["natural_language_task"],
        expected_outcome=entry["expected_outcome"],
        success_conditions=[SuccessCondition(**c) for c in conds])
    return entry


def build_subset(raw_tasks: list[dict], counts: dict[str, int],
                 fetched_from: str, added: str) -> dict:
    tasks = [normalize(r) for r in raw_tasks]
    kept, excluded = [], []
    for t in tasks:
        why = exclude_reason(t)
        (excluded if why else kept).append({**t, "why": why} if why else t)
    sample = stratified_sample(kept, counts)
    entries = [to_subset_entry(t, added) for t in sample]
    if len({e["task_id"] for e in entries}) != len(entries):
        raise ValueError("task_id collision in sampled subset")
    return {
        "note": ("External live-task layer (P1-1): a stratified sample of "
                 "Online-Mind2Web tasks, converted to our task+contract format. "
                 "Task text + metadata only — trajectories/screenshots are never "
                 "committed. Live tasks go stale: staleness check + replacement "
                 "rule in data/browser_eval/external/README.md."),
        "source": {
            "dataset": "osunlp/Online-Mind2Web",
            "license": "CC-BY-4.0",
            "attribution": ATTRIBUTION,
            "homepage": "https://huggingface.co/datasets/osunlp/Online-Mind2Web",
            "fetched_from": fetched_from,
            "fetched_at": added,
            "total_upstream_tasks": len(tasks),
            "level_rule": LEVEL_RULE,
            "sampling": {
                "counts": counts,
                "per_domain_cap": 2,
                "method": "deterministic even-spread by source_task_id per level",
                "excluded_domains": EXCLUDED_DOMAINS,
                "excluded_count": len(excluded),
            },
        },
        "tasks": entries,
    }


# --- network fetchers (thin; not unit-tested) -----------------------------------

def _get(url: str, token: str | None = None) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "wealth-eval/1.0"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def fetch_official(token: str) -> list[dict]:
    return json.loads(_get(OFFICIAL_URL, token))


def fetch_mirror() -> list[dict]:
    """Paginated datasets-server rows -> the official field shape."""
    out, offset = [], 0
    while True:
        page = json.loads(_get(f"{MIRROR_ROWS_URL}&offset={offset}&length=100"))
        for r in page["rows"]:
            row = r["row"]
            meta = json.loads(row["metadata"])
            td = json.loads(row["evaluate_tool"])["arguments"]["arguments"]["task_description"]
            out.append({"task_id": td["task_id"],
                        "confirmed_task": td["confirmed_task"],
                        "website": meta["website"],
                        "reference_length": meta["reference_length"]})
        if len(page["rows"]) < 100:
            return out
        offset += 100


def main() -> None:
    import os
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--counts", default="8,8,4",
                    help="easy,medium,hard sample sizes (default 8,8,4)")
    ap.add_argument("--out", type=Path, default=OUT_DEFAULT)
    ap.add_argument("--token", default=os.environ.get("HF_TOKEN", ""))
    args = ap.parse_args()
    e, m, h = (int(x) for x in args.counts.split(","))
    counts = {"easy": e, "medium": m, "hard": h}

    if args.token:
        raw, src = fetch_official(args.token), OFFICIAL_URL
    else:
        print("no HF_TOKEN -> falling back to the ungated CC-BY mirror "
              "(hud-evals/Online-Mind2Web via datasets-server)")
        raw, src = fetch_mirror(), "hud-evals/Online-Mind2Web (datasets-server rows API)"
    RAW_CACHE.parent.mkdir(parents=True, exist_ok=True)
    RAW_CACHE.write_text(json.dumps(raw, indent=1), encoding="utf-8")

    added = _dt.date.today().isoformat()
    subset = build_subset(raw, counts, src, added)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(subset, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    lv = [t["difficulty"] for t in subset["tasks"]]
    print(f"wrote {args.out} — {len(lv)} tasks "
          f"(easy={lv.count('easy')} medium={lv.count('medium')} hard={lv.count('hard')}) "
          f"from {subset['source']['total_upstream_tasks']} upstream, "
          f"excluded={subset['source']['sampling']['excluded_count']}")


if __name__ == "__main__":
    main()
