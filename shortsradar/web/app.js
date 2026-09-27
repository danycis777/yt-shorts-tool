// ShortsRadar UI: shell, router and pages.
import {
  api, append, avatar, band, barList, card, cardWithActions, chips, clear, columnChart, copyBtn, copyText, dataTable,
  debounce, empty, errorBox, field, fmt, formatPill, h, icon, img, lineChart, loader, meter, miniMeter, notes, onQuota,
  overallLabel, pill, scoreRing, seg, select, hideTip, tabs, tile, toast,
} from "./core.js";

try { const t = localStorage.getItem("sr-theme"); if (t) document.documentElement.dataset.theme = t; } catch { /* storage blocked */ }

const state = { status: null, renderSeq: 0 };
const REGIONS = [["US", "United States"], ["GB", "United Kingdom"], ["CA", "Canada"], ["AU", "Australia"], ["IN", "India"],
  ["DE", "Germany"], ["FR", "France"], ["ES", "Spain"], ["IT", "Italy"], ["BR", "Brazil"], ["MX", "Mexico"], ["JP", "Japan"],
  ["KR", "South Korea"], ["ID", "Indonesia"], ["PH", "Philippines"], ["NG", "Nigeria"], ["ZA", "South Africa"], ["TR", "Turkey"],
  ["PL", "Poland"], ["NL", "Netherlands"], ["SE", "Sweden"], ["AE", "UAE"], ["SA", "Saudi Arabia"], ["PK", "Pakistan"], ["VN", "Vietnam"]];
const FORMATS = [["short", "Shorts"], ["long", "Long-form"], ["any", "All"]];

const NAV = [
  ["", "Home", "home"],
  ["Research"],
  ["keywords", "Keyword research", "key"],
  ["outliers", "Outliers", "zap"],
  ["trending", "Trending", "trending"],
  ["ideas", "Daily ideas", "bulb"],
  ["Analyze"],
  ["video", "Video scorecard", "video"],
  ["channel", "Channel audit", "user"],
  ["competitors", "Competitors", "users"],
  ["Create"],
  ["seo", "SEO studio", "seo"],
  ["titles", "Title lab", "type"],
  ["ai", "AI studio", "sparkles"],
  ["earnings", "Earnings", "dollar"],
  ["More"],
  ["saved", "Saved", "bookmark"],
  ["settings", "Settings", "settings"],
];

const plural = (n, word) => `${fmt.int(n)} ${word}${n === 1 ? "" : "s"}`;

// ---------- routing ----------
function parseHash() {
  const raw = location.hash.replace(/^#\/?/, "");
  const [path, query] = raw.split("?");
  return { path: path || "", params: Object.fromEntries(new URLSearchParams(query || "")) };
}
function go(path, params) {
  const qs = params ? new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "")).toString() : "";
  const target = "#/" + path + (qs ? "?" + qs : "");
  if (location.hash === target) render(); else location.hash = target;
}
const PAGES = {};
let mainEl, navEl, quotaEl, bannerEl;

function render() {
  const { path, params } = parseHash();
  const seq = ++state.renderSeq;
  hideTip();
  for (const a of navEl.querySelectorAll("a")) a.classList.toggle("active", a.dataset.path === path);
  document.querySelector(".sidebar").classList.remove("open");
  const page = PAGES[path] || PAGES[""];
  clear(mainEl);
  const title = NAV.find((n) => n.length > 1 && n[0] === path);
  document.title = (title && path ? title[1] + " · " : "") + "ShortsRadar";
  page(params, mainEl, () => seq === state.renderSeq);
  window.scrollTo(0, 0);
}

function isVideoRef(t) {
  return /youtu\.be\/|youtube\.com\/(watch|shorts|embed|live)/i.test(t) || (/^[A-Za-z0-9_-]{11}$/.test(t) && /[A-Z_-]/.test(t) && /[a-z]/.test(t));
}
function isChannelRef(t) {
  return /^@[\w.\-À-￿]{3,}$/.test(t) || /youtube\.com\/(channel\/|@|c\/|user\/)/i.test(t) || /^UC[A-Za-z0-9_-]{22}$/.test(t);
}
function routeSearch(text) {
  text = (text || "").trim();
  if (!text) return;
  if (isVideoRef(text)) go("video", { id: text });
  else if (isChannelRef(text)) go("channel", { id: text });
  else go("keywords", { q: text });
}

// ---------- shared UI pieces ----------
function pageHead(title, desc, actions) {
  return h("div", { class: "page-head" }, h("div", {}, h("h1", {}, title), desc ? h("p", {}, desc) : null),
    actions ? h("div", { class: "row" }, actions) : null);
}

let suggestSeq = 0;
function withSuggest(input) {
  const id = "dl-" + Math.random().toString(36).slice(2);
  const list = h("datalist", { id });
  input.setAttribute("list", id);
  input.setAttribute("autocomplete", "off");
  const run = debounce(async () => {
    const q = input.value.trim();
    if (q.length < 2 || isVideoRef(q) || isChannelRef(q)) return;
    const my = ++suggestSeq;
    try {
      const res = await api("/api/suggest", { params: { q } });
      if (my !== suggestSeq) return;
      clear(list);
      for (const sgt of res.suggestions) list.appendChild(h("option", { value: sgt }));
    } catch { /* ignore */ }
  }, 220);
  input.addEventListener("input", run);
  return h("span", { style: { display: "contents" } }, input, list);
}

async function saveItem(kind, ref, title, data) {
  try {
    await api("/api/saved", { method: "POST", body: { kind, ref, title, data } });
    toast("Saved");
  } catch (e) { toast(e.message, true); }
}

function scoreBadge(score) {
  if (score === null || score === undefined) return null;
  const cls = score >= 5 ? " hot" : score >= 2 ? " warm" : "";
  return h("span", { class: "score-badge" + cls, title: "Outlier score: views ÷ the channel's median views" },
    score >= 10 ? String(Math.round(score)) : Number(score).toFixed(1), h("small", {}, "×"));
}

function videoCard(v, opts = {}) {
  const ytUrl = v.url || `https://www.youtube.com/watch?v=${v.id}`;
  const statCells = [
    ["Views", fmt.compact(v.views)],
    [opts.vphLabel || "Views/hr", fmt.compact(v.vph_recent ?? v.vph)],
    ["Age", v.age_hours !== undefined && v.age_hours !== null ? fmt.hoursAge(v.age_hours) : v.age_days !== undefined && v.age_days !== null ? fmt.hoursAge(v.age_days * 24) : v.published ? fmt.ago(v.published) : "—"],
  ];
  return h("article", { class: "vcard" },
    h("a", { class: "thumb", href: `#/video?id=${encodeURIComponent(v.id)}`, title: "Open scorecard" },
      img(v.thumbnail || `https://i.ytimg.com/vi/${v.id}/hqdefault.jpg`, ""),
      h("span", { class: "badge-tl" }, opts.noScore ? null : scoreBadge(v.outlier_score)),
      v.duration ? h("span", { class: "badge-br" }, v.duration) : null),
    h("div", { class: "body" },
      h("a", { class: "title", href: `#/video?id=${encodeURIComponent(v.id)}`, title: v.title }, v.title),
      h("div", { class: "meta" },
        v.channel_id ? h("a", { href: `#/channel?id=${encodeURIComponent(v.channel_id)}` }, v.channel_title || "Channel") : h("span", {}, v.channel_title || ""),
        v.channel_subs !== undefined && v.channel_subs !== null ? h("span", {}, `${fmt.compact(v.channel_subs)} subs`) : null,
        v.chart_position ? h("span", {}, `#${v.chart_position} trending`) : null),
      h("div", { class: "stats" }, statCells.map(([k, val]) => h("div", {}, h("b", { class: "num" }, val), k))),
      h("div", { class: "foot" },
        h("div", { class: "pills" },
          formatPill(v.is_short ?? v.format === "short"),
          v.trending ? pill("Trending", "bad", "zap") : null,
          v.baseline_views ? h("span", { class: "pill", title: v.score_basis || "Channel's usual views" }, `usual ${fmt.compact(v.baseline_views)}`) : null),
        h("div", { class: "acts" },
          h("a", { class: "icon-btn", href: ytUrl, target: "_blank", rel: "noopener", title: "Open on YouTube" }, icon("external")),
          h("button", { class: "icon-btn", title: "Save", onClick: () => saveItem("video", v.id, v.title, v) }, icon("bookmark"))))));
}

function videoGrid(videos, opts) {
  if (!videos.length) return empty("No videos found", "Try a broader keyword, a longer time range or fewer filters.");
  return h("div", { class: "video-grid" }, videos.map((v) => videoCard(v, opts)));
}

async function runInto(container, alive, text, fn, renderFn) {
  clear(container).appendChild(loader(text));
  try {
    const data = await fn();
    if (!alive()) return;
    clear(container);
    renderFn(data, container);
  } catch (e) {
    if (!alive()) return;
    clear(container).appendChild(errorBox(e, go));
  }
}

function needsKeyNote(what) {
  return h("div", { class: "note warn" }, icon("alert"), h("div", {},
    `${what} needs a free YouTube Data API key. `, h("a", { href: "#/settings" }, "Add it in Settings"), " — it takes about 5 minutes."));
}

// ---------- pages ----------
PAGES[""] = async (params, main, alive) => {
  const st = state.status || {};
  main.appendChild(pageHead("Welcome to ShortsRadar", "Find what to make, how to package it, and what's working for your competitors — keyword research, outliers, scorecards and AI tools for YouTube Shorts and long-form."));
  const input = h("input", { type: "search", placeholder: "Keyword, video URL, or channel @handle", "aria-label": "Search" });
  const quick = card("Start researching", "Type a keyword, paste a video/Shorts link or a channel.",
    h("form", { class: "row", onSubmit: (e) => { e.preventDefault(); routeSearch(input.value); } },
      h("div", { class: "grow" }, withSuggest(input)), h("button", { class: "btn primary", type: "submit" }, icon("search"), "Go")),
    h("div", { style: { marginTop: "12px" } }, chips(["minecraft redstone", "easy dinner recipes", "ai tools", "gym motivation"], { onClick: (t) => go("keywords", { q: t }) })),
    h("div", { style: { marginTop: "16px" } }, notes([
      { type: "info", text: "The search bar at the top works everywhere: keywords open research, video links open a scorecard, @handles open a channel audit." },
      { type: "info", text: "Autocomplete, title/SEO scores, competitor tracking and templates are free. Only YouTube API lookups use your daily quota (shown at the top, and in Settings)." },
    ])));
  const setupItems = [
    [st.youtube_key, "YouTube Data API key", "Unlocks competition scores, outliers, scorecards and audits (free).", "settings"],
    [st.ai && st.ai.ready, "Claude API key (optional)", "AI titles, hooks and scripts. Templates and copy-prompts work without it.", "settings"],
    [st.competitors > 0, "Track competitors", "Free — uses channel RSS feeds, no quota.", "competitors"],
    [st.settings && st.settings.niche_keywords && st.settings.niche_keywords.length, "Set your niche keywords", "Powers Daily ideas.", "settings"],
  ];
  const setup = card("Setup", null, h("div", {}, setupItems.map(([done, t, d, path]) =>
    h("div", { class: "setup-item " + (done ? "done" : "todo") },
      h("div", { class: "dot" }, icon(done ? "check" : "plus")),
      h("div", { class: "grow" }, h("div", { style: { fontWeight: 600 } }, t), h("div", { class: "small muted" }, d)),
      done ? pill("Done", "good") : h("a", { class: "btn sm", href: "#/" + path }, "Set up")))));
  main.appendChild(h("div", { class: "grid-2" }, quick, setup));
  const lower = h("div", { class: "stack", style: { marginTop: "16px" } });
  main.appendChild(lower);
  const features = [
    ["keywords", "key", "Keyword research", "Volume, competition & overall score + related searches"],
    ["outliers", "zap", "Outliers", "Videos that got 5–100× their channel's normal views"],
    ["video", "video", "Video scorecard", "VPH, engagement, SEO audit & tags of any video"],
    ["channel", "user", "Channel audit", "Best times, formats, lengths & title patterns"],
    ["competitors", "users", "Competitors", "Track uploads & breakouts — free via RSS"],
    ["trending", "trending", "Trending", "What's blowing up now, by views per hour"],
    ["seo", "seo", "SEO studio", "Score your title, description & tags before upload"],
    ["ai", "sparkles", "AI studio", "Hooks, Shorts scripts, titles & descriptions"],
  ];
  lower.appendChild(h("div", { class: "feature-grid" }, features.map(([path, ic, t, d]) =>
    h("a", { class: "feature", href: "#/" + path }, h("div", { class: "fi" }, icon(ic)), h("div", {}, h("b", {}, t), h("span", {}, d))))));
  try {
    const [comp, hist] = await Promise.all([api("/api/competitors"), api("/api/history")]);
    if (!alive()) return;
    if (comp.alerts.length) {
      lower.appendChild(card("Competitor alerts", "Uploads beating their channel's usual views", notes(comp.alerts.map((a) => ({ type: "good", text: a.text })))));
    }
    if (hist.items.length) {
      lower.appendChild(card("Recent research", null, dataTable(hist.items, [
        { key: "kind", label: "Type", render: (r) => pill(r.kind) },
        { key: "query", label: "Query", render: (r) => h("a", { href: r.kind === "keyword" ? `#/keywords?q=${encodeURIComponent(r.query)}` :
          r.kind === "channel" ? `#/channel?id=${encodeURIComponent((r.summary && r.summary.id) || r.query)}` :
            `#/video?id=${encodeURIComponent((r.summary && r.summary.id) || r.query)}` }, r.query) },
        { key: "summary", label: "Result", render: (r) => r.kind === "keyword" && r.summary ? `Overall ${fmt.score(r.summary.overall)} · Volume ${fmt.score(r.summary.volume)} · Competition ${fmt.score(r.summary.competition)}` :
          r.summary && r.summary.subs !== undefined ? `${fmt.compact(r.summary.subs)} subscribers` : "" },
        { key: "ts", label: "When", align: "r", render: (r) => fmt.ago(r.ts) },
      ])));
    }
  } catch { /* home extras are optional */ }
};

