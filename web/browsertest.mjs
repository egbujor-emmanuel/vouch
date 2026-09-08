import { chromium } from "playwright-core";

const URL = process.argv[2] || "https://egbujor-emmanuel.github.io/vouch/";
const browser = await chromium.launch({ channel: undefined, executablePath: process.env.PW_CHROME });
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });

const errors = [], console_ = [], failed = [];
page.on("pageerror", e => errors.push(String(e).slice(0, 200)));
page.on("console", m => { if (m.type() === "error") console_.push(m.text().slice(0, 200)); });
page.on("requestfailed", r => failed.push(r.url().slice(0, 90) + " :: " + (r.failure()?.errorText || "")));

await page.goto(URL, { waitUntil: "networkidle", timeout: 90000 }).catch(e => errors.push("goto: " + e.message));

const panelState = async () => page.evaluate(() => {
  const ids = ["inspect","decision","network","dispute","tamper","gate","memory","policy"];
  const out = {};
  for (const id of ids) {
    const el = document.getElementById(id);
    out[id] = el ? el.innerText.trim().slice(0, 60).replace(/\s+/g," ") : "MISSING";
  }
  out._stats = ["s-ratings","s-verified","s-disputes","s-cp"].map(i=>document.getElementById(i)?.textContent).join("/");
  return out;
});

console.log("=== immediately after load ===");
console.log(JSON.stringify(await panelState(), null, 1));

await page.waitForTimeout(35000);
console.log("\n=== after 35s ===");
console.log(JSON.stringify(await panelState(), null, 1));

console.log("\n=== page errors ===");   console.log(errors.length ? errors.join("\n") : "  none");
console.log("=== console errors ==="); console.log(console_.length ? console_.slice(0,6).join("\n") : "  none");
console.log("=== failed requests ==="); console.log(failed.length ? failed.slice(0,6).join("\n") : "  none");

await page.screenshot({ path: "/tmp/vouch-live.png", fullPage: false });
console.log("\nscreenshot saved");
await browser.close();
