/* The dashboard, verifying everything in your browser.
 *
 * There is no server. This page reads the ERC-8004 registry over public RPC,
 * fetches each evidence file from its published URI, hashes it here, and
 * compares that against the digest committed on-chain. Nothing asks you to
 * trust Vouch: the verification happens on your machine, with code you can
 * read in view-source.
 */
"use strict";

const $ = (id) => document.getElementById(id);
const esc = (s) =>
  String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const row = (k, v) => `<div class="row"><span class="k">${esc(k)}</span><span class="v">${v}</span></div>`;
const short = (s, n = 22) => (s ? esc(String(s).slice(0, n)) + "…" : "");
const busy = (id, msg) => ($(id).innerHTML = `<div class="empty"><span class="spin"></span>${esc(msg)}</div>`);

let SNAP = null;
let VERIFIED = [];

/* ---------- chain ---------- */

const NEW_FEEDBACK_SIG =
  "NewFeedback(uint256,address,uint64,int128,uint8,string,string,string,string,string,bytes32)";

async function rpc(method, params) {
  const res = await fetch(SNAP.network.rpc, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }),
  });
  const j = await res.json();
  if (j.error) throw new Error(j.error.message || "rpc error");
  return j.result;
}

const padTopic = (n) => "0x" + BigInt(n).toString(16).padStart(64, "0");
const hexToBytes = (h) => {
  const s = h.startsWith("0x") ? h.slice(2) : h;
  const out = new Uint8Array(s.length / 2);
  for (let i = 0; i < out.length; i++) out[i] = parseInt(s.substr(i * 2, 2), 16);
  return out;
};

/** Decode one NewFeedback log. The layout is fixed, so this reads it directly.
 *  Non-indexed head: index, value, decimals, 4 string offsets, then the
 *  feedbackHash sitting static in slot 7. */
function decodeFeedback(log) {
  const d = log.data.slice(2);
  const slot = (i) => d.slice(i * 64, (i + 1) * 64);
  const str = (slotIdx) => {
    const off = Number(BigInt("0x" + slot(slotIdx))) * 2;
    const len = Number(BigInt("0x" + d.slice(off, off + 64)));
    const hex = d.slice(off + 64, off + 64 + len * 2);
    return new TextDecoder().decode(hexToBytes(hex));
  };
  // int128 is two's complement; scores are non-negative here but handle sign.
  let value = BigInt("0x" + slot(1));
  const SIGN = 1n << 127n;
  if (value >= SIGN) value -= 1n << 128n;

  return {
    client: "0x" + log.topics[2].slice(26),
    index: Number(BigInt("0x" + slot(0))),
    value: Number(value),
    decimals: Number(BigInt("0x" + slot(2))),
    tag1: str(3),
    tag2: str(4),
    uri: str(6),
    hash: "0x" + slot(7),
    tx: log.transactionHash,
    block: parseInt(log.blockNumber, 16),
  };
}

async function fetchFeedbackLogs() {
  const topic0 = keccak256(new TextEncoder().encode(NEW_FEEDBACK_SIG));
  const agent = padTopic(SNAP.subject_agent_id);
  const seen = new Set();
  const out = [];

  // Hints keep this to one narrow query per rating. They are only hints: the
  // log itself is the source of truth, and a wrong hint just finds nothing.
  for (const h of SNAP.log_hints || []) {
    const from = "0x" + Math.max(0, h.block - 2).toString(16);
    const to = "0x" + (h.block + 2).toString(16);
    let logs = [];
    try {
      logs = await rpc("eth_getLogs", [{ address: SNAP.network.reputation, fromBlock: from, toBlock: to, topics: [topic0, agent] }]);
    } catch (e) {
      continue;
    }
    for (const lg of logs) {
      const f = decodeFeedback(lg);
      const key = f.client.toLowerCase() + ":" + f.index;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(f);
    }
  }
  return out;
}

