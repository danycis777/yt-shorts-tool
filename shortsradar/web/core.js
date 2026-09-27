// ShortsRadar UI core: DOM helpers, API client, formatting, components and SVG charts.
// All dynamic text is inserted with text nodes (never innerHTML) because it comes from YouTube.

const SVGNS = "http://www.w3.org/2000/svg";

// ---------- DOM ----------
export function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  applyAttrs(el, attrs);
  append(el, kids);
  return el;
}

export function s(tag, attrs, ...kids) {
  const el = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === "class") el.setAttribute("class", v);
    else el.setAttribute(k, v);
  }
  append(el, kids);
  return el;
}

function applyAttrs(el, attrs) {
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "style" && typeof v === "object") Object.assign(el.style, v);
    else if (k === "dataset") Object.assign(el.dataset, v);
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === "value") el.value = v;
    else if (k === "checked" || k === "selected" || k === "disabled" || k === "open") el[k] = !!v;
    else if (k === "href" || k === "src") { const u = safeUrl(v); if (u) el.setAttribute(k, u); }
    else if (v === true) el.setAttribute(k, "");
    else el.setAttribute(k, v);
  }
}

export function append(el, kids) {
  for (const kid of kids.flat(Infinity)) {
    if (kid === null || kid === undefined || kid === false) continue;
    el.appendChild(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

export function clear(el) { while (el.firstChild) el.removeChild(el.firstChild); return el; }

export function safeUrl(u) {
  const str = String(u || "");
  if (str.startsWith("#") || str.startsWith("/")) return str;
  try {
    const url = new URL(str);
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : "";
  } catch { return ""; }
}

// ---------- icons (24x24 stroke icons) ----------
const ICONS = {
  home: "M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z",
  search: "M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16zM21 21l-4.3-4.3",
  key: "M4 7h16M4 12h10M4 17h7M17 14l4 4M21 14l-4 4",
  zap: "M13 2 4 14h7l-1 8 9-12h-7z",
  video: "M3 6a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2zM17 10l4-3v10l-4-3",
  user: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21a8 8 0 0 1 16 0",
  users: "M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM2 21a7 7 0 0 1 14 0M16 3.1a4 4 0 0 1 0 7.8M22 21a7 7 0 0 0-5-6.7",
  trending: "M3 17l6-6 4 4 8-8M15 7h6v6",
  seo: "M9 11l3 3 8-8M20 12v7a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h9",
  type: "M4 7V4h16v3M9 20h6M12 4v16",
  sparkles: "M12 3l1.8 4.7L18.5 9.5l-4.7 1.8L12 16l-1.8-4.7L5.5 9.5l4.7-1.8zM19 15l.9 2.1L22 18l-2.1.9L19 21l-.9-2.1L16 18l2.1-.9z",
  bulb: "M9 18h6M10 21h4M12 3a6 6 0 0 0-4 10.5c.8.8 1 1.5 1 2.5h6c0-1 .2-1.7 1-2.5A6 6 0 0 0 12 3z",
  dollar: "M12 2v20M17 6H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6",
  bookmark: "M6 3h12v18l-6-4-6 4z",
  settings: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z",
  menu: "M3 6h18M3 12h18M3 18h18",
  copy: "M9 9h11v11H9zM5 15H4V4h11v1",
  check: "M5 12l5 5L20 7",
  x: "M6 6l12 12M18 6 6 18",
  alert: "M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z",
  info: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 16v-4M12 8h.01",
  external: "M14 3h7v7M10 14 21 3M19 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h5",
  refresh: "M21 12a9 9 0 1 1-2.6-6.4L21 8M21 3v5h-5",
  trash: "M4 7h16M10 11v6M14 11v6M5 7l1 13a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1l1-13M9 7V4h6v3",
  plus: "M12 5v14M5 12h14",
  sun: "M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10zM12 1v2M12 21v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M1 12h2M21 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4",
  moon: "M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z",
  star: "M12 3l2.8 5.7 6.2.9-4.5 4.4 1.1 6.2L12 17.3 6.4 20.2l1.1-6.2L3 9.6l6.2-.9z",
  good: "M5 12l5 5L20 7",
  warn: "M12 8v5M12 16h.01",
  bad: "M7 7l10 10M17 7 7 17",
  radar: "M12 3a9 9 0 1 0 9 9M12 8a4 4 0 1 0 4 4M12 12l6-6",
  clock: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 6v6l4 2",
  chart: "M4 20V10M10 20V4M16 20v-7M22 20H2",
  play: "M6 4l14 8-14 8z",
};

export function icon(name, cls) {
  const svg = s("svg", { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": "2",
    "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true", class: cls || null });
  svg.appendChild(s("path", { d: ICONS[name] || ICONS.info }));
  return svg;
}

// ---------- API ----------
let quotaListener = null;
export function onQuota(fn) { quotaListener = fn; }

export async function api(path, { method = "GET", params, body } = {}) {
  let url = path;
  if (params) {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null && v !== "" && v !== false) qs.set(k, v === true ? "1" : v);
    }
    const q = qs.toString();
    if (q) url += "?" + q;
  }
  const headers = { "X-ShortsRadar": "1" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  let res;
  try {
    res = await fetch(url, { method, headers, body: body !== undefined ? JSON.stringify(body) : undefined });
  } catch {
    const err = new Error("Can't reach ShortsRadar — is the app still running?");
    err.code = "offline";
    throw err;
  }
  let data = null;
  try { data = await res.json(); } catch { /* non-JSON */ }
  if (quotaListener && url.startsWith("/api/") && !url.startsWith("/api/quota")) quotaListener();
  if (!res.ok) {
    const err = new Error((data && data.error) || `Request failed (${res.status})`);
    err.code = data && data.code;
    err.status = res.status;
    throw err;
  }
  return data;
}

// ---------- formatting ----------
export const fmt = {
  compact(n) {
    if (n === null || n === undefined || Number.isNaN(n)) return "—";
    const a = Math.abs(n);
    const f = (x, s2) => (x >= 100 ? Math.round(x) : x >= 10 ? x.toFixed(1).replace(/\.0$/, "") : x.toFixed(1).replace(/\.0$/, "")) + s2;
    if (a >= 1e9) return f(n / 1e9, "B");
    if (a >= 1e6) return f(n / 1e6, "M");
    if (a >= 1e4) return f(n / 1e3, "K");
    if (a >= 1e3) return (n / 1e3).toFixed(1).replace(/\.0$/, "") + "K";
    return a < 10 && n % 1 ? n.toFixed(1) : String(Math.round(n));
  },
  int(n) { return n === null || n === undefined ? "—" : Math.round(n).toLocaleString(); },
  pct(n, d = 1) { return n === null || n === undefined ? "—" : `${Number(n).toFixed(d)}%`; },
  score(n) { return n === null || n === undefined ? "—" : String(Math.round(n)); },
  x(n) { return n === null || n === undefined ? "—" : `${n >= 10 ? Math.round(n) : Number(n).toFixed(1)}×`; },
  money(n) {
    if (n === null || n === undefined) return "—";
    return n >= 100 ? "$" + Math.round(n).toLocaleString() : "$" + Number(n).toFixed(2);
  },
  moneyShort(n) {
    if (n === null || n === undefined) return "—";
    return n >= 10000 ? "$" + fmt.compact(n) : fmt.money(n);
  },
  ago(value) {
    if (!value) return "—";
    const t = typeof value === "number" ? value * (value < 1e12 ? 1000 : 1) : Date.parse(value);
    const s2 = (Date.now() - t) / 1000;
    if (s2 < 60) return "just now";
    const units = [[31536000, "y"], [2592000, "mo"], [604800, "w"], [86400, "d"], [3600, "h"], [60, "m"]];
    for (const [sec, u] of units) if (s2 >= sec) return `${Math.floor(s2 / sec)}${u} ago`;
    return "just now";
  },
  hoursAge(hours) {
    if (hours === null || hours === undefined) return "—";
    if (hours < 48) return `${Math.round(hours)}h`;
    if (hours < 24 * 60) return `${Math.round(hours / 24)}d`;
    if (hours < 24 * 730) return `${Math.round(hours / 24 / 30)}mo`;
    return `${(hours / 24 / 365).toFixed(1)}y`;
  },
  date(value) {
    if (!value) return "—";
    const d = typeof value === "number" ? new Date(value * (value < 1e12 ? 1000 : 1)) : new Date(value);
    return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  },
};

export function band(score) {
  if (score === null || score === undefined) return "—";
  return score >= 80 ? "Very high" : score >= 60 ? "High" : score >= 40 ? "Medium" : score >= 20 ? "Low" : "Very low";
}

export function overallLabel(score) {
  if (score === null || score === undefined) return { text: "Needs API key", cls: "" };
  if (score >= 70) return { text: "Excellent", cls: "good", icon: "good" };
  if (score >= 55) return { text: "Good", cls: "good", icon: "good" };
  if (score >= 40) return { text: "Fair", cls: "warn", icon: "warn" };
  return { text: "Weak", cls: "bad", icon: "bad" };
}

// ---------- small components ----------
export function toast(msg, isErr) {
  const wrap = document.getElementById("toasts");
  const t = h("div", { class: "toast" + (isErr ? " err" : "") }, msg);
  wrap.appendChild(t);
  setTimeout(() => t.remove(), isErr ? 5000 : 2200);
}

export async function copyText(text, label) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const ta = h("textarea", { style: { position: "fixed", opacity: "0" } });
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    ta.remove();
  }
  toast(label ? `Copied ${label}` : "Copied");
}

