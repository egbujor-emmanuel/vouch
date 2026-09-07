"""Reading what *other* agents have published.

Without this module Vouch is a private ledger: an agent that remembers its own
bruises. That is what every other memory build does. The network claim only
becomes true when an agent acts on evidence somebody else wrote — which means
fetching another issuer's feedback, verifying it against the on-chain digest,
and folding it into the decision.

Unverified evidence is not evidence. A rating whose file has gone missing, or
whose bytes no longer hash to the committed digest, is discarded rather than
believed. That is the entire reason the hash field exists.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from .evidence import verify_json

FETCH_TIMEOUT = 20
MAX_EVIDENCE_BYTES = 512 * 1024


@dataclass
class ExternalRating:
    """One rating published by another agent, and whether we believe it."""

    issuer: str
    score: float
    tag1: str
    tag2: str
    uri: str
    digest: str
    tx: str
    verified: bool
    status: str
    # The feedback index identifies which rating this is, per issuer. It is
    # what appendResponse needs to attach a reply to the right entry.
    index: int = 0
    evidence: dict[str, Any] | None = None

    @property
    def disputes(self) -> int:
        if not (self.verified and self.evidence):
            return 0
        return int(self.evidence.get("summary", {}).get("jobs_disputed", 0) or 0)

    @property
    def testimony(self) -> list[str]:
        if not (self.verified and self.evidence):
            return []
        out: list[str] = []
        for ev in self.evidence.get("events", []):
            ts = ev.get("ts") or ev.get("created_at") or ""
            for line in ev.get("acted", []):
                out.append(f"{ts} [{self.issuer[:10]}…] {line}")
        return out


@dataclass
class NetworkView:
    agent_id: int
    ratings: list[ExternalRating] = field(default_factory=list)
    # Set when the lookup itself failed. Callers must distinguish "this agent
    # has no ratings" from "we could not find out".
    error: str | None = None

    @property
    def verified(self) -> list[ExternalRating]:
        return [r for r in self.ratings if r.verified]

    @property
    def rejected(self) -> list[ExternalRating]:
        return [r for r in self.ratings if not r.verified]

    @property
    def verified_disputes(self) -> int:
        return sum(r.disputes for r in self.verified)

    @property
    def mean_score(self) -> float | None:
        scores = [r.score for r in self.verified]
        return sum(scores) / len(scores) if scores else None

    def testimony(self) -> list[str]:
        out: list[str] = []
        for r in self.verified:
            out.extend(r.testimony)
        return out


def _fetch(uri: str) -> bytes:
    if not uri.startswith(("http://", "https://")):
        raise ValueError(f"refusing non-http evidence URI: {uri[:40]}")
    with urllib.request.urlopen(uri, timeout=FETCH_TIMEOUT) as resp:
        return resp.read(MAX_EVIDENCE_BYTES + 1)


def lookup(chain, agent_id: int, *, exclude_issuer: str | None = None,
           from_block: int | None = None, memory=None) -> NetworkView:
    """Gather every published rating for an agent and verify each one.

    `exclude_issuer` drops our own ratings, so the view is genuinely what other
    agents say rather than an echo of what we already hold in memory.
    """
    view = NetworkView(agent_id=agent_id)

    # Prefer the storage-backed read: it is authoritative, needs one call, and
    # is not subject to the block-range limits that make log queries fail on
    # public RPCs. Fall back to logs only where `ratings` is unavailable.
    try:
        if hasattr(chain, "ratings"):
            entries = chain.ratings(agent_id, memory=memory)
        else:
            entries = chain.feedback_uris(agent_id, from_block=from_block)
    except Exception as exc:
        # Never report "no ratings" when the truth is "the lookup failed" —
        # that silently turns a broken connection into a clean bill of health.
        view.error = f"{type(exc).__name__}: {exc}"
        return view

    for e in entries:
        issuer = e.get("client", "")
        if exclude_issuer and issuer.lower() == exclude_issuer.lower():
            continue

        decimals = e.get("value_decimals", 0) or 0
        score = e["value"] / (10 ** decimals) if decimals else float(e["value"])
        uri, digest = e.get("feedback_uri", ""), e.get("feedback_hash", "")

        rating = ExternalRating(
            issuer=issuer, score=score, tag1=e.get("tag1", ""), tag2=e.get("tag2", ""),
            uri=uri, digest=digest, tx=e.get("tx", ""),
            verified=False, status="unchecked", index=int(e.get("index", 0) or 0),
        )

        # A rating with no evidence pointer is exactly the status quo we exist
        # to fix: a number with nothing behind it. Recorded, never believed.
        if not uri or not digest or set(digest.lower().removeprefix("0x")) == {"0"}:
            rating.status = "no evidence attached"
            view.ratings.append(rating)
            continue

        try:
            blob = _fetch(uri)
        except (urllib.error.URLError, ValueError, OSError) as exc:
            rating.status = f"evidence unreachable ({type(exc).__name__})"
            view.ratings.append(rating)
            continue

        if len(blob) > MAX_EVIDENCE_BYTES:
            rating.status = "evidence too large"
            view.ratings.append(rating)
            continue

        try:
            parsed = json.loads(blob)
        except json.JSONDecodeError:
            rating.status = "evidence is not valid JSON"
            view.ratings.append(rating)
            continue

        if not verify_json(parsed, digest):
            rating.status = "HASH MISMATCH — evidence was altered"
            view.ratings.append(rating)
            continue

        rating.verified = True
        rating.status = "verified"
        rating.evidence = parsed
        view.ratings.append(rating)

    return view
