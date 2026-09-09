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
const short = (s, n = 22) => (s ? esc(String(s).slice(0, n)) + "…" : "");
const busy = (id, msg) => ($(id).innerHTML = `<div class="empty blink">${esc(msg)}</div>`);

let SNAP = null;
let RPC_OK = null;   // the endpoint that last answered
let VERIFIED = [];

/* ---------- chain ---------- */

const NEW_FEEDBACK_SIG =
  "NewFeedback(uint256,address,uint64,int128,uint8,string,string,string,string,string,bytes32)";

/** Try each endpoint in turn.
 *
 * Public RPCs throttle, and a single rate-limited request would render an
 * agent with two filings as having none — indistinguishable from an agent
 * that never had any, which is the precise failure this page exists to
 * expose. Anyone reading gets one look, so one flaky response must not
 * decide what they see. */
async function rpc(method, params) {
  const all = SNAP.network.rpcs?.length ? SNAP.network.rpcs : [SNAP.network.rpc];
  // Once an endpoint answers, keep using it. Without this every later call
  // pays the full cost of the dead ones again, and a page doing dozens of
  // reads crawls instead of loading.
  const endpoints = RPC_OK ? [RPC_OK, ...all.filter((u) => u !== RPC_OK)] : all;
  let lastError = null;
  for (const url of endpoints) {
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }),
      });
      if (!res.ok) throw new Error("HTTP " + res.status);
      const j = await res.json();
      if (j.error) throw new Error(j.error.message || "rpc error");
      RPC_OK = url;
      return j.result;
    } catch (e) {
      lastError = e;
    }
  }
  throw lastError ?? new Error("no rpc endpoint answered");
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
const testimonyOf = (r) => {
  if (!r.verified) return [];
  if (r._testimony?.length) return r._testimony;      // snapshot-shaped
  return (r.evidence?.events || []).flatMap((e) => (e.acted || []).map((a) => `${e.ts || ""} — ${a}`));
};

/* ---------- render ---------- */

const pill = (ok, okText = "VERIFIED", badText = "DISCARDED") =>
  `<span class="st ${ok ? "ok" : "bad"}"><span class="d"></span>${ok ? okText : badText}</span>`;
const kv = (pairs) =>
  `<dl class="kv">${pairs.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${v}</dd>`).join("")}</dl>`;
const txLink = (tx) =>
  `<a class="mono" target="_blank" rel="noopener" href="${esc(SNAP.network.explorer)}/tx/${esc(tx)}">${short(tx, 16)}</a>`;

async function boot() {
  SNAP = await (await fetch("snapshot.json", { cache: "no-store" })).json();

  $("net").className = "pill live";
  $("net").innerHTML = `<span class="d"></span>${esc(SNAP.network.name)} · ${SNAP.network.chain_id}`;
  $("issuer").textContent = SNAP.issuer.address ? SNAP.issuer.address.slice(0, 10) + "…" : "";
  $("store").textContent = "sibyl memory v" + (SNAP.memory.schema_version ?? "?");
  $("s-cp").textContent = SNAP.memory.counterparties.length;
  $("gen").textContent = new Date(SNAP.generated_at).toISOString().slice(0, 16).replace("T", " ") + " UTC";

  renderSwitch();   // instant: answers from the snapshot, no chain call
  renderMemory();
  renderPolicy();
  renderGate();
  await renderNetwork();
  renderSwitch();   // again, now the verified filings are known
  decide("newcomer");
  renderDispute();
  inspect(String(SNAP.subject_agent_id));
}

function renderMemory() {
  const inc = SNAP.memory.incidents || [];
  const rows = SNAP.memory.counterparties.map((c) => `<tr>
      <td><b>${esc(c.handle)}</b>${c.flagged ? ' <span class="st bad"><span class="d"></span>FLAGGED</span>' : ""}
        ${inc.filter((i) => i.handle === c.handle).map((i) => `<div class="quote">${esc(i.detail)}</div>`).join("")}</td>
      <td class="mono">#${esc(c.agent_id)}</td>
      <td class="num">${c.jobs_completed}</td>
      <td class="num"><b style="color:${c.jobs_disputed ? "var(--bad)" : "var(--muted)"}">${c.jobs_disputed}</b></td>
    </tr>`).join("");

  $("memory").innerHTML = `<div class="tblwrap"><table>
      <thead><tr><th>Counterparty</th><th>Agent</th><th class="num">Completed</th><th class="num">Disputed</th></tr></thead>
      <tbody>${rows}</tbody></table></div>
    <div class="note">One row per counterparty, with duplicates made impossible by the schema —
      <b>UNIQUE (tenant_id, category, name)</b> is enforced by the database, not by convention.</div>`;
}

function renderPolicy() {
  const rows = Object.entries(SNAP.memory.policy)
    .filter(([k]) => k !== "notes")
    .map(([k, v]) => `<tr><td>${esc(k.replace(/_/g, " "))}</td><td class="mono">${esc(v)}</td></tr>`)
    .join("");
  $("policy").innerHTML = `<div class="tblwrap"><table>
    <thead><tr><th>Rule</th><th>Value</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}

