/**
 * A Virtuals ACP seller agent whose accept/refuse decision comes from memory.
 *
 * The ACP job is the event a Vouch rating is *about*:
 *
 *   job.created   -> ask memory whether to take it (accept / reprice / refuse)
 *   job.funded    -> deliver
 *   job.completed -> record the outcome, seal evidence, publish to Base
 *   job.rejected  -> record it; the next request from this agent is judged differently
 *
 * Run with --simulate to exercise the whole path with a scripted event stream,
 * so the integration is testable without touching the network.
 *
 *   node acp/seller.js --simulate
 *   node acp/seller.js                 (needs .env: see acp/README.md)
 */

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import vouch from "./vouch.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const SIMULATE = process.argv.includes("--simulate");
const STANDARD_PRICE = Number(process.env.VOUCH_STANDARD_PRICE || 25);

/** Load ../.env without adding a dependency. Real env vars win. */
function loadEnv() {
  try {
    for (const line of readFileSync(join(HERE, "..", ".env"), "utf8").split(/\r?\n/)) {
      const t = line.trim();
      if (!t || t.startsWith("#") || !t.includes("=")) continue;
      const i = t.indexOf("=");
      const k = t.slice(0, i).trim();
      if (process.env[k] === undefined) process.env[k] = t.slice(i + 1).trim();
    }
  } catch {
    /* no .env is fine for --simulate */
  }
}

function log(tag, msg) {
  console.log(`${new Date().toISOString().slice(11, 19)}  ${tag.padEnd(14)} ${msg}`);
}

/**
 * The core handler. Identical whether events arrive from ACP or the simulator,
 * so the demo path and the production path are the same code.
 */
export async function onJobEvent(evt) {
  const handle = evt.buyerHandle;

  switch (evt.type) {
    case "job.created": {
      const v = await vouch.decide(handle, {
        price: STANDARD_PRICE,
        jobRef: evt.jobId,
        agentId: evt.buyerAgentId,
      });
      log("job.created", `${handle} wants ${evt.service ?? "a job"}`);
      log("memory says", v.headline);
      for (const c of v.citations || []) log("  cited", c);

      if (v.decision === "REFUSE") {
        log("-> REJECT", `declining job ${evt.jobId}`);
        return { action: "reject", reason: v.reason, verdict: v };
      }
      if (v.decision === "REPRICE") {
        log("-> REPRICE", `$${v.standard_price_usd} -> $${v.quoted_price_usd}`);
        return { action: "accept", price: v.quoted_price_usd, verdict: v };
      }
      log("-> ACCEPT", v.escrow_required ? "with escrow" : "standard terms");
      return { action: "accept", price: v.quoted_price_usd, verdict: v };
    }

    case "job.funded": {
      // The service we sell is a counterparty check, so the deliverable *is*
      // the verdict plus a pointer to the evidence behind it.
      const sealed = await vouch.rate(handle, { subjectAgentId: evt.buyerAgentId });
      const current = await vouch.decide(handle, {
        price: STANDARD_PRICE,
        agentId: evt.buyerAgentId,
      });
      log("job.funded", `delivering ${evt.jobId}`);
      log("  evidence", sealed.erc8004?.feedbackHash ?? "(none)");
      return {
        action: "deliver",
        deliverable: JSON.stringify({
          decision: current.decision,
          score: sealed.score,
          citations: current.citations ?? [],
          feedbackURI: sealed.erc8004?.feedbackURI,
          feedbackHash: sealed.erc8004?.feedbackHash,
        }),
      };
    }

    case "job.completed":
      log("job.completed", `recording clean outcome for ${handle}`);
      await vouch.record(handle, {
        kind: "completed",
        detail: `completed ${evt.jobId} without dispute`,
        jobRef: evt.jobId,
        agentId: evt.buyerAgentId,
      });
      return { action: "rated" };

    case "job.rejected":
    case "job.expired": {
      log(evt.type, `recording incident against ${handle}`);
      await vouch.record(handle, {
        kind: "dispute",
        detail: evt.detail || `${evt.type} on ${evt.jobId}`,
        jobRef: evt.jobId,
        agentId: evt.buyerAgentId,
      });
      return { action: "rated" };
    }

    default:
      return { action: "ignore" };
  }
}

// --------------------------------------------------------------- simulate

const SCRIPT = [
  { type: "job.created", jobId: "acp-101", buyerHandle: "swiftrender", buyerAgentId: 4242, service: "render pipeline" },
  { type: "job.funded", jobId: "acp-101", buyerHandle: "swiftrender", buyerAgentId: 4242 },
  { type: "job.rejected", jobId: "acp-101", buyerHandle: "swiftrender", buyerAgentId: 4242,
    detail: "disputed acp-101 after accepting delivery, then short-paid by 60%" },
  { type: "job.created", jobId: "acp-102", buyerHandle: "swiftrender", buyerAgentId: 4242, service: "render pipeline" },
];

