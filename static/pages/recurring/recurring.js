import { money } from "/static/shared/format.module.js";
import { parseISODateLocal, formatDateLong, formatMMDDYY } from "/static/shared/dates.module.js";

// --- calendar state (GLOBAL, REQUIRED) ---
const today = new Date();
window.__calYear  = today.getFullYear();
window.__calMonth = today.getMonth() + 1; // 1–12
window.__calEventsByDate = {};


if (window.__recurringPageLoaded) {
  console.warn("recurring_page.js loaded twice; skipping re-init");
} else {
  window.__recurringPageLoaded = true;

  window.__mainData = window.__mainData || [];
  window.__lastData = window.__lastData || [];
  window.__reopenIgnoredAfterOcc = window.__reopenIgnoredAfterOcc ?? false;

// Shared profile helpers (provided by /static/shared/profile.js)
function getProfile(){ return window.Profile?.get?.() || null; }
function setProfile(p){ return window.Profile?.set?.(p); }
function openProfile(){ return window.Profile?.open?.(); }
function closeProfile(){ return window.Profile?.close?.(); }
function bindProfileUI(){
  // profile.js auto-mounts the UI; we only hook refresh behavior here.
  window.Profile?.ensureUI?.();
  window.Profile?.onChange?.(() => {
    // Refresh month view with new profile
    loadCalendar();
  });
}

async function fetchPaychecks(year, month){
  const profile0 = getProfile();
  if (!profile0) return [];
    if (!profile0?.paygrade) {
      console.warn("LES profile missing paygrade; skipping paycheck calc.");
      return [];
}
  // Normalize a few fields so the backend always understands them
  const profile = {...profile0};
  if (profile.paygrade != null){
    profile.paygrade = String(profile.paygrade).toUpperCase().replace(/\s+/g,"").replace("E-","E").replace("-","");
  }
  if (profile.service_start != null){
    profile.service_start = String(profile.service_start);
  }
  if (profile.bah_override === "") profile.bah_override = null;

  const res = await fetch("/les/paychecks", {
    method: "POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify({year, month, profile})
  });

  if (!res.ok){
    const txt = await res.text().catch(()=> "");
    console.error("Paycheck calc failed:", res.status, txt);
    return [];
  }

  const data = await res.json().catch(()=>null);
  const events = Array.isArray(data?.events) ? data.events : [];
  return events;
}


function monthName(m){
  return ["January","February","March","April","May","June","July","August","September","October","November","December"][m-1] || "";
}

function isoYMD(d){
  const y = d.getFullYear();
  const m = String(d.getMonth()+1).padStart(2,"0");
  const day = String(d.getDate()).padStart(2,"0");
  return `${y}-${m}-${day}`;
}

function truncMerchant(s, n=16){
  const t = String(s || "").toUpperCase().trim();
  return t.length > n ? (t.slice(0,n-1) + "…") : t;
}

async function loadCalendar(){
  const grid = document.getElementById("calGrid");
  const title = document.getElementById("calTitle");
  if (!grid || !title) return;

  title.textContent = `${monthName(__calMonth)} ${__calYear}`;
  grid.innerHTML = `<div style="grid-column:1/-1; padding:10px; opacity:.7;">Loading…</div>`;

  const n = Number(document.getElementById("minOcc")?.value || 3);
  const includeStale = document.getElementById("includeStale")?.checked ? "true" : "false";

  const res = await fetch(`/recurring/calendar?year=${encodeURIComponent(__calYear)}&month=${encodeURIComponent(__calMonth)}&min_occ=${encodeURIComponent(n)}&include_stale=${includeStale}`);
  if (!res.ok){
    grid.innerHTML = `<div style="grid-column:1/-1; padding:10px; color:#b00;">Failed to load calendar.</div>`;
    return;
  }

  const data = await res.json();
  let events = Array.isArray(data?.events) ? data.events : [];

  // Add DFAS paycheck events based on profile + month being viewed
  const payEvents = await fetchPaychecks(__calYear, __calMonth);
  if (payEvents.length) events = events.concat(payEvents);


  // ---- Month totals (In/Out) ----
  let totalOut = 0;
  let totalIn = 0;

const monthKey = `${__calYear}-${String(__calMonth).padStart(2,"0")}`;

for (const e of events){
  const amt = Number(e.amount) || 0;

  // ✅ paychecks: only count if the TARGET payday is in this month
  if (e.cadence === "paycheck"){
    if (String(e.pay_target || "").startsWith(monthKey + "-")) {
      totalIn += amt;
    }
    continue;
  }

  // ✅ other income (interest, etc.)
  if (e.type === "income"){
    totalIn += amt;
    continue;
  }

  // ✅ expenses
  if (amt > 0) totalOut += amt;
}
const topOut = document.getElementById("calTopOut");
const topIn  = document.getElementById("calTopIn");

if (topOut) topOut.textContent = `Out: ${money(totalOut)}`;
if (topIn)  topIn.textContent  = `In: ${money(totalIn)}`;

  __calEventsByDate = {};
  for (const e of events){
    const key = e.date;
    (__calEventsByDate[key] ||= []).push(e);
  }

  renderCalendarGrid(__calYear, __calMonth);
}

function renderCalendarGrid(year, month){
  const grid = document.getElementById("calGrid");
  if (!grid) return;

  const first = new Date(year, month - 1, 1);
  const last  = new Date(year, month, 0); // last day of month

  // Start on the Sunday before (or on) the 1st
  const start = new Date(first);
  start.setDate(first.getDate() - first.getDay());

  // End on the Saturday after (or on) the last day
  const end = new Date(last);
  end.setDate(last.getDate() + (6 - last.getDay()));

  // Keep a “calendar looking” minimum of 5 rows (35 cells).
  // This prevents months like Feb-2026 (exact 4 weeks) from rendering only 4 rows,
  // while avoiding the “two extra weeks” effect from always forcing 6 rows.
  const MS_DAY = 24 * 60 * 60 * 1000;
  const daysBetweenInclusive = (a, b) => Math.round((b - a) / MS_DAY) + 1;

  while (daysBetweenInclusive(start, end) < 35){
    end.setDate(end.getDate() + 7);
  }

  const cells = [];
  for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)){
    const cellDate = new Date(d);
    const inMonth = cellDate.getMonth() === (month - 1);
    const dayNum = cellDate.getDate();

    const key = isoYMD(cellDate);
    const evts = __calEventsByDate[key] || [];

    const grouped = (() => {
      const byCat = {};
      for (const e of evts){
        const cat = (e.category || e.type || e.cat || "Unassigned");
        const amt = Number(e.amount || 0);
        if (!byCat[cat]) byCat[cat] = { cat, total: 0, count: 0 };
        byCat[cat].total += amt;
        byCat[cat].count += 1;
      }
      // sort by absolute total desc, then name
      return Object.values(byCat).sort((a,b)=> (Math.abs(b.total)-Math.abs(a.total)) || a.cat.localeCompare(b.cat));
    })();

    // After you compute `grouped`...

    const isMobile = window.matchMedia && window.matchMedia("(max-width: 900px)").matches;

    const topCats = grouped.slice(0, 3);

    const chips = isMobile
      ? `
        <div class="cal-icons" aria-hidden="true">
          ${topCats.map(g => {
            const tip = `${g.cat} (${g.count}) — ${money(g.total)}`;
            return `<span class="cal-ic" title="${esc(tip)}">${categoryIconHTML(g.cat)}</span>`;
          }).join("")}
        </div>
      `
      : topCats.map(g => {
          const label = `${g.cat.toUpperCase()} • ${money(g.total)}`;
          const tip = `${g.cat} (${g.count}) — ${money(g.total)}`;
          return `<div class="cal-chip" title="${esc(tip)}">${esc(label)}</div>`;
        }).join("");

    // Desktop only: keep the "+N more" chip
    const more = (!isMobile && grouped.length > 3)
      ? `<div class="cal-chip cal-chip--more">+${grouped.length - 3} more</div>`
      : "";

    const cls = `cal-day${inMonth ? "" : " is-out"}`;

    // Click only if in current month AND has events
    const click = (inMonth && evts.length)
      ? `onclick="openCalDayModal('${key}')"`
      : "";

    cells.push(`
      <div class="${cls}" ${click}>
        <div class="cal-daynum">${dayNum}</div>
        ${chips}
        ${more}
      </div>
    `);
  }

  grid.innerHTML = cells.join("");
}