/** Paint the filings table.
 *
 * `source` says who checked: "snapshot" means the seals were verified when the
 * page was published, "browser" means this machine just re-fetched every file
 * and recomputed every hash. The distinction is shown rather than smoothed
 * over, because a page arguing that evidence should be checkable cannot quietly
 * ask to be taken at its word.
 */
function paintNetwork(rated, source) {
  const ver = rated.filter((r) => r.verified);
  const disputes = ver.reduce((n, r) => n + disputesOf(r), 0);
  $("s-ratings").textContent = rated.length;
  $("s-verified").textContent = ver.length;
  $("s-disputes").textContent = disputes;

  if (!rated.length) {
    $("network").innerHTML = `<div class="empty">no filings found</div>`;
    return;
  }

  const checkedBy =
    source === "browser"
      ? '<span class="st ok"><span class="d"></span>VERIFIED IN YOUR BROWSER</span>'
      : '<span class="st mut">from snapshot · re-checking here now…</span>';

  const rows = rated.map((r) => `<tr>
      <td class="mono">${esc(r.client.slice(0, 14))}…</td>
      <td class="num"><b>${(r.value / 10 ** r.decimals).toFixed(2)}</b><span style="color:var(--muted)">/100</span></td>
      <td>${pill(r.verified)}<div style="color:var(--muted);font-size:12px;margin-top:5px">${esc(r.status)}</div></td>
      <td>${r.uri ? `<a class="mono" target="_blank" rel="noopener" href="${esc(r.uri)}">evidence</a>` : '<span style="color:var(--muted)">none</span>'}</td>
      <td>${r.tx ? txLink(r.tx) : "—"}</td>
    </tr>`).join("");

  const seals = rated.map((r) => `
    <div class="hashline ${r.verified ? "ok" : "bad"}"><span class="lbl">on chain</span><span class="hv">${esc(r.hash)}</span></div>
    ${r.computed ? `<div class="hashline ${r.verified ? "ok" : "bad"}"><span class="lbl">hashed here</span><span class="hv">${esc(r.computed)}</span></div>` : ""}`).join("");

  $("network").innerHTML =
    kv([
      ["Subject", `<span class="mono">ERC-8004 agent #${SNAP.subject_agent_id}</span>`],
      ["Reputation registry", `<span class="mono">${esc(SNAP.network.reputation)}</span>`],
      ["Admitted", `<b>${ver.length}</b> of ${rated.length} filings`],
      ["Checked by", checkedBy],
    ]) +
    `<div class="tblwrap" style="margin-top:14px"><table>
       <thead><tr><th>Issuer</th><th class="num">Score</th><th>Seal check</th><th>Statement</th><th>Transaction</th></tr></thead>
       <tbody>${rows}</tbody></table></div>` +
    `<div style="margin-top:16px">${seals}</div>` +
    (ver.flatMap(testimonyOf).length
      ? `<div style="margin-top:12px"><div style="font:700 10.5px/1 var(--sans);letter-spacing:.09em;text-transform:uppercase;color:var(--muted);margin-bottom:8px">Testimony recovered from verified filings</div>
         ${ver.flatMap(testimonyOf).map((t) => `<div class="quote">${esc(t)}</div>`).join("")}</div>`
      : "");
}

