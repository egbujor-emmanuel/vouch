#!/usr/bin/env python
"""Stand up a second, independent agent that also runs Vouch.

The point of the network is that one agent acts on another agent's experience.
Evidence we published ourselves does not demonstrate that — so this script
creates a genuinely separate issuer, with its own wallet, its own Sibyl Memory
store, and its own incident, and publishes its rating about the shared
counterparty.

    python scripts/second_issuer.py --network base-sepolia

Costs a small amount of testnet gas. Idempotent: reuses the wallet and skips
publishing if this issuer has already rated the subject.
"""

from __future__ import annotations

import argparse
import os
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eth_account import Account  # noqa: E402

from vouch.chain import Chain  # noqa: E402
from vouch.memory import VouchMemory  # noqa: E402
from vouch.publish import EvidenceStore, build_and_store, score_from_counterparty  # noqa: E402
from vouch.publish import VOUCH_TAG1, VOUCH_TAG2  # noqa: E402
from vouch.trust import TrustEngine  # noqa: E402

ENV = Path(".env")
HANDLE = "swiftrender"
# A second agent's store. Separate file, separate tenant: this agent cannot see
# our memory, and we cannot see theirs. All they share is the chain.
SECOND_DB = ".vouch/second-issuer.db"
SECOND_TENANT = "00000000-0000-0000-0000-0000000000b2"


def load_env() -> None:
    if not ENV.exists():
        return
    for line in ENV.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def save_env(**pairs: str) -> None:
    lines = [
        l
        for l in (ENV.read_text(encoding="utf-8").splitlines() if ENV.exists() else [])
        if not any(l.startswith(f"{k}=") for k in pairs)
    ]
    lines += [f"{k}={v}" for k, v in pairs.items()]
    ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--network", default="base-sepolia")
    ap.add_argument("--fund", type=float, default=0.0004)
    args = ap.parse_args()

    load_env()
    suffix = args.network.replace("-", "_").upper()
    subject = os.environ.get(f"VOUCH_SUBJECT_AGENT_ID_{suffix}")
    if not subject:
        print(f"no VOUCH_SUBJECT_AGENT_ID_{suffix}; run bootstrap_chain.py first")
        return 2
    subject = int(subject)

    primary = Chain(args.network, private_key=os.environ["VOUCH_PRIVATE_KEY"])

    key = os.environ.get("VOUCH_SECOND_ISSUER_KEY")
    if not key:
        key = Account.create(secrets.token_bytes(32)).key.hex()
        save_env(VOUCH_SECOND_ISSUER_KEY=key)
    second = Account.from_key(key)
    print(f"second issuer wallet: {second.address}")

    # This issuer must not be the subject's owner either, or the registry
    # rejects the feedback as self-authored.
    owner = primary.identity.functions.ownerOf(subject).call()
    if owner.lower() == second.address.lower():
        print("second issuer owns the subject; pick a different wallet")
        return 1

    if primary.w3.eth.get_balance(second.address) == 0:
        tx = {
            "from": primary.account.address, "to": second.address,
            "value": primary.w3.to_wei(args.fund, "ether"),
            "nonce": primary.w3.eth.get_transaction_count(primary.account.address, "pending"),
            "chainId": primary.cfg["chain_id"], "gas": 21000,
            "maxFeePerGas": max(primary.w3.eth.gas_price * 2, primary.w3.to_wei(0.01, "gwei")),
            "maxPriorityFeePerGas": primary.w3.to_wei(0.001, "gwei"),
        }
        s = primary.account.sign_transaction(tx)
        raw = getattr(s, "raw_transaction", None) or s.rawTransaction
        r = primary.w3.eth.wait_for_transaction_receipt(
            primary.w3.eth.send_raw_transaction(raw), timeout=300
        )
        print(f"funded second issuer: {primary.explorer_tx(r['transactionHash'].hex())}")

    chain = Chain(args.network, private_key=key)
    if chain.reputation.functions.getLastIndex(subject, second.address).call() > 0:
        print("second issuer has already rated this subject; nothing to do")
        return 0

    # Its own memory, its own experience of the same counterparty.
    Path(SECOND_DB).parent.mkdir(parents=True, exist_ok=True)
    mem = VouchMemory(SECOND_DB, tenant_id=SECOND_TENANT)
    mem.upsert_counterparty(HANDLE, agent_id=subject, jobs_completed=1, jobs_disputed=1)
    # Only log the incident once. Re-running the script must not invent a
    # second dispute, or the evidence inflates every time it is regenerated.
    already = any(
        (e.get("extra") or {}).get("job_ref") == "job-B7" for e in mem.incidents(HANDLE)
    )
    if not already:
        mem.record_incident(
            HANDLE,
            kind="dispute",
            detail="abandoned job mid-delivery after the escrow released, never returned the funds",
            job_ref="job-B7",
        )
    verdict = TrustEngine(mem).decide(HANDLE, standard_price_usd=40.0)
    print(f"second issuer's own verdict: {verdict.headline()}")

    store = EvidenceStore()
    receipt = build_and_store(
        store, memory=mem, handle=HANDLE, verdict=verdict,
        issuer={"handle": "northgate.vouch", "agent_id": None, "address": second.address},
        subject_agent_id=subject,
    )
    print(f"evidence  : {receipt['filename']}")
    print(f"hash      : {receipt['hash']}")
    print("\nPush evidence/ before publishing so the URI resolves, then re-run.")

    if os.environ.get("VOUCH_SECOND_PUBLISH") != "1":
        print("set VOUCH_SECOND_PUBLISH=1 to publish this rating on-chain")
        return 0

    value, decimals = score_from_counterparty(mem.get_counterparty(HANDLE))
    tx_hash = chain.give_feedback(
        subject, value=value, value_decimals=decimals,
        tag1=VOUCH_TAG1, tag2=VOUCH_TAG2, endpoint="",
        feedback_uri=receipt["uri"], feedback_hash=receipt["hash"],
    )
    rcpt = chain.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)
    print(f"published : {chain.explorer_tx(rcpt['transactionHash'].hex())} status {rcpt['status']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