// --- keyword research
PAGES.keywords = (params, main, alive) => {
  main.appendChild(pageHead("Keyword research", "Search volume, competition and an overall opportunity score (0–100) for any YouTube search, plus long-tail variations, questions and what's ranking."));
  const q = h("input", { type: "search", value: params.q || "", placeholder: "e.g. minecraft redstone", "aria-label": "Keyword" });
  const fmtSel = select(FORMATS.slice().reverse(), params.format || "any");
  const regionSel = select(REGIONS, params.region || (state.status && state.status.settings.region) || "US");
  const deep = h("input", { type: "checkbox", checked: params.deep !== "0" });
  main.appendChild(h("form", { class: "filters", onSubmit: (e) => { e.preventDefault(); go("keywords", { q: q.value.trim(), format: fmtSel.value, region: regionSel.value, deep: deep.checked ? "" : "0" }); } },
    field("Keyword", withSuggest(q), null, "grow"), field("Format", fmtSel), field("Region", regionSel),
    h("label", { class: "check", style: { paddingBottom: "9px" } }, deep, "Deep scan"),
    h("button", { class: "btn primary", type: "submit" }, icon("search"), "Research")));
  const out = h("div", { class: "stack" });
  main.appendChild(out);
  if (!params.q) {
    out.appendChild(empty("Research any YouTube search", "We estimate volume from YouTube autocomplete (free) and competition from the ranking videos (needs a YouTube API key).", "key"));
    return;
  }
  runInto(out, alive, `Researching “${params.q}”… checking YouTube autocomplete${state.status && state.status.youtube_key ? " and the top search results" : ""}.`,
    () => api("/api/keyword", { params: { q: params.q, format: params.format, region: params.region, deep: params.deep } }),
    (r, box) => renderKeyword(r, box));
};

function renderKeyword(r, box) {
  const s = r.scores;
  const ov = overallLabel(s.overall);
  const sv = r.search_volume;
  const tilesRow = h("div", { class: "tiles" },
    tile("Overall score", fmt.score(s.overall), s.overall === null ? "Add a YouTube API key to score competition" : "Volume vs competition",
      { hero: true, meter: s.overall ?? 0, extra: s.overall !== null ? h("div", { style: { marginTop: "8px" } }, pill(ov.text, ov.cls, ov.icon)) : null }),
    tile("Search volume", fmt.score(s.volume), `${band(s.volume)} · ~${fmt.compact(sv.monthly_estimate)} searches/mo`, { meter: s.volume ?? 0, title: "Estimated from YouTube autocomplete" + (s.demand !== null ? " and views/day of ranking videos" : "") }),
    tile("Competition", fmt.score(s.competition), s.competition === null ? "Needs a YouTube API key" : `${band(s.competition)} · lower is easier`, { meter: s.competition ?? 0 }),
    r.insights ? tile("Trend", r.insights.trend === "rising" ? "Rising" : r.insights.trend === "evergreen" ? "Evergreen" : r.insights.trend === "steady" ? "Steady" : "—",
      r.insights.fresh_share !== null ? `${fmt.pct(r.insights.fresh_share, 0)} of top results < 30 days old` : "", {}) : null,
    r.insights ? tile("Shorts in results", fmt.pct(r.insights.shorts_share, 0), "of the top 20 results", {}) : null);
  box.appendChild(h("div", { class: "row", style: { justifyContent: "space-between", alignItems: "center" } },
    h("h2", {}, "“", r.keyword, "”"),
    h("div", { class: "row", style: { gap: "6px" } },
      h("button", { class: "btn sm", onClick: () => saveItem("keyword", r.keyword, r.keyword, { scores: r.scores }) }, icon("bookmark"), "Save"),
      h("a", { class: "btn sm", href: `#/outliers?q=${encodeURIComponent(r.keyword)}` }, icon("zap"), "Outliers"),
      h("a", { class: "btn sm", href: `#/titles?q=${encodeURIComponent(r.keyword)}` }, icon("type"), "Titles"),
      h("a", { class: "btn sm", href: `#/ai?task=script&keyword=${encodeURIComponent(r.keyword)}&topic=${encodeURIComponent(r.keyword)}` }, icon("sparkles"), "Script"))));
  box.appendChild(tilesRow);
  if (!r.api_used) box.appendChild(needsKeyNote("Competition scoring and top-video analysis"));
  if (r.api_error) box.appendChild(errorBox({ message: "YouTube API: " + r.api_error }, go));
  if (r.insights && r.insights.notes.length) box.appendChild(card("What the search results tell us", null, notes(r.insights.notes)));

  const kwTable = (rows) => rows.length ? dataTable(rows, [
    { key: "keyword", label: "Keyword", render: (x) => h("a", { class: "kw", href: `#/keywords?q=${encodeURIComponent(x.keyword)}` }, x.keyword), sort: (x) => x.keyword },
    { key: "volume", label: "Volume", render: (x) => miniMeter(x.volume, x.approx), sort: (x) => x.volume },
    { key: "competition", label: "Competition", render: (x) => x.competition === null ? h("span", { class: "muted" }, "—") : miniMeter(x.competition, true), sort: (x) => x.competition },
    { key: "overall", label: "Overall", render: (x) => x.overall === null ? h("span", { class: "muted" }, "—") : miniMeter(x.overall, true), sort: (x) => x.overall },
    { key: "monthly", label: "~Searches/mo", align: "r", render: (x) => fmt.compact(x.monthly), sort: (x) => x.monthly },
    { key: "a", label: "", cls: "actions", render: (x) => h("span", {},
      h("button", { class: "icon-btn", title: "Copy", onClick: () => copyText(x.keyword) }, icon("copy")),
      h("button", { class: "icon-btn", title: "Save", onClick: () => saveItem("keyword", x.keyword, x.keyword, x) }, icon("bookmark"))) },
  ], { sortKey: "overall" }) : empty("Nothing here", "Autocomplete returned no variations for this group.");
  box.appendChild(card("Keyword ideas", "Competition for ideas is estimated from the seed's search results (~); click a keyword for a full analysis.",
    tabs([
      { id: "matching", label: "Long-tail", count: r.matching.length, render: () => kwTable(r.matching) },
      { id: "questions", label: "Questions", count: r.questions.length, render: () => kwTable(r.questions) },
      { id: "related", label: "Related", count: r.related.length, render: () => kwTable(r.related) },
    ])));

  if (r.top_videos.length) {
    const rankCols = [
      { key: "rank", label: "#", render: (v) => v.rank, sort: (v) => -v.rank },
      { key: "thumb", label: "", cls: "thumb-cell", render: (v) => h("a", { href: `#/video?id=${v.id}` }, img(v.thumbnail, "")) },
      { key: "title", label: "Video", render: (v) => h("div", {}, h("a", { href: `#/video?id=${v.id}`, style: { fontWeight: 600 } }, v.title),
        h("div", { class: "small muted" }, v.channel_title, v.channel_subs !== null ? ` · ${fmt.compact(v.channel_subs)} subs` : "")) },
      { key: "views", label: "Views", align: "r", render: (v) => fmt.compact(v.views), sort: (v) => v.views },
      { key: "vph", label: "Views/hr", align: "r", render: (v) => fmt.compact(v.vph), sort: (v) => v.vph },
      { key: "age", label: "Age", align: "r", render: (v) => fmt.hoursAge((v.age_days || 0) * 24), sort: (v) => -v.age_days },
      { key: "fmt", label: "Format", render: (v) => formatPill(v.is_short) },
      { key: "kw", label: "Exact kw in title", render: (v) => v.keyword_in_title ? pill("Yes", "good", "good") : pill("No") },
    ];
    const holder = h("div", {}, dataTable(r.top_videos.slice(0, 10), rankCols));
    const more = r.top_videos.length > 10 ? h("button", { class: "btn sm", onClick: () => { clear(holder).appendChild(dataTable(r.top_videos, rankCols)); more.remove(); } }, `Show all ${r.top_videos.length}`) : null;
    box.appendChild(cardWithActions("Top ranking videos", `What YouTube shows for “${r.keyword}” right now`, more, holder));
  }
  if (r.common_tags.length || r.title_phrases.length) {
    box.appendChild(h("div", { class: "grid-2" },
      cardWithActions("Tags the top videos use", "Tags used by 2+ ranking videos", r.common_tags.length ? copyBtn(() => r.common_tags.map((t) => t.tag).join(", "), "tags", "Copy all") : null,
        r.common_tags.length ? chips(r.common_tags.map((t) => ({ text: t.tag, count: t.count })), { onClick: (t) => go("keywords", { q: t }) }) : h("div", { class: "muted" }, "Top videos don't share tags.")),
      card("Common phrases in top titles", null,
        r.title_phrases.length ? chips(r.title_phrases.map((p) => ({ text: p.phrase, count: p.count })), { onClick: (t) => go("keywords", { q: t }) }) : h("div", { class: "muted" }, "No repeated phrases."))));
  }
  box.appendChild(h("details", { class: "card more" }, h("summary", {}, "How these scores are calculated"),
    h("div", { class: "stack-sm small ink2" },
      h("p", {}, "Search volume: we walk YouTube's autocomplete prefix by prefix. Popular searches appear after typing a letter or two; niche ones only when typed almost completely. The chain of suggestion ranks gives an estimated monthly search count", s.demand !== null ? ", blended 75/25 with how many views per day the ranking videos get." : "."),
      h("ul", {}, sv.path.map((p) => h("li", {}, p))),
      h("p", {}, "Competition: share of the top 20 results that explicitly target the phrase (titles/tags), the size of the ranking channels, the views of the top 10 and how many come from 1M+ channels."),
      h("p", {}, "Overall: a weighted geometric blend of volume and (100 − competition) — high only when people search it AND you can realistically rank."),
      h("p", { class: "muted" }, `Quota used: ${r.quota_units} units · autocomplete lookups: ${r.autocomplete_requests} · ${r.elapsed_s}s`))));
}

