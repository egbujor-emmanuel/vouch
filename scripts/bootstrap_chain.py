#!/usr/bin/env python
"""Stand up Vouch's on-chain identities on a given network, idempotently.

    python scripts/bootstrap_chain.py --network base-sepolia

Registers the issuer identity (Vouch itself) and a counterparty identity owned
by a *different* wallet, because the registry rejects self-feedback. Writes the
resulting agent ids back to .env so the demo can use them.

Costs gas. Nothing here runs unless you ask for it by name.
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

ENV = Path(".env")
CARD_BASE = "https://raw.githubusercontent.com/egbujor-emmanuel/vouch/main/agents"


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
    ap.add_argument("--fund-counterparty", type=float, default=0.0004,
                    help="ETH to send the counterparty wallet so it can register")
    args = ap.parse_args()

    load_env()
    key = os.environ.get("VOUCH_PRIVATE_KEY")
    if not key:
        print("VOUCH_PRIVATE_KEY not set")
        return 2

    c = Chain(args.network, private_key=key)
    net = args.network.upper()
    bal = c.w3.eth.get_balance(c.account.address)
    print(f"[{net}] chain {c.w3.eth.chain_id}  block {c.w3.eth.block_number}")
    print(f"[{net}] issuer  {c.account.address}  {c.w3.from_wei(bal,'ether')} ETH")
    print(f"[{net}] gas price {c.w3.from_wei(c.w3.eth.gas_price,'gwei')} gwei")
    if bal == 0:
        print("issuer wallet has no funds on this network")
        return 1

    suffix = args.network.replace("-", "_").upper()

    # 1. The issuer identity. Registering twice would mint a second, pointless
    #    id and spend gas, so an existing one in .env is reused.
    issuer_id = os.environ.get(f"VOUCH_AGENT_ID_{suffix}")
    if issuer_id:
        print(f"\n[{net}] issuer already registered as agentId {issuer_id}, skipping")
    else:
        print(f"\n[{net}] registering issuer identity...")
        issuer_id = c.register_agent(f"{CARD_BASE}/vouch.json")
        print(f"[{net}] issuer agentId = {issuer_id}")
        save_env(**{f"VOUCH_AGENT_ID_{suffix}": str(issuer_id)})

    # 2. A counterparty owned by someone else. Reuse the key if we already made one.
    cp_key = os.environ.get("VOUCH_COUNTERPARTY_KEY")
    if not cp_key:
        cp_key = Account.create(secrets.token_bytes(32)).key.hex()
    cp = Account.from_key(cp_key)
    print(f"\n[{net}] counterparty wallet {cp.address}")

    if c.w3.eth.get_balance(cp.address) == 0:
        amount = c.w3.to_wei(args.fund_counterparty, "ether")
        tx = {
            "from": c.account.address, "to": cp.address, "value": amount,
            "nonce": c.w3.eth.get_transaction_count(c.account.address, "pending"),
            "chainId": c.cfg["chain_id"], "gas": 21000,
            "maxFeePerGas": max(c.w3.eth.gas_price * 2, c.w3.to_wei(0.01, "gwei")),
            "maxPriorityFeePerGas": c.w3.to_wei(0.001, "gwei"),
        }
        s = c.account.sign_transaction(tx)
        raw = getattr(s, "raw_transaction", None) or s.rawTransaction
        r = c.w3.eth.wait_for_transaction_receipt(c.w3.eth.send_raw_transaction(raw), timeout=300)
        print(f"[{net}] funded counterparty: {c.explorer_tx(r['transactionHash'].hex())}")

    cc = Chain(args.network, private_key=cp_key)
    print(f"[{net}] registering counterparty identity...")
    subject_id = os.environ.get(f"VOUCH_SUBJECT_AGENT_ID_{suffix}")
    if subject_id:
        print(f"[{net}] counterparty already registered as agentId {subject_id}, skipping")
    else:
        subject_id = cc.register_agent(f"{CARD_BASE}/swiftrender.json")
        print(f"[{net}] counterparty agentId = {subject_id}")

    save_env(**{
        f"VOUCH_AGENT_ID_{suffix}": str(issuer_id),
        f"VOUCH_SUBJECT_AGENT_ID_{suffix}": str(subject_id),
        "VOUCH_COUNTERPARTY_KEY": cp_key,
    })
    print(f"\n[{net}] saved to .env")
    print(f"  VOUCH_AGENT_ID_{suffix}={issuer_id}")
    print(f"  VOUCH_SUBJECT_AGENT_ID_{suffix}={subject_id}")
    left = c.w3.from_wei(c.w3.eth.get_balance(c.account.address), "ether")
    print(f"[{net}] issuer balance remaining {left} ETH")
    return 0


if __name__ == "__main__":
    sys.exit(main())