function openCalDayModal(isoDate){
  const modal = document.getElementById("calDayModal");
  const title = document.getElementById("calDayTitle");
  const sub   = document.getElementById("calDaySub");
  const body  = document.getElementById("calDayBody");
  if (!modal || !title || !sub || !body) return;

  const evts = __calEventsByDate[isoDate] || [];
  if (!evts.length) return;

  title.textContent = formatDateLong(isoDate);

  const total = evts.reduce((a,e)=>a+Number(e.amount||0),0);
  sub.textContent = `${evts.length} expected • Total ${money(total)}`;

  // Group by category, but show merchant rows inside each group
  const byCat = {};
  for (const e of evts){
    const cat = (e.category || e.type || e.cat || "Unassigned");
    if (!byCat[cat]) byCat[cat] = { cat, total: 0, count: 0, items: [] };
    byCat[cat].total += Number(e.amount || 0);
    byCat[cat].count += 1;
    byCat[cat].items.push(e);
  }

  const groups = Object.values(byCat).sort((a,b)=>
    (Math.abs(b.total)-Math.abs(a.total)) || a.cat.localeCompare(b.cat)
  );

  const itemRow = (e) => {
    const merch = (e.merchant_display || e.merchant || "").trim() || "Unknown";
    const cat = (e.category || e.category_label || "Unassigned");
    const cadence = (e.cadence || "").trim();
    return `
      <div class="occ-tx occ-tx--sub">
        <div class="occ-left">
          <div class="occ-merchant">${esc(merch.toUpperCase())}</div>
          <div class="occ-meta">${esc(cat)}${cadence ? " • " + esc(cadence) : ""}</div>
        </div>
        <div class="occ-amt">${money(Number(e.amount||0))}</div>
      </div>
    `;
  };

  body.innerHTML = groups.map(g => {
    const items = (g.items || []).slice().sort((a,b)=>Math.abs(Number(b.amount||0))-Math.abs(Number(a.amount||0)));
    return `
      <div class="occ-group">
        <div class="occ-tx">
          <div class="occ-left">
            <div class="occ-merchant">${esc(g.cat.toUpperCase())}</div>
            <div class="occ-meta">${esc(String(g.count))} item${g.count===1?"":"s"}</div>
          </div>
          <div class="occ-amt">${money(g.total)}</div>
        </div>
        <div class="occ-sublist">
          ${items.map(itemRow).join("")}
        </div>
      </div>
    `;
  }).join("");

  modal.classList.remove("hidden");
}