// --- outliers
PAGES.outliers = (params, main, alive) => {
  if (params.min_score === undefined) params.min_score = "1.5";
  main.appendChild(pageHead("Outlier finder", "Videos that got far more views than their channel normally gets — proof the idea and packaging worked, not just the channel size."));
  const q = h("input", { type: "search", value: params.q || "", placeholder: "Niche or topic, e.g. cooking hacks", "aria-label": "Keyword" });
  const fmtSel = select(FORMATS, params.format || "short");
  const within = select([["week", "Past week"], ["month", "Past month"], ["3months", "Past 3 months"], ["6months", "Past 6 months"], ["year", "Past year"], ["all", "All time"]], params.within || "month");
  const minScore = select([["0", "Any"], ["1.5", "1.5×+"], ["2", "2×+"], ["3", "3×+"], ["5", "5×+"], ["10", "10×+"]], params.min_score);
  const maxSubs = select([["", "Any size"], ["1000", "< 1K subs"], ["10000", "< 10K subs"], ["100000", "< 100K subs"], ["1000000", "< 1M subs"]], params.max_subs || "");
  const sort = select([["score", "Outlier score"], ["views", "Views"], ["vph", "Views/hour"], ["recent", "Newest"], ["engagement", "Engagement"]], params.sort || "score");
  const deep = h("input", { type: "checkbox", checked: params.deep === "1" });
  const chans = h("input", { type: "text", value: params.channels || "", placeholder: "@channel1, @channel2 (optional)" });
  main.appendChild(h("form", { class: "filters", onSubmit: (e) => {
    e.preventDefault();
    go("outliers", { q: q.value.trim(), format: fmtSel.value, within: within.value, min_score: minScore.value, max_subs: maxSubs.value, sort: sort.value, deep: deep.checked ? "1" : "", channels: chans.value.trim() });
  } },
  field("Keyword / niche", withSuggest(q), null, "grow"), field("Format", fmtSel), field("Published", within), field("Min score", minScore),
  field("Channel size", maxSubs), field("Sort by", sort), field("Or scan channels", chans, null, "grow"),
  h("label", { class: "check", title: "3 searches instead of 1 (300 quota units)", style: { paddingBottom: "9px" } }, deep, "Deep scan"),
  h("button", { class: "btn primary", type: "submit" }, icon("zap"), "Find outliers")));
  const out = h("div", { class: "stack" });
  main.appendChild(out);
  if (!state.status.youtube_key) out.appendChild(needsKeyNote("The outlier finder"));
  if (!params.q && !params.channels) {
    out.appendChild(empty("Find breakout videos", "Enter your niche to see which videos massively outperformed their channel. Remake the idea with your own twist.", "zap"));
    return;
  }
  runInto(out, alive, "Scanning videos and comparing each one with its channel's usual views…",
    () => api("/api/outliers", { params }), (r, box) => {
      const sm = r.summary;
      box.appendChild(h("div", { class: "tiles" },
        tile("Videos found", fmt.int(sm.count), `from ${r.scanned} scanned`),
        tile("Strong outliers", fmt.int(sm.strong_outliers), "2× their channel's median or more"),
        tile("Small-channel hits", fmt.int(sm.small_channel_hits), "strong outliers from < 10K-sub channels"),
        tile("Median score", sm.median_score !== null ? fmt.x(sm.median_score) : "—", `quota used: ${r.quota_units} units`)));
      if (sm.title_phrases.length || sm.durations.length) {
        box.appendChild(h("div", { class: "grid-2" },
          card("What's working", "Phrases that repeat across the outliers", sm.title_phrases.length ? chips(sm.title_phrases.map((p) => ({ text: p.phrase, count: p.count })), { onClick: (t) => go("keywords", { q: t }) }) : h("div", { class: "muted" }, "No repeated phrases.")),
          card("Best-performing lengths", "Median outlier score by video length", sm.durations.length ? barList(sm.durations.map((d) => ({ label: d.bucket, sub: plural(d.count, "video"), value: d.median_score })), { fmt: fmt.x }) : h("div", { class: "muted" }, "Not enough data."))));
      }
      box.appendChild(videoGrid(r.results));
    });
};

// --- video scorecard
PAGES.video = (params, main, alive) => {
  main.appendChild(pageHead("Video scorecard", "Views per hour, engagement, outlier score, SEO audit and tags for any video or Short."));
  const q = h("input", { type: "search", value: params.id || "", placeholder: "Paste a YouTube or Shorts URL", "aria-label": "Video URL" });
  const kw = h("input", { type: "text", value: params.keyword || "", placeholder: "optional — auto-detected" });
  main.appendChild(h("form", { class: "filters", onSubmit: (e) => { e.preventDefault(); go("video", { id: q.value.trim(), keyword: kw.value.trim() }); } },
    field("Video URL or ID", q, null, "grow"), field("Target keyword", kw), h("button", { class: "btn primary", type: "submit" }, icon("video"), "Analyze")));
  const out = h("div", { class: "stack" });
  main.appendChild(out);
  if (!params.id) { out.appendChild(empty("Analyze any video", "Paste a link to see its stats, what's working and what to fix.", "video")); return; }
  runInto(out, alive, "Loading video stats…", () => api("/api/video", { params: { id: params.id, keyword: params.keyword } }), (r, box) => renderVideo(r, box));
};

function renderVideo(r, box) {
  const v = r.video, st = r.stats || {}, ch = r.channel || {};
  if (r.note) box.appendChild(h("div", { class: "note warn" }, icon("alert"), h("div", {}, r.note, " ", h("a", { href: "#/settings" }, "Open settings"))));
  const tagsText = (v.tags || []).join(", ");
  box.appendChild(h("section", { class: "card vid-head" },
    h("a", { href: v.url, target: "_blank", rel: "noopener" }, img(v.thumbnail, v.title)),
    h("div", {},
      h("div", { class: "t" }, v.title),
      h("div", { class: "meta" },
        ch.id ? h("a", { href: `#/channel?id=${encodeURIComponent(ch.id)}` }, ch.title || v.channel_title) : h("span", {}, v.channel_title),
        ch.subs !== undefined && ch.subs !== null ? h("span", {}, `${fmt.compact(ch.subs)} subscribers`) : null,
        v.published_at ? h("span", {}, `Published ${fmt.date(v.published_at)} (${fmt.ago(v.published_at)})`) : null,
        v.duration ? h("span", {}, v.duration) : null),
      h("div", { class: "row", style: { gap: "6px" } },
        formatPill(v.is_short),
        h("a", { class: "btn sm", href: v.url, target: "_blank", rel: "noopener" }, icon("external"), "YouTube"),
        v.tags && v.tags.length ? copyBtn(tagsText, "tags", "Copy tags") : null,
        h("button", { class: "btn sm", onClick: () => saveItem("video", v.id, v.title, { title: v.title }) }, icon("bookmark"), "Save"),
        ch.id ? h("button", { class: "btn sm", onClick: () => trackCompetitor(ch.id) }, icon("users"), "Track channel") : null))));
  const o = r.outlier;
  box.appendChild(h("div", { class: "tiles" },
    tile("Views", fmt.compact(st.views), st.views_per_sub !== null && st.views_per_sub !== undefined ? `${fmt.int(st.views)} · ${fmt.x(st.views_per_sub)} subscribers` : st.views !== null && st.views !== undefined ? fmt.int(st.views) : "",
      { title: "Views per subscriber shows reach beyond the channel's subscriber base" }),
    tile("Views / hour", fmt.compact(st.vph_recent ?? st.vph_lifetime), st.vph_recent !== null && st.vph_recent !== undefined ? `last ${Math.round(st.vph_recent_window_h || 0)}h (tracked) · lifetime ${fmt.compact(st.vph_lifetime)}` : "lifetime average"),
    tile("Outlier score", o ? fmt.x(o.score) : "—", o ? `vs usual ${fmt.compact(o.baseline_views)} views` : "not enough channel data", { title: o ? o.basis : "" }),
    tile("Engagement", fmt.pct(st.engagement_rate), "likes + comments per view"),
    tile("Likes", fmt.compact(st.likes), st.like_rate !== null && st.like_rate !== undefined ? `${fmt.pct(st.like_rate, 2)} of views` : ""),
    tile("Comments", fmt.compact(st.comments), st.comment_rate !== null && st.comment_rate !== undefined ? `${fmt.pct(st.comment_rate, 2)} of views` : "")));
  const seo = r.seo, ts = r.title_score;
  box.appendChild(h("div", { class: "grid-2" },
    card("SEO audit", seo.keyword ? `Target keyword: “${seo.keyword}”${seo.keyword_detected ? " (auto-detected)" : ""}` : "No keyword detected",
      h("div", { class: "score-head" }, scoreRing(seo.score, "SEO score"), h("div", {}, h("span", { class: "grade " + seo.grade }, "Grade " + seo.grade),
        h("div", { class: "small muted", style: { marginTop: "6px" } }, `${seo.checks.filter((c) => c.status === "pass").length} of ${seo.checks.length} checks passed`))),
      checklist(seo.checks)),
    card("Title click potential", "Heuristic CTR score — see what helps and hurts",
      h("div", { class: "score-head" }, scoreRing(ts.score, "Title score"), h("div", {}, h("span", { class: "grade " + ts.grade }, "Grade " + ts.grade),
        h("div", { style: { marginTop: "6px" } }, h("a", { class: "btn sm", href: `#/titles?q=${encodeURIComponent(seo.keyword || "")}&t=${encodeURIComponent(v.title)}` }, icon("type"), "Improve in Title lab")))),
      signalsList(ts))));
  const tagBox = h("div", { class: "stack-sm" });
  if (v.tags && v.tags.length) {
    tagBox.appendChild(chips(v.tags, { onClick: (t) => go("keywords", { q: t }) }));
    if (r.mode === "api") {
      const rankOut = h("div", {});
      tagBox.appendChild(h("div", { class: "row", style: { alignItems: "center" } },
        h("button", { class: "btn sm", onClick: async (e) => {
          if (!confirm("Check where this video ranks for its first 3 tags? This costs 100 quota units per tag.")) return;
          e.target.disabled = true;
          clear(rankOut).appendChild(loader("Searching YouTube for each tag…"));
          try {
            const res = await api("/api/video/tag-ranks", { method: "POST", body: { id: v.id, tags: v.tags.slice(0, 3) } });
            clear(rankOut).appendChild(barList(res.ranks.map((x) => ({ label: x.tag, value: x.rank ? 51 - x.rank : 0, sub: x.rank ? `rank #${x.rank}` : `not in top ${x.searched}` })), { fmt: () => "" }));
          } catch (err) { clear(rankOut).appendChild(errorBox(err, go)); }
        } }, icon("search"), "Check tag rankings"), h("span", { class: "small muted" }, "100 quota units per tag")), rankOut);
    }
  } else {
    tagBox.appendChild(h("div", { class: "muted" }, r.mode === "api" ? "This video has no tags." : "Tags need a YouTube API key."));
  }
  box.appendChild(h("div", { class: "grid-2" },
    cardWithActions("Tags", `${(v.tags || []).length} tag${(v.tags || []).length === 1 ? "" : "s"}`, v.tags && v.tags.length ? copyBtn(tagsText, "tags") : null, tagBox),
    card("Description", null, v.description ? h("div", { class: "desc" }, v.description) : h("div", { class: "muted" }, "No description."))));
  const lower = [];
  if (r.earnings) {
    const e = r.earnings;
    lower.push(card("Estimated earnings", `${e.category} · ${e.country} audience · ${v.is_short ? "Shorts" : "long-form"} RPM ${fmt.money(e.rpm.low)}–${fmt.money(e.rpm.high)}`,
      h("div", { class: "tiles" }, tile("Low", fmt.money(e.earnings.low)), tile("Likely", fmt.money(e.earnings.mid)), tile("High", fmt.money(e.earnings.high))),
      h("p", { class: "small muted", style: { marginTop: "10px" } }, e.note)));
  }
  if (r.history && r.history.length >= 2) {
    lower.push(card("Views over time", "Tracked each time ShortsRadar loads this video",
      lineChart(r.history.filter((p) => p.views !== null).map((p) => ({ t: p.ts * 1000, v: p.views })), { name: "Views", label: "Views over time" })));
  }
  if (lower.length) box.appendChild(h("div", { class: "grid-2" }, lower));
}

