"""Verify prompt-record classification and verbatim transcript lineage."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "prompts" / "provenance_manifest.json"
RECORD_DIRS = (
    "browser_agent", "eval_design", "failure_triage", "project",
    "rejected_prompts", "transcripts",
)
ALLOWED_TYPES = (
    "Derived decision record",
    "Verbatim transcript excerpt",
    "Verbatim prompt artifact",
)
SECRET_PATTERNS = {
    "openrouter_key": re.compile(r"sk-or-v1-[A-Za-z0-9]{20,}"),
    "openai_key": re.compile(r"sk-[A-Za-z0-9-]{20,}"),
    "github_token": re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    "school_email": re.compile(r"\b[a-z]\d{8}@gs\.ncku\.edu\.tw\b", re.IGNORECASE),
}


def _record_files() -> list[Path]:
    files: list[Path] = []
    for directory in RECORD_DIRS:
        files.extend(p for p in (ROOT / "prompts" / directory).glob("*.md")
                     if p.name != "README.md")
    return sorted(files)


def _record_type(text: str) -> str | None:
    header = text[:1200]
    matches = [kind for kind in ALLOWED_TYPES if kind.lower() in header.lower()]
    return matches[0] if len(matches) == 1 else None


def _verbatim_body(text: str) -> str:
    normalized = text.replace("\r\n", "\n")
    marker = "\n---\n"
    if marker not in normalized:
        raise ValueError("missing verbatim boundary delimiter")
    return normalized.split(marker, 1)[1].strip()


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def verify(manifest_path: Path = DEFAULT_MANIFEST) -> list[str]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    counts: Counter[str] = Counter()

    for path in _record_files():
        rel = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        kind = _record_type(text)
        if kind is None:
            errors.append(f"{rel}: missing or ambiguous Record type")
            continue
        counts[kind] += 1
        if kind == "Verbatim transcript excerpt":
            if "**Verbatim boundary**" not in text:
                errors.append(f"{rel}: Verbatim boundary metadata missing")
            try:
                _verbatim_body(text)
            except ValueError as exc:
                errors.append(f"{rel}: {exc}")
            for name, pattern in SECRET_PATTERNS.items():
                if pattern.search(text):
                    errors.append(f"{rel}: possible {name} in transcript")

    expected_counts = Counter(manifest["record_counts"])
    if counts != expected_counts:
        errors.append(f"record counts drift: expected {dict(expected_counts)}, got {dict(counts)}")

    readme = (ROOT / "prompts" / "README.md").read_text(encoding="utf-8")
    for kind, count in expected_counts.items():
        if f"| **{kind}** | {count} |" not in readme:
            errors.append(f"prompts/README.md: count row drift for {kind}={count}")

    source = manifest["source_commit"]
    for rel, expected_sha in manifest["transcript_body_sha256"].items():
        current = ROOT / rel
        if not current.exists():
            errors.append(f"{rel}: transcript missing")
            continue
        try:
            current_sha = _sha256(_verbatim_body(current.read_text(encoding="utf-8")))
        except ValueError as exc:
            errors.append(f"{rel}: {exc}")
            continue
        if current_sha != expected_sha:
            errors.append(f"{rel}: current verbatim body hash drift")
        proc = subprocess.run(
            ["git", "show", f"{source}:{rel}"], cwd=ROOT,
            capture_output=True, text=True, encoding="utf-8",
        )
        if proc.returncode != 0:
            errors.append(f"{rel}: source Git object unavailable ({source})")
            continue
        try:
            source_sha = _sha256(_verbatim_body(proc.stdout))
        except ValueError as exc:
            errors.append(f"{rel}: source object {exc}")
            continue
        if source_sha != expected_sha:
            errors.append(f"{rel}: source Git body hash differs from manifest")

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args(argv)
    errors = verify(args.manifest)
    if errors:
        print("Prompt provenance: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    total = sum(manifest["record_counts"].values())
    transcripts = len(manifest["transcript_body_sha256"])
    print(f"Prompt provenance: PASS ({total} records, {transcripts} verbatim bodies)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