function closeCalDayModal(){
  document.getElementById("calDayModal")?.classList.add("hidden");
}


function esc(s){
  return String(s ?? "")
    .replaceAll("&","&amp;")
    .replaceAll("<","&lt;")
    .replaceAll(">","&gt;")
    .replaceAll('"',"&quot;")
    .replaceAll("'","&#39;");
}

function merchantHTML(g, gi){
  const m = (g.merchant_display || g.merchant || "").toUpperCase();
  const date = formatMMDDYY(g.last_seen);

  return `
    <div class="rec-head">
      <button class="rec-toggle" type="button" data-gi="${gi}" aria-expanded="true">
        <span class="rec-caret">▾</span>
      </button>

      <div class="rec-head-main">
        <button class="rec-merchant-name" type="button" data-full="${esc(m)}">${esc(m)}</button>
        <div class="rec-merchant-sub">${esc(date)}</div>
      </div>

      <div class="rec-merchant-actions">
        <button class="pill-btn" type="button" onclick="mergeMerchantPrompt('${esc(g.merchant)}')">Merge</button>
        <button class="pill-btn" type="button" onclick="ignoreMerchant('${esc(g.merchant)}')">Ignore</button>
      </div>
    </div>
  `;
}

function patternCategory(p){
  const tx = Array.isArray(p?.tx) ? p.tx : [];
  // Prefer the most recent tx's category
  for (let i = tx.length - 1; i >= 0; i--){
    const c = (tx[i]?.category || "").trim();
    if (c) return c;
  }
  // Fallback: first non-empty
  for (let i = 0; i < tx.length; i++){
    const c = (tx[i]?.category || "").trim();
    if (c) return c;
  }
  return "";
}

