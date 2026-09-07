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
    """Decides from memory, and — when a chain is wired in — from the network.

    Own memory alone makes this a private ledger: an agent that remembers only
    its own bruises. Passing a `chain` lets it also read what *other* issuers
    published about a counterparty, verify each file against its on-chain
    digest, and count only what survives that check.
    """

    def __init__(self, memory: VouchMemory, chain=None, issuer_address: str | None = None):
        self.mem = memory
        self.chain = chain
        self.issuer_address = issuer_address

    def decide(
        self,
        handle: str,
        *,
        standard_price_usd: float,
        job_ref: str | None = None,
        agent_id: int | None = None,
        use_network: bool = True,
    ) -> Verdict:
        policy = self.mem.get_policy()
        citations: list[str] = []

        # What other agents have published about this one. Ratings whose
        # evidence is missing or whose bytes no longer match the committed
        # digest are collected but never counted.
        view = None
        if self.chain is not None and use_network:
            cp_row = self.mem.get_counterparty(handle) or {}
            subject = agent_id or cp_row.get("agent_id")
            if subject:
                from .network import lookup

                view = lookup(
                    self.chain, int(subject), exclude_issuer=self.issuer_address
                )
                for r in view.verified:
                    citations.append(
                        f"network [{r.issuer[:10]}…] {r.score:.2f}/100 · verified · {r.tx[:12]}…"
                    )
                    citations.extend(r.testimony)
                for r in view.rejected:
                    citations.append(
                        f"network [{r.issuer[:10]}…] DISCARDED — {r.status}"
                    )

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
        net_disputed = view.verified_disputes if view else 0
        checked = view is not None
        verified_any = bool(view and view.verified) if checked else None

        # 2. An agent we have never met ourselves. The network still gets a say:
        #    somebody else's verified evidence is the whole point of publishing.
        if not cp:
            if net_disputed:
                verdict = Verdict(
                    decision=REFUSE,
                    handle=handle,
                    reason=(
                        f"never dealt with them, but {net_disputed} verified "
                        f"dispute(s) published by {len(view.verified)} other agent(s)"
                    ),
                    quoted_price_usd=0.0,
                    standard_price_usd=standard_price_usd,
                    citations=citations,
                    evidence_checked=checked,
                    evidence_verified=verified_any,
                )
                self._record(verdict, job_ref)
                return verdict

            posture = policy.get("unknown_counterparty", "accept_with_escrow")
            decision = ACCEPT_WITH_ESCROW if posture == "accept_with_escrow" else ACCEPT
            verdict = Verdict(
                decision=decision,
                handle=handle,
                reason="no prior history in memory"
                + (", nothing verified on the network" if checked else ""),
                quoted_price_usd=standard_price_usd,
                standard_price_usd=standard_price_usd,
                escrow_required=decision == ACCEPT_WITH_ESCROW,
                citations=citations,
                evidence_checked=checked,
                evidence_verified=verified_any,
            )
            self._record(verdict, job_ref)
            return verdict

        completed = int(cp.get("jobs_completed", 0) or 0)
        own_disputed = int(cp.get("jobs_disputed", 0) or 0)
        # Our own experience and the network's verified experience both count.
        disputed = own_disputed + net_disputed
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
                reason=(
                    f"{disputed} of {total} jobs disputed ({ratio:.0%})"
                    + (f", {net_disputed} from the network" if net_disputed else "")
                ),
                quoted_price_usd=0.0,
                standard_price_usd=standard_price_usd,
                citations=citations,
                evidence_checked=checked,
                evidence_verified=verified_any,
            )
            self._record(verdict, job_ref)
            return verdict

        # 4. A worrying record is priced, not refused. Risk has a number.
        if ratio >= float(policy.get("dispute_ratio_reprice", 0.2)) and disputed:
            mult = float(policy.get("reprice_multiplier", 2.0))
            verdict = Verdict(
                decision=REPRICE,
                handle=handle,
                reason=(
                    f"{disputed} prior dispute(s) on {total} jobs"
                    + (f", {net_disputed} from the network" if net_disputed else "")
                ),
                quoted_price_usd=round(standard_price_usd * mult, 6),
                standard_price_usd=standard_price_usd,
                escrow_required=True,
                citations=citations,
                evidence_checked=checked,
                evidence_verified=verified_any,
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
                evidence_checked=checked,
                evidence_verified=verified_any,
            )
            self._record(verdict, job_ref)
            return verdict

        verdict = Verdict(
            decision=ACCEPT,
            handle=handle,
            reason=f"{completed} clean job(s), no disputes on record"
            + (", network clean too" if checked and not net_disputed else ""),
            quoted_price_usd=standard_price_usd,
            standard_price_usd=standard_price_usd,
            citations=citations,
            evidence_checked=checked,
            evidence_verified=verified_any,
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
