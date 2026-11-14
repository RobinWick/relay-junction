"use strict";
/* Front end. The product name comes from brand.js (window.APP_NAME). Plain JS, no build step. Everything rendered from API data goes through esc(). */

const $ = (s, el = document) => el.querySelector(s);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const fmtM = (m) => m == null ? "" : (m >= 100 ? Math.round(m) : m >= 10 ? m.toFixed(0) : m.toFixed(1).replace(/\.0$/, ""));
const plural = (n, a, b) => `${n} ${n === 1 ? a : b}`;

const APP = () => window.APP_NAME || "";
const state = {stage: "seed", investors: [], lead: null, competitors: [], meta: null, last: null, sortByVerdict: true};

const SAMPLE = [
  "Wed 10:30  Maki.vc  (Table 12)",
  "Voima Ventures",
  "Creandum - partner meeting",
  "Inventure",
  "Speedinvest",
  "Northzone",
  "Icebreaker.vc",
  "byFounders",
  "Seedcamp",
  "Point Nine",
  "Business Finland",
  "Superhero Capital",
  "FJ Labs",
  "Thu 14:00 coffee w/ Anna from Kvanted?",
].join("\n");

async function api(path, opts = {}) {
  const res = await fetch(path, {headers: {"Content-Type": "application/json"}, ...opts});
  if (res.status === 401) { location.href = "/login"; throw new Error("auth"); }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || body.error || `Request failed (${res.status})`);
  return body;
}

/* ---------------- routing ---------------- */
function route() {
  const isMethod = location.pathname === "/method";
  $("#view-check").classList.toggle("hidden", isMethod);
  $("#view-method").classList.toggle("hidden", !isMethod);
  $("#nav-check").toggleAttribute("aria-current", !isMethod);
  $("#nav-method").toggleAttribute("aria-current", isMethod);
  if (isMethod) $("#nav-method").setAttribute("aria-current", "page"); else $("#nav-check").setAttribute("aria-current", "page");
  if (isMethod) renderMethod();
}
document.addEventListener("click", (e) => {
  const a = e.target.closest("a[href^='/']");
  if (!a || a.target || e.metaKey || e.ctrlKey) return;
  if (a.getAttribute("href") === "/" || a.getAttribute("href") === "/method") {
    e.preventDefault(); history.pushState({}, "", a.getAttribute("href")); route(); window.scrollTo(0, 0);
  }
});
window.addEventListener("popstate", route);

/* ---------------- meta + form ---------------- */
async function init() {
  try {
    state.meta = await api("/api/meta");
    const m = state.meta;
    $("#data-chip").textContent = `Cala round data · ${m.funds_queried} funds · ${m.companies.toLocaleString("en")} companies · ${m.rounds.toLocaleString("en")} rounds · ${m.retrieved}`;
    $("#foot-version").textContent = `snapshot ${m.version}`;
    const seg = $("#stage-seg");
    seg.innerHTML = m.stages.slice(0, 6).map((s) => `<button type="button" data-stage="${esc(s.key)}" aria-pressed="${s.key === state.stage}">${esc(s.label)}</button>`).join("");
    seg.addEventListener("click", (e) => {
      const b = e.target.closest("button[data-stage]"); if (!b) return;
      state.stage = b.dataset.stage;
      seg.querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", x === b));
      if (activeTab() === "find") { if (state.findDone) runFind(); } else if (state.last) run();
    });
  } catch (err) {
    if (err.message !== "auth") $("#data-chip").textContent = "Could not load data. Reload the page.";
  }
  route();
}

function renderChips(kind) {
  const box = kind === "investors" ? $("#inv-chips") : $("#comp-chips");
  box.querySelectorAll(".tag").forEach((t) => t.remove());
  const input = box.querySelector("input");
  const items = kind === "investors" ? state.investors : state.competitors;
  items.forEach((name, i) => {
    const tag = document.createElement("span");
    const isLead = kind === "investors" && state.lead === name;
    tag.className = "tag" + (isLead ? " is-lead" : "");
    tag.innerHTML = `${esc(name)}${kind === "investors" ? `<button type="button" class="lead-toggle" data-lead="${i}" aria-pressed="${isLead}" title="Mark as your current lead">${isLead ? "lead" : "set lead"}</button>` : ""}<button type="button" data-rm="${i}" aria-label="Remove ${esc(name)}">×</button>`;
    box.insertBefore(tag, input);
  });
}

