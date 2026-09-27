// UI smoke test: visits every page of a running ShortsRadar (demo mode), fails on JS errors,
// and saves screenshots. Usage: node tests/ui/smoke.mjs http://127.0.0.1:8765 ./screenshots
import { createRequire } from "module";
const require = createRequire(import.meta.url);
let playwright;
try { playwright = require("playwright"); } catch { playwright = require("/opt/node22/lib/node_modules/playwright"); }
const { chromium } = playwright;
import fs from "fs";

const base = (process.argv[2] || "http://127.0.0.1:8765").replace(/\/$/, "");
const outDir = process.argv[3] || "screenshots";
fs.mkdirSync(outDir, { recursive: true });
const H = { "X-ShortsRadar": "1", "Content-Type": "application/json" };
const apiGet = async (p) => (await fetch(base + p, { headers: H })).json();
const apiPost = async (p, body) => (await fetch(base + p, { method: "POST", headers: H, body: JSON.stringify(body) })).json();

const trending = await apiGet("/api/trending?format=any");
const short = trending.videos.find((v) => v.is_short) || trending.videos[0];
const channelId = short.channel_id;
const others = [...new Set(trending.videos.map((v) => v.channel_id))].filter((c) => c !== channelId).slice(0, 3);
for (const c of [channelId, ...others]) await apiPost("/api/competitors", { ref: c });
await apiPost("/api/saved", { kind: "keyword", ref: "minecraft redstone", title: "minecraft redstone", data: {} });

const pages = [
  ["home", "#/"],
  ["keywords", "#/keywords?q=minecraft%20redstone"],
  ["outliers", "#/outliers?q=minecraft&format=short&within=3months"],
  ["video", `#/video?id=${short.id}`],
  ["channel", `#/channel?id=${channelId}`],
  ["competitors", "#/competitors"],
  ["trending", "#/trending"],
  ["trending-niche", "#/trending?mode=niche&q=cooking&hours=720&format=any"],
  ["seo", "#/seo?keyword=minecraft%20redstone&title=I%20Built%20a%20Hidden%20Redstone%20Door%20in%2060%20Seconds"],
  ["titles", "#/titles?q=minecraft%20redstone&t=" + encodeURIComponent("minecraft redstone door\nI Tried Minecraft Redstone for 24 Hours\nTHIS IS INSANE!!!")],
  ["ai", "#/ai?task=script&topic=hidden%20redstone%20door&keyword=minecraft%20redstone&run=1"],
  ["ideas", "#/ideas?run=1"],
  ["earnings", "#/earnings"],
  ["saved", "#/saved"],
  ["settings", "#/settings"],
];

const browser = await chromium.launch();
const errors = [];
// Demo thumbnails point at i.ytimg.com with synthetic IDs: serve a neutral placeholder instead.
const PIXEL = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mN88OjRfwAJKgPmNXgKmQAAAABJRU5ErkJggg==", "base64");
async function stubExternal(ctx) {
  await ctx.route(/^https?:\/\/(?!127\.0\.0\.1|localhost)/, (route) => route.fulfill({ status: 200, contentType: "image/png", body: PIXEL }));
}
async function visit(ctx, name, hash, file) {
  const page = await ctx.newPage();
  page.on("console", (m) => { if (m.type() === "error") errors.push(`[${name}] console: ${m.text()}`); });
  page.on("pageerror", (e) => errors.push(`[${name}] pageerror: ${e.message}`));
  await page.goto(base + "/" + hash, { waitUntil: "networkidle" });
  await page.waitForFunction(() => !document.querySelector("#main .loader") && document.querySelector("#main").children.length > 0, null, { timeout: 60000 });
  await page.waitForTimeout(700);
  const errBox = await page.$("#main .error-box");
  if (errBox) errors.push(`[${name}] error box shown: ${(await errBox.innerText()).slice(0, 200)}`);
  await page.screenshot({ path: `${outDir}/${file}.png`, fullPage: true });
  await page.close();
}
const desktop = await browser.newContext({ viewport: { width: 1440, height: 950 } });
await stubExternal(desktop);
for (const [name, hash] of pages) await visit(desktop, name, hash, name);
const dark = await browser.newContext({ viewport: { width: 1440, height: 950 }, colorScheme: "dark" });
await stubExternal(dark);
await visit(dark, "channel-dark", `#/channel?id=${channelId}`, "channel-dark");
await visit(dark, "keywords-dark", "#/keywords?q=minecraft%20redstone", "keywords-dark");
const mobile = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
await stubExternal(mobile);
await visit(mobile, "home-mobile", "#/", "home-mobile");
await visit(mobile, "keywords-mobile", "#/keywords?q=minecraft%20redstone", "keywords-mobile");
await visit(mobile, "video-mobile", `#/video?id=${short.id}`, "video-mobile");
// overflow check on mobile: no horizontal page scroll
const mp = await mobile.newPage();
await mp.goto(base + "/#/channel?id=" + channelId, { waitUntil: "networkidle" });
await mp.waitForFunction(() => !document.querySelector("#main .loader"), null, { timeout: 60000 });
const overflow = await mp.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
if (overflow > 1) errors.push(`[mobile] horizontal overflow of ${overflow}px on channel page`);
await browser.close();
if (errors.length) { console.log("FAILURES:\n" + errors.join("\n")); process.exit(1); }
console.log(`OK — ${pages.length + 5} page renders, no JS errors. Screenshots in ${outDir}`);