/** Snapshot filings reshaped to look like a freshly verified one. */
function fromSnapshot() {
  return (SNAP.filings || []).map((f) => ({
    client: f.issuer,
    index: f.index,
    value: Math.round(f.score * 100),
    decimals: 2,
    uri: f.uri,
    hash: f.hash,
    tx: f.tx,
    verified: f.verified,
    status: f.status,
    computed: null,
    evidence: f.verified ? { summary: { jobs_disputed: f.disputes }, events: [] } : null,
    _testimony: f.testimony || [],
  }))
}

async function renderNetwork() {
  // Paint the known-good answer first so nobody waits on a spinner.
  const pre = fromSnapshot();
  if (pre.length) {
    VERIFIED = pre;
    paintNetwork(pre, "snapshot");
  } else {
    busy("network", "reading the registry…");
  }

  // Then do the real thing: fetch every file and recompute every seal here.
  let raw;
  try {
    raw = await fetchFeedbackLogs();
  } catch (e) {
    if (!pre.length) $("network").innerHTML = `<div class="empty">${esc(e.message)}</div>`;
    return;
  }

  const rated = [];
  for (const f of raw) rated.push(await verifyRating(f));
  if (!rated.length) return; // keep the snapshot rather than blanking the table
  VERIFIED = rated;
  paintNetwork(rated, "browser");
}

/* ---------- decision ---------- */

function panel(title, v) {
  const bad = v.decision === "REFUSE";
  const warn = v.decision !== "ACCEPT" && !bad;
  return `<div><h3>${esc(title)}</h3>
    <div class="dec ${bad ? "bad" : warn ? "warn" : "ok"}">${esc(v.decision.replace(/_/g, " "))}</div>
    <div class="why">${esc(v.reason)}</div>
    ${kv([
      ["Quoted", `<span class="mono">$${Number(v.quoted_price_usd).toFixed(2)}</span> <span style="color:var(--muted)">of $${Number(v.standard_price_usd).toFixed(2)}</span>`],
      ["Escrow", v.escrow_required ? '<span class="st warn"><span class="d"></span>REQUIRED</span>' : '<span class="st mut">not required</span>'],
    ])}</div>`;
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
      reason: `never dealt with them, but ${netDisputes} proven dispute(s) filed by ${ver.length} other agent(s)`,
      quoted_price_usd: 0,
      standard_price_usd: offline.standard_price_usd,
      escrow_required: false,
    };
  } else {
    online = { ...offline };
    if (netDisputes) online.reason += `, ${netDisputes} of them from the registry`;
  }

  const changed = offline.decision !== online.decision;
  $("decision").innerHTML = `<div class="cmp">
      ${panel("Its own memory only", offline)}
      ${panel("Memory + the registry", online)}
    </div>
    <div class="note" style="margin-top:14px">
      ${changed
        ? '<span class="st ok"><span class="d"></span>OUTCOME CHANGED</span> &nbsp;Reading other agents\' filings turned this from a job it would have taken into one it refuses.'
        : '<span class="st mut">no change</span> &nbsp;Its own memory already accounted for this counterparty.'}
    </div>`;
}

/* ---------- tamper ---------- */

async function tamper() {
  busy("tamper", "downloading a genuine statement and altering it here…");
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

  $("tamper").innerHTML =
    kv([["Alteration", `disputes ${before} → 0, testimony removed`]]) +
    `<div class="hashline ok"><span class="lbl">genuine file</span><span class="hv">${esc(honest)}</span></div>
     <div style="margin:8px 0">${pill(true, "SEAL MATCHES")}</div>
     <div class="hashline bad"><span class="lbl">after tampering</span><span class="hv">${diff(honest, forged)}</span></div>
     <div style="margin:8px 0">${pill(false, "", "SEAL BROKEN")}</div>
     <div class="explain" style="margin-top:12px">One field changed and the seal moved. Your browser
       computed both hashes; neither came from us.</div>`;
}