export function copyBtn(getText, label, text = "Copy") {
  return h("button", { class: "btn sm", type: "button", onClick: () => copyText(typeof getText === "function" ? getText() : getText, label) },
    icon("copy"), text);
}

export function pill(text, cls, ic) {
  return h("span", { class: "pill" + (cls ? " " + cls : "") }, ic ? icon(ic) : null, text);
}

export function formatPill(isShort) {
  return isShort ? pill("Short", "short") : pill("Long-form");
}

export function meter(value, max = 100) {
  const pct = Math.max(0, Math.min(100, ((value || 0) / max) * 100));
  return h("div", { class: "meter", role: "meter", "aria-valuenow": String(value ?? 0), "aria-valuemin": "0", "aria-valuemax": String(max) },
    h("span", { style: { width: pct + "%" } }));
}

export function miniMeter(value, approx) {
  if (value === null || value === undefined) return h("span", { class: "muted" }, "—");
  return h("span", { class: "mini-meter" }, meter(value), h("span", { class: "num" }, (approx ? "~" : "") + Math.round(value)));
}

export function tile(label, value, sub, opts = {}) {
  return h("div", { class: "tile" + (opts.hero ? " hero" : ""), title: opts.title || null },
    h("div", { class: "label" }, opts.icon ? icon(opts.icon) : null, label),
    h("div", { class: "value" }, value, opts.unit ? h("span", { class: "unit" }, opts.unit) : null),
    opts.meter !== undefined ? meter(opts.meter) : null,
    sub ? h("div", { class: "sub" }, sub) : null,
    opts.extra || null);
}