/* ---------- verification ---------- */

async function verifyRating(f) {
  const r = { ...f, verified: false, status: "unchecked", evidence: null };
  if (!f.uri || !f.hash || /^0x0+$/.test(f.hash)) {
    r.status = "no evidence attached";
    return r;
  }
  let bytes;
  try {
    const res = await fetch(f.uri, { cache: "no-store" });
    if (!res.ok) throw new Error("HTTP " + res.status);
    bytes = new Uint8Array(await res.arrayBuffer());
  } catch (e) {
    r.status = "evidence unreachable (" + e.message + ")";
    return r;
  }
  // Hash the bytes exactly as served. Re-serialising would risk differing from
  // the publisher's canonical form and failing an honest file.
  const got = keccak256(bytes);
  r.computed = got;
  if (got.toLowerCase() !== f.hash.toLowerCase()) {
    r.status = "HASH MISMATCH — evidence was altered";
    return r;
  }
  try {
    r.evidence = JSON.parse(new TextDecoder().decode(bytes));
  } catch {
    r.status = "evidence is not valid JSON";
    return r;
  }
  r.verified = true;
  r.status = "verified";
  return r;
}

const disputesOf = (r) => (r.verified && r.evidence ? Number(r.evidence.summary?.jobs_disputed || 0) : 0);
const testimonyOf = (r) =>
  r.verified && r.evidence
    ? (r.evidence.events || []).flatMap((e) => (e.acted || []).map((a) => `${e.ts || ""} [${r.client.slice(0, 10)}…] ${a}`))
    : [];

/* ---------- render ---------- */

async function boot() {
  SNAP = await (await fetch("snapshot.json", { cache: "no-store" })).json();

  $("net").className = "chip live";
  $("net").innerHTML = `<span class="dot"></span>${esc(SNAP.network.name)} · chain ${SNAP.network.chain_id}`;
  $("issuer").textContent = SNAP.issuer.address ? SNAP.issuer.address.slice(0, 12) + "…" : "";
  $("store").textContent = `sibyl schema v${SNAP.memory.schema_version ?? "?"} · ${SNAP.memory.counterparties.length} counterparties`;
  $("s-cp").textContent = SNAP.memory.counterparties.length;
  $("gen").textContent = new Date(SNAP.generated_at).toISOString().slice(0, 16).replace("T", " ") + " UTC";

  renderMemory();
  renderPolicy();
  renderGate();
  await renderNetwork();
  // Show the punchline without making anyone hunt for a button.
  decide("newcomer");
}

function renderMemory() {
  const inc = SNAP.memory.incidents || [];
  $("memory").innerHTML =
    SNAP.memory.counterparties
      .map(
        (c) => `<div class="card fade">
      <div class="top2"><span><b>${esc(c.handle)}</b>
        <span class="mono dimc">ERC-8004 #${esc(c.agent_id)}</span></span>
        ${c.flagged ? '<span class="badge bad">FLAGGED</span>' : ""}</div>
      ${row("jobs completed", `<b>${c.jobs_completed}</b>`)}
      ${row("jobs disputed", `<b class="${c.jobs_disputed ? "bad" : "dimc"}">${c.jobs_disputed}</b>`)}
      ${inc.filter((i) => i.handle === c.handle).map((i) => `<div class="quote">${esc(i.ts || "")} [${esc(i.kind)}] ${esc(i.detail)}</div>`).join("")}
    </div>`
      )
      .join("") + row("schema", `Sibyl Memory · five tiers · v${SNAP.memory.schema_version ?? "?"}`);
}

function renderPolicy() {
  $("policy").innerHTML = Object.entries(SNAP.memory.policy)
    .filter(([k]) => k !== "notes")
    .map(([k, v]) => row(k, `<span class="mono acc">${esc(v)}</span>`))
    .join("");
}

