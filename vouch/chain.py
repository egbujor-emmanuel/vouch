"""ERC-8004 on Base.

Two registries, deployed with CREATE2 so the addresses are identical on every
supported mainnet. Verified against the erc-8004/erc-8004-contracts repo and
against Sibyl Labs' own links (SIBYL is agent #20880 on Base mainnet).

Reads work with no key and no funds. Writes need a funded key, and the caller
has to opt in explicitly — nothing in this module spends anything by default.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

BASE_MAINNET = {
    "name": "base",
    "chain_id": 8453,
    "rpc": os.environ.get("BASE_RPC_URL", "https://mainnet.base.org"),
    "identity": "0x8004A169FB4a3325136EB29fA0ceB6D2e539a432",
    "reputation": "0x8004BAa17C55a88189AE136b182e5fdA19dE9b63",
    "explorer": "https://basescan.org",
}

BASE_SEPOLIA = {
    "name": "base-sepolia",
    "chain_id": 84532,
    "rpc": os.environ.get("BASE_SEPOLIA_RPC_URL", "https://sepolia.base.org"),
    "identity": "0x8004A818BFB912233c491871b3d84c89A494BD9e",
    "reputation": "0x8004B663056A597Dffe9eCcC1965A193B7388713",
    "explorer": "https://sepolia.basescan.org",
}

NETWORKS = {"base": BASE_MAINNET, "base-sepolia": BASE_SEPOLIA}

# SIBYL's own on-chain identity, used by the demo to read a real record.
SIBYL_AGENT_ID = 20880

REPUTATION_ABI = json.loads(
    """
[
 {"type":"function","name":"giveFeedback","stateMutability":"nonpayable",
  "inputs":[{"name":"agentId","type":"uint256"},{"name":"value","type":"int128"},
            {"name":"valueDecimals","type":"uint8"},{"name":"tag1","type":"string"},
            {"name":"tag2","type":"string"},{"name":"endpoint","type":"string"},
            {"name":"feedbackURI","type":"string"},{"name":"feedbackHash","type":"bytes32"}],
  "outputs":[]},
 {"type":"function","name":"appendResponse","stateMutability":"nonpayable",
  "inputs":[{"name":"agentId","type":"uint256"},{"name":"clientAddress","type":"address"},
            {"name":"feedbackIndex","type":"uint64"},{"name":"responseURI","type":"string"},
            {"name":"responseHash","type":"bytes32"}],
  "outputs":[]},
 {"type":"function","name":"getSummary","stateMutability":"view",
  "inputs":[{"name":"agentId","type":"uint256"},{"name":"clientAddresses","type":"address[]"},
            {"name":"tag1","type":"string"},{"name":"tag2","type":"string"}],
  "outputs":[{"name":"count","type":"uint64"},{"name":"summaryValue","type":"int128"},
             {"name":"summaryValueDecimals","type":"uint8"}]},
 {"type":"function","name":"readFeedback","stateMutability":"view",
  "inputs":[{"name":"agentId","type":"uint256"},{"name":"clientAddress","type":"address"},
            {"name":"feedbackIndex","type":"uint64"}],
  "outputs":[{"name":"value","type":"int128"},{"name":"valueDecimals","type":"uint8"},
             {"name":"tag1","type":"string"},{"name":"tag2","type":"string"},
             {"name":"isRevoked","type":"bool"}]},
 {"type":"function","name":"readAllFeedback","stateMutability":"view",
  "inputs":[{"name":"agentId","type":"uint256"},{"name":"clientAddresses","type":"address[]"},
            {"name":"tag1","type":"string"},{"name":"tag2","type":"string"},
            {"name":"includeRevoked","type":"bool"}],
  "outputs":[{"name":"clients","type":"address[]"},{"name":"feedbackIndexes","type":"uint64[]"},
             {"name":"values","type":"int128[]"},{"name":"valueDecimals","type":"uint8[]"},
             {"name":"tag1s","type":"string[]"},{"name":"tag2s","type":"string[]"},
             {"name":"revokedStatuses","type":"bool[]"}]},
 {"type":"function","name":"getClients","stateMutability":"view",
  "inputs":[{"name":"agentId","type":"uint256"}],
  "outputs":[{"name":"","type":"address[]"}]},
 {"type":"function","name":"getLastIndex","stateMutability":"view",
  "inputs":[{"name":"agentId","type":"uint256"},{"name":"clientAddress","type":"address"}],
  "outputs":[{"name":"","type":"uint64"}]},
 {"type":"event","name":"NewFeedback","anonymous":false,
  "inputs":[{"name":"agentId","type":"uint256","indexed":true},
            {"name":"clientAddress","type":"address","indexed":true},
            {"name":"feedbackIndex","type":"uint64","indexed":false},
            {"name":"value","type":"int128","indexed":false},
            {"name":"valueDecimals","type":"uint8","indexed":false},
            {"name":"indexedTag1","type":"string","indexed":true},
            {"name":"tag1","type":"string","indexed":false},
            {"name":"tag2","type":"string","indexed":false},
            {"name":"endpoint","type":"string","indexed":false},
            {"name":"feedbackURI","type":"string","indexed":false},
            {"name":"feedbackHash","type":"bytes32","indexed":false}]}
]
"""
)

IDENTITY_ABI = json.loads(
    """
