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
  window.__reopenIgnoredAfterOcc = window.__reopenIgnoredAfterOcc ?? false;

// Shared profile helpers (provided by /static/profile.js)
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

function parseISODateLocal(iso){
  // iso = "YYYY-MM-DD"
  const [y, m, d] = String(iso).split("-").map(Number);
  return new Date(y, (m || 1) - 1, d || 1); // local time
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

    const chips = grouped
      .slice(0, 3)
      .map(g => {
        const label = `${g.cat.toUpperCase()} • ${money(g.total)}`;
        const tip = `${g.cat} (${g.count}) — ${money(g.total)}`;
        return `<div class="cal-chip" title="${esc(tip)}">${esc(label)}</div>`;
      })
      .join("");

    const more = grouped.length > 3
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

function prettyLongDate(iso){
  // iso = "YYYY-MM-DD"
  if (!iso) return "";
  const d = parseISODateLocal(iso);
  return d.toLocaleDateString(undefined, {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric"
  });
}

function openCalDayModal(isoDate){
  const modal = document.getElementById("calDayModal");
  const title = document.getElementById("calDayTitle");
  const sub   = document.getElementById("calDaySub");
  const body  = document.getElementById("calDayBody");
  if (!modal || !title || !sub || !body) return;

  const evts = __calEventsByDate[isoDate] || [];
  if (!evts.length) return;

  title.textContent = prettyLongDate(isoDate);

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


function money(n){
  const x = Number(n || 0);
  return x.toLocaleString(undefined, { style:"currency", currency:"USD" });
}

function shortDateISO(iso){
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { month:"2-digit", day:"2-digit", year:"2-digit" });
}

function esc(s){
  return String(s ?? "")
    .replaceAll("&","&amp;")
    .replaceAll("<","&lt;")
    .replaceAll(">","&gt;")
    .replaceAll('"',"&quot;")
    .replaceAll("'","&#39;");
}

function merchantHTML(g){
    const m = (g.merchant_display || g.merchant || "").toUpperCase();

  const date = shortDateISO(g.last_seen);

  return `
    <div class="rec-merchant">
      <div>
        <div class="rec-merchant-name" title="${esc(m)}">${esc(m)}</div>
        <div class="rec-merchant-sub">${esc(date)}</div>
      </div>

      <div class="rec-merchant-actions">
        <button class="ignore-btn" onclick="mergeMerchantPrompt('${esc(g.merchant)}')">Merge</button>
        <button class="ignore-btn" onclick="ignoreMerchant('${esc(g.merchant)}')">Ignore</button>
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
  const freq = p.cadence || "irregular";
  const date = shortDateISO(p.last_seen);
  const occ  = `x${p.occurrences || 0}`;

  const merchant = p.merchant ?? __lastData[gIdx]?.merchant ?? "";
  const amount = p.amount;
  const accountId = p.account_id ?? -1; // optional if you include it from backend

  return `
    <div class="tx-row">
      <div class="tx-icon-wrap tx-icon-hit" role="button" tabindex="0"
           aria-label="Show transactions"
           onclick="event.stopPropagation(); openOccModal(${gIdx}, ${pIdx});">
        ${categoryIconHTML(patternCategory(p))}
      </div>

      <div class="tx-date">${esc(freq)}</div>

      <div class="tx-main">
        <div class="rec-sub">${esc(date)} • ${esc(occ)}</div>
        <div style="display:flex; gap:8px; margin-top:6px; flex-wrap:wrap;">
          <button class="ignore-btn" onclick="event.stopPropagation(); ignorePattern('${esc(merchant)}', ${Number(amount)}, ${Number(accountId)})">Ignore this</button>

          <select onchange="event.stopPropagation(); overrideCadence('${esc(merchant)}', ${Number(amount)}, this.value, ${Number(accountId)})">
            <option value="">Set cadence…</option>
            <option value="weekly">weekly</option>
            <option value="monthly">monthly</option>
            <option value="quarterly">quarterly</option>
            <option value="yearly">yearly</option>
            <option value="irregular">irregular</option>
          </select>
        </div>
      </div>

      <div class="tx-amt">${money(p.amount)}</div>
    </div>
  `;
}

function merchantHTMLIgnored(g){
  const m = (g.merchant_display || g.merchant || "").toUpperCase();
  const date = shortDateISO(g.last_seen);

  return `
    <div class="rec-merchant">
      <div>
        <div class="rec-merchant-name" title="${esc(m)}">${esc(m)}</div>
        <div class="rec-merchant-sub">${esc(date)}</div>
      </div>
      <div style="display:flex; gap:8px;">
        <button class="ignore-btn" onclick="mergeMerchantPrompt('${esc(g.merchant)}')">Merge</button>
        <button class="ignore-btn" onclick="unignoreMerchant('${esc(g.merchant)}')">Unignore</button>
      </div>
    </div>
  `;
}

function patternHTMLIgnored(gIdx, pIdx, p){
  const freq = p.cadence || "irregular";
  const date = shortDateISO(p.last_seen);
  const occ  = `x${p.occurrences || 0}`;

  const merchant = p.merchant ?? window.__ignoredData?.[gIdx]?.merchant ?? "";
  const amount = p.amount;
  const accountId = p.account_id ?? -1;

  return `
    <div class="tx-row">
      <div class="tx-icon-wrap tx-icon-hit" role="button" tabindex="0"
           aria-label="Show transactions"
           onclick="event.stopPropagation(); openOccFromIgnored(${gIdx}, ${pIdx});">
        ${categoryIconHTML(patternCategory(p))}
      </div>

      <div class="tx-date">${esc(freq)}</div>

      <div class="tx-main">
        <div class="rec-sub">${esc(date)} • ${esc(occ)}</div>
        <div style="display:flex; gap:8px; margin-top:6px; flex-wrap:wrap;">
          <button class="ignore-btn" onclick="event.stopPropagation(); ignorePattern('${esc(merchant)}', ${Number(amount)}, ${Number(accountId)})">Ignore this</button>

          <select onchange="event.stopPropagation(); overrideCadence('${esc(merchant)}', ${Number(amount)}, this.value, ${Number(accountId)})">
            <option value="">Set cadence…</option>
            <option value="weekly">weekly</option>
            <option value="monthly">monthly</option>
            <option value="quarterly">quarterly</option>
            <option value="yearly">yearly</option>
            <option value="irregular">irregular</option>
          </select>
        </div>
      </div>

      <div class="tx-amt">${money(p.amount)}</div>
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
    merchantHTML(g) + (g.patterns || []).map((p, pi) => patternHTML(gi, pi, p)).join("")
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
  sub.textContent = `${freq} • ${shortDateISO(p.last_seen)} • ${occ} • ${money(p.amount)}`;

  const tx = Array.isArray(p.tx) ? p.tx : [];
  body.innerHTML = tx.map(t => `
<div class="occ-tx">
  <div class="occ-left">
        <div class="occ-date">${esc(shortDateISO(t.date))}</div>
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


async function mergeMerchantPrompt(alias){
  const canonical = prompt(
    `Merge merchant:\n\n${alias}\n\nInto canonical merchant (type name exactly as shown):`
  );
  if (!canonical) return;

  await fetch(
    `/recurring/merchant-alias?alias=${encodeURIComponent(alias)}&canonical=${encodeURIComponent(canonical)}`,
    { method: "POST" }
  );

  loadRecurring();
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
    merchantHTMLIgnored(g) + (g.patterns || []).map((p, pi) => patternHTMLIgnored(gi, pi, p)).join("")
  )).join("");


  // store for modal drilldown
  window.__ignoredData = groups;
}

async function unignoreMerchant(name){
  await fetch(`/recurring/unignore/merchant?name=${encodeURIComponent(name)}`, { method: "POST" });
  await openIgnoredModal(); // refresh ignored list
  loadRecurring();          // refresh main list
}

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
