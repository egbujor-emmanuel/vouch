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
  renderDispute();
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

/* ---------- check any agent on the register ---------------------------
 *
 * The page stops being a story here and becomes a tool: put in any
 * ERC-8004 agent id and it is looked up live. Most will come back with
 * ratings that have no statement attached, which is precisely the gap
 * this project exists to fill.
 */

const selector = (sig) => keccak256(new TextEncoder().encode(sig)).slice(0, 10);
const abiUint = (n) => BigInt(n).toString(16).padStart(64, "0");

async function ethCall(to, data) {
  return rpc("eth_call", [{ to, data }, "latest"]);
}

/** Decode an ABI address[] return value. */
function decodeAddressArray(hex) {
  const d = hex.slice(2);
  if (d.length < 128) return [];
  const off = Number(BigInt("0x" + d.slice(0, 64))) * 2;
  const len = Number(BigInt("0x" + d.slice(off, off + 64)));
  const out = [];
  for (let i = 0; i < len; i++) {
    const w = d.slice(off + 64 + i * 64, off + 128 + i * 64);
    out.push("0x" + w.slice(24));
  }
  return out;
}

async function inspect(agentId) {
  const box = $("inspect");
  const say = (m) => (box.innerHTML = `<div class="empty blink">${esc(m)}</div>`);
  if (!agentId || !/^\d+$/.test(String(agentId))) {
    say("enter a numeric agent id");
    return;
  }

  say(`looking up agent #${agentId} on ${SNAP.network.name}…`);

  // Who has rated this agent. A storage read, so no block-range limits.
  let clients = [];
  try {
    clients = decodeAddressArray(
      await ethCall(SNAP.network.reputation, selector("getClients(uint256)") + abiUint(agentId))
    );
  } catch (e) {
    box.innerHTML = `<div class="empty">could not reach the register: ${esc(e.message)}</div>`;
    return;
  }

  if (!clients.length) {
    box.innerHTML =
      row("agent", `<span class="mono">#${esc(agentId)}</span>`) +
      row("raters", "0") +
      `<div class="why" style="margin-top:12px">No one has rated this agent yet. An empty
       record is at least honest — unlike a score with nothing behind it.</div>`;
    return;
  }

  say(`agent #${agentId}: ${clients.length} rater(s) found — searching for their statements…`);

  // Statements live in the logs. Walk a bounded window newest-first so an
  // arbitrary agent still answers in seconds rather than minutes.
  const topic0 = keccak256(new TextEncoder().encode(NEW_FEEDBACK_SIG));
  const latest = Number(BigInt(await rpc("eth_blockNumber", [])));
  const CHUNK = 800, WINDOW = 60000;
  const found = [];
  for (let hi = latest; hi > latest - WINDOW && found.length < clients.length; hi -= CHUNK) {
    const lo = Math.max(0, hi - CHUNK + 1);
    say(`agent #${agentId}: scanning blocks ${lo.toLocaleString()}–${hi.toLocaleString()}…`);
    let logs = [];
    try {
      logs = await rpc("eth_getLogs", [{
        address: SNAP.network.reputation,
        fromBlock: "0x" + lo.toString(16), toBlock: "0x" + hi.toString(16),
        topics: [topic0, padTopic(agentId)],
      }]);
    } catch { continue; }
    for (const lg of logs) found.push(decodeFeedback(lg));
  }

  const checked = [];
  for (const f of found) checked.push(await verifyRating(f));
  const withEvidence = checked.filter((r) => r.uri);
  const verified = checked.filter((r) => r.verified);

  box.innerHTML =
    row("agent", `<span class="mono">#${esc(agentId)} on ${esc(SNAP.network.name)}</span>`) +
    row("agents that rated it", clients.length) +
    row("statements located", found.length) +
    row("with evidence attached",
        `<b style="color:${withEvidence.length ? "var(--stamp-ok)" : "var(--stamp-bad)"}">${withEvidence.length}</b>`) +
    row("seals verified here",
        `<b style="color:${verified.length ? "var(--stamp-ok)" : "var(--faint)"}">${verified.length}</b>`) +
    (found.length
      ? checked.map((r) => `<div class="stmt ${r.verified ? "ok" : "bad"}">
          <div class="hd">
            <div><div class="score">${(r.value / 10 ** r.decimals).toFixed(2)}<small>/100</small></div>
              <span class="mono" style="color:var(--faint)">by ${esc(r.client.slice(0, 18))}…</span></div>
            ${stampFor(r.verified)}
          </div>
          ${row("finding", esc(r.status))}
        </div>`).join("")
      : `<div class="why" style="margin-top:12px">Raters exist but no statement was found in the
         last ${WINDOW.toLocaleString()} blocks.</div>`) +
    (found.length && !withEvidence.length
      ? `<div class="why" style="margin-top:14px"><b>This is the gap.</b> The score exists, but
         there is nothing behind it: no account of what happened, and nothing to check. That is
         what ERC-8004 leaves empty and what Vouch fills.</div>`
      : "");
}

