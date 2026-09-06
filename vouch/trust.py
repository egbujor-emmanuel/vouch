"""The decision engine.

This is where memory stops being storage and starts being consequence. Given a
counterparty and an incoming job, it decides: accept, accept with escrow,
reprice, or refuse — reading only from Sibyl Memory.

The load-bearing test lives here. `decide()` takes no arguments describing the
counterparty's past; it looks that up. Remove the memory layer and every
decision collapses to ACCEPT at standard terms, forever, for everyone.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

from .memory import VouchMemory

ACCEPT = "ACCEPT"
ACCEPT_WITH_ESCROW = "ACCEPT_WITH_ESCROW"
REPRICE = "REPRICE"
REFUSE = "REFUSE"


@dataclass
class Verdict:
    decision: str
    handle: str
    reason: str
    quoted_price_usd: float
    standard_price_usd: float
    escrow_required: bool = False
    citations: list[str] = field(default_factory=list)
    evidence_checked: bool = False
    evidence_verified: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def headline(self) -> str:
        if self.decision == REFUSE:
            return f"REFUSED {self.handle}: {self.reason}"
        if self.decision == REPRICE:
            return (
                f"REPRICED {self.handle}: ${self.standard_price_usd:.2f} "
                f"-> ${self.quoted_price_usd:.2f} ({self.reason})"
            )
        if self.decision == ACCEPT_WITH_ESCROW:
            return f"ACCEPTED {self.handle} with escrow: {self.reason}"
        return f"ACCEPTED {self.handle} at standard terms: {self.reason}"


class TrustEngine:
    def __init__(self, memory: VouchMemory):
        self.mem = memory

    def decide(
        self,
        handle: str,
        *,
        standard_price_usd: float,
        job_ref: str | None = None,
    ) -> Verdict:
        policy = self.mem.get_policy()
        citations: list[str] = []

        # 1. The flagged tier is absolute. Nothing below it gets evaluated.
        flag = self.mem.is_flagged(handle)
        if flag and policy.get("decline_if_flagged", True):
            verdict = Verdict(
                decision=REFUSE,
                handle=handle,
                reason=f"flagged {flag.get('flagged_at')}: {flag.get('reason')}",
                quoted_price_usd=0.0,
                standard_price_usd=standard_price_usd,
                citations=[f"flagged:{flag.get('flagged_at')}"],
            )
            self._record(verdict, job_ref)
            return verdict

        cp = self.mem.get_counterparty(handle)

        # 2. An agent we have never met. Policy decides the posture.
        if not cp:
            posture = policy.get("unknown_counterparty", "accept_with_escrow")
            decision = ACCEPT_WITH_ESCROW if posture == "accept_with_escrow" else ACCEPT
            verdict = Verdict(
                decision=decision,
                handle=handle,
                reason="no prior history in memory",
                quoted_price_usd=standard_price_usd,
                standard_price_usd=standard_price_usd,
                escrow_required=decision == ACCEPT_WITH_ESCROW,
                citations=[],
            )
            self._record(verdict, job_ref)
            return verdict

        completed = int(cp.get("jobs_completed", 0) or 0)
        disputed = int(cp.get("jobs_disputed", 0) or 0)
        total = completed + disputed
        ratio = (disputed / total) if total else 0.0

        # Citations come only from typed incident records, never from decision
        # records that happen to contain the word "dispute".
        for ev in self.mem.incidents(handle):
            kind = (ev.get("extra") or {}).get("kind", "incident")
            for line in (ev.get("acted") or []):
                ts = ev.get("ts") or ev.get("created_at")
                citations.append(f"{ts} [{kind}] {line}")

        # 3. Enough disputes and we stop dealing with them at any price.
        if ratio >= float(policy.get("dispute_ratio_decline", 0.5)) and disputed:
            verdict = Verdict(
                decision=REFUSE,
                handle=handle,
                reason=f"{disputed} of {total} jobs disputed ({ratio:.0%})",
                quoted_price_usd=0.0,
                standard_price_usd=standard_price_usd,
                citations=citations,
            )
            self._record(verdict, job_ref)
            return verdict

        # 4. A worrying record is priced, not refused. Risk has a number.
        if ratio >= float(policy.get("dispute_ratio_reprice", 0.2)) and disputed:
            mult = float(policy.get("reprice_multiplier", 2.0))
            verdict = Verdict(
                decision=REPRICE,
                handle=handle,
                reason=f"{disputed} prior dispute(s) on {total} jobs",
                quoted_price_usd=round(standard_price_usd * mult, 6),
                standard_price_usd=standard_price_usd,
                escrow_required=True,
                citations=citations,
            )
            self._record(verdict, job_ref)
            return verdict

        # 5. Any dispute at all still buys an escrow requirement.
        if disputed >= int(policy.get("escrow_required_after_disputes", 1)):
            verdict = Verdict(
                decision=ACCEPT_WITH_ESCROW,
                handle=handle,
                reason=f"{disputed} prior dispute(s), escrow required",
                quoted_price_usd=standard_price_usd,
                standard_price_usd=standard_price_usd,
                escrow_required=True,
                citations=citations,
            )
            self._record(verdict, job_ref)
            return verdict

        verdict = Verdict(
            decision=ACCEPT,
            handle=handle,
            reason=f"{completed} clean job(s), no disputes on record",
            quoted_price_usd=standard_price_usd,
            standard_price_usd=standard_price_usd,
            citations=citations,
        )
        self._record(verdict, job_ref)
        return verdict

    def _record(self, verdict: Verdict, job_ref: str | None) -> None:
        """Every decision lands in the append-only journal. No record, no action."""
        self.mem.journal(
            evaluated=[
                f"incoming job from {verdict.handle}"
                + (f" (ref {job_ref})" if job_ref else ""),
                f"recalled: {verdict.reason}",
            ],
            acted=[verdict.headline()],
            forward=["publish verdict as ERC-8004 feedback"]
            if verdict.decision != ACCEPT
            else ["deliver job, then rate counterparty"],
            extra={
                "job_ref": job_ref,
                "decision": verdict.decision,
                "quoted_price_usd": verdict.quoted_price_usd,
            },
        )
