"use strict";
/* Recount Explore: role picker, AI-described filters, Dealroom-style filter rail + sortable tables, detail pages
   with hand-built SVG charts. No inline styles or scripts (CSP). All text from data goes in via textContent.

   Data: /api/explore/ui/* (app/explore_views.py; contract in docs/explore-api.md). Lists come whole and are
   filtered and sorted here. Founder careers come from people.json (Cala entity graph) and are facts, never scores. */

(() => {
  const API = "/api/explore/ui/";
  const PAGE = 50;
  const SVGNS = "http://www.w3.org/2000/svg";
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const STAGE_LABEL = { "pre-seed": "Pre-seed", seed: "Seed", growth: "Growth" };

  /* ---------- tiny DOM helpers ---------- */
  function h(tag, attrs, ...kids) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k === "class") el.className = v;
      else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? "" : v);
    }
    append(el, kids);
    return el;
  }
  function append(el, kids) {
    for (const k of kids.flat(Infinity)) {
      if (k === null || k === undefined || k === false) continue;
      el.append(k instanceof Node ? k : document.createTextNode(String(k)));
    }
    return el;
  }
  function s(tag, attrs, ...kids) {
    const el = document.createElementNS(SVGNS, tag);
    for (const [k, v] of Object.entries(attrs || {})) if (v !== null && v !== undefined) el.setAttribute(k, v);
    for (const k of kids.flat()) if (k !== null && k !== undefined) el.append(k instanceof Node ? k : document.createTextNode(String(k)));
    return el;
  }
  const svgTitle = (t) => s("title", {}, t);

  /* ---------- formatting ---------- */
  const fmtYm = (ym) => {
    if (!ym) return "None";
    const [y, m] = ym.split("-");
    return `${MONTHS[(+m || 1) - 1]} ${y}`;
  };
  const fmtStage = (st) => (st ? STAGE_LABEL[st] || st.replace(/^series /, "Series ").replace(/ ([a-f])$/, (x) => x.toUpperCase()) : "Unknown");
  const fmtEur = (m) => (m === null || m === undefined ? "n/a" : m >= 1000 ? `€${(m / 1000).toFixed(1)}B` : `€${m >= 10 ? Math.round(m) : m.toFixed(1)}M`);
  const fmtPct = (x) => (x === null || x === undefined ? "n/a" : `${Math.round(x * 100)}%`);
  const fmtMonths = (m) => {
    if (m === null || m === undefined) return "n/a";
    if (m < 24) return `${Math.round(m)} mo`;
    const y = Math.floor(m / 12), r = Math.round(m % 12);
    return r ? `${y} y ${r} mo` : `${y} y`;
  };
  const fmtYears = (y, n) => (y === null || y === undefined ? "n/a" : `${y} y${n ? ` (n=${n})` : ""}`);
  const ymToNum = (ym) => { const [y, m] = ym.split("-"); return +y + ((+m || 1) - 1) / 12; };
  const plural = (n, one, many) => `${n.toLocaleString("en")} ${n === 1 ? one : many || one + "s"}`;

  /* ---------- data layer ---------- */
  const cache = new Map();
  async function getJson(url, opts) {
    const key = opts ? null : url;
    if (key && cache.has(key)) return cache.get(key);
    const p = fetch(url, opts).then(async (r) => {
      if (!r.ok) throw new Error(`${url} answered ${r.status}`);
      return r.json();
    });
    if (key) { cache.set(key, p); p.catch(() => cache.delete(key)); }
    return p;
  }
  const api = {
    meta: () => getJson(API + "meta"),
    list: (view) => getJson(API + view),
    detail: (kind, key) => getJson(`${API}${kind}/${encodeURIComponent(key)}`),
    aiFilters: (body) => getJson(API + "ai-filters", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    }),
  };

  /* ---------- filter definitions ---------- */
  const has = (v) => v !== undefined && v !== null && v !== "" && !(Array.isArray(v) && !v.length) &&
    !(typeof v === "object" && !Array.isArray(v) && v.min == null && v.max == null);
  const inRange = (x, r) => x !== null && x !== undefined && (r.min == null || x >= r.min) && (r.max == null || x <= r.max);
  const anyName = (list, q) => (list || []).some((i) => i.name.toLowerCase().includes(q.toLowerCase()));

  const FILTERS = {
    funds: [
      { key: "q", label: "Fund name", type: "text", ph: "Search funds", test: (f, v) => f.name.toLowerCase().includes(v.toLowerCase()) },
      { key: "country", label: "Has rounds in", type: "multi", opts: "countries", test: (f, v) => v.some((c) => (f.countries || {})[c] > 0) },
      { key: "stage", label: "Led at stage", type: "multi", opts: "stages", fmt: fmtStage, test: (f, v) => v.some((st) => (f.stages_led || {})[st] > 0) },
      { key: "lead_share", label: "Lead share, % of lead-known rounds", type: "range", unit: "%", step: 5,
        test: (f, v) => inRange(f.lead_share === null ? null : f.lead_share * 100, v) },
      { key: "lead_known", label: "Lead-known rounds, at least", type: "number", hint: "Small counts swing a lot. 10 or more is steadier.",
        test: (f, v) => f.lead_known >= v },
      { key: "round", label: "Median led round, €M", type: "range", step: 1, test: (f, v) => inRange(f.median_led_round_eur_m, v) },
      { key: "last_lead", label: "Last lead within", type: "select", options: [[6, "6 months"], [12, "12 months"], [18, "18 months"], [24, "24 months"], [36, "36 months"]],
        test: (f, v) => f.months_since_last_lead !== null && f.months_since_last_lead <= +v },
      { key: "downturn", label: "Led a round in 2022 to 2023", type: "check", text: "Yes, at least one", test: (f) => f.downturn_led > 0 },
      { key: "exits", label: "Exit receipts", type: "check", text: "Has at least one acquisition receipt", test: (f) => f.exit_receipts > 0 },
      { key: "co_investor", label: "Co-invested with", type: "multi", opts: "fundNames", free: true, ph: "Type a fund",
        test: (f, v) => v.every((q) => anyName(f.co_investors, q)) },
    ],
    companies: [
      { key: "q", label: "Company name", type: "text", ph: "Search companies", test: (c, v) => c.name.toLowerCase().includes(v.toLowerCase()) },
      { key: "stage", label: "Last stage", type: "multi", opts: "stages", fmt: fmtStage, test: (c, v) => v.includes(c.last_stage) },
      { key: "country", label: "Country", type: "multi", opts: "countries", test: (c, v) => v.includes(c.country) },
      { key: "last_round_after", label: "Last round on or after", type: "month", test: (c, v) => c.last_round >= v },
      { key: "months_since", label: "Months since last round", type: "range", step: 1, test: (c, v) => inRange(c.months_since_last_round, v) },
      { key: "investor", label: "Investors include", type: "multi", opts: "investors", free: true, ph: "Type an investor",
        test: (c, v) => v.every((q) => anyName(c.investors, q)) },
      { key: "lead", label: "Led a round", type: "multi", opts: "investors", free: true, ph: "Type a fund",
        hint: "A fund named as lead in any of its rounds.", test: (c, v) => v.every((q) => anyName(c.leads, q)) },
      { key: "rounds", label: "Rounds on record, at least", type: "number", test: (c, v) => c.rounds >= v },
      { key: "last_amount", label: "Last round size, €M", type: "range", step: 1, test: (c, v) => inRange(c.last_amount_eur_m, v) },
      { key: "raised", label: "Known raised in total, €M", type: "range", step: 1, test: (c, v) => inRange(c.total_known_eur_m, v) },
      { key: "founder_tags", label: "Founder background", type: "multi", opts: "founder_tags",
        hint: "Only companies whose founders have Cala career records.", test: (c, v) => v.every((t) => c.founder_tags.includes(t)) },
      { key: "repeat", label: "Repeat founder", type: "check", text: "A founder founded a company before", test: (c) => c.repeat_founder },
    ],
    founders: [
      { key: "q", label: "Name or company", type: "text", ph: "Search people", test: (p, v) => `${p.name} ${p.company}`.toLowerCase().includes(v.toLowerCase()) },
      { key: "tags", label: "Background", type: "multi", opts: "founder_tags", hint: "Employer types outside their own company, from hand lists.",
        test: (p, v) => v.every((t) => p.tags.includes(t)) },
      { key: "country", label: "Country", type: "multi", opts: "countries", test: (p, v) => v.includes(p.country) },
      { key: "stage", label: "Company stage", type: "multi", opts: "stages", fmt: fmtStage, test: (p, v) => v.includes(p.company_stage) },
      { key: "career", label: "Career record", type: "check", text: "Has a role outside their own company", test: (p) => p.metrics.roles_outside_company > 0 },
      { key: "dated", label: "Roles with dates, at least", type: "number", test: (p, v) => p.metrics.roles_dated >= v },
      { key: "tenure", label: "Average years per dated role", type: "range", step: 0.5, hint: "Only roles with both a start and an end date count.",
        test: (p, v) => inRange(p.metrics.avg_tenure_years, v) },
      { key: "ups", label: "Title level-ups per year", type: "range", step: 0.1, hint: "Steps up in title level, divided by the years between the first and last dated role.",
        test: (p, v) => inRange(p.metrics.level_ups_per_year, v) },
      { key: "repeat", label: "Repeat founder", type: "check", text: "Founded a company before this one", test: (p) => p.metrics.repeat_founder },
      { key: "prior_exit", label: "Prior exit", type: "check", text: "An earlier company was acquired", test: (p) => p.metrics.prior_exit },
    ],
  };
  const defOf = (view, key) => FILTERS[view].find((d) => d.key === key);

  /* ---------- columns ---------- */
  const shareBar = (x) => {
    const w = 48, v = x === null ? 0 : Math.max(0, Math.min(1, x));
    return s("svg", { width: w, height: 6, viewBox: `0 0 ${w} 6`, "aria-hidden": "true" },
      s("rect", { class: "c-track", width: w, height: 6, rx: 3 }),
      s("rect", { class: "c-led", width: Math.max(v ? 2 : 0, w * v), height: 6, rx: 3 }));
  };
  const COLUMNS = {
    funds: [
      { key: "name", label: "Fund", cls: "name", get: (f) => f.name.toLowerCase(), cell: (f) => h("a", { href: `#/fund/${encodeURIComponent(f.key)}` }, f.name) },
      { key: "lead_share", label: "Lead share", r: true, get: (f) => f.lead_share ?? -1,
        cell: (f) => h("span", { class: "share", title: `${f.led} led of ${f.lead_known} lead-known rounds` }, `${fmtPct(f.lead_share)} of ${f.lead_known}`, shareBar(f.lead_share)) },
      { key: "led", label: "Led", r: true, get: (f) => f.led, cell: (f) => f.led },
      { key: "lead_unknown", label: "Lead unknown", r: true, get: (f) => f.lead_unknown, cell: (f) => f.lead_unknown },
      { key: "round", label: "Median led round", r: true, get: (f) => f.median_led_round_eur_m ?? -1, cell: (f) => fmtEur(f.median_led_round_eur_m) },
      { key: "last_lead", label: "Last lead", r: true, get: (f) => f.last_lead || "", cell: (f) => fmtYm(f.last_lead) },
      { key: "downturn", label: "Led 2022 to 2023", r: true, get: (f) => f.downturn_led, cell: (f) => `${f.downturn_led} of ${f.downturn_lead_known}` },
      { key: "exits", label: "Exit receipts", r: true, get: (f) => f.exit_receipts, cell: (f) => f.exit_receipts || "None found" },
      { key: "co", label: "Top co-investors", cls: "small", get: (f) => (f.co_investors[0] || {}).name || "", cell: (f) => f.co_investors.slice(0, 3).map((c) => c.name).join(", ") },
    ],
    companies: [
      { key: "name", label: "Company", cls: "name", get: (c) => c.name.toLowerCase(), cell: (c) => h("a", { href: `#/company/${encodeURIComponent(c.key)}` }, c.name) },
      { key: "country", label: "Country", get: (c) => c.country || "", cell: (c) => c.country || "Unknown" },
      { key: "stage", label: "Last stage", get: (c) => c.last_stage || "", cell: (c) => fmtStage(c.last_stage) },
      { key: "last_round", label: "Last round", r: true, get: (c) => c.last_round, cell: (c) => fmtYm(c.last_round) },
      { key: "months_since", label: "Months since", r: true, get: (c) => c.months_since_last_round, cell: (c) => c.months_since_last_round },
      { key: "rounds", label: "Rounds", r: true, get: (c) => c.rounds, cell: (c) => c.rounds },
      { key: "last_amount", label: "Last round", r: true, get: (c) => c.last_amount_eur_m ?? -1, cell: (c) => fmtEur(c.last_amount_eur_m) },
      { key: "raised", label: "Known raised", r: true, get: (c) => c.total_known_eur_m ?? -1, cell: (c) => fmtEur(c.total_known_eur_m) },
      { key: "leads", label: "Last round leads", cls: "small", get: (c) => (c.last_leads[0] || {}).name || "", cell: (c) => c.last_leads.map((l) => l.name).join(", ") || "Lead unknown" },
    ],
    /* People: only name and company sort. Metric columns are facts to read, never an ordering of people. */
    founders: [
      { key: "name", label: "Person", cls: "name", get: (p) => p.name.toLowerCase(),
        cell: (p) => h("a", { href: `#/person/${encodeURIComponent(p.id)}` }, p.name) },
      { key: "company", label: "Company", get: (p) => p.company.toLowerCase(),
        cell: (p) => (p.company_key ? h("a", { href: `#/company/${encodeURIComponent(p.company_key)}` }, p.company) : p.company) },
      { key: "country", label: "Country", get: (p) => p.country, cell: (p) => p.country },
      { key: "roles", label: "Roles on file", r: true, nosort: true, cell: (p) => (p.metrics.roles ? `${p.metrics.roles}, ${p.metrics.roles_dated} dated` : "None") },
      { key: "tenure", label: "Avg years per role", r: true, nosort: true, cell: (p) => fmtYears(p.metrics.avg_tenure_years, p.metrics.avg_tenure_n) },
      { key: "ups", label: "Level-ups per year", r: true, nosort: true, cell: (p) => (p.metrics.level_ups_per_year ?? "n/a") },
      { key: "founded", label: "Founded", r: true, nosort: true, cell: (p) => p.metrics.companies_founded },
      { key: "tags", label: "Background", cls: "small", nosort: true, cell: (p) => p.tags.join(", ") || "None on file" },
    ],
  };

  /* ---------- state ---------- */
  const state = {
    role: null,
    filters: { funds: {}, companies: {}, founders: {} },
    ai: { funds: null, companies: null, founders: null }, // last AI response per view
    aiKeys: { funds: new Set(), companies: new Set(), founders: new Set() },
    sort: { funds: { key: "name", dir: 1 }, companies: { key: "last_round", dir: -1 }, founders: { key: "name", dir: 1 } },
    shown: { funds: PAGE, companies: PAGE, founders: PAGE },
    railOpen: false,
  };
  try { state.role = localStorage.getItem("explore.role"); } catch { /* storage blocked: role stays per page load */ }
  const setRole = (r) => {
    state.role = r;
    document.body.dataset.role = r || "";
    try { localStorage.setItem("explore.role", r); } catch { /* ignore */ }
  };

  const main = () => document.getElementById("main");

  /* ---------- router ---------- */
  async function route() {
    const parts = location.hash.replace(/^#\/?/, "").split("/").map(decodeURIComponent);
    const [page, key] = parts;
    document.querySelectorAll("[data-nav]").forEach((a) => a.removeAttribute("aria-current"));
    const nav = { "": "start", funds: "funds", companies: "companies", founders: "founders", fund: "funds", company: "companies", person: "founders" }[page || ""];
    const cur = document.querySelector(`[data-nav="${nav}"]`);
    if (cur) cur.setAttribute("aria-current", "page");
    const m = main();
    try {
      if (!page) await renderStart(m);
      else if (page === "funds") { setRole("founder"); await renderExplorer(m, "funds"); }
      else if (page === "companies" || page === "founders") { setRole("investor"); await renderExplorer(m, page); }
      else if (page === "fund") await renderFund(m, key);
      else if (page === "company") await renderCompany(m, key);
      else if (page === "person") await renderPerson(m, key);
      else m.replaceChildren(h("div", { class: "page" }, h("p", { class: "error" }, "Page not found. "), h("a", { href: "#/" }, "Start over")));
    } catch (err) {
      m.replaceChildren(h("div", { class: "page" }, h("p", { class: "error", role: "alert" }, `Could not load this view: ${err.message}`)));
      console.error(err);
    }
  }

  /* ---------- start: role picker ---------- */
  async function renderStart(m) {
    const meta = await api.meta();
    m.replaceChildren(h("section", { class: "start", "aria-labelledby": "start-h" },
      h("h1", { id: "start-h" }, "Explore the receipts"),
      h("p", { class: "sub" }, "Filter funds, companies and founder careers counted from Cala data. Describe what you want and the filters set themselves. Every number links to the rounds behind it."),
      h("div", { class: "roles" },
        h("a", { class: "role", href: "#/funds", "data-role": "founder" },
          h("b", {}, "I am a founder"),
          h("span", {}, "Find funds that actually lead rounds at your stage and size, and see how they behaved when the market turned."),
          h("em", {}, "Explore funds")),
        h("a", { class: "role", href: "#/companies", "data-role": "investor" },
          h("b", {}, "I am an investor"),
          h("span", {}, "Find companies by stage and time since their last round, and read founder careers as timelines and facts."),
          h("em", {}, "Explore companies and founders"))),
      h("div", { class: "start-facts num" },
        h("span", {}, plural(meta.counts.funds, "fund")),
        h("span", {}, plural(meta.counts.companies, "company", "companies")),
        h("span", {}, `${plural(meta.counts.founders, "founder")} with Cala career records`),
        h("span", {}, `${meta.source.name}, retrieved ${meta.source.retrieved}`))));
  }

  /* ---------- explorer (filter rail + table) ---------- */
  const VIEW_TEXT = {
    funds: { title: "Funds", sub: "Who leads, at what size, and how recently. Counted from rounds, not from fund websites.",
      ph: "For example: seed funds in the Nordics that lead rounds around €3M and led during 2022 to 2023" },
    companies: { title: "Companies", sub: "Companies by stage, country and time since their last round.",
      ph: "For example: Series A companies in Sweden or Finland with no round in the last 18 months" },
    founders: { title: "Founders", sub: "Career records as facts. Filter by background, time per employer and title steps.",
      ph: "For example: repeat founders who came from strategy consulting and moved up titles quickly" },
  };

  async function renderExplorer(m, view) {
    const [meta, list] = await Promise.all([api.meta(), api.list(view)]);
    const funds = view === "funds" ? list : null;
    const opts = {
      countries: meta.countries, stages: meta.stages, founder_tags: meta.founder_tags, investors: meta.investors,
      fundNames: funds ? funds.items.map((f) => f.name) : meta.investors,
    };
    const t = VIEW_TEXT[view];
    const isInvestor = view !== "funds";

    const page = h("div", { class: "page" });
    page.append(h("div", { class: "page-h" },
      h("div", {}, h("h1", {}, t.title), h("p", {}, t.sub))));
    if (isInvestor) {
      page.append(h("div", { class: "tabs", role: "tablist", "aria-label": "Investor views" },
        h("a", { href: "#/companies", role: "tab", "aria-selected": String(view === "companies") }, "Companies"),
        h("a", { href: "#/founders", role: "tab", "aria-selected": String(view === "founders") }, "Founders")));
    }
    if (view === "founders" && list.coverage) {
      const cv = list.coverage;
      const hv = (n) => `${n} ${n === 1 ? "has" : "have"}`;
      page.append(h("p", { class: "banner" }, h("span", { class: "badge" }, "Coverage"),
        h("span", {}, `Cala career records for ${cv.founders_fetched} founders of ${cv.companies_with_founder_edge} Nordic companies. ` +
          `${hv(cv.founders_with_any_role)} any role on file, ${hv(cv.founders_with_role_outside_company)} a role outside their own company and ` +
          `${hv(cv.founders_with_dated_role)} dated roles, so tenure and title-pace values rest on very few people. Fetched ${cv.generated}.`)));
    }
    page.append(askBox(view, t.ph));
    const aiOut = h("div", { id: "ai-out" });
    page.append(aiOut);

    const explorer = h("div", { class: "explorer" + (state.railOpen ? "" : " rail-closed") });
    const rail = h("aside", { class: "rail", "aria-label": "Filters", id: "rail" });
    const results = h("section", { class: "results", "aria-label": "Results" });
    explorer.append(rail, results);
    page.append(explorer);
    m.replaceChildren(page);

    const rerender = () => {
      renderAiOut(aiOut, view, rerender);
      renderRail(rail, view, opts, rerender);
      renderResults(results, view, list, explorer, rerender);
    };
    page.querySelector("form.ask").addEventListener("submit", async (e) => {
      e.preventDefault();
      const input = e.target.querySelector("input");
      const btn = e.target.querySelector("button");
      const text = input.value.trim();
      if (!text) { input.focus(); return; }
      btn.disabled = true; btn.textContent = "Setting filters";
      try {
        const res = await api.aiFilters({ role: state.role || (isInvestor ? "investor" : "founder"), view, text });
        const target = res.view && FILTERS[res.view] ? res.view : view;
        state.filters[target] = { ...res.filters };
        state.aiKeys[target] = new Set(Object.keys(res.filters));
        state.ai[target] = { ...res, text };
        state.shown[target] = PAGE;
        if (target !== view) { location.hash = `#/${target}`; return; }
        rerender();
      } catch (err) {
        aiOut.replaceChildren(h("p", { class: "error", role: "alert" }, `Could not set filters: ${err.message}`));
      } finally {
        btn.disabled = false; btn.textContent = "Set filters";
      }
    });
    rerender();
  }

  function askBox(view, ph) {
    const prev = state.ai[view];
    return h("form", { class: "ask", role: "search", "aria-label": "Describe what you are looking for" },
      h("label", {}, h("span", { class: "sr" }, "Describe what you are looking for"),
        h("input", { type: "text", name: "q", placeholder: ph, value: prev ? prev.text : "", autocomplete: "off", maxlength: "400" })),
      h("button", { class: "btn primary", type: "submit" }, "Set filters"));
  }

  function renderAiOut(el, view, rerender) {
    const ai = state.ai[view];
    const keys = [...state.aiKeys[view]];
    if (!ai) { el.replaceChildren(); return; }
    const labels = keys.map((k) => (defOf(view, k) || { label: k }).label);
    el.replaceChildren(h("div", { class: "ask-out", role: "status" },
      h("span", { class: "badge ai" }, "AI"),
      keys.length
        ? h("span", {}, `Set ${plural(keys.length, "filter")}: ${labels.join("; ")}. Edit any of them in the filter rail.`)
        : h("span", {}, "No filter matched that description. Try naming a stage, a country, a round size or a background."),
      ai.unmatched && ai.unmatched.length ? h("span", { class: "muted" }, `Not used: ${ai.unmatched.join(", ")}.`) : null,
      ai.engine ? h("span", { class: "muted" }, `Read by ${ai.engine}${ai.notice ? ` (${ai.notice})` : ""}`) : null,
      h("span", { class: "sp" }),
      keys.length ? h("button", { class: "linkbtn", type: "button", onclick: () => {
        for (const k of keys) delete state.filters[view][k];
        state.aiKeys[view].clear(); state.ai[view] = null; rerender();
      } }, "Clear AI filters") : null));
  }

  function setFilter(view, key, value) {
    if (has(value)) state.filters[view][key] = value;
    else delete state.filters[view][key];
    state.aiKeys[view].delete(key); // the user owns it now
    state.shown[view] = PAGE;
  }

  function renderRail(rail, view, opts, rerender) {
    const f = state.filters[view];
    const n = Object.keys(f).length;
    rail.replaceChildren(h("div", { class: "rail-h" }, h("h2", {}, "Filters"),
      n ? h("button", { class: "linkbtn", type: "button", onclick: () => {
        state.filters[view] = {}; state.aiKeys[view].clear(); state.ai[view] = null; rerender();
      } }, "Clear all") : null));
    for (const d of FILTERS[view]) rail.append(filterControl(view, d, opts, rerender));
  }

  function filterControl(view, d, opts, rerender) {
    const v = state.filters[view][d.key];
    const ai = state.aiKeys[view].has(d.key);
    const id = `f-${view}-${d.key}`;
    const g = h("div", { class: "fgroup" + (ai ? " ai-set" : "") });
    g.append(h("label", { class: "flabel", for: id }, d.label, ai ? h("span", { class: "badge ai", title: "Set by AI from your description" }, "AI") : null));
    const commit = (val) => { setFilter(view, d.key, val); rerender(); };
    if (d.type === "text") {
      const inp = h("input", { class: "fin", id, type: "search", placeholder: d.ph, value: v || "" });
      let tmr;
      inp.addEventListener("input", () => { clearTimeout(tmr); tmr = setTimeout(() => { commit(inp.value.trim()); focusBack(id); }, 220); });
      g.append(inp);
    } else if (d.type === "number") {
      const inp = h("input", { class: "fin", id, type: "number", min: "0", inputmode: "numeric", value: v ?? "" });
      inp.addEventListener("change", () => commit(inp.value === "" ? null : +inp.value));
      g.append(inp);
    } else if (d.type === "month") {
      const inp = h("input", { class: "fin", id, type: "month", value: v || "" });
      inp.addEventListener("change", () => commit(inp.value || null));
      g.append(inp);
    } else if (d.type === "select") {
      const sel = h("select", { class: "fin", id }, h("option", { value: "" }, "Any time"),
        d.options.map(([val, label]) => h("option", { value: val, selected: String(v) === String(val) }, label)));
      sel.addEventListener("change", () => commit(sel.value || null));
      g.append(sel);
    } else if (d.type === "check") {
      const cb = h("input", { type: "checkbox", id, checked: !!v });
      cb.addEventListener("change", () => commit(cb.checked || null));
      g.querySelector("label").removeAttribute("for");
      g.append(h("label", { class: "fcheck", for: id }, cb, h("span", {}, d.text)));
    } else if (d.type === "range") {
      const r = v || {};
      const mk = (which, ph) => {
        const inp = h("input", { class: "fin", type: "number", step: d.step || 1, min: "0", placeholder: ph, value: r[which] ?? "",
          id: which === "min" ? id : `${id}-max`, "aria-label": `${d.label}, ${which === "min" ? "from" : "to"}` });
        inp.addEventListener("change", () => {
          const next = { ...(state.filters[view][d.key] || {}) };
          next[which] = inp.value === "" ? null : +inp.value;
          commit(next.min == null && next.max == null ? null : next);
        });
        return inp;
      };
      g.append(h("div", { class: "frange" }, mk("min", "Min"), h("span", {}, "to"), mk("max", "Max")));
    } else if (d.type === "multi") {
      const list = v || [];
      const all = opts[d.opts] || [];
      const fmt = d.fmt || ((x) => x);
      if (d.free) {
        const dl = `${id}-list`;
        const inp = h("input", { class: "fin", id, list: dl, placeholder: d.ph || "Type to add", autocomplete: "off" });
        const add = () => { const val = inp.value.trim(); if (val && !list.includes(val)) commit([...list, val]); };
        inp.addEventListener("change", add);
        inp.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); add(); } });
        g.append(inp, h("datalist", { id: dl }, all.slice(0, 1500).map((o) => h("option", { value: o }))));
      } else {
        const sel = h("select", { class: "fin", id }, h("option", { value: "" }, list.length ? "Add another" : "Any"),
          all.filter((o) => !list.includes(o)).map((o) => h("option", { value: o }, fmt(o))));
        sel.addEventListener("change", () => { if (sel.value) commit([...list, sel.value]); });
        g.append(sel);
      }
      if (list.length) {
        g.append(h("div", { class: "fchips" }, list.map((x) => h("span", { class: "chip" + (ai ? " ai" : "") }, fmt(x),
          h("button", { type: "button", "aria-label": `Remove ${fmt(x)}`, onclick: () => commit(list.filter((y) => y !== x)) }, "×")))));
      }
    }
    if (d.hint) g.append(h("p", { class: "fhint" }, d.hint));
    return g;
  }
  function focusBack(id) { const el = document.getElementById(id); if (el) { el.focus(); const n = el.value.length; try { el.setSelectionRange(n, n); } catch { /* search inputs */ } } }

  function valueText(d, v) {
    if (d.type === "check") return d.label;
    if (d.type === "multi") return `${d.label}: ${v.map(d.fmt || ((x) => x)).join(", ")}`;
    if (d.type === "range") {
      const r = v.min != null && v.max != null ? `${v.min} to ${v.max}` : v.min != null ? `at least ${v.min}` : `at most ${v.max}`;
      return `${d.label}: ${r}`;
    }
    if (d.type === "select") return `${d.label} ${(d.options.find(([x]) => String(x) === String(v)) || [0, v])[1]}`;
    if (d.type === "month") return `${d.label} ${fmtYm(v)}`;
    return `${d.label}: ${v}`;
  }

  function applyFilters(view, items) {
    const f = state.filters[view];
    const active = FILTERS[view].filter((d) => has(f[d.key]));
    return items.filter((it) => active.every((d) => d.test(it, f[d.key])));
  }

  function renderResults(el, view, list, explorer, rerender) {
    const rows = applyFilters(view, list.items);
    const sort = state.sort[view];
    const col = COLUMNS[view].find((c) => c.key === sort.key) || COLUMNS[view][0];
    rows.sort((a, b) => { const x = col.get(a), y = col.get(b); return (x < y ? -1 : x > y ? 1 : 0) * sort.dir; });
    const f = state.filters[view];
    const nActive = Object.keys(f).length;
    const noun = { funds: ["fund", "funds"], companies: ["company", "companies"], founders: ["person", "people"] }[view];

    const head = h("div", { class: "results-h" },
      h("button", { class: "btn line sm rail-toggle", type: "button", "aria-controls": "rail", "aria-expanded": String(state.railOpen),
        onclick: () => { state.railOpen = !state.railOpen; explorer.classList.toggle("rail-closed", !state.railOpen); rerender(); } },
        nActive ? `Filters (${nActive})` : "Filters"),
      h("span", { class: "count num", role: "status" }, `${rows.length.toLocaleString("en")} of ${plural(list.items.length, noun[0], noun[1])}`),
      h("span", { class: "sp" }),
      h("div", { class: "active" }, FILTERS[view].filter((d) => has(f[d.key])).map((d) =>
        h("span", { class: "chip" + (state.aiKeys[view].has(d.key) ? " ai" : "") }, valueText(d, f[d.key]),
          h("button", { type: "button", "aria-label": `Remove filter ${d.label}`, onclick: () => { setFilter(view, d.key, null); rerender(); } }, "×")))));

    const parts = [head];
    if (view === "founders" && rows.length) parts.push(founderScatter(rows));
    if (!rows.length) {
      parts.push(h("div", { class: "table-wrap" }, h("p", { class: "empty" }, "Nothing matches these filters. Remove one to widen the search.",
        view === "founders" ? " Cala has career records for only a few founders in this sample, so career filters often come back empty." : "")));
    } else {
      const shown = rows.slice(0, state.shown[view]);
      const table = h("table", { class: "grid" },
        h("caption", { class: "sr" }, `${VIEW_TEXT[view].title}, sortable by column`),
        h("thead", {}, h("tr", {}, COLUMNS[view].map((c) => {
          if (c.nosort) return h("th", { scope: "col", class: c.r ? "plain r" : "plain" }, c.label);
          const on = c.key === sort.key;
          return h("th", { scope: "col", class: c.r ? "r" : null, "aria-sort": on ? (sort.dir > 0 ? "ascending" : "descending") : null },
            h("button", { type: "button", onclick: () => {
              state.sort[view] = on ? { key: c.key, dir: -sort.dir } : { key: c.key, dir: c.r ? -1 : 1 };
              rerender();
            } }, c.label, h("span", { class: "arrow", "aria-hidden": "true" }, on ? (sort.dir > 0 ? "▲" : "▼") : "↕")));
        }))),
        h("tbody", {}, shown.map((it) => h("tr", {}, COLUMNS[view].map((c) => h("td", { class: [c.cls, c.r ? "r" : null].filter(Boolean).join(" ") || null }, c.cell(it)))))));
      parts.push(h("div", { class: "table-wrap" }, table));
      if (rows.length > shown.length) {
        parts.push(h("div", { class: "more" }, h("button", { class: "btn line", type: "button", onclick: () => { state.shown[view] += PAGE; rerender(); } },
          `Show ${Math.min(PAGE, rows.length - shown.length)} more`)));
      }
    }
    parts.push(h("p", { class: "note" }, sourceLine(list.source)));
    // Below the table: a different list (Cala's previous-employer queries), not a filter result
    if (view === "founders" && list.cohorts && list.cohorts.length) parts.push(cohortPanel(list.cohorts));
    el.replaceChildren(...parts);
  }

  const sourceLine = (src) => (src ? `Source: ${src.name}, retrieved ${src.retrieved}. ${src.note || ""}` : "");

  /* ---------- founders cohort scatter (facts, not scores) ---------- */
  /* Below 3 people with both values a scatter would only decorate one or two dots, so the panel says so instead. */
  function founderScatter(rows) {
    const pts = rows.filter((p) => p.metrics.avg_tenure_years != null && p.metrics.level_ups_per_year != null);
    const head = h("div", { class: "section-h" }, h("h2", {}, "Years per role and title pace"),
      h("span", { class: "muted" }, `${plural(pts.length, "person", "people")} of ${rows.length} with both values`));
    if (pts.length < 3) {
      return h("div", { class: "panel section", "aria-label": "Career pace" }, head,
        h("p", { class: "neutral" }, `Cala has dated roles for too few people in this set to chart. ${pts.map((p) => `${p.name}: ${fmtYears(p.metrics.avg_tenure_years, p.metrics.avg_tenure_n)} per role, ${p.metrics.level_ups_per_year} level-ups per year.`).join(" ")} Open a person for their timeline.`));
    }
    const W = chartW(640), H = 220, L = 46, R = 14, T = 12, B = 34;
    const xMax = Math.max(4, ...pts.map((p) => p.metrics.avg_tenure_years)) * 1.1;
    const yMax = Math.max(1, ...pts.map((p) => p.metrics.level_ups_per_year)) * 1.1;
    const X = (v) => L + (v / xMax) * (W - L - R);
    const Y = (v) => T + (1 - v / yMax) * (H - T - B);
    const svg = s("svg", { class: "chart", viewBox: `0 0 ${W} ${H}`, role: "img",
      "aria-label": `Average years per role against title level-ups per year for ${pts.length} people` });
    for (let i = 0; i <= 4; i++) {
      const yv = (yMax / 4) * i, xv = (xMax / 4) * i;
      svg.append(s("line", { class: "gridl", x1: L, x2: W - R, y1: Y(yv), y2: Y(yv) }),
        s("text", { x: L - 6, y: Y(yv) + 4, "text-anchor": "end" }, yv.toFixed(1)),
        s("text", { x: X(xv), y: H - B + 16, "text-anchor": "middle" }, xv.toFixed(1)));
    }
    svg.append(s("text", { x: (L + W - R) / 2, y: H - 4, "text-anchor": "middle" }, "Average years per dated role"),
      s("text", { x: 12, y: (T + H - B) / 2, transform: `rotate(-90 12 ${(T + H - B) / 2})`, "text-anchor": "middle" }, "Level-ups per year"));
    for (const p of pts) {
      svg.append(s("a", { href: `#/person/${encodeURIComponent(p.id)}` },
        s("circle", { class: "c-pt", cx: X(p.metrics.avg_tenure_years), cy: Y(p.metrics.level_ups_per_year), r: 6 },
          svgTitle(`${p.name}: ${p.metrics.avg_tenure_years} years per role, ${p.metrics.level_ups_per_year} level-ups per year`))));
    }
    return h("div", { class: "panel section", "aria-label": "Career pace chart" }, head, svg,
      h("p", { class: "neutral" }, "Each dot is one person in the filtered set. Position shows two facts from the career record. No position is better than another, and Recount does not rank people."));
  }

  /* ---------- background cohorts: Cala's "founder previously worked at X" lists ---------- */
  function cohortPanel(cohorts) {
    return h("section", { class: "panel section", "aria-labelledby": "coh-h" },
      h("div", { class: "section-h" }, h("h2", { id: "coh-h" }, "Where founders worked before"),
        h("span", { class: "muted" }, "Companies Cala lists for a founder's previous employer")),
      h("p", { class: "neutral" }, "Each list is one Cala query. Rows carry no source links, so a stated prior job is a claim to check, not a fact. Some rows are companies the employer funded or bought, and each row says which."),
      cohorts.map((c) => h("details", { class: "cohort" },
        h("summary", {}, h("b", {}, c.employer),
          h("span", { class: "muted num" }, c.n ? ` ${plural(c.n, "company", "companies")}, ${c.n_worked_at_stated} say a founder worked there, ${c.n_in_snapshot} in our round data` : " No companies returned")),
        c.rows.length ? h("div", { class: "table-wrap" }, h("table", { class: "grid" },
          plainHead(["Company", "Founders", "Founded", "Tie to employer", "What the row says"], -1),
          h("tbody", {}, c.rows.map((r) => h("tr", {},
            h("td", { class: "name" }, r.ckey ? h("a", { href: `#/company/${encodeURIComponent(r.ckey)}` }, r.company) : r.company),
            h("td", { class: "small" }, r.founders || "Not named"), h("td", {}, r.founded || "n/a"),
            h("td", { class: "small" }, r.relation_label), h("td", { class: "small" }, r.evidence || r.about || "")))))) : null,
        h("p", { class: "note" }, `Source: ${c.source}, fetched ${c.fetched}.`))));
  }

  /* ---------- fund detail ---------- */
  async function renderFund(m, key) {
    const [f, fundsList] = await Promise.all([api.detail("funds", key), api.list("funds")]);
    const fundKeys = new Set(fundsList.items.map((x) => x.key));
    const page = h("div", { class: "page detail" },
      h("p", { class: "crumbs" }, h("a", { href: "#/funds" }, "Funds"), " / ", f.name),
      h("div", { class: "d-h" }, h("div", {}, h("h1", {}, f.name),
        h("p", { class: "meta" }, `${plural(f.rounds, "round")} on record, ${f.lead_unknown} with the lead unknown`))),
      tiles([
        ["Lead share", fmtPct(f.lead_share), `of ${f.lead_known} lead-known`],
        ["Rounds led", f.led],
        ["Median led round", fmtEur(f.median_led_round_eur_m)],
        ["Last lead", fmtYm(f.last_lead), f.months_since_last_lead != null ? `${f.months_since_last_lead} mo ago` : ""],
        ["Led in 2022 to 2023", f.downturn_led, `of ${f.downturn_lead_known} lead-known`],
        ["Exit receipts", f.exit_receipts || "None found"],
      ]),
      h("section", { class: "section panel", "aria-labelledby": "pace-h" },
        h("div", { class: "section-h" }, h("h2", { id: "pace-h" }, "Lead pace by year"),
          h("span", { class: "legend" }, h("span", {}, h("i", { class: "l-led" }), "Led"), h("span", {}, h("i", { class: "l-joined" }), "Joined"),
            h("span", {}, h("i", { class: "l-unknown" }), "Lead unknown"))),
        paceChart(f.pace),
        h("p", { class: "neutral" }, "Counts of announced rounds per year. Grey rounds had another lead. Light rounds have no lead named in the source, so they could go either way.")),
      h("div", { class: "two section" },
        h("section", { "aria-labelledby": "rounds-h" },
          h("div", { class: "section-h" }, h("h2", { id: "rounds-h" }, "Recent rounds"), h("span", { class: "muted" }, `Latest ${f.recent_rounds.length}`)),
          h("div", { class: "table-wrap" }, h("table", { class: "grid" },
            plainHead(["Company", "Date", "Stage", "Amount", "Role"], 3),
            h("tbody", {}, f.recent_rounds.map((r) => h("tr", {},
              h("td", { class: "name" }, h("a", { href: `#/company/${encodeURIComponent(r.ckey)}` }, r.company)),
              h("td", {}, fmtYm(r.date)), h("td", {}, fmtStage(r.stage)), h("td", { class: "r" }, fmtEur(r.amount_eur_m)),
              h("td", {}, { led: "Led", joined: "Joined", unknown: "Lead unknown" }[r.role]))))))),
        h("div", {},
          h("section", { class: "panel", "aria-labelledby": "exits-h" },
            h("div", { class: "section-h" }, h("h2", { id: "exits-h" }, "Who bought its companies")),
            f.exits.length ? f.exits.map((x) => h("div", { class: "receipt" },
              h("div", {}, h("b", {}, x.company), ` acquired by ${x.acquirers.map((a) => a.name).join(", ")}, ${fmtYm(x.date.slice(0, 7))}`),
              h("div", { class: "muted" }, `${x.value.display} (${x.value.label})`),
              h("div", { class: "src" }, x.sources.map((src) => h("a", { href: src.url, rel: "noopener noreferrer", target: "_blank" }, src.name)))))
              : h("p", { class: "muted" }, "No acquisition receipt found in Cala yet."),
            h("p", { class: "neutral" }, f.exits_caveat)),
          h("section", { class: "panel section", "aria-labelledby": "co-h" },
            h("div", { class: "section-h" }, h("h2", { id: "co-h" }, "Shared rounds with")),
            h("ul", { class: "list" }, f.co_investors.map((c) => h("li", {},
              fundKeys.has(c.key) ? h("a", { href: `#/fund/${encodeURIComponent(c.key)}` }, c.name) : h("span", {}, c.name),
              h("span", { class: "muted num" }, plural(c.shared_rounds, "round"))))),
            h("p", { class: "neutral" }, "A shared round is not a relationship.")))),
      h("p", { class: "note" }, sourceLine(f.source)));
    m.replaceChildren(page);
    m.focus();
  }

  function plainHead(labels, rIdx) {
    return h("thead", {}, h("tr", {}, labels.map((x, i) => h("th", { scope: "col", class: i === rIdx ? "plain r" : "plain" }, x))));
  }

  function tiles(list) {
    return h("dl", { class: "tiles" }, list.map(([dt, dd, small]) => h("div", { class: "tile" }, h("dt", {}, dt), h("dd", { class: "num" }, String(dd), small ? h("small", {}, small) : null))));
  }

  function paceChart(pace) {
    const W = chartW(720), H = 220, L = 32, R = 8, T = 10, B = 26;
    const max = Math.max(1, ...pace.map((p) => p.led + p.joined + p.unknown));
    const step = Math.max(1, Math.ceil(max / 4));
    const top = step * 4;
    const bw = (W - L - R) / pace.length;
    const Y = (v) => T + (1 - v / top) * (H - T - B);
    const svg = s("svg", { class: "chart", viewBox: `0 0 ${W} ${H}`, role: "img",
      "aria-label": "Rounds per year split into led, joined and lead unknown: " + pace.map((p) => `${p.year} ${p.led} led, ${p.joined} joined, ${p.unknown} unknown`).join("; ") });
    for (let v = 0; v <= top; v += step) {
      svg.append(s("line", { class: "gridl", x1: L, x2: W - R, y1: Y(v), y2: Y(v) }), s("text", { x: L - 6, y: Y(v) + 4, "text-anchor": "end" }, v));
    }
    const every = Math.max(1, Math.ceil(pace.length / Math.floor((W - L - R) / 44)));
    pace.forEach((p, i) => {
      const x = L + i * bw + bw * 0.18, w = bw * 0.64;
      let base = 0;
      const g = s("g", {}, svgTitle(`${p.year}: ${p.led} led, ${p.joined} joined, ${p.unknown} lead unknown`));
      for (const [k, cls] of [["led", "c-led"], ["joined", "c-joined"], ["unknown", "c-unknown"]]) {
        if (!p[k]) continue;
        g.append(s("rect", { class: cls, x, width: w, y: Y(base + p[k]), height: Y(base) - Y(base + p[k]) }));
        base += p[k];
      }
      svg.append(g);
      if (i % every === 0) svg.append(s("text", { x: x + w / 2, y: H - 8, "text-anchor": "middle" }, p.year));
    });
    svg.append(s("line", { class: "axis", x1: L, x2: W - R, y1: Y(0), y2: Y(0) }));
    return svg;
  }

  /* ---------- company detail ---------- */
  async function renderCompany(m, key) {
    const [c, fundsList] = await Promise.all([api.detail("companies", key), api.list("funds")]);
    const fundKeys = new Set(fundsList.items.map((x) => x.key));
    const inv = (i) => (fundKeys.has(i.key) ? h("a", { href: `#/fund/${encodeURIComponent(i.key)}` }, i.name) : h("span", {}, i.name));
    const join = (arr) => arr.flatMap((x, i) => (i ? [", ", inv(x)] : [inv(x)]));
    m.replaceChildren(h("div", { class: "page detail" },
      h("p", { class: "crumbs" }, h("a", { href: "#/companies" }, "Companies"), " / ", c.name),
      h("div", { class: "d-h" }, h("div", {}, h("h1", {}, c.name), h("p", { class: "meta" }, c.country || "Country unknown", " · ", fmtStage(c.last_stage)))),
      tiles([
        ["Rounds on record", c.rounds],
        ["Last round", fmtYm(c.last_round), `${c.months_since_last_round} mo ago`],
        ["Known raised", fmtEur(c.total_known_eur_m)],
        ["Investors named", c.investors.length],
      ]),
      h("section", { class: "section panel", "aria-labelledby": "tl-h" },
        h("div", { class: "section-h" }, h("h2", { id: "tl-h" }, "Rounds timeline"),
          h("span", { class: "legend" }, h("span", {}, h("i", { class: "l-led" }), "Lead named"), h("span", {}, h("i", { class: "l-unknown" }), "Lead unknown"))),
        roundsTimeline(c.timeline)),
      c.founders.length ? h("section", { class: "section panel", "aria-labelledby": "fo-h" },
        h("div", { class: "section-h" }, h("h2", { id: "fo-h" }, "Founders with a Cala record"),
          c.founder_tags.length ? h("span", { class: "muted" }, `Background: ${c.founder_tags.join(", ")}`) : null),
        h("ul", { class: "list" }, c.founders.map((p) => h("li", {}, h("a", { href: `#/person/${encodeURIComponent(p.id)}` }, p.name),
          h("span", { class: "muted" }, "Career facts and source"))))) : null,
      h("section", { class: "section", "aria-labelledby": "rl-h" },
        h("div", { class: "section-h" }, h("h2", { id: "rl-h" }, "Rounds and leads")),
        h("div", { class: "table-wrap" }, h("table", { class: "grid" },
          plainHead(["Date", "Round", "Amount", "Lead", "Also in the round"], 2),
          h("tbody", {}, [...c.timeline].reverse().map((r) => h("tr", {},
            h("td", {}, fmtYm(r.date)), h("td", {}, r.type || fmtStage(r.stage)), h("td", { class: "r" }, fmtEur(r.amount_eur_m)),
            h("td", {}, r.leads.length ? join(r.leads) : h("span", { class: "muted" }, "Lead unknown")),
            h("td", { class: "small" }, r.participants.map((p) => p.name).join(", ") + (r.participants_total > r.participants.length ? ` and ${r.participants_total - r.participants.length} more` : "")))))))),
      h("p", { class: "note" }, sourceLine(c.source))));
    m.focus();
  }

  function roundsTimeline(tl) {
    const W = chartW(720), H = 120, L = 20, R = 20, mid = 62;
    const ts = tl.map((r) => ymToNum(r.date));
    const t0 = Math.floor(Math.min(...ts)), t1 = Math.max(Math.ceil(Math.max(...ts)), t0 + 2);
    const X = (t) => L + ((t - t0) / (t1 - t0)) * (W - L - R);
    const maxAmt = Math.max(1, ...tl.map((r) => r.amount_eur_m || 0));
    const svg = s("svg", { class: "chart", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": `${tl.length} rounds from ${t0} to ${t1}` });
    svg.append(s("line", { class: "axis", x1: L, x2: W - R, y1: mid, y2: mid }));
    const yStep = Math.max(1, Math.ceil((t1 - t0) / Math.floor((W - L - R) / 48)));
    for (let y = t0; y <= t1; y += yStep) svg.append(s("line", { class: "gridl", x1: X(y), x2: X(y), y1: mid - 4, y2: mid + 4 }), s("text", { x: X(y), y: H - 6, "text-anchor": "middle" }, y));
    tl.forEach((r, i) => {
      const x = X(ymToNum(r.date));
      const rad = 5 + 11 * Math.sqrt((r.amount_eur_m || 0) / maxAmt);
      const up = i % 2 === 0;
      svg.append(s("g", {}, svgTitle(`${fmtYm(r.date)}: ${r.type || fmtStage(r.stage)}, ${fmtEur(r.amount_eur_m)}, lead ${r.leads.map((l) => l.name).join(", ") || "unknown"}`),
        s("circle", { class: r.leads.length ? "c-round" : "c-round unk", cx: x, cy: mid, r: rad }),
        s("text", { class: "lbl", x, y: up ? mid - rad - 6 : mid + rad + 14, "text-anchor": "middle" }, r.stage ? fmtStage(r.stage) : "Round")));
    });
    return svg;
  }

  /* ---------- person detail ---------- */
  async function renderPerson(m, id) {
    const [p, meta] = await Promise.all([api.detail("founders", id), api.meta()]);
    const mt = p.metrics;
    const src = p.source;
    const dated = p.roles.length > 0;
    m.replaceChildren(h("div", { class: "page detail" },
      h("p", { class: "crumbs" }, h("a", { href: "#/founders" }, "Founders"), " / ", p.name),
      h("div", { class: "source", role: "note" }, h("span", { class: "dot", "aria-hidden": "true" }),
        h("span", {}, h("b", {}, "Source: "), `${src.name}, fetched ${src.retrieved}. Cala entity ${src.entity_id}. ${src.note}`,
          p.linkedin_url ? [" ", h("a", { href: p.linkedin_url, rel: "noopener noreferrer", target: "_blank" }, "Public profile")] : null)),
      h("div", { class: "d-h" }, h("div", {}, h("h1", {}, p.name),
        h("p", { class: "meta" }, p.company_key ? h("a", { href: `#/company/${encodeURIComponent(p.company_key)}` }, p.company) : p.company,
          ` · ${fmtStage(p.company_stage)} · ${p.country}`),
        p.description ? h("p", { class: "muted" }, p.description) : null),
        h("div", { class: "tags" }, p.tags.map((t) => h("span", { class: "tag", title: (p.tag_evidence[t] || []).join(", ") || null }, t)))),
      tiles([
        ["Roles on file", mt.roles, `${mt.roles_dated} with dates`],
        ["Organisations", mt.employers ?? "n/a"],
        ["Average years per role", mt.avg_tenure_years ?? "n/a", mt.avg_tenure_n ? `over ${plural(mt.avg_tenure_n, "dated role")}` : "needs start and end dates"],
        ["Shortest and longest", mt.shortest_tenure_years == null ? "n/a" : `${mt.shortest_tenure_years} to ${mt.longest_tenure_years} y`],
        ["Title level-ups", mt.level_ups ?? "n/a", mt.level_ups_per_year != null ? `${mt.level_ups_per_year} per year` : ""],
        ["Years before this company", mt.years_before_company ?? "n/a"],
        ["Companies founded", mt.companies_founded, mt.repeat_founder ? "founded one before" : ""],
      ]),
      h("section", { class: "section panel", "aria-labelledby": "career-h" },
        h("div", { class: "section-h" }, h("h2", { id: "career-h" }, "Career timeline"),
          dated ? h("span", { class: "legend" }, h("span", {}, h("i", { class: "l-joined" }), "Employed"), h("span", {}, h("i", { class: "l-led" }), "Own company")) : null),
        dated ? careerChart(p, src.retrieved) : h("p", { class: "muted" }, "Cala has no dated roles for this person, so there is no timeline to draw."),
        dated ? roleSources(p.roles) : null),
      p.roles.filter((r) => r.level != null).length > 1 ? h("section", { class: "section panel", "aria-labelledby": "level-h" },
        h("div", { class: "section-h" }, h("h2", { id: "level-h" }, "Title level over time"),
          h("span", { class: "muted" }, "Dots mark a dated role")),
        levelChart(p, meta.levels, src.retrieved),
        h("p", { class: "neutral" }, "Levels come from a keyword map of job titles (intern to founder). They describe a title, not the person.")) : null,
      p.undated_roles.length ? h("section", { class: "section", "aria-labelledby": "und-h" },
        h("div", { class: "section-h" }, h("h2", { id: "und-h" }, "Roles without dates")),
        h("ul", { class: "list panel" }, p.undated_roles.map((r) => h("li", {}, h("span", {}, h("b", {}, r.org), r.title !== "Title not stated" ? `, ${r.title}` : ""),
          h("span", { class: "muted" }, r.org_type))))) : null,
      h("section", { class: "section", "aria-labelledby": "founded-h" },
        h("div", { class: "section-h" }, h("h2", { id: "founded-h" }, "Companies founded")),
        h("ul", { class: "list panel" }, p.founded.map((f) => h("li", {}, h("span", {}, h("b", {}, f.company), ` · ${f.how}`),
          f.exit ? h("span", { class: "muted" }, f.exit) : null)))),
      p.gaps.length ? h("section", { class: "section", "aria-labelledby": "gaps-h" },
        h("div", { class: "section-h" }, h("h2", { id: "gaps-h" }, "What Cala does not have")),
        h("ul", { class: "list panel" }, p.gaps.map((g) => h("li", {}, h("span", {}, g))))) : null,
      h("p", { class: "neutral" }, "These are facts from Cala's career record: dates, titles and employers. Recount does not score, rank or predict people.")));
    m.focus();
  }

  function roleSources(roles) {
    return h("details", { class: "cohort" }, h("summary", {}, "Where each dated role comes from"),
      h("ul", { class: "list" }, roles.map((r) => h("li", {}, h("span", {}, h("b", {}, r.org), `, ${r.title}`),
        h("span", { class: "src" }, r.sources.length ? r.sources.map((x) => h("a", { href: x.url, rel: "noopener noreferrer", target: "_blank" }, `${x.name}${x.date ? `, ${x.date}` : ""}`)) : "No source link in Cala")))));
  }

  function careerRange(p, retrieved) {
    const end = ymToNum(retrieved.slice(0, 7));
    return { t0: Math.floor(ymToNum(p.roles[0].start)), t1: Math.ceil(end + 0.01), end };
  }

  function careerChart(p, retrieved) {
    const { t0, t1, end } = careerRange(p, retrieved);
    const W = chartW(760), narrow = W < 560;
    const rowH = narrow ? 48 : 30, L = narrow ? 4 : 210, R = 16, T = 8;
    const H = T + p.roles.length * rowH + 26;
    const X = (t) => L + ((t - t0) / (t1 - t0)) * (W - L - R);
    const until = (r) => (r.end ? fmtYm(r.end) : r.current ? "now" : "end not known");
    const svg = s("svg", { class: "chart", viewBox: `0 0 ${W} ${H}`, role: "img",
      "aria-label": "Career timeline: " + p.roles.map((r) => `${r.title} at ${r.org}, ${fmtYm(r.start)} to ${until(r)}, ${fmtMonths(r.months)}`).join("; ") });
    const yStep = Math.max(1, Math.ceil((t1 - t0) / Math.floor((W - L - R) / 48)));
    for (let y = t0; y <= t1; y += yStep) svg.append(s("line", { class: "gridl", x1: X(y), x2: X(y), y1: T, y2: H - 22 }), s("text", { x: X(y), y: H - 6, "text-anchor": narrow && y === t0 ? "start" : "middle" }, y));
    let lastOrg = null, alt = false;
    p.roles.forEach((r, i) => {
      if (r.org !== lastOrg) { alt = !alt; lastOrg = r.org; }
      const y = T + i * rowH + (narrow ? 18 : 0);
      const a = X(ymToNum(r.start)), b = X(r.end ? ymToNum(r.end) : end);
      const own = r.org_type === "Own company";
      const w = Math.max(3, b - a);
      const len = r.end || r.current ? fmtMonths(r.months) : `${fmtMonths(r.months)}+`;
      svg.append(s("g", {}, svgTitle(`${r.title}, ${r.org} (${r.org_type}): ${fmtYm(r.start)} to ${until(r)}, ${fmtMonths(r.months)}`),
        narrow ? s("text", { class: "lbl", x: 0, y: y - 2 }, s("tspan", { class: "lbl-b" }, trunc(r.title, 26)), ` · ${trunc(r.org, 22)}`) : null,
        narrow ? null : s("text", { class: "lbl-b", x: 0, y: y + 13 }, trunc(r.title, 30)),
        narrow ? null : s("text", { x: 0, y: y + 26 }, trunc(r.org, 34)),
        s("rect", { class: own ? "c-own" : "c-role" + (alt ? "" : " alt"), x: a, y: y + 5, width: w, height: 18, rx: 3 }),
        w > 46 ? s("text", { class: "c-bar-txt", x: a + 6, y: y + 18 }, len) : s("text", { x: a + w + 4, y: y + 18 }, len)));
    });
    return svg;
  }
  /* Chart width follows the panel so text stays readable on a phone instead of shrinking with the viewBox. */
  const chartW = (max) => Math.max(320, Math.min(max, (main().clientWidth || max) - 60));
  const trunc = (t, n) => (t.length > n ? t.slice(0, n - 1) + "…" : t);

  /* levels: {"0": "Intern, trainee or analyst", ... "4": "Founder, C-level or partner"} from people.py */
  function levelChart(p, levels, retrieved) {
    const { t0, t1, end } = careerRange(p, retrieved);
    const roles = p.roles.filter((r) => r.level != null);
    const lvls = Object.keys(levels).map(Number).sort((a, b) => a - b);
    const lo = lvls[0], hi = lvls[lvls.length - 1];
    const W = chartW(760), narrow = W < 560, H = 200, L = narrow ? 70 : 210, R = 16, T = 12, B = 26;
    const X = (t) => L + ((t - t0) / (t1 - t0)) * (W - L - R);
    const Y = (lv) => T + (1 - (lv - lo) / (hi - lo)) * (H - T - B);
    const svg = s("svg", { class: "chart", viewBox: `0 0 ${W} ${H}`, role: "img",
      "aria-label": "Title level over time: " + roles.map((r) => `${fmtYm(r.start)} ${levels[r.level]}`).join(", ") });
    for (const lv of lvls) svg.append(s("line", { class: "gridl", x1: L, x2: W - R, y1: Y(lv), y2: Y(lv) }), s("text", { x: L - 8, y: Y(lv) + 4, "text-anchor": "end" }, trunc(levels[lv].split(",")[0], narrow ? 9 : 30)));
    const yStep = Math.max(1, Math.ceil((t1 - t0) / Math.floor((W - L - R) / 48)));
    for (let y = t0; y <= t1; y += yStep) svg.append(s("text", { x: X(y), y: H - 6, "text-anchor": "middle" }, y));
    let d = "";
    roles.forEach((r, i) => {
      const a = X(ymToNum(r.start)), b = X(r.end ? ymToNum(r.end) : end), y = Y(r.level);
      d += i ? ` H${a} V${y} H${b}` : `M${a} ${y} H${b}`;
    });
    svg.append(s("path", { class: "c-line", d }));
    roles.forEach((r) => svg.append(s("circle", { class: "c-dot", cx: X(ymToNum(r.start)), cy: Y(r.level), r: 4.5 },
      svgTitle(`${fmtYm(r.start)}: ${r.title} at ${r.org} (${levels[r.level]})`))));
    return svg;
  }

  /* ---------- boot ---------- */
  async function boot() {
    try {
      const meta = await api.meta();
      document.getElementById("side-source").textContent = meta.source.name;
      document.getElementById("side-date").textContent = `Retrieved ${meta.source.retrieved}`;
    } catch (err) {
      document.getElementById("side-date").textContent = "Source unavailable";
    }
    if (state.role) document.body.dataset.role = state.role;
    window.addEventListener("hashchange", () => { route(); window.scrollTo(0, 0); });
    route();
  }
  boot();
})();