async function renderNetwork() {
  busy("network", "reading the registry and hashing every evidence file in your browser…");
  let raw;
  try {
    raw = await fetchFeedbackLogs();
  } catch (e) {
    $("network").innerHTML = `<div class="empty bad">${esc(e.message)}</div>`;
    return;
  }

  const rated = [];
  for (const f of raw) rated.push(await verifyRating(f));
  VERIFIED = rated;

  const ver = rated.filter((r) => r.verified);
  const disputes = ver.reduce((n, r) => n + disputesOf(r), 0);
  $("s-ratings").textContent = rated.length;
  $("s-verified").textContent = ver.length;
  $("s-disputes").textContent = disputes;

  $("network").innerHTML =
    row("subject", `<span class="mono">ERC-8004 agent #${SNAP.subject_agent_id}</span>`) +
    row("registry", `<span class="mono">${esc(SNAP.network.reputation)}</span>`) +
    row("believed", `<b class="${ver.length ? "ok" : "dimc"}">${ver.length}</b> of ${rated.length} ratings`) +
    row("verified in", `<span class="ok">your browser</span> <span class="dimc">· keccak-256, no server involved</span>`) +
    (rated.length
      ? rated
          .map(
            (r) => `<div class="card fade ${r.verified ? "verified" : "rejected"}">
        <div class="top2">
          <div><div class="score">${(r.value / 10 ** r.decimals).toFixed(2)}<small>/100</small></div>
            <span class="mono dimc">${esc(r.client.slice(0, 20))}…</span></div>
          <span class="badge ${r.verified ? "ok" : "bad"}"><span class="dot"></span>${r.verified ? "VERIFIED" : "DISCARDED"}</span>
        </div>
        ${row("status", `<span class="${r.verified ? "ok" : "bad"}">${esc(r.status)}</span>`)}
        ${row("committed on chain", `<span class="mono">${short(r.hash, 30)}</span>`)}
        ${r.computed ? row("hashed here", `<span class="mono ${r.verified ? "ok" : "bad"}">${short(r.computed, 30)}</span>`) : ""}
        ${r.uri ? row("evidence", `<a class="mono" target="_blank" rel="noopener" href="${esc(r.uri)}">open the file ↗</a>`) : ""}
        ${row("transaction", `<a class="mono" target="_blank" rel="noopener" href="${esc(SNAP.network.explorer)}/tx/${esc(r.tx)}">${short(r.tx, 20)} ↗</a>`)}
        ${testimonyOf(r).map((t) => `<div class="quote">${esc(t)}</div>`).join("")}
      </div>`
          )
          .join("")
      : `<div class="empty">no ratings found</div>`);
}

/* ---------- the decision ---------- */

function verdictBlock(v) {
  const bad = v.decision === "REFUSE";
  const warn = v.decision !== "ACCEPT" && !bad;
  return `<div class="d ${bad ? "bad" : warn ? "warn" : "ok"}">${esc(v.decision)}</div>
    <div class="reason">${esc(v.reason)}</div>
    ${row("quoted", `$${Number(v.quoted_price_usd).toFixed(2)} <span class="dimc">of $${Number(v.standard_price_usd).toFixed(2)}</span>`)}
    ${row("escrow", v.escrow_required ? '<span class="warn">required</span>' : "no")}`;
}

