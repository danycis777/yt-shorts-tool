// Loads the unpacked extension into Chromium, serves mock YouTube pages, and checks the panel
// renders data from a running ShortsRadar (demo mode). Usage: node tests/ui/extension.mjs http://127.0.0.1:8765 outdir
import { createRequire } from "module";
import fs from "fs";
import os from "os";
import path from "path";
import { fileURLToPath } from "url";
const require = createRequire(import.meta.url);
let playwright;
try { playwright = require("playwright"); } catch { playwright = require("/opt/node22/lib/node_modules/playwright"); }
const { chromium } = playwright;
const here = path.dirname(fileURLToPath(import.meta.url));
const extDir = path.resolve(here, "../../extension");
const base = (process.argv[2] || "http://127.0.0.1:8765").replace(/\/$/, "");
const outDir = process.argv[3] || "screenshots";
fs.mkdirSync(outDir, { recursive: true });
const H = { "X-ShortsRadar": "1" };
const tr = await (await fetch(base + "/api/trending?format=any", { headers: H })).json();
const short = tr.videos.find((v) => v.is_short);
const long = tr.videos.find((v) => !v.is_short) || tr.videos[1];

const userDir = fs.mkdtempSync(path.join(os.tmpdir(), "sr-ext-"));
const ctx = await chromium.launchPersistentContext(userDir, {
  channel: "chromium", headless: true, viewport: { width: 1280, height: 800 },
  args: [`--disable-extensions-except=${extDir}`, `--load-extension=${extDir}`],
});
const mockPage = (title, dark) => `<!doctype html><html ${dark ? "dark" : ""}><head><title>${title}</title></head>
<body style="margin:0;font-family:sans-serif;background:${dark ? "#0f0f0f" : "#fff"};color:${dark ? "#fff" : "#000"}">
<div style="height:60px;border-bottom:1px solid #8884;padding:18px 24px;font-weight:700">YouTube (mock page for testing)</div>
<div style="margin:24px;width:760px;height:428px;background:#222;border-radius:12px"></div><h2 style="margin:24px">${title}</h2></body></html>`;
await ctx.route("https://www.youtube.com/**", (route) => {
  const u = new URL(route.request().url());
  if (route.request().resourceType() !== "document") return route.fulfill({ status: 204, body: "" });
  const dark = u.searchParams.get("dark") === "1";
  return route.fulfill({ status: 200, contentType: "text/html", body: mockPage(u.pathname + u.search, dark) });
});
const errors = [];
const page = await ctx.newPage();
page.on("pageerror", (e) => errors.push("pageerror: " + e.message));
const panelText = () => page.evaluate(() => {
  const host = document.getElementById("shortsradar-extension");
  return host && host.shadowRoot ? host.shadowRoot.textContent : "";
});
async function waitFor(text, label) {
  const start = Date.now();
  while (Date.now() - start < 20000) {
    const t = await panelText();
    if (t.includes(text)) return t;
    await page.waitForTimeout(250);
  }
  errors.push(`${label}: panel never showed "${text}". Last text: ${(await panelText()).slice(0, 300)}`);
  return "";
}
// 1) a Short
await page.goto(`https://www.youtube.com/shorts/${short.id}`);
let t = await waitFor("Outlier score", "shorts page");
if (t && !t.includes("SEO score")) errors.push("shorts page: SEO score missing");
if (t && !t.includes("Short")) errors.push("shorts page: not labelled as a Short");
await page.waitForTimeout(800);
await page.screenshot({ path: `${outDir}/ext-short.png` });
// 2) SPA navigation to a long-form watch page (no reload) in YouTube dark theme
await page.evaluate((id) => { document.documentElement.setAttribute("dark", ""); history.pushState({}, "", `/watch?v=${id}`); }, long.id);
t = await waitFor(long.title.slice(0, 12) ? "Views / hour" : "Views", "spa watch");
await page.waitForTimeout(1500);
const t2 = await panelText();
if (!t2.includes("Tags (")) errors.push("watch page: tags section missing");
await page.screenshot({ path: `${outDir}/ext-watch-dark.png` });
// 3) search results page -> keyword score
await page.goto(`https://www.youtube.com/results?search_query=${encodeURIComponent("minecraft redstone")}`);
t = await waitFor("Search volume", "search page");
if (t && !t.includes("minecraft redstone")) errors.push("search page: query not shown");
await page.waitForTimeout(500);
await page.screenshot({ path: `${outDir}/ext-search.png` });
// 4) minimize -> pill, persisted across navigation
await page.evaluate(() => document.getElementById("shortsradar-extension").shadowRoot.querySelector('button[title="Minimize"]').click());
await page.waitForTimeout(300);
await page.goto(`https://www.youtube.com/shorts/${short.id}`);
await page.waitForTimeout(2500);
const miniVisible = await page.evaluate(() => { const m = document.getElementById("shortsradar-extension").shadowRoot.querySelector(".mini"); return m && !m.classList.contains("hidden"); });
if (!miniVisible) errors.push("minimized state not persisted");
// 5) offline behaviour: point the extension at a closed port
const [sw] = ctx.serviceWorkers().length ? ctx.serviceWorkers() : [await ctx.waitForEvent("serviceworker")];
await sw.evaluate(() => chrome.storage.local.set({ port: 9, collapsed: false }));
await page.goto(`https://www.youtube.com/watch?v=${short.id}`);
await waitFor("isn't running", "offline message");
await page.screenshot({ path: `${outDir}/ext-offline.png` });
await ctx.close();
if (errors.length) { console.log("FAILURES:\n" + errors.join("\n")); process.exit(1); }
console.log("OK — extension panel works on Shorts, watch (SPA nav, dark), search, minimize persistence and offline state.");
