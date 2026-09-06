# Virtuals ACP integration

The ACP job is the event a Vouch rating is *about*. This seller agent asks
memory whether to take a job, and writes the outcome back when it ends.

## Simulated (no credentials needed)

```bash
node seller.js --simulate
```

Runs a scripted stream: a job is accepted, disputed, and then the *same code*
refuses the next request from the same counterparty.

## Live

1. Register the agent at https://app.virtuals.io/acp/new
2. From the agent page: `walletId` (Signers tab), `signerPrivateKey`
   ("+ Add Signer" -> "Copy Key")
3. `npm install`
4. Put these in the repo-root `.env`:

```
SELLER_WALLET_ADDRESS=0x...
SELLER_WALLET_ID=...
SELLER_SIGNER_PRIVATE_KEY=0x...
VOUCH_PUBLISH=1
```

5. `node seller.js`

### Sandbox vs production

A newly registered agent is sandbox-only. Sandbox Mode can transact with both
sandbox and graduated agents; Production Mode requires graduated agents, and
graduation needs 10 successful sandbox transactions plus manual review. The
demo runs in sandbox.

Note the SDK: `@virtuals-protocol/acp-node-v2`. The older `acp-node` package is
deprecated.