[
 {"type":"function","name":"register","stateMutability":"nonpayable",
  "inputs":[{"name":"agentURI","type":"string"}],
  "outputs":[{"name":"agentId","type":"uint256"}]},
 {"type":"function","name":"setAgentURI","stateMutability":"nonpayable",
  "inputs":[{"name":"agentId","type":"uint256"},{"name":"newURI","type":"string"}],
  "outputs":[]},
 {"type":"function","name":"getAgentWallet","stateMutability":"view",
  "inputs":[{"name":"agentId","type":"uint256"}],
  "outputs":[{"name":"","type":"address"}]},
 {"type":"function","name":"ownerOf","stateMutability":"view",
  "inputs":[{"name":"tokenId","type":"uint256"}],
  "outputs":[{"name":"","type":"address"}]},
 {"type":"function","name":"tokenURI","stateMutability":"view",
  "inputs":[{"name":"tokenId","type":"uint256"}],
  "outputs":[{"name":"","type":"string"}]}
]
"""
)


@dataclass
class FeedbackRecord:
    client: str
    index: int
    value: int
    value_decimals: int
    tag1: str
    tag2: str
    revoked: bool

    @property
    def score(self) -> float:
        return self.value / (10 ** self.value_decimals)


class Chain:
    """Thin ERC-8004 client. Read-only unless a private key is supplied."""

    def __init__(self, network: str = "base", private_key: str | None = None):
        from web3 import Web3  # imported lazily so memory-only use needs no web3

        if network not in NETWORKS:
            raise ValueError(f"unknown network {network!r}; try {list(NETWORKS)}")
        self.cfg = NETWORKS[network]
        self.w3 = Web3(Web3.HTTPProvider(self.cfg["rpc"], request_kwargs={"timeout": 30}))
        self.reputation = self.w3.eth.contract(
            address=self.w3.to_checksum_address(self.cfg["reputation"]),
            abi=REPUTATION_ABI,
        )
        self.identity = self.w3.eth.contract(
            address=self.w3.to_checksum_address(self.cfg["identity"]),
            abi=IDENTITY_ABI,
        )
        self.account = None
        if private_key:
            from eth_account import Account

            self.account = Account.from_key(private_key)

    # ---- reads (free, no key) -------------------------------------------

    def connected(self) -> bool:
        try:
            return self.w3.is_connected() and self.w3.eth.chain_id == self.cfg["chain_id"]
        except Exception:
            return False

    def summary(self, agent_id: int, tag1: str = "", tag2: str = "") -> dict[str, Any]:
        count, value, decimals = self.reputation.functions.getSummary(
            agent_id, [], tag1, tag2
        ).call()
        return {
            "agent_id": agent_id,
            "count": count,
            "value": value,
            "value_decimals": decimals,
            "score": (value / (10 ** decimals)) if decimals else float(value),
        }

    def clients(self, agent_id: int) -> list[str]:
        return self.reputation.functions.getClients(agent_id).call()

    def all_feedback(self, agent_id: int, include_revoked: bool = False) -> list[FeedbackRecord]:
        (
            clients,
            indexes,
            values,
            decimals,
            tag1s,
            tag2s,
            revoked,
        ) = self.reputation.functions.readAllFeedback(
            agent_id, [], "", "", include_revoked
        ).call()
        return [
            FeedbackRecord(
                client=clients[i],
                index=indexes[i],
                value=values[i],
                value_decimals=decimals[i],
                tag1=tag1s[i],
                tag2=tag2s[i],
                revoked=revoked[i],
            )
            for i in range(len(clients))
        ]

    def feedback_uris(self, agent_id: int, from_block: int | None = None) -> list[dict[str, Any]]:
        """Pull feedbackURI + feedbackHash out of NewFeedback logs.

        The registry stores URI and hash in the event rather than in storage, so
        this is how a consumer finds the evidence file for a given rating.
        """
        latest = self.w3.eth.block_number
        start = from_block if from_block is not None else max(0, latest - 500_000)
        logs = self.reputation.events.NewFeedback().get_logs(
            from_block=start, to_block=latest, argument_filters={"agentId": agent_id}
        )
        out = []
        for lg in logs:
            a = lg["args"]
            out.append(
                {
                    "client": a["clientAddress"],
                    "index": a["feedbackIndex"],
                    "value": a["value"],
                    "value_decimals": a["valueDecimals"],
                    "tag1": a["tag1"],
                    "tag2": a["tag2"],
                    "endpoint": a["endpoint"],
                    "feedback_uri": a["feedbackURI"],
                    "feedback_hash": "0x" + a["feedbackHash"].hex()
                    if isinstance(a["feedbackHash"], (bytes, bytearray))
                    else a["feedbackHash"],
                    "tx": lg["transactionHash"].hex(),
                    "block": lg["blockNumber"],
                }
            )
        return out

    # ---- write (needs a funded key and an explicit call) -----------------

    def give_feedback(
        self,
        agent_id: int,
        *,
        value: int,
        value_decimals: int = 0,
        tag1: str = "",
        tag2: str = "",
        endpoint: str = "",
        feedback_uri: str = "",
        feedback_hash: str = "0x" + "00" * 32,
        gas_limit: int | None = None,
    ) -> str:
        if self.account is None:
            raise RuntimeError("no private key configured; this client is read-only")
        fh = feedback_hash
        if isinstance(fh, str):
            fh = bytes.fromhex(fh[2:] if fh.startswith("0x") else fh)
        if len(fh) != 32:
            raise ValueError("feedback_hash must be exactly 32 bytes")

        fn = self.reputation.functions.giveFeedback(
            agent_id, value, value_decimals, tag1, tag2, endpoint, feedback_uri, fh
        )
        tx = fn.build_transaction(
            {
                "from": self.account.address,
                "nonce": self.w3.eth.get_transaction_count(self.account.address),
                "chainId": self.cfg["chain_id"],
            }
        )
        if gas_limit:
            tx["gas"] = gas_limit
        signed = self.account.sign_transaction(tx)
        raw = getattr(signed, "raw_transaction", None) or signed.rawTransaction
        tx_hash = self.w3.eth.send_raw_transaction(raw)
        return tx_hash.hex()

    def explorer_tx(self, tx_hash: str) -> str:
        h = tx_hash if tx_hash.startswith("0x") else "0x" + tx_hash
        return f"{self.cfg['explorer']}/tx/{h}"