function patternHTML(gIdx, pIdx, p){
  const freq = (p.cadence || "irregular").toLowerCase();
  const date = formatMMDDYY(p.last_seen);
  const occ  = `x${p.occurrences || 0}`;

  const merchant = p.merchant ?? __lastData[gIdx]?.merchant ?? "";
  const amount = Number(p.amount || 0);
  const accountId = p.account_id ?? -1;

  return `
    <div class="rec-item">
      <div class="tx-icon-wrap tx-icon-hit" role="button" tabindex="0"
           aria-label="Show transactions"
           onclick="event.stopPropagation(); openOccModal(${gIdx}, ${pIdx});">
        ${categoryIconHTML(patternCategory(p))}
      </div>

      <div class="rec-mid">
        <div class="rec-freq">${esc(freq)}</div>
        <div class="rec-meta">${esc(date)} • ${esc(occ)}</div>
      </div>

      <div class="rec-right">
        <button class="pill-btn pill-btn--sub"
          onclick="event.stopPropagation(); ignorePattern('${esc(merchant)}', ${amount}, ${Number(accountId)})">
          Ignore
        </button>
        <div class="rec-amt">${money(amount)}</div>
      </div>
    </div>
  `;
}

function merchantHTMLIgnored(g, gi){
  const m = (g.merchant_display || g.merchant || "").toUpperCase();
  const date = formatMMDDYY(g.last_seen);

  return `
    <div class="rec-head">
      <button class="rec-toggle" type="button" data-gi="${gi}" aria-expanded="true">
        <span class="rec-caret">▾</span>
      </button>

      <div class="rec-head-main">
        <button class="rec-merchant-name" type="button" data-full="${esc(m)}">${esc(m)}</button>
        <div class="rec-merchant-sub">${esc(date)}</div>
      </div>

      <div class="rec-merchant-actions">
        <button class="pill-btn" type="button" onclick="mergeMerchantPrompt('${esc(g.merchant)}')">Merge</button>
        <button class="pill-btn" type="button"
  onclick="unignoreMerchant('${esc(g.merchant)}')">Unignore</button>

      </div>
    </div>
  `;
}

function patternHTMLIgnored(gIdx, pIdx, p){
  const freq = (p.cadence || "irregular").toLowerCase();
  const date = formatMMDDYY(p.last_seen);
  const occ  = `x${p.occurrences || 0}`;

  const merchant = p.merchant ?? __lastData[gIdx]?.merchant ?? "";
  const amount = Number(p.amount || 0);
  const accountId = p.account_id ?? -1;

  return `
    <div class="rec-item">
      <div class="tx-icon-wrap tx-icon-hit" role="button" tabindex="0"
           aria-label="Show transactions"
           onclick="event.stopPropagation(); openOccModal(${gIdx}, ${pIdx});">
        ${categoryIconHTML(patternCategory(p))}
      </div>

      <div class="rec-mid">
        <div class="rec-freq">${esc(freq)}</div>
        <div class="rec-meta">${esc(date)} • ${esc(occ)}</div>
      </div>

      <div class="rec-right">
        <button class="pill-btn pill-btn--sub"
          onclick="event.stopPropagation(); ignorePattern('${esc(merchant)}', ${amount}, ${Number(accountId)})">
          Ignore
        </button>
        <div class="rec-amt">${money(amount)}</div>
      </div>
    </div>
  `;
}

