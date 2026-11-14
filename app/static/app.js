"use strict";
/* Front end. The product name comes from brand.js (window.APP_NAME). Plain JS, no build step.
   Everything rendered from API data or from a file the founder picks goes through esc(). */

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const fmtM = (m) => m == null ? "" : (m >= 100 ? String(Math.round(m)) : m >= 10 ? m.toFixed(0) : m.toFixed(1).replace(/\.0$/, ""));
const plural = (n, a, b) => `${n} ${n === 1 ? a : b}`;
const APP = () => window.APP_NAME || "";
const reduceMotion = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

const state = {stage: "seed", investors: [], lead: null, competitors: [], meta: null, mode: "list",
  view: null, req: null, ranked: [], network: null, openIdx: null};

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

/* Made-up people. The companies are real portfolio companies of the sample funds in the Cala snapshot,
   so the demo shows real matches. Names are invented and roles are kept neutral (no founder or CEO titles),
   so nothing here reads as a claim about who runs a real company. */
const SAMPLE_NETWORK = `Notes:
"Made-up sample network for the demo. These people do not exist."

First Name,Last Name,URL,Email Address,Company,Position,Connected On
Demo Contact,B,,,Aventix,Product Designer,18 Jun 2024
Demo Contact,C,,,KineDB,Software Engineer,02 Feb 2026
Demo Contact,D,,,TesterArmy,Software Engineer,11 Sep 2025
Demo Contact,E,,,Causa Prima,Sales,29 Jan 2026
Demo Contact,F,,,Marble Cognition,Product Designer,07 Oct 2025
Demo Contact,G,,,Metaktik,Operations,21 Apr 2026
Demo Contact,H,,,Self-employed,Advisor,15 May 2023
Demo Contact,I,,,Northwind Example Oy,Engineer,30 Aug 2022
Demo Contact,J,,,Demo Bakery,Owner,12 Dec 2021`;

async function api(path, opts = {}) {
  const res = await fetch(path, {headers: {"Content-Type": "application/json"}, ...opts});
  if (res.status === 401) { location.href = "/login"; throw new Error("auth"); }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const d = body.detail;
    const err = new Error(Array.isArray(d) ? d.map((e) => e.msg).join("; ") : d || body.error || `Request failed (${res.status})`);
    err.status = res.status;
    throw err;
  }
  return body;
}

function announce(msg) { const st = $("#status"); st.textContent = ""; setTimeout(() => { st.textContent = msg; }, 50); }
/* Only the visible screen animates: the first-run strip on paste, the map's sweep on results. */
function setScreen(s) {
  const was = document.body.dataset.screen;
  document.body.dataset.screen = s;
  hideTip();
  if (s !== "results") stopMap();
  else if (was !== "results" && state.resultView === "map" && MAP?.wrap.isConnected) ambient(0);
  if (s === "paste" && was !== "paste") runProof();
}

/* ---------------- routing ---------------- */
function route() {
  const isMethod = location.pathname === "/method";
  $("#view-check").classList.toggle("hidden", isMethod);
  $("#view-method").classList.toggle("hidden", !isMethod);
  $("#nav-check").toggleAttribute("aria-current", !isMethod && state.mode === "list");
  $("#nav-find").toggleAttribute("aria-current", !isMethod && state.mode === "find");
  $("#nav-method").toggleAttribute("aria-current", isMethod);
  ["#nav-check", "#nav-find", "#nav-method"].forEach((id) => { if ($(id).hasAttribute("aria-current")) $(id).setAttribute("aria-current", "page"); });
  if (isMethod) { renderMethod(); stopMap(); hideTip(); if ($("#tour-root").firstChild) tourClose("done"); }
}
function go(path) { if (location.pathname !== path) history.pushState({}, "", path); route(); window.scrollTo(0, 0); }
document.addEventListener("click", (e) => {
  const a = e.target.closest("a[href='/'], a[href='/method']");
  if (!a || e.metaKey || e.ctrlKey || e.shiftKey) return;
  e.preventDefault();
  if (a.getAttribute("href") === "/") { setMode("list"); setScreen("paste"); }
  go(a.getAttribute("href"));
});
window.addEventListener("popstate", route);

/* ---------------- form ---------------- */
async function init() {
  try {
    state.meta = await api("/api/meta");
    const m = state.meta;
    $("#data-chip").innerHTML = `${m.rounds.toLocaleString("en")} funding rounds from Cala, ${m.companies.toLocaleString("en")} companies, retrieved ${esc(m.retrieved)}. <a href="/method">How we count</a>`;
    $("#side-stats").innerHTML = `${m.rounds.toLocaleString("en")} rounds, ${m.funds_queried} funds<br>Retrieved ${esc(m.retrieved)}`;
    const seg = $("#stage-seg");
    seg.innerHTML = m.stages.slice(0, 6).map((s) => `<button type="button" data-stage="${esc(s.key)}" aria-pressed="${s.key === state.stage}">${esc(s.label)}</button>`).join("");
    seg.addEventListener("click", (e) => {
      const b = e.target.closest("button[data-stage]"); if (!b) return;
      setStage(b.dataset.stage);
    });
  } catch (err) {
    if (err.message !== "auth") $("#data-chip").textContent = "Could not load the data. Reload the page.";
  }
  route();
}
function setStage(key) {
  state.stage = key;
  $$("#stage-seg button").forEach((x) => x.setAttribute("aria-pressed", x.dataset.stage === key));
}

function setMode(mode) {
  state.mode = mode;
  const find = mode === "find";
  $("#mode-list").classList.toggle("hidden", find);
  $("#mode-find").classList.toggle("hidden", !find);
  $("#sample").classList.toggle("hidden", find);
  $("#go").textContent = find ? "Find funds" : "Check funds";
  $("#to-find").textContent = find ? "Have a list? Check it instead" : "No list yet? Find funds for me";
  route();
}

