"""The Vouch memory layer.

Every tier of Sibyl Memory carries weight here. Delete this module and Vouch has
nothing to score an agent on, nothing to hash, and nothing to publish: the
product does not degrade, it stops existing.

  HOT       state       the negotiation currently in flight
  WARM      counterparty  one row per agent, the single source of truth
  WARM      flagged     agents that must never be transacted with again
  COLD      journal     append-only record of every interaction and decision
  REFERENCE policy      the trust rules the decision engine reads
  ARCHIVE   retired counterparties, out of the active set but still on disk
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sibyl_memory_client import MemoryClient
from sibyl_memory_client.exceptions import NotFoundError

DEFAULT_DB = os.environ.get("VOUCH_DB", "~/.sibyl-memory/vouch.db")

CATEGORY_COUNTERPARTY = "counterparty"
CATEGORY_FLAGGED = "flagged"
POLICY_KEY = "vouch/trust-policy"
STATE_OPEN_JOB = "vouch/open-job"

# Sibyl's own agent runs a six-tier schema; the shipped product has five and
# leaves FLAGGED out. We reinstate it as a WARM category with a hard status so
# a flagged agent can never be silently re-accepted.
STATUS_FLAGGED = "flagged"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class VouchMemory:
    """Structured access to the Sibyl store, in the shapes Vouch reasons about."""

    def __init__(self, db_path: str | Path = DEFAULT_DB, tenant_id: str | None = None):
        kwargs: dict[str, Any] = {}
        if tenant_id:
            kwargs["tenant_id"] = tenant_id
        self.db_path = str(db_path)
        self.m = MemoryClient.local(db_path, **kwargs)

    # ---- REFERENCE tier: the rules the decision engine reads -------------

    def set_policy(self, policy: dict[str, Any]) -> None:
        self.m.set_reference(POLICY_KEY, policy, metadata={"updated_at": _now()})

    def get_policy(self) -> dict[str, Any]:
        try:
            row = self.m.get_reference(POLICY_KEY)
        except NotFoundError:
            row = None
        if not row:
            return dict(DEFAULT_POLICY)
        body = row.get("body") if isinstance(row, dict) else row
        return body if isinstance(body, dict) else dict(DEFAULT_POLICY)

    # ---- WARM tier: one row per counterparty, Rule 43 enforced ----------

    def upsert_counterparty(
        self,
        handle: str,
        *,
        agent_id: int | None = None,
        address: str | None = None,
        **fields: Any,
    ) -> dict[str, Any]:
        """Merge new facts into the single source of truth for this agent.

        UNIQUE (tenant_id, category, name) is enforced by the schema, so there
        can only ever be one row describing this counterparty. Drift is
        impossible by construction; we merge rather than append.
        """
        existing = self.get_counterparty(handle) or {}
        body: dict[str, Any] = dict(existing)
        body.setdefault("handle", handle)
        body.setdefault("first_seen", _now())
        if agent_id is not None:
            body["agent_id"] = agent_id
        if address is not None:
            body["address"] = address
        body.update(fields)
        body["last_seen"] = _now()
        body.setdefault("jobs_completed", 0)
        body.setdefault("jobs_disputed", 0)
        body.setdefault("total_value_usd", 0.0)
        self.m.set_entity(CATEGORY_COUNTERPARTY, handle, body)
        return body

    def get_counterparty(self, handle: str) -> dict[str, Any] | None:
        try:
            row = self.m.get_entity(CATEGORY_COUNTERPARTY, handle)
        except NotFoundError:
            return None
        if not row:
            return None
        return row.get("body") if isinstance(row, dict) else None

    def list_counterparties(self, limit: int = 200) -> list[dict[str, Any]]:
        rows = self.m.list_entities(CATEGORY_COUNTERPARTY, limit=limit)
        return [r.get("body", {}) for r in rows if isinstance(r, dict)]

    # ---- The reinstated FLAGGED tier ------------------------------------

    def flag(self, handle: str, reason: str, *, evidence_ref: str | None = None) -> None:
        body = {
            "handle": handle,
            "reason": reason,
            "evidence_ref": evidence_ref,
            "flagged_at": _now(),
        }
        self.m.set_entity(CATEGORY_FLAGGED, handle, body, status=STATUS_FLAGGED)
        self.journal(
            evaluated=[f"counterparty {handle} met flag condition"],
            acted=[f"flagged {handle}: {reason}"],
            forward=["refuse all future jobs from this counterparty"],
        )

    def is_flagged(self, handle: str) -> dict[str, Any] | None:
        try:
            row = self.m.get_entity(CATEGORY_FLAGGED, handle)
        except NotFoundError:
            return None
        if not row:
            return None
        return row.get("body") if isinstance(row, dict) else None

    # ---- COLD tier: append-only journal ---------------------------------

    def journal(
        self,
        *,
        evaluated: list[str] | None = None,
        acted: list[str] | None = None,
        forward: list[str] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> str:
        """Append one decision record. Never rewritten, never deleted."""
        return self.m.write_event(
            evaluated=evaluated,
            acted=acted,
            forward=forward,
            extra=extra,
        )

    def record_incident(
        self,
        handle: str,
        *,
        kind: str,
        detail: str,
        job_ref: str | None = None,
    ) -> str:
        """Log something that went wrong, typed so it can be cited later.

        Incidents are tagged rather than string-matched. A decision record that
        merely contains the word "dispute" is not evidence of one; only an entry
        written here is.
        """
        return self.journal(
            evaluated=[f"outcome review for {handle}" + (f" ({job_ref})" if job_ref else "")],
            acted=[detail],
            forward=[f"weight {kind} against {handle} on next request"],
            extra={"kind": kind, "handle": handle, "job_ref": job_ref, "incident": True},
        )

    def incidents(self, handle: str, limit: int = 200) -> list[dict[str, Any]]:
        """Only the typed incident records for this counterparty."""
        out = []
        for ev in self.m.read_events(limit=limit):
            extra = ev.get("extra") or {}
            if isinstance(extra, dict) and extra.get("incident") and extra.get("handle") == handle:
                out.append(ev)
        out.sort(key=lambda e: str(e.get("ts") or e.get("created_at") or ""))
        return out

    def history(self, handle: str, limit: int = 200) -> list[dict[str, Any]]:
        """Every journal entry that mentions this counterparty, oldest first."""
        events = self.m.read_events(limit=limit)
        hits = []
        needle = handle.lower()
        for ev in events:
            if needle in _flatten(ev).lower():
                hits.append(ev)
        hits.sort(key=lambda e: str(e.get("ts") or e.get("created_at") or ""))
        return hits

    # ---- HOT tier: what is in flight right now --------------------------

    def set_open_job(self, job: dict[str, Any]) -> None:
        self.m.set_state(STATE_OPEN_JOB, job)

    def get_open_job(self) -> dict[str, Any] | None:
        try:
            row = self.m.get_state(STATE_OPEN_JOB)
        except NotFoundError:
            return None
        if not row:
            return None
        return row.get("body") if isinstance(row, dict) else row

    # ---- ARCHIVE tier ---------------------------------------------------

    def retire(self, handle: str, reason: str = "inactive") -> None:
        self.m.archive_entity(CATEGORY_COUNTERPARTY, handle, reason=reason)

    # ---- Search across every tier ---------------------------------------

    def search(self, query: str, limit: int = 20):
        return self.m.search(query, limit=limit)

    def stats(self) -> dict[str, Any]:
        return {
            "db_path": self.db_path,
            "tenant": self.m.get_tenant(),
            "tier": self.m.get_tier(),
            "schema_version": self.m.schema_version(),
            "counterparties": len(self.list_counterparties()),
            "free_tier": self.m.free_tier_status(),
        }


def _flatten(obj: Any) -> str:
    if isinstance(obj, dict):
        return " ".join(_flatten(v) for v in obj.values())
    if isinstance(obj, (list, tuple)):
        return " ".join(_flatten(v) for v in obj)
    return str(obj)


DEFAULT_POLICY: dict[str, Any] = {
    "version": 1,
    "decline_if_flagged": True,
    "dispute_ratio_decline": 0.5,
    "dispute_ratio_reprice": 0.2,
    "reprice_multiplier": 2.0,
    "escrow_required_after_disputes": 1,
    "unknown_counterparty": "accept_with_escrow",
    "notes": "Rules are memory. Editing this record changes what the agent will do.",
}