function checklist(checks) {
  return h("div", { class: "checklist" }, checks.map((c) => h("div", { class: "check-item " + c.status },
    h("div", { class: "ic", title: c.status }, icon(c.status === "pass" ? "good" : c.status === "warn" ? "warn" : "bad")),
    h("div", {}, h("div", { class: "t" }, c.label, h("span", { class: "sr-only" }, ` (${c.status})`)), h("div", { class: "d" }, c.detail),
      c.tip ? h("div", { class: "tip" }, c.tip) : null))));
}

function signalsList(ts) {
  return h("div", { class: "stack-sm" },
    h("div", { class: "checklist" }, ts.signals.map((sg) => h("div", { class: "check-item " + (sg.points > 0 ? "pass" : sg.points < 0 ? "fail" : "warn") },
      h("div", { class: "ic" }, icon(sg.points > 0 ? "good" : sg.points < 0 ? "bad" : "warn")),
      h("div", {}, h("div", { class: "t" }, `${sg.points > 0 ? "+" : ""}${sg.points}  ${sg.label}`), sg.detail ? h("div", { class: "d" }, sg.detail) : null)))),
    ts.suggestions.length ? notes(ts.suggestions.map((t) => ({ type: "info", text: t }))) : null);
}

async function trackCompetitor(ref) {
  try {
    const c = await api("/api/competitors", { method: "POST", body: { ref } });
    toast(`Tracking ${c.title}`);
  } catch (e) { toast(e.message, true); }
}

// --- channel audit
PAGES.channel = (params, main, alive) => {
  main.appendChild(pageHead("Channel audit", "How any channel performs: Shorts vs long-form, upload cadence, best posting times, best lengths, winning title words and what to do next."));
  const q = h("input", { type: "search", value: params.id || "", placeholder: "@handle, channel URL or ID", "aria-label": "Channel" });
  const max = select([["50", "Last 50 uploads"], ["100", "Last 100 uploads"], ["200", "Last 200 uploads"]], params.max || "100");
  main.appendChild(h("form", { class: "filters", onSubmit: (e) => { e.preventDefault(); go("channel", { id: q.value.trim(), max: max.value }); } },
    field("Channel", q, null, "grow"), field("Analyze", max), h("button", { class: "btn primary", type: "submit" }, icon("user"), "Audit")));
  const out = h("div", { class: "stack" });
  main.appendChild(out);
  if (!state.status.youtube_key) out.appendChild(needsKeyNote("The channel audit"));
  if (!params.id) { out.appendChild(empty("Audit your channel or a competitor", "Paste your own channel to get a personalised plan.", "user")); return; }
  runInto(out, alive, "Analyzing uploads…", () => api("/api/channel", { params: { id: params.id, max: params.max } }), (r, box) => renderChannel(r, box));
};

function renderChannel(r, box) {
  const ch = r.channel, f = r.formats, c = r.cadence;
  box.appendChild(h("section", { class: "card" }, h("div", { class: "ch-head" },
    avatar(ch.thumbnail, ch.title),
    h("div", { style: { flex: "1", minWidth: "200px" } },
      h("div", { style: { fontSize: "19px", fontWeight: 650 } }, ch.title),
      h("div", { class: "small ink2" }, [ch.handle, ch.country, ch.age_years ? `${ch.age_years} years old` : null].filter(Boolean).join(" · ")),
      h("div", { class: "small muted" }, `${fmt.compact(ch.subs)} subscribers · ${fmt.compact(ch.views)} views · ${plural(ch.video_count, "video")}`)),
    h("div", { class: "row", style: { gap: "6px" } },
      h("button", { class: "btn sm", onClick: () => trackCompetitor(ch.id) }, icon("users"), "Track as competitor"),
      h("a", { class: "btn sm", href: `#/outliers?channels=${encodeURIComponent(ch.id)}&format=any&within=all` }, icon("zap"), "Outliers"),
      h("a", { class: "btn sm", href: ch.url, target: "_blank", rel: "noopener" }, icon("external"), "YouTube")))));
  const e = r.earnings;
  box.appendChild(h("div", { class: "tiles" },
    tile("Uploads / week", String(c.per_week_90d), `last 90 days · ${c.uploads_last_30d} in 30 days`),
    tile("Median Shorts views", fmt.compact(f.short.median_views), `${plural(f.short.count, "Short")} analyzed`),
    tile("Median long-form views", fmt.compact(f.long.median_views), `${plural(f.long.count, "video")} analyzed`),
    tile("Consistency", c.consistency !== null ? `${c.consistency}` : "—", "upload rhythm, 0–100", { meter: c.consistency ?? 0 }),
    tile("Last upload", c.days_since_last_upload !== null ? `${Math.round(c.days_since_last_upload)}d` : "—", "days ago"),
    tile("Est. monthly earnings", `${fmt.moneyShort(e.earnings.low)}–${fmt.moneyShort(e.earnings.high)}`, e.monetization_likely ? "if monetized" : "likely not monetized yet (< 1K subs)", { title: e.basis })));
  if (r.recommendations.length) box.appendChild(card("Recommendations", "Based on this channel's own data", notes(r.recommendations)));
  const chrono = r.videos.slice().reverse();
  box.appendChild(card("Views per upload", `Last ${chrono.length} uploads, oldest → newest`,
    columnChart(chrono.map((v) => ({
      label: v.title, value: v.views || 0, short: fmt.date(v.published_at).replace(/,? \d{4}$/, ""),
      color: v.format === "short" ? "var(--series-1)" : "var(--series-2)",
      tip: [h("div", { class: "v" }, fmt.int(v.views) + " views"), h("div", { class: "k" }, v.title),
        h("div", { class: "k" }, `${v.format === "short" ? "Short" : "Long-form"} · ${fmt.date(v.published_at)} · ${fmt.x(v.outlier_score)} usual`)],
    })), { height: 240, legend: [{ label: "Shorts", color: "var(--series-1)" }, { label: "Long-form", color: "var(--series-2)" }],
    xName: "Upload", yName: "Views", label: "Views per upload", onClick: (d) => { const v = chrono.find((x) => x.title === d.label); if (v) go("video", { id: v.id }); } })));
  const p = r.posting;
  box.appendChild(h("div", { class: "grid-3" },
    card("Uploads per week", "Last 12 weeks", columnChart(c.weekly.map((w) => ({ label: `Week of ${w.week_start}`, short: w.week_start.slice(5), value: w.uploads })),
      { height: 170, yFmt: (v) => String(Math.round(v * 10) / 10), xName: "Week", yName: "Uploads" })),
    card("Best day to post", `Median outlier score (line = usual, 1×) · ${p.timezone}`, columnChart(p.days.map((d) => ({ label: d.day, short: d.day, value: d.median_score || 0,
      tip: [h("div", { class: "v" }, d.median_score !== null ? fmt.x(d.median_score) : "no uploads"), h("div", { class: "k" }, `${d.day} · ${plural(d.count, "upload")}`)] })),
    { height: 170, yFmt: (v) => v.toFixed(1) + "×", xName: "Day", yName: "Median score", refLine: 1 })),
    card("Best time window", `Median outlier score (line = usual, 1×) · ${p.timezone}`, columnChart(p.windows.map((w) => ({ label: w.window, short: w.window.slice(0, 2), value: w.median_score || 0,
      tip: [h("div", { class: "v" }, w.median_score !== null ? fmt.x(w.median_score) : "no uploads"), h("div", { class: "k" }, `${w.window} · ${plural(w.count, "upload")}`)] })),
    { height: 170, yFmt: (v) => v.toFixed(1) + "×", xName: "Window", yName: "Median score", refLine: 1 }))));
  const durCards = [];
  for (const [key, label] of [["short", "Shorts length"], ["long", "Long-form length"]]) {
    if (r.durations[key].length) durCards.push(card(label, "Median outlier score by length", barList(r.durations[key].map((d) => ({ label: d.bucket, sub: plural(d.count, "upload"), value: d.median_score })), { fmt: fmt.x })));
  }
  const t = r.titles;
  const words = card("Title words that win", "Median score of titles containing the word vs the channel's median",
    t.top_words.length ? barList(t.top_words.slice(0, 8).map((w) => ({ label: w.word, sub: plural(w.count, "title"), value: w.lift })), { fmt: fmt.x }) : h("div", { class: "muted" }, "Not enough titles yet."));
  const feats = card("Title features", "Lift = median score with the feature ÷ without",
    t.features.length ? barList(t.features.map((x) => ({ label: x.feature, sub: `${x.with} vs ${x.without}`, value: x.lift })), { fmt: fmt.x }) : h("div", { class: "muted" }, "Not enough titles yet."));
  box.appendChild(h("div", { class: "grid-2" }, ...durCards, words, feats));
  const vt = (rows) => dataTable(rows, [
    { key: "thumb", label: "", cls: "thumb-cell", render: (v) => h("a", { href: `#/video?id=${v.id}` }, img(v.thumbnail, "")) },
    { key: "title", label: "Video", render: (v) => h("div", {}, h("a", { href: `#/video?id=${v.id}`, style: { fontWeight: 600 } }, v.title),
      h("div", { class: "small muted" }, `${v.format === "short" ? "Short" : "Long-form"} · ${fmt.ago(v.published_at)}`)) },
    { key: "score", label: "Score", align: "r", render: (v) => fmt.x(v.outlier_score), sort: (v) => v.outlier_score },
    { key: "views", label: "Views", align: "r", render: (v) => fmt.compact(v.views), sort: (v) => v.views },
  ], { cls: "fit" });
  box.appendChild(h("div", { class: "grid-2" },
    card("Biggest hits", "Highest outlier scores — make more like these", vt(r.top_videos)),
    card("Underperformers", "Lowest outlier scores — what to avoid", vt(r.bottom_videos))));
  const m = r.metadata;
  box.appendChild(card("Metadata habits", null, h("dl", { class: "kv" },
    h("dt", {}, "Average tags per upload"), h("dd", {}, String(m.avg_tags)),
    h("dt", {}, "Uploads without tags"), h("dd", {}, fmt.pct(m.no_tags_share, 0)),
    h("dt", {}, "Median description length"), h("dd", {}, `${fmt.int(m.median_description_chars)} characters`)),
  m.top_tags.length ? h("div", { style: { marginTop: "12px" } }, chips(m.top_tags.map((x) => ({ text: x.tag, count: x.count })), { onClick: (x) => go("keywords", { q: x }) })) : null,
  h("p", { class: "small muted", style: { marginTop: "10px" } }, `Quota used: ${r.quota_units} units · ${r.elapsed_s}s`)));
}

