/**
 * The agent as a hirer.
 *
 * Selling is the easy half. The half that matters is deciding who to hire, and
 * that is exactly where a reputation record earns its keep: before money moves,
 * not after it is lost.
 *
 *   browse the ACP registry for agents offering what we need
 *   look each one up on ERC-8004 and verify the evidence behind its score
 *   drop the ones with proven disputes, and rank what is left
 *   hire the best remaining candidate
 *   record how it went, so the next run is better informed
 *
 * Browsing and checking are free reads and run by default. Actually creating
 * the job escrows USDC, so it is gated behind --hire and refuses outright on a
 * chain where funds are real unless you also pass --i-know-this-costs-money.
 *
 *   node acp/buyer.js --need "render pipeline"
 *   node acp/buyer.js --need "render pipeline" --hire
 */

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import vouch from "./vouch.js";

const HERE = dirname(fileURLToPath(import.meta.url));

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
loadEnv();

const args = process.argv.slice(2);
const flag = (name) => args.includes(`--${name}`);
const value = (name, fallback = null) => {
  const i = args.indexOf(`--${name}`);
  return i >= 0 && args[i + 1] && !args[i + 1].startsWith("--") ? args[i + 1] : fallback;
};

const NEED = value("need", "render pipeline");
const MAX_PRICE = Number(value("max-price", 25));
const WILL_HIRE = flag("hire");

function log(tag, msg) {
  console.log(`${new Date().toISOString().slice(11, 19)}  ${tag.padEnd(14)} ${msg}`);
}

/**
 * Ask Vouch about a candidate before hiring it.
 *
 * A candidate with no record is not the same as a candidate with a clean one,
 * and both differ from one that other agents have filed disputes against. The
 * distinction is the entire reason this project exists.
 */
async function vet(candidate) {
  const verdict = await vouch.decide(candidate.handle, {
    price: MAX_PRICE,
    agentId: candidate.agentId ?? null,
  });
  return {
    ...candidate,
    verdict,
    hireable: verdict.decision !== "REFUSE",
    // Verified evidence outranks an unbacked score every time. A candidate
    // nobody has vouched for is merely unknown; one with proven disputes is
    // known to be bad.
    rank:
      (verdict.decision === "ACCEPT" ? 2 : verdict.decision === "REFUSE" ? -1 : 1) +
      (verdict.evidence_verified ? 0.5 : 0),
  };
}

async function main() {
  const required = ["SELLER_WALLET_ADDRESS", "SELLER_WALLET_ID", "SELLER_SIGNER_PRIVATE_KEY"];
  const missing = required.filter((k) => !process.env[k]);
  if (missing.length) {
    console.error(`missing env: ${missing.join(", ")} — see acp/README.md`);
    process.exit(2);
  }
  log("need", `looking for an agent that can do: ${NEED}`);

  const { AcpAgent, PrivyAlchemyEvmProviderAdapter } = await import(
    "@virtuals-protocol/acp-node-v2"
  );
  const infra = await import("@account-kit/infra");
  const chain = process.env.ACP_NETWORK === "base-sepolia" ? infra.baseSepolia : infra.base;

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
      ? { serverUrl: constants.ACP_TESTNET_SERVER_URL, privyAppId: constants.TESTNET_PRIVY_APP_ID }
      : {}),
    ...(process.env.BUILDER_CODE ? { builderCode: process.env.BUILDER_CODE } : {}),
  });
  const agent = await AcpAgent.create({ evmProvider: provider });

  log("acp", `browsing the registry on ${chain.name}`);
  let found = [];
  try {
    found = await agent.browseAgents(NEED, { top_k: 8 });
  } catch (e) {
    log("acp", `browse failed: ${e.message?.slice(0, 90)}`);
    process.exit(1);
  }
  log("acp", `${found.length} candidate(s) offered`);

  const candidates = found.map((a) => ({
    handle: a.name || a.handle || a.walletAddress,
    walletAddress: a.walletAddress,
    agentId: a.agentId ?? a.erc8004AgentId ?? null,
    offerings: (a.offerings || []).length,
  }));

  const vetted = [];
  for (const c of candidates) {
    const v = await vet(c);
    vetted.push(v);
    const mark = v.hireable ? "ok" : "REFUSED";
    log("vetted", `${String(v.handle).slice(0, 28).padEnd(28)} ${mark.padEnd(8)} ${v.verdict.reason}`);
    for (const cite of (v.verdict.citations || []).slice(0, 2)) log("  cited", cite.slice(0, 96));
  }

  const shortlist = vetted.filter((v) => v.hireable).sort((a, b) => b.rank - a.rank);
  const refused = vetted.filter((v) => !v.hireable);

  console.log();
  log("shortlist", `${shortlist.length} hireable, ${refused.length} refused on their record`);
  if (!shortlist.length) {
    log("result", "nobody on this registry is safe to hire for that job");
    return;
  }

  const pick = shortlist[0];
  log("pick", `${pick.handle} — ${pick.verdict.reason}`);

  if (!WILL_HIRE) {
    log("dry run", "pass --hire to actually create the job (escrows USDC)");
    return;
  }

  // Creating a job escrows real USDC. On a chain where that money is real,
  // refuse unless the caller has said so in as many words.
  const isMainnet = (chain.id) === 8453;
  if (isMainnet && !flag("i-know-this-costs-money")) {
    log("refused", "creating a job on Base mainnet escrows real USDC — refusing");
    log("refused", "pass --i-know-this-costs-money if that is genuinely intended");
    process.exit(3);
  }

  log("hire", `creating job with ${pick.handle} at ${MAX_PRICE} USDC`);
  const jobId = await agent.createJob(chain.id, {
    providerAddress: pick.walletAddress,
    serviceRequirement: NEED,
    amount: MAX_PRICE,
    expiredAt: new Date(Date.now() + 24 * 3600 * 1000),
  });
  log("hire", `job ${jobId} created`);

  await vouch.record(pick.handle, {
    kind: "note",
    detail: `hired for "${NEED}" at ${MAX_PRICE} USDC (job ${jobId})`,
    agentId: pick.agentId,
  });
  log("memory", "hire recorded; the outcome will be filed when the job closes");
}

main().catch((e) => {
  console.error(e?.message || e);
  process.exit(1);
});