export function card(title, sub, ...body) {
  const head = title || sub ? h("div", { class: "card-head" },
    h("div", {}, title ? h("h2", {}, title) : null, sub ? h("div", { class: "sub" }, sub) : null)) : null;
  return h("section", { class: "card" }, head, ...body);
}

export function cardWithActions(title, sub, actions, ...body) {
  return h("section", { class: "card" },
    h("div", { class: "card-head" }, h("div", {}, h("h2", {}, title), sub ? h("div", { class: "sub" }, sub) : null),
      h("div", { class: "row", style: { gap: "6px" } }, actions)),
    ...body);
}

export function notes(items) {
  if (!items || !items.length) return null;
  return h("div", { class: "notes" }, items.map((n) => {
    const type = n.type === "good" ? "good" : n.type === "warn" ? "warn" : n.type === "bad" ? "bad" : "info";
    const ic = type === "good" ? "good" : type === "info" ? "info" : "alert";
    return h("div", { class: "note " + type }, icon(ic), h("div", {}, n.text));
  }));
}

export function loader(text) {
  const started = Date.now();
  const secs = h("span", { class: "muted small num" }, "");
  const el = h("div", { class: "loader" }, h("div", { class: "spinner" }), h("div", {}, h("div", {}, text), secs));
  const timer = setInterval(() => {
    if (!el.isConnected) return clearInterval(timer);
    const e = Math.round((Date.now() - started) / 1000);
    if (e >= 2) secs.textContent = `${e}s`;
  }, 1000);
  return el;
}

export function errorBox(err, go) {
  const actions = [];
  if (err.code === "no_api_key" || err.code === "keyInvalid" || err.code === "accessNotConfigured") {
    actions.push(h("button", { class: "btn sm", onClick: () => go("settings") }, icon("settings"), "Open settings"));
  }
  return h("div", { class: "error-box", role: "alert" }, icon("alert"),
    h("div", { class: "stack-sm" }, h("div", { class: "msg" }, err.message || String(err)), actions.length ? h("div", {}, actions) : null));
}

