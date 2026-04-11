import { money } from "/static/shared/format.module.js";
import { isoLocal, parseISODateLocal, shortDate, formatMMDD, formatWeekdayShort } from "/static/shared/dates.module.js";
import { mountUpcomingCard } from "/static/components/cards/upcomingCard.js";

let chart = null;
let accountId = null;
const TX_MODE = window.TX_MODE || "prod";
let latestAccountRows = [];
let pendingBalanceMultiplier = -1;


const ACCOUNT_CHART_IDS = {
  title: "aChartTitle",
  dots: "aChartDots",
  toggle: "aChartToggle", // will be hidden on this page
  breakLabel: "aBreakLabel",
  breakValue: "aBreakValue",
  growthLabel: "aGrowthLabel",
  growthValue: "aGrowthValue",
  quarters: "aQuarterButtons",
  yearBack: "a-yearBack",
  yearLabel: "aYearLabel",
  yearFwd: "a-yearFwd",
  update: "a-update",
  start: "a-start",
  end: "a-end",
  canvas: "accountChart",
  monthSelect: "aMonthSelect",
  monthSelectWrap: "aSelectWrap",
  monthButtons: "aButtons",
};


function qs(name){
  return new URLSearchParams(window.location.search).get(name);
}

function parseNum(x) {
  if (x == null) return null;
  const s = String(x).trim();
  if (!s) return null;
  const v = Number(s.replace(/[^0-9.\-]/g, ""));
  return Number.isFinite(v) ? v : null;
}