function renderChips(kind) {
  const box = kind === "investors" ? $("#inv-chips") : $("#comp-chips");
  $$(".tag", box).forEach((t) => t.remove());
  const input = box.querySelector("input");
  const items = kind === "investors" ? state.investors : state.competitors;
  items.forEach((name, i) => {
    const tag = document.createElement("span");
    const isLead = kind === "investors" && state.lead === name;
    tag.className = "tag" + (isLead ? " is-lead" : "");
    tag.innerHTML = `${esc(name)}${kind === "investors" ? `<button type="button" class="lead-toggle" data-lead="${i}" aria-pressed="${isLead}" aria-label="${esc(name)} is your current lead">${isLead ? "your lead" : "mark lead"}</button>` : ""}<button type="button" data-rm="${i}" aria-label="Remove ${esc(name)}">×</button>`;
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
    name = name.trim().slice(0, 120);
    if (!name || list.length >= max || list.some((x) => x.toLowerCase() === name.toLowerCase())) return;
    list.push(name);
    if (kind === "investors" && list.length === 1 && !state.lead) state.lead = name;
    input.value = ""; hide(); renderChips(kind);
  };
  const hide = () => { if (kind === "investors") { sug.classList.add("hidden"); input.setAttribute("aria-expanded", "false"); input.removeAttribute("aria-activedescendant"); } active = -1; };
  const show = (rows) => {
    items = rows;
    if (!rows.length) return hide();
    sug.innerHTML = rows.map((r, i) => `<button type="button" tabindex="-1" role="option" id="opt-${i}" data-i="${i}" aria-selected="${i === active}"><span>${esc(r.name)}</span><span>${plural(r.rounds, "round", "rounds")}</span></button>`).join("");
    sug.classList.remove("hidden"); input.setAttribute("aria-expanded", "true");
    if (active >= 0) input.setAttribute("aria-activedescendant", `opt-${active}`); else input.removeAttribute("aria-activedescendant");
  };

  box.addEventListener("click", (e) => {
    const rm = e.target.closest("[data-rm]");
    if (rm) { const name = list[+rm.dataset.rm]; list.splice(+rm.dataset.rm, 1); if (state.lead === name) state.lead = null; renderChips(kind); input.focus(); return; }
    const ld = e.target.closest("[data-lead]");
    if (ld) { const name = list[+ld.dataset.lead]; state.lead = state.lead === name ? null : name; renderChips(kind); return; }
    const opt = e.target.closest("[data-i]");
    if (opt) { add(items[+opt.dataset.i].name); input.focus(); return; }
    if (e.target === box) input.focus();
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

function lineCount() {
  const n = $("#funds").value.split(/\n|;/).filter((l) => l.trim().length > 1).length;
  $("#line-count").textContent = n ? `${plural(n, "line", "lines")}. Times, tables and notes are ignored.` : "Any format works. Times, tables and notes are ignored.";
}
const TARGET_MAX = 5000;
const targetValue = () => { const t = parseFloat(($("#target").value || "").replace(",", ".")); return isFinite(t) && t > 0 ? t : null; };
/* Shows an inline hint and returns false when the target raise is out of range. */
function targetOk() {
  const t = targetValue(), bad = t != null && t > TARGET_MAX;
  $("#target-err").textContent = bad ? `Enter EUR ${TARGET_MAX} million or less.` : "";
  $("#target").setAttribute("aria-invalid", String(bad));
  if (bad) $("#target").focus();
  return !bad;
}

/* ---------------- LinkedIn network (read in the browser, never uploaded) ---------------- */
/* Same rule as merge.company_key on the server, so a connection's company and a portfolio company meet on one key. */
function companyKey(name) {
  let s = String(name ?? "").toLowerCase().replace(/\(.*?\)/g, "");
  s = s.replace(/(?<![\p{L}\p{N}\p{M}_])(oy|ab|as|gmbh|ltd|inc|sa|bv|aps|oyj|plc)(?![\p{L}\p{N}\p{M}_])/gu, "");
  return s.replace(/[^a-z0-9]/g, "");
}
/* Company names that are too generic to say two people work at the same place. */
const STOP_KEYS = new Set(["selfemployed", "freelance", "freelancer", "stealth", "stealthstartup", "stealthmode", "confidential",
  "independent", "consultant", "consulting", "none", "retired", "student", "various", "unemployed", "private", "startup",
  "ever", "garage", "home", "studio", "labs", "group", "capital", "ventures", "partners", "digital", "media", "solutions",
  "technologies", "global", "international", "company", "business", "university",
  "junction"]);  // Junction Oy runs the hackathon: nearly every visitor this week is connected to it
const usableKey = (k) => k.length >= 4 && !STOP_KEYS.has(k);

/* Founder level only when a title part STARTS with a founder role: "Co-founder & CEO" yes,
   "Executive Assistant to the CEO" and "Channel Partner Manager" no. */
const FOUNDER_START = /^(?:co-?\s?founder|founder|founding partner|ceo|cto|chief (?:executive|technology) officer|managing director|(?:general|managing) partner|partner$)/i;
const NOT_FOUNDER = /\b(assistant|associate|office of|to the|chief of staff|intern)\b/i;
function isFounderLevel(position) {
  return String(position || "").split(/\s*(?:[,|/&·]|\band\b|\bat\b|@)\s*/i)
    .some((seg) => seg && !NOT_FOUNDER.test(seg) && FOUNDER_START.test(seg.trim()));
}

function parseCsv(text) {
  const rows = []; let row = [], f = "", q = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (q) {
      if (c === '"') { if (text[i + 1] === '"') { f += '"'; i++; } else q = false; } else f += c;
    } else if (c === '"' && f === "") q = true;
    else if (c === ",") { row.push(f); f = ""; }
    else if (c === "\n" || c === "\r") { if (c === "\r" && text[i + 1] === "\n") i++; row.push(f); rows.push(row); row = []; f = ""; }
    else f += c;
  }
  if (f || row.length) { row.push(f); rows.push(row); }
  return rows;
}

/* Keeps first name, last name, company and position only. URL and email columns are never read. */
function parseConnections(text) {
  const rows = parseCsv(String(text).replace(/^﻿/, ""));
  const h = rows.findIndex((r) => (r[0] || "").trim().toLowerCase() === "first name");
  if (h < 0) return null;
  const head = rows[h].map((x) => x.trim().toLowerCase());
  const col = (name) => head.indexOf(name);
  const [cF, cL, cC, cP] = [col("first name"), col("last name"), col("company"), col("position")];
  if (cC < 0) return null;
  const clip = (v) => String(v || "").trim().slice(0, 120);
  return rows.slice(h + 1).filter((r) => r.length > 1 && (r[cC] || "").trim()).map((r) => {
    const company = clip(r[cC]), position = clip(cP >= 0 ? r[cP] : "");
    return {first: clip(cF >= 0 ? r[cF] : ""), last: clip(cL >= 0 ? r[cL] : ""), company, position,
      ckey: companyKey(company), founder: isFounderLevel(position)};
  });
}

function setNetwork(people, label, sample) {
  const byKey = new Map();
  people.forEach((p) => { if (!usableKey(p.ckey)) return; if (!byKey.has(p.ckey)) byKey.set(p.ckey, []); byKey.get(p.ckey).push(p); });
  state.network = {people, byKey, label, sample};
  paintNetStatus();
  rerenderKeepFocus();
}
function clearNetwork() { state.network = null; paintNetStatus(); rerenderKeepFocus(); }

/* Re-rendering the results removes the control that had focus; put focus on the new network bar instead of <body>. */
function rerenderKeepFocus() {
  if (!state.view) return;
  const wasInResults = $("#results").contains(document.activeElement);
  renderResults();
  if (wasInResults) ($("#netbar [data-net-clear]") || $("#li-file-2"))?.focus();
}

function paintNetStatus(msg, isErr) {
  const st = $("#net-status");
  st.classList.toggle("err", !!isErr);
  if (msg) { st.textContent = msg; return; }
  const n = state.network;
  st.innerHTML = n ? `${n.sample ? "Made-up sample network loaded" : `Read ${esc(n.label)}`}: ${plural(n.people.length, "connection", "connections")}. <button type="button" class="linkbtn" data-net-clear>Remove</button>` : "";
}

/* Reads Connections.csv out of a LinkedIn archive .zip, in the browser. Only the central directory and that one
   entry are read; deflate goes through the browser's own DecompressionStream, so no library and nothing inline. */
async function csvFromZip(file) {
  const buf = new Uint8Array(await file.arrayBuffer());
  const dv = new DataView(buf.buffer, buf.byteOffset, buf.byteLength);
  let end = -1;
  for (let i = buf.length - 22; i >= Math.max(0, buf.length - 22 - 65535); i--) {
    if (dv.getUint32(i, true) === 0x06054b50) { end = i; break; }
  }
  if (end < 0) throw new Error("not a zip");
  const count = dv.getUint16(end + 10, true);
  let p = dv.getUint32(end + 16, true);
  const dec = new TextDecoder();
  for (let n = 0; n < count && p + 46 <= buf.length; n++) {
    if (dv.getUint32(p, true) !== 0x02014b50) break;
    const method = dv.getUint16(p + 10, true), size = dv.getUint32(p + 20, true);
    const nameLen = dv.getUint16(p + 28, true), extraLen = dv.getUint16(p + 30, true), noteLen = dv.getUint16(p + 32, true);
    const at = dv.getUint32(p + 42, true);
    const name = dec.decode(buf.subarray(p + 46, p + 46 + nameLen));
    if (/(^|\/)connections\.csv$/i.test(name)) {
      const start = at + 30 + dv.getUint16(at + 26, true) + dv.getUint16(at + 28, true);
      const data = buf.subarray(start, start + size);
      if (method === 0) return dec.decode(data);
      if (method === 8 && typeof DecompressionStream === "function") {
        return new Response(new Blob([data]).stream().pipeThrough(new DecompressionStream("deflate-raw"))).text();
      }
      throw new Error("unsupported zip");
    }
    p += 46 + nameLen + extraLen + noteLen;
  }
  return null;
}

async function readNetworkFile(file) {
  if (!file) return;
  const isZip = /\.zip$/i.test(file.name) || /zip/.test(file.type);
  if (!isZip && !/\.csv$/i.test(file.name) && file.type !== "text/csv") return paintNetStatus("Choose Connections.csv or the .zip from your LinkedIn export.", true);
  if (file.size > (isZip ? 80 : 8) * 1024 * 1024) return paintNetStatus("That file is too large for a connections export.", true);
  try {
    const text = isZip ? await csvFromZip(file) : await file.text();
    if (isZip && text == null) return paintNetStatus("No Connections.csv in that .zip. Ask LinkedIn for the Connections archive.", true);
    const people = parseConnections(text);
    if (!people || !people.length) return paintNetStatus("No connections found. Use Connections.csv from the LinkedIn export.", true);
    setNetwork(people, file.name, false);
    announce(`${plural(people.length, "connection", "connections")} read in your browser.`);
  } catch {
    paintNetStatus("Could not read that file.", true);
  }
}

function setupDrop(el) {
  el.addEventListener("dragover", (e) => { e.preventDefault(); el.classList.add("over"); });
  el.addEventListener("dragleave", () => el.classList.remove("over"));
  el.addEventListener("drop", (e) => { e.preventDefault(); el.classList.remove("over"); readNetworkFile(e.dataTransfer?.files?.[0]); });
}

/* ---------------- ranking ---------------- */
const GROUPS = ["pitch", "size", "few", "avoid"];
const GROUP_NAME = {pitch: "Pitch first", size: "Leads, but a different size", few: "Too little data to tell", avoid: "Mostly follows or sometimes leads"};
const groupOf = (r) => (r.verdict === "leads" ? "pitch" : r.verdict === "leads_size" ? "size" : r.verdict === "few" ? "few" : "avoid");

/* Way-in strengths: founder at a company it led 5, anyone there 4, anyone at a company it joined 3,
   your investor in a small round with it 2, a same-name match on a short or ordinary-word company 1. */
function networkMatches(r) {
  const net = state.network;
  if (!net) return [];
  const out = [];
  for (const p of r.portfolio || []) {
    for (const person of net.byKey.get(p.ckey) || []) {
      out.push({person, round: p, weak: !!p.weak, strength: p.weak ? 1 : p.led ? (person.founder ? 5 : 4) : 3});
    }
  }
  return out.sort((a, b) => b.strength - a.strength || b.round.t - a.round.t);
}

const shortFund = (name) => String(name).replace(/\s+(ventures|venture capital|capital|partners|vc|fund|invest)$/i, "");

function wayIn(r) {
  const m = networkMatches(r);
  const best = m[0];
  if (best && best.strength > 1) {
    return {strength: best.strength, matches: m,
      text: best.strength === 5 ? `You know a founder at ${best.round.company}` : `You know someone at ${best.round.company}`};
  }
  if (r.tie) return {strength: 2, matches: m, text: `Ask ${shortFund(r.tie.investor)}`};
  if (best) return {strength: 1, matches: m, text: `Same name: someone at ${best.round.company}`};
  return {strength: 0, matches: [], text: ""};
}

const hasConflict = (r) => (r.conflicts || []).length > 0;

/* Lower bound of the lead share (Wilson, z = 1): "Led 3 of 3" ranks below "Led 31 of 36". */
function leadScore(r) {
  const n = r.known, z = 1;
  if (!n) return -1;
  const p = r.led / n;
  return (p + z * z / (2 * n) - z * Math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / (1 + z * z / n);
}

/* Group by verdict; competitor conflicts sink to the bottom of their group; then stronger way in;
   then (when finding funds) more led rounds like yours; then the lead share's lower bound. */
function rankRows(rows) {
  return rows.map((r, idx) => ({...r, group: groupOf(r), way: wayIn(r), idx}))
    .sort((a, b) => GROUPS.indexOf(a.group) - GROUPS.indexOf(b.group)
      || hasConflict(a) - hasConflict(b)
      || b.way.strength - a.way.strength
      || (b.like_you?.length || 0) - (a.like_you?.length || 0)
      || leadScore(b) - leadScore(a)
      || a.idx - b.idx);
}

/* ---------------- check + find ---------------- */
function skeleton() {
  return `<div class="skel skel-lg"></div><div class="skel skel-md"></div>${'<div class="skel"></div>'.repeat(6)}`;
}

async function run() {
  const text = $("#funds").value;
  if (!text.trim()) { $("#funds").focus(); $("#line-count").textContent = "Paste at least one fund name first."; return; }
  if (!targetOk()) return;
  await check({funds_text: text, stage: state.stage, target_eur_m: targetValue(), investors: [...state.investors],
    lead: state.lead, company: $("#company").value.trim() || null, competitors: [...state.competitors]});
}

/* The sample has its own request, so its investor, competitor and raise never land in the founder's form.
   Lifeline Ventures is the sample's investor (for the way-in ties) but not its lead: two of the ten rounds behind
   its "Will your lead come back?" card are not supported by press, so the sample does not show that card. */
function runSample() {
  setStage("seed");
  check({funds_text: SAMPLE, stage: "seed", target_eur_m: 3, investors: ["Lifeline Ventures"], lead: null,
    company: null, competitors: ["Lovable"], sample: true});
}

function check(body) {
  const {sample, ...payload} = body;
  return load(() => api("/api/check", {method: "POST", body: JSON.stringify(payload)}), (data) => ({...data, mode: "check"}), body);
}

const REGION_LABEL = {nordics: "the Nordics", baltics: "the Baltics", dach: "Germany, Austria and Switzerland", "uk-ie": "the UK and Ireland",
  "france-benelux": "France and Benelux", south: "Southern Europe", cee: "Central and Eastern Europe", "": "Europe"};

async function runFind() {
  if (!targetOk()) return;
  const req = {stage: state.stage, target_eur_m: targetValue(), region: $("#region").value || null,
    investors: [...state.investors], competitors: [...state.competitors]};
  await load(() => api("/api/discover", {method: "POST", body: JSON.stringify(req)}), (d) => {
    const sz = d.filters.size ? ` of EUR ${fmtM(d.filters.size[0])} to ${fmtM(d.filters.size[1])}m` : "";
    const where = esc(REGION_LABEL[req.region || ""]);
    return {mode: "discover", stage: d.filters.stage, rows: d.funds, unmatched: [], competitors: {},
      headline: d.funds.length
        ? `These <b>${d.funds.length}</b> funds led the most of the <b>${d.rounds_matched}</b> ${esc(d.filters.stage)} rounds${sz} in ${where} from the last 30 months.`
        : `No ${esc(d.filters.stage)} rounds${sz} in ${where} from the last 30 months in our data. Try a wider region or clear the target raise.`};
  }, req);
}

async function load(fetcher, toView, req) {
  closePane();
  setScreen("results");
  const out = $("#results");
  out.setAttribute("aria-busy", "true");
  out.innerHTML = skeleton();
  window.scrollTo(0, 0);
  $("#go").disabled = true;
  try {
    const view = toView(await fetcher());
    counted.clear();
    state.view = view;
    state.req = req;
    state.resultView = "list";
    state.mapRevealed = false;
    renderResults();
    $("#results h1")?.focus();
  } catch (err) {
    const retry = !err.status || err.status >= 500 || err.status === 429;
    if (err.message !== "auth") out.innerHTML = `<div class="alert" role="alert"><h3>Could not check the list</h3>${esc(err.message)}.${retry ? " Try again in a moment." : " Change it and check again."}</div><div class="after"><button class="btn line" type="button" data-edit>Back to the list</button></div>`;
  } finally {
    $("#go").disabled = false;
    out.setAttribute("aria-busy", "false");
  }
}

/* ---------------- results ---------------- */
const ICON = {
  back: `<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M10 3.5 5.5 8l4.5 4.5"/></svg>`,
  copy: `<svg viewBox="0 0 16 16" aria-hidden="true"><rect x="5" y="5" width="8.5" height="8.5" rx="1.5"/><path d="M11 5V3.5a1 1 0 0 0-1-1H3.5a1 1 0 0 0-1 1V10a1 1 0 0 0 1 1H5"/></svg>`,
  print: `<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4.5 6V2.5h7V6M4.5 11.5h-2v-5h11v5h-2"/><rect x="4.5" y="9.5" width="7" height="4"/></svg>`,
  link: `<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M6.5 9.5 9.5 6.5M7 4.5l1-1a2.5 2.5 0 0 1 3.5 3.5l-1 1M9 11.5l-1 1A2.5 2.5 0 0 1 4.5 9l1-1"/></svg>`,
  flag: `<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3.5 14V2.5M3.5 3h8l-1.5 3 1.5 3h-8"/></svg>`,
  x: `<svg viewBox="0 0 16 16" aria-hidden="true"><path d="m4 4 8 8M12 4l-8 8"/></svg>`,
};

function verdictText(r) {
  switch (r.verdict) {
    case "leads": return r.verdict_label;
    case "leads_size": return /smaller/.test(r.verdict_label) ? "Leads smaller rounds" : "Leads larger rounds";
    case "mixed": return "Sometimes leads";
    case "follows": return "Mostly follows";
    case "few": return "Too little data";
    case "public": return "Public funder, not a lead";
    default: return r.verdict_label;
  }
}
const verdictPill = (r) => `<span class="pill v-${esc(r.verdict)}"><span class="g" aria-hidden="true"></span>${esc(verdictText(r))}</span>`;

/* One shared log scale (EUR 0.2m to 50m) so every row's size strip reads the same way. */
function sx(v) {
  const lo = Math.log(0.2), hi = Math.log(50);
  return Math.max(0, Math.min(1, (Math.log(Math.max(v, 0.2)) - lo) / (hi - lo))) * 56;
}
function sizeCell(r, target) {
  if (!r.size) return `<span class="muted">Not stated</span>`;
  const s = r.size, a = sx(s.lo), b = sx(s.hi);
  const fits = s.fit === "fits";
  /* Fewer than 5 led rounds with an amount: grey range, its n, and no size verdict. */
  const unclear = s.unclear ? `<small>${plural(s.n, "sized round", "sized rounds")}, size unclear</small>` : "";
  const you = target ? `<rect class="you" x="${(sx(target) - 1).toFixed(1)}" y="0" width="2" height="14" rx="1"/>` : "";
  const fitWord = {fits: "fits your raise", larger: "smaller than your raise", smaller: "larger than your raise"}[s.fit] || "";
  return `<span class="size${s.unclear ? " unclear" : ""}"><svg class="strip${fits ? " fit" : ""}" viewBox="0 0 56 14" aria-hidden="true"><rect class="trk" x="0" y="6" width="56" height="2" rx="1"/><rect class="rng" x="${a.toFixed(1)}" y="4" width="${Math.max(4, b - a).toFixed(1)}" height="6" rx="3"/>${you}</svg><span>EUR ${fmtM(s.lo)}${s.hi !== s.lo ? ` to ${fmtM(s.hi)}` : ""}m</span>${unclear}${fitWord ? `<span class="sr">, ${fitWord}</span>` : ""}</span>`;
}
/* ---------------- recount tally: one dot per round with a named lead ----------------
   Filled = it led, hollow = it joined, oldest first. Rounds with no named lead and rounds the source disputes are
   never dots; the row prints how many there are. Long records keep the newest TALLY_CAP dots and say "+N earlier". */
const TALLY_COLS = 24, TALLY_CAP = 48;

function tallyRounds(r) {
  if (!r._tally) {
    r._tally = [...(r.rounds_led || []).map((x) => ({...x, L: 1})), ...(r.rounds_joined || []).map((x) => ({...x, L: 0}))]
      .sort((a, b) => a.t - b.t || a.id - b.id);
  }
  return r._tally;
}

/* Rings on a dot: your investor was in that round, someone you know works there, or it backed your competitor. */
function dotMarks(r) {
  const marks = new Map();
  const add = (rid, k, text) => { if (rid == null) return; if (!marks.has(rid)) marks.set(rid, []); marks.get(rid).push({k, text}); };
  if (r.tie) add(r.tie.round.id, "tie", `Your investor ${r.tie.investor} was in this round too`);
  for (const c of r.conflicts || []) add(c.round.id, "cf", `${c.level === "led" ? "Led" : "Joined"} ${c.competitor}, your competitor`);
  for (const m of r.way?.matches || []) if (m.strength > 1) add(m.round.rid, "net", `You know ${personName(m.person)} here${sampleNet() ? " (made-up sample)" : ""}`);
  return marks;
}

function tallyHtml(r, {plain = false, cols = TALLY_COLS, cap = TALLY_CAP} = {}) {
  const all = tallyRounds(r);
  if (all.length > cap) { cols -= 4; cap = cols * 2; }  // room for "+N earlier" in front of the dots
  const shown = all.slice(-cap), hidden = all.length - shown.length;
  const rows = Math.min(2, Math.max(1, Math.ceil(shown.length / cols)));
  const marks = plain ? new Map() : dotMarks(r);
  const dots = shown.map((x, j) => {
    const ks = (marks.get(x.id) || []).map((m) => m.k);
    const ring = ks.includes("cf") ? " cf" : ks.includes("tie") ? " tie" : ks.includes("net") ? " net" : "";
    return `<span class="td${x.L ? " led" : ""}${ring}" data-r="${hidden + j}"></span>`;
  }).join("");
  const label = `${r.name}: led ${r.led} of ${r.known} rounds with a named lead${r.unknown ? `, ${r.unknown} more name no lead` : ""}${r.disputed ? `, ${r.disputed} disputed by the source and not counted` : ""}. Arrow keys read each round.`;
  return `<span class="tw">${hidden ? `<span class="earlier">+${hidden} earlier</span>` : ""}<span class="tally" data-rows="${rows}" tabindex="0" role="img" aria-label="${esc(label)}">${dots}<span class="tsw" aria-hidden="true"></span></span></span>`;
}

const counterHtml = (r) => `<span class="counter" aria-hidden="true">Led <b class="cl">${r.led}</b> of <span class="ck">${r.known}</span>${r.unknown ? " named" : ""}</span>`;

function ledCell(r) {
  const extra = [r.unknown ? `${r.unknown} unnamed` : "", r.disputed ? `${r.disputed} disputed, not counted` : ""].filter(Boolean).join(", ");
  if (!r.known) return `<span class="rec"><span class="muted">No named leads</span>${extra ? `<small>${extra}</small>` : ""}</span>`;
  return `<span class="rec${r.verdict === "leads" ? " lead" : ""}">${tallyHtml(r)}<span class="rec-l">${counterHtml(r)}${extra ? `<small aria-hidden="true">${extra}</small>` : ""}</span></span>`;
}

/* One clock drives every row that is counting: dot i lands at t0 + i * iv; the counter and the sweep follow it. */
const counted = new Set();
const countJobs = new Set();
let countRaf = 0, countIO = null;

function startCount(host, r, delay, iv) {
  const all = tallyRounds(r), dots = $$(".td", host), n = dots.length, hidden = all.length - n;
  if (!n) return;
  const cum = [0];
  all.forEach((x) => cum.push(cum[cum.length - 1] + x.L));
  const job = {host, n, hidden, cum, shown: 0, t0: performance.now() + delay,
    iv: iv || Math.max(14, Math.min(34, Math.round(900 / n))),
    cl: $(".cl", host), ck: $(".ck", host), sw: $(".tsw", host), dots};
  host.classList.add("tpre");
  host.classList.remove("landed");
  dots.forEach((d) => d.classList.remove("in"));
  job.cl.textContent = cum[hidden];
  job.ck.textContent = hidden;
  countJobs.add(job);
  if (!countRaf) countRaf = requestAnimationFrame(countTick);
}
function countTick(now) {
  for (const j of countJobs) {
    const e = now - j.t0;
    if (e < 0) continue;
    const k = Math.min(j.n, Math.floor(e / j.iv) + 1);
    if (k > j.shown) {
      const before = j.cum[j.hidden + j.shown];
      for (let i = j.shown; i < k; i++) j.dots[i].classList.add("in");
      j.shown = k;
      j.host.classList.add("counting");
      j.ck.textContent = j.hidden + k;
      j.cl.textContent = j.cum[j.hidden + k];
      if (j.cum[j.hidden + k] > before && j.cl.animate) j.cl.animate([{transform: "translateY(-3px) scale(1.18)"}, {transform: "none"}], {duration: 240, easing: "cubic-bezier(.3,1.6,.5,1)"});
      const d = j.dots[k - 1];
      j.sw.style.transform = `translateX(${d.offsetLeft + d.offsetWidth + 3}px)`;
    }
    if (k >= j.n && e > j.n * j.iv + 140) landCount(j);
  }
  countRaf = countJobs.size ? requestAnimationFrame(countTick) : 0;
}
function landCount(j) {
  j.host.classList.remove("counting", "tpre");
  j.host.classList.add("landed");
  j.dots.forEach((d) => d.classList.remove("in"));
  j.cl.textContent = j.cum[j.cum.length - 1];
  j.ck.textContent = j.cum.length - 1;
  countJobs.delete(j);
}
/* Print, reduced motion and re-renders all show the final count. */
function landAll() { [...countJobs].forEach(landCount); }

/* Rows count in when they scroll into view; rows that arrive together go top to bottom, 70 ms apart.
   A fund counts once per result set: adding a network or switching views never replays it. */
function setupCounting(out) {
  countIO?.disconnect();
  for (const j of countJobs) if (!j.host.isConnected) countJobs.delete(j);
  const rows = $$(".row", out).filter((el) => $(".tally", el));
  if (reduceMotion() || typeof IntersectionObserver !== "function") return;
  const fresh = rows.filter((el) => !counted.has(el.dataset.k));
  fresh.forEach((el) => el.classList.add("tpre"));
  countIO = new IntersectionObserver((entries) => {
    const now = entries.filter((e) => e.isIntersecting).map((e) => e.target).sort((a, b) => rows.indexOf(a) - rows.indexOf(b));
    now.forEach((el, i) => {
      countIO.unobserve(el);
      counted.add(el.dataset.k);
      startCount(el, state.ranked[+el.dataset.i], 120 + i * 70);
    });
  }, {threshold: 0.4});
  fresh.forEach((el) => countIO.observe(el));
}

/* ---------------- hover and focus card for one dot ---------------- */
function tallyFund(host) {
  if (host.dataset.p != null) return state.proof?.funds[+host.dataset.p];
  return state.ranked[+host.dataset.i];
}
function dotInfo(r, x, withMarks) {
  const others = (x.leads || []).filter((n) => companyKey(n) !== companyKey(r.name));
  const who = x.L ? (others.length ? `Led by ${r.name}, with ${others.join(", ")}` : `Led by ${r.name}`)
    : `Joined. Led by ${(x.leads || []).join(", ")}`;
  const marks = withMarks ? (dotMarks(r).get(x.id) || []) : [];
  return {company: x.company, date: x.date, detail: `${x.stage}${x.amount_eur_m ? `, EUR ${fmtM(x.amount_eur_m)}m` : ", amount not stated"}`, who, marks};
}
function showTip(dot) {
  const host = dot.closest("[data-i], [data-p]"), r = host && tallyFund(host);
  if (!r) return;
  const x = tallyRounds(r)[+dot.dataset.r];
  if (!x) return;
  const info = dotInfo(r, x, host.dataset.p == null);
  const tip = $("#tip");
  tip.innerHTML = `<b>${esc(info.company)}</b> <span class="m">${esc(info.date)}</span><br><span class="m">${esc(info.detail)}</span><br>${esc(info.who)}`
    + info.marks.map((m) => `<span class="k"><i class="${m.k === "cf" ? "x" : ""}"></i>${esc(m.text)}</span>`).join("");
  tip.classList.add("on");
  const b = dot.getBoundingClientRect(), w = tip.offsetWidth, h = tip.offsetHeight;
  const left = Math.max(8, Math.min(innerWidth - w - 8, b.left + b.width / 2 - w / 2));
  const top = b.top - h - 10 < 8 ? b.bottom + 10 : b.top - h - 10;
  tip.style.transform = `translate(${Math.round(left)}px, ${Math.round(top)}px)`;
  $$(".td.hot").forEach((d) => d.classList.remove("hot"));
  dot.classList.add("hot");
  return info;
}
function hideTip() { $("#tip").classList.remove("on"); $$(".td.hot").forEach((d) => d.classList.remove("hot")); }

function setupTips() {
  document.addEventListener("mouseover", (e) => {
    const d = e.target.closest(".td");
    if (d) { showTip(d); return; }
    if (!e.target.closest(".tally")) hideTip();
    /* Last lead and way in point at their dot. */
    const row = e.target.closest(".row");
    const r = row && state.ranked[+row.dataset.i];
    if (!r) return;
    let rid = null;
    if (e.target.closest(".c-last") && r.last_lead) rid = r.last_lead.id;
    if (e.target.closest(".c-way")) rid = r.way.matches.find((m) => m.strength > 1)?.round.rid ?? r.tie?.round.id;
    const i = tallyRounds(r).findIndex((x) => x.id === rid);
    const dot = i >= 0 && row.querySelector(`.td[data-r="${i}"]`);
    if (dot) dot.classList.add("hot");
  });
  document.addEventListener("scroll", hideTip, true);
  document.addEventListener("focusout", (e) => { if (e.target.closest?.(".tally")) hideTip(); });
  document.addEventListener("keydown", (e) => {
    const t = e.target.closest?.(".tally");
    if (!t) return;
    const dots = $$(".td", t);
    if (!dots.length) return;
    let cur = dots.findIndex((d) => d.classList.contains("hot"));
    if (e.key === "ArrowRight" || e.key === "ArrowDown") cur = Math.min(dots.length - 1, cur + 1);
    else if (e.key === "ArrowLeft" || e.key === "ArrowUp") cur = cur < 0 ? dots.length - 1 : Math.max(0, cur - 1);
    else if (e.key === "Home") cur = 0;
    else if (e.key === "End") cur = dots.length - 1;
    else if (e.key === "Escape") { hideTip(); return; }
    else return;
    e.preventDefault();
    const info = showTip(dots[cur]);
    if (info) announce(`${info.company}, ${info.date}. ${info.detail}. ${info.who}.${info.marks.map((m) => ` ${m.text}.`).join("")}`);
  });
}
function lastCell(r) {
  if (r.verdict === "public") return `<span class="last muted">Not counted</span>`;
  return r.last_lead ? `<span class="last">${esc(r.last_lead.company)} <span class="d">${esc(r.last_lead.date)}</span></span>` : `<span class="last muted">Never led</span>`;
}
/* The Way in column only shows once the founder gave us something to look for paths with. */
const askedForPaths = () => (state.req?.investors?.length || 0) > 0 || !!state.network;
const sampleNet = () => !!state.network?.sample;
const wayFromNet = (r) => r.way.matches.length > 0 && r.way.strength !== 2;
function wayCell(r) {
  if (!r.way.strength) return `<span class="way">None found</span>`;
  const weak = r.way.strength === 1;
  return `<span class="way${weak ? " weak" : " yes"}">${ICON.link}${esc(r.way.text)}</span>${sampleNet() && wayFromNet(r) ? `<span class="tag-sample">Sample</span>` : ""}`;
}
function conflictFlag(r) {
  const c = (r.conflicts || [])[0];
  if (!c) return "";
  return `<span class="flag">${ICON.flag}${c.level === "led" ? "Led" : "Backed"} ${esc(c.competitor)}</span>`;
}

function rowHtml(r, i, showWay) {
  return `<li class="row" data-i="${i}" data-k="${esc(r.key || r.name)}">
    <div class="cell c-fund"><span class="fund-l1"><button type="button" class="nm" data-open="${i}" aria-haspopup="dialog">${esc(r.name)}</button>${conflictFlag(r)}</span>${verdictLine(r)}</div>
    <div class="cell c-led"><span class="lbl">Lead record</span>${ledCell(r)}</div>
    <div class="cell c-size"><span class="lbl">Round size it leads</span>${sizeCell(r, state.req?.target_eur_m)}</div>
    <div class="cell c-last"><span class="lbl">Last lead</span>${lastCell(r)}</div>
    ${showWay ? `<div class="cell c-way"><span class="lbl">Way in</span>${wayCell(r)}</div>` : ""}
  </li>`;
}
/* Verdict as one quiet line under the fund name: the group heading already says the rest. */
const verdictLine = (r) => `<span class="vline v-${esc(r.verdict)}"><span class="g" aria-hidden="true"></span>${esc(verdictText(r))}</span>`;

function groupHead(key, n, d, req) {
  const t = req.target_eur_m;
  const cap = {
    pitch: `They led at least half of the ${d.stage} rounds they joined where the lead is named${t ? `. Size is judged against your EUR ${fmtM(t)}m only with 5 or more sized rounds` : ""}`,
    size: "They lead, but rounds bigger or smaller than yours",
    few: "Too few rounds with a named lead to judge. Open a fund to see its rounds",
    avoid: "They lead less than half the time, or have not led lately. Open a fund to see its rounds",
  }[key];
  return `<h2 class="grp" id="g-${key}">${GROUP_NAME[key]} <span class="n">${n}</span><span class="cap">${esc(cap)}</span></h2>`;
}

function summaryLine(d, ranked, req) {
  if (d.headline) return d.headline;
  const n = ranked.length;
  if (!n) return "None of the pasted lines matched a fund in our Cala data.";
  const by = (g) => ranked.filter((r) => r.group === g).length;
  const conf = ranked.filter(hasConflict).length;
  const ways = ranked.filter((r) => r.way.strength > 0).length;
  const fits = ranked.filter((r) => r.group === "pitch" && r.size?.fit === "fits").length;
  const parts = [`<b class="acc">${by("pitch")} of ${n}</b> mostly lead ${esc(d.stage)} rounds${req.target_eur_m ? `, ${fits} of them at a size like your EUR ${fmtM(req.target_eur_m)}m` : ""}`];
  if (by("size")) parts.push(`<b>${by("size")}</b> ${by("size") === 1 ? "leads" : "lead"}, but a different size`);
  if (conf) parts.push(`<b class="wrn">${conf}</b> backed ${esc(req.competitors.join(" or "))}`);
  if (askedForPaths()) parts.push(`you have a way in to <b>${ways}</b>`);
  return parts.join(". ").replace(/\. you/, ". You") + ".";
}

function roundLine(req) {
  const bits = [esc(state.view.stage)];
  if (req.target_eur_m) bits.push(`EUR ${fmtM(req.target_eur_m)}m`);
  if (req.investors?.length) bits.push(`with ${esc(req.investors.join(", "))}`);
  if (req.competitors?.length) bits.push(`vs ${esc(req.competitors.join(", "))}`);
  return bits.join(" · ");
}

/* Without a target raise the size column is not judged, so "Pitch first" only means "leads at your stage". Say so. */
function notesUnderSummary(req) {
  const out = [];
  if (req.sample) out.push(`<p class="sample-line">Sample round: Seed, EUR 3m, Lifeline Ventures as your investor, Lovable as a competitor. <button type="button" class="linkbtn" data-edit>Check your own list</button></p>`);
  else if (!req.target_eur_m) out.push(`<p class="size-off">Size not checked. <button type="button" class="linkbtn" data-edit-target>Add your target raise</button></p>`);
  return out.join("");
}

function netbarHtml() {
  const n = state.network;
  const privacy = `<p class="privacy"><svg viewBox="0 0 16 16" aria-hidden="true"><rect x="3.5" y="7" width="9" height="6.5" rx="1.5"/><path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2"/></svg>Read in your browser. Nothing is uploaded or stored.</p>`;
  if (n) {
    return `<div class="netbar on" id="netbar"><div class="t"><b>Matched against ${plural(n.people.length, "connection", "connections")}</b> ${n.sample ? "from a made-up sample network." : "from your LinkedIn file."}${privacy}</div><button type="button" class="btn line" data-net-clear>Remove network</button></div>`;
  }
  return `<div class="netbar" id="netbar"><div class="t"><b>See who can introduce you.</b> Add your LinkedIn connections and we match them to the companies each fund backed.${privacy}</div>
    <input type="file" id="li-file-2" class="file-in" accept=".csv,.zip,text/csv,application/zip" aria-label="Add LinkedIn connections, Connections.csv or the LinkedIn .zip">
    <label for="li-file-2" class="btn line">Add LinkedIn connections</label>
    <button type="button" class="linkbtn" data-net-sample>Try with a sample network</button></div>`;
}

function renderSide(req) {
  const dd = (v, empty) => v ? `<dd>${esc(v)}</dd>` : `<dd class="unset">${empty}</dd>`;
  const n = state.network;
  $("#props").innerHTML = `
    <div class="prop"><dt>Stage</dt>${dd(state.view.stage)}</div>
    <div class="prop"><dt>Raising</dt>${dd(req.target_eur_m ? `EUR ${fmtM(req.target_eur_m)}m` : "", "Not set")}</div>
    <div class="prop"><dt>Investors</dt>${dd((req.investors || []).join(", "), "None added")}</div>
    <div class="prop"><dt>Competitors</dt>${dd((req.competitors || []).join(", "), "None added")}</div>
    <div class="prop"><dt>Network</dt>${dd(n ? `${plural(n.people.length, "connection", "connections")}${n.sample ? ", made-up sample" : ""}` : "", "Not added")}</div>`;
}

function renderResults() {
  const d = state.view, req = state.req;
  const out = $("#results");
  const ranked = rankRows(d.rows || []);
  state.ranked = ranked;
  renderSide(req);
  const showWay = askedForPaths();
  const groups = GROUPS.map((g) => [g, ranked.map((r, i) => [r, i]).filter(([r]) => r.group === g)]).filter(([, rs]) => rs.length);
  const list = groups.map(([g, rs]) => `<section aria-labelledby="g-${g}">${groupHead(g, rs.length, d, req)}<ul class="grp-list">${rs.map(([r, i]) => rowHtml(r, i, showWay)).join("")}</ul></section>`).join("");
  const isFind = d.mode === "discover";
  const isMap = state.resultView === "map" && ranked.length > 0;
  out.classList.toggle("has-way", showWay);
  out.innerHTML = `
    <div class="topbar">
      <button class="btn" type="button" data-edit>${ICON.back}${isFind ? "Change search" : "Edit list"}</button>
      <span class="sp"></span>
      <button class="btn" type="button" id="csv">${ICON.copy}Copy as CSV</button>
      <button class="btn" type="button" id="print">${ICON.print}Print sheet</button>
    </div>
    <p class="print-head"><b>${esc(APP())}</b> · ${roundLine(req)} · Cala round data, retrieved ${esc(state.meta?.retrieved || "")}${req.sample ? " · Sample round" : ""}${sampleNet() ? " · Way in uses a made-up sample network" : ""}</p>
    <div class="head">
      <div class="head-row">
        <h1 tabindex="-1">${isFind ? "Funds that led rounds like yours" : "Your shortlist"} <span class="meta">${plural(ranked.length, "fund", "funds")}${isFind ? " found" : " recounted"}</span></h1>
        ${ranked.length ? viewToggleHtml(isMap) : ""}
      </div>
      <p class="round-line">${roundLine(req)}</p>
      <p class="summary">${summaryLine(d, ranked, req)}</p>
      ${notesUnderSummary(req)}
    </div>
    ${ranked.length ? netbarHtml() : ""}
    ${ranked.length ? `<div class="listview${isMap ? " hidden" : ""}" id="listview">${readLine(req, showWay)}<div class="cols" aria-hidden="true"><span>Fund</span><span>Lead record, oldest first</span><span>Round size${req.target_eur_m ? ` vs your ${fmtM(req.target_eur_m)}m` : " it leads"}</span><span class="c-last">Last lead</span>${showWay ? "<span>Way in</span>" : ""}</div>${list}</div>
      <div class="mapview${isMap ? "" : " hidden"}" id="mapview"><div class="radar-wrap"><div class="radar" id="radar"><div class="rsweep" aria-hidden="true"></div><svg viewBox="-320 -320 640 640" role="group" aria-label="Fund map. Closer to You means the fund leads rounds like yours more often. Around the dial is when it last led, newest at the top."></svg></div><p class="map-note" id="map-note"></p></div><div class="rail" id="rail"></div></div>`
      : `<p class="empty">None of the pasted lines matched a fund in our Cala data.</p>`}
    <div class="after">${afterHtml(d)}</div>`;
  $("#csv").onclick = () => copyCsv(ranked);
  $("#print").onclick = () => { landAll(); window.print(); };
  $("#ask-live")?.addEventListener("click", () => startLookup(d.lookup_candidates));
  const f2 = $("#li-file-2");
  if (f2) { f2.addEventListener("change", () => { readNetworkFile(f2.files[0]); f2.value = ""; }); setupDrop($("#netbar")); }
  $$(".row", out).forEach((row) => row.addEventListener("click", (e) => { if (!e.target.closest("button, a")) openFund(+row.dataset.i, row.querySelector(".nm")); }));
  $$("[data-open]", out).forEach((b) => b.addEventListener("click", () => openFund(+b.dataset.open, b)));
  $$("[data-view]", out).forEach((b) => b.addEventListener("click", () => setResultView(b.dataset.view)));
  setupCounting(out);
  if (isMap) drawMap({reveal: !state.mapRevealed, linesIn: state.mapRevealed});
  else stopMap();
  announce(`${plural(ranked.length, "fund", "funds")}. ${out.querySelector(".summary")?.textContent || ""}`);
  tourAfterResults();
}

const viewToggleHtml = (isMap) => `<div class="viewtog" role="group" aria-label="View">
  <button type="button" data-view="list" aria-pressed="${!isMap}"><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 4.5h10M3 8h10M3 11.5h10"/></svg>List</button>
  <button type="button" data-view="map" aria-pressed="${isMap}"><svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6"/><circle cx="8" cy="8" r="3"/><path d="M8 8 12.2 3.8"/></svg>Map</button></div>`;

/* How to read a row's dots, said once above the list. Rings only show once there is something to ring. */
function readLine(req, showWay) {
  const comps = req.competitors || [];
  return `<p class="read"><span class="legend" aria-hidden="true"><span><i class="l"></i>Led the round</span><span><i></i>Joined it</span>${showWay ? `<span><i class="w"></i>Your way in</span>` : ""}${comps.length ? `<span><i class="x"></i>Backed ${esc(comps.join(" or "))}</span>` : ""}</span><span>One dot per round with a named lead, oldest first. Hover a dot for the round.</span></p>`;
}

function setResultView(v) {
  if (state.resultView === v) return;
  state.resultView = v;
  const isMap = v === "map";
  $$("#results [data-view]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.view === v)));
  $("#listview")?.classList.toggle("hidden", isMap);
  $("#mapview")?.classList.toggle("hidden", !isMap);
  hideTip();
  if (isMap) { drawMap({reveal: !state.mapRevealed}); announce("Map view. Closer to You means the fund leads rounds like yours more often."); }
  else { stopMap(); announce("List view."); }
}

function afterHtml(d) {
  const notes = [];
  if (d.lead_back) {
    const l = d.lead_back;
    notes.push(`<div class="note"><h3>Will your lead come back?</h3>In the data, <b>${esc(l.lead)}</b> led ${plural(l.cases, "round", "rounds")} whose company raised again. It joined the next round in <b>${l.came_back} of ${l.cases}</b> and led it in <b>${l.led_again}</b>.</div>`);
  }
  if (d.timing) {
    const t = d.timing;
    notes.push(`<div class="note"><h3>Timing from peers</h3>Companies here raised their ${esc(t.to)} a median <b>${t.median} months</b> after their ${esc(t.from)}. Middle half: ${t.p25} to ${t.p75} months, ${t.n} companies.</div>`);
  }
  const miss = Object.entries(d.competitors || {}).filter(([, n]) => !n).map(([c]) => c);
  if (miss.length) notes.push(`<div class="note thin"><h3>Competitor not in our data</h3>No rounds found for ${miss.map(esc).join(", ")}, so no conflict can be shown for ${miss.length === 1 ? "it" : "them"}.</div>`);
  return [
    notes.length ? `<div class="notes">${notes.join("")}</div>` : "",
    geminiNote(d.read_by_gemini),
    d.lookup_candidates?.length ? lookupPanel(d.lookup_candidates) : "",
    d.unmatched?.length ? `<div class="unmatched"><b>Not recognised:</b> ${d.unmatched.map((u) => `<span class="mono">${esc(u)}</span>`).join(" · ")}</div>` : "",
  ].join("");
}

function geminiNote(g) {
  if (!g) return "";
  if (g.error) return "";
  const notFound = g.funds.filter((f) => !g.matched.includes(f));
  return `<p class="plain">${plural(g.lines, "line", "lines")} our parser could not read went to ${esc(g.model)}, which only picks out fund names. ${g.matched.length ? `Found: ${g.matched.map((f) => `<b>${esc(f)}</b>`).join(", ")}.` : "No fund names matched our data."}${notFound.length ? ` Not in our data: ${notFound.map(esc).join(", ")}.` : ""} Every verdict is still counted.</p>`;
}

function lookupPanel(names) {
  return `<div class="lookup" id="live">
    <div class="lookup-head"><div><h3>Not in our data yet</h3><p>${names.map((n) => `<b>${esc(n)}</b>`).join(", ")}. We can ask Cala now, about a minute per fund.</p></div>
    <button class="btn line" type="button" id="ask-live">Look up ${plural(names.length, "fund", "funds")} in Cala</button></div>
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
  const label = {queued: "waiting", asking: "asking Cala", done: "rounds found", empty: "Cala has no rounds for this fund", error: "Cala did not answer", budget: "live lookups used up"};
  const paint = (j) => {
    ledger.innerHTML = j.items.map((i) => `<li class="led-${esc(i.status)}"><span class="dot" aria-hidden="true"></span><b>${esc(i.name)}</b><span class="st">${esc(label[i.status] || i.status)}${i.status === "done" ? `, ${plural(i.rows, "round", "rounds")}` : ""}${i.seconds != null ? `, ${i.seconds} s` : ""}</span></li>`).join("");
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
    const req = state.req;
    if (req?.funds_text == null) return;
    if (!req.sample) { const box = $("#funds"); if (!box.value.includes(extra)) box.value = box.value.trim() + "\n" + extra; lineCount(); }
    check({...req, funds_text: req.funds_text.includes(extra) ? req.funds_text : `${req.funds_text.trim()}\n${extra}`});
  }
}

function copyCsv(rows) {
  const q = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  const head = ["Group", "Fund", "Verdict", "Led", "Known rounds", "Lead not named", "Size it leads (EUR m)", "Size vs your raise", "Last lead", "Way in", "Conflict"];
  const lines = [head.map(q).join(",")];
  const fake = sampleNet();
  rows.forEach((r) => lines.push([GROUP_NAME[r.group], r.name, verdictText(r), r.led, r.known, r.unknown,
    r.size ? `${fmtM(r.size.lo)}-${fmtM(r.size.hi)}` : "", r.size?.fit || "", r.last_lead ? `${r.last_lead.company} ${r.last_lead.date}` : "",
    fake && wayFromNet(r) ? `SAMPLE, made-up contact: ${r.way.text}` : r.way.text,
    (r.conflicts || []).map((c) => `${c.level} ${c.competitor}`).join("; ")].map(q).join(",")));
  const btn = $("#csv");
  const done = (msg) => { btn.lastChild.textContent = msg; setTimeout(() => { btn.lastChild.textContent = "Copy as CSV"; }, 1600); };
  if (!navigator.clipboard) return done("Copy not available");
  navigator.clipboard.writeText(lines.join("\n")).then(() => done("Copied"), () => done("Copy blocked"));
}

/* ---------------- evidence pane ---------------- */
let paneCleanup = null;

function openPane(returnFocus) {
  if ($("#pane-root .pane")) return;
  const root = $("#pane-root");
  root.innerHTML = `<div class="pane-back" data-close></div><aside class="pane" role="dialog" aria-modal="true" aria-labelledby="pane-h"><div class="ph" id="ph"></div><div class="pb" id="pb"></div></aside>`;
  const bg = [$(".app")];
  bg.forEach((el) => el.setAttribute("inert", ""));
  document.body.classList.add("no-scroll");
  const onKey = (ev) => {
    if (ev.key === "Escape") return closePane();
    if (ev.key === "Tab") {
      const f = reachable(root);
      if (!f.length) return;
      const first = f[0], last = f[f.length - 1], at = document.activeElement;
      if (!root.contains(at)) { ev.preventDefault(); (ev.shiftKey ? last : first).focus(); }
      else if (ev.shiftKey && at === first) { ev.preventDefault(); last.focus(); }
      else if (!ev.shiftKey && at === last) { ev.preventDefault(); first.focus(); }
    }
  };
  document.addEventListener("keydown", onKey);
  paneCleanup = () => {
    document.removeEventListener("keydown", onKey);
    bg.forEach((el) => el.removeAttribute("inert"));
    document.body.classList.remove("no-scroll");
    $$(".row.sel").forEach((x) => x.classList.remove("sel"));
    returnFocus?.focus();
  };
}
/* Focusable controls a keyboard user can actually reach: not inside a closed <details>, not hidden. */
function reachable(root) {
  return $$("button, a[href], summary, input, [tabindex='0']", root)
    .filter((x) => !x.disabled && !x.closest("details:not([open]) > :not(summary)") && !x.closest(".hidden") && x.getClientRects().length);
}

/* One click handler for the pane, attached once at boot (#pane-root persists across opens). */
function onPaneClick(e) {
  if (e.target.closest("[data-close]")) return closePane();
  const rid = e.target.closest("[data-rid]");
  if (rid) { e.preventDefault(); openRound(+rid.dataset.rid); return; }
  if (e.target.closest("[data-backfund]")) { e.preventDefault(); showFund(state.openIdx); return; }
  const more = e.target.closest("[data-more]");
  const list = more?.previousElementSibling;
  if (list) {
    const hidden = $$(".hidden", list);
    hidden.forEach((x) => x.classList.remove("hidden"));
    hidden[0]?.querySelector("a")?.focus();
    more.remove();
  }
}

function closePane() {
  $("#pane-root").innerHTML = "";
  const c = paneCleanup; paneCleanup = null; c?.();
  state.openIdx = null;
}

function openFund(i, from) {
  openPane(from);
  $$(".row.sel").forEach((x) => x.classList.remove("sel"));
  $(`.row[data-i="${i}"]`)?.classList.add("sel");
  showFund(i);
}

const closeBtn = `<span class="sp"></span><button class="x" type="button" data-close aria-label="Close">${ICON.x}</button>`;

function roundTable(rounds, limit = 8) {
  if (!rounds.length) return "";
  const li = (r, i) => `<div class="rr${i >= limit ? " hidden" : ""}"><span class="co"><a href="#" data-rid="${r.id}">${esc(r.company)}</a></span><span class="st">${esc(r.stage)}</span><span class="am num">${r.amount_eur_m ? `${fmtM(r.amount_eur_m)}m` : ""}</span><span class="dt">${esc(r.date)}</span></div>`;
  return `<div class="rt"><div class="rr hd"><span>Company</span><span>Stage</span><span class="am">EUR</span><span>Date</span></div><div>${rounds.map(li).join("")}</div>${rounds.length > limit ? `<button type="button" class="more" data-more>Show ${rounds.length - limit} more</button>` : ""}</div>`;
}

const personName = (p) => [p.first, p.last.length === 1 ? p.last : p.last ? `${p.last[0]}.` : ""].filter(Boolean).join(" ");

function waysHtml(r) {
  const parts = [];
  const m = r.way.matches;
  const fake = sampleNet();
  if (m.length) {
    const shown = m.slice(0, 8);
    parts.push(`<div class="introcard"><div class="l1">${ICON.link}${fake ? "Made-up sample: " : ""}You know ${plural(m.length, "person", "people")} at companies it backed</div>
      <ul class="people">${shown.map(({person, round, weak}) => `<li><span><span class="who">${esc(personName(person))}</span> <span class="role">${esc(person.position || "Role not given")}</span></span>${fake ? `<span class="tag-sample">Made-up sample contact</span>` : person.founder && !weak ? `<span class="tagx">Founder level</span>` : ""}<span class="via">Works at <a href="#" data-rid="${round.rid}">${esc(round.company)}</a>, whose ${esc(round.stage)} round in ${esc(round.date)} ${esc(r.name)} ${round.led ? "led" : "joined"}.${weak ? ` <span class="wrn">Same name only: check it is the same company.</span>` : ""}</span></li>`).join("")}</ul>
      ${m.length > shown.length ? `<p>And ${m.length - shown.length} more.</p>` : ""}</div>`);
  }
  if (r.tie) {
    const x = r.tie.round;
    parts[r.way.strength === 2 ? "unshift" : "push"](`<div class="introcard"><div class="l1">${ICON.link}Ask ${esc(r.tie.investor)}</div><p>Your investor <b>${esc(r.tie.investor)}</b> and ${esc(r.name)} were both in <a href="#" data-rid="${x.id}">${esc(x.company)}</a>'s ${esc(String(x.stage).toLowerCase())} round, ${esc(x.date)}, with ${x.n_investors} investors in total. Ask which partner was on that deal.</p></div>`);
  }
  if (!parts.length) {
    parts.push(`<div class="okline">${askedForPaths() ? "No one in your network or among your investors connects to this fund yet." : "Add your investors or LinkedIn connections to find a way in."}</div>`);
  }
  return parts.join("");
}

function showFund(i) {
  const r = state.ranked[i];
  if (!r) return;
  state.openIdx = i;
  const req = state.req;
  $("#ph").innerHTML = `<span class="muted">${i + 1} of ${state.ranked.length}</span>${closeBtn}`;
  const s1 = r.known
    ? `<div class="v">${r.led} <span class="of">of ${r.known}</span></div><div class="s">rounds with a named lead near your stage${r.unknown ? `. ${r.unknown} more had no named lead` : ""}${r.disputed ? `. ${r.disputed} disputed by its own source, not counted` : ""}</div>`
    : `<div class="v of">No data</div><div class="s">No rounds with a named lead near your stage</div>`;
  const fit = r.size?.fit;
  const s2 = r.size
    ? `<div class="v${r.size.unclear ? " of" : ""}">EUR ${fmtM(r.size.lo)}${r.size.hi !== r.size.lo ? ` to ${fmtM(r.size.hi)}` : ""}m</div><div class="s">${r.size.unclear ? `Middle half of ${plural(r.size.n, "sized led round", "sized led rounds")}, size unclear` : fit === "fits" ? `<span class="acc">Your ${fmtM(req.target_eur_m)}m fits</span>` : fit ? `<span class="wrn">Your ${fmtM(req.target_eur_m)}m is ${fit === "larger" ? "larger" : "smaller"}</span>` : `From ${plural(r.size.n, "led round", "led rounds")}`}</div>`
    : `<div class="v of">Not stated</div><div class="s">No round sizes in the data</div>`;
  const s3 = r.last_lead
    ? `<div class="v"><a href="#" data-rid="${r.last_lead.id}">${esc(r.last_lead.company)}</a></div><div class="s">${esc(r.last_lead.stage)}, ${esc(r.last_lead.date)}</div>`
    : `<div class="v of">Never</div><div class="s">No led round in our data</div>`;
  const comps = state.req.competitors || [];
  const conflicts = (r.conflicts || []).map((c) => `<div class="conf${c.level === "led" ? "" : " joined"}"><span>${c.level === "led" ? "Led" : "Joined"} <a href="#" data-rid="${c.round.id}">${esc(c.competitor)}</a>'s ${esc(c.round.stage)} round, ${esc(c.round.date)}</span></div>`).join("");
  const counts = [
    r.follow_ons ? `${plural(r.follow_ons, "follow-on round", "follow-on rounds")} in its own companies not counted` : "",
    `${r.total_rounds} rounds in total for this fund in our data`,
  ].filter(Boolean).join(". ");
  $("#pb").innerHTML = `
    <div class="ptitle"><h2 id="pane-h">${esc(r.name)}</h2>${verdictPill(r)}</div>
    ${r.pasted && r.pasted !== r.name ? `<div class="pasted">You pasted <q>${esc(r.pasted)}</q>${r.via === "gemini" ? ". Name read by Gemini" : ""}</div>` : ""}
    <div class="stats">
      <div class="stat"><div class="k">Led</div>${s1}</div>
      <div class="stat"><div class="k">Round size it leads</div>${s2}</div>
      <div class="stat"><div class="k">Last lead</div>${s3}</div>
    </div>
    <div class="sec"><h3 class="sech">How to get in</h3>${waysHtml(r)}</div>
    ${comps.length ? `<div class="sec"><h3 class="sech">Competitors</h3>${conflicts || `<div class="okline">No round with ${esc(comps.join(" or "))} in the data.</div>`}</div>` : ""}
    ${r.like_you?.length ? `<div class="sec"><h3 class="sech">Rounds like yours it led <span class="n">${r.like_you.length}</span></h3>${roundTable(r.like_you, 5)}</div>` : ""}
    <div class="sec"><h3 class="sech">Rounds it led <span class="n">${r.rounds_led.length}, newest first</span></h3>${roundTable(r.rounds_led) || `<div class="okline">No led rounds near your stage in the last four years.</div>`}</div>
    ${r.rounds_joined.length ? `<details class="fold"><summary>Joined, did not lead (${r.rounds_joined.length})</summary>${roundTable(r.rounds_joined)}</details>` : ""}
    ${r.rounds_unknown.length ? `<details class="fold"><summary>Lead not named (${r.rounds_unknown.length})</summary>${roundTable(r.rounds_unknown)}</details>` : ""}
    ${r.rounds_disputed?.length ? `<details class="fold"><summary>Disputed by the source, not counted (${r.rounds_disputed.length})</summary>${roundTable(r.rounds_disputed)}</details>` : ""}
    <p class="pnote">Counted over the last four years, at your stage and the stages next to it. ${esc(counts)}. Click any company to see the Cala record behind it.</p>`;
  $(".pane .x").focus();
}

async function openRound(rid) {
  const fund = state.ranked[state.openIdx];
  $("#ph").innerHTML = `${fund ? `<button class="back" type="button" data-backfund>${ICON.back}Back to ${esc(fund.name)}</button>` : ""}${closeBtn}`;
  $("#pb").innerHTML = `<h2 id="pane-h">Loading the round</h2><div class="skel"></div>`;
  ($(".pane .back") || $(".pane .x")).focus();
  try {
    const r = await api(`/api/record/${encodeURIComponent(rid)}`);
    $("#pb").innerHTML = `
      <div class="ptitle"><h2 id="pane-h">${esc(r.company)}, ${esc(r.stage)}</h2></div>
      <dl class="kv">
        <dt>Date</dt><dd>${esc(r.date)}</dd>
        <dt>Round</dt><dd>${esc(r.type || r.stage)}</dd>
        <dt>Amount</dt><dd>${r.amount_raw ? esc(r.amount_raw) : `<span class="none">not stated</span>`}${r.amount_eur_m ? ` <span class="muted">about EUR ${fmtM(r.amount_eur_m)}m</span>` : ""}</dd>
        <dt>Lead</dt><dd>${r.leads.length ? r.leads.map(esc).join(", ") : `<span class="none">not named</span>`}${disputeHtml(r.disputed)}</dd>
        <dt>Also in</dt><dd>${r.participants.length ? r.participants.map(esc).join(", ") : `<span class="none">none named</span>`}</dd>
        <dt>Found by</dt><dd>${r.path === "both" ? "Asking about the fund and about the company, both agree" : r.path === "investor_first" ? "Asking Cala about the fund" : "Asking Cala about the company"}</dd>
        <dt>Cala ids</dt><dd>${entityHtml(r)}</dd>
      </dl>
      <div class="sec"><h3 class="sech">Source documents</h3><div id="src-box">${sourceHtml(r.source)}</div></div>
      <div class="sec"><h3 class="sech">Cala company graph</h3><div id="graph-box">${graphHtml(r.graph)}</div></div>
      <details class="fold"><summary>Raw Cala rows (${r.sources.length})</summary>
        ${r.sources.map((s) => `<div class="prov"><div>POST /v1/knowledge/query, ${esc(s.path.replace("_", " "))}</div><div class="q">"${esc(s.query)}"</div><pre>${esc(JSON.stringify(s.row, null, 2))}</pre></div>`).join("")}
      </details>
      <p class="pnote">${esc(APP())} only counts and merges these Cala rows. Source documents come from Cala search.</p>`;
    const askG = $("#ask-graph");
    if (askG) askG.onclick = async () => {
      askG.disabled = true; askG.textContent = "Asking Cala";
      try { const g = await api(`/api/graph/${encodeURIComponent(rid)}`, {method: "POST", body: "{}"}); $("#graph-box").innerHTML = graphHtml(g, true); }
      catch (err) { askG.disabled = false; askG.textContent = err.message; }
    };
    const ask = $("#ask-src");
    if (ask) ask.onclick = async () => {
      ask.disabled = true; ask.textContent = "Asking Cala";
      try { const src = await api(`/api/source/${encodeURIComponent(rid)}`, {method: "POST", body: "{}"}); $("#src-box").innerHTML = sourceHtml(src, true); }
      catch (err) { ask.disabled = false; ask.textContent = err.message; }
    };
  } catch (err) {
    if (err.message !== "auth") $("#pb").innerHTML = `<h2 id="pane-h">Could not load this round</h2><p role="alert">${esc(err.message)}</p>`;
  }
}

/* The round's own Cala source text names another lead: say so next to the lead, in the source's words. */
function disputeHtml(d) {
  if (!d) return "";
  return `<span class="disp">Disputed: Cala's source text below names ${d.source_leads.map((x) => `<b>${esc(x)}</b>`).join(", ")} as lead, not ${d.not_lead_in_source.map(esc).join(", ")}. Not counted in any fund's lead record.</span>`;
}

function entityHtml(r) {
  const e = r.entity_ids || {};
  const one = (name, id) => `<span class="ent">${esc(name)} <code title="${esc(id || "")}">${id ? esc(id.slice(0, 8)) : "no id"}</code></span>`;
  return [one(r.company, e.company), ...(e.leads || []).map((l) => one(l.name, l.id))].join(" ");
}

const GRAPH_VERDICT = {
  agrees: ["g-ok", "The graph names the same lead"],
  differs: ["g-diff", "The graph names a different lead"],
  graph_no_lead: ["g-none", "The graph has this round but names no lead"],
};

function graphHtml(g, fresh) {
  if (!g) return `<div class="ask"><button class="btn line" type="button" id="ask-graph">Check in Cala's company graph</button><span class="muted">Not checked yet. Takes a few seconds.</span></div>`;
  const when = fresh ? `<span class="src-k">Checked just now</span>` : `<span class="src-k">From Cala's company graph</span>`;
  if (g.status === "no_rounds_in_graph") return `<div class="src">${when}<p>The graph has no funding rounds for this company yet. The round above comes from Cala's answers.</p></div>`;
  if (g.status === "round_not_in_graph") return `<div class="src">${when}<p>The graph has ${esc((g.graph_rounds || []).join(", ") || "other rounds")} for this company, but not this stage.</p></div>`;
  const x = g.round || {};
  if (g.agreement === "not_in_graph") return `<div class="src">${when}<p>The graph's ${esc(x.label || "")} round is dated ${esc(x.announced || x.event_date || "")}, more than a year from this one, so it is a different round.</p></div>`;
  const [cls, text] = GRAPH_VERDICT[g.agreement] || ["g-none", ""];
  const amount = x.amount ? `${esc(x.currency || "")} ${fmtM(x.amount / 1e6)}m` : "amount not stated";
  const srcs = (x.sources || []).filter((d) => /^https:\/\//.test(d.url));
  return `<div class="src">${when}
    <p class="g-verdict ${cls}">${esc(text)}</p>
    <dl class="kv">
      <dt>Round</dt><dd>${esc(x.label || "")} <code title="${esc(x.round_id || "")}">${esc((x.round_id || "").slice(0, 8))}</code></dd>
      <dt>Announced</dt><dd>${esc(x.announced || x.event_date || "not stated")}, ${amount}</dd>
      <dt>Marked lead</dt><dd>${x.leads?.length ? x.leads.map((l) => esc(l.name)).join(", ") : `<span class="none">none marked</span>`} <span class="muted">of ${x.n_investors || 0} investors</span></dd>
    </dl>
    ${srcs.length ? `<ol class="src-docs">${srcs.map((d) => `<li><a href="${esc(d.url)}" target="_blank" rel="noopener noreferrer">${esc(d.name)}</a>${d.date ? `<span class="muted">, ${esc(d.date)}</span>` : ""}</li>`).join("")}</ol>` : ""}
  </div>`;
}

function sourceHtml(src, fresh) {
  if (!src) return `<div class="ask"><button class="btn line" type="button" id="ask-src">Ask Cala for a source</button><span class="muted">None saved yet. One live search, about 30 seconds.</span></div>`;
  const docs = (src.docs || []).filter((d) => /^https:\/\//.test(d.url));
  const host = (u) => { try { return new URL(u).hostname; } catch { return ""; } };
  return `<div class="src">
    <span class="src-k">${fresh ? "Cala search, just now" : "Cala search"}</span>
    <p>${esc(String(src.answer || "").replace(/^#+\s*/gm, "").replace(/\*\*/g, ""))}</p>
    ${docs.length ? `<ol class="src-docs">${docs.map((d) => `<li><a href="${esc(d.url)}" target="_blank" rel="noopener noreferrer">${esc(d.name)}</a><span class="muted">, ${esc(d.site || host(d.url))}</span>${d.passage ? `<blockquote>${esc(d.passage.slice(0, 260))}${d.passage.length > 260 ? "…" : ""}</blockquote>` : ""}</li>`).join("")}</ol>` : `<p class="muted">Cala answered without a linked document.</p>`}
  </div>`;
}

/* ---------------- first run: two real funds recounted on a loop ---------------- */
const andList = (xs) => (xs.length < 2 ? xs.join("") : `${xs.slice(0, -1).join(", ")} and ${xs[xs.length - 1]}`);
let proofTimer = 0, proofPaused = false;

async function loadProof() {
  let d;
  try { d = await api("/api/proof"); } catch { return; }
  if (!d.funds?.length) return;
  state.proof = d;
  $("#proof-h").textContent = `${d.funds.length === 2 ? "Two funds" : "A fund"} from the sample list, recounted for a EUR ${fmtM(d.target_eur_m)}m ${d.stage} round`;
  $("#proof-rows").innerHTML = d.funds.map((r, p) => `<div class="proof-row v-${esc(r.verdict)}" data-p="${p}">
      <div class="c-fund"><span class="nm">${esc(r.name)}</span><span class="pill v-${esc(r.verdict)}"><span class="g" aria-hidden="true"></span>${esc(r.verdict === "leads" ? "Leads rounds like this" : verdictText(r))}</span></div>
      ${tallyHtml(r, {plain: true, cols: 60, cap: 120})}${counterHtml(r)}</div>`).join("");
  const unnamed = d.funds.filter((r) => r.unknown).map((r) => `${r.unknown} more ${r.name} rounds`);
  const disputed = d.funds.reduce((n, r) => n + (r.disputed || 0), 0);
  $("#proof-foot").textContent = `One dot per round where Cala names the lead, oldest first.${unnamed.length ? ` ${andList(unnamed)} name no lead, so they are not counted.` : ""}${disputed ? ` ${plural(disputed, "round is", "rounds are")} disputed by the source and left out.` : ""} Hover a dot to see the round.`;
  $("#proof").classList.remove("hidden");
  const box = $("#proof");
  box.addEventListener("mouseenter", () => { proofPaused = true; });
  box.addEventListener("mouseleave", () => { proofPaused = false; });
  box.addEventListener("focusin", () => { proofPaused = true; });
  box.addEventListener("focusout", () => { proofPaused = false; });
  runProof();
}

function proofLive() { return document.body.dataset.screen === "paste" && location.pathname !== "/method" && !document.hidden; }
function stopProof() { clearTimeout(proofTimer); }

/* Same speed per dot in both rows, so the short all-led record lands first while the long one keeps counting. */
function runProof() {
  clearTimeout(proofTimer);
  const d = state.proof;
  if (!d) return;
  const rows = $$("#proof .proof-row");
  if (reduceMotion()) return;
  rows.forEach((el, i) => startCount(el, d.funds[i], 250, 34));
  const total = 250 + Math.max(...d.funds.map((r) => tallyRounds(r).length)) * 34 + 300;
  proofTimer = setTimeout(function hold() {
    if (proofPaused || !proofLive()) { proofTimer = setTimeout(hold, 600); return; }
    $("#proof").classList.add("resetting");
    proofTimer = setTimeout(() => { $("#proof").classList.remove("resetting"); runProof(); }, 420);
  }, total + 3600);
}

/* ---------------- map: the shortlist as a radar ----------------
   Ring: the group, same as the list. Inside a ring, closer to You = higher lead score (the list's ranking).
   Around the dial: months since it last led a round (log scale), Now at 12 o'clock. Dot area: rounds it led.
   Orange ring: backed your competitor. Green line: a way in, from You through your investor or a contact. */
const SVGNS = "http://www.w3.org/2000/svg";
const R_YOU = 22, R_VIA = 70, R_IN = 98, R_OUT = 282;
const RING = {pitch: [R_IN, 172], size: [172, 214], few: [214, 248], avoid: [248, R_OUT]};
const RING_LABEL = {pitch: "PITCH FIRST", size: "DIFFERENT SIZE", few: "TOO LITTLE DATA", avoid: "FOLLOWS OR SOMETIMES LEADS"};
const DIAL_MAX = 300, NONE_A = 328;
const TICKS = [[0, "Now"], [1, "1 mo"], [3, "3 mo"], [6, "6 mo"], [12, "1 yr"], [24, "2 yrs"], [36, "3+ yrs"]];
const angleOf = (months) => (DIAL_MAX * Math.log1p(Math.min(months, 36))) / Math.log1p(36);
const polar = (r, deg) => [r * Math.sin((deg * Math.PI) / 180), -r * Math.cos((deg * Math.PI) / 180)];
const blipR = (led) => 5 + 2.05 * Math.sqrt(Math.min(led, 80));
let MAP = null, mapRaf = 0, arcId = 0;

function nowT() {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(state.meta?.retrieved || "");
  return m ? +m[1] + (+m[2] - 1 + +m[3] / 30) / 12 : 2026.87;
}
function svgEl(tag, attrs, parent) {
  const n = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs || {})) n.setAttribute(k, v);
  if (parent) parent.appendChild(n);
  return n;
}
function arcPath(r0, r1, a0, a1) {
  const [x0, y0] = polar(r1, a0), [x1, y1] = polar(r1, a1), [x2, y2] = polar(r0, a1), [x3, y3] = polar(r0, a0);
  const large = a1 - a0 > 180 ? 1 : 0;
  return `M${x0} ${y0}A${r1} ${r1} 0 ${large} 1 ${x1} ${y1}L${x2} ${y2}A${r0} ${r0} 0 ${large} 0 ${x3} ${y3}Z`;
}
/* Text that follows a ring, centred on angle a, flipped on the lower half so it never reads upside down. */
function arcText(g, defs, r, a, span, text, cls, fs) {
  const lower = a > 90 && a < 270;
  const [s, e] = lower ? [a + span, a - span] : [a - span, a + span];
  const [x0, y0] = polar(r, s), [x1, y1] = polar(r, e);
  const id = `arc${arcId++}`;
  svgEl("path", {id, d: `M${x0} ${y0}A${r} ${r} 0 0 ${lower ? 0 : 1} ${x1} ${y1}`, fill: "none"}, defs);
  const t = svgEl("text", {class: cls, "font-size": fs, dy: lower ? fs * 0.75 : fs * 0.1}, g);
  svgEl("textPath", {href: `#${id}`, startOffset: "50%", "text-anchor": "middle"}, t).textContent = text;
}
/* Ring names go in the widest empty stretch of the dial, so they never sit under a fund; inside that stretch,
   as close to the bottom as they fit, where the text runs flat. */
function quietAngle(items) {
  const as = items.map((P) => (P.a + 360) % 360).sort((x, y) => x - y);
  if (!as.length) return 200;
  let lo = 0, hi = 360, gap = -1;
  as.forEach((a, i) => {
    const b = i + 1 < as.length ? as[i + 1] : as[0] + 360;
    if (b - a > gap) { gap = b - a; lo = a; hi = b; }
  });
  if (hi - lo < 100) return ((lo + hi) / 2) % 360;
  const want = [190, 550].find((x) => x > lo + 50 && x < hi - 50);
  return (want ?? Math.max(lo + 50, Math.min(hi - 50, 190 + (lo > 190 ? 360 : 0)))) % 360;
}

function drawField(svg, k, items) {
  const defs = svgEl("defs", {}, svg);
  const f = svgEl("filter", {id: "glow", x: "-20%", y: "-20%", width: "140%", height: "140%"}, defs);
  svgEl("feGaussianBlur", {stdDeviation: 3.2}, f);
  const g = svgEl("g", {class: "rfield", "aria-hidden": "true"}, svg);
  svgEl("circle", {class: "band-few", r: RING.few[1]}, g);
  svgEl("circle", {class: "band-size", r: RING.size[1]}, g);
  svgEl("circle", {class: "band-pitch", r: RING.pitch[1]}, g);
  svgEl("path", {class: "stale-arc", d: arcPath(R_IN, R_OUT, angleOf(24), DIAL_MAX)}, g);
  svgEl("path", {class: "none-arc", d: arcPath(R_IN, R_OUT, DIAL_MAX + 5, 354)}, g);
  for (const [m] of TICKS) {
    const [x0, y0] = polar(R_IN, angleOf(m)), [x1, y1] = polar(R_OUT, angleOf(m));
    svgEl("line", {class: "spoke", x1: x0, y1: y0, x2: x1, y2: y1}, g);
  }
  svgEl("circle", {class: "ring pitch", r: RING.pitch[1]}, g);
  svgEl("circle", {class: "ring dash", r: RING.size[1]}, g);
  svgEl("circle", {class: "ring dash", r: RING.few[1]}, g);
  svgEl("circle", {class: "ring", r: R_OUT}, g);
  svgEl("circle", {class: "ring dash", r: R_IN}, g);
  const fs = 10.5 * k;
  for (const [m, label] of TICKS) {
    const a = angleOf(m), [x0, y0] = polar(R_OUT, a), [x1, y1] = polar(R_OUT + 5, a), [lx, ly] = polar(R_OUT + 9 + fs * 0.6, a);
    svgEl("line", {class: "tick", x1: x0, y1: y0, x2: x1, y2: y1}, g);
    svgEl("text", {class: `tick-l${m === 0 ? " now" : ""}`, x: lx, y: ly, "font-size": fs, "text-anchor": Math.abs(lx) < 8 ? "middle" : lx > 0 ? "start" : "end", "dominant-baseline": "central"}, g).textContent = label;
  }
  const zfs = 9 * k;
  arcText(g, defs, R_OUT + 10, (angleOf(24) + DIAL_MAX) / 2, 30, "OVER 2 YRS", "dial-l stale", zfs);
  arcText(g, defs, R_OUT + 10, (DIAL_MAX + 5 + 354) / 2, 30, "NO LEAD FOUND", "dial-l", zfs);
  const qa = quietAngle(items), bl = 9 * k;
  for (const [grp, [lo, hi]] of Object.entries(RING)) {
    arcText(g, defs, (lo + hi) / 2 - 3, qa, grp === "avoid" ? 52 : 40, RING_LABEL[grp], `band-l ${grp}`, bl);
  }
}
function drawYou(svg, k) {
  const you = svgEl("g", {class: "youg", "aria-hidden": "true"}, svg);
  svgEl("circle", {class: "you-halo", r: R_YOU + 12}, you);
  svgEl("circle", {class: "you", r: R_YOU}, you);
  svgEl("text", {class: "you-t", "font-size": Math.min(11.5 * k, 15), y: 0.5}, you).textContent = "You";
}

/* Each fund sits on its own ring at its last-lead angle; overlapping dots push apart a little, never off their ring. */
function layoutBlips(rows) {
  const now = nowT();
  const items = rows.map((r, idx) => {
    const months = r.last_lead ? Math.max(0, (now - r.last_lead.t) * 12) : null;
    const a0 = months == null ? NONE_A : angleOf(months);
    const [lo0, hi0] = RING[r.group] || RING.avoid;
    const lo = lo0 + 6, hi = hi0 - 6;
    const rb = blipR(r.led), score = Math.max(0, leadScore(r));
    const rad = lo + rb * 0.4 + (1 - score) * Math.max(0, hi - lo - rb * 0.8);
    return {r, idx, a0, a: a0, rad, rb, lo, hi, months};
  });
  const SLACK = 13;
  for (let it = 0; it < 240; it++) {
    for (let i = 0; i < items.length; i++) for (let j = i + 1; j < items.length; j++) {
      const A = items[i], B = items[j];
      const [ax, ay] = polar(A.rad, A.a), [bx, by] = polar(B.rad, B.a);
      const dx = bx - ax, dy = by - ay, d = Math.hypot(dx, dy) || 0.01, need = A.rb + B.rb + 8;
      if (d >= need) continue;
      const push = (need - d) / 2, ux = dx / d, uy = dy / d;
      const move = (P, s) => {
        const [px, py] = polar(P.rad, P.a), nx = px + ux * s, ny = py + uy * s;
        P.rad = Math.hypot(nx, ny);
        P.a = ((Math.atan2(nx, -ny) * 180) / Math.PI + 360) % 360;
        if (P.a > 350 && P.a0 < 40) P.a -= 360;
      };
      move(A, -push); move(B, push);
    }
    for (const P of items) {
      P.a = Math.max(Math.max(P.a0 - SLACK, 4), Math.min(P.a0 + SLACK, P.a));
      P.rad = Math.max(P.lo + P.rb * 0.4, Math.min(P.hi - P.rb * 0.4, P.rad));
    }
  }
  for (const P of items) [P.x, P.y] = polar(P.rad, P.a);
  return items;
}

/* Who stands between you and a fund: your investor (a small round together), or people at a company it backed.
   One node per investor or company, strongest first, at most 12 so the middle stays readable. */
function viaNodes(items) {
  const nodes = new Map();
  const add = (key, kind, label, P, strength, detail) => {
    if (!nodes.has(key)) nodes.set(key, {key, kind, label, links: [], people: new Set()});
    const n = nodes.get(key);
    if (!n.links.some((l) => l.item === P)) n.links.push({item: P, strength, detail});
    if (detail?.person) n.people.add(personName(detail.person));
  };
  for (const P of items) {
    const r = P.r;
    if (r.tie) add(`inv:${r.tie.investor}`, "inv", r.tie.investor, P, 2, r.tie);
    for (const m of r.way.matches) if (m.strength > 2) add(`co:${m.round.ckey}`, "person", m.round.company, P, m.strength, m);
  }
  const top = (n) => Math.max(...n.links.map((l) => l.strength));
  const all = [...nodes.values()].sort((p, q) => (q.kind === "inv") - (p.kind === "inv") || top(q) - top(p) || q.links.length - p.links.length);
  const list = all.slice(0, 12);
  list.extra = all.length - list.length;
  for (const n of list) {
    let sx = 0, sy = 0;
    for (const l of n.links) { sx += l.strength * Math.sin((l.item.a * Math.PI) / 180); sy += l.strength * Math.cos((l.item.a * Math.PI) / 180); }
    n.a0 = ((Math.atan2(sx, sy) * 180) / Math.PI + 360) % 360;
    n.a = n.a0; n.rad = R_VIA;
  }
  for (let it = 0; it < 200; it++) {
    for (let i = 0; i < list.length; i++) for (let j = i + 1; j < list.length; j++) {
      const A = list[i], B = list[j];
      const [ax, ay] = polar(A.rad, A.a), [bx, by] = polar(B.rad, B.a);
      const dx = bx - ax, dy = by - ay, d = Math.hypot(dx, dy) || 0.01;
      if (d >= 21) continue;
      const s = (21 - d) / 2, ux = dx / d, uy = dy / d;
      for (const [P, sg] of [[A, -s], [B, s]]) {
        const [px, py] = polar(P.rad, P.a), nx = px + ux * sg, ny = py + uy * sg;
        P.rad = Math.hypot(nx, ny);
        P.a = ((Math.atan2(nx, -ny) * 180) / Math.PI + 360) % 360;
      }
    }
    for (const n of list) {
      const da = Math.max(-28, Math.min(28, ((n.a - n.a0 + 540) % 360) - 180));
      n.a = (n.a0 + da + 360) % 360;
      n.rad = Math.max(R_YOU + 26, Math.min(R_IN - 10, n.rad));
    }
  }
  for (const n of list) [n.x, n.y] = polar(n.rad, n.a);
  return list;
}
function curve(n, P) {
  const da = ((P.a - n.a + 540) % 360) - 180;
  const [cx, cy] = polar(n.rad + (P.rad - n.rad) * 0.5, n.a + da * 0.2);
  return `M${n.x} ${n.y}Q${cx} ${cy} ${P.x} ${P.y}`;
}

const boxHit = (a, b) => !(a.x > b.x + b.w || a.x + a.w < b.x || a.y > b.y + b.h || a.y + a.h < b.y);
const circleHit = (box, x, y, r) => x + r > box.x && x - r < box.x + box.w && y + r > box.y && y - r < box.y + box.h;

/* Labels use their measured width and try eight spots around the dot, most important funds first.
   A label that fits nowhere is hidden and shows on hover or focus, so two names never print over each other. */
function placeLabels(items, nodes, fs, sfs) {
  const placed = [];
  const free = (box, self) => !placed.some((b) => boxHit(box, b))
    && !items.some((Q) => Q !== self && circleHit(box, Q.x, Q.y, Q.rb + (Q.r.conflicts?.length ? 6 : 2)))
    && !nodes.some((m) => circleHit(box, m.x, m.y, 11))
    && !circleHit(box, 0, 0, R_YOU + 10)
    && Math.hypot(box.x + box.w / 2, box.y + box.h / 2) < R_OUT + 4
    && box.x > -318 && box.x + box.w < 318;
  for (const n of nodes.filter((x) => x.labelEl)) {
    const t = n.labelEl, w = t.getComputedTextLength(), h = fs * 1.2;
    const ox = n.x >= 0 ? 1 : -1, oy = n.y >= 0 ? 1 : -1;
    const spots = [[ox, oy], [0, oy], [ox, 0], [-ox, 0], [0, -oy], [-ox, -oy]];
    let pick = null;
    for (const [cx, cy] of spots) {
      const box = {x: cx > 0 ? n.x + 13 : cx < 0 ? n.x - 13 - w : n.x - w / 2, y: cy > 0 ? n.y + 12 : cy < 0 ? n.y - 12 - h : n.y - h / 2, w, h};
      if (free(box, null)) { pick = box; break; }
    }
    if (!pick) { t.classList.add("off"); continue; }
    placed.push(pick);
    t.setAttribute("x", pick.x); t.setAttribute("y", pick.y + h * 0.8);
  }
  const order = [...items].sort((a, b) => (a.r.group === "pitch" ? 0 : 1) - (b.r.group === "pitch" ? 0 : 1) || b.r.led - a.r.led);
  for (const P of order) {
    const t = P.labelEl, s = P.subEl;
    const w = Math.max(t.getComputedTextLength(), s ? s.getComputedTextLength() : 0), lh = fs * 1.15, h = lh + (s ? sfs * 1.25 : 0);
    const pad = P.rb + (P.r.conflicts?.length ? 7 : 5), out = P.x >= 0 ? 1 : -1, d = pad * 0.72;
    const spots = [[out, 0], [-out, 0], [0, -1], [0, 1], [out, -1], [out, 1], [-out, -1], [-out, 1]];
    let pick = null;
    for (const [sx, sy] of spots) {
      const diag = sx && sy;
      const bx = sx > 0 ? (diag ? d : pad) : sx < 0 ? -(diag ? d : pad) - w : -w / 2;
      const by = sy < 0 ? -(diag ? d : pad) - h : sy > 0 ? (diag ? d : pad) : -h / 2;
      const box = {x: P.x + bx, y: P.y + by, w, h};
      if (free(box, P)) { pick = {box, bx, by, sx}; break; }
    }
    if (!pick) {  // hidden until hover or focus, then shown on the outer side
      const bx = out > 0 ? pad : -pad - w;
      pick = {box: null, bx, by: -h / 2, sx: out};
      t.classList.add("off"); s?.classList.add("off");
    } else placed.push(pick.box);
    const anchor = pick.sx > 0 ? "start" : pick.sx < 0 ? "end" : "middle";
    const tx = pick.sx > 0 ? pick.bx : pick.sx < 0 ? pick.bx + w : 0;
    t.setAttribute("x", tx); t.setAttribute("y", pick.by + lh * 0.8); t.setAttribute("text-anchor", anchor);
    if (s) { s.setAttribute("x", tx); s.setAttribute("y", pick.by + lh * 0.8 + sfs * 1.25); s.setAttribute("text-anchor", anchor); }
  }
}

function blipLabel(r) {
  const parts = [`${r.name}. ${GROUP_NAME[r.group]}.`, r.known ? `Led ${r.led} of ${r.known} rounds with a named lead.` : "No rounds with a named lead.",
    r.last_lead ? `Last lead ${r.last_lead.date}.` : "No lead found."];
  if (r.way.strength > 1) parts.push(`Way in: ${r.way.text}.`);
  if (r.conflicts?.length) parts.push(`Backed ${r.conflicts[0].competitor}.`);
  return `${parts.join(" ")} Opens the rounds behind it.`;
}

function stopMap() { cancelAnimationFrame(mapRaf); mapRaf = 0; }

function drawMap({reveal = false, linesIn = false} = {}) {
  const wrap = $("#radar");
  if (!wrap) return;
  stopMap();
  const svg = $("svg", wrap);
  svg.innerHTML = "";
  arcId = 0;
  const width = wrap.clientWidth || 640, compact = width < 520;
  const k = 640 / Math.max(300, width);
  wrap.classList.toggle("compact", compact);
  const items = layoutBlips(state.ranked);
  const nodes = viaNodes(items);
  drawField(svg, k, items);
  const pathsG = svgEl("g", {class: "paths", "aria-hidden": "true"}, svg);
  const viaG = svgEl("g", {class: "vias", "aria-hidden": "true"}, svg);
  drawYou(svg, k);
  const blipsG = svgEl("g", {class: "blips"}, svg);
  const fs = 12 * k, sfs = 10.5 * k;
  for (const n of nodes) {
    n.g = svgEl("g", {class: "pg"}, pathsG);
    const [sx, sy] = polar(R_YOU + 3, n.a);
    const segs = [`M${sx} ${sy}L${n.x} ${n.y}`, ...n.links.map((l) => curve(n, l.item))];
    n.segEls = segs.map((d, i) => {
      const weak = i > 0 && n.links[i - 1].strength === 3;
      const sg = svgEl("g", {class: "sg"}, n.g);
      svgEl("path", {class: "path-glow", d, "stroke-width": weak ? 3 : 6}, sg);
      svgEl("path", {class: `path${weak ? " weak" : ""}`, d, ...(weak ? {} : {pathLength: 1})}, sg);
      return sg;
    });
    n.links.forEach((l) => { (l.item.links = l.item.links || []).push(n); });
    const vg = svgEl("g", {class: `via ${n.kind}`, transform: `translate(${n.x} ${n.y})`}, viaG);
    n.vg = vg;
    if (n.kind === "inv") {
      svgEl("rect", {x: -10, y: -10, width: 20, height: 20, rx: 6}, vg);
      svgEl("text", {"font-size": 11, y: 0.5}, vg).textContent = n.label[0].toUpperCase();
      if (!compact) { n.labelEl = svgEl("text", {class: "via-l", "font-size": fs}, viaG); n.labelEl.textContent = shortFund(n.label); }
    } else {
      svgEl("circle", {r: 8}, vg);
      svgEl("circle", {class: "person", cy: -2, r: 2.3}, vg);
      svgEl("path", {class: "person", d: "M-3.9 4.4c.7-2.3 2.1-3.2 3.9-3.2s3.2.9 3.9 3.2"}, vg);
    }
  }
  for (const P of items) {
    const r = P.r;
    P.links = P.links || [];
    const kind = r.verdict === "public" ? "public" : r.group;
    const g = svgEl("g", {class: `blip ${kind}`, transform: `translate(${P.x} ${P.y})`, tabindex: 0, role: "button", "aria-label": blipLabel(r)}, blipsG);
    P.g = g;
    svgEl("circle", {class: "hit", r: Math.max(P.rb + 6, 14)}, g);
    svgEl("circle", {class: "ping", r: P.rb}, g);
    const core = svgEl("g", {class: "core"}, g);
    svgEl("circle", {class: "dotc", r: P.rb}, core);
    if (r.conflicts?.length) svgEl("circle", {class: "cfr", r: P.rb + 4}, core);
    svgEl("circle", {class: "sel", r: P.rb + (r.conflicts?.length ? 8 : 5)}, g);
    const lg = svgEl("g", {class: "labels"}, blipsG);
    P.lg = lg;
    lg.setAttribute("transform", `translate(${P.x} ${P.y})`);
    P.labelEl = svgEl("text", {class: "bl", "font-size": fs}, lg);
    P.labelEl.textContent = r.name;
    if (r.conflicts?.length) { P.subEl = svgEl("text", {class: "bl-sub", "font-size": sfs}, lg); P.subEl.textContent = `Backed ${r.conflicts[0].competitor}`; }
    if (compact) { P.labelEl.classList.add("off"); P.subEl?.classList.add("off"); }
    g.addEventListener("click", () => openFund(P.idx, g));
    g.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openFund(P.idx, g); } });
    g.addEventListener("mouseenter", () => focusOn(P));
    g.addEventListener("mouseleave", () => focusOn(null));
    g.addEventListener("focus", () => focusOn(P));
    g.addEventListener("blur", () => focusOn(null));
  }
  if (!compact) placeLabels(items, nodes, fs, sfs);
  MAP = {items, nodes, wrap};
  paintRail(nodes);
  $("#map-note").textContent = compact
    ? "Tap a dot to open the fund. Turn your phone sideways to see names, or use List."
    : "Hover a fund to light its way in. Click it to see the rounds behind it.";
  if (reveal && !reduceMotion()) revealMap();
  else {
    for (const n of nodes) n.g.querySelectorAll("path:not(.weak)").forEach((p) => p.classList.add("drawn"));
    if (linesIn && !reduceMotion()) drawPaths();
    ambient(0);
  }
  state.mapRevealed = true;
}

/* One pass of the sweep (about 1.15 s) shows each fund as it passes, then the ways in draw from You outward. */
function ping(P, strong) {
  if (reduceMotion() || !P.g) return;
  $(".ping", P.g).animate([{opacity: strong ? 0.55 : 0.2, transform: "scale(1)"}, {opacity: 0, transform: `scale(${1 + (strong ? 16 : 10) / P.rb})`}], {duration: strong ? 650 : 900, easing: "cubic-bezier(.2,.7,.2,1)"});
}
function revealMap() {
  const {items, nodes, wrap} = MAP;
  const sweep = $(".rsweep", wrap);
  wrap.classList.remove("ambient");
  wrap.classList.add("revealing");
  items.forEach((P) => { P.g.classList.add("pre"); P.lg.classList.add("pre"); P.shown = false; });
  nodes.forEach((n) => [n.g, n.vg, n.labelEl].forEach((x) => x?.classList.add("pre")));
  const T = 1150, t0 = performance.now();
  const ease = (x) => 1 - Math.pow(1 - x, 2.2);
  const step = (now) => {
    const x = Math.min(1, (now - t0) / T), th = ease(x) * 360;
    sweep.style.transform = `rotate(${th}deg)`;
    for (const P of items) {
      if (!P.shown && ((P.a + 360) % 360) <= th + 1) { P.shown = true; P.g.classList.remove("pre"); P.lg.classList.remove("pre"); ping(P, true); }
    }
    if (x < 1) { mapRaf = requestAnimationFrame(step); return; }
    items.forEach((P) => { P.g.classList.remove("pre"); P.lg.classList.remove("pre"); });
    wrap.classList.remove("revealing");
    drawPaths();
    ambient(360);
  };
  mapRaf = requestAnimationFrame(step);
}
function drawPaths() {
  MAP.nodes.forEach((n, i) => {
    [n.g, n.vg, n.labelEl].forEach((x) => x?.classList.remove("pre"));
    n.labelEl?.animate([{opacity: 0}, {opacity: 1}], {duration: 300, delay: 250, fill: "backwards"});
    n.vg.animate([{opacity: 0}, {opacity: 1}], {duration: 260, delay: i * 40, fill: "backwards"});
    n.segEls.forEach((sg, j) => sg.querySelectorAll("path").forEach((p) => {
      const delay = (j === 0 ? 0 : 200) + i * 45;
      if (p.classList.contains("weak")) { p.animate([{opacity: 0}, {opacity: 1}], {duration: 400, delay, fill: "backwards"}); return; }
      p.classList.add("drawn");
      p.animate([{strokeDashoffset: 1}, {strokeDashoffset: 0}], {duration: j === 0 ? 220 : 380, delay, easing: "cubic-bezier(.3,.6,.2,1)", fill: "backwards"});
    }));
  });
}
/* After the reveal a faint sweep keeps turning, 12 s a lap, and touches each fund it passes. */
function ambient(start) {
  if (reduceMotion() || !MAP) return;
  const wrap = MAP.wrap, sweep = $(".rsweep", wrap);
  wrap.classList.add("ambient");
  let last = performance.now(), th = start % 360;
  const step = (now) => {
    if (!wrap.isConnected) { mapRaf = 0; return; }
    const prev = th;
    th = (th + ((now - last) / 12000) * 360) % 360; last = now;
    sweep.style.transform = `rotate(${th}deg)`;
    for (const P of MAP.items) {
      const a = (P.a + 360) % 360;
      if ((prev < a && th >= a) || (th < prev && (a > prev || a <= th))) ping(P, false);
    }
    mapRaf = requestAnimationFrame(step);
  };
  mapRaf = requestAnimationFrame(step);
}

/* Hover lights a fund and every route into it; everything else steps back. */
function focusOn(P) {
  if (!MAP) return;
  MAP.wrap.classList.toggle("focus", !!P);
  for (const Q of MAP.items) {
    Q.g.classList.toggle("lit", Q === P);
    Q.lg.classList.toggle("lit", Q === P);
  }
  for (const n of MAP.nodes) {
    const on = !!P && n.links.some((l) => l.item === P);
    n.g.classList.toggle("lit", on); n.vg.classList.toggle("lit", on); n.labelEl?.classList.toggle("lit", on);
    n.segEls.forEach((s, i) => s.classList.toggle("off", on && i > 0 && n.links[i - 1].item !== P));
  }
  $$("#rail [data-node]").forEach((b) => b.classList.toggle("on", !!P && MAP.nodes[+b.dataset.node].links.some((l) => l.item === P)));
}
function focusNode(n) {
  if (!MAP) return;
  MAP.wrap.classList.toggle("focus", !!n);
  for (const m of MAP.nodes) {
    m.g.classList.toggle("lit", m === n); m.vg.classList.toggle("lit", m === n); m.labelEl?.classList.toggle("lit", m === n);
    m.segEls.forEach((s) => s.classList.remove("off"));
  }
  for (const Q of MAP.items) {
    const on = !!n && n.links.some((l) => l.item === Q);
    Q.g.classList.toggle("lit", on); Q.lg.classList.toggle("lit", on);
  }
}

const PERSON = `<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="5.5" r="2.5"/><path d="M3.5 13.5c.8-2.8 2.4-4 4.5-4s3.7 1.2 4.5 4"/></svg>`;
function paintRail(nodes) {
  const comps = state.req?.competitors || [];
  const funds = new Set(nodes.flatMap((n) => n.links.map((l) => l.item))).size;
  const fake = sampleNet();
  const ways = nodes.length
    ? `<ul class="ways">${nodes.map((n, i) => {
        const names = andList(n.links.map((l) => esc(l.item.r.name)));
        const who = n.kind === "inv" ? `<b>${esc(n.label)}</b>, your investor, was in a small round with ${names}`
          : `<b>${n.people.size > 1 ? `${n.people.size} people` : "Someone"} at ${esc(n.label)}</b>${fake ? " (made-up sample)" : ""}, backed by ${names}`;
        return `<li><button type="button" data-node="${i}"><span class="ic${n.kind === "inv" ? " inv" : ""}">${n.kind === "inv" ? esc(n.label[0].toUpperCase()) : PERSON}</span><span>${who}</span></button></li>`;
      }).join("")}</ul>${nodes.extra > 0 ? `<p class="rail-more">And ${plural(nodes.extra, "more way in", "more ways in")}. The list shows the best one per fund.</p>` : ""}`
    : `<p class="rail-none">${askedForPaths() ? "No one among your investors or connections links to these funds yet." : "Add your investors or LinkedIn connections to see who can introduce you."}</p>`;
  const legend = `<ul class="legend-map">
    <li><svg viewBox="0 0 28 20" aria-hidden="true"><circle cx="4" cy="10" r="3" class="lg-ink"/><path d="M10 10a10 10 0 0 1 16 -6" class="lg-ring"/><path d="M10 10a10 10 0 0 1 16 6" class="lg-dash"/></svg><span><b>Closer to You</b> means it leads rounds like yours more often. Rings are the list's groups.</span></li>
    <li><svg viewBox="0 0 28 20" aria-hidden="true"><path d="M14 2a8 8 0 1 1 -8 8" class="lg-arc"/><path d="M14 0v5" class="lg-now"/></svg><span><b>Around the dial</b> is when it last led a round. Newest at the top.</span></li>
    <li><svg viewBox="0 0 28 20" aria-hidden="true"><circle cx="6" cy="10" r="3.5" class="lg-pitch"/><circle cx="19" cy="10" r="7" class="lg-pitch"/></svg><span><b>Bigger dot</b> means more rounds led.</span></li>
    <li><svg viewBox="0 0 40 20" aria-hidden="true"><circle cx="5" cy="10" r="4.5" class="lg-pitch"/><circle cx="15" cy="10" r="4.5" class="lg-size"/><circle cx="25" cy="10" r="4.5" class="lg-few"/><circle cx="35" cy="10" r="4.5" class="lg-avoid"/></svg><span><b>Green</b> leads at your stage, <b>pale green</b> at another size, <b>dashed</b> too little data or a public funder, <b>grey</b> rarely leads.</span></li>
    <li><svg viewBox="0 0 28 20" aria-hidden="true"><path d="M2 14Q12 2 26 8" class="lg-line"/></svg><span><b>Green line</b> is a way in, through your investor or someone you know.</span></li>
    ${comps.length ? `<li><svg viewBox="0 0 28 20" aria-hidden="true"><circle cx="14" cy="10" r="4.5" class="lg-pitch"/><circle cx="14" cy="10" r="8" class="lg-conf"/></svg><span><b>Orange ring</b> means it backed ${esc(comps.join(" or "))}.</span></li>` : ""}
  </ul>`;
  $("#rail").innerHTML = `<section class="panel"><h2>Ways in ${funds ? `<span class="n">${plural(funds, "fund", "funds")}</span>` : ""}</h2>${ways}</section>
    <section class="panel"><h2>How to read it</h2>${legend}</section>`;
  $$("#rail [data-node]").forEach((b) => {
    const n = nodes[+b.dataset.node];
    b.addEventListener("mouseenter", () => focusNode(n));
    b.addEventListener("focus", () => focusNode(n));
    b.addEventListener("mouseleave", () => focusOn(null));
    b.addEventListener("blur", () => focusOn(null));
    b.addEventListener("click", () => openFund(n.links[0].item.idx, b));
  });
}

let mapResizeT = 0;
window.addEventListener("resize", () => {
  clearTimeout(mapResizeT);
  mapResizeT = setTimeout(() => { if (state.resultView === "map" && $("#mapview:not(.hidden)")) drawMap(); }, 200);
});

/* ---------------- green-dot guide: four short steps on the first visit ---------------- */
const TOUR_KEY = "recount.tour.v1";
const tourGet = () => { try { return localStorage.getItem(TOUR_KEY); } catch { return "done"; } };
const tourSet = (v) => { try { localStorage.setItem(TOUR_KEY, v); } catch { /* private mode: the guide just shows again */ } };
const TOUR = [
  {screen: "paste", title: "Start with your list", text: "Paste the funds you plan to pitch, one per line. No list yet? Press Try a sample.",
    anchor: () => (state.mode === "find" ? $("#mode-find") : $("#mode-list"))},
  {screen: "paste", title: "Your round", text: "Pick your stage and how much you want to raise. We check if each fund leads rounds like that.",
    anchor: () => $(".round-fields")},
  {screen: "paste", title: "Who can introduce you", text: "Optional: add your investors or LinkedIn connections. We show who can introduce you to each fund.",
    anchor: () => $("#opt > summary")},
  {screen: "results", title: "Read your shortlist", text: "Funds come in groups, best first. Click a fund to see the rounds behind every number. Try Map for the big picture.",
    anchor: () => [$("#results .grp"), $("#results .grp-list .row"), innerWidth >= 600 ? $("#results .viewtog") : null]},
];
const tour = {i: -1, back: null, raf: 0, dotAt: null};

function tourRect(anchor) {
  const els = (Array.isArray(anchor) ? anchor : [anchor]).filter((x) => x && x.getClientRects().length);
  if (!els.length) return null;
  const rs = els.map((x) => x.getBoundingClientRect());
  const top = Math.min(...rs.map((r) => r.top)), left = Math.min(...rs.map((r) => r.left));
  return {top, left, right: Math.max(...rs.map((r) => r.right)), bottom: Math.max(...rs.map((r) => r.bottom)), els};
}

function tourOpen(i) {
  const root = $("#tour-root");
  if (!root.firstChild) {
    tour.back = document.activeElement;
    root.innerHTML = `<div class="tour-ring" aria-hidden="true"></div><span class="guide" aria-hidden="true"></span>
      <div class="tour-card" role="dialog" aria-modal="false" aria-labelledby="tour-h" aria-describedby="tour-t">
        <div class="tour-top"><span class="tour-dot" aria-hidden="true"></span><span class="tour-step" id="tour-step"></span><span class="sp"></span><button type="button" class="linkbtn" data-tour="skip">Skip</button></div>
        <h2 id="tour-h"></h2><p id="tour-t"></p>
        <div class="tour-act"><button type="button" class="btn line" data-tour="back">Back</button><button type="button" class="btn primary" data-tour="next">Next</button></div>
      </div>`;
    root.addEventListener("click", onTourClick);
    document.addEventListener("keydown", onTourKey, true);
    window.addEventListener("scroll", tourPlaceSoon, true);
    window.addEventListener("resize", tourPlaceSoon);
    const logo = $(".brand .logo")?.getBoundingClientRect();
    if (logo) tour.dotAt = [logo.left + logo.width * 0.486 - 6, logo.top + logo.height * 0.575 - 6];  // the dot in the logo's o
  }
  tourShow(i);
}

function tourShow(i) {
  const step = TOUR[i];
  tour.i = i;
  if (step.screen === "results" && !state.view) return tourClose("p");
  if (document.body.dataset.screen !== step.screen) {
    setScreen(step.screen);
    if (step.screen === "paste") window.scrollTo(0, 0);
  }
  $("#tour-step").textContent = `Step ${i + 1} of ${TOUR.length}`;
  $("#tour-h").textContent = step.title;
  $("#tour-t").textContent = step.text;
  const back = $("[data-tour='back']"), next = $("[data-tour='next']");
  back.classList.toggle("hidden", i === 0);
  next.textContent = i === TOUR.length - 1 ? "Done" : i === 2 && !state.view ? "Got it" : "Next";
  const r = tourRect(step.anchor());
  const roomBelow = innerWidth < 600 ? 200 : 40;  // the card sits under the anchor, or as a sheet on phones
  if (r && (r.top < 64 || r.bottom > innerHeight - roomBelow)) r.els[0].scrollIntoView({block: "center", behavior: reduceMotion() ? "auto" : "smooth"});
  tourPlace();
  next.focus({preventScroll: true});
  announce(`${step.title}. ${step.text}`);
}

function tourPlaceSoon() { cancelAnimationFrame(tour.raf); tour.raf = requestAnimationFrame(tourPlace); }
function tourPlace() {
  const card = $(".tour-card"), ring = $(".tour-ring"), dot = $(".guide");
  if (!card || tour.i < 0) return;
  const r = tourRect(TOUR[tour.i].anchor());
  if (!r) { ring.classList.add("hidden"); return; }
  ring.classList.remove("hidden");
  const pad = 6, top = r.top - pad, left = r.left - pad, w = r.right - r.left + pad * 2, h = r.bottom - r.top + pad * 2;
  ring.style.transform = `translate(${Math.round(left)}px, ${Math.round(top)}px)`;
  ring.style.width = `${Math.round(w)}px`;
  ring.style.height = `${Math.round(h)}px`;
  const [dx, dy] = [left - 7, top - 7];
  if (tour.dotAt) { dot.style.transform = `translate(${tour.dotAt[0]}px, ${tour.dotAt[1]}px)`; tour.dotAt = null; void dot.offsetWidth; }
  dot.style.transform = `translate(${Math.round(dx)}px, ${Math.round(dy)}px)`;
  const narrow = innerWidth < 600;
  card.classList.toggle("sheet", narrow);
  if (narrow) { card.style.transform = ""; return; }
  const cw = card.offsetWidth, ch = card.offsetHeight;
  const x = Math.max(16, Math.min(innerWidth - cw - 16, left));
  let y = top + h + 12;
  if (y + ch > innerHeight - 12) y = top - ch - 12;
  if (y < 12) y = Math.min(innerHeight - ch - 12, Math.max(12, top + 24));
  card.style.transform = `translate(${Math.round(x)}px, ${Math.round(y)}px)`;
}

function tourClose(flag) {
  const root = $("#tour-root");
  if (!root.firstChild) return;
  tourSet(flag);
  root.removeEventListener("click", onTourClick);
  document.removeEventListener("keydown", onTourKey, true);
  window.removeEventListener("scroll", tourPlaceSoon, true);
  window.removeEventListener("resize", tourPlaceSoon);
  root.innerHTML = "";
  tour.i = -1;
  const back = tour.back;
  tour.back = null;
  if (back && back.isConnected && back.getClientRects().length) back.focus({preventScroll: true});
}

function onTourClick(e) {
  const b = e.target.closest("[data-tour]");
  if (!b) return;
  const act = b.dataset.tour;
  if (act === "skip") return tourClose("done");
  if (act === "back") return tourShow(Math.max(0, tour.i - 1));
  if (tour.i === TOUR.length - 1) return tourClose("done");
  if (tour.i === 2 && !state.view) return tourClose("p");  // step 4 waits for the first results
  tourShow(tour.i + 1);
}
function onTourKey(e) {
  if (e.key === "Escape" && !$("#pane-root .pane")) { e.stopPropagation(); tourClose("done"); }
}

/* First results after steps 1 to 3 (or the guide still open on them): show step 4 once. */
function tourAfterResults() {
  const open = !!$("#tour-root").firstChild;
  if (open || tourGet() === "p") setTimeout(() => { if (state.view && $("#results .grp")) tourOpen(3); }, reduceMotion() ? 0 : 600);
}
function tourMaybeStart() {
  if (location.pathname === "/method" || location.hash === "#demo") return;
  if (tourGet() == null) tourOpen(0);
}

/* ---------------- method ---------------- */
function renderMethod() {
  const m = state.meta || {};
  const v = m.validation;
  const rule = (verdict, label, text) => `<li>${verdictPill({verdict, verdict_label: label})}<span>${text}</span></li>`;
  $("#view-method").innerHTML = `<div class="method">
    <h1>Method and limits</h1>
    <p class="lede">How ${esc(APP())} turns Cala round records into a verdict per fund, what we tested, and where it can be wrong.</p>
    <section class="ai-box"><h2>Counting, not AI</h2>
      <p>Verdicts, counts, ties and conflicts are plain counting over Cala round records. The same input always gives the same list, and every number opens the rounds behind it. No language model ranks or judges a fund. Gemini only reads pasted lines our parser cannot match, and only picks out fund names.</p></section>
    <section><h2>Verdict rules</h2>
      <p>Counted over the last four years, at your stage and the stages next to it. A round counts as known when Cala names its lead. Follow-on rounds in a fund's own companies are not counted as new investments.</p>
      <p>Answers to "which rounds did this fund invest in" name the rounds a fund led more often than the rounds it only joined, so the lead share is an upper bound. Every row shows how many of its rounds had no named lead. When a round's own Cala source text names a different lead, the round is marked disputed and left out of every fund's lead count.</p>
      <ul class="rules">
        ${rule("leads", "Leads rounds like yours", "Led 2 or more rounds at your stage, led at least half of its new investments where the lead is named, and your target raise sits inside the range it leads (the middle half of its led round sizes, from 0.8x the low end to 1.25x the high end).")}
        ${rule("leads_size", "Leads larger rounds", "Leads at your stage, but your target is outside that size range. Sizes come from its leads at your exact stage when there are at least 2, otherwise from the stages next to it.")}
        ${rule("leads", "Leads at your stage, size unclear", "Leads at your stage, but fewer than 5 of its led rounds have a known amount. The range is shown in grey with its count, and no size verdict is given.")}
        ${rule("follows", "Mostly follows", "5 or more new investments with a named lead, and led fewer than 15% of them.")}
        ${rule("stale", "No lead since a date", "Has led before, but not in the last 24 months.")}
        ${rule("mixed", "Sometimes leads", "Everything in between, for example a fund that led 4 of 10.")}
        ${rule("few", "Too little data", "Fewer than 3 known rounds in the window. We show the rounds, not a verdict.")}
        ${rule("public", "Public funder, not a lead", "Grant bodies, public funds and accelerators. Shown, never judged as a lead.")}
      </ul></section>
    <section><h2>How the list is ordered</h2>
      <p>Funds are grouped by verdict (leads rounds like yours first, then leads a different size, then too little data to tell, then mostly follows, sometimes leads, no recent lead or public funder), a fund that led or joined a competitor's round sinks to the bottom of its group, and inside a group a stronger way in comes first (a founder at a company the fund led, then anyone at a company it led, then anyone at a company it joined, then one of your investors in a small round with it, then a same-name match on a short or ordinary-word company), then, when finding funds, more led rounds like yours, then the share of rounds led, judged by its lower bound (Wilson, z = 1) so 3 of 3 does not beat 31 of 36.</p></section>
    <section><h2>Your network</h2>
      <p>Your LinkedIn connections file is read in your browser. Only first name, last name, company and position are kept, in memory, for this page; URLs and emails are never read, and nothing is uploaded or stored. Each connection's company is matched by name to the companies a fund led or joined in our data. Very short or generic company names are skipped. Names of 5 letters or fewer and ordinary words (Junction, Bolt, Garage) are shown as "same name" only, never as founder level, because a stranger's employer can share them. A title counts as founder level only when it starts with founder, co-founder, CEO, CTO, managing director or general or managing partner; assistants and associates do not count. A match is a person at a company, not a promise they know the partner.</p></section>
    <section><h2>What we tested</h2>
      ${v ? `<table class="simple"><thead><tr><th>Test</th><th>Result</th><th>n</th></tr></thead><tbody>${v.rows.map((r) => `<tr><td>${esc(r.test)}</td><td>${esc(r.result)}</td><td class="num">${esc(r.n)}</td></tr>`).join("")}</tbody></table><p class="muted">${esc(v.note || "")}</p>` : `<p class="muted">Validation numbers are being recomputed on the full data.</p>`}
      ${v?.accuracy?.length ? `<details class="fold-raw"><summary>Every hand check, with its source (${v.accuracy.length})</summary><table class="simple"><thead><tr><th>Round</th><th>Lead in Cala</th><th>Check</th></tr></thead><tbody>${v.accuracy.map((a) => `<tr><td>${esc(a.company)} <span class="muted">${esc(a.date)} ${esc(a.stage || "")}</span></td><td>${esc((a.cala_leads || []).join(", "))}</td><td>${esc(a.verdict)}${a.source_url && /^https:\/\//.test(a.source_url) ? `, <a href="${esc(a.source_url)}" target="_blank" rel="noopener noreferrer">source</a>` : ""}</td></tr>`).join("")}</tbody></table></details>` : ""}
      <p><a href="/static/cala-data-quality.json" download>Data quality findings we prepared for Cala</a> (JSON).</p></section>
    <section><h2>Limits</h2>
      <ul>
        <li>Fund level, not partner level. A tie means two funds sat in the same round; ask your investor which partner was on it.</li>
        <li>About a third of seed rounds in our data name no lead. Those rounds are left out of the lead ratio, so thinly covered funds show "Too little data"; every fund shows how many rounds had no named lead.</li>
        <li>Coverage is what Cala returned to our questions: mostly European venture rounds from 2021 to 2026. A fund missing here is missing from our snapshot, not necessarily from Cala.</li>
        <li>Company discovery started from startups that raised over EUR 2m, so very small rounds are under-represented.</li>
        <li>Two ways of asking can label the same round differently. The round record shows both raw rows when that happens.</li>
      </ul></section>
    <section><h2>Coverage</h2>
      <dl class="cover">
        <div><dt>Funds asked</dt><dd class="num">${esc(m.funds_queried ?? "")}</dd></div>
        <div><dt>Companies</dt><dd class="num">${esc(m.companies?.toLocaleString("en") ?? "")}</dd></div>
        <div><dt>Rounds</dt><dd class="num">${esc(m.rounds?.toLocaleString("en") ?? "")}</dd></div>
        <div><dt>Investors</dt><dd class="num">${esc(m.investors?.toLocaleString("en") ?? "")}</dd></div>
        <div><dt>Retrieved</dt><dd class="num">${esc(m.retrieved ?? "")}</dd></div>
      </dl>
      <p>Cala endpoints used: /v1/knowledge/query for round data (asked about each fund and about each company), /v1/knowledge/search for source documents, /v1/entities for ids and the cross-check against Cala's company graph.</p>
      <p>Aiven Postgres stores the snapshot, the rounds and every live Cala answer. Modal serves this app and runs the live Cala lookups. Snapshot ${esc(m.version || "")}.</p></section>
  </div>`;
}

/* ---------------- boot ---------------- */
document.addEventListener("DOMContentLoaded", () => {
  setupChips("investors"); setupChips("competitors");
  $("#funds").addEventListener("input", lineCount);
  $("#sample").addEventListener("click", runSample);
  $("#sample-top").addEventListener("click", runSample);
  $("#pane-root").addEventListener("click", onPaneClick);
  $("#target").addEventListener("input", () => { if ($("#target-err").textContent) targetOk(); });
  $("#check-form").addEventListener("submit", (e) => { e.preventDefault(); (state.mode === "find" ? runFind : run)(); });
  $("#to-find").addEventListener("click", () => setMode(state.mode === "find" ? "list" : "find"));
  $("#nav-find").addEventListener("click", () => { setMode("find"); setScreen("paste"); go("/"); $("#region").focus(); });
  $("#side-edit").addEventListener("click", () => { setScreen("paste"); $("#opt").open = true; window.scrollTo(0, 0); $("#funds").focus(); });
  document.addEventListener("click", (e) => {
    if (e.target.closest("[data-edit]")) { closePane(); setScreen("paste"); window.scrollTo(0, 0); (state.mode === "find" ? $("#region") : $("#funds")).focus(); }
    if (e.target.closest("[data-edit-target]")) { setScreen("paste"); $("#target").focus(); $("#target").scrollIntoView({block: "center"}); }
    if (e.target.closest("[data-net-sample]")) { setNetwork(parseConnections(SAMPLE_NETWORK), "sample", true); announce("Made-up sample network loaded."); }
    if (e.target.closest("[data-net-clear]")) clearNetwork();
  });
  $("#net-sample").addEventListener("click", () => { setNetwork(parseConnections(SAMPLE_NETWORK), "sample", true); });
  $("#li-file").addEventListener("change", (e) => { readNetworkFile(e.target.files[0]); e.target.value = ""; });
  setupDrop($("#drop"));
  setupTips();
  window.addEventListener("beforeprint", landAll);
  $("#nav-tour").addEventListener("click", () => {
    if (location.pathname === "/method") go("/");
    tourOpen(document.body.dataset.screen === "results" && state.view ? 3 : 0);
  });
  init().then(async () => {
    await loadProof();
    if (location.hash === "#demo") $("#sample").click();
    else tourMaybeStart();
  });
});
