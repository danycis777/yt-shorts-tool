// ShortsRadar panel on YouTube: stats for the current video/Short, and keyword scores on search pages.
// Rendered inside a Shadow DOM so YouTube's CSS can't break it (and vice versa).
(() => {
  if (window.__shortsRadarLoaded) return;
  window.__shortsRadarLoaded = true;

  const STYLE = `
    :host { all: initial; }
    .panel { position: fixed; right: 16px; bottom: 16px; z-index: 2147483000; width: 320px; max-height: 72vh; overflow: auto;
      font: 13px/1.45 system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif; color: var(--ink);
      background: var(--surface); border: 1px solid var(--border); border-radius: 14px; box-shadow: 0 10px 40px rgba(0,0,0,.28); }
    .panel { --surface: #fcfcfb; --surface2: #f0efec; --ink: #0b0b0b; --ink2: #52514e; --muted: #7a7873; --border: rgba(11,11,11,.12);
      --accent: #2a78d6; --good: #006300; --goodbg: #e5f5e5; --warn: #7a5200; --warnbg: #fdf3dc; --bad: #a42a2a; --badbg: #fbe6e6; }
    .panel.dark { --surface: #1a1a19; --surface2: #262625; --ink: #fff; --ink2: #c3c2b7; --muted: #979590; --border: rgba(255,255,255,.14);
      --accent: #3987e5; --good: #3ec43e; --goodbg: #0f2a10; --warn: #fab219; --warnbg: #33280b; --bad: #f08080; --badbg: #3a1515; }
    .head { display: flex; align-items: center; gap: 8px; padding: 10px 12px; border-bottom: 1px solid var(--border); position: sticky; top: 0; background: var(--surface); }
    .logo { flex: none; width: 22px; height: 22px; border-radius: 7px; background: var(--accent); display: grid; place-items: center; color: #fff; font-weight: 800; font-size: 11px; }
    .name { font-weight: 700; flex: 1; min-width: 0; display: flex; align-items: center; gap: 6px; white-space: nowrap; overflow: hidden; }
    .head a.btn, .head button { flex: none; white-space: nowrap; }
    .badge { font-size: 11px; font-weight: 700; padding: 1px 7px; border-radius: 99px; background: var(--surface2); color: var(--ink2); }
    button, a.btn { font: inherit; border: 1px solid var(--border); background: var(--surface); color: var(--ink); border-radius: 8px; padding: 4px 9px; cursor: pointer; text-decoration: none; font-size: 12px; font-weight: 600; }
    button:hover, a.btn:hover { background: var(--surface2); }
    .icon { border: none; background: transparent; padding: 2px 6px; font-size: 16px; line-height: 1; color: var(--ink2); }
    .body { padding: 12px; display: flex; flex-direction: column; gap: 12px; }
    .grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
    .stat { background: var(--surface2); border-radius: 10px; padding: 8px 10px; }
    .stat .k { font-size: 11.5px; color: var(--ink2); font-weight: 600; }
    .stat .v { font-size: 18px; font-weight: 750; margin-top: 1px; }
    .stat .s { font-size: 11px; color: var(--muted); }
    .scores { display: flex; gap: 8px; }
    .score { flex: 1; border: 1px solid var(--border); border-radius: 10px; padding: 8px 10px; }
    .score .v { font-size: 20px; font-weight: 800; }
    .grade { display: inline-block; font-size: 11px; font-weight: 800; padding: 1px 6px; border-radius: 5px; margin-left: 4px; vertical-align: middle; }
    .A, .B { background: var(--goodbg); color: var(--good); } .C { background: var(--warnbg); color: var(--warn); } .D, .F { background: var(--badbg); color: var(--bad); }
    .label { font-size: 11.5px; font-weight: 700; color: var(--ink2); margin-bottom: 6px; display: flex; justify-content: space-between; align-items: center; }
    .chips { display: flex; flex-wrap: wrap; gap: 5px; }
    .chip { background: var(--surface2); border: 1px solid var(--border); border-radius: 99px; padding: 2px 8px; font-size: 12px; }
    .fix { font-size: 12px; color: var(--ink2); padding-left: 14px; position: relative; margin: 3px 0; }
    .fix::before { content: "→"; position: absolute; left: 0; color: var(--accent); }
    .meter { height: 6px; border-radius: 99px; background: var(--surface2); overflow: hidden; margin-top: 5px; }
    .meter i { display: block; height: 100%; background: var(--accent); border-radius: 99px; }
    .muted { color: var(--muted); font-size: 12px; }
    .err { background: var(--badbg); color: var(--bad); border-radius: 10px; padding: 10px; font-size: 12.5px; }
    .spin { width: 16px; height: 16px; border: 2px solid var(--surface2); border-top-color: var(--accent); border-radius: 50%; animation: s .8s linear infinite; display: inline-block; vertical-align: middle; margin-right: 8px; }
    @keyframes s { to { transform: rotate(360deg); } }
    .mini { position: fixed; right: 16px; bottom: 16px; z-index: 2147483000; display: flex; align-items: center; gap: 6px; cursor: pointer;
      font: 700 13px system-ui, sans-serif; background: #2a78d6; color: #fff; border-radius: 99px; padding: 7px 12px; box-shadow: 0 6px 24px rgba(0,0,0,.3); border: none; }
    .hidden { display: none !important; }
  `;

  const host = document.createElement("div");
  host.id = "shortsradar-extension";
  const root = host.attachShadow({ mode: "open" });
  const style = document.createElement("style");
  style.textContent = STYLE;
  const panel = el("div", { class: "panel hidden", role: "complementary", "aria-label": "ShortsRadar" });
  const mini = el("button", { class: "mini hidden", title: "Show ShortsRadar" }, "SR");
  root.append(style, panel, mini);
  document.documentElement.appendChild(host);

  let collapsed = false;
  let enabled = true;
  let dashboard = "http://127.0.0.1:8765";
  let lastKey = null;
  let seq = 0;
  const cache = new Map();

  chrome.storage.local.get(["collapsed", "enabled"], (v) => {
    collapsed = !!v.collapsed;
    enabled = v.enabled !== false;
    onNav(true);
  });
  chrome.storage.onChanged.addListener((changes) => {
    if (changes.enabled) { enabled = changes.enabled.newValue !== false; onNav(true); }
  });

  function el(tag, attrs, ...kids) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k.startsWith("on") && typeof v === "function") n.addEventListener(k.slice(2).toLowerCase(), v);
      else n.setAttribute(k, v);
    }
    for (const kid of kids.flat()) if (kid !== null && kid !== undefined && kid !== false) n.append(kid instanceof Node ? kid : String(kid));
    return n;
  }
  const compact = (n) => {
    if (n === null || n === undefined) return "—";
    const a = Math.abs(n);
    if (a >= 1e9) return (n / 1e9).toFixed(1).replace(/\.0$/, "") + "B";
    if (a >= 1e6) return (n / 1e6).toFixed(1).replace(/\.0$/, "") + "M";
    if (a >= 1e3) return (n / 1e3).toFixed(1).replace(/\.0$/, "") + "K";
    return String(Math.round(n));
  };
  const times = (x) => (x === null || x === undefined ? "—" : `${x >= 10 ? Math.round(x) : Number(x).toFixed(1)}×`);
  const safeHref = (u) => { try { const x = new URL(u); return x.protocol === "http:" || x.protocol === "https:" ? x.href : "#"; } catch { return "#"; } };

  function target() {
    const u = new URL(location.href);
    if (u.pathname === "/watch" && u.searchParams.get("v")) return { type: "video", id: u.searchParams.get("v") };
    const m = u.pathname.match(/^\/shorts\/([A-Za-z0-9_-]{11})/);
    if (m) return { type: "video", id: m[1] };
    if (u.pathname === "/results" && u.searchParams.get("search_query")) return { type: "search", q: u.searchParams.get("search_query") };
    return null;
  }

  function api(path, params) {
    return new Promise((resolve) => {
      try {
        chrome.runtime.sendMessage({ type: "api", path, params }, (res) => {
          if (chrome.runtime.lastError) resolve({ error: "Extension was updated — reload this page.", code: "reload" });
          else resolve(res || { error: "No response", code: "none" });
        });
      } catch {
        resolve({ error: "Extension was updated — reload this page.", code: "reload" });
      }
    });
  }

  function theme() {
    // YouTube marks its dark theme with <html dark>.
    panel.classList.toggle("dark", document.documentElement.hasAttribute("dark"));
  }

  function frame(badge, bodyKids, fullLink) {
    theme();
    panel.replaceChildren(
      el("div", { class: "head" },
        el("div", { class: "logo" }, "SR"),
        el("div", { class: "name", title: "ShortsRadar" }, badge ? el("span", { class: "badge" }, badge) : "ShortsRadar"),
        fullLink ? el("a", { class: "btn", href: safeHref(fullLink), target: "_blank", rel: "noopener", title: "Open the full report in ShortsRadar" }, "Report ↗") : null,
        el("button", { class: "icon", title: "Minimize", "aria-label": "Minimize", onClick: () => setCollapsed(true) }, "–")),
      el("div", { class: "body" }, bodyKids));
  }

  function setCollapsed(v) {
    collapsed = v;
    chrome.storage.local.set({ collapsed: v });
    show();
  }
  mini.addEventListener("click", () => setCollapsed(false));

  function show() {
    const active = enabled && lastKey;
    panel.classList.toggle("hidden", !active || collapsed);
    mini.classList.toggle("hidden", !active || !collapsed);
  }

  function loading(text) { frame(null, [el("div", { class: "muted" }, el("span", { class: "spin" }), text)]); }

  function error(res) {
    frame(null, [el("div", { class: "err" }, res.error || "Something went wrong."),
      res.code === "no_api_key" || res.code === "keyInvalid" ? el("a", { class: "btn", href: safeHref(`${dashboard}/#/settings`), target: "_blank", rel: "noopener" }, "Open ShortsRadar settings") : null]);
  }

  function stat(k, v, s) { return el("div", { class: "stat" }, el("div", { class: "k" }, k), el("div", { class: "v" }, v), s ? el("div", { class: "s" }, s) : null); }

  function renderVideo(r) {
    const st = r.stats || {};
    const seo = r.seo, ts = r.title_score;
    const tags = (r.video.tags || []);
    const kids = [
      el("div", { class: "grid" },
        stat("Views", compact(st.views), st.views_per_sub ? `${times(st.views_per_sub)} subscribers` : null),
        stat("Views / hour", compact(st.vph_recent ?? st.vph_lifetime), st.vph_recent !== null && st.vph_recent !== undefined ? "recent (tracked)" : "lifetime avg"),
        stat("Outlier score", r.outlier ? times(r.outlier.score) : "—", r.outlier ? `usual ${compact(r.outlier.baseline_views)} views` : "not enough data"),
        stat("Engagement", st.engagement_rate !== null && st.engagement_rate !== undefined ? `${st.engagement_rate}%` : "—", st.like_rate ? `${st.like_rate}% like rate` : null)),
      el("div", { class: "scores" },
        el("div", { class: "score" }, el("div", { class: "muted" }, "SEO score"), el("div", {}, el("span", { class: "v" }, String(seo.score)), el("span", { class: "grade " + seo.grade }, seo.grade))),
        el("div", { class: "score" }, el("div", { class: "muted" }, "Title score"), el("div", {}, el("span", { class: "v" }, String(ts.score)), el("span", { class: "grade " + ts.grade }, ts.grade)))),
    ];
    if (seo.keyword) kids.push(el("div", {}, el("div", { class: "label" }, "Target keyword"), el("div", { class: "chip", style: "display:inline-block" }, seo.keyword), el("div", { class: "kwscore muted", style: "margin-top:6px" }, "")));
    if (seo.fixes && seo.fixes.length) kids.push(el("div", {}, el("div", { class: "label" }, "Top fixes"), seo.fixes.slice(0, 3).map((f) => el("div", { class: "fix" }, f))));
    const copy = el("button", { onClick: async () => { try { await navigator.clipboard.writeText(tags.join(", ")); copy.textContent = "Copied ✓"; } catch { copy.textContent = "Copy failed"; } } }, "Copy tags");
    kids.push(el("div", {}, el("div", { class: "label" }, `Tags (${tags.length})`, tags.length ? copy : null),
      tags.length ? el("div", { class: "chips" }, tags.slice(0, 30).map((t) => el("span", { class: "chip" }, t))) : el("div", { class: "muted" }, r.mode === "api" ? "No tags on this video." : "Tags need a YouTube API key in ShortsRadar.")));
    if (r.note) kids.push(el("div", { class: "muted" }, r.note));
    frame(r.video.is_short ? "Short" : "Video", kids, `${dashboard}/#/video?id=${encodeURIComponent(r.video.id)}`);
    if (seo.keyword) {
      const my = seq;
      api("/api/keyword/quick", { q: seo.keyword }).then((k) => {
        if (my !== seq || !k.data) return;
        const slot = panel.querySelector(".kwscore");
        if (slot) slot.textContent = `Search volume ${k.data.volume === null || k.data.volume === undefined ? "—" : Math.round(k.data.volume)}/100 · ~${compact(k.data.monthly)} searches/mo (${(k.data.band || "").toLowerCase()})`;
      });
    }
  }

  function renderSearch(q, k) {
    const meter = (v) => el("div", { class: "meter" }, el("i", { style: `width:${Math.max(0, Math.min(100, v || 0))}%` }));
    const kids = [
      el("div", { class: "muted" }, "Keyword: ", el("b", {}, q)),
      el("div", { class: "grid" },
        el("div", { class: "stat" }, el("div", { class: "k" }, "Search volume"), el("div", { class: "v" }, k.volume === null || k.volume === undefined ? "—" : Math.round(k.volume)), meter(k.volume), el("div", { class: "s" }, `~${compact(k.monthly)} searches/mo`)),
        el("div", { class: "stat" }, el("div", { class: "k" }, "Competition"), el("div", { class: "v" }, k.competition === null || k.competition === undefined ? "—" : Math.round(k.competition)), meter(k.competition), el("div", { class: "s" }, k.competition === null ? "click below to check" : "lower is easier"))),
    ];
    if (k.overall !== null && k.overall !== undefined) kids.push(el("div", { class: "stat" }, el("div", { class: "k" }, "Overall"), el("div", { class: "v" }, Math.round(k.overall)), meter(k.overall)));
    if (k.competition === null) {
      kids.push(el("button", { onClick: async () => {
        loading("Checking competition (uses ~102 YouTube API units)…");
        const my = seq;
        const res = await api("/api/keyword/quick", { q, competition: "1" });
        if (my !== seq) return;
        if (res.error) error(res); else renderSearch(q, res.data);
      } }, "Check competition & overall score"));
    }
    frame("Keyword", kids, `${dashboard}/#/keywords?q=${encodeURIComponent(q)}`);
  }

  async function load(t) {
    const my = ++seq;
    const key = JSON.stringify(t);
    if (cache.has(key)) { const c = cache.get(key); return t.type === "video" ? renderVideo(c) : renderSearch(t.q, c); }
    loading(t.type === "video" ? "Loading video stats…" : "Scoring this search…");
    const res = t.type === "video" ? await api("/api/video", { id: t.id }) : await api("/api/keyword/quick", { q: t.q });
    if (my !== seq) return;
    if (res.base) dashboard = res.base;
    if (res.error) return error(res);
    cache.set(key, res.data);
    if (t.type === "video") renderVideo(res.data); else renderSearch(t.q, res.data);
  }

  function onNav(force) {
    const t = target();
    const key = t ? JSON.stringify(t) : null;
    if (!force && key === lastKey) return;
    lastKey = key;
    show();
    if (t && enabled) load(t);
  }

  window.addEventListener("yt-navigate-finish", () => onNav(false));
  setInterval(() => onNav(false), 800); // Shorts swipes change the URL without a navigation event
})();
