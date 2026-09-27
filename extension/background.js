// ShortsRadar extension service worker: relays a few read-only requests from YouTube tabs to the
// ShortsRadar app running on this computer (http://127.0.0.1:<port>). Only whitelisted endpoints.
const ALLOWED = new Set(["/api/video", "/api/keyword/quick", "/api/status"]);

async function settings() {
  const { port = 8765 } = await chrome.storage.local.get("port");
  return { base: `http://127.0.0.1:${Number(port) || 8765}` };
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg || msg.type !== "api" || !ALLOWED.has(msg.path)) {
    sendResponse({ error: "Not allowed", code: "forbidden" });
    return false;
  }
  (async () => {
    const { base } = await settings();
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(msg.params || {})) if (v !== undefined && v !== null && v !== "") qs.set(k, String(v));
    try {
      const res = await fetch(`${base}${msg.path}?${qs}`, { headers: { "X-ShortsRadar": "1" } });
      const data = await res.json().catch(() => null);
      if (!res.ok) sendResponse({ error: (data && data.error) || `Error ${res.status}`, code: data && data.code, base });
      else sendResponse({ data, base });
    } catch {
      sendResponse({ error: "ShortsRadar isn't running. Start it on your computer (python run.py), then reload this page.", code: "offline", base });
    }
  })();
  return true; // keep the channel open for the async response
});