/* ---------- the gate ---------- */

function renderGate() {
  const withMem = SNAP.offline_verdicts.swiftrender;
  const without = {
    decision: "ACCEPT_WITH_ESCROW",
    reason: "no prior history in memory",
    quoted_price_usd: 25, standard_price_usd: 25, escrow_required: true,
  };
  $("gate").innerHTML = `<div class="cmp">
      ${panel("With memory", withMem)}
      ${panel("Memory deleted", without)}
    </div>
    <div class="note" style="margin-top:14px">
      <span class="st ok"><span class="d"></span>LOAD-BEARING</span>
      &nbsp;Without memory it cannot tell a counterparty that burned it from one it has never met.
      Reproduce it with <span class="mono">python -m vouch delete-test</span>.</div>`;
}

/* ---------- the right of reply ---------- */

const RESPONSE_TOPIC0 = "0xb1c6be0b5b8aef6539e2fac0fd131a2faa7b49edf8e505b5eb0ad487d56051d4";

function decodeResponse(log) {
  const d = log.data.slice(2);
  const slot = (i) => d.slice(i * 64, (i + 1) * 64);
  const off = Number(BigInt("0x" + slot(1))) * 2;
  const len = Number(BigInt("0x" + d.slice(off, off + 64)));
  return {
    agentId: Number(BigInt(log.topics[1])),
    accuser: "0x" + log.topics[2].slice(26),
    responder: "0x" + log.topics[3].slice(26),
    feedbackIndex: Number(BigInt("0x" + slot(0))),
    uri: new TextDecoder().decode(hexToBytes(d.slice(off + 64, off + 64 + len * 2))),
    hash: "0x" + slot(2),
    tx: log.transactionHash,
  };
}

