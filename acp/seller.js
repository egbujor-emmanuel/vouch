/**
 * A Virtuals ACP seller agent whose accept/refuse decision comes from memory.
 *
 * The ACP job is the event a Vouch rating is *about*. Concretely:
 *
 *   job.created  -> ask memory whether to take it (accept / reprice / refuse)
 *   job.funded   -> deliver
 *   job.complete -> record the outcome, seal evidence, publish to Base
 *   job.disputed -> record the dispute; the next request from this agent differs
 *
 * Run with --simulate to exercise the whole path with a scripted event stream,
 * so the integration is testable before Virtuals credentials exist.
 *
 *   node acp/seller.js --simulate
 *   node acp/seller.js                 (needs .env: see acp/README.md)
 */

import vouch from "./vouch.js";

const SIMULATE = process.argv.includes("--simulate");
const STANDARD_PRICE = Number(process.env.VOUCH_STANDARD_PRICE || 25);

function log(tag, msg) {
  const stamp = new Date().toISOString().slice(11, 19);
  console.log(`${stamp}  ${tag.padEnd(14)} ${msg}`);
}

/**
 * The core handler. Identical whether events come from ACP or the simulator,
 * so the demo path and the production path are the same code.
 */
export async function onJobEvent(evt) {
  const handle = evt.buyerHandle;

  switch (evt.type) {
    case "job.created": {
      const v = await vouch.decide(handle, { price: STANDARD_PRICE, jobRef: evt.jobId });
      log("job.created", `${handle} wants ${evt.service}`);
      log("memory says", v.headline);
      for (const c of v.citations || []) log("  cited", c);

      if (v.decision === "REFUSE") {
        log("-> REJECT", `declining job ${evt.jobId}`);
        return { action: "reject", reason: v.reason, verdict: v };
      }
      if (v.decision === "REPRICE") {
        log("-> COUNTER", `quoting $${v.quoted_price_usd} instead of $${v.standard_price_usd}`);
        return { action: "counter", price: v.quoted_price_usd, escrow: true, verdict: v };
      }
      const escrow = v.decision === "ACCEPT_WITH_ESCROW";
      log("-> ACCEPT", escrow ? "with escrow required" : "at standard terms");
      return { action: "accept", price: v.quoted_price_usd, escrow, verdict: v };
    }

    case "job.funded": {
      log("job.funded", `delivering ${evt.jobId}`);
      return { action: "deliver", deliverable: evt.deliverable || "https://attrito.dev/deliverable" };
    }

    case "job.completed": {
      await vouch.record(handle, {
        kind: "completed",
        detail: `completed ACP job ${evt.jobId} and paid in full`,
        jobRef: evt.jobId,
        agentId: evt.buyerAgentId,
      });
      const r = await vouch.rate(handle, {
        publish: Boolean(process.env.VOUCH_PUBLISH),
        subjectAgentId: evt.buyerAgentId,
      });
      log("job.completed", `recorded; score ${r.score}/100`);
      log("evidence", `${r.erc8004.feedbackHash}`);
      if (r.published) log("published", r.explorer);
      return { action: "rated", rating: r };
    }

    case "job.disputed": {
      await vouch.record(handle, {
        kind: "dispute",
        detail: evt.detail || `disputed ACP job ${evt.jobId} after delivery was accepted`,
        jobRef: evt.jobId,
        agentId: evt.buyerAgentId,
        flag: Boolean(evt.fraudulent),
      });
      const r = await vouch.rate(handle, {
        publish: Boolean(process.env.VOUCH_PUBLISH),
        subjectAgentId: evt.buyerAgentId,
      });
      log("job.disputed", `recorded against ${handle}; score now ${r.score}/100`);
      log("evidence", `${r.erc8004.feedbackHash}`);
      if (r.published) log("published", r.explorer);
      return { action: "rated", rating: r };
    }

    default:
      return { action: "ignore" };
  }
}

// --------------------------------------------------------------- simulate

const SCRIPT = [
  { type: "job.created", jobId: "acp-101", buyerHandle: "swiftrender", buyerAgentId: 4242, service: "render pipeline" },
  { type: "job.funded", jobId: "acp-101", buyerHandle: "swiftrender", buyerAgentId: 4242 },
  { type: "job.disputed", jobId: "acp-101", buyerHandle: "swiftrender", buyerAgentId: 4242,
    detail: "disputed acp-101 after accepting delivery, then short-paid by 60%" },
  { type: "job.created", jobId: "acp-102", buyerHandle: "swiftrender", buyerAgentId: 4242, service: "render pipeline" },
];

async function simulate() {
  console.log("\n  ACP seller · simulated event stream");
  console.log("  " + "-".repeat(62));
  for (const evt of SCRIPT) {
    await onJobEvent(evt);
    console.log();
  }
  console.log("  " + "-".repeat(62));
  console.log("  Note acp-101 was accepted and acp-102 refused, by the same code.");
  console.log("  The only thing that changed between them is memory.\n");
}

// ------------------------------------------------------------------ live

async function live() {
  const { default: AcpClient, AcpContractClientV2 } = await import("@virtuals-protocol/acp-node-v2");
  const required = ["SELLER_WALLET_ADDRESS", "SELLER_WALLET_ID", "SELLER_SIGNER_PRIVATE_KEY"];
  const missing = required.filter((k) => !process.env[k]);
  if (missing.length) {
    console.error(`missing env: ${missing.join(", ")} — see acp/README.md`);
    process.exit(2);
  }

  const seller = new AcpClient({
    acpContractClient: await AcpContractClientV2.build(
      process.env.SELLER_SIGNER_PRIVATE_KEY,
      process.env.SELLER_WALLET_ID,
      process.env.SELLER_WALLET_ADDRESS,
    ),
  });

  seller.on("entry", async (session, entry) => {
    if (entry.kind !== "system") return;
    const t = entry.event.type;
    const evt = {
      type: t,
      jobId: session.jobId,
      buyerHandle: session.buyerHandle || session.buyerAddress,
      buyerAgentId: session.buyerAgentId,
      service: session.serviceRequirement,
    };
    const result = await onJobEvent(evt);
    if (result.action === "accept") await session.accept?.();
    if (result.action === "reject") await session.reject?.(result.reason);
    if (result.action === "deliver") await session.submit?.(result.deliverable);
  });

  await seller.start();
  log("acp", "seller online, waiting for jobs");
}

if (import.meta.url === `file://${process.argv[1]}`.replace(/\\/g, "/") || SIMULATE) {
  (SIMULATE ? simulate() : live()).catch((e) => {
    console.error(e);
    process.exit(1);
  });
}