// --- competitors
PAGES.competitors = async (params, main, alive) => {
  main.appendChild(pageHead("Competitors", "Track channels in your niche. New uploads, views and breakout videos are checked through free RSS feeds — no API quota needed."));
  const ref = h("input", { type: "text", placeholder: "@handle, channel URL or ID", "aria-label": "Channel to track" });
  const addForm = h("form", { class: "filters", onSubmit: async (e) => {
    e.preventDefault();
    if (!ref.value.trim()) return;
    const btn = addForm.querySelector("button[type=submit]");
    btn.disabled = true;
    try { const c = await api("/api/competitors", { method: "POST", body: { ref: ref.value.trim() } }); toast(`Tracking ${c.title}`); ref.value = ""; load(); }
    catch (err) { toast(err.message, true); }
    finally { btn.disabled = false; }
  } }, field("Add a channel", ref, null, "grow"), h("button", { class: "btn primary", type: "submit" }, icon("plus"), "Track"),
  h("button", { class: "btn", type: "button", onClick: async () => {
    toast("Refreshing feeds…");
    try { const r = await api("/api/competitors/refresh", { method: "POST" }); toast(`Refreshed ${r.refreshed} channels${r.errors.length ? ` (${r.errors.length} errors)` : ""}`); load(); }
    catch (err) { toast(err.message, true); }
  } }, icon("refresh"), "Refresh now"));
  main.appendChild(addForm);
  const out = h("div", { class: "stack" });
  main.appendChild(out);
  let feedFmt = "any", feedSort = "score";
  const load = async () => {
    const hadContent = out.children.length > 0;
    if (hadContent) out.classList.add("dim"); else out.appendChild(loader("Loading competitors…"));
    try {
      const [data, feed] = await Promise.all([api("/api/competitors"), api("/api/competitors/feed", { params: { format: feedFmt, sort: feedSort, days: 14 } })]);
      if (!alive()) return;
      out.classList.remove("dim");
      clear(out);
      if (!data.competitors.length) {
        out.appendChild(empty("No competitors yet", "Add 3–10 channels in your niche. Views are re-checked every hour while ShortsRadar is running, which gives you real views-per-hour.", "users"));
        return;
      }
      if (data.alerts.length) out.appendChild(card("Breakout alerts", "Uploads from the last 7 days with 2×+ their channel's usual views", notes(data.alerts.map((a) => ({ type: "good", text: a.text })))));
      out.appendChild(card("Tracked channels", `${data.competitors.length} channels · auto-refresh every ${state.status.settings.auto_refresh_minutes || "—"} min while running`, dataTable(data.competitors, [
        { key: "title", label: "Channel", render: (c) => h("div", { class: "row", style: { gap: "10px", alignItems: "center", flexWrap: "nowrap" } }, avatar(c.thumbnail, c.title, true),
          h("div", {}, h("a", { href: `#/channel?id=${c.channel_id}`, style: { fontWeight: 600 } }, c.title), h("div", { class: "small muted" }, c.last_error ? "⚠ " + c.last_error : `updated ${fmt.ago(c.last_refresh)}`))), sort: (c) => c.title },
        { key: "subs", label: "Subscribers", align: "r", render: (c) => fmt.compact(c.subs), sort: (c) => c.subs },
        { key: "growth", label: "Subs/day", align: "r", render: (c) => c.subs_growth ? fmt.compact(c.subs_growth.per_day) : "—", sort: (c) => c.subs_growth && c.subs_growth.per_day },
        { key: "up", label: "Uploads (7d)", align: "r", render: (c) => String(c.uploads_7d), sort: (c) => c.uploads_7d },
        { key: "ms", label: "Median Short", align: "r", render: (c) => fmt.compact(c.median_short_views), sort: (c) => c.median_short_views },
        { key: "ml", label: "Median long", align: "r", render: (c) => fmt.compact(c.median_long_views), sort: (c) => c.median_long_views },
        { key: "latest", label: "Latest upload", render: (c) => c.latest ? h("a", { href: `#/video?id=${c.latest.id}` }, `${fmt.ago(c.latest.published)} · ${fmt.compact(c.latest.views)} views`) : "—" },
        { key: "x", label: "", cls: "actions", render: (c) => h("button", { class: "icon-btn", title: "Stop tracking", onClick: async () => {
          if (!confirm(`Stop tracking ${c.title}?`)) return;
          await api("/api/competitors", { method: "DELETE", params: { id: c.channel_id } });
          load();
        } }, icon("trash")) },
      ], { sortKey: "subs" })));
      const feedHead = h("div", { class: "row", style: { gap: "8px" } },
        seg([["any", "All"], ["short", "Shorts"], ["long", "Long-form"]], feedFmt, (v) => { feedFmt = v; load(); }),
        select([["score", "Sort: outlier score"], ["vph", "Sort: views/hour"], ["recent", "Sort: newest"], ["views", "Sort: views"]], feedSort, { onChange: (e) => { feedSort = e.target.value; load(); }, style: { width: "auto" } }));
      out.appendChild(cardWithActions("Latest uploads", "Last 14 days across your competitors", feedHead, videoGrid(feed.videos)));
    } catch (err) {
      if (!alive()) return;
      out.classList.remove("dim");
      clear(out).appendChild(errorBox(err, go));
    }
  };
  load();
};

// --- trending
PAGES.trending = (params, main, alive) => {
  const mode = params.mode || (params.q ? "niche" : "chart");
  main.appendChild(pageHead("Trending", "What's gaining views fastest right now — YouTube's official trending chart, or any niche ranked by views per hour."));
  const modeSeg = seg([["chart", "YouTube trending chart"], ["niche", "Hot in my niche"]], mode, (v) => go("trending", { mode: v }));
  main.appendChild(h("div", { style: { marginBottom: "12px" } }, modeSeg));
  const out = h("div", { class: "stack" });
  const fmtSel = select([["any", "All"], ["short", "Shorts"], ["long", "Long-form"]], params.format || (mode === "niche" ? "short" : "any"));
  if (mode === "chart") {
    const region = select(REGIONS, params.region || state.status.settings.region || "US");
    const cat = select([["", "All categories"]], params.category || "");
    main.appendChild(h("form", { class: "filters", onSubmit: (e) => { e.preventDefault(); go("trending", { mode, region: region.value, category: cat.value, format: fmtSel.value, run: "1" }); } },
      field("Region", region), field("Category", cat), field("Format", fmtSel), h("button", { class: "btn primary", type: "submit" }, icon("trending"), "Show trending")));
    main.appendChild(out);
    if (!state.status.youtube_key) { out.appendChild(needsKeyNote("The trending chart")); return; }
    runInto(out, alive, "Loading the trending chart…", () => api("/api/trending", { params: { region: region.value, category: params.category, format: fmtSel.value } }), (r, box) => {
      for (const c of r.categories) cat.appendChild(h("option", { value: c.id, selected: c.id === params.category }, c.title));
      box.appendChild(videoGrid(r.videos, { noScore: true }));
    });
  } else {
    const q = h("input", { type: "search", value: params.q || "", placeholder: "Your niche, e.g. ai tools", "aria-label": "Niche" });
    const hours = select([["24", "Last 24 hours"], ["72", "Last 3 days"], ["168", "Last 7 days"], ["720", "Last 30 days"]], params.hours || "72");
    main.appendChild(h("form", { class: "filters", onSubmit: (e) => { e.preventDefault(); go("trending", { mode, q: q.value.trim(), hours: hours.value, format: fmtSel.value }); } },
      field("Niche keyword", withSuggest(q), null, "grow"), field("Uploaded in", hours), field("Format", fmtSel), h("button", { class: "btn primary", type: "submit" }, icon("trending"), "Find hot videos")));
    main.appendChild(out);
    if (!state.status.youtube_key) { out.appendChild(needsKeyNote("Niche trending")); return; }
    if (!params.q) { out.appendChild(empty("See what's hot in your niche", "Recent uploads ranked by views per hour.", "trending")); return; }
    runInto(out, alive, "Finding the fastest-growing uploads…", () => api("/api/trending/niche", { params }), (r, box) => {
      box.appendChild(h("div", { class: "small muted" }, `Median ${fmt.compact(r.median_vph)} views/hour across ${r.videos.length} videos · quota used: ${r.quota_units}`));
      box.appendChild(videoGrid(r.videos, { noScore: true }));
    });
  }
};