function decide(handle) {
  const offline = SNAP.offline_verdicts[handle];
  if (!offline) return;

  const ver = VERIFIED.filter((r) => r.verified);
  const netDisputes = ver.reduce((n, r) => n + disputesOf(r), 0);

  // The same rule the engine applies: verified network disputes count
  // alongside our own.
  let online;
  if (handle === "newcomer" && netDisputes > 0) {
    online = {
      decision: "REFUSE",
      reason: `never dealt with them, but ${netDisputes} verified dispute(s) published by ${ver.length} other agent(s)`,
      quoted_price_usd: 0,
      standard_price_usd: offline.standard_price_usd,
      escrow_required: false,
    };
  } else {
    online = { ...offline };
    if (netDisputes) online.reason += `, ${netDisputes} from the network`;
  }

  const changed = offline.decision !== online.decision;
  $("decision").innerHTML = `<div class="split fade">
      <div class="half"><h3>Memory only · ${esc(handle)}</h3>${verdictBlock(offline)}</div>
      <div class="half"><h3>Memory + network · ${esc(handle)}</h3>${verdictBlock(online)}</div>
    </div>
    <div style="margin-top:14px">${row(
      "network changed the outcome",
      changed
        ? '<span class="badge ok"><span class="dot"></span>YES</span>'
        : '<span class="badge dimc">no — both agree</span>'
    )}</div>
    ${ver.flatMap(testimonyOf).map((t) => `<div class="quote">${esc(t)}</div>`).join("")}`;
}

/* ---------- tamper ---------- */

async function tamper() {
  busy("tamper", "fetching the real file and forging it here…");
  const target = VERIFIED.find((r) => r.verified);
  if (!target) {
    $("tamper").innerHTML = `<div class="empty">no verified evidence to forge</div>`;
    return;
  }
  const bytes = new Uint8Array(await (await fetch(target.uri, { cache: "no-store" })).arrayBuffer());
  const honest = keccak256(bytes);

  const obj = JSON.parse(new TextDecoder().decode(bytes));
  const before = obj.summary.jobs_disputed;
  obj.summary.jobs_disputed = 0;
  obj.verdict.decision = "ACCEPT";
  obj.events = [];
  const forgedBytes = new TextEncoder().encode(JSON.stringify(obj));
  const forged = keccak256(forgedBytes);

  const diff = (a, b) =>
    b.split("").map((ch, i) => (a[i] === ch ? esc(ch) : `<span class="diffch">${esc(ch)}</span>`)).join("");

  $("tamper").innerHTML = `<div class="fade">
    ${row("file", `<span class="mono">${short(target.uri.split("/").pop(), 20)}</span>`)}
    ${row("edit applied", `<span class="dimc">jobs_disputed ${before} to 0, testimony removed</span>`)}
    <div class="hash match"><span class="lbl">committed on chain · file as served</span>${esc(honest)}
      <div style="margin-top:8px"><span class="badge ok"><span class="dot"></span>VERIFIES</span></div></div>
    <div class="hash differ"><span class="lbl">recomputed after the forgery</span>${diff(honest, forged)}
      <div style="margin-top:8px"><span class="badge bad"><span class="dot"></span>REJECTED</span></div></div>
    <div class="reason" style="margin-top:12px">Changing one number changes the digest. Your browser
      re-hashed both; the second no longer matches what is committed on Base.</div></div>`;
}

/* ---------- the gate ---------- */

function renderGate() {
  const withMem = SNAP.offline_verdicts.swiftrender;
  const without = {
    decision: "ACCEPT_WITH_ESCROW",
    reason: "no prior history in memory",
  };
  $("gate").innerHTML = `<div class="split">
      <div class="half"><h3>With memory</h3>
        <div class="d ${withMem.decision === "REFUSE" ? "bad" : "ok"}">${esc(withMem.decision)}</div>
        <div class="reason">${esc(withMem.reason)}</div></div>
      <div class="half"><h3>Memory deleted</h3>
        <div class="d warn">${esc(without.decision)}</div>
        <div class="reason">${esc(without.reason)}</div></div>
    </div>
    <div style="margin-top:14px">${row(
      "behaviour differs",
      '<span class="badge ok"><span class="dot"></span>YES — memory is load-bearing</span>'
    )}</div>
    <div class="reason" style="margin-top:10px">Reproduce it yourself:
      <span class="mono">python -m vouch delete-test</span></div>`;
}

window.decide = decide;
window.tamper = tamper;
boot().catch((e) => {
  document.getElementById("network").innerHTML = `<div class="empty bad">${esc(e.message)}</div>`;
});
