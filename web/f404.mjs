import { chromium } from "playwright-core";
const browser = await chromium.launch({ executablePath: process.env.PW_CHROME });
const page = await browser.newPage();
page.on("response", r => { if (r.status() >= 400) console.log("  " + r.status() + "  " + r.url()); });
await page.goto("https://egbujor-emmanuel.github.io/vouch/", { waitUntil: "networkidle", timeout: 60000 }).catch(()=>{});
await browser.close();