async function loadRecurring(){
  const list = document.getElementById("recurringList");
  const minOcc = document.getElementById("minOcc");
  const includeStale = document.getElementById("includeStale")?.checked ? "true" : "false";

  if (!list) return;

  list.innerHTML = `<div style="padding:12px; opacity:.7;">Loading…</div>`;

  const n = Number(minOcc?.value || 3);
  const res = await fetch(`/recurring?min_occ=${encodeURIComponent(n)}&include_stale=${includeStale}`);

  if (!res.ok){
    list.innerHTML = `<div style="padding:12px; color:#b00;">Failed to load (/recurring)</div>`;
    return;
  }

  const data = await res.json();
  __lastData = Array.isArray(data) ? data : [];
  __mainData = __lastData;


  if (!__lastData.length){
    list.innerHTML = `<div style="padding:12px; opacity:.7;">No recurring items found.</div>`;
    return;
  }

list.innerHTML = __lastData.map((g, gi) => (
  `<div class="rec-card" data-gi="${gi}">
     ${merchantHTML(g, gi)}
     <div class="rec-body">
       ${(g.patterns || []).map((p, pi) => patternHTML(gi, pi, p)).join("")}
     </div>
   </div>`
)).join("");


}

async function ignoreMerchant(name){
  await fetch(`/recurring/ignore/merchant?name=${encodeURIComponent(name)}`, { method: "POST" });
  loadRecurring();
}

/* ---------- Modal ---------- */

function openOccModal(groupIndex, patternIndex){
  const g = __lastData[groupIndex];
  const p = g?.patterns?.[patternIndex];
  if (!g || !p) return;

  const modal = document.getElementById("occModal");
  const title = document.getElementById("occTitle");
  const sub   = document.getElementById("occSub");
  const body  = document.getElementById("occBody");

  const merch = p?.transfer_display ? String(p.transfer_display) : (g.merchant || "").toUpperCase();
  const freq  = p.cadence || "irregular";
  const occ   = `x${p.occurrences || 0}`;

  title.textContent = merch;
  sub.textContent = `${freq} • ${formatMMDDYY(p.last_seen)} • ${occ} • ${money(p.amount)}`;

  const tx = Array.isArray(p.tx) ? p.tx : [];
  body.innerHTML = tx.map(t => `
<div class="occ-tx">
  <div class="occ-left">
        <div class="occ-date">${esc(formatMMDDYY(t.date))}</div>
        <div class="occ-merchant">${esc((t.merchant_display ? String(t.merchant_display) : (t.merchant || "").toUpperCase()))}</div>
        <div class="occ-meta">${esc(t.category || "")}${t.account_id ? " • acct " + esc(t.account_id) : ""}</div>
      </div>
  <div class="occ-amt">${money(t.amount)}</div>
</div>
  `).join("") || `<div style="opacity:.7; padding:8px 0;">No transactions found.</div>`;

  modal.classList.remove("hidden");
}

function openOccFromIgnored(groupIndex, patternIndex){
  if (Array.isArray(window.__ignoredData)) {
    __reopenIgnoredAfterOcc = true;
    closeIgnoredModal();
    __lastData = window.__ignoredData;
    openOccModal(groupIndex, patternIndex);
  }
}


function closeOccModal(){
  document.getElementById("occModal")?.classList.add("hidden");

  if (__reopenIgnoredAfterOcc){
    __reopenIgnoredAfterOcc = false;
    openIgnoredModal(); // re-open the ignored modal after closing details
  }
}


document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    closeOccModal();
    closeIgnoredModal();
  }
});

async function ignorePattern(merchant, amount, accountId){
  await fetch(`/recurring/ignore/pattern?merchant=${encodeURIComponent(merchant)}&amount=${encodeURIComponent(amount)}&account_id=${encodeURIComponent(accountId ?? -1)}`, {
    method: "POST"
  });
  loadRecurring();
}

async function overrideCadence(merchant, amount, cadence, accountId){
  await fetch(`/recurring/override-cadence?merchant=${encodeURIComponent(merchant)}&amount=${encodeURIComponent(amount)}&cadence=${encodeURIComponent(cadence)}&account_id=${encodeURIComponent(accountId ?? -1)}`, {
    method: "POST"
  });
  loadRecurring();
}

document.getElementById("reloadRecurring")?.addEventListener("click", () => {
  loadRecurring();
  loadCalendar();
});