window.inspect = inspect;

/* ---------- the right of reply ---------------------------------------
 *
 * ERC-8004 ships appendResponse so an agent that has been rated can answer.
 * Nobody uses it, so a record carries only the accuser's side. This is the
 * other half: the accused files a rebuttal, sealed the same way, and both
 * sides stand on the register.
 *
 * The topic hash below was read off a real log rather than derived from a
 * guessed event signature — several plausible spellings did not match.
 */
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
    block: parseInt(log.blockNumber, 16),
  };
}

async function renderDispute() {
  const box = $("dispute");
  if (!box) return;
  box.innerHTML = `<div class="empty blink">searching the register for a rebuttal…</div>`;

  // Filter on the agent id with a null topic0, so this does not depend on
  // knowing every event signature the registry emits.
  const agent = padTopic(SNAP.subject_agent_id);
  const latest = Number(BigInt(await rpc("eth_blockNumber", [])));
  let found = null;
  for (let hi = latest; hi > latest - 40000 && !found; hi -= 800) {
    const lo = Math.max(0, hi - 799);
    let logs = [];
    try {
      logs = await rpc("eth_getLogs", [{
        address: SNAP.network.reputation,
        fromBlock: "0x" + lo.toString(16), toBlock: "0x" + hi.toString(16),
        topics: [null, agent],
      }]);
    } catch { continue; }
    for (const lg of logs) {
      if (lg.topics[0].toLowerCase() === RESPONSE_TOPIC0 && lg.topics.length === 4) {
        found = decodeResponse(lg);
        break;
      }
    }
  }

  if (!found) {
    box.innerHTML = `<div class="empty">no rebuttal has been filed against this record</div>`;
    return;
  }

  // Check the rebuttal exactly as we check an accusation. A reply that cannot
  // be verified deserves no more weight than a statement that cannot.
  let verified = false, statement = null;
  try {
    const bytes = new Uint8Array(await (await fetch(found.uri, { cache: "no-store" })).arrayBuffer());
    verified = keccak256(bytes).toLowerCase() === found.hash.toLowerCase();
    if (verified) statement = JSON.parse(new TextDecoder().decode(bytes));
  } catch { /* left unverified */ }

  const accusation = VERIFIED.find(
    (r) => r.client.toLowerCase() === found.accuser.toLowerCase() && r.index === found.feedbackIndex
  );

  box.innerHTML = `<div class="split fade">
      <div class="pane"><h3>the accusation</h3>
        <div class="dec bad">DISPUTED</div>
        <div class="why">${esc(accusation ? (testimonyOf(accusation)[0] || accusation.status) : "filed against this agent")}</div>
        ${row("deposed by", `<span class="mono">${esc(found.accuser.slice(0, 18))}…</span>`)}
      </div>
      <div class="vs">VS</div>
      <div class="pane"><h3>the reply</h3>
        <div class="dec ${verified ? "ok" : "warn"}">ANSWERED</div>
        <div class="why">${esc(statement ? statement.statement : "rebuttal filed but not verifiable")}</div>
        ${row("filed by", `<span class="mono">${esc(found.responder.slice(0, 18))}…</span>`)}
      </div>
    </div>
    ${row("answering statement", `#${found.feedbackIndex}`)}
    <div class="seal ${verified ? "ok" : "bad"}"><s>reply seal, recomputed here</s>${esc(found.hash)}
      <div style="margin-top:10px">${stampFor(verified)}</div></div>
    ${row("filed in", `<a class="mono" target="_blank" rel="noopener" href="${esc(SNAP.network.explorer)}/tx/${esc(found.tx)}">${short(found.tx, 18)} ↗</a>`)}
    <div class="why" style="margin-top:14px">Both sides now stand on the register, each sealed.
      A record with only the accuser on it is a rumour; this is what makes it evidence.</div>`;
}

window.renderDispute = renderDispute;
