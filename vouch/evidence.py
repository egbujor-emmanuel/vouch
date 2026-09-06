"""Turn memory into evidence.

ERC-8004 stores a reputation *score* on-chain and leaves two fields for the
story behind it:

    giveFeedback(..., string feedbackURI, bytes32 feedbackHash)

The spec marks both OPTIONAL, and in practice they are empty everywhere. That
is the hole Vouch fills: we serialise the agent's Sibyl Memory record into a
canonical evidence file, commit its keccak-256 digest on Base, and publish the
file at the URI. Anyone can then re-hash the file and prove it was not edited
after the fact.

Canonicalisation is the whole ballgame. If two honest parties serialise the
same record and get different bytes, every hash check fails. So: UTF-8, sorted
keys, no insignificant whitespace, and no floating-point ambiguity.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

try:  # web3 brings a keccak implementation; fall back to pysha3-style if absent
    from eth_utils import keccak as _keccak
except Exception:  # pragma: no cover - exercised only without web3 installed
    _keccak = None

EVIDENCE_SCHEMA = "vouch.evidence/v1"


def canonical_json(obj: Any) -> bytes:
    """Deterministic bytes for any JSON-serialisable object.

    sort_keys makes key order irrelevant; separators strips insignificant
    whitespace; ensure_ascii=False keeps UTF-8 stable rather than escaping it.
    """
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def keccak256(data: bytes) -> bytes:
    if _keccak is None:
        raise RuntimeError(
            "keccak unavailable: install web3/eth-utils (pip install web3)"
        )
    return _keccak(data)


def hash_hex(data: bytes) -> str:
    return "0x" + keccak256(data).hex()


def build_evidence(
    *,
    subject_handle: str,
    subject_agent_id: int | None,
    counterparty: dict[str, Any],
    history: list[dict[str, Any]],
    verdict: dict[str, Any],
    issuer: dict[str, Any],
) -> dict[str, Any]:
    """Assemble the off-chain feedback file from what memory actually holds.

    Every field here is read out of Sibyl Memory. There is no separate store:
    if the memory layer is gone, this function has nothing to serialise.
    """
    return {
        "schema": EVIDENCE_SCHEMA,
        "issued_at": datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "issuer": {
            "handle": issuer.get("handle"),
            "agent_id": issuer.get("agent_id"),
            "address": issuer.get("address"),
        },
        "subject": {
            "handle": subject_handle,
            "agent_id": subject_agent_id,
            "address": counterparty.get("address"),
        },
        "summary": {
            "jobs_completed": counterparty.get("jobs_completed", 0),
            "jobs_disputed": counterparty.get("jobs_disputed", 0),
            "total_value_usd": counterparty.get("total_value_usd", 0.0),
            "first_seen": counterparty.get("first_seen"),
            "last_seen": counterparty.get("last_seen"),
        },
        "verdict": verdict,
        # The journal entries are the actual testimony. Trimmed to the fields
        # that carry meaning so the file stays small enough to serve cheaply.
        "events": [_trim_event(e) for e in history],
    }


def _trim_event(ev: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in ("ts", "created_at", "evaluated", "acted", "forward"):
        val = ev.get(key)
        if val:
            out[key] = val
    extra = ev.get("extra")
    if isinstance(extra, dict) and extra:
        out["extra"] = extra
    return out


def seal(evidence: dict[str, Any]) -> tuple[bytes, str]:
    """Return (canonical bytes, 0x-prefixed keccak-256 digest)."""
    blob = canonical_json(evidence)
    return blob, hash_hex(blob)


def verify(blob: bytes, expected_hash: str) -> bool:
    """Does this file match the digest committed on-chain?

    This is the function that makes a forged record detectable. A counterparty
    can serve any JSON they like at their feedbackURI; only the bytes whose
    keccak matches what was written to Base are admissible.
    """
    if not expected_hash:
        return False
    got = hash_hex(blob).lower()
    want = expected_hash.lower()
    if not want.startswith("0x"):
        want = "0x" + want
    return got == want


def verify_json(obj: Any, expected_hash: str) -> bool:
    """Re-canonicalise a parsed object and check it against the digest."""
    return verify(canonical_json(obj), expected_hash)