document.getElementById("includeStale")?.addEventListener("change", () => {
  loadRecurring();
  loadCalendar();
});


const __mergeState = {
  alias: "",
  selectedKeys: new Set(),
  choices: [],
};

function _normMerchantLabel(s){
  return String(s || "").trim().toUpperCase();
}

function _patternMergeKey(p){
  const cadence = String(p?.cadence || "").trim().toLowerCase();
  const amt = Number(p?.amount || 0);
  const sign = amt >= 0 ? 1 : -1;
  const bucket = Math.round(Math.abs(amt) * 100) / 100;
  const accountId = Number(p?.account_id ?? -1);
  let day = 0;
  try {
    const ls = String(p?.last_seen || "");
    if (ls) day = parseISODateLocal(ls).getDate();
  } catch {}
  return `${cadence}|${bucket.toFixed(2)}|${sign}|${accountId}|${day}`;
}

function _findMerchantGroup(alias){
  const target = String(alias || "").trim().toUpperCase();
  if (!target) return null;
  const pools = [window.__mainData, window.__lastData, window.__ignoredData];
  for (const p of pools) {
    const rows = Array.isArray(p) ? p : [];
    const hit = rows.find((g) => String(g?.merchant || "").trim().toUpperCase() === target);
    if (hit) return hit;
  }
  return null;
}

function _collectMergeChoices(alias){
  const g = _findMerchantGroup(alias);
  const patterns = Array.isArray(g?.patterns) ? g.patterns : [];
  const counts = new Map();
  const rows = patterns
    .map((p, idx) => {
      const cadence = String(p?.cadence || "").trim().toLowerCase();
      if (!cadence || cadence === "irregular" || cadence === "unknown") return null;
      const key = _patternMergeKey(p);
      counts.set(cadence, (counts.get(cadence) || 0) + 1);
      return {
        idx,
        key,
        cadence,
        amount: Number(p?.amount || 0),
        last: formatMMDDYY(p?.last_seen || ""),
        occ: Number(p?.occurrences || 0),
        accountId: Number(p?.account_id ?? -1),
      };
    })
    .filter(Boolean);
  const dupCadences = new Set(Array.from(counts.entries()).filter(([, n]) => n > 1).map(([c]) => c));
  return rows.filter((x) => dupCadences.has(x.cadence));
}

function ensureMergeModal(){
  if (document.getElementById("mergeModal")) return;

  const root = document.createElement("div");
  root.id = "mergeModal";
  root.className = "occ-modal hidden";
  root.innerHTML = `
    <div class="occ-backdrop" data-merge-close></div>
    <div class="occ-card" role="dialog" aria-modal="true" aria-label="Merge recurring patterns">
      <div class="occ-head">
        <div>
          <div class="occ-title">Merge recurring patterns</div>
          <div class="occ-sub" id="mergeAliasSub"></div>
        </div>
        <button class="occ-close" data-merge-close>&#10005;</button>
      </div>
      <div class="occ-body">
        <div id="mergeChoices" class="merge-choices"></div>
        <div class="merge-actions">
          <button id="mergeCancelBtn" type="button">Cancel</button>
          <button id="mergeConfirmBtn" type="button">Merge</button>
        </div>
        <div id="mergeStatus" class="merge-status" aria-live="polite"></div>
      </div>
    </div>
  `;
  document.body.appendChild(root);

  const close = () => closeMergeModal();
  root.querySelectorAll("[data-merge-close]").forEach((el) => el.addEventListener("click", close));
  root.querySelector("#mergeCancelBtn")?.addEventListener("click", close);

  root.querySelector("#mergeConfirmBtn")?.addEventListener("click", submitMergeSelection);
}

function closeMergeModal(){
  document.getElementById("mergeModal")?.classList.add("hidden");
}

