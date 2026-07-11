"""Fetch the NTU itemseg 10-K item-segmentation dataset (P0-2 external benchmark).

Dataset: Lu, Chien, Yen, Chen — "Utilizing Pre-trained and Large Language
Models for 10-K Items Segmentation" (arXiv 2502.08875, Journal of Information
Systems). 3,737 manually line-labelled 10-K filings (2001-2019), BIO tags per
line, split into training_csv/ (3,364) and test_csv/ (373).

LICENSE STANCE (three-tier rule, docs/ATTRIBUTION.md):
  The companion code repo https://github.com/hsinmin/itemseg is CC BY-NC 4.0;
  the dataset archive itself ships NO license file and the journal statement
  says "Data available upon request". We therefore treat the data as
  research-only / non-commercial -> DOWNLOAD-SCRIPT ROUTE: fetched on demand
  into the gitignored data/raw_filings/ tree, NEVER committed to the repo.
  Cite the paper in anything that uses the numbers.

Usage:
  .venv/Scripts/python tools/fetch_ntu_itemseg.py            # test split only
  .venv/Scripts/python tools/fetch_ntu_itemseg.py --full     # + training split
  .venv/Scripts/python tools/fetch_ntu_itemseg.py --force    # re-download

Requires py7zr (pip install py7zr) — lazy-imported so the loaders below stay
usable without it.
"""

from __future__ import annotations

import csv
import hashlib
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DATASET_URL = "https://www.im.ntu.edu.tw/~lu/data/itemseg/itemseg10kdata.7z"
# Verified 2026-07-10 (HTTP 200, Last-Modified 2025-01-06).
DATASET_SHA256 = "769bc7da89cdd0c53f8182f74d294be23839607ad9e75735767be445d1efd727"
DATASET_SIZE = 148_468_503

# Inside the gitignored data/raw_filings/ tree on purpose: research-only data
# must never be commit-able without touching .gitignore.
DEFAULT_DEST = ROOT / "data" / "raw_filings" / "external" / "ntu_itemseg"

# NTU BIO label suffixes ("B1A" / "I1A") are already our item codes.
_GOLD_LABEL_PREFIXES = ("B", "I")


def _arg(flag: str, default: str) -> str:
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_archive(path: Path) -> None:
    """Raise ValueError on size or sha256 mismatch (frozen upstream snapshot)."""
    size = path.stat().st_size
    if size != DATASET_SIZE:
        raise ValueError(f"archive size {size} != expected {DATASET_SIZE}")
    digest = sha256_file(path)
    if digest != DATASET_SHA256:
        raise ValueError(f"archive sha256 {digest} != expected {DATASET_SHA256}")


# -- gold loaders (used by tools/head_to_head.py and tests) --------------------

def parse_bio_csv(path: Path) -> list[tuple[str, str]]:
    """One NTU filing CSV -> [(label, line_text), ...] preserving line order.

    Columns are `label,Content`; labels are O / B<code> / I<code> where <code>
    is the 10-K item code (1, 1A, ... 15).
    """
    rows: list[tuple[str, str]] = []
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            rows.append((row["label"].strip(), row.get("Content") or ""))
    return rows


def label_to_item(label: str) -> str | None:
    """BIO label -> item code ('B1A' -> '1A', 'I15' -> '15', 'O' -> None)."""
    if label.startswith(_GOLD_LABEL_PREFIXES) and len(label) > 1:
        return label[1:].upper()
    return None


def gold_line_labels(rows: list[tuple[str, str]]) -> list[str | None]:
    """Per-line gold item code (None = outside any item)."""
    return [label_to_item(label) for label, _ in rows]


def load_report_list(dataset_dir: Path) -> list[dict]:
    """report_list.csv -> [{'fold', 'uid', 'cik', 'link', 'date_filed', ...}]."""
    path = dataset_dir / "report_list.csv"
    out: list[dict] = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            out.append({
                "fold": row["fold"].strip(),
                "uid": row["uid"].strip(),
                "cik": row["cik"].strip(),
                "company": row.get("company name", "").strip(),
                "date_filed": row.get("date_filed", "").strip(),
                "link": row.get("Link to edgar", "").strip(),
                "sic": row.get("SIC", "").strip(),
            })
    return out


def gold_csv_path(dataset_dir: Path, uid: str, fold: str) -> Path:
    sub = "test_csv" if fold == "test" else "training_csv"
    return dataset_dir / sub / f"uid_{uid}.csv"


# -- download ------------------------------------------------------------------

def download(dest: Path, full: bool = False, force: bool = False) -> Path:
    """Download + verify + extract. Returns the extracted dataset dir."""
    try:
        import py7zr
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("py7zr required: .venv/Scripts/python -m pip install py7zr") from exc

    dest.mkdir(parents=True, exist_ok=True)
    archive = dest / "itemseg10kdata.7z"
    extracted = dest / "itemseg10kdata"

    if archive.exists() and not force:
        print(f"archive exists: {archive}")
    else:
        print(f"downloading {DATASET_URL} ({DATASET_SIZE / 1e6:.0f} MB) ...")
        urllib.request.urlretrieve(DATASET_URL, archive)  # noqa: S310 — pinned https URL
    verify_archive(archive)
    print(f"sha256 OK: {DATASET_SHA256}")

    with py7zr.SevenZipFile(archive) as z:
        names = z.getnames()
        targets = [n for n in names if not n.startswith("itemseg10kdata/training_csv/")]
        if full:
            targets = None  # everything
        z.extract(path=dest, targets=targets)
    n_test = len(list((extracted / "test_csv").glob("*.csv")))
    n_train = len(list((extracted / "training_csv").glob("*.csv"))) \
        if (extracted / "training_csv").exists() else 0
    print(f"extracted -> {extracted}  (test: {n_test}, train: {n_train})")
    print("REMINDER: research-only data (CC BY-NC companion repo); never commit.")
    return extracted


def main() -> None:
    dest = Path(_arg("--dest", str(DEFAULT_DEST)))
    download(dest, full="--full" in sys.argv, force="--force" in sys.argv)


if __name__ == "__main__":
    main()