function setupChips(kind) {
  const box = kind === "investors" ? $("#inv-chips") : $("#comp-chips");
  const input = box.querySelector("input");
  const list = kind === "investors" ? state.investors : state.competitors;
  const max = kind === "investors" ? 12 : 3;
  const sug = $("#inv-suggest");
  let active = -1, items = [], timer;

  const add = (name) => {
    name = name.trim();
    if (!name || list.length >= max || list.some((x) => x.toLowerCase() === name.toLowerCase())) return;
    list.push(name);
    if (kind === "investors" && list.length === 1 && !state.lead) state.lead = name;
    input.value = ""; hide(); renderChips(kind);
  };
  const hide = () => { if (sug && kind === "investors") { sug.classList.add("hidden"); input.setAttribute("aria-expanded", "false"); } active = -1; };
  const show = (rows) => {
    items = rows;
    if (!rows.length) return hide();
    sug.innerHTML = rows.map((r, i) => `<button type="button" tabindex="-1" role="option" id="opt-${i}" data-i="${i}" aria-selected="${i === active}"><span>${esc(r.name)}</span><span class="faint mono">${r.rounds} rounds</span></button>`).join("");
    sug.classList.remove("hidden"); input.setAttribute("aria-expanded", "true");
    if (active >= 0) input.setAttribute("aria-activedescendant", `opt-${active}`); else input.removeAttribute("aria-activedescendant");
  };

  box.addEventListener("click", (e) => {
    const rm = e.target.closest("[data-rm]");
    if (rm) { const name = list[+rm.dataset.rm]; list.splice(+rm.dataset.rm, 1); if (state.lead === name) state.lead = null; renderChips(kind); return; }
    const ld = e.target.closest("[data-lead]");
    if (ld) { const name = list[+ld.dataset.lead]; state.lead = state.lead === name ? null : name; renderChips(kind); return; }
    const opt = e.target.closest("[data-i]");
    if (opt) { add(items[+opt.dataset.i].name); input.focus(); return; }
    input.focus();
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || (e.key === "," && kind === "competitors")) {
      e.preventDefault();
      if (kind === "investors" && active >= 0 && items[active]) add(items[active].name); else add(input.value);
    } else if (e.key === "Backspace" && !input.value && list.length) {
      const name = list.pop(); if (state.lead === name) state.lead = null; renderChips(kind);
    } else if (kind === "investors" && (e.key === "ArrowDown" || e.key === "ArrowUp") && items.length) {
      e.preventDefault(); active = (active + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length; show(items);
    } else if (e.key === "Escape") hide();
  });
  if (kind === "investors") {
    input.addEventListener("input", () => {
      clearTimeout(timer);
      const q = input.value.trim();
      if (q.length < 2) return hide();
      timer = setTimeout(async () => { try { active = -1; show(await api(`/api/suggest?q=${encodeURIComponent(q)}`)); } catch { hide(); } }, 120);
    });
    input.addEventListener("blur", () => setTimeout(hide, 150));
  }
}

/* ---------------- check ---------------- */
const activeTab = () => ($("#tab-find").getAttribute("aria-selected") === "true" ? "find" : "list");
function announce(msg) { const st = $("#status"); if (st) { st.textContent = ""; setTimeout(() => { st.textContent = msg; }, 50); } }
function lineCount() {
  const n = $("#funds").value.split(/\n|;/).filter((l) => l.trim().length > 1).length;
  $("#line-count").textContent = n ? plural(n, "line", "lines") : "";
  $("#go").textContent = n ? `Check ${plural(n, "line", "lines")}` : "Check funds";
}

async function run() {
  const text = $("#funds").value;
  if (!text.trim()) { $("#funds").focus(); return; }
  const out = $("#results");
  out.classList.remove("hidden");
  out.setAttribute("aria-busy", "true");
  out.innerHTML = skeleton();
  $("#go").disabled = true;
  try {
    const t = parseFloat(($("#target").value || "").replace(",", "."));
    const body = {
      funds_text: text, stage: state.stage, target_eur_m: isFinite(t) ? t : null,
      investors: state.investors, lead: state.lead, company: $("#company").value.trim() || null,
      competitors: state.competitors,
    };
    const data = await api("/api/check", {method: "POST", body: JSON.stringify(body)});
    state.last = data;
    renderResults(data, body);
  } catch (err) {
    if (err.message !== "auth") out.innerHTML = `<div class="alert" role="alert"><h3>Could not check the list</h3>${esc(err.message)}. Try again in a moment.</div>`;
  } finally {
    $("#go").disabled = false;
    out.setAttribute("aria-busy", "false");
  }
}

function skeleton() {
  const card = `<div class="fund"><div class="skel skel-lg"></div><div class="skel skel-md"></div><div class="skel"></div></div>`;
  return `<div class="skel skel-lg"></div><div class="fund-list">${card.repeat(4)}</div>`;
}

const VERDICT_ORDER = {leads: 0, leads_size: 1, mixed: 2, stale: 3, follows: 4, few: 5, public: 6};

const REGION_LABEL = {nordics: "the Nordics", baltics: "the Baltics", dach: "DACH", "uk-ie": "the UK and Ireland",
  "france-benelux": "France and Benelux", south: "Southern Europe", cee: "Central and Eastern Europe", "": "Europe"};

async function runFind() {
  const out = $("#results");
  out.classList.remove("hidden");
  out.setAttribute("aria-busy", "true");
  out.innerHTML = skeleton();
  const t = parseFloat(($("#target").value || "").replace(",", "."));
  const req = {stage: state.stage, target_eur_m: isFinite(t) ? t : null, region: $("#region").value || null,
               investors: state.investors, competitors: state.competitors};
  try {
    const d = await api("/api/discover", {method: "POST", body: JSON.stringify(req)});
    state.findDone = true;
    const counts = {};
    d.funds.forEach((f) => { counts[f.verdict] = (counts[f.verdict] || 0) + 1; });
    const sz = d.filters.size ? ` of EUR ${fmtM(d.filters.size[0])} to ${fmtM(d.filters.size[1])}m` : "";
    const view = {mode: "discover", stage: d.filters.stage, rows: d.funds, counts, unmatched: [], competitors: {},
      conflict_count: d.funds.filter((f) => f.conflicts.some((c) => c.level === "led")).length,
      headline: d.funds.length
        ? `In the <b>${d.rounds_matched}</b> ${esc(d.filters.stage)} rounds${sz} in ${esc(REGION_LABEL[req.region || ""])} from the last 30 months that we pulled from Cala, these <b>${d.funds.length}</b> funds led most often.`
        : `No ${esc(d.filters.stage)} rounds${sz} in ${esc(REGION_LABEL[req.region || ""])} over the last 30 months in our data. Widen the region or clear the target raise.`};
    state.last = null;
    renderResults(view, req);
  } catch (err) {
    if (err.message !== "auth") out.innerHTML = `<div class="alert" role="alert"><h3>Could not search</h3>${esc(err.message)}.</div>`;
  } finally { out.setAttribute("aria-busy", "false"); }
}