function renderMergeChoices(){
  const root = document.getElementById("mergeModal");
  if (!root) return;
  const list = root.querySelector("#mergeChoices");
  if (!__mergeState.choices.length) {
    list.innerHTML = `<div style="opacity:.7; padding:8px 0;">No duplicate recurring patterns found for this merchant.</div>`;
    root.querySelector("#mergeConfirmBtn").disabled = true;
    return;
  }

  list.innerHTML = __mergeState.choices.map((x, idx) => {
    const id = `mergeChoice_${idx}_${esc(x.key)}`;
    const checked = __mergeState.selectedKeys.has(x.key) ? "checked" : "";
    return `
      <label class="merge-choice" for="${id}">
        <input id="${id}" type="checkbox" name="mergeChoice" value="${esc(x.key)}" ${checked}>
        <span class="merge-choice__label">${esc(x.cadence)} · ${money(x.amount)} · ${esc(x.last)}</span>
        <div class="merge-choice__sub">occurrences: ${x.occ} · account: ${x.accountId}</div>
      </label>
    `;
  }).join("");

  list.querySelectorAll('input[name="mergeChoice"]').forEach((el) => {
    el.addEventListener("change", (ev) => {
      const key = String(ev.target?.value || "");
      if (!key) return;
      if (ev.target?.checked) __mergeState.selectedKeys.add(key);
      else __mergeState.selectedKeys.delete(key);
      root.querySelector("#mergeConfirmBtn").disabled = __mergeState.selectedKeys.size < 2;
    });
  });

  root.querySelector("#mergeConfirmBtn").disabled = __mergeState.selectedKeys.size < 2;
}

async function submitMergeSelection(){
  const root = document.getElementById("mergeModal");
  if (!root) return;
  const status = root.querySelector("#mergeStatus");
  const btn = root.querySelector("#mergeConfirmBtn");
  const keys = Array.from(__mergeState.selectedKeys);
  const alias = String(__mergeState.alias || "").trim();

  if (!alias || keys.length < 2) {
    if (status) status.textContent = "Select at least 2 patterns to merge.";
    return;
  }

  const selectedRows = __mergeState.choices.filter((x) => __mergeState.selectedKeys.has(x.key));
  const cadenceSet = new Set(selectedRows.map((x) => x.cadence));
  if (cadenceSet.size > 1) {
    if (status) status.textContent = "Selected patterns must have the same cadence.";
    return;
  }

  btn.disabled = true;
  if (status) status.textContent = "Merging...";
  try {
    const res = await fetch(`/recurring/merge-patterns-selected`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ merchant: alias, pattern_keys: keys }),
    });
    const out = await res.json().catch(() => ({}));
    if (!res.ok || out?.ok === false) {
      throw new Error(out?.error || `HTTP ${res.status}`);
    }
    closeMergeModal();
    await loadRecurring();
    await loadCalendar();
  } catch (err) {
    if (status) status.textContent = `Merge failed: ${err?.message || err}`;
    btn.disabled = false;
  }
}

function mergeMerchantPrompt(alias){
  ensureMergeModal();
  const root = document.getElementById("mergeModal");
  if (!root) return;

  __mergeState.alias = String(alias || "").trim();
  __mergeState.choices = _collectMergeChoices(__mergeState.alias);
  __mergeState.selectedKeys = new Set();

  const sub = root.querySelector("#mergeAliasSub");
  if (sub) sub.textContent = `Merchant: ${_normMerchantLabel(__mergeState.alias)}`;
  const status = root.querySelector("#mergeStatus");
  if (status) status.textContent = "";

  root.classList.remove("hidden");
  renderMergeChoices();
}

function closeIgnoredModal(){
  document.getElementById("ignoredModal")?.classList.add("hidden");
}

