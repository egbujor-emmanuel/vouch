"""Publishing evidence: write the file, commit the hash.

The evidence file is content-addressed by its own keccak digest, so the URI and
the on-chain commitment cannot drift apart. The host does not need to be
trusted: a mutable host serving a tampered file is exactly the case the hash is
there to catch.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .evidence import build_evidence, seal

DEFAULT_DIR = Path(os.environ.get("VOUCH_EVIDENCE_DIR", "evidence"))
DEFAULT_BASE_URL = os.environ.get("VOUCH_EVIDENCE_BASE_URL", "").rstrip("/")


class EvidenceStore:
    def __init__(self, directory: Path | str = DEFAULT_DIR, base_url: str = DEFAULT_BASE_URL):
        self.dir = Path(directory)
        self.base_url = base_url.rstrip("/")
        self.dir.mkdir(parents=True, exist_ok=True)

    def put(self, evidence: dict[str, Any]) -> dict[str, Any]:
        """Seal the evidence and write it under its own digest."""
        blob, digest = seal(evidence)
        name = f"{digest[2:]}.json"
        path = self.dir / name
        path.write_bytes(blob)
        return {
            "hash": digest,
            "path": str(path),
            "filename": name,
            "uri": f"{self.base_url}/{name}" if self.base_url else f"file://{path.resolve()}",
            "bytes": len(blob),
        }

    def get(self, digest: str) -> bytes | None:
        name = f"{digest[2:] if digest.startswith('0x') else digest}.json"
        path = self.dir / name
        return path.read_bytes() if path.exists() else None

    def list(self) -> list[str]:
        return sorted(p.name for p in self.dir.glob("*.json"))


def build_and_store(
    store: EvidenceStore,
    *,
    memory,
    handle: str,
    verdict,
    issuer: dict[str, Any],
    subject_agent_id: int | None = None,
) -> dict[str, Any]:
    """Read memory, build the evidence file, seal it, write it."""
    cp = memory.get_counterparty(handle) or {}
    evidence = build_evidence(
        subject_handle=handle,
        subject_agent_id=subject_agent_id or cp.get("agent_id"),
        counterparty=cp,
        history=memory.incidents(handle),
        verdict=verdict.to_dict() if hasattr(verdict, "to_dict") else verdict,
        issuer=issuer,
    )
    receipt = store.put(evidence)
    receipt["evidence"] = evidence
    return receipt


def score_from_counterparty(cp: dict[str, Any]) -> tuple[int, int]:
    """Map a memory record onto an ERC-8004 (value, valueDecimals) pair.

    Two decimals on a 0-100 scale, so 87.50 is value=8750, decimals=2. Fixing a
    scale matters: the registry today holds ratings on 0-1, 0-5 and 0-100 scales
    side by side, which makes any aggregate across them meaningless.
    """
    completed = int(cp.get("jobs_completed", 0) or 0)
    disputed = int(cp.get("jobs_disputed", 0) or 0)
    total = completed + disputed
    if total == 0:
        return 5000, 2  # 50.00, no information either way
    ratio = completed / total
    return int(round(ratio * 100 * 100)), 2


VOUCH_TAG1 = "vouch"
VOUCH_TAG2 = "counterparty-conduct"
