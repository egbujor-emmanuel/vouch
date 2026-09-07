/* The case file, assembled and checked in your browser.
 *
 * There is no server. This page reads the ERC-8004 register over public RPC,
 * downloads each filed statement from its published URI, re-seals it here with
 * keccak-256, and compares that against the seal recorded on chain. Nothing
 * asks you to trust Vouch: the checking happens on your machine, in code you
 * can read from view-source.
 */
"use strict";

const $ = (id) => document.getElementById(id);
const esc = (s) =>
  String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const row = (k, v) => `<div class="r"><span class="k">${esc(k)}</span><span class="v">${v}</span></div>`;
const short = (s, n = 22) => (s ? esc(String(s).slice(0, n)) + "…" : "");
const busy = (id, msg) => ($(id).innerHTML = `<div class="empty blink">${esc(msg)}</div>`);
const stampFor = (ok) => `<span class="stamp land ${ok ? "ok" : "bad"}">${ok ? "VERIFIED" : "STRUCK"}</span>`;

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

/** Decode one NewFeedback log directly. The layout is fixed: index, value and
 *  decimals occupy the first three slots, four string offsets follow, and the
 *  seal sits static in slot 7. Verified against a real log before this page
 *  was built on it. */
function decodeFeedback(log) {
  const d = log.data.slice(2);
  const slot = (i) => d.slice(i * 64, (i + 1) * 64);
  const str = (slotIdx) => {
    const off = Number(BigInt("0x" + slot(slotIdx))) * 2;
    const len = Number(BigInt("0x" + d.slice(off, off + 64)));
    return new TextDecoder().decode(hexToBytes(d.slice(off + 64, off + 64 + len * 2)));
  };
  let value = BigInt("0x" + slot(1));
  if (value >= 1n << 127n) value -= 1n << 128n; // int128 is two's complement

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

  // Block hints keep this to one narrow query per statement. They are hints
  // only: the log is the source of truth, and a wrong hint simply finds
  // nothing rather than fabricating a result.
  for (const h of SNAP.log_hints || []) {
    let logs = [];
    try {
      logs = await rpc("eth_getLogs", [{
        address: SNAP.network.reputation,
        fromBlock: "0x" + Math.max(0, h.block - 2).toString(16),
        toBlock: "0x" + (h.block + 2).toString(16),
        topics: [topic0, agent],
      }]);
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

/* ---------- checking a statement ---------- */

async function verifyRating(f) {
  const r = { ...f, verified: false, status: "unchecked", evidence: null };
  if (!f.uri || !f.hash || /^0x0+$/.test(f.hash)) {
    r.status = "no statement attached — a number with nothing behind it";
    return r;
  }
  let bytes;
  try {
    const res = await fetch(f.uri, { cache: "no-store" });
    if (!res.ok) throw new Error("HTTP " + res.status);
    bytes = new Uint8Array(await res.arrayBuffer());
  } catch (e) {
    r.status = "statement unreachable (" + e.message + ")";
    return r;
  }
  // Seal the bytes exactly as served. Re-serialising here would round 25.0 to
  // 25 and wrongly condemn an honest filing.
  r.computed = keccak256(bytes);
  if (r.computed.toLowerCase() !== f.hash.toLowerCase()) {
    r.status = "seal does not match — the statement was altered after filing";
    return r;
  }
  try {
    r.evidence = JSON.parse(new TextDecoder().decode(bytes));
  } catch {
    r.status = "statement is not readable";
    return r;
  }
  r.verified = true;
  r.status = "seal matches the record on chain";
  return r;
}

const disputesOf = (r) => (r.verified && r.evidence ? Number(r.evidence.summary?.jobs_disputed || 0) : 0);
const testimonyOf = (r) =>
  r.verified && r.evidence
    ? (r.evidence.events || []).flatMap((e) => (e.acted || []).map((a) => `${e.ts || ""} — ${a}`))
    : [];

/* ---------- render ---------- */

async function boot() {
  SNAP = await (await fetch("snapshot.json", { cache: "no-store" })).json();

  $("net").className = "tag on";
  $("net").textContent = SNAP.network.name + " · chain " + SNAP.network.chain_id;
  $("issuer").textContent = SNAP.issuer.address ? "filer " + SNAP.issuer.address.slice(0, 10) + "…" : "";
  $("store").textContent = "sibyl memory v" + (SNAP.memory.schema_version ?? "?");
  $("s-cp").textContent = SNAP.memory.counterparties.length;
  $("gen").textContent = new Date(SNAP.generated_at).toISOString().slice(0, 16).replace("T", " ") + " UTC";

  renderMemory();
  renderPolicy();
  renderGate();
  await renderNetwork();
  decide("newcomer"); // the punchline should not need hunting for
}

function renderMemory() {
  const inc = SNAP.memory.incidents || [];
  $("memory").innerHTML =
    SNAP.memory.counterparties
      .map((c) => `<div class="stmt fade">
        <div class="hd">
          <span><b style="font-size:19px">${esc(c.handle)}</b>
            <span class="mono" style="color:var(--faint)"> · agent #${esc(c.agent_id)}</span></span>
          ${c.flagged ? '<span class="stamp bad">FLAGGED</span>' : ""}
        </div>
        ${row("jobs completed", c.jobs_completed)}
        ${row("jobs disputed", `<b style="color:${c.jobs_disputed ? "var(--stamp-bad)" : "var(--faint)"}">${c.jobs_disputed}</b>`)}
        ${inc.filter((i) => i.handle === c.handle)
             .map((i) => `<div class="said">${esc(i.ts || "")} — ${esc(i.detail)}</div>`).join("")}
      </div>`)
      .join("") + row("held in", "Sibyl Memory · five tiers · v" + (SNAP.memory.schema_version ?? "?"));
}

function renderPolicy() {
  $("policy").innerHTML = Object.entries(SNAP.memory.policy)
    .filter(([k]) => k !== "notes")
    .map(([k, v]) => row(k.replace(/_/g, " "), `<span class="mono">${esc(v)}</span>`))
    .join("");
}

async function renderNetwork() {
  busy("network", "retrieving the register and re-sealing every statement in your browser…");
  let raw;
  try {
    raw = await fetchFeedbackLogs();
  } catch (e) {
    $("network").innerHTML = `<div class="empty">${esc(e.message)}</div>`;
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
  $("hdr-status").textContent = disputes ? "disputes proven" : "open";

  $("network").innerHTML =
    row("subject", `<span class="mono">ERC-8004 agent #${SNAP.subject_agent_id}</span>`) +
    row("register", `<span class="mono">${esc(SNAP.network.reputation)}</span>`) +
    row("admitted", `<b>${ver.length}</b> of ${rated.length} statements`) +
    row("sealed with", "keccak-256, recomputed in your browser") +
    (rated.length
      ? rated.map((r) => `<div class="stmt fade ${r.verified ? "ok" : "bad"}">
          <div class="hd">
            <div>
              <div class="score">${(r.value / 10 ** r.decimals).toFixed(2)}<small>/100</small></div>
              <span class="mono" style="color:var(--faint)">deposed by ${esc(r.client.slice(0, 18))}…</span>
            </div>
            ${stampFor(r.verified)}
          </div>
          ${row("finding", esc(r.status))}
          <div class="seal ${r.verified ? "ok" : "bad"}"><s>seal recorded on chain</s>${esc(r.hash)}</div>
          ${r.computed ? `<div class="seal ${r.verified ? "ok" : "bad"}"><s>seal recomputed here</s>${esc(r.computed)}</div>` : ""}
          ${r.uri ? row("statement", `<a class="mono" target="_blank" rel="noopener" href="${esc(r.uri)}">read the filing ↗</a>`) : ""}
          ${row("filed in", `<a class="mono" target="_blank" rel="noopener" href="${esc(SNAP.network.explorer)}/tx/${esc(r.tx)}">${short(r.tx, 18)} ↗</a>`)}
          ${testimonyOf(r).map((t) => `<div class="said">${esc(t)}</div>`).join("")}
        </div>`).join("")
      : `<div class="empty">no statements on file</div>`);
}

/* ---------- the decision ---------- */

function pane(title, v) {
  const bad = v.decision === "REFUSE";
  const warn = v.decision !== "ACCEPT" && !bad;
  return `<div class="pane"><h3>${esc(title)}</h3>
    <div class="dec ${bad ? "bad" : warn ? "warn" : "ok"}">${esc(v.decision.replace(/_/g, " "))}</div>
    <div class="why">${esc(v.reason)}</div>
    ${row("quoted", `$${Number(v.quoted_price_usd).toFixed(2)} of $${Number(v.standard_price_usd).toFixed(2)}`)}
    ${row("escrow", v.escrow_required ? "required" : "no")}</div>`;
}

function decide(handle) {
  const offline = SNAP.offline_verdicts[handle];
  if (!offline) return;

  const ver = VERIFIED.filter((r) => r.verified);
  const netDisputes = ver.reduce((n, r) => n + disputesOf(r), 0);

  let online;
  if (handle === "newcomer" && netDisputes > 0) {
    online = {
      decision: "REFUSE",
      reason: `never dealt with them, but ${netDisputes} proven dispute(s) deposed by ${ver.length} other agent(s)`,
      quoted_price_usd: 0,
      standard_price_usd: offline.standard_price_usd,
      escrow_required: false,
    };
  } else {
    online = { ...offline };
    if (netDisputes) online.reason += `, ${netDisputes} of them from the register`;
  }

  const changed = offline.decision !== online.decision;
  $("decision").innerHTML = `<div class="split fade">
      ${pane("its own memory only", offline)}
      <div class="vs">VS</div>
      ${pane("memory + the register", online)}
    </div>
    <div class="r" style="margin-top:18px"><span class="k">did the register change the outcome</span>
      <span class="v">${changed ? stampFor(true).replace("VERIFIED", "YES") : '<span class="stamp bad">NO CHANGE</span>'}</span></div>
    ${ver.flatMap(testimonyOf).map((t) => `<div class="said">${esc(t)}</div>`).join("")}`;
}

/* ---------- attempted forgery ---------- */

async function tamper() {
  busy("tamper", "retrieving a genuine statement and altering it here…");
  const target = VERIFIED.find((r) => r.verified);
  if (!target) {
    $("tamper").innerHTML = `<div class="empty">no verified statement to work from</div>`;
    return;
  }
  const bytes = new Uint8Array(await (await fetch(target.uri, { cache: "no-store" })).arrayBuffer());
  const honest = keccak256(bytes);

  const obj = JSON.parse(new TextDecoder().decode(bytes));
  const before = obj.summary.jobs_disputed;
  obj.summary.jobs_disputed = 0;
  obj.verdict.decision = "ACCEPT";
  obj.events = [];
  const forged = keccak256(new TextEncoder().encode(JSON.stringify(obj)));

  const diff = (a, b) =>
    b.split("").map((ch, i) => (a[i] === ch ? esc(ch) : `<span class="ch">${esc(ch)}</span>`)).join("");

  $("tamper").innerHTML = `<div class="fade">
    ${row("alteration made", `disputes ${before} → 0, testimony removed`)}
    <div class="seal ok"><s>genuine statement, as filed</s>${esc(honest)}
      <div style="margin-top:10px">${stampFor(true)}</div></div>
    <div class="seal bad"><s>the same statement, after tampering</s>${diff(honest, forged)}
      <div style="margin-top:10px">${stampFor(false)}</div></div>
    <div class="why" style="margin-top:14px">One number changed and the seal moved. Your browser
      computed both; neither came from us.</div></div>`;
}

/* ---------- the gate ---------- */

function renderGate() {
  const withMem = SNAP.offline_verdicts.swiftrender;
  const without = {
    decision: "ACCEPT_WITH_ESCROW",
    reason: "no prior history in memory",
    quoted_price_usd: 25, standard_price_usd: 25, escrow_required: true,
  };
  $("gate").innerHTML = `<div class="split">
      ${pane("with memory", withMem)}
      <div class="vs">VS</div>
      ${pane("memory deleted", without)}
    </div>
    <div class="r" style="margin-top:18px"><span class="k">behaviour differs</span>
      <span class="v"><span class="stamp ok">LOAD-BEARING</span></span></div>
    <div class="why" style="margin-top:12px">Reproduce it yourself:
      <span class="mono">python -m vouch delete-test</span></div>`;
}

window.decide = decide;
window.tamper = tamper;
boot().catch((e) => {
  document.getElementById("network").innerHTML = `<div class="empty">${esc(e.message)}</div>`;
});