async function renderDispute() {
  const box = $("dispute");
  if (!box) return;
  box.innerHTML = `<div class="empty blink">searching the registry for a reply…</div>`;

  // Filtered on the agent id with a null topic0, so this does not depend on
  // knowing every event signature the registry emits.
  const agent = padTopic(SNAP.subject_agent_id);
  let found = null;

  // The reply's block is recorded, so this is one query rather than a walk back
  // through forty thousand blocks. That walk was fifty sequential requests and
  // the single largest reason this page felt slow to load.
  for (const h of SNAP.response_hints || []) {
    try {
      const logs = await rpc("eth_getLogs", [{
        address: SNAP.network.reputation,
        fromBlock: "0x" + Math.max(0, h.block - 2).toString(16),
        toBlock: "0x" + (h.block + 2).toString(16),
        topics: [null, agent],
      }]);
      for (const lg of logs) {
        if (lg.topics[0].toLowerCase() === RESPONSE_TOPIC0 && lg.topics.length === 4) {
          found = decodeResponse(lg);
          break;
        }
      }
    } catch { /* a stale hint finds nothing, which is the safe failure */ }
    if (found) break;
  }

  if (!found) {
    box.innerHTML = `<div class="empty">no reply found in the blocks searched</div>`;
    return;
  }

  let verified = false, statement = null;
  try {
    const bytes = new Uint8Array(await (await fetch(found.uri, { cache: "no-store" })).arrayBuffer());
    verified = keccak256(bytes).toLowerCase() === found.hash.toLowerCase();
    if (verified) statement = JSON.parse(new TextDecoder().decode(bytes));
  } catch { /* left unverified */ }

  const accusation = VERIFIED.find(
    (r) => r.client.toLowerCase() === found.accuser.toLowerCase() && r.index === found.feedbackIndex
  );

  box.innerHTML = `<div class="cmp">
      <div><h3>The accusation</h3>
        <div class="dec bad">DISPUTED</div>
        <div class="why">${esc(accusation ? (testimonyOf(accusation)[0] || accusation.status) : "filed against this agent")}</div>
        ${kv([["Filed by", `<span class="mono">${esc(found.accuser.slice(0, 16))}…</span>`]])}</div>
      <div><h3>The reply</h3>
        <div class="dec ${verified ? "ok" : "warn"}">ANSWERED</div>
        <div class="why">${esc(statement ? statement.statement : "reply filed but not verifiable")}</div>
        ${kv([["Filed by", `<span class="mono">${esc(found.responder.slice(0, 16))}…</span>`]])}</div>
    </div>
    <div style="margin-top:14px">
      <div class="hashline ${verified ? "ok" : "bad"}"><span class="lbl">reply seal</span><span class="hv">${esc(found.hash)}</span></div>
      ${kv([["Answering filing", `#${found.feedbackIndex}`], ["Transaction", txLink(found.tx)]])}
    </div>
    <div class="note" style="margin-top:12px">${pill(verified, "REPLY VERIFIED", "REPLY UNVERIFIED")}
      &nbsp;Both sides now stand on the registry, each sealed independently.</div>`;
}

/* ---------- look up any agent ---------- */

const selector = (sig) => keccak256(new TextEncoder().encode(sig)).slice(0, 10);
const abiUint = (n) => BigInt(n).toString(16).padStart(64, "0");
const ethCall = (to, data) => rpc("eth_call", [{ to, data }, "latest"]);

function decodeAddressArray(hex) {
  const d = hex.slice(2);
  if (d.length < 128) return [];
  const off = Number(BigInt("0x" + d.slice(0, 64))) * 2;
  const len = Number(BigInt("0x" + d.slice(off, off + 64)));
  const out = [];
  for (let i = 0; i < len; i++) out.push("0x" + d.slice(off + 64 + i * 64, off + 128 + i * 64).slice(24));
  return out;
}

// Two lookups can be in flight at once: the one the page runs on load, and one
// a visitor starts before that has finished. Whatever the order they land in,
// the visitor's answer is the one that must be on screen — so a boot query only
// writes while nobody has asked for anything, and between visitor lookups the
// newest wins.
let INSPECT_SEQ = 0;
let USER_SEQ = 0;

async function inspect(agentId, reveal = false) {
  const box = $("inspect");
  const seq = ++INSPECT_SEQ;
  const asked = reveal;
  if (asked) USER_SEQ++;
  const mine = () => seq === INSPECT_SEQ && (asked || USER_SEQ === 0);
  const say = (m) => {
    if (mine()) box.innerHTML = `<div class="empty blink">${esc(m)}</div>`;
  };
  // The panel this writes into is below the fold, so a click on Look up looked
  // like nothing had happened. Bring the answer to the reader when the reader
  // asked for it — never on the boot query, which would scroll the page out
  // from under someone who has just arrived.
  //
  // The offset is computed rather than left to scroll-margin: the header is
  // sticky, and scrollIntoView lands the panel under it.
  const bring = () => {
    if (!reveal) return;
    const panel = box.closest(".panel");
    const bar = document.querySelector(".top");
    if (!panel) return;
    const y = panel.getBoundingClientRect().top + window.scrollY
      - ((bar?.getBoundingClientRect().height || 0) + 16);
    window.scrollTo({ top: Math.max(0, y), behavior: "smooth" });
  };
  bring();
  if (!agentId || !/^\d+$/.test(String(agentId))) {
    if (mine()) box.innerHTML = `<div class="empty">enter a numeric agent id</div>`;
    return;
  }

  say(`looking up agent #${agentId}…`);
  let clients = [];
  try {
    clients = decodeAddressArray(
      await ethCall(SNAP.network.reputation, selector("getClients(uint256)") + abiUint(agentId))
    );
  } catch (e) {
    if (mine()) box.innerHTML = `<div class="empty">could not reach the registry: ${esc(e.message)}</div>`;
    return;
  }
  if (!mine()) return;

  if (!clients.length) {
    if (!mine()) return;
    box.innerHTML = kv([
      ["Agent", `<span class="mono">#${esc(agentId)} on ${esc(SNAP.network.name)}</span>`],
      ["Agents that rated it", "0"],
    ]) + `<div class="note">Nobody has rated this agent. An empty record is at least honest —
        unlike a score with nothing behind it.</div>`;
    return;
  }

  // Known agents resolve from the committed hints, which is one narrow query
  // each rather than a blind walk back through tens of thousands of blocks.
  // The earlier version scanned 60,000 blocks in 800-block steps — seventy-odd
  // sequential requests — and left this panel visibly stuck for a minute on the
  // very agent the rest of the page had already resolved.
  const found = [];
  const topic0 = keccak256(new TextEncoder().encode(NEW_FEEDBACK_SIG));
  const hinted = String(agentId) === String(SNAP.subject_agent_id) ? SNAP.log_hints || [] : [];

  if (hinted.length) {
    say(`agent #${agentId}: ${clients.length} rater(s) — reading their filings…`);
    for (const h of hinted) {
      try {
        const logs = await rpc("eth_getLogs", [{
          address: SNAP.network.reputation,
          fromBlock: "0x" + Math.max(0, h.block - 2).toString(16),
          toBlock: "0x" + (h.block + 2).toString(16),
          topics: [topic0, padTopic(agentId)],
        }]);
        for (const lg of logs) found.push(decodeFeedback(lg));
      } catch { /* a missing hint simply finds nothing */ }
    }
  }

  // An agent we hold no hint for still gets a search, but a bounded one: recent
  // history only, and the panel says so rather than implying it looked everywhere.
  if (!found.length) {
    const latest = Number(BigInt(await rpc("eth_blockNumber", [])));
    const WINDOW = 12000, CHUNK = 800;
    for (let hi = latest; hi > latest - WINDOW && found.length < clients.length; hi -= CHUNK) {
      const lo = Math.max(0, hi - CHUNK + 1);
      say(`agent #${agentId}: searching recent blocks ${lo.toLocaleString()}–${hi.toLocaleString()}…`);
      try {
        const logs = await rpc("eth_getLogs", [{
          address: SNAP.network.reputation,
          fromBlock: "0x" + lo.toString(16), toBlock: "0x" + hi.toString(16),
          topics: [topic0, padTopic(agentId)],
        }]);
        for (const lg of logs) found.push(decodeFeedback(lg));
      } catch { continue; }
    }
  }

  const checked = [];
  for (const f of found) checked.push(await verifyRating(f));
  const withEvidence = checked.filter((r) => r.uri);
  const verified = checked.filter((r) => r.verified);

  const rows = checked.map((r) => `<tr>
      <td class="mono">${esc(r.client.slice(0, 14))}…</td>
      <td class="num"><b>${(r.value / 10 ** r.decimals).toFixed(2)}</b><span style="color:var(--muted)">/100</span></td>
      <td>${r.uri ? '<span class="st ok"><span class="d"></span>ATTACHED</span>' : '<span class="st bad"><span class="d"></span>NONE</span>'}</td>
      <td>${pill(r.verified)}<div style="color:var(--muted);font-size:12px;margin-top:5px">${esc(r.status)}</div></td>
    </tr>`).join("");

  if (!mine()) return;
  box.innerHTML =
    kv([
      ["Agent", `<span class="mono">#${esc(agentId)} on ${esc(SNAP.network.name)}</span>`],
      ["Agents that rated it", clients.length],
      ["Filings located", found.length],
      ["With evidence attached", `<b style="color:${withEvidence.length ? "var(--ok)" : "var(--bad)"}">${withEvidence.length}</b> of ${found.length}`],
      ["Seals verified here", `<b style="color:${verified.length ? "var(--ok)" : "var(--muted)"}">${verified.length}</b>`],
    ]) +
    (found.length
      ? `<div class="tblwrap" style="margin-top:14px"><table>
          <thead><tr><th>Issuer</th><th class="num">Score</th><th>Evidence</th><th>Seal check</th></tr></thead>
          <tbody>${rows}</tbody></table></div>`
      : `<div class="note">Raters exist, but no filing turned up in the recent blocks searched.
          An older one needs its block noted in <span class="mono">filings.json</span>.</div>`) +
    // The point of the whole project is that a verified filing carries an
    // account, not just a number — so show the account here, where a judge
    // types an id, and not only in the panel further down.
    (verified.flatMap(testimonyOf).length
      ? `<div style="margin-top:14px"><div style="font:700 10.5px/1 var(--sans);letter-spacing:.09em;
           text-transform:uppercase;color:var(--muted);margin-bottom:8px">Testimony recovered from the verified filings</div>
         ${verified.flatMap(testimonyOf).map((x) => `<div class="quote">${esc(x)}</div>`).join("")}</div>`
      : "") +
    (found.length && !withEvidence.length
      ? `<div class="note"><b>This is the gap.</b> The score exists, but there is nothing behind it:
         no account of what happened and nothing to check. That is what ERC-8004 leaves empty and
         what Vouch fills.</div>`
      : "");

  // The panels above are still resolving while this runs, and they grow as they
  // do, which walks this one back down the page. Anchor it again now that the
  // answer is on screen.
  bring();
}

