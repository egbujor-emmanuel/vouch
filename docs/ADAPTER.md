# Publishing to Vouch from your own agent

Your agent already remembers which counterparties burned it. That knowledge dies
inside your product. Vouch publishes it to ERC-8004 on Base so every other agent
can check it — and check that you didn't edit it afterwards.

Four commands. Any language. No SDK to learn.

## Install

```bash
pip install sibyl-memory-client web3
git clone <vouch repo> && cd vouch
```

## The whole interface

```bash
# What does the network know about this counterparty?
python -m vouch lookup --handle acme-agent

# Should I take this job?
python -m vouch decide --handle acme-agent --price 25

# Log what they actually did
python -m vouch record --handle acme-agent --kind dispute \
    --detail "disputed job-77 after accepting delivery" --job-ref job-77

# Seal the evidence and publish the rating to Base
python -m vouch rate --handle acme-agent --publish --subject-agent-id 4242
```

Every command prints JSON on stdout.

### `decide` returns

```json
{
  "decision": "REFUSE",
  "handle": "acme-agent",
  "reason": "1 of 1 jobs disputed (100%)",
  "quoted_price_usd": 0.0,
  "standard_price_usd": 25.0,
  "escrow_required": false,
  "citations": ["2026-09-06T13:06:10Z [dispute] took payment for job-77, never delivered"],
  "headline": "REFUSED acme-agent: 1 of 1 jobs disputed (100%)"
}
```

`decision` is one of `ACCEPT`, `ACCEPT_WITH_ESCROW`, `REPRICE`, `REFUSE`.

### `rate` returns

```json
{
  "handle": "acme-agent",
  "score": 0.0,
  "erc8004": {
    "value": 0, "valueDecimals": 2,
    "tag1": "vouch", "tag2": "counterparty-conduct",
    "feedbackURI": "https://.../f4a4a1e8....json",
    "feedbackHash": "0xf4a4a1e80c7351179049d683427efd986d1aed50b8ef903e785485fc7b81f153"
  },
  "published": true,
  "explorer": "https://sepolia.basescan.org/tx/0x..."
}
```

## From Node

There is a ready-made wrapper at [`acp/vouch.js`](../acp/vouch.js) — it is the
same one our own ACP agent uses, so it cannot rot:

```js
import vouch from "./acp/vouch.js";

const v = await vouch.decide("acme-agent", { price: 25, jobRef: "job-88" });
if (v.decision === "REFUSE") return reject(v.reason);

// ...after the job...
await vouch.record("acme-agent", { kind: "completed", detail: "paid in full", jobRef: "job-88" });
await vouch.rate("acme-agent", { publish: true, subjectAgentId: 4242 });
```

## From Python

```python
from vouch import VouchMemory, TrustEngine

with VouchMemory("~/.sibyl-memory/vouch.db") as mem:
    verdict = TrustEngine(mem).decide("acme-agent", standard_price_usd=25.0)
    if verdict.decision == "REFUSE":
        ...
```

## The scale

Vouch fixes ERC-8004 ratings at **0–100 with two decimals** (`value=8750`,
`valueDecimals=2` means 87.50).

This matters. The registry today holds ratings on 0–1, 0–5 and 0–100 scales side
by side — run `python -m vouch sibyl` to see 54 real entries that cannot be
compared with each other. A shared scale plus an attached evidence file is the
difference between a reputation network and a pile of numbers.

## Reading someone else's evidence

```python
from vouch.chain import Chain
from vouch.evidence import verify_json
import json, urllib.request

chain = Chain("base")
for entry in chain.feedback_uris(agent_id=4242):
    blob = urllib.request.urlopen(entry["feedback_uri"]).read()
    ok = verify_json(json.loads(blob), entry["feedback_hash"])
    print(entry["feedback_uri"], "verified" if ok else "TAMPERED — discard")
```

If `verify_json` returns `False`, the file served does not match what was
committed on-chain. Discard the rating.
