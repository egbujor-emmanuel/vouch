"""Public facts about this deployment.

A fresh clone has no .env, and without these it fell back to a placeholder
agent id, wrote file:// evidence URIs, and found nothing on the register — so
the one thing that makes Vouch more than a private ledger was invisible to
anyone who had just cloned it.

None of this is secret. Agent ids, the issuer address and the evidence
location are all published on-chain or in this repository already; they are
facts about where our filings live, not credentials. Keys are never defaulted:
they come from the environment or nowhere, and every writing path fails
closed without them.

Real environment variables always win, so a fork points these at its own
deployment by setting them.
"""

from __future__ import annotations

import os

REPO = "https://github.com/egbujor-emmanuel/vouch"

PUBLIC_DEFAULTS: dict[str, str] = {
    # Where our sealed statements are served from. Content-addressed, so the
    # filename is the seal and a wrong file cannot masquerade as a right one.
    "VOUCH_EVIDENCE_BASE_URL":
        "https://raw.githubusercontent.com/egbujor-emmanuel/vouch/main/evidence",

    # ERC-8004 identities on Base Sepolia.
    "VOUCH_AGENT_ID_BASE_SEPOLIA": "9177",          # the filer, Vouch itself
    "VOUCH_SUBJECT_AGENT_ID_BASE_SEPOLIA": "9178",  # the counterparty of record

    # The wallet our filings are signed by. Public: it is the clientAddress on
    # every statement we have filed. Holding it is what excludes our own
    # filings from "what other agents say".
    "VOUCH_ADDRESS": "0xEf67DD86cC1E9FE35De02e2c0A8C47E9a3f7ed83",
    "VOUCH_HANDLE": "attrito.vouch",
}

# Anything matching these is a credential and must never be defaulted here.
SECRET_MARKERS = ("PRIVATE_KEY", "SIGNER", "SECRET", "TOKEN", "MNEMONIC")


def apply_public_defaults() -> None:
    """Fill in what a clone does not have, without overriding what it does."""
    for key, value in PUBLIC_DEFAULTS.items():
        if any(marker in key for marker in SECRET_MARKERS):
            raise RuntimeError(f"refusing to ship a default for {key}")
        os.environ.setdefault(key, value)
