# Vouch

**The vouching layer for autonomous agents.**

Everyone at this hackathon is building agents that remember. Vouch is the layer
that lets them **tell each other**.

Built by team **Attrito** for the [Sibyl Labs Hackathon 2026](https://hack.sibyllabs.org/).

---

## The problem, in thirty seconds

Agents have started hiring each other. Virtuals ACP is a live marketplace on
Base where one agent posts a job, another accepts it, money moves, work gets
delivered — with no human in the loop.

They have no way to check who burned them last time.

There is a standard for this. [ERC-8004](https://eips.ethereum.org/EIPS/eip-8004)
gives every agent an on-chain identity and a reputation registry, live on Base
today. Its write function ends with two fields:

```solidity
function giveFeedback(
    uint256 agentId, int128 value, uint8 valueDecimals,
    string tag1, string tag2, string endpoint,
    string feedbackURI,      // <- a link to the story behind the score
    bytes32 feedbackHash     // <- a keccak-256 commitment to that story
) external
```

The spec marks both **OPTIONAL**. In practice they are empty.

So on-chain agent reputation today is a star rating with no reviews attached.
It is worse than that, and you can check this yourself in one command:

```bash
python -m vouch sibyl
```

That reads the real record of **SIBYL, ERC-8004 agent #20880** — the agent that
runs Sibyl Labs — from Base mainnet. She has **31 clients and 54 feedback
entries**. Their values look like this:

| raw `value` | `valueDecimals` | actually means | `tag1` |
|---|---|---|---|
| 80 | 2 | 0.80 | `ping` |
| 100 | 0 | 100 | `ping` |
| 5 | 0 | 5 | `advisory` |
| 1 | 0 | 1 | `credible` |

Those ratings are not on the same scale. Some are 0–1, some 0–5, some 0–100.
Averaging them produces 56.04, which is arithmetic across incompatible units —
a number that means nothing. **There is no evidence attached to any of them, and
no common scale to compare them on.**

Vouch fills the socket the standard left open.

---

## What Vouch does

An agent running Vouch keeps a structured record of every counterparty it deals
with. When it rates one, it does three things no one else does:

1. **Serialises the record** into a canonical evidence file, straight out of
   Sibyl Memory.
2. **Seals it** with a keccak-256 digest, and publishes the rating on Base with
   `feedbackURI` and `feedbackHash` actually populated.
3. **Fixes the scale** at 0–100 with two decimals, so ratings can be compared.

Any other agent can then fetch the file, re-hash it, and prove it was not edited
after the fact. Reputation stops being a number and becomes **evidence**.

---

## Where memory is load-bearing

> The gate: delete the Sibyl Memory layer. If the project still does what it
> claims, it is a wrapper.

Run it yourself:

```bash
python -m vouch delete-test
```

```
with memory     REFUSED swiftrender: 1 of 1 jobs disputed (100%)
without memory  ACCEPTED swiftrender with escrow: no prior history in memory
```

Without memory, Vouch cannot tell a counterparty that defrauded it from one it
has never met. There is no verdict to publish, nothing to serialise, and nothing
to hash. **The product does not degrade. It stops existing.**

### The exact critical-path calls

| Where | Call | Why it is load-bearing |
|---|---|---|
| [`vouch/memory.py`](vouch/memory.py) `upsert_counterparty()` | `set_entity("counterparty", …)` | **WARM.** The single source of truth per agent. `UNIQUE (tenant_id, category, name)` means drift is impossible by construction |
| [`vouch/memory.py`](vouch/memory.py) `record_incident()` | `write_event(...)` | **COLD.** The append-only testimony that later becomes evidence |
| [`vouch/memory.py`](vouch/memory.py) `flag()` | `set_entity("flagged", …)` | **FLAGGED.** See below |
| [`vouch/memory.py`](vouch/memory.py) `get_policy()` | `get_reference()` | **REFERENCE.** The trust rules the engine reads. Edit this record and the agent behaves differently |
| [`vouch/memory.py`](vouch/memory.py) `set_open_job()` | `set_state()` | **HOT.** The negotiation in flight |
| [`vouch/trust.py`](vouch/trust.py) `TrustEngine.decide()` | `get_counterparty` / `incidents` / `is_flagged` | **The read that changes the action.** `decide()` takes no argument describing the counterparty's past — it looks that up |
| [`vouch/publish.py`](vouch/publish.py) `build_and_store()` | reads WARM + COLD | Memory *is* the evidence file. Nothing else is serialised |

### The sixth tier

Sibyl's own agent runs a **six**-tier schema; the shipped product ships five and
leaves out `FLAGGED` — *"suspected scams, social engineering attempts,
compromised wallets."* Vouch reinstates it as a WARM category with a hard status,
checked before any other rule, so a flagged counterparty can never be silently
re-accepted.

---

## The four proofs

Each is independently runnable, so a curious judge can re-run any of them.

```bash
python -m vouch seed         # session 1: work with an agent, log what happened
python -m vouch coldstart    # session 2: FRESH process — memory changes the call
python -m vouch tamper       # a forged evidence file is rejected
python -m vouch delete-test  # the gate
python -m vouch sibyl        # live read of SIBYL's real record on Base mainnet
```

`seed` and `coldstart` are **separate processes**. The second shares nothing with
the first but the SQLite file.

### Tamper detection

The evidence file is served from a mutable host. The on-chain hash is what makes
editing it detectable — which is the entire point of `feedbackHash`:

```
on-chain hash         0xee6121e896fdfdd3d453ef2a7c412f6cae1caf5d8885a4674c83c98a176b8cd5
honest file verifies  True

forgery               jobs_disputed 1 -> 0, events scrubbed
forged hash           0xbab7d6ec0361b5e88c19cff93f217294e1f499f655f730fe3a531e3eb9d153ea
forged verifies       False
```

No other memory project can show this, because no other project commits a hash.

---

## Partner stacks

### Base

ERC-8004 is read and written directly. Registry addresses are CREATE2-deployed
and identical across mainnets; verified against
[erc-8004/erc-8004-contracts](https://github.com/erc-8004/erc-8004-contracts)
and against Sibyl Labs' own published links.

| | Base Mainnet (8453) | Base Sepolia (84532) |
|---|---|---|
| IdentityRegistry | `0x8004A169FB4a3325136EB29fA0ceB6D2e539a432` | `0x8004A818BFB912233c491871b3d84c89A494BD9e` |
| ReputationRegistry | `0x8004BAa17C55a88189AE136b182e5fdA19dE9b63` | `0x8004B663056A597Dffe9eCcC1965A193B7388713` |

Reads run against **mainnet** (free, no wallet). Writes run on **Sepolia**.

### Virtuals Protocol

An ACP job is the event a rating is *about*. See [`acp/`](acp/).

---

## Setup

Requires Python 3.10+.

```bash
git clone <this repo> && cd vouch
python -m venv .venv && . .venv/Scripts/activate   # Windows
pip install -r requirements.txt
python -m vouch seed && python -m vouch coldstart
```

Nothing touches a network unless you ask it to: `vouch sibyl` reads Base
mainnet, and `vouch seed --publish` writes to Sepolia. Everything else is local.

---

## How memory made this possible

We did not pick Sibyl Memory because the hackathon required it. Three of its
properties are load-bearing for this specific product:

**The schema is the evidence format.** Because memory is structured at write
time into typed tiers, serialising it into a canonical evidence file is a
projection, not an extraction. A vector store would have to reconstruct a record
by similarity search, and the result would not be byte-stable — so it could not
be hashed, so it could not be committed on-chain. **Schema-first memory is what
makes hash-committed reputation possible at all.**

**Rule 43 is what makes the record trustworthy.** `UNIQUE (tenant_id, category,
name)` at the schema level means there is exactly one row describing a
counterparty. An evidence file cannot cite a stale duplicate, because a stale
duplicate cannot exist.

**Append-only journalling is what makes it testimony.** The COLD tier is written
once and never rewritten, so the incident record backing a rating has the same
integrity guarantee as the hash committed on-chain.

---

## Prior work declaration

All code in this repository was written during the build window (Sep 1–10, 2026)
for this hackathon. No pre-existing codebase was carried in.

Third-party dependencies: `sibyl-memory-client` (MIT, Sibyl Labs),
`web3`/`eth-account` (MIT). The ERC-8004 ABIs are transcribed from the
[EIP-8004 specification](https://eips.ethereum.org/EIPS/eip-8004); the registry
contracts are deployed and maintained by the ERC-8004 team, not by us.

The observation that SIBYL's on-chain ratings use inconsistent scales is our own,
made by reading the live registry — see `python -m vouch sibyl`.

## License

MIT. See [LICENSE](LICENSE).
