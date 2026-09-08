import { chromium } from "playwright-core";
const URL = "https://egbujor-emmanuel.github.io/vouch/";
const browser = await chromium.launch({ executablePath: process.env.PW_CHROME });
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
const errs = [], cons = [], failed = [];
page.on("pageerror", e => errs.push(String(e).slice(0,180)));
page.on("console", m => { if (m.type()==="error") cons.push(m.text().slice(0,180)); });
page.on("requestfailed", r => failed.push(r.url().slice(0,70)+" :: "+(r.failure()?.errorText||"")));

const t0 = Date.now();
await page.goto(URL, { waitUntil: "domcontentloaded", timeout: 60000 });
const snap = async () => page.evaluate(() => {
  const g = id => { const e = document.getElementById(id); return e ? e.innerText.trim().replace(/\s+/g," ").slice(0,70) : "MISSING"; };
  return { stats: ["s-ratings","s-verified","s-disputes","s-cp"].map(i=>document.getElementById(i)?.textContent).join("/"),
           network: g("network"), decision: g("decision"), inspect: g("inspect") };
});
await page.waitForTimeout(2500);
console.log("=== at 2.5s (does it paint instantly?) ===");
console.log(JSON.stringify(await snap(), null, 1));
await page.waitForTimeout(40000);
console.log("\n=== at 42s (after live verification) ===");
console.log(JSON.stringify(await snap(), null, 1));
console.log("\npage errors :", errs.length ? errs.join(" | ") : "none");
console.log("console errs:", cons.length ? cons.slice(0,4).join(" | ") : "none");
console.log("failed reqs :", failed.length ? failed.slice(0,4).join(" | ") : "none");
await page.screenshot({ path: "shot.png" });
await browser.close();
