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

# The registries are CREATE2-deployed, so testnet addresses are identical across
# chains. Ethereum Sepolia is kept as a validation target: it lets the full
# write path be proven on a chain where faucet ETH is easy to come by, without
# changing a line of the code that runs on Base.
ETHEREUM_SEPOLIA = {
    "name": "ethereum-sepolia",
    "chain_id": 11155111,
    "rpc": os.environ.get("ETH_SEPOLIA_RPC_URL", "https://ethereum-sepolia-rpc.publicnode.com"),
    "identity": "0x8004A818BFB912233c491871b3d84c89A494BD9e",
    "reputation": "0x8004B663056A597Dffe9eCcC1965A193B7388713",
    "explorer": "https://sepolia.etherscan.io",
}

NETWORKS = {
    "base": BASE_MAINNET,
    "base-sepolia": BASE_SEPOLIA,
    "ethereum-sepolia": ETHEREUM_SEPOLIA,
}

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

    def summary(
        self,
        agent_id: int,
        tag1: str = "",
        tag2: str = "",
        clients: list[str] | None = None,
    ) -> dict[str, Any]:
        # The registry reverts with "clientAddresses required" on an empty list,
        # so resolve the full client set first when the caller does not supply one.
        addrs = clients if clients else self.clients(agent_id)
        if not addrs:
            return {
                "agent_id": agent_id, "count": 0, "value": 0,
                "value_decimals": 0, "score": None,
            }
        count, value, decimals = self.reputation.functions.getSummary(
            agent_id, addrs, tag1, tag2
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

    def all_feedback(
        self,
        agent_id: int,
        include_revoked: bool = False,
        clients: list[str] | None = None,
    ) -> list[FeedbackRecord]:
        addrs = clients if clients else self.clients(agent_id)
        if not addrs:
            return []
        (
            clients,
            indexes,
            values,
            decimals,
            tag1s,
            tag2s,
            revoked,
        ) = self.reputation.functions.readAllFeedback(
            agent_id, addrs, "", "", include_revoked
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

    # Public RPCs reject wide eth_getLogs ranges (Base Sepolia answers 413
    # above ~1k blocks), so the window is walked in chunks. The lookback is
    # deliberately modest: 250k blocks would mean 300+ round trips and a UI
    # that appears to hang. Discovered pointers are cached by the caller.
    LOG_CHUNK = 1_000
    LOG_MAX_LOOKBACK = 40_000

    def feedback_uris(
        self,
        agent_id: int,
        from_block: int | None = None,
        *,
        chunk: int | None = None,
    ) -> list[dict[str, Any]]:
        """Pull feedbackURI + feedbackHash out of NewFeedback logs.

        The registry keeps the URI and digest in the event rather than in
        storage, so logs are the only way to find the evidence for a rating.
        Public RPCs cap the block range (Base Sepolia answers 413 Payload Too
        Large), so the window is walked in chunks, newest first. Errors are
        raised rather than swallowed: an empty result must mean "no ratings",
        never "the query failed".
        """
        span = chunk or self.LOG_CHUNK
        latest = self.w3.eth.block_number
        floor = from_block if from_block is not None else max(0, latest - self.LOG_MAX_LOOKBACK)

        out: list[dict[str, Any]] = []
        seen: set[tuple[str, int]] = set()
        hi = latest
        while hi >= floor:
            lo = max(floor, hi - span + 1)
            logs = self.reputation.events.NewFeedback().get_logs(
                from_block=lo, to_block=hi, argument_filters={"agentId": agent_id}
            )
            for lg in logs:
                a = lg["args"]
                key = (a["clientAddress"].lower(), a["feedbackIndex"])
                if key in seen:
                    continue
                seen.add(key)
                fh = a["feedbackHash"]
                out.append({
                    "client": a["clientAddress"],
                    "index": a["feedbackIndex"],
                    "value": a["value"],
                    "value_decimals": a["valueDecimals"],
                    "tag1": a["tag1"],
                    "tag2": a["tag2"],
                    "endpoint": a["endpoint"],
                    "feedback_uri": a["feedbackURI"],
                    "feedback_hash": "0x" + fh.hex() if isinstance(fh, (bytes, bytearray)) else fh,
                    "tx": lg["transactionHash"].hex(),
                    "block": lg["blockNumber"],
                })
            hi = lo - 1
        out.sort(key=lambda e: e["block"])
        return out

    def ratings(
        self,
        agent_id: int,
        *,
        with_evidence: bool = True,
        memory=None,
    ) -> list[dict[str, Any]]:
        """Every rating for an agent, read from storage, enriched from logs.

        Storage is authoritative for who rated whom and what score they gave,
        and it answers in one call with no block-range limits. The evidence
        pointer only exists in the event, so logs fill it in where they can. A
        rating whose URI cannot be located is reported with an empty pointer
        rather than omitted, because a missing pointer is itself a finding.
        """
        clients = self.clients(agent_id)
        if not clients:
            return []

        cl, idx, vals, decs, t1, t2, rev = self.reputation.functions.readAllFeedback(
            agent_id, clients, "", "", False
        ).call()

        by_key: dict[tuple[str, int], dict[str, Any]] = {}
        if with_evidence:
            # Ask memory first. Pointers are immutable once written, so a cache
            # hit is as good as the log and costs nothing.
            missing = []
            for i in range(len(cl)):
                key = (cl[i].lower(), idx[i])
                hit = memory.recall_pointer(agent_id, cl[i], idx[i]) if memory else None
                if hit:
                    by_key[key] = hit
                else:
                    missing.append(key)

            if missing:
                try:
                    for e in self.feedback_uris(agent_id):
                        k = (e["client"].lower(), e["index"])
                        by_key[k] = e
                        if memory:
                            memory.remember_pointer(agent_id, e["client"], e["index"], e)
                except Exception as exc:  # logs unavailable; scores still stand
                    self.last_log_error = exc

        out = []
        for i in range(len(cl)):
            key = (cl[i].lower(), idx[i])
            ev = by_key.get(key, {})
            out.append({
                "client": cl[i],
                "index": idx[i],
                "value": vals[i],
                "value_decimals": decs[i],
                "tag1": t1[i],
                "tag2": t2[i],
                "revoked": rev[i],
                "feedback_uri": ev.get("feedback_uri", ""),
                "feedback_hash": ev.get("feedback_hash", ""),
                "tx": ev.get("tx", ""),
                "block": ev.get("block"),
            })
        return out

    # ---- write (needs a funded key and an explicit call) -----------------

    # Mainnet spends real money. This project runs on testnet, so every writing
    # path refuses Base mainnet unless someone deliberately sets
    # VOUCH_ALLOW_MAINNET=1. A forgotten --network flag cannot cost anything.
    MAINNET_ESCAPE_HATCH = "VOUCH_ALLOW_MAINNET"

    def _refuse_mainnet(self, what: str) -> None:
        if self.cfg["chain_id"] != BASE_MAINNET["chain_id"]:
            return
        if os.environ.get(self.MAINNET_ESCAPE_HATCH) == "1":
            return
        raise RuntimeError(
            f"refusing to {what} on Base mainnet: this would spend real funds. "
            f"Use --network base-sepolia, or set {self.MAINNET_ESCAPE_HATCH}=1 "
            "if you genuinely intend to pay."
        )

    def register_agent(self, agent_uri: str, timeout: int = 240) -> int:
        """Register an ERC-8004 identity and return the new agentId.

        The registry is an ERC-721, so the id arrives as tokenId in the mint
        Transfer log rather than as the first topic of the Registered event.
        """
        if self.account is None:
            raise RuntimeError("no private key configured; this client is read-only")
        self._refuse_mainnet("register an agent")
        fn = self.identity.functions.register(agent_uri)
        tx = fn.build_transaction({
            "from": self.account.address,
            "nonce": self.w3.eth.get_transaction_count(self.account.address, "pending"),
            "chainId": self.cfg["chain_id"],
        })
        signed = self.account.sign_transaction(tx)
        raw = getattr(signed, "raw_transaction", None) or signed.rawTransaction
        receipt = self.w3.eth.wait_for_transaction_receipt(
            self.w3.eth.send_raw_transaction(raw), timeout=timeout
        )
        transfer = self.w3.keccak(text="Transfer(address,address,uint256)")
        for log in receipt["logs"]:
            if len(log["topics"]) == 4 and log["topics"][0] == transfer:
                return int(log["topics"][3].hex(), 16)
        raise RuntimeError("register() succeeded but no agentId was found in the logs")

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
        self._refuse_mainnet("giveFeedback")
        # The registry rejects rating an agent you own ("Self-feedback not
        # allowed"), so issuer and subject must be different owners.
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
                "nonce": self.w3.eth.get_transaction_count(self.account.address, "pending"),
                "chainId": self.cfg["chain_id"],
            }
        )
        if gas_limit:
            tx["gas"] = gas_limit
        signed = self.account.sign_transaction(tx)
        raw = getattr(signed, "raw_transaction", None) or signed.rawTransaction
        tx_hash = self.w3.eth.send_raw_transaction(raw)
        return tx_hash.hex()

    def append_response(
        self,
        agent_id: int,
        client_address: str,
        feedback_index: int,
        *,
        response_uri: str = "",
        response_hash: str = "0x" + "00" * 32,
    ) -> str:
        """Answer a rating made against you.

        ERC-8004 ships this so the rated agent has a right of reply, and it is
        as unused as feedbackURI. A record with only the accuser's side on it
        is a rumour; this is what makes it evidence.
        """
        if self.account is None:
            raise RuntimeError("no private key configured; this client is read-only")
        self._refuse_mainnet("appendResponse")
        rh = response_hash
        if isinstance(rh, str):
            rh = bytes.fromhex(rh[2:] if rh.startswith("0x") else rh)
        if len(rh) != 32:
            raise ValueError("response_hash must be exactly 32 bytes")

        fn = self.reputation.functions.appendResponse(
            agent_id,
            self.w3.to_checksum_address(client_address),
            feedback_index,
            response_uri,
            rh,
        )
        tx = fn.build_transaction({
            "from": self.account.address,
            "nonce": self.w3.eth.get_transaction_count(self.account.address, "pending"),
            "chainId": self.cfg["chain_id"],
        })
        signed = self.account.sign_transaction(tx)
        raw = getattr(signed, "raw_transaction", None) or signed.rawTransaction
        return self.w3.eth.send_raw_transaction(raw).hex()

    def explorer_tx(self, tx_hash: str) -> str:
        h = tx_hash if tx_hash.startswith("0x") else "0x" + tx_hash
        return f"{self.cfg['explorer']}/tx/{h}"