function summaryLine(d, target) {
  if (d.headline) return d.headline + (d.conflict_count ? ` <b class="conf-led">${d.conflict_count}</b> already led a competitor.` : "");
  const c = d.counts, n = d.rows.length;
  const parts = [];
  const leaders = (c.leads || 0) + (c.leads_size || 0);
  const fits = d.rows.filter((r) => r.verdict === "leads" && r.size?.fit === "fits").length;
  parts.push(`<b>${leaders} of your ${n}</b> ${n === 1 ? "fund" : "funds"} lead ${esc(d.stage)} rounds in Cala's data${target ? `, and <b>${fits}</b> of those lead rounds your size` : ""}`);
  if (c.follows) parts.push(`<b>${c.follows}</b> mostly ${c.follows === 1 ? "follows" : "follow"}`);
  if (c.stale) parts.push(`<b>${c.stale}</b> ${c.stale === 1 ? "has" : "have"} not led in the last two years`);
  if (d.conflict_count) parts.push(`<b class="conf-led">${d.conflict_count}</b> already led a competitor`);
  return parts.join(". ") + ".";
}

function renderResults(d, req) {
  const out = $("#results");
  const sorted = [...d.rows];
  const ranked = d.mode === "discover";  // find mode keeps the server's ranking by lead count
  if (state.sortByVerdict && !ranked) sorted.sort((a, b) => VERDICT_ORDER[a.verdict] - VERDICT_ORDER[b.verdict]);
  const cards = [];
  if (d.lead_back) {
    const l = d.lead_back;
    cards.push(`<div class="note note-accent"><h3>Will your lead come back?</h3>In Cala's data, <b>${esc(l.lead)}</b> led ${plural(l.cases, "round", "rounds")} whose company raised again. It came back in the next round in <b>${l.came_back} of ${l.cases}</b> and led it in <b>${l.led_again}</b>.</div>`);
  }
  if (d.timing) {
    const t = d.timing;
    cards.push(`<div class="note"><h3>Timing, from peers</h3>Companies in the data raised their ${esc(t.to)} a median <b>${t.median} months</b> after their ${esc(t.from)} (middle half ${t.p25} to ${t.p75}, n=${t.n}).</div>`);
  }
  if (Object.keys(d.competitors || {}).length) {
    const miss = Object.entries(d.competitors).filter(([, n]) => !n).map(([c]) => c);
    if (miss.length) cards.push(`<div class="note note-thin"><h3>Competitor not in our data</h3>${miss.map(esc).join(", ")}: no rounds found in our Cala snapshot, so no conflict can be shown for ${miss.length === 1 ? "it" : "them"}.</div>`);
  }
  const list = sorted.map((r, i) => cardHtml(r, i)).join("");
  out.innerHTML = `
    <div class="print-head"><b>${esc(APP())}</b> · ${esc(d.stage)}${req.target_eur_m ? ` · target EUR ${esc(req.target_eur_m)}m` : ""} · data: Cala, retrieved ${esc(state.meta?.retrieved || "")}</div>
    <div class="summary">
      <div><span class="mono-chip"><span class="bolt" aria-hidden="true"></span>Counting, not AI</span>
      <p class="summary-big">${summaryLine(d, req.target_eur_m)}</p></div>
      <div class="actions">
        <button class="btn btn-sm${ranked ? " hidden" : ""}" type="button" id="sort">${state.sortByVerdict ? "Show in my order" : "Best first"}</button>
        <button class="btn btn-sm" type="button" id="print">Print sheet</button>
        <button class="btn btn-sm btn-ghost" type="button" id="csv">Copy as CSV</button>
      </div>
    </div>
    ${cards.length ? `<div class="cards-top">${cards.join("")}</div>` : ""}
    <div class="fund-list">${list || `<div class="card empty">None of the pasted lines matched a fund in our Cala data.</div>`}</div>
    ${geminiNote(d.read_by_gemini)}
    ${d.lookup_candidates?.length ? lookupPanel(d.lookup_candidates) : ""}
    ${d.unmatched.length ? `<div class="unmatched"><b>Not recognised:</b> ${d.unmatched.map((u) => `<span class="mono">${esc(u)}</span>`).join(" · ")}</div>` : ""}`;
  const ask = $("#ask-live");
  if (ask) ask.onclick = () => startLookup(d.lookup_candidates);
  $("#sort").onclick = () => { state.sortByVerdict = !state.sortByVerdict; renderResults(d, req); };
  $("#print").onclick = () => window.print();
  $("#csv").onclick = () => copyCsv(sorted);
  out.querySelectorAll("article.fund [data-toggle]").forEach((b) => {
    const card = b.closest("article.fund");
    b.addEventListener("click", () => toggleCard(card, sorted[+card.dataset.i]));
  });
  out.querySelectorAll("[data-rid]").forEach((a) => a.addEventListener("click", openRecord));
  out.scrollIntoView({behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start"});
  announce(`${plural(d.rows.length, "fund", "funds")} checked. ${out.querySelector(".summary-big")?.textContent || ""}`);
}

function geminiNote(g) {
  if (!g) return "";
  if (g.error) return `<div class="unmatched"><b>Some lines were not recognised.</b> ${esc(g.error)}.</div>`;
  const notFound = g.funds.filter((f) => !g.matched.includes(f));
  return `<div class="ai-note"><span class="pill pill-ai">Read by Gemini</span> ${plural(g.lines, "line", "lines")} our parser could not match went to ${esc(g.model)} (${(g.ms / 1000).toFixed(1)} s). ${g.matched.length ? `Matched to our data: ${g.matched.map((f) => `<b>${esc(f)}</b>`).join(", ")}.` : "No fund names matched our data."}${notFound.length ? ` Not in our data: ${notFound.map(esc).join(", ")}.` : ""} Gemini only reads the list; every verdict is counted.</div>`;
}

function lookupPanel(names) {
  return `<div class="live card" id="live">
    <div class="live-head"><div><h3>Ask Cala directly about these funds</h3><p class="muted">Not in our snapshot, or only seen from the company side with too few rounds: ${names.map((n) => `<span class="mono">${esc(n)}</span>`).join(" · ")}. One live Cala query per fund, about a minute each.</p></div>
    <button class="btn btn-primary" type="button" id="ask-live">Ask Cala live about ${plural(names.length, "fund", "funds")}</button></div>
    <ol class="ledger hidden" id="ledger" role="status" aria-live="polite"></ol></div>`;
}

async function startLookup(names) {
  const btn = $("#ask-live");
  btn.disabled = true; btn.textContent = "Asking Cala";
  let job;
  try { job = await api("/api/lookup", {method: "POST", body: JSON.stringify({names})}); }
  catch (err) { btn.textContent = err.message; return; }
  const ledger = $("#ledger");
  ledger.classList.remove("hidden");
  const label = {queued: "queued", asking: "asking Cala /v1/knowledge/query", done: "rounds landed", empty: "Cala has no rounds for this fund", error: "Cala did not answer", budget: "live lookups used up"};
  const paint = (j) => {
    ledger.innerHTML = j.items.map((i) => `<li class="led-${esc(i.status)}"><span class="dot" aria-hidden="true"></span><b>${esc(i.name)}</b><span class="mono">${esc(label[i.status] || i.status)}${i.status === "done" ? ` · ${i.rows} rounds` : ""}${i.seconds != null ? ` · ${i.seconds} s` : ""}</span></li>`).join("");
  };
  paint(job);
  const t0 = Date.now();
  while (!job.done && Date.now() - t0 < 6 * 60 * 1000) {
    await new Promise((r) => setTimeout(r, 2500));
    try { job = await api(`/api/lookup/${encodeURIComponent(job.id)}`); paint(job); } catch { break; }
  }
  btn.textContent = "Done";
  if (job.items.some((i) => i.status === "done")) {
    const extra = job.items.filter((i) => i.status === "done").map((i) => i.name).join("\n");
    const box = $("#funds");
    if (!box.value.includes(extra)) box.value = box.value.trim() + "\n" + extra;
    lineCount();
    run();
  }
}

const sizeText = (s) => `EUR ${fmtM(s.lo)}${s.hi !== s.lo ? ` to ${fmtM(s.hi)}` : ""}m`;
const FIT_LABEL = {fits: "Fits your raise", larger: "Smaller than yours", smaller: "Larger than yours"};
const year = (date) => esc(String(date || "").split(" ").pop());

function introHtml(r) {
  if (r.tie) {
    const x = r.tie.round;
    return `<div class="intro intro-yes"><span class="intro-l">Intro path</span><span>Your investor <b>${esc(r.tie.investor)}</b> sat with them in <a href="#" data-rid="${x.id}">${esc(x.company)}</a>'s ${x.n_investors}-investor ${esc(String(x.stage).toLowerCase())} round, ${year(x.date)}.</span></div>`;
  }
  const msg = state.investors.length ? "No shared round found with your investors." : "Add your current investors to see intro paths.";
  return `<div class="intro"><span class="intro-l">Intro path</span><span class="muted">${msg}</span></div>`;
}

function cardHtml(r, i) {
  const led = r.conflicts.filter((c) => c.level === "led");
  const flags = [
    led.length ? `<span class="warn-flag"><span class="tri" aria-hidden="true"></span>Led a competitor</span>` : "",
    r.via === "gemini" ? `<span class="pill pill-ai">name read by Gemini</span>` : "",
  ].join("");
  const s1 = r.known
    ? `<div class="stat-v">Led ${r.led} <span class="of">of ${r.known}</span></div><div class="stat-s">new investments near your stage, ${r.led_at_stage} at your exact stage</div>`
    : `<div class="stat-v of">No data</div><div class="stat-s">No rounds with a named lead near your stage</div>`;
  const s2 = r.size
    ? `<div class="stat-v">${sizeText(r.size)}</div>${r.size.fit ? `<span class="fit fit-${r.size.fit}">${FIT_LABEL[r.size.fit] || ""}</span>` : `<div class="stat-s">from ${plural(r.size.n, "led round", "led rounds")}</div>`}`
    : `<div class="stat-v of">Not stated</div><div class="stat-s">No round sizes in the data</div>`;
  const s3 = r.last_lead
    ? `<div class="stat-v"><a href="#" data-rid="${r.last_lead.id}">${esc(r.last_lead.company)}</a></div><div class="stat-s">${esc(r.last_lead.stage)} · ${esc(r.last_lead.date)}</div>`
    : `<div class="stat-v of">Never</div><div class="stat-s">No led round in our data</div>`;
  const conf = r.conflicts.length
    ? `<div class="conflicts">${r.conflicts.slice(0, 2).map((c) => `<div class="conf conf-${c.level}"><span class="tri" aria-hidden="true"></span><span>${c.level === "led" ? "Led" : "Joined"} <a href="#" data-rid="${c.round.id}">${esc(c.competitor)}</a>'s ${esc(c.round.stage)} round, ${year(c.round.date)}</span></div>`).join("")}</div>`
    : "";
  return `<article class="fund" data-i="${i}" data-open="false" aria-labelledby="fn-${i}">
    <div class="fund-head">
      <div><h3 class="fund-name" id="fn-${i}">${esc(r.name)}</h3>${r.pasted !== r.name ? `<div class="fund-sub">${esc(r.pasted)}</div>` : ""}</div>
      <div class="fund-flags">${flags}</div>
    </div>
    <div class="verdict-big v-${esc(r.verdict)}"><span class="v-icon" aria-hidden="true"></span>${esc(r.verdict_label)}</div>
    <div class="stats">
      <div class="stat"><div class="stat-l">Lead record</div>${s1}</div>
      <div class="stat"><div class="stat-l">Round size it leads</div>${s2}</div>
      <div class="stat"><div class="stat-l">Last lead</div>${s3}</div>
    </div>
    ${introHtml(r)}
    ${conf}
    <div class="fund-foot">
      <button type="button" class="rounds-btn" data-toggle aria-expanded="false" aria-controls="det-${i}"><span class="chev" aria-hidden="true"></span><span>Show the record</span></button>
      <div class="prov-chips"><span class="pill pill-q" title="Rounds come from Cala /v1/knowledge/query">${r.queried ? "asked Cala about this fund" : "seen in company rounds"}</span></div>
    </div>
  </article>`;
}

function roundList(rounds, empty, limit = 6) {
  if (!rounds.length) return `<p class="none">${empty}</p>`;
  const li = (r) => `<li><span class="rl-name"><a href="#" data-rid="${r.id}">${esc(r.company)}</a>${r.sourced ? ` <span class="pill pill-src" title="Cala search found a source document for this round">sourced</span>` : ""}</span><span class="when">${esc(r.stage)} · ${esc(r.date)}${r.amount_eur_m ? ` · ${fmtM(r.amount_eur_m)}m` : ""}</span></li>`;
  const head = rounds.slice(0, limit).map(li).join("");
  const rest = rounds.slice(limit);
  return `<ul class="rlist">${head}</ul>${rest.length ? `<button type="button" class="more" data-more>Show ${rest.length} more</button><ul class="rlist hidden" data-rest>${rest.map(li).join("")}</ul>` : ""}`;
}

function toggleCard(card, r) {
  const btn = card.querySelector("[data-toggle]");
  const open = card.dataset.open === "true";
  const existing = card.querySelector(".detail-in");
  if (open) {
    card.dataset.open = "false"; btn.setAttribute("aria-expanded", "false"); btn.lastChild.textContent = "Show the record";
    existing?.remove(); return;
  }
  card.dataset.open = "true"; btn.setAttribute("aria-expanded", "true"); btn.lastChild.textContent = "Hide the record";
  const det = document.createElement("div");
  det.className = "detail-in";
  det.id = `det-${card.dataset.i}`;
  const counts = [
    r.unknown ? `${plural(r.unknown, "round", "rounds")} with no named lead` : "",
    r.follow_ons ? `${plural(r.follow_ons, "follow-on", "follow-ons")} in its own companies not counted` : "",
    `${r.total_rounds} rounds in total for this fund in our Cala data`,
  ].filter(Boolean).join(" · ");
  det.innerHTML = `
    <div><h3>Led <span class="faint">${r.rounds_led.length}</span></h3>${roundList(r.rounds_led, "No led rounds at this stage in the last four years.")}</div>
    <div><h3>Joined, did not lead <span class="faint">${r.rounds_joined.length}</span></h3>${roundList(r.rounds_joined, "None.")}</div>
    <div><h3>Lead not named <span class="faint">${r.rounds_unknown.length}</span></h3>${roundList(r.rounds_unknown, "None.")}</div>
    ${r.like_you?.length ? `<div class="detail-note"><span class="pill pill-q">like yours</span><span>Led <b>${r.like_you.length}</b> ${r.like_you.length === 1 ? "round" : "rounds"} like yours: ${r.like_you.slice(0, 5).map((x) => `<a href="#" data-rid="${x.id}">${esc(x.company)}</a>`).join(", ")}${r.like_you.length > 5 ? " and more" : ""}</span></div>` : ""}
    ${r.tie ? `<div class="detail-note"><span class="pill">tie</span><span>Your investor <b>${esc(r.tie.investor)}</b> and ${esc(r.name)} were both in <a href="#" data-rid="${r.tie.round.id}">${esc(r.tie.round.company)}</a> (${esc(r.tie.round.stage)}, ${esc(r.tie.round.date)}, ${r.tie.round.n_investors} investors). Fund-level tie: ask your investor which partner was on that deal.</span></div>` : ""}
    <div class="detail-note">Window: last four years, your stage and the stages next to it. ${esc(counts)}.</div>`;
  card.querySelector(".fund-foot").after(det);
  det.querySelectorAll("[data-rid]").forEach((a) => a.addEventListener("click", openRecord));
  det.querySelectorAll("[data-more]").forEach((b) => b.addEventListener("click", () => { b.nextElementSibling.classList.remove("hidden"); b.remove(); }));
}

function copyCsv(rows) {
  const q = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  const lines = [["Fund", "Verdict", "Led", "Known rounds", "Lead unknown", "Size it leads (EUR m)", "Last lead", "Conflict"].map(q).join(",")];
  rows.forEach((r) => lines.push([r.name, r.verdict_label, r.led, r.known, r.unknown,
    r.size ? `${fmtM(r.size.lo)}-${fmtM(r.size.hi)}` : "", r.last_lead ? `${r.last_lead.company} ${r.last_lead.date}` : "",
    r.conflicts.map((c) => `${c.level} ${c.competitor}`).join("; ")].map(q).join(",")));
  navigator.clipboard?.writeText(lines.join("\n")).then(() => { $("#csv").textContent = "Copied"; setTimeout(() => ($("#csv").textContent = "Copy as CSV"), 1500); });
}

/* ---------------- record sheet ---------------- */
async function openRecord(e) {
  e.preventDefault();
  const rid = e.currentTarget.dataset.rid;
  const root = $("#sheet-root");
  const prev = document.activeElement;
  root.innerHTML = `<div class="sheet-backdrop" data-close></div><aside class="sheet" role="dialog" aria-modal="true" aria-labelledby="sheet-h"><header><div><div class="eyebrow">Cala round record</div><h2 id="sheet-h">Loading</h2></div><button class="x" data-close aria-label="Close">×</button></header><div class="body"><div class="skel"></div></div></aside>`;
  const bg = [...document.querySelectorAll("body > header, body > main, body > footer")];
  bg.forEach((el) => el.setAttribute("inert", ""));
  document.body.classList.add("no-scroll");
  const close = () => {
    root.innerHTML = ""; document.removeEventListener("keydown", onKey);
    bg.forEach((el) => el.removeAttribute("inert")); document.body.classList.remove("no-scroll"); prev?.focus();
  };
  const onKey = (ev) => {
    if (ev.key === "Escape") return close();
    if (ev.key === "Tab") {
      const f = [...root.querySelectorAll("button, a[href], summary, [tabindex='0']")].filter((x) => x.offsetParent !== null);
      if (!f.length) return;
      const first = f[0], last = f[f.length - 1];
      if (ev.shiftKey && document.activeElement === first) { ev.preventDefault(); last.focus(); }
      else if (!ev.shiftKey && document.activeElement === last) { ev.preventDefault(); first.focus(); }
    }
  };
  document.addEventListener("keydown", onKey);
  root.querySelectorAll("[data-close]").forEach((x) => x.addEventListener("click", close));
  $(".sheet .x").focus();
  try {
    const r = await api(`/api/record/${encodeURIComponent(rid)}`);
    $("#sheet-h").textContent = `${r.company} · ${r.stage}`;
    $(".sheet .body").innerHTML = `
      <dl class="kv">
        <dt>Date</dt><dd>${esc(r.date)}</dd>
        <dt>Round</dt><dd>${esc(r.type || r.stage)}</dd>
        <dt>Amount</dt><dd class="num">${r.amount_raw ? esc(r.amount_raw) : "not stated"}${r.amount_eur_m ? ` <span class="faint">≈ EUR ${fmtM(r.amount_eur_m)}m</span>` : ""}</dd>
        <dt>Lead</dt><dd>${r.leads.length ? r.leads.map(esc).join(", ") : `<span class="none">not named</span>`}</dd>
        <dt>Participants</dt><dd>${r.participants.length ? r.participants.map(esc).join(", ") : `<span class="none">none named</span>`}</dd>
        <dt>Cala entities</dt><dd>${entityHtml(r)}</dd>
        <dt>Found via</dt><dd>${r.path === "both" ? "Both query paths agree on this round" : r.path === "investor_first" ? "Investor-first query" : "Company-first query"}</dd>
      </dl>
      <h3>Source documents</h3>
      <div id="src-box">${sourceHtml(r.source)}</div>
      <h3>Cala entity graph</h3>
      <div id="graph-box">${graphHtml(r.graph)}</div>
      <h3>Provenance</h3>
      ${r.sources.map((s) => `<div class="prov"><span class="pill pill-q">POST /v1/knowledge/query</span> <span class="pill">${esc(s.path.replace("_", "-"))}</span><div class="q">"${esc(s.query)}"</div><details class="raw"><summary>Raw Cala row</summary><pre>${esc(JSON.stringify(s.row, null, 2))}</pre></details></div>`).join("")}
      <p class="faint">${esc(APP())} only counts and merges these Cala rows. Source documents come from Cala's /v1/knowledge/search.</p>`;
    const askG = $("#ask-graph");
    if (askG) askG.onclick = async () => {
      askG.disabled = true; askG.textContent = "Asking Cala /v1/entities";
      try { const g = await api(`/api/graph/${encodeURIComponent(rid)}`, {method: "POST", body: "{}"}); $("#graph-box").innerHTML = graphHtml(g, true); }
      catch (err) { askG.disabled = false; askG.textContent = err.message; }
    };
    const ask = $("#ask-src");
    if (ask) ask.onclick = async () => {
      ask.disabled = true; ask.textContent = "Asking Cala /v1/knowledge/search";
      try { const src = await api(`/api/source/${encodeURIComponent(rid)}`, {method: "POST", body: "{}"}); $("#src-box").innerHTML = sourceHtml(src, true); }
      catch (err) { ask.disabled = false; ask.textContent = err.message; }
    };
  } catch (err) {
    if (err.message !== "auth") $(".sheet .body").innerHTML = `<p role="alert">Could not load this record: ${esc(err.message)}</p>`;
  }
}

function entityHtml(r) {
  const e = r.entity_ids || {};
  const one = (name, id) => `<span class="ent">${esc(name)} <code title="${esc(id || "")}">${id ? esc(id.slice(0, 8)) : "no id"}</code></span>`;
  const parts = [one(r.company, e.company), ...(e.leads || []).map((l) => one(l.name, l.id))];
  return parts.join(" ");
}

const GRAPH_VERDICT = {
  agrees: ["g-ok", "The graph marks the same lead"],
  differs: ["g-diff", "The graph marks a different lead"],
  graph_no_lead: ["g-none", "The graph has this round but marks no lead"],
};

function graphHtml(g, fresh) {
  if (!g) return `<p class="muted">Not checked against Cala's entity graph yet.</p><button class="btn" type="button" id="ask-graph">Check in Cala's entity graph</button> <span class="faint">2 to 4 entity calls, a few seconds</span>`;
  const pill = `<span class="pill pill-q">POST /v1/entities/{id}</span>${fresh ? ` <span class="pill">just now</span>` : ""}`;
  if (g.status === "no_rounds_in_graph") return `<div class="graph">${pill}<p class="muted">Cala's entity graph has no funding round entities for this company yet. The round above comes from Cala's query layer.</p></div>`;
  if (g.status === "round_not_in_graph") return `<div class="graph">${pill}<p class="muted">The graph has ${esc((g.graph_rounds || []).join(", ") || "other rounds")} for this company, but not this stage.</p></div>`;
  const x = g.round || {};
  if (g.agreement === "not_in_graph") return `<div class="graph">${pill}<p class="muted">The graph's ${esc(x.label || "")} round is dated ${esc(x.announced || x.event_date || "")}, more than a year from this one, so it is a different round.</p></div>`;
  const [cls, text] = GRAPH_VERDICT[g.agreement] || ["g-none", ""];
  const amount = x.amount ? `${esc(x.currency || "")} ${fmtM(x.amount / 1e6)}m` : "amount not stated";
  const srcs = (x.sources || []).filter((d) => /^https:\/\//.test(d.url));
  return `<div class="graph">${pill}
    <p class="g-verdict ${cls}">${esc(text)}</p>
    <dl class="kv">
      <dt>Round entity</dt><dd>${esc(x.label || "")} <code title="${esc(x.round_id || "")}">${esc((x.round_id || "").slice(0, 8))}</code></dd>
      <dt>Announced</dt><dd>${esc(x.announced || x.event_date || "not stated")} · ${amount}</dd>
      <dt>is_lead</dt><dd>${x.leads?.length ? x.leads.map((l) => esc(l.name)).join(", ") : `<span class="none">none marked</span>`} <span class="faint">of ${x.n_investors || 0} participants</span></dd>
    </dl>
    ${srcs.length ? `<ol class="src-docs">${srcs.map((d) => `<li><a href="${esc(d.url)}" target="_blank" rel="noopener noreferrer">${esc(d.name)}</a> <span class="pill">${esc(d.rank || "")}</span>${d.date ? `<span class="faint"> · ${esc(d.date)}</span>` : ""}</li>`).join("")}</ol>` : ""}
  </div>`;
}

function sourceHtml(src, fresh) {
  if (!src) return `<p class="muted">No source document cached for this round yet.</p><button class="btn" type="button" id="ask-src">Ask Cala for a source</button> <span class="faint">one live Cala search, about 30 seconds</span>`;
  const docs = (src.docs || []).filter((d) => /^https:\/\//.test(d.url));
  return `<div class="src">
    <div class="src-answer"><span class="pill pill-q">POST /v1/knowledge/search</span>${fresh ? ` <span class="pill">just now</span>` : ""}<p>${esc(String(src.answer || "").replace(/^#+\s*/gm, "").replace(/\*\*/g, ""))}</p></div>
    ${docs.length ? `<ol class="src-docs">${docs.map((d) => `<li><a href="${esc(d.url)}" target="_blank" rel="noopener noreferrer">${esc(d.name)}</a><span class="faint"> · ${esc(d.site || new URL(d.url).hostname)}</span>${d.passage ? `<blockquote>${esc(d.passage.slice(0, 260))}${d.passage.length > 260 ? "…" : ""}</blockquote>` : ""}</li>`).join("")}</ol>` : `<p class="muted">Cala answered without a linked document.</p>`}
  </div>`;
}

/* ---------------- method ---------------- */
function renderMethod() {
  const m = state.meta || {};
  const v = m.validation;
  $("#view-method").innerHTML = `
  <section class="wrap method-hero"><h1>Method <span class="h1-soft">and limits.</span></h1><p class="lede">How ${esc(APP())} turns Cala round records into a verdict per fund, what we tested, and where it can be wrong.</p></section>
  <div class="wrap method">
    <div>
      <section class="card ai-box"><h2>Where AI is used, and where it is not</h2>
        <p>Verdicts, counts, ties and conflicts are plain counting over Cala round records. The same input always gives the same table, and every number opens the rounds behind it. No language model ranks or judges a fund.</p>
        <p>Cala answers our questions about funds and companies. ${esc(APP())} stores those answers in Postgres, merges rounds seen from both sides, and counts. Where Cala's entity graph has the round, the record sheet shows which investor the graph marks as lead, with its ranked sources, so you can see both layers side by side.</p>
      </section>
      <section class="card"><h2>Verdict rules</h2>
        <p class="muted">Counted over the last four years, at your stage and the stages next to it. A round counts as "known" when Cala names its lead.</p>
        <ul class="rules">
          <li><span class="verdict v-leads"><span class="v-icon"></span>Leads rounds like yours</span><span>Led 2 or more rounds at your stage, and led at least 30% of its new investments where Cala names the lead (follow-on rounds in its own portfolio companies are not counted), and your target raise sits inside the range of rounds it led (the middle half of its led round sizes, from 0.8x the low end to 1.25x the high end).</span></li>
          <li><span class="verdict v-leads_size"><span class="v-icon"></span>Leads, but larger or smaller rounds</span><span>Leads at your stage, but your target is outside that size range. Sizes come from its leads at your exact stage when there are at least 2, otherwise from the stages next to it (the row says which).</span></li>
          <li><span class="verdict v-follows"><span class="v-icon"></span>Mostly follows</span><span>5 or more new investments with a named lead, and led fewer than 15% of them.</span></li>
          <li><span class="verdict v-stale"><span class="v-icon"></span>No lead since …</span><span>Has led before, but not in the last 24 months.</span></li>
          <li><span class="verdict v-mixed"><span class="v-icon"></span>Mixed</span><span>Everything in between.</span></li>
          <li><span class="verdict v-few"><span class="v-icon"></span>Too few rounds</span><span>Fewer than 3 known rounds in the window. We show the rounds, not a verdict.</span></li>
          <li><span class="verdict v-public"><span class="v-icon"></span>Public body or programme</span><span>Grant bodies, public funds and accelerators. Shown, never judged as a lead.</span></li>
        </ul>
      </section>
      <section class="card"><h2>What we tested</h2>
        ${v ? `<table class="simple"><thead><tr><th>Test</th><th>Result</th><th>n</th></tr></thead><tbody>${v.rows.map((r) => `<tr><td>${esc(r.test)}</td><td>${esc(r.result)}</td><td class="num">${esc(r.n)}</td></tr>`).join("")}</tbody></table><p class="muted">${esc(v.note || "")}</p>` : `<p class="muted">Validation numbers are being recomputed on the full data.</p>`}
        ${v?.accuracy?.length ? `<details class="raw"><summary>Every hand check, with its source (${v.accuracy.length})</summary><table class="simple"><thead><tr><th>Round</th><th>Lead in Cala</th><th>Check</th></tr></thead><tbody>${v.accuracy.map((a) => `<tr><td>${esc(a.company)} <span class="faint mono">${esc(a.date)} ${esc(a.stage || "")}</span></td><td>${esc((a.cala_leads || []).join(", "))}</td><td>${esc(a.verdict)}${a.source_url && /^https:\/\//.test(a.source_url) ? ` · <a href="${esc(a.source_url)}" target="_blank" rel="noopener noreferrer">source</a>` : ""}</td></tr>`).join("")}</tbody></table></details>` : ""}
        <p class="muted"><a href="/static/cala-data-quality.json" download>Data-quality findings we prepared for Cala</a> (JSON).</p>
      </section>
      <section class="card"><h2>Limits</h2>
        <ul>
          <li>Fund level, not partner level. A tie means two funds sat in the same round; ask which partner was on it.</li>
          <li>About a third of seed rounds in our data name no lead. Those rounds are left out of the lead ratio, so thinly covered funds show "Too few rounds"; every row shows how many rounds had no named lead.</li>
          <li>Coverage is what Cala returned to our queries: European venture rounds, mostly 2021 to 2026. A fund missing here is missing from our snapshot, not necessarily from Cala.</li>
          <li>Company discovery started from startups that raised over EUR 2m, so very small rounds are under-represented.</li>
          <li>Two query paths can label the same round differently. The record view shows both rows when that happens.</li>
        </ul>
      </section>
    </div>
    <aside>
      <section class="card"><h2>Coverage</h2>
        <dl class="kv">
          <dt>Funds asked</dt><dd class="num">${esc(m.funds_queried ?? "")}</dd>
          <dt>Companies</dt><dd class="num">${esc(m.companies ?? "")}</dd>
          <dt>Rounds</dt><dd class="num">${esc(m.rounds ?? "")}</dd>
          <dt>Investors</dt><dd class="num">${esc(m.investors ?? "")}</dd>
          <dt>Retrieved</dt><dd class="num">${esc(m.retrieved ?? "")}</dd>
        </dl>
        <p class="muted">Endpoints:</p>
        <ul class="muted endpoints">
          <li><span class="pill pill-q">/v1/knowledge/query</span> round data, asked investor-first and company-first</li>
          <li><span class="pill pill-q">/v1/knowledge/search</span> source documents for a round</li>
          <li><span class="pill pill-q">/v1/entities</span> entity IDs, and the cross-check against Cala's FundingRound graph (is_lead)</li>
        </ul>
      </section>
      <section class="card"><h2>Stack</h2>
        <p class="muted">Cala for the data. Aiven Postgres stores the snapshot, the normalised rounds and every live Cala answer. Modal serves this app and runs the live Cala lookups. Gemini only reads pasted lines our parser cannot match.</p>
      </section>
    </aside>
  </div>`;
}

/* ---------------- boot ---------------- */
document.addEventListener("DOMContentLoaded", () => {
  setupChips("investors"); setupChips("competitors");
  $("#funds").addEventListener("input", lineCount);
  $("#sample").addEventListener("click", () => {
    $("#funds").value = SAMPLE; lineCount();
    if (!state.investors.length) { state.investors.push("Lifeline Ventures"); state.lead = "Lifeline Ventures"; renderChips("investors"); }
    if (!state.competitors.length) { state.competitors.push("Lovable"); renderChips("competitors"); }
    if (!$("#target").value) $("#target").value = "3";
    run();
  });
  $("#check-form").addEventListener("submit", (e) => { e.preventDefault(); run(); });
  $("#find").addEventListener("click", runFind);
  const tabs = [$("#tab-list"), $("#tab-find")];
  const select = (tab) => {
    tabs.forEach((x) => { x.setAttribute("aria-selected", x === tab); x.tabIndex = x === tab ? 0 : -1; });
    $("#pane-list").classList.toggle("hidden", tab.id !== "tab-list");
    $("#pane-find").classList.toggle("hidden", tab.id !== "tab-find");
  };
  select(tabs[0]);
  tabs.forEach((tab, i) => {
    tab.addEventListener("click", () => select(tab));
    tab.addEventListener("keydown", (e) => {
      const k = {ArrowRight: 1, ArrowLeft: -1}[e.key];
      if (k) { e.preventDefault(); const t = tabs[(i + k + tabs.length) % tabs.length]; select(t); t.focus(); }
      if (e.key === "Home" || e.key === "End") { e.preventDefault(); const t = tabs[e.key === "Home" ? 0 : tabs.length - 1]; select(t); t.focus(); }
    });
  });
  document.addEventListener("keydown", (e) => { if ((e.metaKey || e.ctrlKey) && e.key === "Enter") (activeTab() === "find" ? runFind : run)(); });
  init().then(() => { if (location.hash === "#demo") $("#sample").click(); });
});