export function empty(title, text, ic = "search") {
  return h("div", { class: "empty" }, icon(ic), h("h3", {}, title), text ? h("div", {}, text) : null);
}

export function seg(options, value, onChange) {
  const wrap = h("div", { class: "seg", role: "tablist" });
  for (const [val, label] of options) {
    const b = h("button", { type: "button", class: val === value ? "on" : "", "aria-pressed": String(val === value) }, label);
    b.addEventListener("click", () => {
      for (const c of wrap.children) { c.classList.remove("on"); c.setAttribute("aria-pressed", "false"); }
      b.classList.add("on");
      b.setAttribute("aria-pressed", "true");
      onChange(val);
    });
    wrap.appendChild(b);
  }
  return wrap;
}

export function select(options, value, attrs = {}) {
  const el = h("select", attrs);
  for (const opt of options) {
    const [val, label] = Array.isArray(opt) ? opt : [opt, opt];
    el.appendChild(h("option", { value: val, selected: String(val) === String(value) }, label));
  }
  return el;
}

export function field(label, control, hint, cls) {
  return h("label", { class: "field" + (cls ? " " + cls : "") }, h("span", {}, label, hint ? h("span", { class: "hint" }, " · " + hint) : null), control);
}

export function tabs(defs, initial, onChange) {
  // defs: [{id, label, count, render: () => Node}]
  const bar = h("div", { class: "tabs", role: "tablist" });
  const body = h("div", {});
  let current = initial || defs[0].id;
  const show = (id) => {
    current = id;
    for (const b of bar.children) b.classList.toggle("on", b.dataset.id === id);
    clear(body);
    const def = defs.find((d) => d.id === id);
    if (def) body.appendChild(def.render());
    if (onChange) onChange(id);
  };
  for (const d of defs) {
    bar.appendChild(h("button", { type: "button", role: "tab", dataset: { id: d.id }, onClick: () => show(d.id) },
      d.label, d.count !== undefined ? h("span", { class: "count" }, `(${d.count})`) : null));
  }
  show(current);
  return h("div", {}, bar, body);
}

export function chips(items, opts = {}) {
  return h("div", { class: "chips" }, items.map((it) => {
    const text = typeof it === "string" ? it : it.text;
    const count = typeof it === "string" ? null : it.count;
    const c = h("span", { class: "chip" + (opts.onClick ? " link" : ""), title: opts.title || null },
      text, count !== null && count !== undefined ? h("span", { class: "count" }, `×${count}`) : null);
    if (opts.onClick) c.addEventListener("click", () => opts.onClick(text));
    return c;
  }));
}

export function img(src, alt, cls) {
  const el = h("img", { src, alt: alt || "", loading: "lazy", class: cls || null, referrerpolicy: "no-referrer" });
  el.addEventListener("error", () => { el.style.visibility = "hidden"; }, { once: true });
  return el;
}

export function avatar(src, name, small) {
  const box = h("div", { class: "avatar" + (small ? " sm" : "") }, (name || "?").trim().slice(0, 1).toUpperCase());
  if (src) {
    const im = h("img", { src, alt: "", loading: "lazy", referrerpolicy: "no-referrer" });
    im.addEventListener("load", () => { clear(box); box.appendChild(im); }, { once: true });
  }
  return box;
}

export function scoreRing(score, label) {
  const r = 36, c = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(100, score || 0)) / 100;
  const color = score >= 70 ? "var(--good)" : score >= 50 ? "var(--warning)" : "var(--critical)";
  return h("div", { class: "ring", role: "img", "aria-label": `${label || "Score"} ${score} out of 100` },
    s("svg", { viewBox: "0 0 84 84" },
      s("circle", { cx: 42, cy: 42, r, fill: "none", stroke: "var(--surface-3)", "stroke-width": 8 }),
      s("circle", { cx: 42, cy: 42, r, fill: "none", stroke: color, "stroke-width": 8, "stroke-linecap": "round",
        "stroke-dasharray": `${c * pct} ${c}` })),
    h("div", { class: "v" }, h("div", {}, String(Math.round(score || 0)), h("small", {}, "/100"))));
}

