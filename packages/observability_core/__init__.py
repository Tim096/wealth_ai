"""Shared evidence-first observability layer.

Every run in either app (browser_agent / sec_extractor) emits EvidenceRecord
entries through an EvidenceStore. Nothing may claim success without a
verifier_result backed by observed evidence — see docs/SPEC.md section 4.
"""

from observability_core.evidence import (
    AppName,
    EvidenceRecord,
    EvidenceType,
    StepStatus,
    VerifierResult,
    VerifierStatus,
)
from observability_core.store import EvidenceStore
from observability_core.hashing import sha256_bytes, sha256_text

__all__ = [
    "AppName",
    "EvidenceRecord",
    "EvidenceStore",
    "EvidenceType",
    "StepStatus",
    "VerifierResult",
    "VerifierStatus",
    "sha256_bytes",
    "sha256_text",
]
