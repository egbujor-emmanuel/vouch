"""The dashboard markup.

Kept apart from the server so the page can be edited without touching request
handling. No framework, no build step, no CDN: everything a judge needs to run
this is already on their machine.
"""

PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Vouch — verifiable counterparty history for agents</title>
<style>
:root{
  --bg:#07090c; --bg2:#0b0f14; --panel:#0e1319; --panel2:#121922;
  --line:#1b2430; --line2:#26323f;
  --ink:#eaf0f7; --ink2:#a7b4c4; --dim:#6b7a8c;
  --ok:#35d99a; --bad:#ff5f6d; --warn:#ffb545; --accent:#6ea8ff;
  --mono:ui-monospace,"SF Mono","Cascadia Mono",Menlo,Consolas,monospace;
  --sans:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Inter,sans-serif;
  --r:14px;
}
*{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{background:var(--bg);color:var(--ink);font:15px/1.6 var(--sans);
  -webkit-font-smoothing:antialiased;
  background-image:radial-gradient(1200px 600px at 78% -10%,rgba(110,168,255,.10),transparent 60%),
                   radial-gradient(900px 500px at 8% 0%,rgba(53,217,154,.06),transparent 55%)}

/* ---------- shell ---------- */
.wrap{max-width:1320px;margin:0 auto;padding:0 28px}
header.top{position:sticky;top:0;z-index:20;backdrop-filter:blur(14px);
  background:rgba(7,9,12,.82);border-bottom:1px solid var(--line)}
.top .wrap{display:flex;align-items:center;gap:14px;height:62px}
.brand{font-size:17px;font-weight:680;letter-spacing:-.01em}
.brand i{color:var(--accent);font-style:normal}
.chip{font:11px/1 var(--mono);color:var(--ink2);border:1px solid var(--line2);
  padding:6px 10px;border-radius:99px;white-space:nowrap;display:inline-flex;
  align-items:center;gap:6px}
.dot{width:6px;height:6px;border-radius:99px;background:currentColor;flex:none}
.chip.live{color:var(--ok)} .chip.off{color:var(--warn)}
.spacer{margin-left:auto}

/* ---------- hero ---------- */
.hero{padding:74px 0 44px;border-bottom:1px solid var(--line)}
.kicker{font:12px/1 var(--mono);letter-spacing:.16em;text-transform:uppercase;
  color:var(--accent);margin-bottom:20px}
h1{font-size:clamp(30px,4.6vw,54px);line-height:1.06;letter-spacing:-.028em;
  font-weight:700;max-width:20ch}
h1 em{font-style:normal;color:var(--dim)}
.lede{margin-top:20px;max-width:60ch;color:var(--ink2);font-size:17px}
.stats{display:flex;gap:40px;margin-top:38px;flex-wrap:wrap}
.stat b{display:block;font:600 26px/1.15 var(--sans);letter-spacing:-.02em}
.stat span{font:11px/1 var(--mono);letter-spacing:.1em;text-transform:uppercase;
  color:var(--dim);margin-top:7px;display:block}

/* ---------- layout ---------- */
main{padding:36px 0 90px;display:grid;gap:20px;
  grid-template-columns:repeat(auto-fit,minmax(440px,1fr));align-items:start}
section{background:linear-gradient(180deg,var(--panel),var(--bg2));
  border:1px solid var(--line);border-radius:var(--r);padding:22px 24px;
  transition:border-color .25s}
section:hover{border-color:var(--line2)}
section.wide{grid-column:1/-1}
.h{display:flex;align-items:center;gap:10px;margin-bottom:6px}
.h h2{font-size:13px;letter-spacing:.13em;text-transform:uppercase;color:var(--ink2);font-weight:600}
.num{font:11px/1 var(--mono);color:var(--dim);border:1px solid var(--line);
  border-radius:5px;padding:4px 7px}
.lede2{color:var(--dim);font-size:13.5px;margin-bottom:18px;max-width:62ch}

/* ---------- primitives ---------- */
.row{display:flex;justify-content:space-between;align-items:baseline;gap:16px;
  padding:9px 0;border-bottom:1px solid var(--line);font-size:13.5px}
.row:last-child{border-bottom:0}
.k{color:var(--dim);flex:none}
.v{text-align:right;word-break:break-word}
.mono{font-family:var(--mono);font-size:12px}
.badge{display:inline-flex;align-items:center;gap:6px;font:11px/1 var(--mono);
  padding:5px 10px;border-radius:99px;border:1px solid currentColor;letter-spacing:.05em}
.ok{color:var(--ok)} .bad{color:var(--bad)} .warn{color:var(--warn)}
.dimc{color:var(--dim)} .acc{color:var(--accent)}
button{background:var(--panel2);color:var(--ink);border:1px solid var(--line2);
  border-radius:9px;padding:10px 16px;font:500 13.5px var(--sans);cursor:pointer;
  transition:all .18s;margin:0 8px 8px 0}
button:hover{border-color:var(--accent);color:#fff;transform:translateY(-1px)}
button:active{transform:none}
button.primary{background:linear-gradient(180deg,#1b2e4d,#16233a)}
button[disabled]{opacity:.5;cursor:wait;transform:none}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
.empty{color:var(--dim);font-size:13.5px;padding:16px 0;text-align:center}
.spin{display:inline-block;width:11px;height:11px;border:2px solid var(--line2);
  border-top-color:var(--accent);border-radius:99px;animation:sp .7s linear infinite;
  vertical-align:-1px;margin-right:8px}
@keyframes sp{to{transform:rotate(360deg)}}
.fade{animation:fd .32s ease both}
@keyframes fd{from{opacity:0;transform:translateY(5px)}to{opacity:1;transform:none}}

/* ---------- rating cards ---------- */
.card{border:1px solid var(--line);border-radius:11px;padding:15px 17px;margin:12px 0;
  background:var(--bg2);position:relative;overflow:hidden}
.card::before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--line2)}
.card.verified::before{background:var(--ok)}
.card.rejected::before{background:var(--bad)}
.card .top2{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:10px}
.score{font:700 30px/1 var(--sans);letter-spacing:-.03em}
.score small{font:400 13px/1 var(--sans);color:var(--dim);margin-left:3px}
.quote{border-left:2px solid var(--line2);padding:5px 0 5px 12px;margin:9px 0;
  color:var(--ink2);font-size:12.5px;font-family:var(--mono);line-height:1.55}

/* ---------- verdict ---------- */
.verdict{display:flex;align-items:baseline;gap:14px;margin:6px 0 4px;flex-wrap:wrap}
.verdict b{font:700 32px/1.05 var(--sans);letter-spacing:-.03em}
.reason{color:var(--ink2);font-size:14px;margin-bottom:14px}
.split{display:grid;grid-template-columns:1fr 1fr;gap:14px}
@media(max-width:620px){.split{grid-template-columns:1fr}}
.half{border:1px solid var(--line);border-radius:11px;padding:14px 16px;background:var(--bg2)}
.half h3{font:11px/1 var(--mono);letter-spacing:.12em;text-transform:uppercase;
  color:var(--dim);margin-bottom:10px}
.half .d{font:700 20px/1.15 var(--sans);letter-spacing:-.02em;margin-bottom:6px}

/* ---------- hash compare ---------- */
.hash{font-family:var(--mono);font-size:11.5px;letter-spacing:.02em;
  background:var(--bg);border:1px solid var(--line);border-radius:8px;
  padding:11px 13px;margin:7px 0;word-break:break-all;line-height:1.65;position:relative}
.hash.match{border-color:rgba(53,217,154,.45)}
.hash.differ{border-color:rgba(255,95,109,.45)}
.hash .lbl{display:block;font-size:10px;letter-spacing:.12em;text-transform:uppercase;
  color:var(--dim);margin-bottom:5px}
.diffch{color:var(--bad);font-weight:700}
footer{border-top:1px solid var(--line);padding:26px 0 46px;color:var(--dim);font-size:12.5px}
</style></head><body>

<header class="top"><div class="wrap">
  <span class="brand">Vouch<i>.</i></span>
  <span class="chip" id="net"><span class="dot"></span>connecting</span>
  <span class="chip" id="issuer"></span>
  <span class="spacer"></span>
  <span class="chip dimc" id="store">memory</span>
</div></header>

<div class="wrap">
  <div class="hero">
    <div class="kicker">ERC-8004 · Base · Sibyl Memory</div>
    <h1>Agents remember.<br><em>Now they can tell each other.</em></h1>
    <p class="lede">ERC-8004 stores a reputation score on-chain and leaves two fields —
      <span class="mono acc">feedbackURI</span> and <span class="mono acc">feedbackHash</span> —
      for the story behind it. They are empty everywhere. Vouch fills them with
      hash-committed memory, so one agent's experience becomes evidence another
      agent can verify for itself.</p>
    <div class="stats">
      <div class="stat"><b id="s-ratings">—</b><span>ratings on chain</span></div>
      <div class="stat"><b id="s-verified">—</b><span>verified evidence</span></div>
      <div class="stat"><b id="s-disputes">—</b><span>verified disputes</span></div>
      <div class="stat"><b id="s-cp">—</b><span>counterparties known</span></div>
    </div>
  </div>
</div>

<div class="wrap"><main>

  <section class="wide">
    <div class="h"><span class="num">01</span><h2>The network</h2></div>
    <p class="lede2">Every rating published about this counterparty, by anyone. Each evidence
      file is fetched and re-hashed; only files that still match the digest committed on-chain
      are believed. Everything else is recorded and ignored.</p>
    <div id="network"><div class="empty"><span class="spin"></span>reading the registry…</div></div>
  </section>

  <section>
    <div class="h"><span class="num">02</span><h2>The decision</h2></div>
    <p class="lede2">A counterparty this agent has <b>never dealt with</b>, decided twice: once
      knowing only its own history, once with verified evidence from the network. Own memory
      alone knows nothing about a stranger. This is the whole product in one comparison.</p>
    <button class="primary" onclick="both('newcomer')">Stranger · run both</button>
    <button onclick="both('swiftrender')">Known counterparty</button>
    <div id="decision"><div class="empty">press Run both</div></div>
  </section>

  <section>
    <div class="h"><span class="num">03</span><h2>Tamper detection</h2></div>
    <p class="lede2">Evidence lives on a mutable host, on purpose. The on-chain hash is what
      makes editing it detectable. This forges the file for real and re-checks it.</p>
    <button onclick="tamper()">Forge the evidence</button>
    <div id="tamper"><div class="empty">press the button</div></div>
  </section>

  <section>
    <div class="h"><span class="num">04</span><h2>The gate</h2></div>
    <p class="lede2">Delete the memory layer and the product must stop working — not degrade.
      Same code, same counterparty, memory removed.</p>
    <button onclick="gate()">Run the delete test</button>
    <div id="gate"><div class="empty">press the button</div></div>
  </section>

  <section>
    <div class="h"><span class="num">05</span><h2>Memory</h2></div>
    <p class="lede2">Sibyl Memory, five tiers. Counterparties are WARM entities, one row each,
      uniqueness enforced by the schema so two records of the same agent cannot exist.</p>
    <div id="memory"><div class="empty"><span class="spin"></span>loading…</div></div>
  </section>

  <section>
    <div class="h"><span class="num">06</span><h2>Policy · the REFERENCE tier</h2></div>
    <p class="lede2">The rules the engine reads at decision time. They live in memory, not in
      code: edit the record and the agent behaves differently on the next call.</p>
    <div id="policy"><div class="empty"><span class="spin"></span>loading…</div></div>
  </section>

</main>
<footer>Vouch · team Attrito · Sibyl Labs Hackathon 2026 · all transactions on Base Sepolia testnet</footer>
</div>

<script>
const $=id=>document.getElementById(id);
const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const row=(k,v)=>`<div class="row"><span class="k">${esc(k)}</span><span class="v">${v}</span></div>`;
const get=async u=>{const r=await fetch(u);return r.json()};
const busy=(el,msg)=>{$(el).innerHTML=`<div class="empty"><span class="spin"></span>${esc(msg)}</div>`};
const short=(s,n=22)=>s?esc(s.slice(0,n))+"…":"";

function hashCompare(a,b){
  let out="";
  for(let i=0;i<b.length;i++){
    const same=a[i]===b[i];
    out+= same?esc(b[i]):`<span class="diffch">${esc(b[i])}</span>`;
  }
  return out;
}

async function load(){
  const s=await get("/api/state");
  if(!s.ready){$("memory").innerHTML=`<div class="empty">${esc(s.hint)}</div>`;return}

  const n=$("net");
  n.className="chip "+(s.chain_live?"live":"off");
  n.innerHTML=`<span class="dot"></span>${esc(s.network)}${s.chain_live?" · live":" · offline"}`;
  $("issuer").textContent=s.issuer?s.issuer.slice(0,12)+"…":"";
  $("store").textContent=`sibyl schema v${s.schema_version} · ${(s.db_bytes/1024).toFixed(0)} KB`;
  $("s-cp").textContent=s.counterparties.length;

  $("memory").innerHTML=s.counterparties.map(c=>`
    <div class="card fade">
      <div class="top2">
        <span><b>${esc(c.handle)}</b> <span class="mono dimc">ERC-8004 #${esc(c.agent_id)}</span></span>
        ${c.flagged?'<span class="badge bad">FLAGGED</span>':''}
      </div>
      ${row("jobs completed",`<b>${c.jobs_completed}</b>`)}
      ${row("jobs disputed",`<b class="${c.jobs_disputed?'bad':'dimc'}">${c.jobs_disputed}</b>`)}
    </div>`).join("")
    +row("store",`<span class="mono">${esc(s.store)}</span>`)
    +row("evidence files",s.evidence_files.length);

  $("policy").innerHTML=Object.entries(s.policy).filter(([k])=>k!=="notes")
    .map(([k,v])=>row(k,`<span class="mono acc">${esc(v)}</span>`)).join("");

  network();
}

async function network(){
  busy("network","reading the registry and verifying every evidence file…");
  const n=await get("/api/network");
  if(n.error){$("network").innerHTML=`<div class="empty bad">${esc(n.error)}</div>`;return}

  const ver=n.ratings.filter(r=>r.verified).length;
  $("s-ratings").textContent=n.ratings.length;
  $("s-verified").textContent=ver;
  $("s-disputes").textContent=n.verified_disputes;

  $("network").innerHTML=
    row("subject",`<span class="mono">ERC-8004 agent #${n.agent_id}</span>`)+
    row("registry",`<span class="mono">${esc(n.registry)}</span>`)+
    row("believed",`<b class="${ver?'ok':'dimc'}">${ver}</b> of ${n.ratings.length} ratings`)+
    (n.ratings.length?n.ratings.map(r=>`
      <div class="card fade ${r.verified?'verified':'rejected'}">
        <div class="top2">
          <div><div class="score">${r.score.toFixed(2)}<small>/100</small></div>
            <span class="mono dimc">${esc(r.issuer.slice(0,20))}…</span></div>
          <span class="badge ${r.verified?'ok':'bad'}">
            <span class="dot"></span>${r.verified?'VERIFIED':'DISCARDED'}</span>
        </div>
        ${row("status",`<span class="${r.verified?'ok':'bad'}">${esc(r.status)}</span>`)}
        ${r.digest?row("committed hash",`<span class="mono">${short(r.digest,30)}</span>`):""}
        ${r.uri?row("evidence",`<a class="mono" target="_blank" href="${esc(r.uri)}">open file ↗</a>`):""}
        ${r.tx?row("transaction",`<a class="mono" target="_blank" href="${esc(n.explorer)}/tx/${esc(r.tx.startsWith("0x")?r.tx:"0x"+r.tx)}">${short(r.tx,20)} ↗</a>`):""}
        ${r.testimony.length?`<div style="margin-top:10px">${r.testimony.map(t=>`<div class="quote">${esc(t)}</div>`).join("")}</div>`:""}
      </div>`).join(""):`<div class="empty">no ratings published yet</div>`);
}

function verdictBlock(v){
  const bad=v.decision==="REFUSE", warn=v.decision!=="ACCEPT"&&!bad;
  return `<div class="d ${bad?'bad':(warn?'warn':'ok')}">${esc(v.decision)}</div>
    <div class="reason">${esc(v.reason)}</div>
    ${row("quoted",`$${Number(v.quoted_price_usd).toFixed(2)} <span class="dimc">of $${Number(v.standard_price_usd).toFixed(2)}</span>`)}
    ${row("escrow",v.escrow_required?'<span class="warn">required</span>':'no')}
    ${row("evidence",v.evidence_checked?(v.evidence_verified?'<span class="ok">verified</span>':'<span class="dimc">none verified</span>'):'<span class="dimc">not checked</span>')}`;
}

async function both(handle){
  busy("decision","deciding twice…");
  const q=`&handle=${encodeURIComponent(handle||"swiftrender")}`;
  const [off,on]=await Promise.all([get("/api/decide?offline=1"+q),get("/api/decide?offline=0"+q)]);
  const changed=off.decision!==on.decision;
  $("decision").innerHTML=`<div class="split fade">
      <div class="half"><h3>Memory only · ${esc(off.handle)}</h3>${verdictBlock(off)}</div>
      <div class="half"><h3>Memory + network · ${esc(on.handle)}</h3>${verdictBlock(on)}</div>
    </div>
    <div style="margin-top:14px">${row("network changed the outcome",
      changed?'<span class="badge ok"><span class="dot"></span>YES</span>'
             :'<span class="badge dimc">no — both agree</span>')}</div>
    ${on.citations.length?`<div style="margin-top:8px">${on.citations.map(c=>`<div class="quote">${esc(c)}</div>`).join("")}</div>`:""}`;
}

async function decide(offline){
  busy("decision","deciding…");
  const v=await get(`/api/decide?offline=${offline}`);
  $("decision").innerHTML=`<div class="fade">
    <div class="verdict"><b class="${v.decision==="REFUSE"?'bad':(v.decision==="ACCEPT"?'ok':'warn')}">${esc(v.decision)}</b>
      <span class="badge dimc">${offline?'memory only':'memory + network'}</span></div>
    <div class="reason">${esc(v.reason)}</div>
    ${row("quoted",`$${Number(v.quoted_price_usd).toFixed(2)} <span class="dimc">of $${Number(v.standard_price_usd).toFixed(2)}</span>`)}
    ${row("escrow",v.escrow_required?'<span class="warn">required</span>':'no')}
    ${row("evidence",v.evidence_checked?(v.evidence_verified?'<span class="ok">checked · verified</span>':'<span class="dimc">checked · none verified</span>'):'<span class="dimc">not checked</span>')}
    ${v.citations.map(c=>`<div class="quote">${esc(c)}</div>`).join("")}</div>`;
}

async function tamper(){
  busy("tamper","forging and re-checking…");
  const t=await get("/api/tamper");
  if(t.error){$("tamper").innerHTML=`<div class="empty bad">${esc(t.error)}</div>`;return}
  $("tamper").innerHTML=`<div class="fade">
    ${row("file",`<span class="mono">${short(t.file,20)}</span>`)}
    ${row("edit applied",`<span class="dimc">${esc(t.forgery)}</span>`)}
    <div class="hash match"><span class="lbl">committed on chain · honest file</span>${esc(t.committed_hash)}
      <div style="margin-top:8px"><span class="badge ok"><span class="dot"></span>VERIFIES</span></div></div>
    <div class="hash differ"><span class="lbl">recomputed after the forgery</span>${hashCompare(t.committed_hash,t.forged_hash)}
      <div style="margin-top:8px"><span class="badge bad"><span class="dot"></span>REJECTED</span></div></div>
    <div class="reason" style="margin-top:12px">Changing one number changes the digest. A consumer
      re-hashes the file it was served and discards anything that does not match.</div></div>`;
}

async function gate(){
  busy("gate","running with and without memory…");
  const g=await get("/api/delete-test");
  $("gate").innerHTML=`<div class="split fade">
      <div class="half"><h3>With memory</h3>
        <div class="d ${g.with_memory&&g.with_memory.decision==='REFUSE'?'bad':'ok'}">${esc(g.with_memory?g.with_memory.decision:'n/a')}</div>
        <div class="reason">${esc(g.with_memory?g.with_memory.reason:'')}</div></div>
      <div class="half"><h3>Memory deleted</h3>
        <div class="d warn">${esc(g.without_memory.decision)}</div>
        <div class="reason">${esc(g.without_memory.reason)}</div></div>
    </div>
    <div style="margin-top:14px">${row("behaviour differs",
      g.differs?'<span class="badge ok"><span class="dot"></span>YES — memory is load-bearing</span>'
               :'<span class="badge bad">NO</span>')}</div>`;
}

load();
</script></body></html>
"""