// Sortable table: columns [{key, label, align, render(row), sort(row) , cls}]
export function dataTable(rows, columns, opts = {}) {
  let sortKey = opts.sortKey || null;
  let sortDir = opts.sortDir || -1;
  const table = h("table", { class: "tbl" + (opts.cls ? " " + opts.cls : "") });
  const thead = h("thead");
  const tbody = h("tbody");
  table.append(thead, tbody);
  const draw = () => {
    clear(thead);
    clear(tbody);
    const tr = h("tr");
    for (const col of columns) {
      const sortable = !!col.sort;
      const th = h("th", { class: [col.align === "r" ? "r" : "", sortable ? "sortable" : "", col.thCls || ""].join(" ").trim(), scope: "col" },
        col.label, sortable && sortKey === col.key ? h("span", { class: "arrow" }, sortDir < 0 ? "▼" : "▲") : null);
      if (sortable) th.addEventListener("click", () => {
        if (sortKey === col.key) sortDir = -sortDir; else { sortKey = col.key; sortDir = -1; }
        draw();
      });
      tr.appendChild(th);
    }
    thead.appendChild(tr);
    let data = rows.slice();
    const col = columns.find((c) => c.key === sortKey);
    if (col && col.sort) {
      data.sort((a, b) => {
        const va = col.sort(a), vb = col.sort(b);
        if (va === vb) return 0;
        if (va === null || va === undefined) return 1;
        if (vb === null || vb === undefined) return -1;
        return (va < vb ? -1 : 1) * sortDir;
      });
    }
    for (const row of data) {
      const r = h("tr");
      for (const c of columns) r.appendChild(h("td", { class: [c.align === "r" ? "r" : "", c.cls || ""].join(" ").trim() || null }, c.render(row)));
      tbody.appendChild(r);
    }
  };
  draw();
  return h("div", { class: "table-wrap" }, table);
}

export function debounce(fn, ms) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

// ---------- tooltip ----------
const tip = () => document.getElementById("viz-tip");
export function showTip(evt, nodes) {
  const el = tip();
  clear(el);
  append(el, [nodes]);
  el.style.display = "block";
  const pad = 14;
  const w = el.offsetWidth, hgt = el.offsetHeight;
  let x = evt.clientX + pad, y = evt.clientY + pad;
  if (x + w > window.innerWidth - 8) x = evt.clientX - w - pad;
  if (y + hgt > window.innerHeight - 8) y = evt.clientY - hgt - pad;
  el.style.left = Math.max(8, x) + "px";
  el.style.top = Math.max(8, y) + "px";
}
export function hideTip() { tip().style.display = "none"; }

// ---------- charts (SVG, hand-rolled, themed with CSS variables) ----------
function niceStep(max, count = 4) {
  if (!(max > 0)) return 1;
  const raw = max / count;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const n = raw / mag;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * mag;
}

function roundedTop(x, y, w, hgt, r) {
  r = Math.max(0, Math.min(r, w / 2, hgt));
  return `M${x},${y + hgt}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + hgt}Z`;
}

function observeWidth(container, draw) {
  let last = 0;
  const run = () => {
    const w = Math.round(container.clientWidth);
    if (w && w !== last) { last = w; draw(w); }
  };
  if (typeof ResizeObserver !== "undefined") new ResizeObserver(run).observe(container);
  requestAnimationFrame(run);
}

function tableView(headers, rows) {
  return h("details", { class: "more" }, h("summary", {}, "View as table"),
    h("div", { class: "table-wrap" }, h("table", { class: "tbl" },
      h("thead", {}, h("tr", {}, headers.map((x, i) => h("th", { class: i ? "r" : "" }, x)))),
      h("tbody", {}, rows.map((r) => h("tr", {}, r.map((c, i) => h("td", { class: i ? "r" : "" }, c))))))));
}