async function simulate() {
  // Its own store: the script's point is that job 1 is accepted and job 2
  // refused, which only reads true starting from nothing.
  process.env.VOUCH_DB = process.env.VOUCH_SIM_DB || ".vouch/acp-sim.db";
  try {
    const { rmSync } = await import("node:fs");
    rmSync(join(HERE, "..", process.env.VOUCH_DB), { force: true });
  } catch { /* first run */ }
  console.log("\n  ACP seller · simulated event stream");
  console.log("  " + "-".repeat(62));
  for (const evt of SCRIPT) {
    await onJobEvent(evt);
    console.log();
  }
  console.log("  " + "-".repeat(62));
  console.log("  acp-101 was accepted and acp-102 refused, by the same code.");
  console.log("  The only thing that changed between them is memory.\n");
}

// ------------------------------------------------------------------ live

/** Map an ACP room entry onto the shape onJobEvent expects. */
function toEvent(session, entry) {
  const ev = entry.event ?? {};
  return {
    type: ev.type,
    jobId: session.jobId?.toString?.() ?? String(session.jobId ?? ""),
    // The buyer is identified by address; the handle is whatever we can resolve.
    buyerHandle: ev.clientAddress ?? session.clientAddress ?? session.buyerAddress ?? "unknown",
    buyerAgentId: ev.clientAgentId ?? session.clientAgentId,
    service: ev.serviceRequirement ?? session.serviceRequirement,
    detail: ev.reason ?? ev.message,
  };
}

export async function live() {
  loadEnv();
  const required = ["SELLER_WALLET_ADDRESS", "SELLER_WALLET_ID", "SELLER_SIGNER_PRIVATE_KEY"];
  const missing = required.filter((k) => !process.env[k]);
  if (missing.length) {
    console.error(`missing env: ${missing.join(", ")} — see acp/README.md`);
    process.exit(2);
  }

  const { AcpAgent, PrivyAlchemyEvmProviderAdapter } = await import(
    "@virtuals-protocol/acp-node-v2"
  );
  const infra = await import("@account-kit/infra");
  const chain = process.env.ACP_NETWORK === "base" ? infra.base : infra.baseSepolia;

  // Testnet is a different backend *and* a different Privy app. The adapter
  // defaults to the mainnet pair, so a sandbox agent authenticating against
  // them fails with a bare "Server error 500" and no explanation.
  const constants = await import(
    "@virtuals-protocol/acp-node-v2/dist/core/constants.js"
  );
  const testnet = chain.id !== 8453;
  const provider = await PrivyAlchemyEvmProviderAdapter.create({
    walletAddress: process.env.SELLER_WALLET_ADDRESS,
    walletId: process.env.SELLER_WALLET_ID,
    signerPrivateKey: process.env.SELLER_SIGNER_PRIVATE_KEY,
    chains: [chain],
    ...(testnet
      ? {
          serverUrl: constants.ACP_TESTNET_SERVER_URL,
          privyAppId: constants.TESTNET_PRIVY_APP_ID,
        }
      : {}),
    ...(process.env.BUILDER_CODE ? { builderCode: process.env.BUILDER_CODE } : {}),
  });

  // The key is `evmProvider`, not `provider`. The README shows `provider`, which
  // throws "At least one provider (evmProvider or solanaProvider) must be provided"
  // because createAcpClients destructures evmProvider/solanaProvider.
  const seller = await AcpAgent.create({ evmProvider: provider });

  seller.on("entry", async (session, entry) => {
    if (entry.kind !== "system") return;
    const evt = toEvent(session, entry);
    if (!evt.type) return;
    const result = await onJobEvent(evt);
    try {
      if (result.action === "accept") await session.accept?.();
      if (result.action === "reject") await session.reject?.({ reason: result.reason });
      if (result.action === "deliver") await session.submit?.(result.deliverable);
    } catch (e) {
      log("acp error", `${evt.type} on ${evt.jobId}: ${e.message}`);
    }
  });

  await seller.start(() => log("acp", `connected on ${chain.name ?? "base-sepolia"}`));
  log("acp", `seller online as ${process.env.SELLER_WALLET_ADDRESS}, waiting for jobs`);
}

// pathToFileURL, not string surgery: on Windows a path such as
// "C:\Users\Yoma Maroh\..." percent-encodes the space in import.meta.url, so a
// hand-built file:// string never matches and the script silently does nothing.
const invoked = Boolean(
  process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href,
);
if (invoked || SIMULATE) {
  (SIMULATE ? simulate() : live()).catch((e) => {
    console.error(e);
    process.exit(1);
  });
}
