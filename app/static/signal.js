/* Recount Signal frontend. Vanilla JS, no build step, CSP 'self' (no inline styles or handlers:
   widths and CSS variables are set through the CSSOM in paint()). API contract: signal/DESIGN.md section 3. */
(function () {
  "use strict";

  /* ---------------- theme (pre-paint, per-viewer convenience only) ---------------- */
  const THEME_KEY = "recount.signal.theme";
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { if (v == null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch (e) { /* storage blocked */ } },
  };
  function applyTheme(t) {
    const el = document.documentElement;
    if (t === "light" || t === "graphite") el.dataset.theme = t; else delete el.dataset.theme;
  }
  applyTheme(store.get(THEME_KEY));

  /* ---------------- icons (lucide-style paths, stroke 1.7) ---------------- */
  const P = {
    building: '<path d="M6 22V4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v18Z"/><path d="M6 12H4a2 2 0 0 0-2 2v8h4M18 9h2a2 2 0 0 1 2 2v11h-4M10 6h4M10 10h4M10 14h4M10 18h4"/>',
    tag: '<path d="M12.6 2.6A2 2 0 0 0 11.2 2H4a2 2 0 0 0-2 2v7.2a2 2 0 0 0 .6 1.4l8.7 8.7a2.4 2.4 0 0 0 3.4 0l6.6-6.6a2.4 2.4 0 0 0 0-3.4z"/><circle cx="7.5" cy="7.5" r="1"/>',
    layers: '<path d="m12 2 10 5-10 5L2 7z"/><path d="m2 17 10 5 10-5M2 12l10 5 10-5"/>',
    calendar: '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
    coins: '<circle cx="8" cy="8" r="6"/><path d="M18.1 10.4A6 6 0 1 1 10.3 18M7 6h1v4M16.7 13.9l.7.7-2.8 2.8"/>',
    flag: '<path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1zM4 22v-7"/>',
    activity: '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
    shield: '<path d="M20 13c0 5-3.5 7.5-7.7 9a1 1 0 0 1-.7 0C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.2-2.7a1.2 1.2 0 0 1 1.6 0C14.5 3.8 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/>',
    list: '<path d="M11 6h10M11 12h10M11 18h10M3 6l1 1 2-2M3 12l1 1 2-2M3 18l1 1 2-2"/>',
    sparkles: '<path d="M9.9 15.5A2 2 0 0 0 8.5 14l-6.1-1.6a.5.5 0 0 1 0-1L8.5 9.9A2 2 0 0 0 9.9 8.5l1.6-6.1a.5.5 0 0 1 1 0l1.6 6.1a2 2 0 0 0 1.4 1.4l6.1 1.6a.5.5 0 0 1 0 1l-6.1 1.6a2 2 0 0 0-1.4 1.4l-1.6 6.1a.5.5 0 0 1-1 0z"/><path d="M20 3v4M22 5h-4"/>',
    history: '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5M12 7v5l4 2"/>',
    chevron: '<path d="m6 9 6 6 6-6"/>',
    x: '<path d="M18 6 6 18M6 6l12 12"/>',
    search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    sliders: '<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6"/>',
    info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>',
    alert: '<path d="m21.7 18-8-14a2 2 0 0 0-3.4 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.7-3"/><path d="M12 9v4M12 17h.01"/>',
    check: '<path d="M20 6 9 17l-5-5"/>',
    checkCircle: '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>',
    expand: '<path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/>',
    copy: '<rect x="8" y="8" width="14" height="14" rx="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M6.3 17.7l-1.4 1.4M19.1 4.9l-1.4 1.4"/>',
    moon: '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
    monitor: '<rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8M12 17v4"/>',
    arrowUp: '<path d="m5 12 7-7 7 7M12 19V5"/>',
    arrowRight: '<path d="M5 12h14M12 5l7 7-7 7"/>',
    funds: '<path d="M3 3v18h18"/><path d="M18 17V9M13 17V5M8 17v-3"/>',
    user: '<circle cx="12" cy="8" r="4"/><path d="M4 21c.9-4 4-6 8-6s7.1 2 8 6"/>',
    target: '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>',
    book: '<path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20"/>',
    flask: '<path d="M9 3h6M10 3v6L4.5 18.5A1.7 1.7 0 0 0 6 21h12a1.7 1.7 0 0 0 1.5-2.5L14 9V3"/><path d="M7 15h10"/>',
    hash: '<path d="M4 9h16M4 15h16M10 3 8 21M16 3l-2 18"/>',
    link: '<path d="M9 17H7A5 5 0 0 1 7 7h2M15 7h2a5 5 0 1 1 0 10h-2M8 12h8"/>',
    filter: '<path d="M22 3H2l8 9.5V19l4 2v-8.5z"/>',
    reset: '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/>',
  };
  const ic = (n, extra) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"${extra ? " " + extra : ""}>${P[n] || ""}</svg>`;

  /* ---------------- helpers ---------------- */
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const isNum = (x) => typeof x === "number" && isFinite(x);
  const fmtInt = (n) => (isNum(n) ? Math.round(n).toLocaleString("en-US") : "");
  const fmt2 = (n) => (isNum(n) ? n.toFixed(2) : "");
  const fmtW = (n) => (isNum(n) ? n.toFixed(2) : "0.00");
  const fmtM = (x) => (!isNum(x) ? "" : x >= 100 ? x.toFixed(0) : x >= 10 ? x.toFixed(1) : x.toFixed(2));
  const fmtPts = (p) => (!isNum(p) ? "" : (p > 0 ? "+" : p < 0 ? "−" : "") + Math.abs(p).toFixed(1));
  const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
  const plural = (n, a, b) => `${fmtInt(n)} ${n === 1 ? a : b || a + "s"}`;
  const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
  const noDash = (s) => String(s == null ? "" : s).replace(/[\u2013\u2014]/g, ",");

  function flagEmoji(code) {
    if (!/^[A-Z]{2}$/.test(code || "")) return "";
    return String.fromCodePoint(...[...code].map((c) => 0x1f1e6 + c.charCodeAt(0) - 65));
  }
  function cc(country) {
    const code = country && (country.code || (typeof country === "string" ? country : ""));
    if (!code || code === "XX") return '<span class="country-code country-code--unknown" title="Country unknown in Cala data">XX</span>';
    const name = (country && country.name) || code;
    const tip = name + (code === "US" ? " · Mostly co-investments of European funds" : "");
    return `<span class="country-code" title="${esc(tip)}"><span class="flag" aria-hidden="true">${(country && country.flag) || flagEmoji(code)}</span>${esc(code)}</span>`;
  }
  function stageLabel(s) {
    if (!s) return "";
    let t = String(s).replace(/[_]/g, " ").replace(/-/g, " ").trim().toLowerCase();
    if (t === "pre seed" || t === "preseed") return "Pre-seed";
    const m = t.match(/^series ([a-z])(\+?)$/);
    if (m) return "Series " + m[1].toUpperCase() + m[2];
    return t.charAt(0).toUpperCase() + t.slice(1);
  }
  function valueLabel(key, v) {
    if (v === "full_history") return "Full history";
    if (v === "investor_first") return "Seen via investors";
    if (key === "last_stage" || key === "stage") return stageLabel(v);
    if (key === "band") return BAND_NAME[v] || v;
    if (key === "evidence_band") return ({ solid: "Solid", some: "Some", thin: "Thin" })[v] || v;
    if (typeof v === "string") return v.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
    return String(v);
  }
  function dateCell(d, prec) {
    if (!d) return "";
    return `<span class="num" title="${esc(prec ? "Dated to " + prec : "")}">${esc(d)}</span>`;
  }

  /* Width and CSS variables can't be inline (CSP style-src 'self'); set them through the CSSOM. */
  function paint(root) {
    $$("[data-w]", root).forEach((e) => { e.style.width = clamp(+e.dataset.w || 0, 0, 100) + "%"; });
    $$("[data-i]", root).forEach((e) => e.style.setProperty("--i", e.dataset.i));
    $$("[data-flex]", root).forEach((e) => { e.style.flex = `${Math.max(+e.dataset.flex || 0, 0.004)} 1 0`; });
    $$("input[type=range]", root).forEach(setRangeFill);
  }
  function setRangeFill(r) {
    const min = +r.min || 0, max = +r.max || 100;
    r.style.setProperty("--p", ((+r.value - min) / (max - min || 1)) * 100 + "%");
  }

  async function api(path, opts) {
    opts = opts || {};
    const headers = { Accept: "application/json" };
    if (opts.body) headers["Content-Type"] = "application/json";
    const r = await fetch(path, { credentials: "same-origin", ...opts, headers });
    let j = null;
    try { j = await r.json(); } catch (e) { /* not JSON */ }
    if (r.status === 401) {
      if (j && j.error === "user_key_rejected") { const e = new Error("user_key_rejected"); e.code = "user_key_rejected"; throw e; }
      location.href = "/login";
      throw new Error("auth");
    }
    if (!r.ok || j == null) {
      const e = new Error((j && (j.detail || j.error)) || `HTTP ${r.status}`);
      e.code = j && j.error; e.status = r.status;
      throw e;
    }
    return j;
  }

  /* ---------------- constants from the design ---------------- */
  const BAND_NAME = { strong: "Strong signal", promising: "Promising, thin data", watch: "Watch", low: "Low", not_enough_data: "Not enough data" };
  const BAND_RULE = {
    strong: "Top 10%, solid data",
    promising: "Top 10%, thin data",
    watch: "Top 40%",
    low: "Bottom 60%",
    not_enough_data: "No sized round to compare",
  };
  const LAB_TXT = { Kept: "Tested: kept", Noise: "Tested: noise", "Not testable": "Not testable" };
  const LAB_CLS = { Kept: "chip--teal", Noise: "chip--grey", "Not testable": "chip--hatch" };
  const labChip = (verdict) => verdict ? `<a class="chip ${LAB_CLS[verdict] || "chip--grey"} chip--link" href="#/lab" title="Held-out test result. Open the Lab">${esc(LAB_TXT[verdict] || verdict)}</a>` : "";
  const TIER = { measured: "Measured", thesis: "Your thesis", conditional: "Only with a sector query" };
  const VIEWS = ["companies", "funds", "founders"];
  const ENTITY = { companies: "company", funds: "fund", founders: "founder" };
  const EXAMPLES = {
    companies: ["A good company in the fintech space", "Nordic seed companies that could raise a Series A", "Resilient companies that raised in the 2022 downturn", "Backed by operator angels"],
    funds: ["Funds that actively lead seed rounds", "Nordic funds with exit receipts"],
    founders: ["Founders who used to work at Google", "Founders of Finnish companies"],
  };
  const MONTH_KEYS = ["raised_within_months", "lead_active_at_stage"];
  const DEFAULT_ON = ["hide_duplicates", "exclude_acquired", "exclude_public_bodies", "exclude_disputed", "fund_queried_only", "hide_twin_links"];

  /* ---------------- state ---------------- */
  const S = {
    meta: null, metaErr: null,
    route: { view: "companies", id: null, tab: "overview", page: null },
    fv: { companies: [], funds: [], founders: [] },
    weights: {}, weightBy: {}, thesis: false,
    sort: { companies: "score:desc", funds: "score:desc", founders: "score:desc" },
    fairRank: false,
    list: { companies: null, funds: null, founders: null },
    rows: { companies: [], funds: [], founders: [] },
    listErr: {}, loading: {}, seq: 0,
    sel: -1,
    chat: { companies: null, funds: null, founders: null },
    chatBusy: false, chatErr: null, chatMsg: "",
    userKey: "",
    detail: new Map(),
    bt: null, btErr: null, btOutcome: "next_round_24m", btSplit: "held_out",
    lab: null, labErr: null, labFilter: "all",
    openGroups: new Set(), railQ: "", railSheet: false,
    layer: null,
  };

  /* ---------------- catalogue access ---------------- */
  const catalogue = () => (S.meta && S.meta.filters) || [];
  function specsFor(view) {
    const ent = ENTITY[view];
    return catalogue().filter((f) => {
      if (f.view) return f.view === view;
      const e = f.entity || ["company"];
      return (Array.isArray(e) ? e : [e]).some((x) => x === ent || x === view || x === "all");
    });
  }
  function spec(view, key) { return specsFor(view).find((f) => f.key === key) || catalogue().find((f) => f.key === key); }
  const ftype = (f) => String((f && f.type) || "text").replace(/-/g, "_");
  const optVal = (o) => (o && typeof o === "object" ? o.value : o);
  const optCount = (o) => (o && typeof o === "object" ? o.count : null);
  const optLabel = (key, o) => (o && typeof o === "object" && o.label) || valueLabel(key, optVal(o));
  function covOf(f) {
    const c = (f && f.coverage) || {};
    const pct = isNum(c.pct) ? c.pct : c.of ? (100 * c.n) / c.of : null;
    return { n: c.n, of: c.of, pct, low: !!(f && f.low_coverage) || (isNum(pct) && pct < 25) };
  }
  function isDefaultOn(f) {
    if (f && f.default && typeof f.default === "object") return f.default.op === "is_true";
    if (f && typeof f.default === "boolean") return f.default;
    return DEFAULT_ON.includes(f && f.key);
  }
  function getF(view, key) { return S.fv[view].find((x) => x.key === key); }
  function setF(view, key, op, value, by) {
    const list = S.fv[view].filter((x) => x.key !== key);
    if (op) list.push({ key, op, value, by: by || "you" });
    S.fv[view] = list;
  }
  const activeFilters = (view) => S.fv[view].map((x) => ({ key: x.key, op: x.op, value: x.value }));
  function filterText(view, x) {
    const f = spec(view, x.key);
    const label = (f && f.label) || valueLabel("", x.key);
    const v = x.value;
    let val;
    if (x.op === "is_true") val = "yes";
    else if (x.op === "is_false") val = "no";
    else if (Array.isArray(v)) val = x.op === "between" ? `${v[0]} to ${v[1]}` : v.map((y) => valueLabel(x.key, y)).join(", ");
    else if (v && typeof v === "object") val = v.component ? `${compLabel(v.component)} at least ${v.min}` : v.stage ? `${stageLabel(v.stage)} at least ${v.min}` : JSON.stringify(v);
    else val = (x.op === "gte" ? "at least " : x.op === "lte" ? "at most " : x.op === "not_in" ? "not " : "") + valueLabel(x.key, v);
    return `${label}: ${val}`;
  }
  const comps = () => (S.meta && S.meta.components) || [];
  const compLabel = (k) => { const c = comps().find((x) => x.key === k); return c ? c.label : valueLabel("", k); };
  const mode = () => (S.thesis ? "thesis" : "size");
  const effWeights = () => {
    const l = S.list.companies;
    return (l && l.meta && l.meta.weights_effective) || null;
  };
  function rawWeight(k) {
    if (k in S.weights) return S.weights[k];
    const c = comps().find((x) => x.key === k);
    return c ? c.default_weight || 0 : 0;
  }

  /* ---------------- routing ---------------- */
  function parseHash() {
    const parts = (location.hash.replace(/^#\/?/, "") || "companies").split("/").map(decodeURIComponent);
    const head = parts[0];
    if (head === "backtest" || head === "lab" || head === "method") return { page: head, view: S.route.view || "companies" };
    const view = VIEWS.includes(head) ? head : "companies";
    return { view, id: parts[1] || null, tab: parts[2] || "overview", page: null };
  }
  const entHref = (view, id, tab) => `#/${view}/${encodeURIComponent(id)}${tab && tab !== "overview" ? "/" + tab : ""}`;

  function onRoute() {
    const prev = S.route;
    const r = parseHash();
    S.route = r;
    renderNav();
    if (r.page) {
      closeLayer();
      if (r.page === "backtest") renderBacktest(); else if (r.page === "lab") renderLab(); else renderMethod();
      window.scrollTo(0, 0);
      return;
    }
    const viewChanged = prev.page || prev.view !== r.view || !$("#sheet-host");
    if (viewChanged) { S.sel = -1; renderView(); if (!S.list[r.view] && !S.loading[r.view]) loadList(r.view); }
    if (r.id) openDetail(r.view, r.id, r.tab); else if (S.layer && S.layer.kind === "detail") closeLayer(true);
  }

  /* ---------------- top nav, tabbar, theme ---------------- */
  function renderNav() {
    const c = (S.meta && S.meta.counts) || {};
    const items = [
      ["companies", "Companies", c.companies, "building"],
      ["funds", "Funds", c.funds_queried, "funds"],
      ["founders", "Founders", c.founders, "user"],
      ["backtest", "Backtest", null, "target"],
      ["lab", "Lab", null, "flask"],
      ["method", "Method", null, "book"],
    ];
    const cur = S.route.page || S.route.view;
    $("#nav").innerHTML = '<span class="seg__ind" aria-hidden="true"></span>' + items.map(([k, l, n]) =>
      `<a class="seg__btn" href="#/${k}"${cur === k ? ' aria-current="page"' : ""}>${l}${isNum(n) ? ` <span class="seg__count">${fmtInt(n)}</span>` : ""}</a>`).join("");
    $("#tabbar").innerHTML = items.map(([k, l, , i]) => `<a href="#/${k}"${cur === k ? ' aria-current="page"' : ""}>${ic(i)}<span>${l}</span></a>`).join("");
    requestAnimationFrame(() => moveInd($("#nav")));
  }
  function moveInd(seg) {
    if (!seg) return;
    const ind = $(".seg__ind", seg);
    const on = $('[aria-current="page"],[aria-pressed="true"]', seg);
    if (!ind) return;
    if (!on || !on.offsetWidth) { ind.style.opacity = "0"; return; }
    ind.style.width = on.offsetWidth + "px";
    ind.style.transform = `translateX(${on.offsetLeft}px)`;
    ind.style.opacity = "1";
  }
  function renderTheme() {
    const t = store.get(THEME_KEY) || "system";
    const opts = [["light", "sun", "Light"], ["graphite", "moon", "Graphite (dark)"], ["system", "monitor", "Follow system"]];
    $("#theme-seg").innerHTML = opts.map(([k, i, l]) => `<button class="seg__btn" type="button" data-theme-set="${k}" aria-label="${l}" title="${l}" aria-pressed="${t === k}">${ic(i)}</button>`).join("");
  }

  /* ---------------- view shell ---------------- */
  function headerMeta() {
    const m = S.meta || {};
    const l = S.list[S.route.view];
    const lm = (l && l.meta) || {};
    const c = m.counts || {};
    const bits = [];
    if (m.as_of) bits.push(`Data as of <b>${esc(m.as_of)}</b>`);
    if (S.route.view === "funds" && isNum(c.funds)) bits.push(`${fmtInt(c.funds_queried)} scored of ${fmtInt(c.funds)} investors`);
    else if (S.route.view === "founders" && isNum(c.founders)) bits.push(`${fmtInt(c.founders_scoreable)} scoreable of ${fmtInt(c.founders)}`);
    return bits.map((b) => `<span>${b}</span>`).join('<span class="sep-dot" aria-hidden="true"></span>');
  }
  const TITLES = {
    companies: ["Companies", "Ranked on round size for its stage. Click a row for the full story."],
    funds: ["Funds", "How actively each fund leads, not how well it picks."],
    founders: ["Founders", "Founder data in Cala is thin. Most show what is missing."],
  };

  function renderView() {
    const v = S.route.view;
    const [title, expl] = TITLES[v];
    $("#main").innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-header__title">${title}</h1>
          <div class="page-header__meta" id="hmeta">${headerMeta()}</div>
        </div>
        <div class="page-header__actions">
          <button class="btn" type="button" data-act="why">${ic("info")}Why these</button>
          ${v === "companies" ? `<button class="btn btn--primary" type="button" data-act="weights">${ic("sliders")}Weights <span class="kbd">W</span></button>` : ""}
        </div>
      </div>
      <p class="explainer" id="expl">${explainer(v, expl)}</p>
      <section class="chat" id="chat" aria-label="Ask in your own words"></section>
      <section class="hero" id="hero" aria-label="Overview"></section>
      <div class="work">
        <aside class="rail" id="rail" aria-label="Filters"></aside>
        <section class="tablewrap" aria-label="Results">
          <div class="tbar" id="tbar"></div>
          <div id="ribbons"></div>
          <div id="sheet-host"></div>
        </section>
      </div>`;
    renderChat(); renderHero(); renderRail(); renderTable();
  }
  function explainer(v, expl) {
    return v === "companies" && S.thesis ? "Ranked on the thesis mix of 13 parts. No measured lift. Click a row for the full story." : expl;
  }
  function refreshAll() {
    if (S.route.page) return;
    const hm = $("#hmeta"); if (hm) hm.innerHTML = headerMeta();
    const ex = $("#expl"); if (ex) ex.innerHTML = explainer(S.route.view, TITLES[S.route.view][1]);
    renderChat(); renderHero(); renderRail(); renderTable();
    if (S.layer && S.layer.kind === "weights") renderWeights();
  }

  /* ---------------- chat bar ---------------- */
  function renderChat() {
    const host = $("#chat"); if (!host) return;
    const v = S.route.view;
    const res = S.chat[v];
    const ph = v === "companies" ? "What are you looking for? e.g. Nordic fintech that could raise a Series B" : v === "funds" ? "What are you looking for? e.g. funds that lead seed rounds in Finland" : "What are you looking for? e.g. founders who worked at Google";
    let out = `
      <form class="chat__form" id="chat-form" role="search">
        ${ic("sparkles", 'class="chat__icon"')}
        <label class="sr-only" for="chat-in">What are you looking for?</label>
        <input class="chat__input" id="chat-in" name="q" autocomplete="off" maxlength="500" placeholder="${esc(ph)}" value="${esc(S.chatMsg)}">
        <button class="icon-btn chat__key" type="button" data-act="key" title="${S.userKey ? "Using your Gemini key" : "Use your own Gemini key"}" aria-label="Use your own Gemini key" aria-pressed="${!!S.userKey}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="7.5" cy="15.5" r="4.5"/><path d="m10.7 12.3 9.3-9.3M17 6l3 3M14.5 8.5l2 2"/></svg></button>
        <button class="btn btn--primary chat__go" type="submit"${S.chatBusy ? " disabled" : ""}>${ic("arrowUp")}<span>Ask</span><span class="kbd">↵</span></button>
      </form>`;
    if (S.chatBusy) {
      out += `<div class="chat__result"><div class="chat__thinking">${ic("sparkles", 'width="14" height="14"')}Reading your request</div><div class="chat__chips"><span class="shimmer shimmer--a"></span><span class="shimmer shimmer--b"></span><span class="shimmer shimmer--c"></span></div></div>`;
    } else if (S.chatErr) {
      out += `<div class="chat__result"><div class="ribbon ribbon--red">${ic("alert")}<span>${esc(S.chatErr)}</span></div></div>`;
    }
    const chatF = S.fv[v].filter((x) => x.by === "chat");
    const chatW = v === "companies" && S.thesis ? Object.keys(S.weightBy).filter((k) => S.weightBy[k] === "chat" && k in S.weights) : [];
    if (!S.chatBusy && res) {
      const diff = (res.weights_diff || []).filter((d) => chatW.includes(d.key));
      out += `<div class="chat__result">
        ${chatF.length || diff.length ? `<div class="chat__chips"><span class="overline">${res.source === "fallback" ? "Keyword match set" : "Gemini set"}</span>
          ${chatF.map((x) => `<span class="chip chip--outline chip--x" title="${esc(x.reason || "")}"><span class="chip__dot"></span>${esc(filterText(v, x))}<button class="chip__x" type="button" data-act="rmf" data-key="${esc(x.key)}" aria-label="Remove ${esc(filterText(v, x))}">${ic("x")}</button></span>`).join("")}
          ${diff.map((d) => `<span class="chip chip--accent chip--x">${esc(compLabel(d.key))} <span class="arrow">${fmtW(d.from)} → ${fmtW(d.to)}</span><button class="chip__x" type="button" data-act="rmw" data-key="${esc(d.key)}" aria-label="Undo weight change for ${esc(compLabel(d.key))}">${ic("x")}</button></span>`).join("")}
          <button class="linkish" type="button" data-act="reset">Reset</button></div>` : ""}
        ${(res.unmatched || []).length ? `<p class="chat__src" title="${esc(res.unmatched.map((u) => `${u.phrase}: ${noDash(u.reason)}`).join("\n"))}">Not in Cala data: ${res.unmatched.map((u) => esc(u.phrase)).join(", ")}</p>` : ""}
      </div>`;
    } else if (!S.chatBusy && !S.chatErr) {
      const g = S.meta && S.meta.gemini;
      if (g && g.server_key === false && !S.userKey) out += `<div class="chat__src chat__note">No server Gemini key here: requests use keyword matching unless you add your own key.</div>`;
      out += `<div class="chat__examples"><span class="overline">Try</span>${EXAMPLES[v].map((e) => `<button class="qchip" type="button" data-act="ask" data-q="${esc(e)}">${ic("sparkles")}${esc(e)}</button>`).join("")}</div>`;
    }
    host.innerHTML = out;
  }
  const modelName = (m) => (m ? String(m).replace(/^gemini-/i, "Gemini ").replace(/-/g, " ").replace(/\bflash\b/i, "Flash").replace(/\blite\b/i, "Lite").replace(/\bpro\b/i, "Pro") : "Gemini");

  async function ask(msg) {
    const v = S.route.view;
    msg = String(msg || "").trim();
    if (!msg) return;
    S.chatMsg = msg; S.chatBusy = true; S.chatErr = null; renderChat();
    const body = { message: msg, view: v, mode: mode(), current: { filters: activeFilters(v), weights: v === "companies" && S.thesis ? S.weights : {} } };
    if (S.userKey) body.user_api_key = S.userKey;
    try {
      const res = await api("/api/signal/chat", { method: "POST", body: JSON.stringify(body) });
      // A new question replaces what the previous answer set; your own filters stay.
      S.fv[v] = S.fv[v].filter((x) => x.by !== "chat");
      (res.filters || []).forEach((f) => { setF(v, f.key, f.op, f.value, "chat"); getF(v, f.key).reason = f.reason; });
      if (v === "companies") {
        Object.keys(S.weightBy).forEach((k) => { if (S.weightBy[k] === "chat") { delete S.weights[k]; delete S.weightBy[k]; } });
        if (S.thesis) Object.entries(res.weight_overrides || {}).forEach(([k, w]) => { if (isNum(w)) { S.weights[k] = w; S.weightBy[k] = "chat"; } });
      }
      if (res.sort && res.sort.key) S.sort[v] = `${res.sort.key}:${res.sort.dir === "asc" ? "asc" : "desc"}`;
      S.chat[v] = res;
    } catch (e) {
      S.chatErr = e.code === "user_key_rejected"
        ? "Gemini rejected your key. Nothing was sent with the server key instead. Check the key, or remove it to use the server key."
        : e.code === "empty_message" ? "Type what you are looking for first." : `Could not read the request: ${e.message}`;
    }
    S.chatBusy = false;
    renderChat();
    loadList(v);
  }

  /* ---------------- hero row ---------------- */
  function renderHero() {
    const host = $("#hero"); if (!host) return;
    const v = S.route.view;
    const rows = S.rows[v] || [];
    const lm = (S.list[v] && S.list[v].meta) || {};
    const byServer = S.sort[v] === "score:desc" && !S.fairRank; // server order = display order, ties already broken
    const scored = rows.filter((r) => isNum(r.score)).slice();
    if (!byServer) scored.sort((a, b) => (a.rank_global != null && b.rank_global != null ? a.rank_global - b.rank_global : b.score - a.score));
    scored.forEach((r, i) => { r._pos = byServer && r.position != null ? r.position : i + 1; });
    const top = scored[0];
    const kind = v === "companies" ? "SIGNAL" : v === "funds" ? "ACTIVITY" : "FOUNDER EVIDENCE";
    let due;
    if (!S.list[v]) due = `<div class="due-card"><div class="due-card__eyebrow"><span>TOP ${kind}</span></div><p class="due-card__empty">${S.listErr[v] ? "No data yet." : "Ranking"}</p></div>`;
    else if (!top) due = `<div class="due-card"><div class="due-card__eyebrow"><span>TOP ${kind}</span><span>${fmtInt(lm.matched || 0)} match</span></div><p class="due-card__empty">${v === "founders" ? "No founder in this set has enough data for a score. Their companies are scored instead." : "Nothing in this set can be ranked. Loosen a filter."}</p></div>`;
    else {
      const fe = v === "founders" ? (top.founder_evidence || {}) : null;
      const why = v === "companies" ? (top.why_short || "") : v === "funds" ? (top.score_label || "How actively this fund leads, not how well it picks.") : `Documented: ${(fe.facts || []).join(", ")}. Counts facts, not a judgment of the founder.`;
      due = `<div class="due-card">
        <div class="due-card__eyebrow"><span>TOP ${kind}</span><span>${fmtInt(lm.matched != null ? lm.matched : rows.length)} match</span></div>
        <div class="due-card__big">${fe ? `<span class="due-card__num">${fe.k}</span><span class="due-card__of">of ${fe.of || 4} facts</span>` : `<span class="due-card__num">${top.score}</span><span class="due-card__of">of 100</span>`}</div>
        <a class="due-card__name" href="${entHref(v, top.id)}">${cc(top.country)}<span>${esc(top.name)}</span></a>
        <p class="due-card__why">${esc(noDash(why))}</p>
        <ul class="due-card__list">${scored.slice(1, 4).map((r, i) => `<li><a href="${entHref(v, r.id)}"><span class="due-card__rank">${String(r._pos).padStart(2, "0")}</span><span class="due-card__lname">${esc(r.name)}</span><span class="due-card__score">${fe ? `${(r.founder_evidence || {}).k} of 4` : r.score}</span></a></li>`).join("")}</ul>
      </div>`;
    }
    host.innerHTML = due + sonarPanel(v, scored) + rankedOnPanel(v);
    paint(host);
  }

  function stageWedge(s) {
    const t = String(s || "").toLowerCase().replace(/[_-]/g, " ");
    if (/pre ?seed/.test(t)) return 0;
    if (t === "seed") return 1;
    if (/series a\b|^a$/.test(t)) return 2;
    return 3;
  }
  function hashUnit(s) { let h = 2166136261; for (const c of String(s)) { h ^= c.charCodeAt(0); h = Math.imul(h, 16777619); } return ((h >>> 0) % 1000) / 1000; }
  function sonarPanel(v, scored) {
    const R = 110;
    const pts = scored.slice(0, 40);
    const rOf = (i) => 8 + (i / Math.max(pts.length - 1, 1)) * (R - 14); // by rank: scores at the top bunch up
    const wedges = v === "companies" ? ["PRE-SEED", "SEED", "SERIES A", "B AND LATER"] : null;
    let blips = "";
    pts.forEach((r, i) => {
      const w = wedges ? stageWedge(r.last_stage) : Math.floor(hashUnit(r.id + "w") * 4);
      const a = ((w * 90 + 12 + hashUnit(r.id) * 66) - 90) * Math.PI / 180;
      const rr = rOf(i);
      const ev = r.evidence && isNum(r.evidence.value) ? r.evidence.value : 0.4;
      const band = r.band || (r.score >= 70 ? "strong" : r.score >= 50 ? "watch" : "low");
      const x = (Math.cos(a) * rr).toFixed(1), y = (Math.sin(a) * rr).toFixed(1);
      blips += `<a href="${entHref(v, r.id)}" aria-label="${esc(r.name)}, score ${r.score}"><circle class="sonar__blip sonar__blip--${esc(band)}" cx="${x}" cy="${y}" r="${(2.4 + ev * 4.2).toFixed(1)}"><title>${esc(r.name)} · ${r.score}</title></circle></a>`;
      if (i < 10) blips += `<text class="sonar__num" x="${(+x + 6).toFixed(1)}" y="${(+y + 2.5).toFixed(1)}">${String(r._pos).padStart(2, "0")}</text>`;
    });
    const rings = [0.25, 0.5, 0.75].map((f) => `<circle class="sonar__ring" r="${(f * R).toFixed(1)}"/>`).join("");
    const spokes = [0, 90, 180, 270].map((d) => { const a = (d - 90) * Math.PI / 180; return `<line class="sonar__spoke" x1="0" y1="0" x2="${(Math.cos(a) * R).toFixed(1)}" y2="${(Math.sin(a) * R).toFixed(1)}"/>`; }).join("");
    const labels = (wedges || ["", "", "", ""]).map((t, i) => { const a = ((i * 90 + 45) - 90) * Math.PI / 180; return `<text class="sonar__label" text-anchor="middle" x="${(Math.cos(a) * (R + 12)).toFixed(1)}" y="${(Math.sin(a) * (R + 12) + 3).toFixed(1)}">${t}</text>`; }).join("");
    return `<div class="panel">
      <div class="panel__head"><h2 class="panel__title">Sonar</h2><span class="panel__meta">Top ${pts.length}</span></div>
      <div class="panel__body">
        <div class="sonar"><svg viewBox="-135 -135 270 270" role="img" aria-label="Top ${pts.length} by rank, closer to centre is higher">
          <defs><linearGradient id="sweep-g" x1="0" y1="0" x2="1" y2="0"><stop offset="0" class="sweep-a"/><stop offset="1" class="sweep-b"/></linearGradient></defs>
          <g class="sonar__sweep"><path d="M0 0 L${R} 0 A${R} ${R} 0 0 1 ${(Math.cos(0.7) * R).toFixed(1)} ${(Math.sin(0.7) * R).toFixed(1)} Z" fill="url(#sweep-g)"/></g>
          <circle class="sonar__ring" r="${R}"/>${rings}${spokes}${labels}${blips}
          <circle r="2" class="sonar__blip--strong"/>
        </svg></div>
        <div class="legend"><span>Closer = higher rank</span></div>
      </div></div>`;
  }

  function rankedOnPanel(v) {
    const rows = [];
    S.fv[v].forEach((x) => { // active filters only; the ranking itself is not a coverage row
      const f = spec(v, x.key); if (!f) return;
      const c = covOf(f);
      rows.push({ name: f.label || x.key, n: c.n, of: c.of, pct: c.pct, low: c.low });
    });
    const body = rows.map((r, i) => `<li class="cov-row${r.low ? " cov-row--low" : ""}">
        <span class="cov-row__dot${r.low ? " cov-row__dot--low" : !r.n ? " cov-row__dot--zero" : ""}"></span>
        <span class="cov-row__name" title="${esc(r.name)}">${esc(r.name)}</span>
        <span class="cov-row__n">${isNum(r.n) ? `${fmtInt(r.n)} / ${fmtInt(r.of)}` : ""}</span>
        <span class="cov-row__bar"><i data-w="${isNum(r.pct) ? r.pct.toFixed(1) : 0}" data-i="${i}"></i></span></li>`).join("");
    const head = v !== "companies" ? ""
      : S.thesis ? `<p class="ranked-on">Ranked on: <b>Thesis mix</b> <span class="chip chip--amber">No measured lift</span></p>`
      : `<p class="ranked-on">Ranked on: <b>Size for stage</b></p><p class="ranked-on__line">Held up in our test of 35 signals. <a class="link" href="#/lab">See Lab</a></p>`;
    const list = body ? `<p class="overline cov-head">FILTER COVERAGE</p><ul class="cov-list">${body}</ul>`
      : v === "companies" ? "" : `<ul class="cov-list"><li class="muted">No filter set.</li></ul>`;
    return `<div class="panel panel--cov">
      <div class="panel__head"><h2 class="panel__title">${v === "companies" ? "Ranking" : "Coverage"}</h2></div>
      <div class="panel__body">${head}${list}</div></div>`;
  }

  /* ---------------- filter rail ---------------- */
  function renderRail() {
    const host = $("#rail"); if (!host) return;
    const v = S.route.view;
    const specs = specsFor(v);
    const q = S.railQ.trim().toLowerCase();
    const groups = [];
    specs.forEach((f) => {
      const g = f.group || "Other";
      let gr = groups.find((x) => x.name === g);
      if (!gr) { gr = { name: g, items: [] }; groups.push(gr); }
      if (!q || (f.label || f.key).toLowerCase().includes(q)) gr.items.push(f);
    });
    if (!S.openGroups.size && groups[0]) S.openGroups.add(v + ":" + groups[0].name);
    const matched = S.list[v] && S.list[v].meta && S.list[v].meta.matched;
    host.className = "rail" + (S.railSheet ? " is-sheet" : "");
    const nUser = S.fv[v].length;
    host.innerHTML = `
      <div class="rail__head">
        <div class="rail__title"><h2>Filters${nUser ? ` <span class="fgroup__active">${nUser}</span>` : ""}</h2>${S.railSheet ? `<button class="icon-btn" type="button" data-act="rail-close" aria-label="Close filters">${ic("x")}</button>` : ""}</div>
        <div class="field-wrap">${ic("search")}<label class="sr-only" for="rail-q">Find a filter</label><input class="input input--search" id="rail-q" placeholder="Find a filter" value="${esc(S.railQ)}" autocomplete="off"></div>
      </div>
      <div class="rail__body">${S.meta ? groups.filter((g) => g.items.length).map((g, gi) => {
        const id = v + ":" + g.name;
        const open = q ? true : S.openGroups.has(id);
        const act = g.items.filter((f) => getF(v, f.key)).length;
        return `<div class="fgroup">
          <button class="fgroup__btn" type="button" data-act="fgroup" data-g="${esc(id)}" aria-expanded="${open}"><span class="fgroup__letter">${String.fromCharCode(65 + gi)}</span>${esc(g.name)}${act ? ` <span class="fgroup__active">${act}</span>` : ""}${ic("chevron")}</button>
          ${open ? `<div class="fgroup__items">${g.items.map((f) => filterRow(v, f)).join("")}</div>` : ""}
        </div>`;
      }).join("") : `<p class="frow__note">${S.metaErr ? "Filters could not load: " + esc(S.metaErr) : "Loading filters"}</p>`}</div>
      <div class="rail__foot"><button class="linkish" type="button" data-act="clear">Clear all</button><span>${isNum(matched) ? fmtInt(matched) + " match" : ""}</span></div>`;
    paint(host);
  }
  function sliderBounds(f) {
    if (isNum(f.min) && isNum(f.max)) return [f.min, f.max, f.step || (f.max - f.min <= 1 ? 0.05 : 1)];
    const l = (f.label || "").toLowerCase();
    if (/0 to 1/.test(l)) return [0, 1, 0.05];
    if (/score/.test(l)) return [0, 100, 1];
    if (/k of 4/.test(l)) return [0, 4, 1];
    if (/components/.test(l)) return [0, comps().length || 13, 1];
    if (/momentum/.test(l)) return [0, 4, 0.1];
    if (/percentile|pct/.test(l)) return [0, 100, 1];
    return [0, 100, 1];
  }
  function filterRow(v, f) {
    const cur = getF(v, f.key);
    const c = covOf(f);
    const t = ftype(f);
    const k = esc(f.key);
    let ctl = "";
    const vals = (f.values || []);
    if (t === "toggle") {
      const on = cur ? cur.op === "is_true" : isDefaultOn(f);
      ctl = `<label class="toggle"><input type="checkbox" data-f="toggle" data-key="${k}"${on ? " checked" : ""}><span class="toggle__track"></span><span>${on ? "On" : "Off"}${isDefaultOn(f) ? " (default on)" : ""}</span></label>`;
    } else if (t === "multi_select" || (t === "select" && !vals.length && /co_invested_with|warm_path_from/.test(f.key))) {
      const sel = cur && Array.isArray(cur.value) ? cur.value.map(String) : [];
      if (vals.length) {
        const showAll = S.openGroups.has("all:" + v + f.key) || vals.length <= 10;
        const shown = showAll ? vals : vals.slice(0, 8).concat(vals.slice(8).filter((o) => sel.includes(String(optVal(o)))));
        ctl = `<div class="frow__opts">${shown.map((o) => {
          const val = String(optVal(o));
          const isCountry = /country/.test(f.key) && /^[A-Z]{2}$/.test(val);
          return `<label class="check"><input type="checkbox" data-f="multi" data-key="${k}" value="${esc(val)}"${sel.includes(val) ? " checked" : ""}><span class="check__box">${ic("check")}</span><span class="check__label">${isCountry ? cc({ code: val }) : ""}${esc(optLabel(f.key, o))}</span>${isNum(optCount(o)) ? `<span class="check__count">${fmtInt(optCount(o))}</span>` : ""}</label>`;
        }).join("")}</div>${!showAll ? `<button class="frow__more" type="button" data-act="fmore" data-key="${k}">Show all ${vals.length}</button>` : ""}`;
      } else {
        ctl = `${sel.length ? `<div class="chat__chips">${sel.map((s) => `<span class="chip chip--outline chip--x">${esc(s)}<button class="chip__x" type="button" data-act="rmval" data-key="${k}" data-val="${esc(s)}" aria-label="Remove ${esc(s)}">${ic("x")}</button></span>`).join("")}</div>` : ""}
          <input class="input" data-f="addval" data-key="${k}" placeholder="Type a name, press Enter" autocomplete="off">`;
      }
    } else if (t === "seg") {
      const curV = cur && (Array.isArray(cur.value) ? cur.value[0] : cur.value);
      ctl = `<div class="seg seg--sm" role="group" aria-label="${esc(f.label)}"><button class="seg__btn" type="button" data-f="seg" data-key="${k}" data-val="" aria-pressed="${!cur}">Any</button>${vals.map((o) => { const val = String(optVal(o)); return `<button class="seg__btn" type="button" data-f="seg" data-key="${k}" data-val="${esc(val)}" aria-pressed="${String(curV) === val}">${esc(optLabel(f.key, o))}</button>`; }).join("")}</div>`;
    } else if (t === "slider") {
      const [mn, mx, st] = sliderBounds(f);
      const val = cur && isNum(cur.value) ? cur.value : mn;
      ctl = `<div class="wrow__slider"><input type="range" min="${mn}" max="${mx}" step="${st}" value="${val}" data-f="slider" data-key="${k}" aria-label="${esc(f.label)}"><span class="wrow__val">${cur ? "≥ " + val : "Any"}</span></div>`;
    } else if (t === "range") {
      const a = cur ? (cur.op === "between" ? cur.value[0] : cur.op === "gte" ? cur.value : "") : "";
      const b = cur ? (cur.op === "between" ? cur.value[1] : cur.op === "lte" ? cur.value : "") : "";
      const isDate = /date/.test(f.key);
      ctl = `<div class="frow__range"><input class="input num" data-f="range" data-end="min" data-key="${k}" inputmode="${isDate ? "text" : "decimal"}" placeholder="${isDate ? "From YYYY-MM" : "Min"}" value="${esc(a)}" aria-label="${esc(f.label)} minimum"><input class="input num" data-f="range" data-end="max" data-key="${k}" inputmode="${isDate ? "text" : "decimal"}" placeholder="${isDate ? "To YYYY-MM" : "Max"}" value="${esc(b)}" aria-label="${esc(f.label)} maximum"></div>`;
    } else if (t === "component_min") {
      const cv = cur && cur.value || {};
      ctl = `<select class="frow__select" data-f="cmp" data-key="${k}" aria-label="Component"><option value="">Pick a part of the score</option>${comps().map((c) => `<option value="${esc(c.key)}"${cv.component === c.key ? " selected" : ""}>${esc(c.label)}</option>`).join("")}</select>
        <div class="wrow__slider"><input type="range" min="0" max="1" step="0.05" value="${isNum(cv.min) ? cv.min : 0.5}" data-f="cmpmin" data-key="${k}" aria-label="Minimum value"${cv.component ? "" : " disabled"}><span class="wrow__val">${isNum(cv.min) ? "≥ " + cv.min : ""}</span></div>`;
    } else if (f.key === "fund_led_at_stage") {
      const cv = cur && cur.value || {};
      const stages = vals.length ? vals.map(optVal) : ["pre-seed", "seed", "series a", "series b"];
      ctl = `<div class="frow__range"><select class="frow__select" data-f="stagecount" data-end="stage" data-key="${k}" aria-label="Stage"><option value="">Any stage</option>${stages.map((s) => `<option value="${esc(s)}"${cv.stage === s ? " selected" : ""}>${esc(stageLabel(s))}</option>`).join("")}</select><input class="input num" data-f="stagecount" data-end="min" data-key="${k}" inputmode="numeric" placeholder="At least n" value="${esc(cv.min || "")}" aria-label="At least n"></div>`;
    } else if (t === "select") {
      const months = MONTH_KEYS.includes(f.key);
      const opts = vals.length ? vals : months ? [6, 12, 18, 24, 36, 48] : [];
      const curV = cur && (Array.isArray(cur.value) ? cur.value[0] : cur.value);
      ctl = `<select class="frow__select" data-f="select" data-key="${k}" aria-label="${esc(f.label)}"><option value="">Any</option>${opts.map((o) => { const val = String(optVal(o)); return `<option value="${esc(val)}"${String(curV) === val ? " selected" : ""}>${esc(months ? val + " months" : optLabel(f.key, o))}</option>`; }).join("")}</select>`;
    } else {
      ctl = `<input class="input" data-f="text" data-key="${k}" placeholder="Contains" value="${esc(cur ? cur.value : "")}" autocomplete="off" aria-label="${esc(f.label)}">`;
    }
    return `<div class="frow${cur ? " is-active" : ""}" data-key="${k}">
      <div class="frow__top"><span class="frow__label">${esc(f.label || f.key)}</span>${c.low ? '<span class="chip chip--amber">Low coverage</span>' : ""}${cur ? `<button class="frow__clear" type="button" data-act="rmf" data-key="${k}">Clear</button>` : ""}</div>
      <div class="frow__cov" title="${isNum(c.n) ? `${fmtInt(c.n)} of ${fmtInt(c.of)} have this data` : "Coverage not measured"}${f.source ? " · source: " + esc(f.source) : ""}"><span class="cbar${c.low ? " cbar--low" : ""}"><i data-w="${isNum(c.pct) ? c.pct : 0}"></i></span><span class="frow__pct">${isNum(c.pct) ? c.pct.toFixed(1) + "%" : ""}</span><span class="frow__pct">${isNum(c.n) ? fmtInt(c.n) : ""}</span></div>
      <div class="frow__ctl">${ctl}</div>
      ${f.note ? `<p class="frow__note">${esc(noDash(f.note))}</p>` : ""}
    </div>`;
  }
  const parseNumOrDate = (s, key) => { s = String(s).trim(); if (!s) return null; if (/date/.test(key)) return s; const n = Number(s.replace(",", ".")); return isFinite(n) ? n : null; };
  function onFilterInput(el, commit) {
    const v = S.route.view, key = el.dataset.key, kind = el.dataset.f;
    const f = spec(v, key);
    if (kind === "toggle") {
      const on = el.checked;
      if (on === isDefaultOn(f)) setF(v, key, null); else setF(v, key, on ? "is_true" : "is_false", on);
    } else if (kind === "multi") {
      const cur = getF(v, key);
      const sel = new Set(cur && Array.isArray(cur.value) ? cur.value.map(String) : []);
      if (el.checked) sel.add(el.value); else sel.delete(el.value);
      setF(v, key, sel.size ? "in" : null, Array.from(sel));
    } else if (kind === "seg") {
      setF(v, key, el.dataset.val ? "eq" : null, el.dataset.val);
    } else if (kind === "slider") {
      const val = +el.value;
      setRangeFill(el);
      const out = el.parentElement.querySelector(".wrow__val");
      const [mn] = sliderBounds(f);
      if (out) out.textContent = val > mn ? "≥ " + val : "Any";
      if (!commit) return;
      setF(v, key, val > mn ? "gte" : null, val);
    } else if (kind === "range") {
      const row = el.closest(".frow__range");
      const a = parseNumOrDate($('[data-end=min]', row).value, key), b = parseNumOrDate($('[data-end=max]', row).value, key);
      if (a != null && b != null) setF(v, key, "between", [a, b]);
      else if (a != null) setF(v, key, "gte", a);
      else if (b != null) setF(v, key, "lte", b);
      else setF(v, key, null);
    } else if (kind === "select") {
      const val = el.value;
      const months = MONTH_KEYS.includes(key);
      setF(v, key, val ? (months ? "lte" : "eq") : null, val === "" ? null : months ? +val : val);
    } else if (kind === "text") {
      const val = el.value.trim();
      setF(v, key, val ? "contains" : null, val);
    } else if (kind === "cmp" || kind === "cmpmin") {
      const row = el.closest(".frow__ctl");
      const comp = $("select", row).value;
      const rng = $("input[type=range]", row);
      rng.disabled = !comp; setRangeFill(rng);
      const out = $(".wrow__val", row); if (out) out.textContent = comp ? "≥ " + rng.value : "";
      if (kind === "cmpmin" && !commit) return;
      setF(v, key, comp ? "gte" : null, { component: comp, min: +rng.value });
    } else if (kind === "stagecount") {
      const row = el.closest(".frow__range");
      const st = $("select", row).value, mn = Number($("input", row).value);
      setF(v, key, st ? "gte" : null, { stage: st, min: isFinite(mn) && mn > 0 ? mn : 1 });
    }
    S.offset = 0;
    loadListSoon(v);
  }

  /* ---------------- data loading ---------------- */
  function listUrl(v, offset, limit) {
    const p = new URLSearchParams();
    const f = activeFilters(v);
    if (f.length) p.set("filters", JSON.stringify(f));
    if (v === "companies" && S.thesis) { p.set("mode", "thesis"); if (Object.keys(S.weights).length) p.set("weights", JSON.stringify(S.weights)); }
    p.set("sort", S.sort[v]);
    p.set("limit", String(limit));
    p.set("offset", String(offset));
    if (v === "companies" && S.fairRank) p.set("fair_rank", "true");
    return `/api/signal/${v}?${p}`;
  }
  async function loadList(v, append) {
    const seq = ++S.seq;
    S.loading[v] = true;
    if (!append) { S.listErr[v] = null; if (S.route.view === v) renderTable(); }
    const offset = append ? S.rows[v].length : 0;
    try {
      const d = await api(listUrl(v, offset, 50));
      if (seq !== S.seq && !append) return;
      S.list[v] = d;
      S.rows[v] = append ? S.rows[v].concat(d.rows || []) : (d.rows || []);
      if (!append) S.sel = -1;
    } catch (e) {
      if (e.message === "auth") return;
      S.listErr[v] = e.status === 400 ? `A filter was refused: ${e.message}` : e.status === 404 ? "The Signal API is not available on this server yet." : `Could not load: ${e.message}`;
    }
    S.loading[v] = false;
    if (S.route.view === v && !S.route.page) refreshAll();
  }
  const loadListSoon = debounce((v) => loadList(v), 150);

  /* ---------------- table ---------------- */
  const COLS = {
    companies: [
      { k: "#", w: "48px" },
      { k: "name", label: "Company", icon: "building", w: "minmax(170px,1.3fr)", sort: "name", pin: true },
      { k: "score", label: "Signal", icon: "activity", w: "150px", sort: "score" },
      { k: "why", label: "Why", icon: "sparkles", w: "minmax(230px,1.5fr)" },
      { k: "stage", label: "Stage", icon: "layers", w: "104px", sort: "stage" },
      { k: "sector", label: "Sector", icon: "tag", w: "minmax(110px,.8fr)" },
    ],
    funds: [
      { k: "#", w: "48px" },
      { k: "name", label: "Fund", icon: "building", w: "240px", sort: "name", pin: true },
      { k: "score", label: "Activity score", icon: "activity", w: "150px", sort: "score" },
      { k: "led24", label: "Led 24m", icon: "flag", w: "100px", sort: "led_24m", num: true },
      { k: "share", label: "Lead share", icon: "layers", w: "150px", num: true },
      { k: "lastlead", label: "Last lead", icon: "calendar", w: "120px", sort: "months_since_last_lead", num: true },
      { k: "exits", label: "Exit receipts", icon: "checkCircle", w: "130px", num: true },
      { k: "evidence", label: "Evidence", icon: "shield", w: "120px", sort: "evidence" },
      { k: "stagef", label: "Main stage", icon: "layers", w: "120px" },
      { k: "fcountry", label: "Main country", icon: "flag", w: "minmax(130px,1fr)" },
    ],
    founders: [
      { k: "#", w: "48px" },
      { k: "name", label: "Founder", icon: "user", w: "230px", sort: "name", pin: true },
      { k: "company", label: "Company", icon: "building", w: "240px" },
      { k: "title", label: "Title", icon: "tag", w: "140px" },
      { k: "fev", label: "Evidence", icon: "shield", w: "150px", sort: "founder_evidence" },
      { k: "fscore", label: "Founder score", icon: "activity", w: "190px", sort: "score" },
      { k: "cscore", label: "Company score", icon: "activity", w: "150px", sort: "company_score" },
      { k: "flags", label: "Flags", icon: "alert", w: "minmax(180px,1fr)" },
    ],
  };
  const pxOf = (w) => { const m = String(w).match(/(\d+)px/); return m ? +m[1] : 0; };

  function meter(v, cls, i) {
    if (!isNum(v)) return '<span class="nodata">No data</span>';
    return `<span class="mini-meter${cls ? " mini-meter--" + cls : ""}"><span class="mini-meter__track"><span class="mini-meter__fill" data-w="${(v * 100).toFixed(1)}" data-i="${i}"></span></span><span class="mini-meter__value">${fmt2(v)}</span></span>`;
  }
  function scoreCell(r, i, v) {
    if (!isNum(r.score)) return `<span class="nodata" title="${esc(r.score_reason || BAND_RULE.not_enough_data)}">${esc(v === "funds" ? "Seen only as a co-investor" : "Not enough data")}</span>`;
    const band = r.band || "watch";
    return `<button class="score-btn" type="button" data-act="score" data-id="${esc(r.id)}" aria-label="Score ${r.score} of 100, show the breakdown"><span class="score-badge score-badge--${esc(band)}">${r.score}</span><span class="mini-meter__track"><span class="mini-meter__fill" data-w="${r.score}" data-i="${i}"></span></span></button>`;
  }
  function cell(v, col, r, i) {
    const lr = r.last_round || {};
    switch (col.k) {
      case "#": return `<div class="sheet__td sheet__rownum">${S.fairRank && r.rank_in_cohort != null ? r.rank_in_cohort : r.position != null ? r.position : ""}</div>`;
      case "name": {
        const tip = [r.name, r.country && r.country.name, r.last_stage && stageLabel(r.last_stage)].filter(Boolean).join(" · ");
        const fl = (r.flags || []).map((f) => flagLabel(f)).filter(Boolean);
        return `<div class="sheet__td sheet__pin"><span class="sheet__name">${cc(r.country)}<a class="sheet__name-text" href="${entHref(v, r.id)}" title="${esc(tip)}" tabindex="-1">${esc(r.name)}</a>${fl.length ? `<span class="flag-dot" title="${esc(fl.join(", "))}" aria-label="${esc(fl.join(", "))}"></span>` : ""}</span></div>`;
      }
      case "sector": {
        const s = r.sector || {};
        const t = (s.tags || []).concat(s.text_tags || []);
        return `<div class="sheet__td">${t.length ? `<span class="chip ${s.source === "text_match" ? "chip--outline" : "chip--grey"}" title="${esc(t.join(", ") + (s.source === "text_match" ? " (text match, not a Cala tag)" : ""))}">${esc(t[0])}</span>` : '<span class="sheet__faint">—</span>'}</div>`;
      }
      case "stage": return `<div class="sheet__td">${r.last_stage ? esc(stageLabel(r.last_stage)) : r.sized_stage ? `<span title="Last round has no stage; last staged round">${esc(stageLabel(r.sized_stage))}</span>` : '<span class="sheet__faint">—</span>'}</div>`;
      case "date": return `<div class="sheet__td">${lr.date ? dateCell(lr.date, lr.date_precision) : '<span class="sheet__faint">Undated</span>'}</div>`;
      case "size": return `<div class="sheet__td sheet__num">${isNum(lr.amount_eur_m) ? fmtM(lr.amount_eur_m) : '<span class="sheet__faint">Undisclosed</span>'}</div>`;
      case "lead": {
        const ls = lr.leads || [];
        return `<div class="sheet__td">${ls.length ? `<span class="sheet__text" title="${esc(ls.map((x) => x.name).join(", "))}">${esc(ls[0].name)}${ls.length > 1 ? ` <span class="sheet__muted num">+${ls.length - 1}</span>` : ""}</span>` : '<span class="sheet__faint">No lead named</span>'}</div>`;
      }
      case "score": return `<div class="sheet__td">${scoreCell(r, i, v)}</div>`;
      case "evidence": return `<div class="sheet__td" title="${esc(r.evidence ? "Evidence: " + valueLabel("evidence_band", r.evidence.band) : "")}">${meter(r.evidence && r.evidence.value, "evidence", i)}</div>`;
      case "based": return `<div class="sheet__td sheet__num">${r.coverage ? `${r.coverage.k} of ${r.coverage.n}` : ""}</div>`;
      case "why": {
        const full = (r.why || []).map((x) => noDash(x.text)).join("\n");
        return `<div class="sheet__td">${r.why_short ? `<span class="sheet__why${isNum(r.score) ? "" : " sheet__faint"}" title="${esc(full || r.score_reason || "")}">${esc(noDash(r.why_short))}</span>` : `<span class="sheet__faint">${isNum(r.score) ? "Near the middle" : "Unranked"}</span>`}</div>`;
      }
      case "depth": return `<div class="sheet__td">${depthChip(r.history_depth)}</div>`;
      case "led24": return `<div class="sheet__td sheet__num">${isNum(r.led_24m) ? fmtInt(r.led_24m) : ""}${isNum(r.led_prior_24m) ? ` <span class="sheet__faint" title="prior 24 months">/ ${fmtInt(r.led_prior_24m)}</span>` : ""}</div>`;
      case "share": { const s = r.lead_share; return `<div class="sheet__td sheet__num" title="${s && isNum(s.lead_unknown) ? `${fmtInt(s.lead_unknown)} rounds with lead unknown` : ""}">${s && isNum(s.of) ? `${fmtInt(s.led)} of ${fmtInt(s.of)}` : '<span class="sheet__faint">No data</span>'}</div>`; }
      case "lastlead": return `<div class="sheet__td sheet__num">${isNum(r.months_since_last_lead) ? `${fmtInt(r.months_since_last_lead)} mo ago` : '<span class="sheet__faint">No lead on file</span>'}</div>`;
      case "exits": { const x = r.exit_receipts; return `<div class="sheet__td sheet__num">${!x || x.state === "not_checked" ? '<span class="chip chip--hatch">not checked</span>' : x.count ? fmtInt(x.count) : '<span class="sheet__faint" title="No exit found does not mean no exit">None found</span>'}</div>`; }
      case "stagef": return `<div class="sheet__td">${r.main_stage ? esc(stageLabel(r.main_stage)) : '<span class="sheet__faint">Not computed</span>'}</div>`;
      case "fcountry": return `<div class="sheet__td">${r.country ? `${cc(r.country)} <span class="sheet__text">${esc(r.country.name || "")}</span>` : ""}</div>`;
      case "company": { const c = r.company || {}; return `<div class="sheet__td"><span class="sheet__name">${cc(r.country)}${c.id ? `<a class="sheet__text link" href="${entHref("companies", c.id)}">${esc(c.name)}</a>` : `<span class="sheet__text">${esc(c.name || "")}</span>`}</span></div>`; }
      case "title": return `<div class="sheet__td">${r.title ? `<span class="sheet__text">${esc(r.title)}</span>` : '<span class="sheet__faint">No title</span>'}</div>`;
      case "fev": { const e = r.founder_evidence || {}; const k = e.k || 0, of = e.of || 4; return `<div class="sheet__td" title="${esc("Has: " + (e.facts || []).join(", ") + (e.missing && e.missing.length ? ". Missing: " + e.missing.join(", ") : ""))}"><span class="dots">${Array.from({ length: of }, (_, j) => `<i${j < k ? "" : ' class="off"'}></i>`).join("")}</span> <span class="num">${k} of ${of}</span></div>`; }
      case "fscore": return `<div class="sheet__td">${isNum(r.score) ? scoreCell(r, i, v) : `<span class="nodata">${esc(r.score_reason || "Not enough data")}</span>`}</div>`;
      case "cscore": { const c = r.company || {}; return `<div class="sheet__td" title="Company score, not a founder score">${isNum(c.score) ? `<span class="score-badge score-badge--watch">${c.score}</span>&nbsp;<span class="sheet__faint">company</span>` : '<span class="sheet__faint">Unranked</span>'}</div>`; }
      case "flags": return `<div class="sheet__td">${(r.flags || []).map(flagChip).join(" ")}${(r.cohort_tags || []).map((t) => `<span class="chip ${t.verified ? "chip--teal" : "chip--grey"}" title="${t.verified ? "Verified" : "Unverified"} cohort tag">${esc(t.tag)}</span>`).join(" ")}</div>`;
      default: return '<div class="sheet__td"></div>';
    }
  }
  function flagLabel(f) {
    const key = typeof f === "string" ? f : f && (f.key || f.flag);
    return ({ possible_duplicate: "Possible duplicate", disputed_round: "Disputed round", already_acquired: "Acquired", backer_faded: "Last lead leads less since 2022", twin_link: "Possible wrong person" })[key] || valueLabel("", key || "");
  }
  function flagChip(f) {
    const key = typeof f === "string" ? f : f && (f.key || f.flag);
    const n = f && f.n;
    const map = {
      twin_link: ["chip--red", "Possible wrong person"], possible_duplicate: ["chip--amber", "Possible duplicate"],
      disputed: ["chip--red", "Disputed round"], backer_faded: ["chip--amber", "Last lead leads less since 2022"],
      lead_desert: ["chip--amber", "Lead desert"], acquired: ["chip--violet", "Acquired"],
    };
    const [cls, label] = map[key] || ["chip--grey", valueLabel("", key)];
    return `<span class="chip ${cls}"${n ? ` title="n ${n}"` : ""}>${esc(label)}${n ? ` <span class="num">${n}</span>` : ""}</span> `;
  }
  const depthChip = (d) => d === "full_history" ? '<span class="chip chip--teal" title="Cala was asked company-first, so the round history is complete as far as Cala knows">Full history</span>'
    : d ? '<span class="chip chip--hatch" title="Seen only through investor portfolios. Rounds may be missing, so compare with care.">Via investors</span>' : "";

  function renderTable() {
    const host = $("#sheet-host"); if (!host) return;
    const v = S.route.view;
    const d = S.list[v];
    const rows = S.rows[v] || [];
    const lm = (d && d.meta) || {};
    const cols = COLS[v];
    // toolbar
    const nc = (lm.not_considered || []);
    $("#tbar").innerHTML = `
      <div class="tbar__left">
        <button class="btn btn--sm filters-btn" type="button" data-act="rail-open">${ic("filter")}Filters${S.fv[v].length ? ` <span class="seg__count">${S.fv[v].length}</span>` : ""}</button>
        <span class="tbar__meta">${d ? `<b>${fmtInt(lm.matched)}</b>&nbsp;${v}${nc.length ? `<span class="sep-dot"></span><span title="${esc(nc.map((x) => `${x.count} ${x.reason}`).join("\n"))}">${fmtInt(nc.reduce((a, x) => a + x.count, 0))} without data</span>` : ""}` : S.loading[v] ? "Ranking" : ""}</span>
        ${v === "companies" ? `<label class="toggle"><input type="checkbox" data-act="fair"${S.fairRank ? " checked" : ""}><span class="toggle__track"></span><span title="Rank within the same stage and history depth">Fair rank</span></label>` : ""}
      </div>`;
    // ribbons
    const rib = [];
    const chatWarned = new Set(((S.chat[v] && S.chat[v].coverage_warnings) || []).map((w) => w.filter));
    (lm.coverage_warnings || []).filter((w) => !chatWarned.has(w.filter)).forEach((w) => rib.push(`<div class="ribbon ribbon--amber">${ic("alert")}<span>${esc(noDash(w.text))}</span></div>`));
    if (v === "companies" && S.thesis) rib.push(`<div class="ribbon ribbon--amber">${ic("alert")}<span>Ranking: <b>thesis mix</b> of 13 parts. No measured lift over size alone. <a class="link" href="#/lab">See Lab</a></span></div>`);
    else if (v === "companies") rib.push(`<div class="ribbon ribbon--sunken">${ic("info")}<span>Ranked on round size for stage, the only signal that held up in our test. <a class="link" href="#/lab">See Lab</a></span></div>`);
    if (v === "funds") rib.push(`<div class="ribbon ribbon--sunken">${ic("info")}<span>Lead accuracy in Cala: 74% exact. No exit found does not mean no exit.</span></div>`);
    if (v === "founders") rib.push(`<div class="ribbon ribbon--sunken">${ic("info")}<span>The company score next to a founder is the company's, not theirs.</span></div>`);
    $("#ribbons").innerHTML = rib.length ? `<div class="chat__result">${rib.join("")}</div><div class="sp12"></div>` : "";

    if (S.listErr[v]) { host.innerHTML = `<div class="state state--error"><b>${esc(S.listErr[v])}</b><p>Nothing is shown instead: this page never fills in numbers it did not get from the server.</p><div><button class="btn btn--sm" type="button" data-act="retry">Try again</button></div></div>`; return; }
    const tmpl = cols.map((c) => c.w).join(" ");
    const minW = cols.reduce((s, c) => s + (pxOf(c.w) || 200), 0) + 2;
    const [sk, sd] = S.sort[v].split(":");
    const head = `<div class="sheet__row sheet__head" role="row">${cols.map((c) => {
      if (c.k === "#") return '<div class="sheet__th sheet__rownum" role="columnheader">#</div>';
      const inner = `${ic(c.icon)}<span class="sheet__th-label">${c.label}</span>`;
      return `<div class="sheet__th${c.pin ? " sheet__pin" : ""}${c.num ? " sheet__th--num" : ""}" role="columnheader"${c.sort ? ` aria-sort="${sk === c.sort ? (sd === "asc" ? "ascending" : "descending") : "none"}"` : ""}>${c.sort ? `<button class="sheet__sort" type="button" data-act="sort" data-sort="${c.sort}" aria-pressed="${sk === c.sort}" data-dir="${sk === c.sort ? sd : "desc"}">${inner}${ic("chevron", 'class="sheet__sort-icon"')}</button>` : inner}</div>`;
    }).join("")}</div>`;
    let body = "", cards = "";
    if (!d && S.loading[v]) {
      body = Array.from({ length: 10 }, () => `<div class="sheet__row" role="row">${cols.map((c) => `<div class="sheet__td${c.k === "#" ? " sheet__rownum" : c.pin ? " sheet__pin" : ""}"><span class="skel"></span></div>`).join("")}</div>`).join("");
    } else if (!rows.length) {
      body = `<div class="sheet__empty"><div class="state"><b>No ${v} match these filters.</b><p>Loosen a filter or clear the query. Filters with low coverage remove most ${v} because Cala has no data for them.</p><div><button class="btn btn--sm" type="button" data-act="clear">Clear all filters</button></div></div></div>`;
    } else {
      const grouped = v === "companies" && sk === "score" && sd === "desc";
      const gcount = {}; ((d && d.groups) || []).forEach((g) => { gcount[g.band] = g.count; });
      let lastBand = null;
      rows.forEach((r, i) => {
        if (grouped && r.band !== lastBand) {
          lastBand = r.band;
          const b = r.band || "not_enough_data";
          const rule = ((S.meta && S.meta.bands) || []).find((x) => x.key === b);
          const g = `<span class="group-dot group-dot--${esc(b)}"></span><b>${esc(BAND_NAME[b] || b)}</b><span class="num">${isNum(gcount[b]) ? fmtInt(gcount[b]) : ""}</span><span class="rule">${esc(noDash(BAND_RULE[b] || (rule && rule.rule) || ""))}</span>`;
          body += `<div class="sheet__group" role="row">${g}</div>`;
          cards += `<div class="card-group">${g}</div>`;
        }
        body += `<div class="sheet__row sheet__row--body${i === S.sel ? " is-selected" : ""}" role="row" tabindex="0" data-row="${i}" data-id="${esc(r.id)}">${cols.map((c) => cell(v, c, r, i)).join("")}</div>`;
        cards += mobileCard(v, r, i);
      });
    }
    const more = d && isNum(lm.matched) && rows.length < lm.matched ? `<div class="sheet__more"><button class="btn btn--sm" type="button" data-act="more"${S.loading[v] ? " disabled" : ""}>Show ${Math.min(50, lm.matched - rows.length)} more of ${fmtInt(lm.matched - rows.length)}</button></div>` : "";
    host.innerHTML = `<div class="sheet" id="sheet" role="grid" aria-label="${v}" aria-rowcount="${rows.length}"><div class="sheet__grid">${head}${body}${more}</div></div><div class="cards">${cards}${more}</div>`;
    const sheet = $("#sheet");
    const grid = $(".sheet__grid", sheet);
    grid.style.setProperty("--sheet-min", minW + "px");
    $$(".sheet__row", grid).forEach((row) => row.style.setProperty("--cols", tmpl));
    paint(host);
  }
  function mobileCard(v, r, i) {
    const why = v === "companies" ? r.why_short : v === "funds" ? (r.lead_share && isNum(r.lead_share.of) ? `Led ${r.lead_share.led} of ${r.lead_share.of} lead-known rounds` : "") : r.score_reason;
    const right = v === "companies" ? [stageLabel(r.last_stage || r.sized_stage), r.sector && (r.sector.tags || [])[0]].filter(Boolean).join(" · ") : v === "founders" ? (r.company && r.company.name) || "" : "";
    return `<a class="card" href="${entHref(v, r.id)}">
      <div class="card__top"><span class="card__rank">${r.position != null ? r.position : ""}</span>${cc(r.country)}<span class="card__name">${esc(r.name)}</span></div>
      <div class="card__line"><span>${isNum(r.score) ? `<span class="score-badge score-badge--${esc(r.band || "watch")}">${r.score}</span> ${esc(BAND_NAME[r.band] || "")}` : `<span class="nodata">${esc(v === "funds" ? "Seen only as a co-investor" : r.score_reason || "Not enough data")}</span>`}</span><span>${esc(right)}</span></div>
      ${why ? `<p class="card__why">${esc(noDash(why))}</p>` : ""}
    </a>`;
  }

  /* ---------------- layers: popover, drawer, palette ---------------- */
  function closeLayer(fromRoute) {
    const was = S.layer;
    S.layer = null;
    $("#layer").innerHTML = "";
    document.body.style.overflow = "";
    if (was && was.kind === "detail" && !fromRoute) {
      const v = S.route.view;
      history.pushState(null, "", `#/${v}`);
      S.route = { view: v, id: null, tab: "overview", page: null };
    }
    if (was && was.returnFocus && document.contains(was.returnFocus)) was.returnFocus.focus();
  }
  function openPop(anchor, html, wide, kind) {
    const prev = S.layer && S.layer.kind === "detail" ? S.layer : null;
    const host = $("#layer");
    $$(".pop,.pop-scrim", host).forEach((e) => e.remove());
    const pop = document.createElement("div");
    pop.className = "pop" + (wide ? " pop--wide" : "");
    pop.setAttribute("role", "dialog");
    pop.innerHTML = `<button class="icon-btn pop__close" type="button" data-act="pop-close" aria-label="Close">${ic("x")}</button>` + html;
    host.appendChild(pop);
    paint(pop);
    const r = anchor ? anchor.getBoundingClientRect() : { left: innerWidth / 2 - 210, bottom: 80, top: 80, right: innerWidth / 2 };
    const w = pop.offsetWidth, h = pop.offsetHeight;
    let left = clamp(r.left, 12, innerWidth - w - 12);
    let top = r.bottom + 8;
    if (top + h > innerHeight - 12) top = Math.max(12, r.top - h - 8);
    pop.style.left = left + "px"; pop.style.top = top + "px";
    if (!prev) S.layer = { kind: kind || "pop", returnFocus: anchor };
    else prev.pop = true;
    const f = $("input,button:not(.pop__close),a", pop); if (f) f.focus({ preventScroll: true });
    return pop;
  }
  function closePop() {
    const p = $("#layer .pop"); if (!p) return false;
    p.remove();
    if (S.layer && S.layer.kind !== "detail" && S.layer.kind !== "weights") { const rf = S.layer.returnFocus; S.layer = null; if (rf && document.contains(rf)) rf.focus(); }
    else if (S.layer) S.layer.pop = false;
    return true;
  }

  /* score breakdown (Scout "Why this score") */
  function breakdown(sc, opts) {
    opts = opts || {};
    const cs = (sc.components || []).slice();
    const n = cs.filter((c) => c.weight > 0).length, k = cs.filter((c) => c.weight > 0 && c.present).length;
    const stack = cs.filter((c) => c.weight > 0).map((c) => `<span class="stack__seg${c.present ? "" : " stack__seg--missing"}" data-flex="${c.weight}" title="${esc(c.label)}: weight ${fmtW(c.weight)}, value ${fmt2(c.value)}">${c.present ? `<i data-w="${(c.value * 100).toFixed(1)}"></i>` : ""}</span>`).join("");
    const order = cs.slice().sort((a, b) => (b.weight > 0) - (a.weight > 0) || Math.abs(b.points || 0) - Math.abs(a.points || 0) || b.weight - a.weight);
    const rows = order.map((c, i) => {
      const off = !(c.weight > 0);
      const tier = off ? "off" : c.tier;
      const pts = c.points || 0;
      return `<div class="comp${off ? " comp--off" : ""}">
        <span class="comp__label">${esc(c.label)} ${off ? "" : `<span class="tier tier--${esc(tier)}">${esc(TIER[c.tier] || c.tier)}</span>`}${labChip(c.lab_verdict)}${!c.present ? '<span class="chip chip--hatch">no data</span>' : ""}</span>
        <span class="comp__bar${c.present ? "" : " comp__bar--missing"}">${c.present ? `<i data-w="${(c.value * 100).toFixed(1)}" data-i="${i}"></i>` : ""}</span>
        ${off ? `<span class="comp__nums"><span>${esc(noDash(c.present ? c.short || fmt2(c.value) : "No data"))}</span><span>not in score</span></span>` : `<span class="comp__nums"><span>value ${c.present ? fmt2(c.value) : "0.50 (neutral)"} · weight ${fmtW(c.weight)}</span><span class="${pts > 0.05 ? "pos" : pts < -0.05 ? "neg" : ""}">${fmtPts(pts)} pts</span></span>`}
        ${!c.present ? `<span class="comp__note">${off ? "" : "No data, counted as neutral (0.5)"}${c.missing_reason ? (off ? "" : ": ") + esc(noDash(c.missing_reason)) : ""}</span>`
          : opts.full && c.peer_group ? `<span class="comp__note">Compared with ${esc(noDash(c.peer_group.label || c.peer_group.kind))}${isNum(c.peer_group.n) ? ` (n ${fmtInt(c.peer_group.n)})` : ""}</span>` : ""}
        ${opts.full ? compExtras(c) : ""}
      </div>`;
    }).join("");
    return `<div class="bd">
      <div class="bd__big"><span class="bd__num">${isNum(sc.value) ? sc.value : "n/a"}</span><span class="bd__of">of 100${isNum(sc.rank) ? ` · global rank ${fmtInt(sc.rank)} of ${fmtInt(sc.of)}` : ""}</span>${sc.band ? `<span class="chip chip--outline"><span class="group-dot group-dot--${esc(sc.band)}"></span>${esc(BAND_NAME[sc.band] || sc.band)}</span>` : ""}</div>
      ${sizeLine(sc)}
      <div class="stack" aria-hidden="true">${stack}</div>
      <p class="overline">WHY THIS SCORE</p>
      <div>${rows}</div>
      <div class="bd__foot"><span>${sc.mode === "thesis" ? `Thesis mix: based on ${k} of ${n} parts, missing ones neutral` : "Ranked on size for stage only. Other parts: 0 weight"}</span>${sc.rules_hash ? `<span class="num">${esc(sc.rules_hash)}</span>` : ""}</div>
      ${sc.formula ? `<p class="frow__note">${esc(noDash(sc.formula))}</p>` : ""}
    </div>`;
  }
  function sizeLine(sc) {
    const z = sc.size_detail;
    if (!z || !isNum(z.pct)) return "";
    const vs = isNum(z.vs_median) ? `EUR ${fmtM(z.amount_eur_m)}m vs peer median EUR ${fmtM(z.peer_median_eur_m)}m (${z.vs_median >= 10 ? Math.round(z.vs_median) : z.vs_median.toFixed(1)}x)` : "";
    return `<p class="size-line num">Exact percentile ${z.pct.toFixed(1)}${vs ? ` · ${esc(vs)}` : ""}</p>`;
  }
  function compExtras(c) {
    const bits = [];
    if (c.raw && typeof c.raw === "object") {
      const raw = Object.entries(c.raw).filter(([, x]) => x != null && typeof x !== "object").map(([a, b]) => `${a.replace(/_/g, " ")} ${isNum(b) && !Number.isInteger(b) ? +b.toFixed(3) : b}`).join(" · ");
      if (raw) bits.push(`<span class="comp__note num">raw: ${esc(raw)}</span>`);
    }
    if (c.text) bits.push(`<span class="comp__note">${esc(noDash(c.text))}</span>`);
    if (c.backtest) {
      const b = c.backtest;
      const t = [isNum(b.next_24m_auc) ? `next round AUC ${b.next_24m_auc}` : "", isNum(b.graduation_auc) ? `Series B+ AUC ${b.graduation_auc}` : "", isNum(b.n) ? `n ${fmtInt(b.n)}` : "", b.verdict || ""].filter(Boolean).join(" · ");
      if (t) bits.push(`<span class="comp__note num">Backtest: ${esc(noDash(t))}</span>`);
    }
    if (c.note) bits.push(`<span class="comp__note">${esc(noDash(c.note))}</span>`);
    if ((c.records || []).length) bits.push(`<span class="comp__note">${c.records.slice(0, 8).map(recChip).join(" ")}${c.records.length > 8 ? ` <span class="num">+${c.records.length - 8}</span>` : ""}</span>`);
    return bits.join("");
  }
  function ridOf(rec) {
    if (!rec) return null;
    const s = String(rec.source_url || rec.round_id || rec.id || "");
    const m = s.match(/(\d+)\s*$/);
    return m ? m[1] : null;
  }
  function recChip(rec, i) {
    if (rec && rec.investor) return `<a class="src" href="${entHref("funds", "f:" + rec.investor)}" title="Open this investor"><i>${(i || 0) + 1}</i>${esc(rec.investor)}</a>`;
    if (rec && rec.exited_company) return `<span class="src" title="Exit receipt of a backer"><i>${(i || 0) + 1}</i>exit: ${esc(rec.exited_company)}</span>`;
    const rid = ridOf(rec);
    const label = [rec.date, rec.stage && stageLabel(rec.stage), isNum(rec.amount_eur_m) ? `EUR ${fmtM(rec.amount_eur_m)}m` : ""].filter(Boolean).join(" · ") || `round ${rid}`;
    return rid ? `<a class="src" href="/api/record/${rid}" data-act="rec" data-rid="${rid}" title="Open the Cala record behind this"><i>${(i || 0) + 1}</i>${esc(label)}</a>` : `<span class="src"><i>${(i || 0) + 1}</i>${esc(label)}</span>`;
  }

  async function getDetail(v, id) {
    const q = v === "companies" && S.thesis ? `?mode=thesis${Object.keys(S.weights).length ? "&weights=" + encodeURIComponent(JSON.stringify(S.weights)) : ""}` : "";
    const key = v + "|" + id + q;
    if (S.detail.has(key)) return S.detail.get(key);
    const p = api(`/api/signal/${v}/${encodeURIComponent(id)}${q}`);
    S.detail.set(key, p);
    p.catch(() => S.detail.delete(key));
    return p;
  }
  async function showScorePop(btn) {
    const v = S.route.view, id = btn.dataset.id;
    const row = S.rows[v].find((r) => r.id === id) || {};
    if (v === "funds") {
      const fc = (S.meta && S.meta.fund_components) || [];
      const cs = Object.entries(row.components || {}).map(([k, val]) => { const m = fc.find((x) => x.key === k) || {}; const w = m.default_weight || 0; return { key: k, label: m.label || valueLabel("", k), tier: "measured", weight: w, present: isNum(val), value: isNum(val) ? val : 0.5, points: w * ((isNum(val) ? val : 0.5) - 0.5) * 100 }; });
      openPop(btn, `<h3>${esc(row.name)}</h3><p>${esc(row.score_label || "How actively this fund leads, not how well it picks.")}</p>${breakdown({ value: row.score, components: cs })}<p><a class="link" href="${entHref(v, id)}">Open full breakdown</a></p>`, true, "score");
      return;
    }
    const pop = openPop(btn, `<h3>${esc(row.name || "Score")}</h3><div class="chat__thinking">Loading the breakdown</div>`, true, "score");
    try {
      const d = await getDetail(v, id);
      if (!document.contains(pop)) return;
      pop.innerHTML = `<button class="icon-btn pop__close" type="button" data-act="pop-close" aria-label="Close">${ic("x")}</button><h3>${esc(d.name)}</h3>${d.score && d.score.components ? breakdown(d.score) : `<p>${esc(d.score_reason || "No breakdown")}</p>`}<p><a class="link" href="${entHref(v, id, "score")}">Open full breakdown</a></p>`;
      paint(pop);
    } catch (e) {
      if (document.contains(pop)) pop.innerHTML = `<button class="icon-btn pop__close" type="button" data-act="pop-close" aria-label="Close">${ic("x")}</button><div class="state state--error"><b>Could not load the breakdown</b><p>${esc(e.message)}</p></div>`;
    }
  }
  async function showRecord(a) {
    const rid = a.dataset.rid;
    const pop = openPop(a, `<h3>Cala record ${esc(rid)}</h3><div class="chat__thinking">Loading</div>`, true, "rec");
    try {
      const rec = await api(`/api/record/${encodeURIComponent(rid)}`);
      const rows = Object.entries(rec).filter(([, v]) => v != null && v !== "").map(([k, v]) => {
        let val = v;
        if (Array.isArray(v)) val = v.map((x) => (x && typeof x === "object" ? x.name || JSON.stringify(x) : x)).join(", ");
        else if (typeof v === "object") val = JSON.stringify(v);
        return `<tr><th>${esc(k.replace(/_/g, " "))}</th><td class="${typeof v === "number" ? "num" : ""}">${esc(String(val).slice(0, 400))}</td></tr>`;
      }).join("");
      if (document.contains(pop)) {
        pop.innerHTML = `<button class="icon-btn pop__close" type="button" data-act="pop-close" aria-label="Close">${ic("x")}</button><h3>Cala record ${esc(rid)}</h3><p>The round as Cala returned it. This is the evidence behind the score part you clicked.</p><table class="tbl">${rows}</table><p><a class="link" href="/api/record/${encodeURIComponent(rid)}" target="_blank" rel="noopener">Open raw record</a></p>`;
      }
    } catch (e) {
      if (document.contains(pop)) pop.innerHTML = `<button class="icon-btn pop__close" type="button" data-act="pop-close" aria-label="Close">${ic("x")}</button><div class="state state--error"><b>Could not load record ${esc(rid)}</b><p>${esc(e.message)}</p></div>`;
    }
  }

  /* "Why these" */
  function showWhy(btn) {
    const v = S.route.view;
    const lm = (S.list[v] && S.list[v].meta) || {};
    const m = S.meta || {};
    let html;
    if (v === "companies") {
      const eff = effWeights() || {};
      const parts = comps().map((c) => [c.label, isNum(eff[c.key]) ? eff[c.key] : rawWeight(c.key)]).filter(([, w]) => w > 0).sort((a, b) => b[1] - a[1]);
      html = S.thesis ? `<h3>Thesis mix</h3>
        <p>100 × weighted average of ${comps().length || 13} parts. Missing parts count as neutral. No measured lift over size for stage alone.</p>
        <p>Weights now: ${parts.map(([l, w]) => `${esc(l.toLowerCase())} ${fmtW(w)}`).join(", ")}.</p>
        <p><a class="link" href="#/lab">See Lab</a></p>` : `<h3>Why these, in this order</h3>
        <p>Signal = how big the last round was for its stage: its percentile among rounds of the same stage and years, 0 to 100.</p>
        <p>We tested 35 signals on held-out years. Only this one held up, and only just. The other parts stay as filters and in each company's details.</p>
        <p>No sized round means “Not enough data”, never a guess.</p>
        <p><a class="link" href="#/lab">See Lab</a></p>`;
    } else if (v === "funds") {
      const fc = m.fund_components || [];
      html = `<h3>How funds are scored</h3><p>How actively this fund leads, not how well it picks. Only the 194 funds with full round lists get a number; the other investors are seen only as co-investors.</p><p>Weights: ${fc.map((c) => `${esc((c.label || c.key).toLowerCase().replace(/_/g, " "))} ${fmtW(c.default_weight)}`).join(", ")}.</p><p>Per-fund hit rates do not survive: only a handful of funds have enough handoffs to judge. Lead accuracy in Cala: 74% exact, 89% right fund.</p>`;
    } else {
      html = `<h3>How founders are scored</h3><p>Founder evidence counts 4 kinds of fact: a dated role, an earlier company with a Cala id, a prior exit, and a person-level cohort match. A number appears only with 2 or more. Everyone else shows “Not enough data (k of 4)” and what is missing.</p><p>Founders linked through a same-name entity get a red “possible wrong person” chip and are hidden by default.</p>`;
    }
    openPop(btn, html, true, "why");
  }

  /* key popover (memory only) */
  function showKey(btn) {
    openPop(btn, `<h3>Your Gemini key</h3>
      <p>Optional. Used for your requests only, for this one call each time. Not stored on our server, never logged, and kept only in this tab's memory: a reload forgets it. Without it, the server's key is used.</p>
      <form id="key-form"><label class="sr-only" for="key-in">Gemini API key</label><input class="input" id="key-in" type="password" autocomplete="off" spellcheck="false" placeholder="${S.userKey ? "A key is set (hidden)" : "Paste a Gemini API key"}">
      <div class="chat__chips" id="key-acts"><button class="btn btn--primary btn--sm" type="submit">Use this key</button>${S.userKey ? '<button class="btn btn--sm" type="button" data-act="key-clear">Forget my key</button>' : ""}</div></form>
      <p class="frow__note">If Gemini rejects your key, the request fails and says so. The server key is never used silently instead.</p>`, false, "key");
  }
  function setKey(k) {
    S.userKey = k;
    $("#key-dot").hidden = !k;
    $("#open-key").setAttribute("aria-pressed", String(!!k));
    renderChat();
  }

  /* weights drawer */
  function openWeights(btn) {
    S.layer = { kind: "weights", returnFocus: btn };
    $("#layer").innerHTML = `<div class="scrim" data-act="close-layer"></div><aside class="drawer drawer--side" role="dialog" aria-modal="true" aria-label="Weights" id="wdrawer"></aside>`;
    renderWeights();
    const f = $("#wdrawer input"); if (f) f.focus({ preventScroll: true });
  }
  function renderWeights() {
    const host = $("#wdrawer"); if (!host) return;
    const eff = effWeights() || {};
    const lm = (S.list.companies && S.list.companies.meta) || {};
    const hasSector = !!getF("companies", "sector");
    const presets = (S.meta && S.meta.intent_presets) || [];
    const sec = (title, tiers) => {
      const cs = comps().filter((c) => tiers.includes(c.tier));
      if (!cs.length) return "";
      return `<div class="wsec"><p class="overline">${title}</p>${cs.map((c) => {
        const raw = rawWeight(c.key);
        const cap = isNum(c.cap) ? c.cap : c.tier === "measured" ? 0.6 : 0.15;
        const changed = c.key in S.weights;
        const cov = c.coverage || {};
        const covPct = cov.of ? (100 * cov.n) / cov.of : null;
        const disabled = c.tier === "conditional" && !hasSector;
        const b = c.backtest || {};
        const bt = [isNum(b.next_24m_auc) ? `next round AUC ${b.next_24m_auc}` : "", isNum(b.graduation_auc) ? `Series B+ AUC ${b.graduation_auc}` : ""].filter(Boolean).join(" · ");
        if (!S.thesis) return `<div class="wrow wrow--plain"><span class="wrow__label">${esc(c.label)}</span><span class="wrow__cov">${labChip(c.lab_verdict)}</span></div>`;
        return `<div class="wrow">
          <span class="wrow__label">${esc(c.label)}${isNum(covPct) && covPct < 25 ? '<span class="chip chip--amber">Low coverage</span>' : ""}</span>
          <span class="wrow__val${changed ? " changed" : ""}" title="Effective weight after renormalising">${fmtW(isNum(eff[c.key]) ? eff[c.key] : raw)}</span>
          <span class="wrow__slider"><input type="range" min="0" max="${cap}" step="0.01" value="${raw}" data-w-key="${esc(c.key)}" aria-label="${esc(c.label)} weight"${disabled || !S.thesis ? " disabled" : ""}><span class="wrow__cov">${labChip(c.lab_verdict)}</span></span>
          ${disabled ? '<span class="wrow__bt">Only with a sector filter. Ask for a sector or set one in the rail.</span>' : ""}
        </div>`;
      }).join("")}</div>`;
    };
    const diff = lm.weights_diff || [];
    host.innerHTML = `
      <div class="drawer__head"><div></div><div><h2 class="drawer__name">Weights</h2><p class="muted">${S.thesis ? "Ranking on the thesis mix. No measured lift." : "Ranked on size for stage only."}</p></div>
        <div class="drawer__acts"><button class="icon-btn" type="button" data-act="close-layer" aria-label="Close">${ic("x")}</button></div></div>
      <div class="drawer__body">
        <label class="toggle thesis-toggle"><input type="checkbox" data-act="thesis"${S.thesis ? " checked" : ""}><span class="toggle__track"></span><span>Thesis mix</span><span class="chip chip--amber">No measured lift</span></label>
        ${presets.length && S.thesis ? `<div class="wsec"><p class="overline">PRESETS</p><div class="seg seg--sm" role="group" aria-label="Presets"><button class="seg__btn" type="button" data-preset="">Default</button>${presets.map((p) => `<button class="seg__btn" type="button" data-preset="${esc(p.id)}" title="${esc(noDash(p.description || ""))}">${esc(p.label)}</button>`).join("")}</div></div>` : ""}
        <div>${sec("PARTS", ["measured", "thesis"])}${sec("ONLY WITH A SECTOR QUERY", ["conditional"])}</div>
        ${diff.length && S.thesis ? `<div class="wsec"><p class="overline">CHANGED FROM DEFAULT</p>${diff.map((d) => `<div class="mrow"><span>${esc(compLabel(d.key))}${d.by ? ` <span class="faint">by ${esc(d.by)}</span>` : ""}</span><span class="num">${fmtW(d.from)}</span><span class="num">${fmtW(d.to)}</span></div>`).join("")}</div>` : ""}
      </div>
      <div class="wsum"><span></span><button class="btn btn--sm" type="button" data-act="wreset">${ic("reset")}Reset</button></div>`;
    paint(host);
  }
  const reloadCompaniesSoon = debounce(() => loadList("companies"), 150);

  /* detail drawer */
  async function openDetail(v, id, tab) {
    const already = S.layer && S.layer.kind === "detail" && S.layer.id === id && S.layer.view === v;
    if (!already) {
      S.layer = { kind: "detail", id, view: v, returnFocus: document.activeElement, full: S.layer && S.layer.full };
      $("#layer").innerHTML = `<div class="scrim" data-act="close-layer"></div><section class="drawer ${S.layer.full ? "drawer--full" : "drawer--card"}" role="dialog" aria-modal="true" aria-label="Details" id="drawer"><div class="drawer__body"><span class="skel"></span></div></section>`;
      document.body.style.overflow = "hidden";
    }
    S.layer.tab = tab || "overview";
    let d;
    try { d = await getDetail(v, id); } catch (e) {
      const dr = $("#drawer"); if (dr) dr.innerHTML = `<div class="drawer__head"><div></div><div><h2 class="drawer__name">Not found</h2></div><div class="drawer__acts"><button class="icon-btn" type="button" data-act="close-layer" aria-label="Close">${ic("x")}</button></div></div><div class="drawer__body"><div class="state state--error"><b>${esc(e.status === 404 ? "No record with this id." : e.message)}</b></div></div>`;
      return;
    }
    if (!S.layer || S.layer.id !== id) return;
    renderDetail(v, d, S.layer.tab);
  }
  function renderDetail(v, d, tab) {
    const dr = $("#drawer"); if (!dr) return;
    const sc = d.score || {};
    const rankTxt = isNum(sc.rank) ? String(sc.rank).padStart(2, "0") : "";
    const tabs = v === "companies" ? [["overview", "Overview"], ["score", "Score"], ["rounds", "Rounds", (d.rounds || []).length], ["investors", "Investors", (d.investors || []).length], ["founders", "Founders", (d.founders || []).length]]
      : v === "funds" ? [["overview", "Overview"], ["portfolio", "Portfolio", (d.portfolio || []).length]] : [["overview", "Overview"]];
    const rows = d.rounds || [];
    const firstYear = d.first_year || rows.map((r) => String(r.date || "").slice(0, 4)).filter(Boolean).sort()[0];
    const lastStage = d.last_stage || (rows.slice().sort((a, b) => String(b.date).localeCompare(String(a.date)))[0] || {}).stage;
    const total = isNum(d.total_known_eur_m) ? d.total_known_eur_m : rows.reduce((s, r) => s + (isNum(r.amount_eur_m) ? r.amount_eur_m : 0), 0);
    const meta = [d.country && d.country.name, lastStage && "Last stage " + stageLabel(lastStage), total ? `Raised to date EUR ${fmtM(total)}m (lower bound)` : "", firstYear && "First round " + firstYear,
      v === "founders" && d.title, v === "founders" && d.company && d.company.name].filter(Boolean);
    const band = sc.band || d.band;
    dr.innerHTML = `
      <div class="drawer__head">
        <div class="drawer__tile${rankTxt ? "" : " drawer__tile--none"}" title="${rankTxt ? `Global rank ${sc.rank} of ${sc.of} ranked companies, before filters` : "Not ranked"}">${rankTxt || "n/a"}</div>
        <div>
          <h2 class="drawer__name">${esc(d.name)}${band ? `<span class="chip chip--accent"><span class="group-dot group-dot--${esc(band)}"></span>${esc(BAND_NAME[band] || band)}</span>` : ""}${depthChip(d.history_depth)}${(d.flags || []).map(flagChip).join("")}</h2>
          <div class="drawer__ids">${cc(d.country)}${d.entity_id ? `<span class="idpill" title="Cala entity id">${esc(String(d.entity_id).slice(0, 18))}<button type="button" data-act="copy" data-copy="${esc(d.entity_id)}" aria-label="Copy Cala id">${ic("copy")}</button></span>` : ""}</div>
          <div class="drawer__meta">${meta.map((x) => esc(x)).join('<span class="sep-dot"></span>')}</div>
        </div>
        <div class="drawer__acts"><button class="icon-btn" type="button" data-act="expand" aria-label="${S.layer.full ? "Back to card" : "Expand to full page"}">${ic("expand")}</button><button class="icon-btn" type="button" data-act="close-layer" aria-label="Close">${ic("x")}</button></div>
      </div>
      <div class="drawer__tabs">
        <div class="seg" role="tablist">${tabs.map(([k, l, n]) => `<a class="seg__btn" role="tab" href="${entHref(v, d.id, k)}" aria-selected="${tab === k}"${tab === k ? ' aria-current="page"' : ""}>${l}${isNum(n) ? ` <span class="seg__count">${n}</span>` : ""}</a>`).join("")}<span class="seg__ind" aria-hidden="true"></span></div>
      </div>
      <div class="drawer__body" id="dbody">${detailBody(v, d, tab)}</div>`;
    // seg indicator for tabs uses aria-current
    paint(dr);
    requestAnimationFrame(() => moveInd($(".drawer__tabs .seg", dr)));
  }
  function detailBody(v, d, tab) {
    if (v === "funds") return tab === "portfolio" ? fundPortfolio(d) : fundOverview(d);
    if (v === "founders") return founderOverview(d);
    const sc = d.score || {};
    const cs = sc.components || [];
    if (tab === "score") {
      const server = Array.isArray(d.what_would_move_it) ? d.what_would_move_it.map((x) => esc(noDash(typeof x === "string" ? x : x.text || ""))).filter(Boolean) : [];
      const moves = server.length || sc.mode !== "thesis" ? server : cs.filter((c) => c.weight > 0 && !c.present).map((c) => `<li>Data on <b>${esc(c.label.toLowerCase())}</b> could move it by up to ${(c.weight * 50).toFixed(1)} points either way${c.missing_reason ? ` (${esc(noDash(c.missing_reason))})` : ""}.</li>`);
      const low = server.length || sc.mode !== "thesis" ? [] : cs.filter((c) => c.weight > 0 && c.present && c.value < 0.5).map((c) => `<li>${esc(c.label)} is below the cohort middle (${fmt2(c.value)}). Reaching the top would add up to ${(c.weight * (1 - c.value) * 100).toFixed(1)} points.</li>`);
      const mv = moves.concat(low);
      return `<div class="cols2"><div class="panel"><div class="panel__head"><h3 class="panel__title">Full breakdown</h3><span class="panel__meta">every part and its records</span></div><div class="panel__body">${breakdown(sc, { full: true })}</div></div>
        <div class="stackp">${mv.length ? `<div class="panel"><div class="panel__head"><h3 class="panel__title">What would move it</h3></div><div class="panel__body"><ul class="facts">${mv.map((x) => `<li>${ic("arrowRight")}<span>${x}</span></li>`).join("")}</ul></div></div>` : ""}
        <div class="ribbon ribbon--sunken">${ic("info")}<span>Never read the score as a probability.</span></div></div></div>`;
    }
    if (tab === "rounds") {
      const rs = (d.rounds || []).slice().sort((a, b) => String(b.date).localeCompare(String(a.date)));
      if (!rs.length) return '<div class="state"><b>No rounds on file.</b></div>';
      return `<div class="tbl-wrap"><table class="tbl"><thead><tr><th>Date</th><th>Stage</th><th class="num">EUR m</th><th>Leads</th><th>Participants</th><th class="num">Sources</th><th>Flags</th><th>Record</th></tr></thead><tbody>${rs.map((r, i) => `<tr><td class="num">${esc(r.date || "")}${r.date_precision && r.date_precision !== "day" ? ` <span class="chip chip--hatch">${esc(r.date_precision)} only</span>` : ""}</td><td>${esc(stageLabel(r.stage) || "No stage")}</td><td class="num">${isNum(r.amount_eur_m) ? fmtM(r.amount_eur_m) : '<span class="faint">Undisclosed</span>'}</td><td>${(r.leads || []).length ? esc((r.leads || []).map((x) => x.name || x).join(", ")) : '<span class="faint">No lead named</span>'}</td><td>${esc((r.participants || []).map((x) => x.name || x).join(", "))}</td><td class="num">${isNum(r.sources) ? r.sources : ""}</td><td>${(r.flags || []).map((f) => `<span class="chip chip--teal">${esc(valueLabel("", f))}</span>`).join(" ")}</td><td>${recChip({ round_id: r.id, date: r.date }, i)}</td></tr>`).join("")}</tbody></table></div>`;
    }
    if (tab === "investors") {
      const iv = d.investors || [];
      if (!iv.length) return '<div class="state"><b>Cala names no investor for this company.</b></div>';
      return `<div class="tbl-wrap"><table class="tbl"><thead><tr><th>Investor</th><th>Role</th><th>Round list</th><th class="num">Graduation</th><th>Exit receipts</th></tr></thead><tbody>${iv.map((x) => `<tr><td><b>${esc(x.name)}</b></td><td>${esc(valueLabel("", x.role || ""))}</td><td>${x.queried ? '<span class="chip chip--teal">Full round list</span>' : '<span class="chip chip--hatch">Co-investor only</span>'}</td><td class="num">${x.graduation && isNum(x.graduation.n) ? `${x.graduation.k} of ${x.graduation.n}` : '<span class="faint">too few to judge</span>'}</td><td>${x.exit_receipts ? (x.exit_receipts.state === "not_checked" ? '<span class="chip chip--hatch">not checked</span>' : esc(String(x.exit_receipts.count))) : ""}</td></tr>`).join("")}</tbody></table></div><p class="frow__note">Graduation = share of this backer's early entries that raised again within 24 months, point in time. No exit found does not mean no exit.</p>`;
    }
    if (tab === "founders") {
      const fs = d.founders || [];
      if (!fs.length) return '<div class="state"><b>Cala names no founder for this company.</b><p>Founder data in Cala is thin: few companies have a founder edge at all.</p></div>';
      return `<ul class="facts">${fs.map((f) => `<li>${ic("user")}<span><a class="link" href="${entHref("founders", f.id)}">${esc(f.name)}</a>${f.title ? ` <span class="muted">${esc(f.title)}</span>` : ""}${(f.flags || []).map(flagChip).join("")}</span></li>`).join("")}</ul>`;
    }
    // overview
    const ev = d.evidence || {};
    const evParts = ev.parts || {};
    const size = cs.find((c) => c.key === "size_for_stage") || {};
    const whyFull = ((d.why || [])[0] || {}).text || sc.reason || d.score_reason || "";
    const evRows = [["Coverage", evParts.coverage], ["Independence", evParts.independence], ["Recency", evParts.recency], ["Date quality", evParts.date_quality]].map(([l, x]) => `<div class="mrow"><span>${l}</span><span class="mrow__bar${isNum(x) ? "" : " mrow__bar--missing"}">${isNum(x) ? `<i data-w="${x * 100}"></i>` : ""}</span><span class="num">${isNum(x) ? fmt2(x) : "n/a"}</span></div>`).join("");
    const others = cs.filter((c) => sc.mode === "thesis" || c.key !== "size_for_stage");
    const partRow = (c) => `<li class="part"><span class="part__label">${esc(c.label)}${sc.mode === "thesis" && c.weight > 0 ? ` <span class="faint num">${fmtPts(c.points)}</span>` : ""}</span><span class="part__val${c.present ? "" : " faint"}" title="${esc(noDash(c.present ? c.text || "" : c.missing_reason || "No data"))}">${esc(noDash(c.present ? c.short || c.text || fmt2(c.value) : "No data"))}</span>${labChip(c.lab_verdict)}</li>`;
    return `<div class="cols2">
      <div class="stackp"><div class="panel"><div class="panel__head"><h3 class="panel__title">Signal</h3><span class="panel__meta">${esc(sc.mode === "thesis" ? "Thesis mix" : "Size for stage")}</span></div><div class="panel__body">
        <div class="bd__big"><span class="bd__num">${isNum(sc.value) ? sc.value : "n/a"}</span><span class="bd__of">of 100${isNum(sc.rank) ? ` · global rank ${fmtInt(sc.rank)} of ${fmtInt(sc.of)}` : ""}</span></div>
        ${sizeLine(sc)}
        <p class="why-full">${esc(noDash(whyFull))}</p>
        ${(size.records || []).length && sc.mode !== "thesis" ? `<div class="chips">${size.records.slice(0, 4).map(recChip).join("")}</div>` : ""}
        <p><a class="link" href="${entHref("companies", d.id, "score")}">Full breakdown</a></p>
      </div></div>
      <div class="panel"><div class="panel__head"><h3 class="panel__title">Evidence</h3><span class="panel__meta">${esc(valueLabel("evidence_band", ev.band || "") || "n/a")} ${isNum(ev.value) ? fmt2(ev.value) : ""}</span></div><div class="panel__body">${evRows}</div></div>
      ${(d.chips || []).length ? `<div class="panel"><div class="panel__head"><h3 class="panel__title">Markers</h3></div><div class="panel__body"><div class="chat__chips">${d.chips.map((c) => { const [k, val] = String(c).split(":"); return `<span class="chip ${val === "true" ? "chip--teal" : val === "false" ? "chip--grey" : "chip--outline"}">${esc(valueLabel("", k))}${val ? ": " + esc(val === "true" ? "yes" : val === "false" ? "no" : valueLabel("", val)) : ""}</span>`; }).join("")}</div></div></div>` : ""}</div>
      <div class="panel"><div class="panel__head"><h3 class="panel__title">${sc.mode === "thesis" ? "All parts" : "Other parts"}</h3><span class="panel__meta">${sc.mode === "thesis" ? "points vs neutral" : "not in the score"}</span></div><div class="panel__body">
        <ul class="parts">${others.map(partRow).join("")}</ul>
      </div></div>
    </div>`;
  }
  function fundOverview(d) {
    const comp = d.components || {};
    const fc = (S.meta && S.meta.fund_components) || [];
    const cards = d.evidence_cards || [];
    return `<div class="cols2">
      <div class="panel"><div class="panel__head"><h3 class="panel__title">Activity score</h3><span class="panel__meta">${esc(d.score_label || "How actively this fund leads, not how well it picks.")}</span></div><div class="panel__body">
        ${isNum(d.score) ? `<div class="bd__big"><span class="bd__num">${d.score}</span><span class="bd__of">of 100</span></div>` : `<div class="state"><b>${esc(d.score_reason || "Not enough data: seen only as a co-investor")}</b></div>`}
        ${Object.keys(comp).map((k) => { const m = fc.find((x) => x.key === k) || {}; const val = comp[k]; return `<div class="mrow"><span>${esc(m.label || valueLabel("", k))} <span class="faint num">w ${fmtW(m.default_weight)}</span></span><span class="mrow__bar${isNum(val) ? "" : " mrow__bar--missing"}">${isNum(val) ? `<i data-w="${val * 100}"></i>` : ""}</span><span class="num">${isNum(val) ? fmt2(val) : "n/a"}</span></div>`; }).join("")}
      </div></div>
      <div class="panel"><div class="panel__head"><h3 class="panel__title">Evidence cards</h3><span class="panel__meta">no weight, read only</span></div><div class="panel__body">
        <ul class="facts">${cards.map((c) => `<li>${ic(c.state === "too_few" || c.state === "not_checked" ? "info" : "checkCircle")}<span><b>${esc(noDash(c.label || c.key || ""))}</b> <span class="muted">${esc(noDash(cardText(c)))}</span>${c.note ? `<br><span class="frow__note">${esc(noDash(c.note))}</span>` : ""}</span></li>`).join("") || '<li><span></span><span class="muted">No evidence cards for this investor.</span></li>'}</ul>
        <p class="frow__note">No exit found does not mean no exit. Lead accuracy in Cala: 74% exact, 89% right fund.</p>
      </div></div></div>`;
  }
  function cardText(c) {
    const v = c.value;
    if (v && typeof v === "object" && !Array.isArray(v)) {
      if ("led_24m" in v) return `${fmtInt(v.led_24m)} leads in the last 24 months, ${fmtInt(v.led_prior_24m)} in the 24 before${isNum(v.months_since_last_lead) ? `, last lead ${v.months_since_last_lead} months ago` : ""}`;
      if (v.downturn && v.boom) { const f = (x) => `${x.led} of ${x.of}`; return `led ${f(v.downturn)} rounds in 2022 to 2023, ${f(v.boom)} in 2019 to 2021`; }
    }
    if (c.text) return c.text;
    if (Array.isArray(v)) return v.slice(0, 6).map((x) => (x && typeof x === "object" ? x.name || x.key : x)).join(", ") || "none on file";
    if (v && typeof v === "object") return Object.entries(v).filter(([, x]) => x != null && typeof x !== "object").map(([k, x]) => `${k.replace(/_/g, " ")} ${x}`).join(", ");
    return v != null ? String(v) : "";
  }
  function fundPortfolio(d) {
    const p = d.portfolio || [];
    if (!p.length) return '<div class="state"><b>No portfolio companies on file.</b></div>';
    return `<div class="tbl-wrap"><table class="tbl"><thead><tr><th>Company</th><th>Role</th><th>Last stage</th><th class="num">Signal</th></tr></thead><tbody>${p.map((c) => `<tr><td>${cc(c.country)} <a class="link" href="${entHref("companies", c.id)}">${esc(c.name)}</a></td><td>${esc(valueLabel("", c.role || ""))}</td><td>${esc(stageLabel(c.last_stage || ""))}</td><td class="num">${isNum(c.score) ? c.score : '<span class="faint">Unranked</span>'}</td></tr>`).join("")}</tbody></table></div>`;
  }
  function founderOverview(d) {
    const e = d.founder_evidence || {};
    const facts = d.facts || e.facts || [], missing = d.missing || e.missing || [];
    return `<div class="cols2">
      <div class="panel"><div class="panel__head"><h3 class="panel__title">Founder evidence</h3><span class="panel__meta">${e.k || 0} of ${e.of || 4}</span></div><div class="panel__body">
        ${isNum(d.score) ? `<div class="bd__big"><span class="bd__num">${d.score}</span><span class="bd__of">of 100</span></div>` : `<div class="state"><b>${esc(d.score_reason || "Not enough data")}</b><p>A founder score needs at least 2 of 4 kinds of evidence.</p></div>`}
        <p class="overline">WHAT CALA HAS</p><ul class="facts">${facts.map((f) => `<li>${ic("checkCircle")}<span>${esc(noDash(typeof f === "string" ? f : f.text || JSON.stringify(f)))}</span></li>`).join("") || '<li><span></span><span class="muted">Nothing beyond the name.</span></li>'}</ul>
        <p class="overline">MISSING</p><div class="chat__chips">${missing.map((m) => `<span class="chip chip--hatch">${esc(m)}</span>`).join("")}</div>
      </div></div>
      <div class="stackp">
        ${d.company ? `<div class="panel"><div class="panel__head"><h3 class="panel__title">Company</h3><span class="panel__meta">company score, not a founder score</span></div><div class="panel__body"><a class="link" href="${entHref("companies", d.company.id)}">${esc(d.company.name)}</a>${isNum(d.company.score) ? ` <span class="score-badge score-badge--watch">${d.company.score}</span>` : ""}</div></div>` : ""}
        ${(d.roles || []).length ? `<div class="panel"><div class="panel__head"><h3 class="panel__title">Roles</h3></div><div class="panel__body"><ul class="facts">${d.roles.map((r) => `<li>${ic("building")}<span>${esc([r.role || r.title, r.org || r.company, (r.since || r.from) ? String(r.since || r.from).slice(0, 7) + " to " + (r.until || r.to ? String(r.until || r.to).slice(0, 7) : "now") : ""].filter(Boolean).join(" · "))}</span></li>`).join("")}</ul></div></div>` : ""}
        ${(d.cohort_tags || []).length ? `<div class="panel"><div class="panel__head"><h3 class="panel__title">Cohort tags</h3></div><div class="panel__body"><div class="chat__chips">${d.cohort_tags.map((t) => `<span class="chip ${t.verified ? "chip--teal" : "chip--grey"}">${esc(t.tag)}${t.verified ? "" : " (unverified)"}</span>`).join("")}</div></div></div>` : ""}
        ${(d.flags || []).includes("twin_link") ? '<div class="ribbon ribbon--red">' + ic("alert") + "<span>Possible wrong person: this founder is linked through a same-name entity in Cala.</span></div>" : ""}
      </div></div>`;
  }

  /* command palette */
  let palSeq = 0;
  function openPal() {
    S.layer = { kind: "pal", returnFocus: document.activeElement, items: [], sel: 0 };
    $("#layer").innerHTML = `<div class="scrim" data-act="close-layer"></div><div class="pal" role="dialog" aria-modal="true" aria-label="Search"><div class="pal__field">${ic("search")}<input id="pal-in" placeholder="Search companies, funds and founders" autocomplete="off" aria-controls="pal-list"><span class="kbd">esc</span></div><div class="pal__list" id="pal-list" role="listbox"><p class="frow__note pal__group">Type a name.</p></div><div class="pal__foot"><span><span class="kbd">↑</span><span class="kbd">↓</span> move</span><span><span class="kbd">↵</span> open</span></div></div>`;
    $("#pal-in").focus();
  }
  const palSearch = debounce(async (q) => {
    const seq = ++palSeq;
    const list = $("#pal-list"); if (!list) return;
    if (!q.trim()) { list.innerHTML = '<p class="frow__note pal__group">Type a name.</p>'; S.layer.items = []; return; }
    const f = JSON.stringify([{ key: "q", op: "contains", value: q.trim() }]);
    const res = await Promise.all(VIEWS.map((v) => api(`/api/signal/${v}?filters=${encodeURIComponent(f)}&limit=5&sort=score:desc`).then((d) => [v, d.rows || []]).catch(() => [v, []])));
    if (seq !== palSeq || !$("#pal-list")) return;
    const items = [];
    let html = "";
    res.forEach(([v, rows]) => {
      if (!rows.length) return;
      html += `<p class="overline pal__group">${v.toUpperCase()}</p>`;
      rows.forEach((r) => {
        const i = items.length;
        items.push(entHref(v, r.id));
        html += `<a class="pal__item" role="option" href="${entHref(v, r.id)}" data-pi="${i}" aria-selected="${i === 0}"><span class="pal__ic">${ic(v === "funds" ? "funds" : v === "founders" ? "user" : "building")}</span><span><span class="pal__t">${esc(r.name)}</span><span class="pal__s">${cc(r.country)}${esc(r.id)}</span></span>${isNum(r.score) ? `<span class="score-badge score-badge--${esc(r.band || "watch")}">${r.score}</span>` : ""}</a>`;
      });
    });
    S.layer.items = items; S.layer.sel = 0;
    $("#pal-list").innerHTML = html || '<p class="frow__note pal__group">No match in Cala data.</p>';
  }, 180);

  /* ---------------- backtest & method pages ---------------- */
  async function renderBacktest() {
    const main = $("#main");
    main.innerHTML = `<div class="page-header"><div><h1 class="page-header__title">Backtest</h1><div class="page-header__meta">Point in time, full-history companies, company-clustered intervals</div></div></div><div id="bt"><span class="skel"></span></div>`;
    if (!S.bt && !S.btErr) {
      try { S.bt = await api("/api/signal/backtest"); } catch (e) { S.btErr = e.message; }
    }
    drawBacktest();
  }
  function drawBacktest() {
    const host = $("#bt"); if (!host) return;
    if (S.btErr || !S.bt) { host.innerHTML = `<div class="state state--error"><b>The backtest could not load.</b><p>${esc(S.btErr || "")}</p></div>`; return; }
    const b = S.bt;
    const verdict = b.verdict || {};
    const res = (b.results || {})[S.btOutcome] || {};
    const split = res[S.btSplit] || {};
    const models = [["signal", "Thesis mix (composite)"], ["size_for_stage_baseline", "Size for stage (ranking)"], ["random_baseline", "Random"], ["n_rounds_baseline", "Most rounds on file"], ["recency_baseline", "Most recent round"]].filter(([k]) => split[k]);
    const best = Math.max(...models.map(([k]) => split[k].auc || 0));
    const nb = split.signal && split.signal.null_band90;
    const outcomes = [["next_round_24m", "Raises again within 24 months"], ["graduate_b_plus_36m", "Reaches Series B+ within 36 months"]];
    const splits = [["held_out", "Held out"], ["validation", "Validation"], ["held_out_all_companies_inflated_by_coverage", "All companies (inflated)"]].filter(([k]) => res[k]);
    const cutoffs = Array.from(new Set(models.flatMap(([k]) => Object.keys(split[k].per_cutoff || {})))).sort();
    const compRows = Object.entries(split.components || {});
    const card = ([k, l]) => {
      const m = split[k];
      const ci = m.cluster_ci90;
      return `<div class="mcard"><span class="mcard__label">${esc(l)}${k === "size_for_stage_baseline" ? '<span class="chip chip--accent">ranking</span>' : ""}</span>
        <span class="mcard__big${m.auc === best ? " win" : ""}">${isNum(m.auc) ? m.auc.toFixed(3) : "n/a"}</span>
        <span class="mcard__rows">AUC${ci ? ` · 90% CI ${ci[0]} to ${ci[1]}` : ""}<br>${isNum(m.top_decile_rate) ? `top tenth ${(m.top_decile_rate * 100).toFixed(0)}% vs base ${(m.base_rate * 100).toFixed(0)}% (lift ${m.lift})<br>` : ""}n ${fmtInt(m.n)} rows · ${fmtInt(m.companies)} companies${m.one_row_per_company ? `<br>one row per company: ${m.one_row_per_company.auc}` : ""}</span></div>`;
    };
    host.innerHTML = `
      <div class="bt-sentence"><span class="overline">IN ONE SENTENCE</span><p>${esc(noDash(verdict.line || ""))}</p>
        <p class="sub">Never read the score as a probability.</p>
        <div class="chat__chips"><span class="chip ${verdict.verdict === "pass" ? "chip--teal" : verdict.verdict === "fail" ? "chip--red" : "chip--amber"}">Verdict: ${esc(verdict.verdict || "n/a")}</span>${nb ? `<span class="chip chip--outline">Noise band ${nb[0]} to ${nb[1]}</span>` : ""}${verdict.gap_vs_size_alone ? `<span class="chip chip--grey">vs size alone: next round ${verdict.gap_vs_size_alone.next_round_24m}, Series B+ ${verdict.gap_vs_size_alone.graduate_b_plus_36m}</span>` : ""}</div></div>
      <div class="tbar bt-tabs"><div class="seg" role="group" aria-label="Outcome">${outcomes.map(([k, l]) => `<button class="seg__btn" type="button" data-bt-outcome="${k}" aria-pressed="${S.btOutcome === k}">${l}</button>`).join("")}</div>
        <div class="seg seg--sm" role="group" aria-label="Split">${splits.map(([k, l]) => `<button class="seg__btn" type="button" data-bt-split="${k}" aria-pressed="${S.btSplit === k}">${l}</button>`).join("")}</div></div>
      ${S.btSplit === "held_out_all_companies_inflated_by_coverage" ? `<div class="ribbon ribbon--amber">${ic("alert")}<span>All companies: inflated by coverage. Companies seen only through investors look like they never raise again. Read the full-history numbers instead.</span></div><div class="sp12"></div>` : ""}
      <div class="mcards">${models.slice(0, 4).map(card).join("")}</div>
      <div class="cols2">
        <div class="panel"><div class="panel__head"><h3 class="panel__title">AUC per cutoff year</h3><span class="panel__meta">0.50 = chance</span></div><div class="panel__body"><div class="tbl-wrap"><table class="tbl"><thead><tr><th>Model</th>${cutoffs.map((c) => `<th class="num">${c}</th>`).join("")}</tr></thead><tbody>${models.map(([k, l]) => `<tr><td>${esc(l)}</td>${cutoffs.map((c) => `<td class="num">${isNum((split[k].per_cutoff || {})[c]) ? split[k].per_cutoff[c].toFixed(3) : ""}</td>`).join("")}</tr>`).join("")}</tbody></table></div>
          ${split.signal && split.signal.precision_at_50 ? `<p class="overline">PRECISION AT 50</p><p class="frow__note num">${Object.entries(split.signal.precision_at_50).map(([y, p]) => `${y}: ${p.precision} vs base ${p.base} (n ${p.n})`).join(" · ")}</p>` : ""}</div></div>
        <div class="panel"><div class="panel__head"><h3 class="panel__title">Each part on its own</h3><span class="panel__meta">AUC as used, missing = neutral</span></div><div class="panel__body"><div class="tbl-wrap"><table class="tbl"><thead><tr><th>Part</th><th class="num">AUC</th><th class="num">Present only</th><th class="num">n</th></tr></thead><tbody>${compRows.map(([k, c]) => { const a = c.as_used_with_neutral || c; const p = c.present_only || {}; return `<tr><td>${esc(compLabel(k))}${(p.n || a.n) < 150 ? ' <span class="chip chip--amber">Small n</span>' : ""}</td><td class="num">${isNum(a.auc) ? a.auc.toFixed(3) : ""}</td><td class="num">${isNum(p.auc) ? p.auc.toFixed(3) : '<span class="faint">no data</span>'}</td><td class="num">${fmtInt(p.n || a.n)}</td></tr>`; }).join("")}</tbody></table></div></div></div>
      </div>
      <div class="sp12"></div>
      <div class="ribbon ribbon--sunken">${ic("info")}<span><b>In-sample.</b> ${b.selection ? `Weights: ${esc(b.selection.chosen || "")}, picked by ${esc(noDash(b.selection.criterion || ""))}. ` : ""}Held-out cutoffs were looked at during the design debate, so no clean holdout exists. Small n: treat every number here as a direction, not a measurement.</span></div>`;
  }
  /* ---------------- lab: every signal tested on held-out years ---------------- */
  const LAB_OUT = [["next_round_24m", "Next round 24m"], ["graduate_b_plus_36m", "Series B+ 36m"]];
  const LAB_CHIP = { "Kept": "chip--teal", "Noise": "chip--grey", "Not testable": "chip--hatch" };
  async function renderLab() {
    const main = $("#main");
    main.innerHTML = `<div class="page-header"><div><h1 class="page-header__title">Lab</h1><div class="page-header__meta">Every signal we tried, scored once on held-out years, full-history companies</div></div></div><div id="lab"><span class="skel"></span></div>`;
    if (!S.lab && !S.labErr) {
      try { S.lab = await api("/api/signal/lab"); } catch (e) { S.labErr = e.message; }
    }
    drawLab();
  }
  const f3 = (x) => (isNum(x) ? x.toFixed(3) : "");
  const sgn = (x) => (isNum(x) ? (x > 0 ? "+" : "") + x.toFixed(3) : "");
  // CI whisker against chance (0.5) and the noise band, on a fixed 0.30 to 0.80 axis so rows compare at a glance
  function ciBar(c) {
    if (!c || !isNum(c.auc) || !c.ci90) return "";
    const W = 120, lo = 0.3, hi = 0.8, x = (v) => Math.max(0, Math.min(W, ((v - lo) / (hi - lo)) * W));
    const nb = c.null_band90;
    return `<svg class="cibar" viewBox="0 0 ${W} 14" width="${W}" height="14" aria-hidden="true">
      ${nb ? `<rect class="cibar__band" x="${x(nb[0])}" y="2" width="${Math.max(1, x(nb[1]) - x(nb[0]))}" height="10" rx="2"/>` : ""}
      <line class="cibar__half" x1="${x(0.5)}" x2="${x(0.5)}" y1="0" y2="14"/>
      <line class="cibar__ci${c.passes_bar ? " is-pass" : ""}" x1="${x(c.ci90[0])}" x2="${x(c.ci90[1])}" y1="7" y2="7"/>
      <circle class="cibar__dot${c.passes_bar ? " is-pass" : ""}" cx="${x(c.auc)}" cy="7" r="3"/></svg>`;
  }
  function labCell(c) {
    if (!c || !c.n) return '<span class="faint">no data</span>';
    if (!isNum(c.auc)) return `<span class="faint">n ${fmtInt(c.n)}, no score</span>`;
    const small = c.n < 100;
    return `<div class="labc"><span class="labc__auc num${c.passes_bar ? " pos" : ""}">${f3(c.auc)}</span>${ciBar(c)}
      <span class="labc__sub num">${c.ci90 ? `CI ${f3(c.ci90[0])} to ${f3(c.ci90[1])}` : ""}${c.null_band90 ? `<br>noise ${f3(c.null_band90[0])} to ${f3(c.null_band90[1])}` : ""}<br>n ${fmtInt(c.n)}${small ? ' <span class="chip chip--amber">n&lt;100</span>' : ""}</span></div>`;
  }
  function labAdds(r) {
    const parts = LAB_OUT.map(([k]) => { const c = r.outcomes[k] || {}; return c.delta_ci90 ? `<span class="${c.adds_over_size ? "pos" : ""}">${k === "next_round_24m" ? "Next" : "B+"} ${sgn(c.delta_vs_size)}<br><span class="faint">${f3(c.delta_ci90[0])} to ${f3(c.delta_ci90[1])}</span></span>` : ""; }).filter(Boolean);
    const any = LAB_OUT.some(([k]) => (r.outcomes[k] || {}).adds_over_size);
    if (r.key === "size_for_stage") return '<span class="faint">is the baseline</span>';
    if (!parts.length) return '<span class="faint">not fitted</span>';
    return `<div class="labadd num"><span class="chip ${any ? "chip--teal" : "chip--outline"}">${any ? "Yes" : "No"}</span>${parts.join("")}</div>`;
  }
  function drawLab() {
    const host = $("#lab"); if (!host) return;
    if (S.labErr || !S.lab) { host.innerHTML = `<div class="state state--error"><b>The lab could not load.</b><p>${esc(S.labErr || "")}</p></div>`; return; }
    const d = S.lab, c = d.counts || {}, ref = d.reference || {};
    const fl = [["all", "All", c.tested], ["Kept", "Kept", c.kept], ["Noise", "Noise", c.noise], ["Not testable", "Not testable", c.not_testable]];
    const rows = (d.rows || []).filter((r) => S.labFilter === "all" || r.verdict === S.labFilter);
    const refChip = (k, l) => ref[k] ? `<span class="chip chip--outline num">${l}: size alone ${f3(ref[k].size_alone)}, thesis mix ${f3(ref[k].composite)}</span>` : "";
    const verdict = (r) => `<span class="chip ${LAB_CHIP[r.verdict] || "chip--grey"}">${r.verdict === "Kept" ? ic("check") : ""}${esc(r.verdict)}</span>`;
    const name = (r) => `<div class="labn"><b>${esc(noDash(r.name))}</b><span class="labn__fam">${esc(r.family)}</span></div><p class="labn__def">${esc(noDash(r.definition))}</p>`;
    host.innerHTML = `
      <div class="bt-sentence lab-head"><span class="overline">HELD-OUT RESULT</span><p class="lab-head__big">${esc(noDash(d.headline || ""))}</p>
        <p class="sub">${esc(noDash(d.subline || ""))}</p>
        <div class="chat__chips"><span class="chip chip--teal">${fmtInt(c.kept)} kept</span><span class="chip chip--grey">${fmtInt(c.noise)} noise</span><span class="chip chip--hatch">${fmtInt(c.not_testable)} not testable</span>
          <span class="chip chip--grey">${fmtInt(c.existing)} thesis parts, ${fmtInt(c.hunt)} new, ${fmtInt(c.models)} learned model</span>
          ${refChip("next_round_24m", "Next round")}${refChip("graduate_b_plus_36m", "Series B+")}</div></div>
      <div class="tbar bt-tabs"><div class="seg" role="group" aria-label="Verdict">${fl.map(([k, l, n]) => `<button class="seg__btn" type="button" data-lab-f="${esc(k)}" aria-pressed="${S.labFilter === k}">${l} <span class="seg__count">${fmtInt(n || 0)}</span></button>`).join("")}</div></div>
      <div class="tbl-wrap lab-tbl"><table class="tbl"><thead><tr><th>Signal</th>${LAB_OUT.map(([, l]) => `<th>${l}<br><span class="faint">AUC, 90% CI, noise band</span></th>`).join("")}<th>Adds over size<br><span class="faint">change in AUC, 90% CI</span></th><th>Verdict</th></tr></thead>
        <tbody>${rows.map((r) => `<tr class="lab-row lab-row--${r.verdict === "Kept" ? "kept" : "x"}"><td class="lab-sig">${name(r)}<p class="labn__why">${esc(noDash(r.reason))}</p></td>${LAB_OUT.map(([k]) => `<td>${labCell(r.outcomes[k])}</td>`).join("")}<td>${labAdds(r)}</td><td>${verdict(r)}</td></tr>`).join("") || `<tr><td colspan="5" class="faint">Nothing here.</td></tr>`}</tbody></table></div>
      <div class="lab-cards">${rows.map((r) => `<article class="lab-card${r.verdict === "Kept" ? " is-kept" : ""}"><div class="lab-card__top">${name(r)}${verdict(r)}</div>
        <div class="lab-card__grid">${LAB_OUT.map(([k, l]) => `<div><span class="overline">${l.toUpperCase()}</span>${labCell(r.outcomes[k])}</div>`).join("")}</div>
        <div class="lab-card__adds"><span class="overline">ADDS OVER SIZE</span>${labAdds(r)}</div><p class="labn__why">${esc(noDash(r.reason))}</p></article>`).join("")}</div>
      <div class="sp12"></div>
      <div class="ribbon ribbon--sunken">${ic("info")}<span><b>The bar.</b> ${esc(noDash(d.rule || ""))} Directions and weights were chosen on 2018 to 2020 only. ${d.meta && d.meta.multiple_comparisons ? `Corrected for ${fmtInt(d.meta.multiple_comparisons.hunt_tests + d.meta.multiple_comparisons.existing_tests)} tests (Holm). ` : ""}Every number comes from Cala's record only; the snapshot only holds companies Cala returns today.</span></div>`;
  }

  function renderMethod() {
    const m = S.meta || {};
    const c = m.counts || {};
    $("#main").innerHTML = `<div class="page-header"><div><h1 class="page-header__title">Method and limits</h1><div class="page-header__meta">${headerMeta()}</div></div></div>
      <div class="cols2 method">
        <div class="panel"><div class="panel__head"><h3 class="panel__title">What the data holds</h3><span class="panel__meta">Cala snapshot</span></div><div class="panel__body"><dl>${Object.entries(c).map(([k, v]) => `<dt>${esc(valueLabel("", k))}</dt><dd>${fmtInt(v)}</dd>`).join("")}</dl>
          <p class="overline">NOT IN CALA DATA HERE</p><ul><li>Revenue, ARR, growth rates</li><li>Headcount and hiring</li><li>Valuations</li><li>Most founder careers (few founders have a dated role)</li></ul></div></div>
        <div class="panel"><div class="panel__head"><h3 class="panel__title">Honesty lines</h3><span class="panel__meta">shown wherever they apply</span></div><div class="panel__body"><ul>${(m.honesty || ["Lead accuracy: 74% exact, 89% right fund.", "Cala names no lead in about a third of seed rounds.", "No exit found does not mean no exit."]).map((h) => `<li>${esc(noDash(h))}</li>`).join("")}</ul></div></div>
        <div class="panel"><div class="panel__head"><h3 class="panel__title">The ${comps().length} parts</h3><span class="panel__meta">ranking uses size for stage only</span></div><div class="panel__body">${comps().map((x) => `<div class="wrow"><span class="wrow__label">${esc(x.label)} ${labChip(x.lab_verdict)}</span><span class="wrow__val">${x.key === "size_for_stage" ? "ranks" : "filter"}</span><span class="wrow__bt">${esc(noDash(x.how || ""))}</span></div>`).join("") || '<p class="muted">Not loaded.</p>'}</div></div>
        <div class="panel"><div class="panel__head"><h3 class="panel__title">How the chat works</h3></div><div class="panel__body"><ul><li>Gemini reads your words and returns filters in a fixed format. Weight changes apply only with the thesis mix on.</li><li>It never sees company rows and never writes a name, number or score.</li><li>The server checks every filter and weight, clamps thesis weights, and computes the ranking itself.</li><li>Anything Cala can't express (revenue, headcount, valuation) is listed as “Not used”.</li><li>Your own key, if you paste one, is used for that call only and lives in this tab's memory.</li></ul></div></div>
      </div>`;
  }

  /* ---------------- events ---------------- */
  function onClick(e) {
    const t = e.target;
    const themeBtn = t.closest("[data-theme-set]");
    if (themeBtn) { const k = themeBtn.dataset.themeSet; store.set(THEME_KEY, k === "system" ? null : k); applyTheme(k === "system" ? null : k); renderTheme(); return; }
    const pre = t.closest("[data-preset]");
    if (pre) {
      const p = ((S.meta && S.meta.intent_presets) || []).find((x) => x.id === pre.dataset.preset);
      S.weights = {}; S.weightBy = {};
      if (p) { S.thesis = true; Object.entries(p.weights || {}).forEach(([k, w]) => { S.weights[k] = w; S.weightBy[k] = "preset"; }); (p.filters || []).forEach((f) => setF("companies", f.key, f.op, f.value, "preset")); }
      loadList("companies"); return;
    }
    const bo = t.closest("[data-bt-outcome]"); if (bo) { S.btOutcome = bo.dataset.btOutcome; drawBacktest(); return; }
    const bs = t.closest("[data-bt-split]"); if (bs) { S.btSplit = bs.dataset.btSplit; drawBacktest(); return; }
    const lf = t.closest("[data-lab-f]"); if (lf) { S.labFilter = lf.dataset.labF; drawLab(); return; }
    const fseg = t.closest('[data-f="seg"]'); if (fseg) { onFilterInput(fseg, true); return; }
    const pi = t.closest("[data-pi]"); if (pi) { closeLayer(); return; }
    const a = t.closest("[data-act]");
    const row = t.closest(".sheet__row--body");
    if (!a && row && !t.closest("a")) { location.hash = entHref(S.route.view, row.dataset.id); return; }
    if (!a) return;
    const act = a.dataset.act;
    if (["fair", "thesis"].includes(act)) return; // handled on change
    switch (act) {
      case "ask": S.chatMsg = a.dataset.q; ask(a.dataset.q); break;
      case "rmf": setF(S.route.view, a.dataset.key, null); loadList(S.route.view); break;
      case "rmw": delete S.weights[a.dataset.key]; delete S.weightBy[a.dataset.key]; loadList("companies"); break;
      case "rmval": { const v = S.route.view; const cur = getF(v, a.dataset.key); const vals = (cur.value || []).filter((x) => x !== a.dataset.val); setF(v, a.dataset.key, vals.length ? "in" : null, vals); loadList(v); break; }
      case "reset": { const v = S.route.view; S.fv[v] = []; if (v === "companies") { S.weights = {}; S.weightBy = {}; } S.chat[v] = null; S.chatMsg = ""; S.chatErr = null; S.sort[v] = "score:desc"; loadList(v); break; }
      case "clear": S.fv[S.route.view] = []; loadList(S.route.view); break;
      case "sort": { const v = S.route.view; const [k, d] = S.sort[v].split(":"); const nk = a.dataset.sort; S.sort[v] = `${nk}:${k === nk ? (d === "desc" ? "asc" : "desc") : nk === "name" ? "asc" : "desc"}`; loadList(v); break; }
      case "score": e.preventDefault(); e.stopPropagation(); showScorePop(a); break;
      case "rec": e.preventDefault(); showRecord(a); break;
      case "why": showWhy(a); break;
      case "weights": openWeights(a); break;
      case "key": showKey(a); break;
      case "key-clear": setKey(""); closePop(); break;
      case "more": loadList(S.route.view, true); break;
      case "retry": loadList(S.route.view); break;
      case "fgroup": { const g = a.dataset.g; if (S.openGroups.has(g)) S.openGroups.delete(g); else S.openGroups.add(g); renderRail(); break; }
      case "fmore": S.openGroups.add("all:" + S.route.view + a.dataset.key); renderRail(); break;
      case "rail-open": S.railSheet = true; renderRail(); $("#layer").innerHTML = '<div class="scrim" data-act="rail-close"></div>'; break;
      case "rail-close": S.railSheet = false; $("#layer").innerHTML = ""; renderRail(); break;
      case "pop-close": closePop(); break;
      case "close-layer": closeLayer(); break;
      case "wreset": S.weights = {}; S.weightBy = {}; S.thesis = false; renderWeights(); loadList("companies"); break;
      case "expand": S.layer.full = !S.layer.full; { const dr = $("#drawer"); dr.className = "drawer " + (S.layer.full ? "drawer--full" : "drawer--card"); } break;
      case "copy": try { navigator.clipboard.writeText(a.dataset.copy); toast("Copied"); } catch (err) { /* clipboard blocked */ } break;
      default: break;
    }
  }
  function onChange(e) {
    const t = e.target;
    if (t.dataset.act === "fair") { S.fairRank = t.checked; loadList("companies"); return; }
    if (t.dataset.act === "thesis") {
      S.thesis = t.checked;
      if (!S.thesis) { S.weights = {}; S.weightBy = {}; }
      renderWeights(); loadList("companies"); return;
    }
    if (t.dataset.wKey) { S.weights[t.dataset.wKey] = +t.value; S.weightBy[t.dataset.wKey] = "you"; reloadCompaniesSoon(); return; }
    if (t.dataset.f && ["toggle", "multi", "select", "cmp", "stagecount", "range", "slider", "cmpmin"].includes(t.dataset.f)) onFilterInput(t, true);
  }
  function onInput(e) {
    const t = e.target;
    if (t.id === "rail-q") { S.railQ = t.value; const pos = t.selectionStart; renderRail(); const n = $("#rail-q"); n.focus(); n.setSelectionRange(pos, pos); return; }
    if (t.id === "chat-in") { S.chatMsg = t.value; return; }
    if (t.id === "pal-in") { palSearch(t.value); return; }
    if (t.dataset.wKey) { setRangeFill(t); S.weights[t.dataset.wKey] = +t.value; S.weightBy[t.dataset.wKey] = "you"; const val = t.closest(".wrow").querySelector(".wrow__val"); if (val) { val.textContent = (+t.value).toFixed(2); val.classList.add("changed"); } reloadCompaniesSoon(); return; }
    if (t.dataset.f === "slider" || t.dataset.f === "cmpmin") { onFilterInput(t, false); return; }
    if (t.dataset.f === "text") { textFilterSoon(t.dataset.key, t.value); }
  }
  const textFilterSoon = debounce((key, val) => { const v = S.route.view; val = val.trim(); setF(v, key, val ? "contains" : null, val); loadList(v); }, 300);
  function onSubmit(e) {
    if (e.target.id === "chat-form") { e.preventDefault(); ask($("#chat-in").value); return; }
    if (e.target.id === "key-form") { e.preventDefault(); const k = $("#key-in").value.trim(); if (k) { setKey(k); closePop(); toast("Your key will be used for your requests in this tab."); } }
  }
  function onKey(e) {
    const t = e.target;
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName);
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); openPal(); return; }
    if (e.key === "Escape") {
      if (closePop()) return;
      if (S.railSheet) { S.railSheet = false; $("#layer").innerHTML = ""; renderRail(); return; }
      if (S.layer) { closeLayer(); return; }
    }
    if (t.dataset && t.dataset.f === "addval" && e.key === "Enter") {
      e.preventDefault(); const v = S.route.view; const val = t.value.trim(); if (!val) return;
      const cur = getF(v, t.dataset.key); const vals = (cur && cur.value) || []; if (!vals.includes(val)) vals.push(val);
      setF(v, t.dataset.key, "in", vals); loadList(v); return;
    }
    if (t.dataset && t.dataset.f === "range" && e.key === "Enter") { onFilterInput(t, true); return; }
    if (S.layer && S.layer.kind === "pal") {
      const items = $$(".pal__item");
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault(); if (!items.length) return;
        S.layer.sel = (S.layer.sel + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
        items.forEach((x, i) => x.setAttribute("aria-selected", String(i === S.layer.sel))); items[S.layer.sel].scrollIntoView({ block: "nearest" });
      } else if (e.key === "Enter" && items.length) { e.preventDefault(); const href = S.layer.items[S.layer.sel]; closeLayer(); location.hash = href; }
      return;
    }
    if (typing || S.layer || S.route.page) return;
    const rows = S.rows[S.route.view] || [];
    if (e.key === "j" || e.key === "k") {
      if (!rows.length) return;
      S.sel = clamp(S.sel + (e.key === "j" ? 1 : -1), 0, rows.length - 1);
      $$(".sheet__row--body").forEach((r) => r.classList.toggle("is-selected", +r.dataset.row === S.sel));
      const el = $(`.sheet__row--body[data-row="${S.sel}"]`); if (el) { el.focus({ preventScroll: true }); el.scrollIntoView({ block: "nearest" }); }
    } else if (e.key === "Enter" && t.classList && t.classList.contains("sheet__row--body")) {
      location.hash = entHref(S.route.view, t.dataset.id);
    } else if (e.key === "Enter" && S.sel >= 0 && rows[S.sel]) {
      location.hash = entHref(S.route.view, rows[S.sel].id);
    } else if (e.key === "w" && S.route.view === "companies") { openWeights(document.activeElement); }
    else if (e.key === "/") { e.preventDefault(); const c = $("#chat-in"); if (c) c.focus(); }
  }
  function toast(msg) {
    const el = document.createElement("div"); el.className = "toast"; el.setAttribute("role", "status"); el.textContent = msg;
    document.body.appendChild(el); setTimeout(() => el.remove(), 2600);
  }

  /* ---------------- init ---------------- */
  async function init() {
    renderTheme();
    document.addEventListener("click", onClick);
    document.addEventListener("change", onChange);
    document.addEventListener("input", onInput);
    document.addEventListener("submit", onSubmit);
    document.addEventListener("keydown", onKey);
    $("#open-pal").addEventListener("click", openPal);
    $("#open-key").addEventListener("click", (e) => showKey(e.currentTarget));
    window.addEventListener("hashchange", onRoute);
    window.addEventListener("resize", debounce(() => { moveInd($("#nav")); }, 100));
    window.addEventListener("scroll", () => { $("#topbar").dataset.scrolled = String(window.scrollY > 4); }, { passive: true });
    if (!location.hash) history.replaceState(null, "", "#/companies");
    S.route = parseHash();
    renderNav();
    if (!S.route.page) renderView();
    api("/api/signal/meta").then((m) => { S.meta = m; renderNav(); refreshAll(); if (S.route.page === "method") renderMethod(); })
      .catch((e) => { if (e.message !== "auth") { S.metaErr = e.message; refreshAll(); } });
    if (S.route.page) { onRouteFirst(); return; }
    loadList(S.route.view);
    if (S.route.id) openDetail(S.route.view, S.route.id, S.route.tab);
  }
  function onRouteFirst() { if (S.route.page === "backtest") renderBacktest(); else if (S.route.page === "lab") renderLab(); else renderMethod(); }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