window.decide = decide;
window.tamper = tamper;
window.inspect = inspect;
window.renderDispute = renderDispute;
boot().catch((e) => {
  document.getElementById("network").innerHTML = `<div class="empty">${esc(e.message)}</div>`;
});

/* ---------- the memory switch --------------------------------------------
 *
 * The hackathon's test is "delete the memory layer and see if it still works".
 * Reading that as a paragraph proves nothing; flipping it does. This answers
 * instantly from the snapshot rather than waiting on the chain, because a
 * control that takes thirty seconds to respond is not a control.
 */

let MEMORY_ON = true;

function verdictWithMemory() {
  // Own memory plus whatever the registry turned out to hold. VERIFIED is
  // populated by the network pass; before it lands we still answer, just
  // without the corroborating filings.
  const base = SNAP.offline_verdicts.newcomer;
  const ver = VERIFIED.filter((r) => r.verified);
  const net = ver.reduce((n, r) => n + disputesOf(r), 0);

  if (net > 0) {
    return {
      decision: "REFUSE",
      reason: `Never dealt with them — but ${net} proven dispute(s), filed by ${ver.length} independent agent(s) and verified in this browser.`,
      cites: ver.flatMap(testimonyOf),
    };
  }
  return {
    decision: base.decision,
    reason: base.reason + ". No filings verified yet — the registry read is still running.",
    cites: [],
  };
}