// Column chart. data: [{label, value, color?, tip: Node[]}], opts: {height, yFmt, legend:[{label,color}], onClick}
export function columnChart(data, opts = {}) {
  const height = opts.height || 220;
  const yFmt = opts.yFmt || fmt.compact;
  const box = h("div", { class: "chart", role: "img", "aria-label": opts.label || "Column chart" });
  const wrap = h("div", {}, opts.legend && opts.legend.length > 1 ? h("div", { class: "legend" },
    opts.legend.map((l) => h("span", {}, h("i", { style: { background: l.color } }), l.label))) : null, box,
  opts.table === false ? null : tableView([opts.xName || "Item", opts.yName || "Value"], data.map((d) => [d.label, yFmt(d.value)])));
  if (!data.length) { box.appendChild(h("div", { class: "muted small" }, "No data")); return wrap; }
  observeWidth(box, (width) => {
    clear(box);
    const m = { l: 46, r: 6, t: 10, b: 26 };
    const pw = Math.max(40, width - m.l - m.r), ph = height - m.t - m.b;
    const max = Math.max(...data.map((d) => d.value || 0), opts.minMax || 0);
    const step = niceStep(max);
    const top = Math.max(step, Math.ceil(max / step) * step);
    const y = (v) => m.t + ph - (v / top) * ph;
    const band = pw / data.length;
    const bw = Math.max(1, Math.min(24, band - 2));
    const svg = s("svg", { viewBox: `0 0 ${width} ${height}`, height });
    for (let v = 0; v <= top + 1e-9; v += step) {
      svg.appendChild(s("line", { x1: m.l, x2: m.l + pw, y1: y(v), y2: y(v), class: v === 0 ? "baseline" : "gridline" }));
      svg.appendChild(s("text", { x: m.l - 8, y: y(v) + 4, "text-anchor": "end", class: "tick" }, yFmt(v)));
    }
    const labelEvery = Math.max(1, Math.ceil(data.length / Math.max(2, Math.floor(pw / 70))));
    data.forEach((d, i) => {
      const cx = m.l + band * i + band / 2;
      const bh = Math.max(d.value > 0 ? 1 : 0, ph - (y(d.value || 0) - m.t));
      const bar = s("path", { d: roundedTop(cx - bw / 2, m.t + ph - bh, bw, bh, 4), fill: d.color || "var(--series-1)", class: "bar" });
      svg.appendChild(bar);
      if (i % labelEvery === 0 && opts.xLabels !== false) {
        svg.appendChild(s("text", { x: cx, y: height - 8, "text-anchor": "middle", class: "tick" }, d.short ?? d.label));
      }
      const hit = s("rect", { x: m.l + band * i, y: m.t, width: band, height: ph, class: "hit" });
      hit.addEventListener("pointermove", (e) => { bar.classList.add("lift"); showTip(e, d.tip || [h("div", { class: "v" }, yFmt(d.value)), h("div", { class: "k" }, d.label)]); });
      hit.addEventListener("pointerleave", () => { bar.classList.remove("lift"); hideTip(); });
      if (opts.onClick) hit.addEventListener("click", () => opts.onClick(d));
      svg.appendChild(hit);
    });
    if (opts.refLine !== undefined && opts.refLine !== null && opts.refLine <= top) {
      svg.appendChild(s("line", { x1: m.l, x2: m.l + pw, y1: y(opts.refLine), y2: y(opts.refLine), stroke: "var(--ink-2)", "stroke-width": 1, opacity: 0.5 }));
      svg.appendChild(s("text", { x: m.l + pw, y: y(opts.refLine) - 4, "text-anchor": "end", class: "tick" }, opts.refLabel || ""));
    }
    box.appendChild(svg);
  });
  return wrap;
}