// --- SEO studio
PAGES.seo = (params, main, alive) => {
  main.appendChild(pageHead("SEO studio", "Optimize a video before you upload it. The score updates as you type."));
  let draft = {};
  try { draft = JSON.parse(localStorage.getItem("sr-seo-draft") || "{}"); } catch { draft = {}; }
  const kw = h("input", { type: "text", value: params.keyword || draft.keyword || "", placeholder: "the search phrase this video should rank for" });
  const fmtSel = select([["short", "Short"], ["long", "Long-form"]], params.format || draft.format || "short");
  const title = h("input", { type: "text", value: params.title || draft.title || "", maxlength: "100", placeholder: "Your title" });
  const desc = h("textarea", { rows: "8", placeholder: "Your description", value: draft.description || "" });
  const tagsIn = h("textarea", { rows: "3", placeholder: "tag one, tag two, tag three", value: draft.tags || "" });
  const counters = { title: h("span", { class: "hint" }), desc: h("span", { class: "hint" }), tags: h("span", { class: "hint" }) };
  const tagBtn = h("button", { class: "btn sm", type: "button", onClick: async () => {
    if (!kw.value.trim()) { toast("Enter a target keyword first", true); return; }
    tagBtn.disabled = true;
    try {
      const r = await api("/api/tags", { params: { q: kw.value.trim(), format: fmtSel.value, title: title.value } });
      tagsIn.value = r.copy;
      if (!/#\w/.test(desc.value)) desc.value = (desc.value.trim() + "\n\n" + r.hashtag_copy).trim();
      update();
      toast("Tags added");
    } catch (e) { toast(e.message, true); } finally { tagBtn.disabled = false; }
  } }, icon("sparkles"), "Suggest tags");
  const form = h("div", { class: "card stack" },
    h("div", { class: "row" }, field("Target keyword", withSuggest(kw), null, "grow"), field("Format", fmtSel)),
    field(h("span", {}, "Title ", counters.title), title),
    field(h("span", {}, "Description ", counters.desc), desc),
    field(h("span", {}, "Tags ", counters.tags), tagsIn),
    h("div", { class: "row" }, tagBtn,
      h("a", { class: "btn sm", href: "#", onClick: (e) => { e.preventDefault(); go("titles", { q: kw.value, t: title.value, format: fmtSel.value }); } }, icon("type"), "Title ideas"),
      h("a", { class: "btn sm", href: "#", onClick: (e) => { e.preventDefault(); go("ai", { task: "description", keyword: kw.value, title: title.value, topic: title.value, format: fmtSel.value }); } }, icon("sparkles"), "Write description with AI"),
      h("button", { class: "btn sm ghost", type: "button", onClick: () => { kw.value = title.value = desc.value = tagsIn.value = ""; update(); } }, "Clear")));
  const result = h("div", { class: "stack" });
  main.appendChild(h("div", { class: "grid-2", style: { alignItems: "start" } }, form, result));
  const update = debounce(async () => {
    const tagList = tagsIn.value.split(",").map((t) => t.trim()).filter(Boolean);
    const tagChars = tagList.reduce((n, t) => n + t.length + (t.includes(" ") ? 2 : 0), 0) + Math.max(0, tagList.length - 1);
    counters.title.textContent = `· ${title.value.length}/100`;
    counters.desc.textContent = `· ${desc.value.length}/5000`;
    counters.tags.textContent = `· ${tagChars}/500 characters`;
    try { localStorage.setItem("sr-seo-draft", JSON.stringify({ keyword: kw.value, format: fmtSel.value, title: title.value, description: desc.value, tags: tagsIn.value })); } catch { /* ignore */ }
    if (!title.value.trim() && !desc.value.trim()) { clear(result).appendChild(empty("Start typing", "Your SEO score and checklist appear here.", "seo")); return; }
    try {
      const r = await api("/api/seo/score", { method: "POST", body: { title: title.value, description: desc.value, tags: tagList, keyword: kw.value.trim() || null, format: fmtSel.value } });
      if (!alive()) return;
      clear(result);
      result.appendChild(card("SEO score", r.keyword ? `Keyword: “${r.keyword}”${r.keyword_detected ? " (auto-detected — set one on the left)" : ""}` : "Set a target keyword",
        h("div", { class: "score-head" }, scoreRing(r.score, "SEO score"), h("div", {}, h("span", { class: "grade " + r.grade }, "Grade " + r.grade))), checklist(r.checks)));
      result.appendChild(card("Title click potential", null, h("div", { class: "score-head" }, scoreRing(r.title_score.score, "Title score"), h("span", { class: "grade " + r.title_score.grade }, "Grade " + r.title_score.grade)), signalsList(r.title_score)));
    } catch (e) { clear(result).appendChild(errorBox(e, go)); }
  }, 350);
  for (const el of [kw, title, desc, tagsIn]) el.addEventListener("input", update);
  fmtSel.addEventListener("change", update);
  update();
};

// --- title lab
PAGES.titles = (params, main, alive) => {
  main.appendChild(pageHead("Title lab", "Score title ideas for click-through potential, compare variations and generate new ones."));
  const kw = h("input", { type: "text", value: params.q || "", placeholder: "target keyword (optional)" });
  const fmtSel = select([["short", "Short"], ["long", "Long-form"]], params.format || "short");
  const ta = h("textarea", { rows: "7", placeholder: "One title per line", value: params.t || "" });
  const out = h("div", { class: "stack" });
  const gen = h("div", { class: "stack" });
  const score = async () => {
    const titlesList = ta.value.split("\n").map((t) => t.trim()).filter(Boolean);
    if (!titlesList.length) { clear(out).appendChild(empty("Add some titles", "Paste a few variations to compare them.", "type")); return; }
    try {
      const r = await api("/api/titles/score", { method: "POST", body: { titles: titlesList, keyword: kw.value.trim() || null, format: fmtSel.value } });
      if (!alive()) return;
      clear(out);
      out.appendChild(card("Ranked titles", "Highest click potential first", h("div", { class: "stack-sm" }, r.results.map((x, i) =>
        h("details", { class: "card", style: { padding: "12px 14px", boxShadow: "none" }, open: i === 0 },
          h("summary", { style: { cursor: "pointer", listStyle: "none" } }, h("div", { class: "row", style: { alignItems: "center", flexWrap: "nowrap" } },
            h("span", { class: "grade " + x.grade }, String(x.score)), h("span", { style: { flex: "1", fontWeight: 600 } }, x.title),
            h("span", { class: "small muted num" }, `${x.length} ch`), h("button", { class: "icon-btn", title: "Copy", onClick: (e) => { e.preventDefault(); copyText(x.title); } }, icon("copy")))),
          h("div", { style: { marginTop: "10px" } }, signalsList(x)))))));
    } catch (e) { clear(out).appendChild(errorBox(e, go)); }
  };
  const debounced = debounce(score, 400);
  ta.addEventListener("input", debounced);
  kw.addEventListener("input", debounced);
  fmtSel.addEventListener("change", score);
  const addTitles = (list) => {
    const existing = new Set(ta.value.split("\n").map((t) => t.trim()));
    const add = list.filter((t) => !existing.has(t));
    ta.value = (ta.value.trim() + "\n" + add.join("\n")).trim();
    score();
  };
  const genTemplates = async () => {
    if (!kw.value.trim()) { toast("Enter a keyword to generate ideas", true); return; }
    clear(gen).appendChild(loader("Generating ideas…"));
    try {
      const r = await api("/api/titles/generate", { params: { q: kw.value.trim(), format: fmtSel.value } });
      clear(gen).appendChild(card("Template ideas", "Proven formats filled with your keyword — click to add", chips(r.titles.map((t) => ({ text: t.title, count: t.score })), { onClick: (t) => addTitles([t]) })));
    } catch (e) { clear(gen).appendChild(errorBox(e, go)); }
  };
  const genAI = async () => {
    if (!kw.value.trim() && !ta.value.trim()) { toast("Enter a keyword or a working title", true); return; }
    clear(gen).appendChild(loader("Asking Claude for title ideas…"));
    try {
      const r = await api("/api/ai", { method: "POST", body: { task: "titles", topic: kw.value || ta.value.split("\n")[0], keyword: kw.value, current_title: ta.value.split("\n")[0], format: fmtSel.value, mode: "auto" } });
      clear(gen).appendChild(card(r.mode === "claude" ? `Claude ideas (${r.model})` : "Template ideas", "Click to add to your list", chips(r.result.titles.map((t) => ({ text: t.title, count: t.score })), { onClick: (t) => addTitles([t]) })));
    } catch (e) { clear(gen).appendChild(errorBox(e, go)); }
  };
  main.appendChild(h("div", { class: "grid-2", style: { alignItems: "start" } },
    h("div", { class: "card stack" }, h("div", { class: "row" }, field("Target keyword", withSuggest(kw), null, "grow"), field("Format", fmtSel)),
      field("Titles", ta, "one per line"),
      h("div", { class: "row" }, h("button", { class: "btn primary", onClick: score }, "Score titles"),
        h("button", { class: "btn", onClick: genTemplates }, icon("type"), "Template ideas"),
        h("button", { class: "btn", onClick: genAI }, icon("sparkles"), state.status.ai.ready ? "AI ideas" : "AI ideas (templates)"))),
    h("div", { class: "stack" }, out, gen)));
  if (ta.value.trim()) score(); else clear(out).appendChild(empty("Add some titles", "Paste a few variations to compare them.", "type"));
};

// --- AI studio
// Installing the Claude SDK: the exact command for the Python that runs ShortsRadar (a bare `pip` often targets another Python).
const sdkNote = (inst) => h("div", { class: "note " + (inst.python_ok ? "info" : "warn") }, icon(inst.python_ok ? "info" : "alert"),
  inst.python_ok
    ? h("div", { class: "stack-sm grow" },
      h("div", {}, `Install the Claude SDK once: open ${inst.shell} on this computer and run`),
      h("div", { class: "cmd" }, inst.command),
      h("div", { class: "row", style: { alignItems: "center" } }, copyBtn(inst.command, "command", "Copy command"), h("span", { class: "small muted" }, inst.after)))
    : h("div", {}, `Claude needs Python 3.10 or newer, but ShortsRadar is running on Python ${inst.python_version}. Install the latest Python from `,
      h("a", { href: "https://www.python.org/downloads/", target: "_blank", rel: "noopener" }, "python.org"), ", then start ShortsRadar again."));

const AI_TASKS = [["titles", "Titles"], ["hooks", "Hooks"], ["script", "Shorts script"], ["description", "Description"], ["tags", "Tags"], ["ideas", "Video ideas"]];
PAGES.ai = (params, main, alive) => {
  const st = state.status.ai;
  main.appendChild(pageHead("AI studio", "Hooks, Shorts scripts, titles, descriptions, tags and ideas. Uses Claude when you add an API key; otherwise free templates, or a ready-to-paste prompt for Claude.ai."));
  let task = params.task || "script";
  const note = st.ready ? h("div", { class: "note good" }, icon("good"), h("div", {}, `Claude is ready (${st.model}, ${st.effort} effort).`))
    : st.key_configured && st.install ? sdkNote(st.install)
    : h("div", { class: "note info" }, icon("info"), h("div", {}, st.hint || "Claude isn't configured.", " ", h("a", { href: "#/settings" }, "Settings")));
  main.appendChild(h("div", { style: { marginBottom: "12px" } }, note));
  const f = {
    topic: h("textarea", { rows: "3", value: params.topic || "", placeholder: "What is the video about? What happens in it?" }),
    keyword: h("input", { type: "text", value: params.keyword || "", placeholder: "main search phrase (optional)" }),
    title: h("input", { type: "text", value: params.title || "", placeholder: "working title (optional)" }),
    niche: h("input", { type: "text", value: params.niche || (state.status.settings.niche_keywords || []).join(", "), placeholder: "your channel's niche" }),
    audience: h("input", { type: "text", value: params.audience || "", placeholder: "e.g. beginners, gamers 13-18 (optional)" }),
    seconds: select([["15", "15 seconds"], ["30", "30 seconds"], ["35", "35 seconds"], ["45", "45 seconds"], ["60", "60 seconds"]], params.seconds || "35"),
    format: select([["short", "Short"], ["long", "Long-form"]], params.format || "short"),
    style: h("input", { type: "text", value: params.style || "", placeholder: "e.g. fast, funny, calm voice (optional)" }),
  };
  const mode = select([["auto", st.ready ? "Claude" : "Auto (templates)"], ["claude", "Claude"], ["template", "Free templates"], ["prompt", "Copy prompt for Claude.ai"]], st.ready ? "auto" : "template");
  const fieldsBox = h("div", { class: "stack" });
  const out = h("div", { class: "stack" });
  const drawFields = () => {
    clear(fieldsBox);
    const show = { titles: ["topic", "keyword", "title", "niche", "format"], hooks: ["topic", "keyword", "niche", "audience"], script: ["topic", "keyword", "seconds", "style", "niche", "audience"],
      description: ["title", "topic", "keyword", "format"], tags: ["title", "topic", "keyword", "format"], ideas: ["niche", "audience", "topic", "format"] }[task];
    const labels = { topic: task === "ideas" ? "Extra notes" : "Topic", keyword: "Keyword", title: "Title", niche: "Niche", audience: "Audience", seconds: "Length", format: "Format", style: "Style" };
    const rowish = [];
    for (const k of show) {
      if (["keyword", "niche", "audience", "format", "seconds", "style", "title"].includes(k)) rowish.push(field(labels[k], f[k], null, "grow"));
      else fieldsBox.appendChild(field(labels[k], f[k]));
    }
    fieldsBox.appendChild(h("div", { class: "row" }, rowish));
    fieldsBox.appendChild(h("div", { class: "row", style: { alignItems: "flex-end" } }, field("Generate with", mode), h("button", { class: "btn primary", type: "button", onClick: run }, icon("sparkles"), "Generate")));
  };
  const run = async () => {
    const body = { task, mode: mode.value };
    for (const k of ["topic", "keyword", "title", "niche", "audience", "style"]) if (f[k].value.trim()) body[k] = f[k].value.trim();
    body.format = f.format.value;
    if (task === "script") { body.seconds = Number(f.seconds.value); body.format = "short"; }
    clear(out).appendChild(loader(mode.value === "claude" || (mode.value === "auto" && st.ready) ? "Claude is writing…" : "Generating…"));
    try {
      const r = await api("/api/ai", { method: "POST", body });
      if (!alive()) return;
      clear(out);
      renderAI(r, out);
    } catch (e) { clear(out).appendChild(errorBox(e, go)); }
  };
  main.appendChild(h("div", { style: { marginBottom: "12px" } }, seg(AI_TASKS, task, (v) => { task = v; drawFields(); clear(out); })));
  main.appendChild(h("div", { class: "grid-2", style: { alignItems: "start" } }, h("div", { class: "card" }, fieldsBox), out));
  drawFields();
  if (params.run) run();
};

function renderAI(r, out) {
  const res = r.result;
  const head = r.mode === "claude" ? `Written by Claude (${r.model})${r.fallback_used ? " · fallback model" : ""}` : r.mode === "template" ? "Free template output" : "Prompt for Claude.ai";
  if (r.mode === "prompt" || !res) {
    out.appendChild(cardWithActions("Paste this into Claude.ai", "Free: open claude.ai, paste, and send.", [copyBtn(r.prompt, "prompt"), h("a", { class: "btn sm", href: "https://claude.ai/new", target: "_blank", rel: "noopener" }, icon("external"), "Open Claude.ai")],
      h("div", { class: "desc" }, r.prompt)));
    return;
  }
  const t = r.task;
  let body;
  if (t === "titles") {
    body = h("div", { class: "stack-sm" }, res.titles.map((x) => h("div", { class: "row", style: { alignItems: "center", flexWrap: "nowrap" } },
      h("span", { class: "grade " + (x.grade || "C") }, String(x.score ?? "")), h("div", { style: { flex: "1" } }, h("div", { style: { fontWeight: 600 } }, x.title), h("div", { class: "small muted" }, [x.angle, x.why].filter(Boolean).join(" — "))),
      h("button", { class: "icon-btn", title: "Copy", onClick: () => copyText(x.title) }, icon("copy")))));
  } else if (t === "hooks") {
    body = h("div", { class: "stack-sm" }, res.hooks.map((x) => h("div", { class: "row", style: { alignItems: "center", flexWrap: "nowrap" } },
      h("div", { style: { flex: "1" } }, h("div", { style: { fontWeight: 600 } }, x.text), h("div", { class: "small muted" }, `${x.type}${x.why ? " — " + x.why : ""}`)),
      h("button", { class: "icon-btn", title: "Copy", onClick: () => copyText(x.text) }, icon("copy")))));
  } else if (t === "script") {
    const text = [`${res.title}`, `HOOK: ${res.hook}`, ...res.beats.map((b) => `[${b.time}] ${b.voiceover}  | on screen: ${b.on_screen_text} | visual: ${b.visual}`), `CTA: ${res.cta}`, `LOOP: ${res.loop}`, `CAPTION: ${res.caption} ${(res.hashtags || []).join(" ")}`].join("\n");
    body = h("div", { class: "stack-sm" },
      h("div", {}, h("b", {}, res.title), h("div", { class: "small ink2" }, "Hook: ", res.hook)),
      dataTable(res.beats, [
        { key: "time", label: "Time", render: (b) => h("span", { class: "num nowrap" }, b.time) },
        { key: "vo", label: "Voiceover", render: (b) => b.voiceover },
        { key: "ost", label: "On screen", render: (b) => b.on_screen_text },
        { key: "vis", label: "Visual", render: (b) => b.visual },
      ], { cls: "script-table" }),
      h("dl", { class: "kv" }, h("dt", {}, "CTA"), h("dd", {}, res.cta), h("dt", {}, "Loop"), h("dd", {}, res.loop), h("dt", {}, "Caption"), h("dd", {}, res.caption, " ", (res.hashtags || []).join(" "))),
      h("div", {}, copyBtn(text, "script", "Copy script")));
  } else if (t === "description") {
    const ta = h("textarea", { rows: "9", value: res.description });
    body = h("div", { class: "stack-sm" }, ta, h("div", { class: "row" }, copyBtn(() => ta.value, "description"),
      res.seo_score !== undefined ? pill(`SEO ${res.seo_score}/100`, res.seo_score >= 70 ? "good" : "warn") : null),
    res.pinned_comment ? h("div", { class: "small" }, h("b", {}, "Pinned comment: "), res.pinned_comment) : null);
  } else if (t === "tags") {
    const text = res.tags.join(", ");
    body = h("div", { class: "stack-sm" }, chips(res.tags), h("div", { class: "small muted" }, `${text.length}/500 characters`),
      h("div", { class: "row" }, copyBtn(text, "tags", "Copy tags"), res.hashtags && res.hashtags.length ? copyBtn(res.hashtags.join(" "), "hashtags", "Copy hashtags") : null));
  } else if (t === "ideas") {
    body = h("div", {}, res.ideas.map((x) => h("div", { class: "idea" },
      h("div", {}, h("div", { class: "t" }, x.title), h("div", { class: "w" }, "Hook: ", x.hook), h("div", { class: "w" }, x.concept), h("div", { class: "w muted" }, x.why_it_works)),
      h("div", { class: "row", style: { gap: "6px", alignItems: "flex-start" } },
        h("a", { class: "btn sm", href: `#/ai?task=script&topic=${encodeURIComponent(x.title + ". " + x.concept)}&run=1` }, "Script it"),
        h("button", { class: "icon-btn", title: "Save", onClick: () => saveItem("idea", x.title, x.title, x) }, icon("bookmark"))))));
  }
  out.appendChild(card(head, r.usage ? `${r.usage.input_tokens} in / ${r.usage.output_tokens} out tokens` : null, body));
  out.appendChild(h("details", { class: "card more" }, h("summary", {}, "Prompt (paste into Claude.ai for free)"),
    h("div", { class: "desc" }, r.prompt), h("div", { style: { marginTop: "8px" } }, copyBtn(r.prompt, "prompt"))));
}

// --- daily ideas
PAGES.ideas = (params, main, alive) => {
  main.appendChild(pageHead("Daily ideas", "Fresh video ideas from what's over-performing in your niches right now, plus real searches nobody has answered well."));
  const niches = h("input", { type: "text", value: params.niches || (state.status.settings.niche_keywords || []).join(", "), placeholder: "e.g. minecraft redstone, cooking hacks" });
  const fmtSel = select([["short", "Shorts"], ["long", "Long-form"]], params.format || "short");
  main.appendChild(h("form", { class: "filters", onSubmit: (e) => { e.preventDefault(); go("ideas", { niches: niches.value, format: fmtSel.value, run: "1" }); } },
    field("Niches", niches, "comma separated, up to 3", "grow"), field("Format", fmtSel),
    h("button", { class: "btn primary", type: "submit" }, icon("bulb"), "Get ideas"),
    h("button", { class: "btn", type: "button", onClick: () => go("ideas", { niches: niches.value, format: fmtSel.value, run: "1", refresh: "1" }) }, icon("refresh"), "Refresh")));
  const out = h("div", { class: "stack" });
  main.appendChild(out);
  if (!params.run && !niches.value.trim()) { out.appendChild(empty("Tell us your niche", "Add niche keywords here or in Settings.", "bulb")); return; }
  if (!params.run) { out.appendChild(h("div", {}, h("button", { class: "btn primary", onClick: () => go("ideas", { niches: niches.value, format: fmtSel.value, run: "1" }) }, "Show today's ideas"))); return; }
  runInto(out, alive, "Looking for today's opportunities…", () => api("/api/ideas", { params: { niches: niches.value, format: fmtSel.value, refresh: params.refresh } }), (r, box) => {
    if (r.errors.length) box.appendChild(notes(r.errors.map((e) => ({ type: "warn", text: e }))));
    if (!state.status.youtube_key) box.appendChild(needsKeyNote("Outlier-based ideas"));
    box.appendChild(card(`${r.ideas.length} ideas for ${r.date}`, r.cached ? "Cached for today — press Refresh for new ones" : `Quota used: ${r.quota_units} units`,
      r.ideas.length ? h("div", {}, r.ideas.map((i) => h("div", { class: "idea" },
        h("div", {}, h("div", { class: "row", style: { gap: "8px", alignItems: "center" } }, pill(i.type === "outlier" ? "Outlier" : "Search", i.type === "outlier" ? "bad" : "short"), h("span", { class: "t" }, i.idea)),
          h("div", { class: "w" }, i.why), i.video ? h("div", { class: "w" }, h("a", { href: `#/video?id=${i.video.id}` }, `${i.video.channel_title} · ${fmt.compact(i.video.views)} views`)) : null),
        h("div", { class: "row", style: { gap: "6px", alignItems: "flex-start" } },
          h("a", { class: "btn sm", href: `#/ai?task=script&topic=${encodeURIComponent(i.idea.replace(/^Your own take on /, ""))}&keyword=${encodeURIComponent(i.keyword || i.niche)}&run=1` }, icon("sparkles"), "Script"),
          i.keyword ? h("a", { class: "btn sm", href: `#/keywords?q=${encodeURIComponent(i.keyword)}` }, "Research") : null,
          h("button", { class: "icon-btn", title: "Save", onClick: () => saveItem("idea", i.idea, i.idea, i) }, icon("bookmark")))))) : empty("No ideas found", "Try broader niche keywords.")));
  });
};

// --- earnings
PAGES.earnings = async (params, main, alive) => {
  main.appendChild(pageHead("Earnings calculator", "Estimate ad revenue from views. Shorts earn far less per view than long-form — see the difference."));
  const meta = await api("/api/earnings/meta").catch(() => ({ categories: ["Entertainment"], countries: ["US"] }));
  if (!alive()) return;
  const views = h("input", { type: "number", min: "0", step: "1000", value: params.views || "1000000" });
  const cat = select(meta.categories, params.category || "Entertainment");
  const country = select(meta.countries, params.country || state.status.settings.region || "US");
  const mix = h("input", { type: "range", min: "0", max: "100", value: params.mix || "100", style: { width: "100%" } });
  const mixLabel = h("span", { class: "hint" });
  const out = h("div", { class: "stack" });
  const update = debounce(async () => {
    mixLabel.textContent = `· ${mix.value}% Shorts / ${100 - Number(mix.value)}% long-form`;
    try {
      const r = await api("/api/earnings", { params: { views: views.value || 0, category: cat.value, country: country.value, shorts_share: Number(mix.value) / 100 } });
      if (!alive()) return;
      clear(out);
      out.appendChild(h("div", { class: "tiles" },
        tile("Per month", `${fmt.money(r.earnings.low)} – ${fmt.money(r.earnings.high)}`, `likely ${fmt.money(r.earnings.mid)}`, { hero: false }),
        tile("Per year", `${fmt.money(r.yearly.low)} – ${fmt.money(r.yearly.high)}`, `likely ${fmt.money(r.yearly.mid)}`),
        tile("Per day", fmt.money(r.daily.mid), "likely"),
        tile("RPM", `${fmt.money(r.rpm.low)} – ${fmt.money(r.rpm.high)}`, "earned per 1,000 views")));
      out.appendChild(card("Good to know", null, notes([
        { type: "info", text: r.note },
        { type: "info", text: "YouTube Partner Program: 1,000 subscribers + 4,000 public watch hours in 12 months, or 1,000 subscribers + 10M public Shorts views in 90 days." },
        { type: "info", text: "Shorts revenue is pooled and shared by views, so Shorts RPM is typically $0.02–$0.12. Most Shorts creators earn more by funnelling viewers to long-form, affiliate links or sponsorships." },
      ])));
    } catch (e) { clear(out).appendChild(errorBox(e, go)); }
  }, 250);
  for (const el of [views, mix]) el.addEventListener("input", update);
  for (const el of [cat, country]) el.addEventListener("change", update);
  main.appendChild(h("div", { class: "grid-2", style: { alignItems: "start" } },
    h("div", { class: "card stack" }, field("Views per month", views), field("Category", cat), field("Main audience country", country), field(h("span", {}, "Content mix ", mixLabel), mix)),
    out));
  update();
};

// --- saved
PAGES.saved = async (params, main, alive) => {
  main.appendChild(pageHead("Saved", "Keywords, videos, ideas and titles you bookmarked."));
  const out = h("div", {});
  main.appendChild(out);
  const load = async () => {
    try {
      const r = await api("/api/saved");
      if (!alive()) return;
      clear(out);
      if (!r.items.length) { out.appendChild(empty("Nothing saved yet", "Use the bookmark buttons across the app.", "bookmark")); return; }
      out.appendChild(card(null, null, dataTable(r.items, [
        { key: "kind", label: "Type", render: (x) => pill(x.kind), sort: (x) => x.kind },
        { key: "title", label: "Item", render: (x) => {
          const href = x.kind === "keyword" ? `#/keywords?q=${encodeURIComponent(x.ref)}` : x.kind === "video" ? `#/video?id=${encodeURIComponent(x.ref)}` :
            x.kind === "channel" ? `#/channel?id=${encodeURIComponent(x.ref)}` : null;
          return href ? h("a", { href, style: { fontWeight: 600 } }, x.title) : h("span", { style: { fontWeight: 600 } }, x.title);
        } },
        { key: "created", label: "Saved", align: "r", render: (x) => fmt.ago(x.created), sort: (x) => x.created },
        { key: "a", label: "", cls: "actions", render: (x) => h("span", {}, h("button", { class: "icon-btn", title: "Copy", onClick: () => copyText(x.title) }, icon("copy")),
          h("button", { class: "icon-btn", title: "Delete", onClick: async () => { await api("/api/saved", { method: "DELETE", params: { id: x.id } }); load(); } }, icon("trash"))) },
      ], { sortKey: "created" })));
    } catch (e) { clear(out).appendChild(errorBox(e, go)); }
  };
  load();
};

// --- settings
PAGES.settings = async (params, main, alive) => {
  main.appendChild(pageHead("Settings", "API keys and preferences are stored only on this computer."));
  let st;
  try { st = await api("/api/settings"); } catch (e) { main.appendChild(errorBox(e, go)); return; }
  if (!alive()) return;
  const ytKey = h("input", { type: "password", value: st.youtube_api_key, placeholder: "AIza…", autocomplete: "off", disabled: st.youtube_api_key_from_env });
  const aiKey = h("input", { type: "password", value: st.anthropic_api_key, placeholder: "sk-ant-…", autocomplete: "off", disabled: st.anthropic_api_key_from_env });
  const model = select([["claude-opus-5", "Claude Opus 5 (default)"], ["claude-fable-5-1", "Claude Fable 5.1 (most capable)"], ["claude-sonnet-5", "Claude Sonnet 5 (faster, cheaper)"], ["claude-haiku-4-5", "Claude Haiku 4.5 (fastest, cheapest)"]], st.ai_model);
  const effort = select([["low", "Low (fastest)"], ["medium", "Medium"], ["high", "High"], ["xhigh", "Extra high"], ["max", "Max (slowest)"]], st.ai_effort);
  const region = select(REGIONS, st.region);
  const lang = h("input", { type: "text", value: st.language, maxlength: "5" });
  const tz = h("input", { type: "text", value: st.timezone, placeholder: Intl.DateTimeFormat().resolvedOptions().timeZone || "e.g. America/New_York" });
  const defFmt = select([["short", "Shorts"], ["long", "Long-form"], ["any", "All"]], st.default_format);
  const niches = h("input", { type: "text", value: (st.niche_keywords || []).join(", "), placeholder: "minecraft redstone, cooking hacks" });
  const refresh = h("input", { type: "number", min: "0", value: String(st.auto_refresh_minutes) });
  const quota = h("input", { type: "number", min: "100", step: "100", value: String(st.daily_quota) });
  const reveal = (inp) => h("button", { class: "btn sm ghost", type: "button", onClick: () => { inp.type = inp.type === "password" ? "text" : "password"; } }, "Show");
  const save = async () => {
    const body = { region: region.value, language: lang.value, timezone: tz.value, default_format: defFmt.value, niche_keywords: niches.value,
      auto_refresh_minutes: refresh.value, daily_quota: quota.value, ai_model: model.value, ai_effort: effort.value };
    if (!st.youtube_api_key_from_env) body.youtube_api_key = ytKey.value.trim();
    if (!st.anthropic_api_key_from_env) body.anthropic_api_key = aiKey.value.trim();
    try { await api("/api/settings", { method: "POST", body }); await loadStatus(); toast("Settings saved"); go("settings"); }
    catch (e) { toast(e.message, true); }
  };
  const testOut = h("span", { class: "small" });
  const test = async () => {
    await save();
    testOut.textContent = "Testing…";
    try { const r = await api("/api/settings/test-youtube", { method: "POST" }); testOut.textContent = "✔ " + r.message; }
    catch (e) { testOut.textContent = "✘ " + e.message; }
  };
  main.appendChild(h("div", { class: "grid-2", style: { alignItems: "start" } },
    h("div", { class: "stack" },
      card("YouTube Data API key", `Free · used today: ${state.status.quota.used.toLocaleString()} of ${state.status.quota.limit.toLocaleString()} units (resets midnight Pacific)`,
        h("div", { class: "stack-sm" }, h("div", { class: "row" }, h("div", { class: "grow" }, ytKey), reveal(ytKey)),
          st.youtube_api_key_from_env ? h("div", { class: "small muted" }, "Set by an environment variable (YOUTUBE_API_KEY or SHORTSRADAR_YOUTUBE_API_KEY).") : null,
          h("div", { class: "row", style: { alignItems: "center" } }, h("button", { class: "btn sm", type: "button", onClick: test }, "Save & test key"), testOut))),
      card("Claude (optional)", "For AI titles, hooks, scripts and descriptions",
        h("div", { class: "stack-sm" }, h("div", { class: "row" }, h("div", { class: "grow" }, aiKey), reveal(aiKey)),
          h("div", { class: "row" }, field("Model", model, null, "grow"), field("Effort", effort)),
          state.status.ai.install ? sdkNote(state.status.ai.install) : h("div", { class: "small muted" }, "Claude SDK installed."))),
      card("Preferences", null, h("div", { class: "stack-sm" },
        h("div", { class: "row" }, field("Region", region, null, "grow"), field("Language", lang)),
        h("div", { class: "row" }, field("Timezone", tz, "for best posting times", "grow"), field("Default format", defFmt)),
        field("Niche keywords", niches, "comma separated — used by Daily ideas"),
        h("div", { class: "row" }, field("Competitor refresh", refresh, "minutes, 0 = off", "grow"), field("Daily quota", quota, "units", "grow")))),
      h("div", { class: "row" }, h("button", { class: "btn primary", type: "button", onClick: save }, "Save settings"),
        h("button", { class: "btn", type: "button", onClick: async () => { const r = await api("/api/cache/clear", { method: "POST" }); toast(`Cleared ${r.cleared} cached responses`); } }, icon("trash"), "Clear cache")),
      h("div", { class: "small muted" }, "Data folder: ", h("code", {}, st.data_dir))),
    h("div", { class: "stack" },
      card("Get a free YouTube API key (5 minutes)", null, h("ol", { class: "steps" },
        h("li", {}, "Open ", h("a", { href: "https://console.cloud.google.com/projectcreate", target: "_blank", rel: "noopener" }, "Google Cloud Console"), " and create a project (any name)."),
        h("li", {}, "Go to ", h("a", { href: "https://console.cloud.google.com/apis/library/youtube.googleapis.com", target: "_blank", rel: "noopener" }, "YouTube Data API v3"), " and click Enable."),
        h("li", {}, "Open ", h("a", { href: "https://console.cloud.google.com/apis/credentials", target: "_blank", rel: "noopener" }, "Credentials"), " → Create credentials → API key."),
        h("li", {}, "Recommended: edit the key → API restrictions → restrict it to YouTube Data API v3."),
        h("li", {}, "Paste it on the left and press “Save & test key”. No billing account needed."))),
      card("What costs quota?", "You get 10,000 units per day, free", h("dl", { class: "kv" },
        h("dt", {}, "Keyword research"), h("dd", {}, "~102 units"),
        h("dt", {}, "Outlier search"), h("dd", {}, "~120–200 units (300+ deep)"),
        h("dt", {}, "Video scorecard"), h("dd", {}, "2–4 units"),
        h("dt", {}, "Channel audit"), h("dd", {}, "3–10 units"),
        h("dt", {}, "Trending chart"), h("dd", {}, "1–2 units"),
        h("dt", {}, "Competitor tracking"), h("dd", {}, "free (RSS)"),
        h("dt", {}, "Autocomplete, title & SEO scores"), h("dd", {}, "free")),
      h("p", { class: "small muted", style: { marginTop: "10px" } }, "Results are cached, so repeating a search is free for several hours.")),
      card("Claude API key", null, h("p", { class: "small ink2" }, "Create one at ", h("a", { href: "https://platform.claude.com/settings/keys", target: "_blank", rel: "noopener" }, "platform.claude.com"),
        ". Without a key, AI studio still works with free templates, or gives you a prompt to paste into the free Claude.ai chat.")))));
};

// ---------- shell ----------
async function loadStatus() {
  state.status = await api("/api/status");
  updateQuota(state.status.quota);
  bannerEl.style.display = state.status.demo ? "block" : "none";
}

function updateQuota(q) {
  clear(quotaEl);
  if (!q) return;
  const pct = Math.min(100, (100 * q.used) / Math.max(1, q.limit));
  quotaEl.title = `YouTube API quota today: ${q.used.toLocaleString()} of ${q.limit.toLocaleString()} units · resets in ${Math.round(q.resets_in_seconds / 3600)}h (midnight Pacific)`;
  append(quotaEl, [meter(pct), h("span", { class: "num" }, `${fmt.compact(q.used)} / ${fmt.compact(q.limit)}`)]);
}

const refreshQuota = debounce(async () => {
  try { updateQuota(await api("/api/quota")); } catch { /* ignore */ }
}, 800);

function buildShell() {
  const root = document.getElementById("root");
  navEl = h("nav", { class: "nav", "aria-label": "Main" });
  for (const item of NAV) {
    if (item.length === 1) { navEl.appendChild(h("div", { class: "nav-group" }, item[0])); continue; }
    const [path, label, ic] = item;
    navEl.appendChild(h("a", { href: "#/" + path, dataset: { path } }, icon(ic), label));
  }
  const sidebar = h("aside", { class: "sidebar" },
    h("div", { class: "brand" }, h("div", { class: "brand-mark" }, icon("radar")), h("div", {}, "ShortsRadar", h("small", {}, "YouTube research toolkit"))),
    navEl, h("div", { class: "sidebar-foot" }, "Runs on your computer · your keys stay local"));
  const search = h("input", { type: "search", placeholder: "Search a keyword, paste a video or channel link…", "aria-label": "Global search" });
  quotaEl = h("span", { class: "pill quota-pill" });
  const themeBtn = h("button", { class: "icon-btn", title: "Toggle dark mode", onClick: () => {
    const cur = document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    const next = cur === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("sr-theme", next); } catch { /* ignore */ }
  } }, icon("moon"));
  const topbar = h("header", { class: "topbar" },
    h("button", { class: "icon-btn menu-btn", title: "Menu", onClick: () => sidebar.classList.toggle("open") }, icon("menu")),
    h("form", { onSubmit: (e) => { e.preventDefault(); routeSearch(search.value); search.blur(); } },
      h("div", { class: "searchbox" }, icon("search"), withSuggest(search))),
    h("span", { class: "spacer" }), quotaEl, themeBtn);
  bannerEl = h("div", { class: "banner", style: { display: "none" } }, "Demo mode — all channels, videos and numbers are synthetic. Add your own YouTube API key and run without --demo for real data.");
  mainEl = h("main", { class: "content", id: "main" });
  root.appendChild(h("div", { class: "app" }, sidebar, h("div", { class: "main" }, bannerEl, topbar, mainEl)));
}

async function boot() {
  buildShell();
  onQuota(refreshQuota);
  try { await loadStatus(); }
  catch (e) { mainEl.appendChild(errorBox(e, go)); return; }
  window.addEventListener("hashchange", render);
  render();
}

boot();