function verdictWithoutMemory() {
  return {
    decision: "ACCEPT_WITH_ESCROW",
    reason:
      "Nothing is known about anyone. With no memory there is no history to consult, nothing to hash, and nothing to publish — so every counterparty is quoted the same price, a fraudster and a saint alike.",
    cites: [],
  };
}

function renderSwitch() {
  const sw = $("memswitch");
  const box = $("bigverdict");
  if (!sw || !box) return;

  sw.classList.toggle("off", !MEMORY_ON);
  sw.setAttribute("aria-checked", String(MEMORY_ON));
  $("memlabel").textContent = MEMORY_ON ? "MEMORY ON" : "MEMORY OFF";

  const v = MEMORY_ON ? verdictWithMemory() : verdictWithoutMemory();
  const bad = v.decision === "REFUSE";
  const warn = v.decision !== "ACCEPT" && !bad;

  box.innerHTML = `
    <div class="big ${bad ? "bad" : warn ? "warn" : "ok"}">${esc(v.decision.replace(/_/g, " "))}</div>
    <div class="bigwhy">${esc(v.reason)}</div>
    ${v.cites.length ? `<div style="margin-top:14px">${v.cites.map((c) => `<div class="quote">${esc(c)}</div>`).join("")}</div>` : ""}
    <div class="note" style="margin-top:16px">
      ${MEMORY_ON
        ? 'Memory is doing the work. Switch it off and watch the same agent, on the same request, lose the ability to tell anyone apart.'
        : '<b>This is the gate.</b> The product did not get worse — it stopped existing. Nothing to score, nothing to seal, nothing to publish. Reproduce it with <span class="mono">python -m vouch delete-test</span>.'}
    </div>`;
}

function toggleMemory() {
  MEMORY_ON = !MEMORY_ON;
  renderSwitch();
}

window.toggleMemory = toggleMemory;
window.renderSwitch = renderSwitch;