// Line chart over time. points: [{t (ms), v}], opts: {height, yFmt, name}
export function lineChart(points, opts = {}) {
  const height = opts.height || 200;
  const yFmt = opts.yFmt || fmt.compact;
  const box = h("div", { class: "chart", role: "img", "aria-label": opts.label || "Line chart" });
  const wrap = h("div", {}, box, tableView(["Time", opts.name || "Value"],
    points.map((p) => [new Date(p.t).toLocaleString(), yFmt(p.v)])));
  if (points.length < 2) { box.appendChild(h("div", { class: "muted small" }, "Not enough history yet")); return wrap; }
  observeWidth(box, (width) => {
    clear(box);
    const m = { l: 50, r: 56, t: 12, b: 26 };
    const pw = Math.max(40, width - m.l - m.r), ph = height - m.t - m.b;
    const t0 = points[0].t, t1 = points[points.length - 1].t;
    const vmin = Math.min(...points.map((p) => p.v)), vmax = Math.max(...points.map((p) => p.v));
    const span = vmax - vmin || Math.max(1, vmax * 0.1);
    const step = niceStep(span);
    const lo = Math.max(0, Math.floor((vmin - span * 0.1) / step) * step);
    const hi = Math.ceil((vmax + span * 0.05) / step) * step || lo + step;
    const x = (t) => m.l + ((t - t0) / Math.max(1, t1 - t0)) * pw;
    const y = (v) => m.t + ph - ((v - lo) / Math.max(1e-9, hi - lo)) * ph;
    const svg = s("svg", { viewBox: `0 0 ${width} ${height}`, height });
    for (let v = lo; v <= hi + 1e-9; v += step) {
      svg.appendChild(s("line", { x1: m.l, x2: m.l + pw, y1: y(v), y2: y(v), class: v === lo ? "baseline" : "gridline" }));
      svg.appendChild(s("text", { x: m.l - 8, y: y(v) + 4, "text-anchor": "end", class: "tick" }, yFmt(v)));
    }
    const ticks = Math.min(5, points.length);
    for (let i = 0; i < ticks; i++) {
      const t = t0 + ((t1 - t0) * i) / Math.max(1, ticks - 1);
      const d = new Date(t);
      const label = t1 - t0 > 2 * 86400000 ? d.toLocaleDateString(undefined, { month: "short", day: "numeric" })
        : d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
      svg.appendChild(s("text", { x: x(t), y: height - 8, "text-anchor": i === 0 ? "start" : i === ticks - 1 ? "end" : "middle", class: "tick" }, label));
    }
    const path = points.map((p, i) => `${i ? "L" : "M"}${x(p.t).toFixed(1)},${y(p.v).toFixed(1)}`).join("");
    svg.appendChild(s("path", { d: `${path}L${x(t1)},${m.t + ph}L${x(t0)},${m.t + ph}Z`, fill: "var(--series-1)", opacity: 0.1 }));
    svg.appendChild(s("path", { d: path, class: "line", stroke: "var(--series-1)" }));
    const last = points[points.length - 1];
    svg.appendChild(s("circle", { cx: x(last.t), cy: y(last.v), r: 4, fill: "var(--series-1)", stroke: "var(--surface)", "stroke-width": 2 }));
    svg.appendChild(s("text", { x: x(last.t) + 8, y: y(last.v) + 4, class: "endlabel" }, yFmt(last.v)));
    const cross = s("line", { y1: m.t, y2: m.t + ph, class: "crosshair", visibility: "hidden" });
    const dot = s("circle", { r: 4, fill: "var(--series-1)", stroke: "var(--surface)", "stroke-width": 2, visibility: "hidden" });
    svg.append(cross, dot);
    const hit = s("rect", { x: m.l, y: m.t, width: pw, height: ph, class: "hit" });
    hit.addEventListener("pointermove", (e) => {
      const rect = svg.getBoundingClientRect();
      const px = ((e.clientX - rect.left) / rect.width) * width;
      let best = points[0];
      for (const p of points) if (Math.abs(x(p.t) - px) < Math.abs(x(best.t) - px)) best = p;
      cross.setAttribute("x1", x(best.t)); cross.setAttribute("x2", x(best.t)); cross.setAttribute("visibility", "visible");
      dot.setAttribute("cx", x(best.t)); dot.setAttribute("cy", y(best.v)); dot.setAttribute("visibility", "visible");
      showTip(e, [h("div", { class: "v" }, yFmt(best.v)), h("div", { class: "row-k k" }, h("i", { style: { background: "var(--series-1)" } }), opts.name || "Value"),
        h("div", { class: "k" }, new Date(best.t).toLocaleString())]);
    });
    hit.addEventListener("pointerleave", () => { cross.setAttribute("visibility", "hidden"); dot.setAttribute("visibility", "hidden"); hideTip(); });
    svg.appendChild(hit);
    box.appendChild(svg);
  });
  return wrap;
}

// Horizontal bar list for small categorical comparisons (labels + values, text in ink tokens)
export function barList(rows, opts = {}) {
  const max = Math.max(...rows.map((r) => r.value || 0), 1e-9);
  const vf = opts.fmt || ((v) => String(v));
  return h("div", { class: "bar-list" }, rows.map((r) => h("div", { class: "bar-row", title: r.title || null },
    h("div", { class: "bl" }, h("span", {}, r.label, r.sub ? h("span", { class: "muted small" }, "  " + r.sub) : null),
      h("div", { class: "track" }, h("i", { style: { width: `${Math.max(2, (100 * (r.value || 0)) / max)}%` } }))),
    h("div", { class: "num r", style: { textAlign: "right", fontWeight: 600 } }, vf(r.value)))));
}
