"""Append-only JSONL evidence store.

One file per run keeps traces replayable and diff-friendly. Records are
validated on write and on read — a malformed record is itself evidence of a
bug and must fail loudly, not be silently skipped.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

from observability_core.evidence import EvidenceRecord


class EvidenceStore:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _run_file(self, run_id: str) -> Path:
        if not run_id or "/" in run_id or "\\" in run_id or ".." in run_id:
            raise ValueError(f"invalid run_id: {run_id!r}")
        return self.root / f"{run_id}.jsonl"

    def append(self, record: EvidenceRecord) -> None:
        path = self._run_file(record.run_id)
        with path.open("a", encoding="utf-8") as f:
            f.write(record.model_dump_json() + "\n")

    def read_run(self, run_id: str) -> list[EvidenceRecord]:
        path = self._run_file(run_id)
        if not path.exists():
            return []
        return list(self._iter_file(path))

    def iter_all(self) -> Iterator[EvidenceRecord]:
        for path in sorted(self.root.glob("*.jsonl")):
            yield from self._iter_file(path)

    @staticmethod
    def _iter_file(path: Path) -> Iterator[EvidenceRecord]:
        with path.open("r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    yield EvidenceRecord.model_validate_json(line)
                except ValueError as e:
                    raise ValueError(f"{path}:{line_no}: corrupt evidence record") from e
