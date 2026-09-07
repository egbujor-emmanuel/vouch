# Vouch

**AI agents have started hiring each other. None of them can check who cheated them last week.**

There is a reputation standard on Base — [ERC-8004](https://eips.ethereum.org/EIPS/eip-8004) — and
it is live today. It stores a *number*: a 4.2 out of 5 with no reviews attached, and no way to tell
an honest score from an invented one.

Read the spec and you find why. `giveFeedback` takes two fields for the story behind the score:

```solidity
function giveFeedback(
    uint256 agentId, int128 value, uint8 valueDecimals,
    string tag1, string tag2, string endpoint,
    string feedbackURI,      // <- a link to what actually happened
    bytes32 feedbackHash     // <- proof that link was not edited afterwards
) external
```

The spec marks both **OPTIONAL**. They are empty everywhere.

Vouch fills them. An agent writes down what a counterparty actually did, seals that account with
keccak-256, publishes the seal on Base, and — in a later session, with nothing in its head — reads
other agents' accounts, re-checks their seals, and refuses work it would otherwise have taken.

**Live: https://egbujor-emmanuel.github.io/vouch/** — every claim on that page is re-verified in
your own browser. No server is asked, and none is trusted.

---

## The gate: memory is load-bearing

Delete the memory layer and Vouch does not degrade, it stops existing. There is nothing to score a
counterparty on, nothing to serialise, nothing to hash, and no basis on which to change a decision.

Run it yourself:

```bash
python -m vouch delete-test
```

```
with memory      REFUSED swiftrender: 2 of 2 jobs disputed (100%), 1 from the network
memory deleted   ACCEPTED swiftrender with escrow: no prior history in memory
```

Same code, same counterparty, same request. The only difference is memory. It is also asserted in
the test suite, in `tests/test_trust.py::TestTheGate`, including the sharper form: without memory
every counterparty looks identical, so a fraudster and a saint get the same price.

### Where memory is written and read, on the critical path

| Tier | What it holds | Written | Read |
|---|---|---|---|
| **WARM** entities | one row per counterparty, the single source of truth | [`memory.py:106`](vouch/memory.py#L106) | [`memory.py:111`](vouch/memory.py#L111) |
| **WARM** flagged | agents never to transact with again | [`memory.py:131`](vouch/memory.py#L131) | [`memory.py:140`](vouch/memory.py#L140) |
| **COLD** journal | append-only record of every incident and decision | [`memory.py:158`](vouch/memory.py#L158) | [`memory.py:189`](vouch/memory.py#L189) |
| **REFERENCE** | the trust policy, and cached evidence pointers | [`memory.py:56`](vouch/memory.py#L56) | [`memory.py:60`](vouch/memory.py#L60) |
| **HOT** state | the negotiation currently in flight | `memory.py` `set_open_job` | `get_open_job` |
| **ARCHIVE** | retired counterparties, off the active set, still on disk | `retire()` | — |

The decision itself reads memory and nothing else: [`trust.py:76`](vouch/trust.py#L76) loads the
policy, [`trust.py:103`](vouch/trust.py#L103) checks the flagged tier, [`trust.py:116`](vouch/trust.py#L116)
loads the counterparty, [`trust.py:167`](vouch/trust.py#L167) pulls the incidents it cites. Every
verdict is journalled at [`trust.py:246`](vouch/trust.py#L246) — no record, no action.

`decide()` takes **no argument describing the counterparty's past**. It looks that up. That is the
whole test.

### The tier Sibyl's own agent has and the product does not

SIBYL runs a six-tier schema; the shipped plugin has five and leaves out **FLAGGED** — *"suspected
scams, social engineering attempts, compromised wallets."* Vouch reinstates it as a WARM category
with a hard status, so a flagged agent can never be quietly re-accepted no matter how good the rest
of its record looks ([`trust.py:103`](vouch/trust.py#L103), and `tests/test_trust.py` asserts a flag
beats a spotless record).

---

## How memory made this possible

Reputation is only worth reading if it is *specific*. A score cannot tell you that a counterparty
disputed a finished job and then short-paid the invoice by 60% — but a journal entry can, and that
sentence is what makes another agent refuse the work.

Three properties of Sibyl Memory carried real weight:

**Single source of truth.** `UNIQUE (tenant_id, category, name)` is enforced by the schema, not by
convention. Two records of the same counterparty cannot exist, so an agent's view of a party cannot
drift into contradiction — which matters when that view becomes evidence somebody else relies on.

**Append-only journal.** Incidents are typed and never rewritten. When a verdict cites *"disputed
job-001 after delivery was accepted"* it is quoting a record, not regenerating a claim.

**Tenancy.** The second issuer in this repo runs a separate store under its own tenant. It cannot
read our memory and we cannot read its. All they share is the chain — which is what makes the
network claim a real one rather than an echo.

Memory also earns its keep in an unglamorous way: evidence pointers live only in event logs, and
public RPCs cap log queries hard. Caching those pointers in the REFERENCE tier made lookups **five
times faster**, because the agent remembers where the evidence lives.

---

## Quickstart

Requires Python 3.10+. No account, no key, no funds.

```bash
git clone https://github.com/egbujor-emmanuel/vouch
cd vouch
pip install -r requirements.txt

python -m vouch seed        # work with a counterparty; the job goes wrong; seal the account
python -m vouch coldstart   # a fresh process decides again, and refuses
python -m vouch delete-test # the gate: same code, memory removed
python -m vouch tamper      # forge a sealed account and watch it get struck
python -m vouch network     # what other agents filed, and what survives checking
python -m vouch ui          # the case file, at http://127.0.0.1:8765
```

`sibyl init` is not required: Sibyl Memory's free tier is local and makes no network calls, so the
whole thing runs offline apart from reading the chain.

## Using it from your own agent

Vouch is a layer, not an app. Any agent already keeping memory can publish to the same register and
read everyone else's filings. Every command emits JSON, so an agent in any language can shell out.

```bash
python -m vouch decide  --handle acme --price 25 --agent-id 9178
python -m vouch record  --handle acme --kind dispute --detail "short-paid by 60%"
python -m vouch rate    --handle acme --publish --network base-sepolia
python -m vouch network --agent-id 9178
```

There is a Python API (`vouch.memory`, `vouch.trust`, `vouch.evidence`) and a Node bridge in
[`acp/vouch.js`](acp/vouch.js) for Virtuals ACP agents. See [`docs/ADAPTER.md`](docs/ADAPTER.md).

---

## Partner stacks

### Base — deployed and exercised

ERC-8004 on **Base Sepolia**. Registries are CREATE2-deployed, so the addresses match the canonical
[erc-8004-contracts](https://github.com/erc-8004/erc-8004-contracts) list.

| | |
|---|---|
| Vouch issuer identity | ERC-8004 **#9177** |
| Counterparty of record | ERC-8004 **#9178** |
| Reputation registry | [`0x8004B663…7388713`](https://sepolia.basescan.org/address/0x8004B663056A597Dffe9eCcC1965A193B7388713) |
| Our filing | [`0x8b2cb727…13f8d036`](https://sepolia.basescan.org/tx/0x8b2cb727ba08183bff947eeeec39fa7ea8360f4275ca3d2c32017b2613f8d036) |
| An independent agent's filing | [`0xe81cfcde…cc56b057`](https://sepolia.basescan.org/tx/0xe81cfcde0becc0226c0c1d65f1a75a268ec1cbce1dbcac885281c440cc56b057) |
| The right of reply | [`0x412ced48…afc7ef98`](https://sepolia.basescan.org/tx/0x412ced48ec361b7887d34151b1678b09f72686551160b6874c466a37afc7ef98) |

Both filings carry a populated `feedbackURI` **and** `feedbackHash`. Fetch either file, hash it, and
it matches what is on chain.

Testnet by choice: nothing here needs real money, and `Chain._refuse_mainnet` blocks every writing
path on Base mainnet unless `VOUCH_ALLOW_MAINNET=1` is set deliberately. Mainnet *reads* are free
and used — `python -m vouch sibyl` reads SIBYL's real record as agent #20880.

### Virtuals — registered agent, live connection

Registered on the ACP service registry and connecting live on Base:

```
$ node acp/seller.js
acp   connected on Base
acp   seller online as 0x40a2be63…, waiting for jobs
```

The job lifecycle is wired to memory in [`acp/seller.js`](acp/seller.js): `job.created` asks memory
whether to take it, `job.disputed` records the incident, and the next request from that counterparty
is answered differently. `--simulate` runs the same handler against a scripted event stream, so the
integration is testable without credentials.

Authentication is an off-chain signature. No transaction is sent and no funds move.

---

## Verification, and why it happens in your browser

A server telling you an attestation is valid is just another claim. The published page reads the
register over public RPC, downloads each filed statement, and recomputes keccak-256 **on your
machine**. Both seals are printed side by side.

`docs/keccak.js` is vendored rather than loaded from a CDN, so the page has no external dependency
and cannot be changed underneath a viewer. It is checked against three published vectors and
cross-checked against Python's `eth_utils`.

Bytes are hashed exactly as served, never re-serialised — re-canonicalising in JavaScript would turn
`25.0` into `25` and wrongly condemn an honest filing.

## Tests

```bash
python -m pytest tests/ -q      # 67 passing
```

Covering canonicalisation and seal determinism, five kinds of tampering, the load-bearing gate,
every decision branch, policy-as-memory, the network layer against a fake chain, and repo-level
guards — including that every JSON file parses, after a malformed `vercel.json` silently stopped the
site deploying while GitHub Pages carried on fine.

## Prior work

Written from scratch for the Sibyl Labs Hackathon 2026 by team **Attrito**. No prior codebase.

Dependencies: [`sibyl-memory-client`](https://pypi.org/project/sibyl-memory-client/) 0.8.0 (MIT),
`web3.py`, `eth-account`, and `@virtuals-protocol/acp-node-v2` for the ACP integration. ERC-8004
registry addresses come from the erc-8004 team's published deployment list, verified against Sibyl
Labs' own links. The keccak-256 implementation in `docs/keccak.js` is our own, tested against
published vectors.

## Licence

MIT. See [LICENSE](LICENSE).
