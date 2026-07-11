"""Fourth arbitration vote — nlpaueb/edgar-crawler driven ARMS-LENGTH (P0-7a).

License gate (decisive): LICENSE re-verified 2026-07-10 in a --depth 1 clone
at commit 84a8d0c5dd7dd6769526e5ccec534c4e0880d56f — **GPLv3**, not
permissive. Its code is therefore never vendored, imported, or linked
(docs/ATTRIBUTION.md three-tier rule). This adapter runs the UNMODIFIED
upstream CLI (extract_items.py) as a separate process on a locally fetched
checkout, communicating only through files — mere aggregation of independent
programs, not a derivative work. The checkout lives under a gitignored path
(data/raw_filings/external/) and is never redistributed with this repo.

Why subprocess instead of a clean-room reimplementation: the value of the
fourth vote is INDEPENDENT lineage. A regex core reimplemented by us would
share our authorship and approach-family blind spots, i.e. it would not be a
vote at all.

remove_tables=False here (unlike EDGAR-CORPUS, which this same code built
with remove_tables=True), so third_engine.compare_item's full
content+boundary mode applies — never source="corpus".

Missing checkout / missing deps / crash / timeout all degrade to None, which
apply_triangulation records as engine_unavailable — never evidence against
our span. Academic citation upstream requests: Loukas et al. 2021 (EDGAR-CORPUS).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from sec_core.headings import VALID_CODES

REPO_URL = "https://github.com/nlpaueb/edgar-crawler"
PINNED_COMMIT = "84a8d0c5dd7dd6769526e5ccec534c4e0880d56f"
ENV_HOME = "EDGAR_CRAWLER_HOME"  # overrides the default checkout location
_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CHECKOUT = _ROOT / "data" / "raw_filings" / "external" / "edgar_crawler" / "edgar-crawler"
# The only files the upstream CLI needs to run on one 10-K. They are COPIED
# into a throwaway workspace per run (local use only, never redistributed) so
# the checkout stays pristine and DATASET_DIR (derived from __init__.py's
# location) resolves inside the workspace.
_CLI_SOURCES = ("extract_items.py", "item_lists.py", "logger.py", "__init__.py")
_METADATA_COLUMNS = (
    "Type", "filename", "CIK", "Company", "Date", "Period of Report", "SIC",
    "State of Inc", "State location", "Fiscal Year End", "html_index",
    "htm_file_link", "complete_text_file_link",
)
_CONFIG = {
    "extract_items": {
        "raw_filings_folder": "RAW_FILINGS",
        "extracted_filings_folder": "EXTRACTED_FILINGS",
        "filings_metadata_file": "FILINGS_METADATA.csv",
        "filing_types": ["10-K"],
        "include_signature": False,
        "items_to_extract": [],
        "remove_tables": False,   # full-boundary vote; EDGAR-CORPUS used True
        "skip_extracted_filings": False,
    }
}


def checkout_dir() -> Path:
    override = os.environ.get(ENV_HOME)
    return Path(override) if override else DEFAULT_CHECKOUT


def ensure_checkout(fetch: bool = False) -> Path | None:
    """Return the edgar-crawler checkout, optionally cloning it (pinned commit)
    into the gitignored default location. None when absent and not fetched."""
    dest = checkout_dir()
    if (dest / "extract_items.py").is_file():
        return dest
    if not fetch:
        return None
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", REPO_URL, str(dest)],
                       check=True, capture_output=True, timeout=600)
        subprocess.run(["git", "-C", str(dest), "checkout", PINNED_COMMIT],
                       check=True, capture_output=True, timeout=120)
    except Exception:  # noqa: BLE001 — no git / no network: engine unavailable
        return None
    return dest if (dest / "extract_items.py").is_file() else None


def _build_workspace(ws: Path, checkout: Path, raw_html: str) -> None:
    for name in _CLI_SOURCES:
        shutil.copy2(checkout / name, ws / name)
    (ws / "config.json").write_text(json.dumps(_CONFIG, indent=1), encoding="utf-8")
    raw_dir = ws / "datasets" / "RAW_FILINGS" / "10-K"
    raw_dir.mkdir(parents=True)
    (raw_dir / "filing.htm").write_text(raw_html, encoding="utf-8")
    rows = [",".join(_METADATA_COLUMNS),
            ",".join({"Type": "10-K", "filename": "filing.htm", "CIK": "0",
                      "Company": "triangulation", "Date": "2026-01-01",
                      "Period of Report": "2026-01-01"}.get(c, "") for c in _METADATA_COLUMNS)]
    (ws / "datasets" / "FILINGS_METADATA.csv").write_text("\n".join(rows) + "\n",
                                                          encoding="utf-8")


def map_output_items(json_content: dict) -> dict[str, str] | None:
    """Upstream JSON ('item_1A': text, metadata fields, 'SIGNATURE') ->
    item_code -> non-empty text, codes validated against VALID_CODES."""
    items: dict[str, str] = {}
    for key, value in json_content.items():
        if not key.startswith("item_") or not isinstance(value, str):
            continue
        code = key[len("item_"):].upper()
        if code in VALID_CODES and value.strip():
            items[code] = value
    return items or None


def extract_items_edgar_crawler(raw_html: str, *, checkout: Path | None = None,
                                python: str | None = None,
                                timeout: int = 300) -> dict[str, str] | None:
    """Run the unmodified edgar-crawler CLI on the SAME raw HTML our pipeline
    consumed. Returns item_code -> text, or None (engine_unavailable)."""
    try:
        checkout = checkout if checkout is not None else ensure_checkout()
        if checkout is None or not (checkout / "extract_items.py").is_file():
            return None
        with tempfile.TemporaryDirectory(prefix="edgar_crawler_vote_") as tmp:
            ws = Path(tmp)
            _build_workspace(ws, checkout, raw_html)
            env = dict(os.environ,
                       PYTHONUTF8="1",              # upstream open() has no encoding=
                       PYTHONIOENCODING="utf-8")
            proc = subprocess.run([python or sys.executable, "extract_items.py"],
                                  cwd=ws, env=env, capture_output=True, timeout=timeout)
            out = ws / "datasets" / "EXTRACTED_FILINGS" / "10-K" / "filing.json"
            if proc.returncode != 0 or not out.is_file():
                return None
            return map_output_items(json.loads(out.read_text(encoding="utf-8")))
    except Exception:  # noqa: BLE001 — third-party crash is engine_unavailable
        return None