function isoTodayLocal() {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

async function initAccountSwitcher(currentAccountId){
  const topTitle = await waitForTopBarTitle();
  if (!topTitle) return;

  topTitle.classList.add("account-title-switcher");
  topTitle.textContent = "";

  const sel = document.createElement("select");
  sel.id = "accountSwitchSelect";
  sel.className = "account-title-switcher__select";
  sel.setAttribute("aria-label", "Switch account");
  topTitle.appendChild(sel);

  sel.innerHTML = `<option value="">Loading accounts...</option>`;
  sel.disabled = true;

  try {
    const res = await fetch("/bank-info", { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const payload = await res.json();

    const fromAccounts = Array.isArray(payload?.accounts)
      ? payload.accounts.map(a => ({
          id: Number(a.account_id),
          label: `${a.bank || ""} - ${a.name || ""}`.trim(),
          group: "Accounts",
        }))
      : [];

    const fromCards = Array.isArray(payload?.credit_cards)
      ? payload.credit_cards.map(c => ({
          id: Number(c.card_id),
          label: `${c.bank || ""} - ${c.name || ""}`.trim(),
          group: "Cards",
        }))
      : [];

    const items = [...fromAccounts, ...fromCards]
      .filter(x => Number.isFinite(x.id) && x.id > 0)
      .sort((a, b) => a.label.localeCompare(b.label));

    if (!items.length) {
      sel.innerHTML = `<option value="">No accounts found</option>`;
      sel.disabled = true;
      return;
    }

    const groups = new Map();
    for (const it of items) {
      if (!groups.has(it.group)) groups.set(it.group, []);
      groups.get(it.group).push(it);
    }

    sel.innerHTML = "";
    for (const [groupName, groupItems] of groups.entries()) {
      const og = document.createElement("optgroup");
      og.label = groupName;
      for (const it of groupItems) {
        const opt = document.createElement("option");
        opt.value = String(it.id);
        opt.textContent = it.label || `Account ${it.id}`;
        if (Number(it.id) === Number(currentAccountId)) opt.selected = true;
        og.appendChild(opt);
      }
      sel.appendChild(og);
    }

    sel.disabled = false;
    sel.addEventListener("change", () => {
      const next = Number(sel.value || 0);
      if (!next || next === Number(currentAccountId)) return;
      window.location.href = `/account?account_id=${encodeURIComponent(String(next))}`;
    });
  } catch (err) {
    console.error("account switcher load failed:", err);
    sel.innerHTML = `<option value="">Account switch unavailable</option>`;
    sel.disabled = true;
  }
}

function waitForTopBarTitle(timeoutMs = 2500){
  return new Promise((resolve) => {
    const started = Date.now();
    const tick = () => {
      const el = document.getElementById("topBarTitle");
      if (el) return resolve(el);
      if (Date.now() - started > timeoutMs) return resolve(null);
      setTimeout(tick, 50);
    };
    tick();
  });
}

function escHtml(s){
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function parseAnyDateToMs(x) {
  if (!x) return 0;
  const s = String(x);

  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return parseISODateLocal(s).getTime();

  if (s.includes("/")) {
    const parts = s.split("/");
    const mm = Number(parts[0] || 1) - 1;
    const dd = Number(parts[1] || 1);
    let yy = Number(parts[2] || 1970);
    if (yy < 100) yy += 2000;
    return new Date(yy, mm, dd).getTime();
  }

  return 0;
}

function firstDayOfMonth(y,m){ return new Date(y,m,1); }
function lastDayOfMonth(y,m){ return new Date(y,m+1,0); }

let showPotentialGrowth = (localStorage.getItem("showPotentialGrowth") === "true");
let endBeforePotential = null;

function endOfCurrentMonthISO() {
  const t = new Date();
  const last = new Date(t.getFullYear(), t.getMonth() + 1, 0);
  return isoLocal(last);
}

function sameMonthISO(aIso, bIso) {
  return String(aIso).slice(0, 7) === String(bIso).slice(0, 7);
}

async function loadAccountHeader(accountId){
  if (TX_MODE === "test") return;

  const res = await fetch(`/account/${accountId}`);
  const a = await res.json();

  // Keep breakdown label contextual while chart title is removed on account page.
  const breakLabel = document.getElementById(ACCOUNT_CHART_IDS.breakLabel);
  if (breakLabel) breakLabel.textContent = a.accountType || "Balance";
}

async function loadAccountChart(accountId){
  const start = document.getElementById("a-start").value;
  const end   = document.getElementById("a-end").value;
  if (!start || !end) return;

  const seriesUrl = TX_MODE === "test" ? "/transactions-test-series" : "/account-series";
  const res = await fetch(`${seriesUrl}?account_id=${accountId}&start=${start}&end=${end}`);
  const data = await res.json();

  const labels = data.map(d => formatMMDD(d.date));
  const values = data.map(d => Number(d.value));
  const last = values.length ? values[values.length - 1] : 0;

  // --- Potential growth projection (Account page, current month only) ---
  let potentialSeries = null;
  let potentialEOM = null;

  if (showPotentialGrowth) {
    const today = new Date();
    const todayIso = isoLocal(today);

    // Only project for current month (and when the selected end is in current month)
    if (sameMonthISO(todayIso, end)) {
      const y = today.getFullYear();
      const m = today.getMonth() + 1;

      // match recurring page defaults
      const minOcc = 3;
      const includeStale = "false";

      const calRes = await fetch(
        `/recurring/calendar?year=${encodeURIComponent(y)}&month=${encodeURIComponent(m)}&min_occ=${encodeURIComponent(minOcc)}&include_stale=${includeStale}`
      );

      const calJson = calRes.ok ? await calRes.json() : { events: [] };
      let events = Array.isArray(calJson?.events) ? calJson.events : [];

      // ✅ If calendar events include account_id, filter to this account
      // (If not provided, we keep them all so paychecks still work if your backend doesn’t tag them yet.)
      // ✅ Always filter for this specific account.
// (If backend marks unknown/multi-account as -1, exclude those here.)
events = events.filter(e => Number(e.account_id) === Number(accountId));


      // Build delta map for remaining days
      const deltaByDate = {}; // { "YYYY-MM-DD": number }
      for (const e of events) {
        const d = String(e.date || "");
        if (!d) continue;
        if (d <= todayIso) continue; // only future days

        const amt = Number(e.amount) || 0;

        // Income rules:
        // - paychecks show cadence="paycheck"
        // - other income: type="income"
        const isIncome =
          (String(e.type || "").toLowerCase() === "income") ||
          (String(e.cadence || "") === "paycheck");

        const delta = isIncome ? amt : -Math.abs(amt);
        deltaByDate[d] = (deltaByDate[d] || 0) + delta;
      }

      // Align to your account series dates
      const idxToday = data.findIndex(p => String(p.date) === todayIso);
      if (idxToday >= 0) {
        potentialSeries = new Array(data.length).fill(null);

        let running = Number(data[idxToday]?.value || 0);
        potentialSeries[idxToday] = running;

        for (let i = idxToday + 1; i < data.length; i++) {
          const d = String(data[i]?.date || "");
          running += Number(deltaByDate[d] || 0);
          potentialSeries[i] = running;
        }

        potentialEOM = running;
      }
    }
  }

  // % Growth (use potentialEOM when toggle is on)
  let growthStr = "—";
  if (values.length >= 2 && Math.abs(values[0]) > 1e-9) {
    const startVal = Number(values[0] || 0);
    const endValActual = Number(values[values.length - 1] || 0);
    const endValForGrowth =
      (showPotentialGrowth && typeof potentialEOM === "number") ? Number(potentialEOM) : endValActual;

    const pct = ((endValForGrowth - startVal) / Math.abs(startVal)) * 100;
    growthStr = (pct > 0 ? "+" : "") + pct.toFixed(2) + "%";
  }
  setInlineGrowthByIds(ACCOUNT_CHART_IDS, "% Growth", growthStr);

  // Inline breakdown
  const l = document.getElementById(ACCOUNT_CHART_IDS.breakLabel);
  const v = document.getElementById(ACCOUNT_CHART_IDS.breakValue);
  if (l) l.textContent = l.textContent || "Balance";
  if (v) v.textContent = money(last);

  const ctx = document.getElementById("accountChart").getContext("2d");
  if (chart) chart.destroy();

  const datasets = (() => {
    const base = { label: "Balance", data: values, tension: 0.2, pointRadius: 0, pointHitRadius: 12, pointHoverRadius: 4 };
    if (showPotentialGrowth && Array.isArray(potentialSeries)) {
      return [
        base,
        {
          label: "Projected",
          data: potentialSeries,
          tension: 0.2,
          pointRadius: 0,
          pointHitRadius: 10,
          pointHoverRadius: 3,
          borderWidth: 2,
          borderDash: [6, 5],
          fill: false
        }
      ];
    }
    return [base];
  })();

  chart = new Chart(ctx, {
    type: "line",
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      devicePixelRatio: window.devicePixelRatio || 1,
      plugins: { legend: { display: false } },
      interaction: { mode:"index", intersect:false },
      scales: { y: { ticks: { callback: v => v.toLocaleString() } } }
    }
  });
}

async function loadAccountTransactions(accountId){
  const start = document.getElementById("a-start").value;
  const end   = document.getElementById("a-end").value;
  if (!start || !end) return;

  const baseUrl =
    TX_MODE === "test"
      ? "/transactions-test-range"
      : "/account-transactions-range";

  const res = await fetch(
    `${baseUrl}?account_id=${accountId}&start=${start}&end=${end}&limit=500`,
    { cache: "no-store" }
  );

  const list = document.getElementById("txList");
  if (!list) return;

  if (!res.ok) {
    console.error("account-transactions-range failed:", res.status);
    list.innerHTML = `<div style="padding:10px;">Failed to load (${res.status}).</div>`;
    return;
  }

  const payload = await res.json(); // ✅ only once
  const data = payload.transactions || [];
  latestAccountRows = Array.isArray(data) ? data : [];
  const mult = Number(payload?.pending_balance_multiplier);
  pendingBalanceMultiplier = Number.isFinite(mult) ? mult : -1;

  list.innerHTML = "";

  if (!Array.isArray(data) || data.length === 0) {
    list.innerHTML = `<div style="padding:10px;">No transactions found in this range.</div>`;
    return;
  }

  const rows = latestAccountRows;

  // split pending vs posted
  const pending = [];
  const posted = [];
  for (const r of rows) {
    const isPending = String(r.status || "").toLowerCase() === "pending";
    (isPending ? pending : posted).push(r);
  }

  // helper: "2026-01-30" -> "01/30 (Fri)"
  function headerDateLabel(isoOrMmdd) {
    if (!isoOrMmdd) return "";
    if (String(isoOrMmdd).includes("/")) return shortDate(isoOrMmdd);
    const mmdd = formatMMDD(isoOrMmdd);
    const wk = formatWeekdayShort(isoOrMmdd);
    return `${mmdd} (${wk})`;
  }

  function makeDayHeader(dateKey, endOfDayBalance) {
    const h = document.createElement("div");
    h.className = "tx-day-header";

    const isPendingHeader = (String(dateKey) === "Pending");

    h.innerHTML = `
      <div class="tx-day-header__date">${isPendingHeader ? "Pending" : escHtml(headerDateLabel(dateKey))}</div>
      <div class="tx-day-header__bal">${(endOfDayBalance == null || isPendingHeader) ? "" : money(endOfDayBalance)}</div>
    `;
    return h;
  }

  // render row (supports overriding the displayed balance)
  function renderRow(row, balanceOverride = null) {
    const wrap = document.createElement("div");
    wrap.className = "tx-row";
    wrap.dataset.txId = String(row.id ?? "");

    const subBits = [];
    if (row.transfer_peer) {
      const dir = String(row.transfer_dir || "").toLowerCase() === "from" ? "From" : "To";
      subBits.push(`${dir}: ${escHtml(row.transfer_peer)}`);
    } else if (row.category) {
      subBits.push(escHtml(row.category));
    }
    const subHtml = subBits.map(s => `<div>${s}</div>`).join("");

    if (String(row.status || "").toLowerCase() === "pending") {
      wrap.classList.add("is-pending");
    }

    const shownBal =
      (balanceOverride != null) ? balanceOverride :
      (row.balance_after != null ? row.balance_after : null);
    const roundupCents = Number(row.roundup_cents || 0);
    const roundupBadge = roundupCents > 0
      ? `<div class="tx-roundup-badge" title="Round-up cents used on this transaction">¢ ${roundupCents}</div>`
      : "";

    wrap.innerHTML = `
      <div class="tx-icon-wrap tx-icon-hit" role="button" tabindex="0" aria-label="Transaction details">
        ${categoryIconHTML(row.category)}
      </div>
      <div class="tx-date">${shortDate(row.effectiveDate || row.dateISO)}</div>
      <div class="tx-main">
        <div class="tx-merchant">${(row.merchant || "").toUpperCase()}</div>
        <div class="tx-sub">${subHtml}</div>
      </div>
      <div class="tx-right">
        ${roundupBadge}
        <div class="tx-amt">${money(row.amount)}</div>
        <div class="tx-bal">${shownBal == null ? "" : money(shownBal)}</div>
      </div>
    `;

    return wrap;
  }
// Base balance = most recent POSTED row balance (posted is newest-first from backend)
const basePostedBalance =
  (posted.length && posted[0].balance_after != null)
    ? Number(posted[0].balance_after)
    : null;

if (pending.length) {
  list.appendChild(makeDayHeader("Pending", null));

  // 1) compute balances in chronological order (oldest -> newest)
  const pendingChrono = [...pending].sort((a, b) => {
    const ad = parseAnyDateToMs(a.effectiveDate || a.dateISO || a.postedDate || a.purchaseDate);
    const bd = parseAnyDateToMs(b.effectiveDate || b.dateISO || b.postedDate || b.purchaseDate);
    if (ad !== bd) return ad - bd;
    return String(a.id || "").localeCompare(String(b.id || ""));
  });

  const balAfterById = new Map();
  let running = basePostedBalance;

  for (const row of pendingChrono) {
    if (running == null) {
      balAfterById.set(String(row.id ?? ""), null);
      continue;
    }
    running = running + (pendingBalanceMultiplier * Number(row.amount || 0));
    balAfterById.set(String(row.id ?? ""), running);
  }

  // 2) render newest-first
  const pendingDisplay = [...pending].sort((a, b) => {
    const ad = parseAnyDateToMs(a.effectiveDate || a.dateISO || a.postedDate || a.purchaseDate);
    const bd = parseAnyDateToMs(b.effectiveDate || b.dateISO || b.postedDate || b.purchaseDate);
    if (ad !== bd) return bd - ad;
    return String(b.id || "").localeCompare(String(a.id || ""));
  });

  for (const row of pendingDisplay) {
    const bal = balAfterById.get(String(row.id ?? ""));
    list.appendChild(renderRow(row, bal));
  }
}


  // ---- 2) Posted section (your existing newest-first day grouping) ----
  let lastDateKey = null;

  posted.forEach(row => {
    const dateKey = String(row.dateISO || row.effectiveDate || "");

    // Insert header BEFORE first tx-row of that day (newest-first list)
    if (dateKey && dateKey !== lastDateKey) {
      list.appendChild(makeDayHeader(dateKey, row.balance_after));
      lastDateKey = dateKey;
    }

    list.appendChild(renderRow(row, null));
  });

  if (typeof window.attachTxInspect === "function") window.attachTxInspect(list);
}

function normalizeCsvField(v) {
  const s = String(v ?? "").trim();
  if (!s || s.toLowerCase() === "unknown") return "";
  return s;
}

function csvCell(v) {
  const s = String(v ?? "");
  if (s.includes('"') || s.includes(",") || s.includes("\n")) {
    return `"${s.replace(/"/g, '""')}"`;
  }
  return s;
}

function asMoneyNumber(v) {
  const n = Number(v);
  return Number.isFinite(n) ? n.toFixed(2) : "";
}

function buildExportRowsWithVisibleRunning(rows) {
  const pending = [];
  const posted = [];

  for (const r of (rows || [])) {
    const isPending = String(r.status || "").toLowerCase() === "pending";
    (isPending ? pending : posted).push(r);
  }

  const basePostedBalance =
    (posted.length && posted[0].balance_after != null)
      ? Number(posted[0].balance_after)
      : null;

  const pendingChrono = [...pending].sort((a, b) => {
    const ad = parseAnyDateToMs(a.effectiveDate || a.dateISO || a.postedDate || a.purchaseDate);
    const bd = parseAnyDateToMs(b.effectiveDate || b.dateISO || b.postedDate || b.purchaseDate);
    if (ad !== bd) return ad - bd;
    return String(a.id || "").localeCompare(String(b.id || ""));
  });

  const balAfterById = new Map();
  let running = basePostedBalance;
  for (const row of pendingChrono) {
    if (running == null) {
      balAfterById.set(String(row.id ?? ""), null);
      continue;
    }
    running = running + (pendingBalanceMultiplier * Number(row.amount || 0));
    balAfterById.set(String(row.id ?? ""), running);
  }

  const pendingDisplay = [...pending].sort((a, b) => {
    const ad = parseAnyDateToMs(a.effectiveDate || a.dateISO || a.postedDate || a.purchaseDate);
    const bd = parseAnyDateToMs(b.effectiveDate || b.dateISO || b.postedDate || b.purchaseDate);
    if (ad !== bd) return bd - ad;
    return String(b.id || "").localeCompare(String(a.id || ""));
  });

  const out = [];
  for (const row of pendingDisplay) {
    out.push({ row, running_total: balAfterById.get(String(row.id ?? "")) });
  }
  for (const row of posted) {
    out.push({ row, running_total: row.balance_after });
  }
  return out;
}

async function downloadAccountCsv() {
  const start = document.getElementById("a-start")?.value || "";
  const end = document.getElementById("a-end")?.value || "";
  if (!start || !end || !accountId) return;

  let rows = latestAccountRows || [];

  if (TX_MODE !== "test") {
    try {
      const res = await fetch(
        `/account-transactions-range?account_id=${accountId}&start=${start}&end=${end}&limit=5000`,
        { cache: "no-store" }
      );
      if (res.ok) {
        const payload = await res.json();
        rows = Array.isArray(payload?.transactions) ? payload.transactions : rows;
        const mult = Number(payload?.pending_balance_multiplier);
        if (Number.isFinite(mult)) pendingBalanceMultiplier = mult;
      }
    } catch (_e) {
      // Fall back to currently loaded rows.
    }
  }

  if (!Array.isArray(rows) || rows.length === 0) {
    alert("No transactions found in this range.");
    return;
  }

  const ordered = buildExportRowsWithVisibleRunning(rows);
  const header = ["status", "purchase date", "posted date", "time", "merchant", "cost", "running total"];
  const lines = [header.join(",")];

  for (const item of ordered) {
    const row = item.row || {};
    const line = [
      normalizeCsvField(row.status),
      normalizeCsvField(row.purchaseDate),
      normalizeCsvField(row.postedDate),
      normalizeCsvField(row.time),
      normalizeCsvField(row.merchant),
      asMoneyNumber(row.amount),
      asMoneyNumber(item.running_total),
    ].map(csvCell).join(",");
    lines.push(line);
  }

  const csv = `${lines.join("\n")}\n`;
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `account_${accountId}_${start}_to_${end}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function setAccountAddTxMessage(msg, isError = false) {
  const el = document.getElementById("accountAddTxMsg");
  if (!el) return;
  el.textContent = msg || "";
  el.classList.toggle("is-error", !!isError);
}

function initAccountAddTransaction(currentAccountId) {
  const panel = document.getElementById("accountAddTxPanel");
  const openBtn = document.getElementById("accountAddTxBtn");
  const cancelBtn = document.getElementById("accountAddTxCancelBtn");
  const saveBtn = document.getElementById("accountAddTxSaveBtn");
  const dateEl = document.getElementById("accountAddTxDate");
  const statusEl = document.getElementById("accountAddTxStatus");
  const amountEl = document.getElementById("accountAddTxAmount");
  const merchantEl = document.getElementById("accountAddTxMerchant");

  if (!panel || !openBtn || !cancelBtn || !saveBtn) return;

  const open = () => {
    panel.hidden = false;
    if (dateEl && !dateEl.value) dateEl.value = isoTodayLocal();
    setAccountAddTxMessage("");
  };

  const close = () => {
    panel.hidden = true;
    setAccountAddTxMessage("");
  };

  openBtn.addEventListener("click", open);
  cancelBtn.addEventListener("click", close);

  saveBtn.addEventListener("click", async () => {
    const date = (dateEl?.value || "").trim();
    const status = (statusEl?.value || "posted").trim().toLowerCase();
    const amount = parseNum(amountEl?.value);
    const merchant = (merchantEl?.value || "").trim();

    if (!date) {
      setAccountAddTxMessage("Pick a date.", true);
      return;
    }
    if (amount == null) {
      setAccountAddTxMessage("Enter a valid amount.", true);
      return;
    }

    saveBtn.disabled = true;
    setAccountAddTxMessage("Saving...");
    try {
      const res = await fetch("/transaction", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          account_id: Number(currentAccountId),
          amount,
          merchant,
          status,
          date,
          source: "Manual",
        }),
      });
      let out = {};
      try { out = await res.json(); } catch (_) {}
      if (!res.ok || !out?.ok) {
        const errText = out?.detail?.error || out?.error || `Save failed (${res.status})`;
        throw new Error(String(errText));
      }

      if (amountEl) amountEl.value = "";
      if (merchantEl) merchantEl.value = "";
      close();
      await loadAccountChart(Number(currentAccountId));
      await loadAccountTransactions(Number(currentAccountId));
    } catch (err) {
      console.error(err);
      setAccountAddTxMessage(err?.message || "Failed to save transaction.", true);
    } finally {
      saveBtn.disabled = false;
    }
  });
}

function setActiveQuickButton(container, btn){
  container.querySelectorAll(".month-btn").forEach(b => b.classList.remove("active"));
  if (btn) btn.classList.add("active");
}

window.addEventListener("load", async () => {
  accountId = Number(qs("account_id"));
  if (!accountId) return alert("Missing account_id");
  await initAccountSwitcher(accountId);
mountUpcomingCard("#upcomingMount", { daysAhead: 30, accountId });
  // 1) mount the shared card FIRST
mountChartCard("#chartMount", {
  ids: ACCOUNT_CHART_IDS,
  title: "Balance",
  showToggle: false,

  // ✅ add this
  growthToggleHtml: `
    <div id="acctPotentialWrap">
      <label style="display:flex; align-items:center; gap:8px; user-select:none;">
        <input id="acctPotentialToggle" type="checkbox" />
        Projected growth
      </label>
    </div>
  `
});

const potentialToggle = document.getElementById("acctPotentialToggle");
if (potentialToggle) {
  potentialToggle.checked = showPotentialGrowth;

  potentialToggle.addEventListener("change", async () => {
    showPotentialGrowth = potentialToggle.checked;
    localStorage.setItem("showPotentialGrowth", String(showPotentialGrowth));

    const endInput = document.getElementById("a-end");
    if (!endInput) return;

    const todayIso = isoLocal(new Date());

    if (showPotentialGrowth) {
      // force projection to run through EOM (only meaningful for current month)
      if (!sameMonthISO(todayIso, endInput.value)) {
        // if they’re not viewing current month, just turn it back off
        showPotentialGrowth = false;
        potentialToggle.checked = false;
        localStorage.setItem("showPotentialGrowth", "false");
        return;
      }

      endBeforePotential = endInput.value;
      endInput.value = endOfCurrentMonthISO();
    } else {
      if (endBeforePotential) endInput.value = endBeforePotential;
      endBeforePotential = null;
    }

    await loadAccountChart(accountId);
  });
}


initChartControls(ACCOUNT_CHART_IDS, async () => {
  await loadAccountChart(accountId);
  await loadAccountTransactions(accountId);
});

  const exportBtn = document.getElementById("accountCsvExportBtn");
  if (exportBtn) {
    exportBtn.addEventListener("click", downloadAccountCsv);
  }
  initAccountAddTransaction(accountId);


  // 6) wire update button
  document.getElementById(ACCOUNT_CHART_IDS.update).addEventListener("click", async () => {
    await loadAccountChart(accountId);
    await loadAccountTransactions(accountId);
  });

  // 7) load content
  await loadAccountHeader(accountId);
  await loadAccountChart(accountId);
  await loadAccountTransactions(accountId);
});


