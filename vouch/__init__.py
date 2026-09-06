"""Vouch — the vouching layer for autonomous agents.

Agents have started hiring each other. Their reputation on-chain is a score
with nothing behind it. Vouch fills ERC-8004's empty feedbackURI/feedbackHash
socket with structured, hash-committed memory, so one agent's experience
becomes evidence another agent can verify.
"""

from .memory import VouchMemory, DEFAULT_POLICY
from .evidence import build_evidence, seal, verify, verify_json, canonical_json
from .trust import TrustEngine, Verdict, ACCEPT, ACCEPT_WITH_ESCROW, REPRICE, REFUSE

__version__ = "0.1.0"
__all__ = [
    "VouchMemory", "DEFAULT_POLICY",
    "build_evidence", "seal", "verify", "verify_json", "canonical_json",
    "TrustEngine", "Verdict",
    "ACCEPT", "ACCEPT_WITH_ESCROW", "REPRICE", "REFUSE",
]