async function openIgnoredModal(){
  const modal = document.getElementById("ignoredModal");
  const body  = document.getElementById("ignoredBody");
  if (!modal || !body) return;

  body.innerHTML = `<div style="opacity:.7; padding:8px 0;">Loading…</div>`;
  modal.classList.remove("hidden");

  const n = Number(document.getElementById("minOcc")?.value || 3);
  const includeStale = document.getElementById("includeStale")?.checked ? "true" : "false";

  const res = await fetch(`/recurring/ignored-preview?min_occ=${encodeURIComponent(n)}&include_stale=${includeStale}`);
  if (!res.ok){
    body.innerHTML = `<div style="color:#b00;">Failed to load ignored preview.</div>`;
    return;
  }

  const data = await res.json();
  const groups = Array.isArray(data) ? data : [];

  if (!groups.length){
    body.innerHTML = `<div style="opacity:.7; padding:8px 0;">No ignored merchants (or none match min occurrences).</div>`;
    return;
  }

    // store for modal drilldown
  window.__ignoredData = groups;

  body.innerHTML = groups.map((g, gi) => (
  `<div class="rec-group">` +
    merchantHTMLIgnored(g) +
    (g.patterns || []).map((p, pi) => patternHTMLIgnored(gi, pi, p)).join("") +
  `</div>`
)).join("");



  // store for modal drilldown
  window.__ignoredData = groups;
}

async function unignoreMerchant(name){
  await fetch(`/recurring/unignore/merchant?name=${encodeURIComponent(name)}`, { method: "POST" });
  await openIgnoredModal(); // refresh ignored list
  loadRecurring();          // refresh main list
}

window.ignoreMerchant = ignoreMerchant;
window.unignoreMerchant = unignoreMerchant;
window.ignorePattern = ignorePattern;
window.mergeMerchantPrompt = mergeMerchantPrompt;
window.openCalDayModal = openCalDayModal;
window.closeCalDayModal = closeCalDayModal;
window.openOccModal = openOccModal;
window.closeOccModal = closeOccModal;
window.closeIgnoredModal = closeIgnoredModal;

document.getElementById("reviewIgnored")?.addEventListener("click", openIgnoredModal);

document.getElementById("calPrev")?.addEventListener("click", () => {
  __calMonth -= 1;
  if (__calMonth < 1){ __calMonth = 12; __calYear -= 1; }
  loadCalendar();
});

document.getElementById("calNext")?.addEventListener("click", () => {
  __calMonth += 1;
  if (__calMonth > 12){ __calMonth = 1; __calYear += 1; }
  loadCalendar();
});

  document.addEventListener("DOMContentLoaded", () => {
    bindProfileUI();
    loadRecurring();
    loadCalendar();
  });
}
(function setupNameBubble(){
  if (window.__nameBubbleSetup) return;
  window.__nameBubbleSetup = true;

  let bubble = null;
  let hideTimer = null;

  function ensureBubble(){
    if (bubble) return bubble;
    bubble = document.createElement("div");
    bubble.className = "name-bubble";
    document.body.appendChild(bubble);
    return bubble;
  }

  function hideBubble(){
    if (!bubble) return;
    bubble.classList.remove("is-on");
  }

  function showBubbleOver(el, text){
    const b = ensureBubble();
    b.textContent = text;

    // position centered above the tapped element
    const r = el.getBoundingClientRect();
    const x = r.left + r.width / 2;
    const y = Math.max(10, r.top - 8); // above it

    b.style.left = `${x}px`;
    b.style.top  = `${y}px`;

    // show
    b.classList.add("is-on");

    // auto-hide
    clearTimeout(hideTimer);
    hideTimer = setTimeout(hideBubble, 1400);
  }

  // tap merchant name => bubble
    function handleNameTap(e){
  const el = e.target.closest?.(".rec-merchant-name");
  if (!el) return;
  if (!window.matchMedia("(max-width: 900px)").matches) return;

  e.stopPropagation?.();

  const full = (el.dataset.full || el.getAttribute("title") || el.textContent || "").trim();
  if (full) showBubbleOver(el, full);
}

// strongest reliability on real phones
document.addEventListener("pointerdown", handleNameTap, { capture: true });

  // hide bubble if user scrolls
  window.addEventListener("scroll", hideBubble, { passive: true });
})();
document.addEventListener("click", (e) => {
  const btn = e.target.closest?.(".rec-toggle");
  if (!btn) return;

  const card = btn.closest(".rec-card");
  if (!card) return;

  const collapsed = card.classList.toggle("is-collapsed");
  btn.setAttribute("aria-expanded", collapsed ? "false" : "true");

  const caret = btn.querySelector(".rec-caret");
  if (caret) caret.textContent = collapsed ? "▸" : "▾";
});


