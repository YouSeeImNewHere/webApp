// IDs used by the shared chart card (chartCard.js)
const HOME_IDS = {
  title: "chartTitle",
  dots: "chartDots",
  toggle: "chartToggleBtn",

  breakLabel: "chartBreakdownLabel",
  breakValue: "chartBreakdownValue",
  growthLabel: "chartGrowthLabel",
  growthValue: "chartGrowthValue",

  quarters: "quarterButtons",
  yearBack: "homeYearBack",
  yearLabel: "homeYearLabel",
  yearFwd: "homeYearFwd",

  start: "nw-start",
  end: "nw-end",
  update: "nw-chart-btn",

  canvas: "netWorthChart",

  monthButtons: "monthButtons"
};

let netWorthChartInstance = null;
const DEBUG_SPENDING = false;
let showPotentialGrowth = (localStorage.getItem("showPotentialGrowth") === "true");
let endBeforePotential = null;
const CREDIT_UTILIZATION_CAP = 0.30; // 30% real utilization == 100% displayed

// =============================
// UI Layout (server-persisted)
// Requires /static/layout.js + /ui-layout backend
// =============================
let UI_LAYOUT = null;


function getDefaultUILayout() {
  return {
    key: "home",
    // big blocks on Home (we currently reorder: chart, upcoming, bank area, recent transactions)
    home_sections: ["chart", "upcoming", "bankArea", "transactions"],
    // sidebar cards inside the bank area
    sidebar_sections: ["monthBudget", "monthlySpending"],
    // order of account types in Bank Totals
    bank_type_order: ["checking", "credit", "savings", "investment"],
    // order of individual accounts (by account_id) within each type
    bank_account_order: {
      checking: [],
      savings: [],
      credit: [],
      investment: []
    }
  };
}

function applyHomeSectionOrder() {
  const host = document.getElementById("homeSections");
  if (!host) return;

  const nodes = Array.from(host.querySelectorAll(".home-section[data-home-section]"));
  const map = new Map(nodes.map(n => [n.dataset.homeSection, n]));

  const order = UI_LAYOUT?.home_sections || getDefaultUILayout().home_sections;
  const seen = new Set();

  for (const key of order) {
    const el = map.get(key);
    if (el && !seen.has(key)) {
      host.appendChild(el);
      seen.add(key);
    }
  }
  // append anything not in saved list
  for (const [key, el] of map.entries()) {
    if (!seen.has(key)) host.appendChild(el);
  }
}

function applySidebarOrder() {
  const host = document.getElementById("sidebarStack");
  if (!host) return;

  const nodes = Array.from(host.querySelectorAll("[data-sidebar-section]"));
  const map = new Map(nodes.map(n => [n.dataset.sidebarSection, n]));

  const order = UI_LAYOUT?.sidebar_sections || getDefaultUILayout().sidebar_sections;
  const seen = new Set();

  for (const key of order) {
    const el = map.get(key);
    if (el && !seen.has(key)) {
      host.appendChild(el);
      seen.add(key);
    }
  }
  for (const [key, el] of map.entries()) {
    if (!seen.has(key)) host.appendChild(el);
  }
}

// -----------------------------
// Customize mode (drag/drop)
// -----------------------------
let _sortableHome = null;
let _sortableSidebar = null;
let _sortableBankTypes = null;
let _sortableAccountsByType = new Map();

function initCustomizeUI() {
  const btn = document.getElementById("customizeBtn");         // optional (we're removing it)
  const doneBtn = document.getElementById("customizeDoneBtn"); // optional (we're removing it)

  // Inline "Done" bar (non-floating) for customize mode
  let bar = document.getElementById("customizeBar");
  if (!bar) {
    bar = document.createElement("div");
    bar.id = "customizeBar";
    bar.className = "customize-bar";
    bar.innerHTML = `
      <div class="customize-bar__inner">
        <div class="customize-bar__title">Customize layout</div>
        <button type="button" class="customize-bar__done" id="customizeBarDoneBtn">Done</button>
      </div>
    `;
    document.body.appendChild(bar);
  }

  const barDoneBtn = bar.querySelector("#customizeBarDoneBtn");

  const enter = () => {
    if (document.body.classList.contains("is-customizing")) return;
    document.body.classList.add("is-customizing");
    if (btn) btn.style.display = "none";
    if (doneBtn) doneBtn.style.display = "none";
    bar.style.display = "block";
    initSortables();
  };

  const exit = () => {
    if (!document.body.classList.contains("is-customizing")) return;
    document.body.classList.remove("is-customizing");
    if (btn) btn.style.display = "inline-flex";
    if (doneBtn) doneBtn.style.display = "none";
    bar.style.display = "none";
    destroySortables();
  };

  // Bind optional old buttons if they still exist (safe)
  if (btn) btn.addEventListener("click", enter);
  if (doneBtn) doneBtn.addEventListener("click", exit);

  if (barDoneBtn && !barDoneBtn.__bound) {
    barDoneBtn.__bound = true;
    barDoneBtn.addEventListener("click", exit);
  }

  // Expose for Settings -> Home one-tap customize
  window.HomeCustomize = { enter, exit };
}


function initSortables() {
  if (!window.Sortable) {
    console.warn("SortableJS not loaded; customize disabled");
    return;
  }

  // Home major blocks
  const homeHost = document.getElementById("homeSections");
  if (homeHost && !_sortableHome) {
    _sortableHome = new Sortable(homeHost, {
      animation: 150,
      handle: ".drag-handle, .category-box__header, .bank-card__head, .bank-accordion__header",
      draggable: ".home-section[data-home-section]",
      onEnd: async () => {
        UI_LAYOUT.home_sections = Array.from(homeHost.querySelectorAll(".home-section[data-home-section]"))
          .map(el => el.dataset.homeSection);
        await window.LayoutStore.save("home", UI_LAYOUT);
      }
    });
  }

  // Sidebar cards
  const sidebarHost = document.getElementById("sidebarStack");
  if (sidebarHost && !_sortableSidebar) {
    _sortableSidebar = new Sortable(sidebarHost, {
      animation: 150,
      handle: ".category-box__header",
      draggable: "[data-sidebar-section]",
      onEnd: async () => {
        UI_LAYOUT.sidebar_sections = Array.from(sidebarHost.querySelectorAll("[data-sidebar-section]"))
          .map(el => el.dataset.sidebarSection);
        await window.LayoutStore.save("home", UI_LAYOUT);
      }
    });
  }

  // Bank types + accounts
  initBankSortablesOnly();
}

function initBankSortablesOnly() {
  if (!window.Sortable) return;

  const bankHost = document.getElementById("bankTotals");
  if (bankHost && !_sortableBankTypes) {
    _sortableBankTypes = new Sortable(bankHost, {
      animation: 150,
      handle: ".bank-card__head, .bank-accordion__header",
      draggable: ".bank-type-block",
      onEnd: async () => {
        UI_LAYOUT.bank_type_order = Array.from(bankHost.querySelectorAll(".bank-type-block"))
          .map(el => el.dataset.typeKey);
        await window.LayoutStore.save("home", UI_LAYOUT);
      }
    });
  }

  // Accounts within each type
  for (const inst of _sortableAccountsByType.values()) {
    try { inst.destroy(); } catch (_) {}
  }
  _sortableAccountsByType.clear();

  const typeBlocks = document.querySelectorAll(".bank-type-block");
  typeBlocks.forEach(block => {
    const typeKey = block.dataset.typeKey;
    const ul = block.querySelector("ul.bank-sublist");
    if (!typeKey || !ul) return;

    const inst = new Sortable(ul, {
      animation: 150,
      handle: ".account-pill",
      draggable: "li",
      onEnd: async () => {
        const ids = Array.from(ul.querySelectorAll("li[data-account-id]"))
          .map(li => li.dataset.accountId)
          .filter(Boolean);

        if (!UI_LAYOUT.bank_account_order) UI_LAYOUT.bank_account_order = {};
        UI_LAYOUT.bank_account_order[typeKey] = ids;
        await window.LayoutStore.save("home", UI_LAYOUT);
      }
    });

    _sortableAccountsByType.set(typeKey, inst);
  });
}

function destroySortables() {
  try { _sortableHome?.destroy(); } catch (_) {}
  try { _sortableSidebar?.destroy(); } catch (_) {}
  try { _sortableBankTypes?.destroy(); } catch (_) {}
  _sortableHome = null;
  _sortableSidebar = null;
  _sortableBankTypes = null;

  for (const inst of _sortableAccountsByType.values()) {
    try { inst.destroy(); } catch (_) {}
  }
  _sortableAccountsByType.clear();
}

// --- ADD: credit usage notifications ---
const CREDIT_USAGE_THRESHOLDS = [5, 10, 15];

function isoDayLocal() {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

async function pushNotif({ kind, dedupe_key, subject, sender, body }) {
  try {
    await fetch("/notifications/push", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind, dedupe_key, subject, sender, body }),
    });
  } catch (e) {
    console.warn("pushNotif failed:", e);
  }
}

function pctUtil(balance, limit) {
  const used = Math.abs(Number(balance) || 0);
  const lim = Number(limit) || 0;
  if (!lim || lim <= 0) return null;
  return Math.round((used / lim) * 100);
}

async function maybeTriggerCreditUsageNotifs(creditAccounts) {
  if (!Array.isArray(creditAccounts) || creditAccounts.length === 0) return;

  // helper: "used" is how much of the limit is consumed.
  // In your UI logic, credit usage is represented by NEGATIVE balances.
  // Positive balances are effectively a credit (overpaid/refund) -> 0 used.
  const usedFromBal = (bal) => Math.max(0, -Number(bal || 0));

  const todayKey = new Date().toISOString().slice(0, 10); // YYYY-MM-DD

  // ----- Per-card thresholds -----
  for (const a of creditAccounts) {
    const limit = Number(a.credit_limit || 0);
    if (!(limit > 0)) continue; // includes Unlimited->0

    const used = usedFromBal(a.total);

    const pct = (used / limit) * 100;

    for (const t of CREDIT_USAGE_THRESHOLDS) {
      if (pct < t) continue;

      await pushNotif({
        kind: "credit_usage",
        dedupe_key: `cc:${a.id}:${t}:${todayKey}`, // once per day per threshold
        subject: `Credit usage: ${a.name} hit ${t}%`,
        sender: "Credit Monitor",
        body: `${a.name}: ${pct.toFixed(1)}% used (${money(used)} of ${money(limit)}).`,
      });
    }
  }

  // ----- Total thresholds -----
  const limits = creditAccounts.map(a => Number(a.credit_limit || 0)).filter(x => x > 0);
  const totalLimit = limits.reduce((s, x) => s + x, 0);
  if (!(totalLimit > 0)) return;

  const totalUsed = creditAccounts.reduce((s, a) => s + usedFromBal(a.total), 0);

  const totalPct = (totalUsed / totalLimit) * 100;

  for (const t of CREDIT_USAGE_THRESHOLDS) {
    if (totalPct < t) continue;

    await pushNotif({
      kind: "credit_usage_total",
      dedupe_key: `cc:TOTAL:${t}:${todayKey}`,
      subject: `Total credit usage hit ${t}%`,
      sender: "Credit Monitor",
      body: `Total: ${totalPct.toFixed(1)}% used (${money(totalUsed)} of ${money(totalLimit)}).`,
    });
  }
}

function computeCreditSummary(accounts) {
  let limitSum = 0;
  let usedSum = 0;

  for (const a of (accounts || [])) {
    const lim = Number(a.credit_limit) || 0;
    if (lim > 0) limitSum += lim;

    // credit usage = debt only (negative balances)
    const bal = Number(a.total) || 0;
    usedSum += Math.max(0, -bal);
  }

  // Avail is based on your 30% cap
  const capLimit = limitSum * CREDIT_UTILIZATION_CAP;
  const available = Math.max(0, capLimit - usedSum);

  // % used is REAL utilization (100% = total credit limit)
  const pctUsed = (limitSum > 0)
    ? Math.round((usedSum / limitSum) * 100)
    : 0;

  return { limitSum, usedSum, available, pctUsed };
}


async function loadData() {
    const res = await fetch("/transactions");
    const data = await res.json();

    const tbody = document.querySelector("#dataTable tbody");
    tbody.innerHTML = "";

    data.forEach(row => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td>${row.postedDate}</td>
            <td>${row.merchant}</td>
            <td>${row.amount}</td>
            <td>${row.bank}</td>
            <td>${row.card}</td>
        `;
        tbody.appendChild(tr);
    });
}

function sortAccountsByOrder(accounts, orderList) {
  if (!Array.isArray(accounts)) return [];
  const pos = new Map();
  (orderList || []).forEach((id, i) => pos.set(String(id), i));

  return [...accounts].sort((a, b) => {
    const ai = pos.has(String(a.id)) ? pos.get(String(a.id)) : 1e9;
    const bi = pos.has(String(b.id)) ? pos.get(String(b.id)) : 1e9;
    if (ai !== bi) return ai - bi;
    return String(a.name || "").localeCompare(String(b.name || ""));
  });
}

async function loadBankTotals() {
  const res = await fetch("/bank-totals");
  if (!res.ok) {
    console.error("bank-totals failed:", res.status);
    return;
  }

  const data = await res.json();

  const container = document.getElementById("bankTotals");
  if (!container) return;
  container.innerHTML = "";

  const map = {
    checking: { title: "Checking", payload: data.checking },
    credit:   { title: "Card Balances", payload: data.credit },
    savings:  { title: "Savings", payload: data.savings },
    investment:{ title: "Investments", payload: data.investment },
  };

  const order = (UI_LAYOUT?.bank_type_order && Array.isArray(UI_LAYOUT.bank_type_order))
    ? UI_LAYOUT.bank_type_order
    : ["checking", "credit", "savings", "investment"];

  const seen = new Set();
  const keys = [...order, ...Object.keys(map).filter(k => !order.includes(k))];

  for (const typeKey of keys) {
    const entry = map[typeKey];
    if (!entry || seen.has(typeKey)) continue;
    seen.add(typeKey);

    const wrap = document.createElement("div");
    wrap.className = "bank-type-block";
    wrap.dataset.typeKey = typeKey;

    await renderCategory(wrap, typeKey, entry.title, entry.payload);
    container.appendChild(wrap);
  }

  if (document.body.classList.contains("is-customizing")) {
    window.LayoutUI?.initBankSortables?.();
  }
}

function creditUsagePctText(balance, limit) {
  const bal = Number(balance) || 0;
  const lim = Number(limit) || 0;
  if (!lim || lim <= 0) return "";
  const used = Math.max(0, -bal); // debt only
  const pct = Math.round((used / lim) * 100);
  return `${pct}%`;
}

async function loadHomePayload() {
  const res = await fetch("/page/home?tx_limit=15", { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to load /page/home");
  const payload = await res.json();

  // ✅ Recent transactions
  if (Array.isArray(payload.transactions)) {
    renderTxList(payload.transactions);   // <— this exists in your file
  }

  // ✅ Category totals (this month)
  if (payload.category_totals_month) {
    // easiest: reuse your existing loader for now
    // (later we can add a render-from-payload function)
    loadCategoryTotalsThisMonth();
  }

  // ✅ Unread badge
  if (payload.notifications_unread && typeof payload.notifications_unread.unread === "number") {
    // setUnreadBadge was missing in your earlier errors sometimes; guard it.
    if (typeof window.setUnreadBadge === "function") {
      window.setUnreadBadge(payload.notifications_unread.unread);
    }
  }

  // ✅ Bank totals
  if (payload.bank_totals) {
    // easiest: reuse existing loader for now
    loadBankTotals();
  }

  // ✅ Month budget
  loadMonthBudget();

  return payload;
}


async function renderCategory(container, typeKey, title, payload) {
  const total = payload?.total ?? 0;
  const accountsRaw = payload?.accounts ?? [];
  const orderList = UI_LAYOUT?.bank_account_order?.[typeKey] ?? [];
  const accounts = sortAccountsByOrder(accountsRaw, orderList);
  const isCardBalances = title === "Card Balances";
  const creditSummary = isCardBalances ? computeCreditSummary(accountsRaw) : null;
const showCreditSummary = !!creditSummary && creditSummary.limitSum > 0;
// --- fire credit-usage notifications (deduped server-side) ---
if (isCardBalances && creditSummary) {
  // renderCategory() is not async, so fire-and-forget
  maybeTriggerCreditUsageNotifs(accountsRaw, creditSummary)
    .catch(e => console.warn("credit usage notif check failed:", e));
}

  const isMobile = window.matchMedia("(max-width: 900px)").matches;

  const displayTotal = total;

  // ---- MOBILE: accordion ----
  if (isMobile) {
    const wrap = document.createElement("div");
    wrap.className = "bank-accordion";

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "bank-accordion__header";

    btn.innerHTML = `
  <span class="bank-accordion__left">
    <span class="bank-accordion__title">${title}</span>
    <span class="bank-accordion__meta">${accounts.length} acct</span>
  </span>

  <span class="bank-accordion__right">
    <div class="bank-accordion__total">
      ${isCardBalances ? formatCardBalance(displayTotal) : money(displayTotal)} ▾
    </div>

    ${isCardBalances && showCreditSummary ? `
      <div class="bank-accordion__sub">
        ${accounts.length} acct • Avail ${money(creditSummary.available)} • ${creditSummary.pctUsed}% used
      </div>
    ` : ""}
  </span>
`;



    const panel = document.createElement("div");
    panel.className = "bank-accordion__panel";
    panel.hidden = true;

    if (accounts.length) {
      const ul = document.createElement("ul");
      ul.className = "bank-sublist";

      accounts.forEach(a => {
        const li = document.createElement("li");
        li.dataset.accountId = String(a.id);

        const pill = document.createElement("button");
        pill.type = "button";
        pill.className = "account-pill";

        const amt = a.total;
        const usage = isCardBalances ? creditUsagePctText(amt, a.credit_limit) : "";
pill.innerHTML = `
  <span>${a.name}</span>
  <span>
    ${isCardBalances ? formatCardBalance(amt) : money(amt)}
    ${usage ? ` <span class="cc-usage">${usage}</span>` : ""}
  </span>
`;

        pill.addEventListener("click", () => {
          if (document.body.classList.contains("is-customizing")) return;
          window.location.href = `/account?account_id=${a.id}`;
        });

        li.appendChild(pill);
        ul.appendChild(li);
      });

      panel.appendChild(ul);
    }

    btn.addEventListener("click", () => {
      panel.hidden = !panel.hidden;
      const rightEl = btn.querySelector(".bank-accordion__right > div");
if (rightEl) {
  rightEl.textContent =
    `${isCardBalances ? formatCardBalance(displayTotal) : money(displayTotal)} ${panel.hidden ? "▾" : "▴"}`;
}

    });

    wrap.appendChild(btn);
    wrap.appendChild(panel);
    container.appendChild(wrap);
    return;
  }

  // ---- DESKTOP: your existing card ----
  const card = document.createElement("div");
  card.className = "bank-card";

  const head = document.createElement("div");
  head.className = "bank-card__head";

  const left = document.createElement("div");
  left.innerHTML = `
    <div class="bank-card__title">${title}</div>
    <div class="bank-card__meta">${accounts.length} account${accounts.length === 1 ? "" : "s"}</div>
  `;

  const right = document.createElement("div");
right.className = "bank-card__total" + (total < 0 ? " negative" : "");

if (isCardBalances) {
  right.innerHTML = `
    <div>${formatCardBalance(displayTotal)}</div>
    ${showCreditSummary ? `
      <div class="bank-card__subtotal">
        <span>Avail ${money(creditSummary.available)}</span>
        <span class="dot">•</span>
        <span>${creditSummary.pctUsed}% used</span>
      </div>
    ` : ""}
  `;
} else {
  right.textContent = money(displayTotal);
}

  head.appendChild(left);
  head.appendChild(right);
  card.appendChild(head);

  if (accounts.length) {
    const ul = document.createElement("ul");
    ul.className = "bank-sublist";

    accounts.forEach(a => {
      const li = document.createElement("li");
      li.dataset.accountId = String(a.id);

      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "account-pill";

      const amt = a.total;
      const usage = isCardBalances ? creditUsagePctText(amt, a.credit_limit) : "";
btn.innerHTML = `
  <span>${a.name}</span>
  <span>
    ${isCardBalances ? formatCardBalance(amt) : money(amt)}
    ${usage ? ` <span class="cc-usage">${usage}</span>` : ""}
  </span>
`;

      btn.addEventListener("click", () => {
        if (document.body.classList.contains("is-customizing")) return;
        window.location.href = `/account?account_id=${a.id}`;
      });

      li.appendChild(btn);
      ul.appendChild(li);
    });

    card.appendChild(ul);
  }

  container.appendChild(card);
}

async function bootHome() {
  try {
    UI_LAYOUT = await window.LayoutStore.load("home", getDefaultUILayout());
    applyHomeSectionOrder();
    applySidebarOrder();

    initCustomizeUI();

    // If Settings sent us here, auto-enter customize mode
    const _params = new URLSearchParams(window.location.search || "");
    if (_params.get("customize") === "1") {
      window.HomeCustomize?.enter?.();
      _params.delete("customize");
      const qs = _params.toString();
      const newUrl = window.location.pathname + (qs ? `?${qs}` : "") + (window.location.hash || "");
      window.history.replaceState({}, "", newUrl);
    }

    setChartHeaderUI();

    // kick these off immediately (parallel)
    setChartHeaderUI();
    const tasks = [
      Promise.resolve().then(() => loadHomePayload()),
      Promise.resolve().then(() => loadChart()),
      Promise.resolve().then(() => mountUpcomingCard("#upcomingMount", { daysAhead: 30 })),
      Promise.resolve().then(() => { try { mountMonthBudgetCard("#monthBudgetMount"); } catch (_) {} }),
    ];

    const results = await Promise.allSettled(tasks);

    for (const r of results) {
      if (r.status === "rejected") console.warn("Home task failed:", r.reason);
    }

    // optional: log failures
    for (const r of results) {
      if (r.status === "rejected") console.warn("Home task failed:", r.reason);
    }

    try { mountMonthBudgetCard("#monthBudgetMount"); } catch(_) {}

    bindIncomeRowClick();
  } catch (err) {
    console.error("bootHome failed:", err);

    setChartHeaderUI();
    loadChart();
    loadBankTotals();
    loadMonthBudget();
    bindIncomeRowClick();
    loadCategoryTotalsThisMonth();
    loadData();
    mountUpcomingCard("#upcomingMount", { daysAhead: 30 });
  }
}

window.bootHome = bootHome; // ✅ make it globally callable if other files want it



function setYearLabel() {
  const el = document.getElementById("homeYearLabel");
  if (el) el.textContent = String(selectedYear);
}


function currentYear() {
  return new Date().getFullYear();
}

function clampDay(y, m, d) {
  // clamp day to last day of month
  const last = new Date(y, m + 1, 0).getDate();
  return Math.min(d, last);
}

function shiftRangeByYears(yearDelta) {
  const s = document.getElementById("nw-start")?.value;
  const e = document.getElementById("nw-end")?.value;
  if (!s || !e) return null;

  const sd = parseISODateLocal(s);
  const ed = parseISODateLocal(e);


  const nsY = sd.getFullYear() + yearDelta;
  const neY = ed.getFullYear() + yearDelta;

  const nsM = sd.getMonth(), nsD = sd.getDate();
  const neM = ed.getMonth(), neD = ed.getDate();

  const newStart = new Date(nsY, nsM, clampDay(nsY, nsM, nsD));
  const newEnd   = new Date(neY, neM, clampDay(neY, neM, neD));

  return { newStart, newEnd };
}

function rebuildYearDependentUI() {
  setYearLabel();
  buildMonthButtons();
  buildMonthDropdown();
}

function toISODate(d) { return isoLocal(d); }

function firstDayOfMonth(year, monthIndex) {
  return new Date(year, monthIndex, 1);
}

function lastDayOfMonth(year, monthIndex) {
  // day 0 of next month = last day of requested month
  return new Date(year, monthIndex + 1, 0);
}

const CHARTS = [
  { key: "net", title: "Net Worth", endpoint: "/net-worth", nextLabel: "Next: Savings" },
  { key: "savings", title: "Savings", endpoint: "/savings", nextLabel: "Next: Investments" },
  { key: "investment", title: "Investments", endpoint: "/investments", nextLabel: "Next: Spending" },
  { key: "spending", title: "Spending", endpoint: "/spending", nextLabel: "Next: Net Worth" },
];

let chartIndex = 0;

function currentChart() {
  return CHARTS[chartIndex];
}

function renderChartDots() {
  const el = document.getElementById("chartDots");
  if (!el) return;

  el.innerHTML = "";
  CHARTS.forEach((_, i) => {
    const dot = document.createElement("span");
    dot.className = "chart-dot" + (i === chartIndex ? " active" : "");
    el.appendChild(dot);
  });
}

function setChartHeaderUI() {
  const t = document.getElementById("chartTitle");
  const btn = document.getElementById("chartToggleBtn");

  const current = CHARTS[chartIndex];
  const next = CHARTS[(chartIndex + 1) % CHARTS.length];

  if (t) t.textContent = current.title;
  if (btn) btn.textContent = `Next: ${next.title} ▾`;

    renderChartDots();
    updatePotentialToggleVisibility();
}

function toggleChart() {
  chartIndex = (chartIndex + 1) % CHARTS.length;
  setChartHeaderUI();
  updatePotentialToggleVisibility();
  loadChart();
}


function formatMMMdd(isoDateStr) {
  const d = parseISODateLocal(isoDateStr);
  return d.toLocaleDateString("en-US", { month: "short", day: "2-digit" });
}


async function loadChart() {
  const start = document.getElementById("nw-start").value;
  const end = document.getElementById("nw-end").value;
  if (!start || !end) return;

  const { endpoint, title } = currentChart();

  const res = await fetch(`${endpoint}?start=${start}&end=${end}`);
  if (!res.ok) {
    alert(`Error fetching ${title}`);
    return;
  }

  const data = await res.json();

  // --- Potential growth projection (Net Worth only, current month only) ---
let potentialSeries = null;
let potentialEOM = null;

const isNet = (currentChart().key === "net");

if (isNet && showPotentialGrowth) {
  const today = new Date();
  const todayIso = isoLocal(today);

  // Only project for current month
  const startIso = document.getElementById("nw-start")?.value;
  const endIso   = document.getElementById("nw-end")?.value;

  if (startIso && endIso && sameMonthISO(todayIso, endIso)) {
    // 1) Pull month events from recurring calendar
    const y = today.getFullYear();
    const m = today.getMonth() + 1;

    // match your recurring page defaults
    const minOcc = 3;
    const includeStale = "false";

    // Pull the same event sources as "Upcoming Transactions":
    //  - /recurring/calendar (bills/recurring/interest/etc)
    //  - /les/paychecks (paychecks are computed, not stored as recurring rows)
    const [payOut, calJson] = await Promise.all([
      fetchPaychecksForMonth(y, m).catch(() => ({ events: [], breakdown: null })),
      (async () => {
        const calRes = await fetch(
          `/recurring/calendar?year=${encodeURIComponent(y)}&month=${encodeURIComponent(m)}&min_occ=${encodeURIComponent(minOcc)}&include_stale=${includeStale}`
        );
        return calRes.ok ? await calRes.json().catch(() => ({ events: [] })) : { events: [] };
      })()
    ]);

    const payEvents = Array.isArray(payOut?.events) ? payOut.events : [];
    const calEvents = Array.isArray(calJson?.events) ? calJson.events : [];

    // merged events feed for projection
    const events = [...calEvents, ...payEvents];

    // 2) Build daily delta map for remaining days in month (after today)
    const deltaByDate = {}; // { "YYYY-MM-DD": number }
    for (const e of events) {
      const d = String(e.date || "");
      if (!d) continue;

      // Only dates after today (projection forward)
      if (d <= todayIso) continue;

      const amt = Number(e.amount) || 0;

      // Income rules:
      // - paychecks from /les/paychecks should come through as type="income"/cadence="paycheck"
      // - other income (interest, etc) may have type="income"
      const isIncome = (String(e.type || "").toLowerCase() === "income") || (String(e.cadence || "") === "paycheck");

      const delta = isIncome ? amt : -Math.abs(amt);
      deltaByDate[d] = (deltaByDate[d] || 0) + delta;
    }

    // 3) Build a projection series aligned to your /net-worth day-by-day data
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

  if (DEBUG_SPENDING && currentChart().key === "spending") {
  console.group("🧾 Spending chart – raw backend data");
  console.table(data.map(d => ({
    date: d.date,
    value: Number(d.value)
  })));
  console.groupEnd();
}


  const labels = data.map(d => formatMMMdd(d.date));
  const values = data.map(d => Number(d.value)); // <— use unified key "value"

  // ---- Breakdown block (top-left) ----
if (currentChart().key === "spending") {
  // Spending endpoint is daily amounts; Home should show the *range total*
  const total = values.reduce((sum, v) => sum + (Number(v) || 0), 0);
  setInlineBreakdown("Total spent", total);
} else {
  const lastPoint = data[data.length - 1];
  if (lastPoint) setInlineBreakdown(currentChart().title, lastPoint.value);

  // Net Worth: optionally show projected EOM value when enabled
  if (currentChart().key === "net" && showPotentialGrowth && typeof potentialEOM === "number") {
    setInlineBreakdown("Potential (EOM)", potentialEOM);
  }
}


    // ---- % Growth (uses potential EOM when toggle is on for Net Worth) ----
  const startVal = (values.length ? Number(values[0] || 0) : 0);
  const endValActual = (values.length ? Number(values[values.length - 1] || 0) : 0);

  let endValForGrowth = endValActual;
  if (currentChart().key === "net" && showPotentialGrowth && typeof potentialEOM === "number") {
    endValForGrowth = Number(potentialEOM);
  }

  let growthStr = "—";
  if (values.length >= 2 && Math.abs(startVal) > 1e-9) {
    const pct = ((endValForGrowth - startVal) / Math.abs(startVal)) * 100;
    growthStr = (pct > 0 ? "+" : "") + pct.toFixed(2) + "%";
  }

  setInlineGrowth("% Growth", growthStr);


    // Running total (cumulative) for spending
let running = 0;
const cumulative = values.map(v => (running += (Number(v) || 0)));

if (DEBUG_SPENDING && currentChart().key === "spending") {
  console.group("📈 Spending chart – cumulative calculation");
  data.forEach((d, i) => {
    console.log(
      `${d.date}: daily=${money(values[i])}, cumulative=${money(cumulative[i])}`
    );
  });
  console.groupEnd();
}


    // ---- Spending total (for currently selected range) ----
    const totalRow = document.getElementById("spendingTotalRow");
    const totalEl  = document.getElementById("spendingTotalValue");

    if (currentChart().key === "spending") {
      const total = values.reduce((sum, v) => sum + (Number(v) || 0), 0);
      if (totalRow) totalRow.style.display = "block";
      if (totalEl) totalEl.textContent = money(total);
    } else {
      if (totalRow) totalRow.style.display = "none";
    }


  const ctx = document.getElementById("netWorthChart").getContext("2d");

  if (netWorthChartInstance) netWorthChartInstance.destroy();

// Only use the accordion on actual touch devices (phones/tablets),
// not just a narrow desktop window.
const isMobile = window.matchMedia(
  "(max-width: 900px) and (hover: none) and (pointer: coarse)"
).matches;



const isSpending = currentChart().key === "spending";

const datasets = isSpending ? [

  {
    label: "Total (cumulative)",
    data: cumulative,
    tension: 0.2,
    pointRadius: 0,
    pointHitRadius: 12,
    pointHoverRadius: 4,
    borderWidth: 2,
    fill: false
  },
  {
    label: "Daily",
    data: values,
    tension: 0.2,
    pointRadius: 0,
    pointHitRadius: 12,
    pointHoverRadius: 4,
    borderWidth: 2.5,
    borderDash: [4, 4],
    fill: false
  }
] : (() => {
  const base = {
    label: title,
    data: values,
    tension: 0.2,
    pointRadius: 0,
    pointHitRadius: 12,
    pointHoverRadius: 4
  };

  // add overlay for potential growth
  if (currentChart().key === "net" && showPotentialGrowth && Array.isArray(potentialSeries)) {
    return [
      base,
      {
        label: "Potential growth",
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



netWorthChartInstance = new Chart(ctx, {
  type: "line",
  data: {
    labels,
    datasets
  },
  options: {
    responsive: true,
  maintainAspectRatio: false,
  devicePixelRatio: window.devicePixelRatio || 1,
    plugins: {
  legend: { display: false },
  tooltip: {
    enabled: true,
    callbacks: {
      label: (ctx) => {
        const i = ctx.dataIndex;
        const y = ctx.parsed.y;
if (currentChart().key === "net" && ctx.datasetIndex === 1) {
    return `Potential: ${money(y)}`;
  }
        // Default label for Savings/Investments charts
if (currentChart().key === "spending") {
  const i = ctx.dataIndex;

  // datasetIndex 0 = Total (cumulative), datasetIndex 1 = Daily
  if (ctx.datasetIndex === 0) {
    const total = Number(cumulative[i] || 0);
    return `Total: ${money(total)}`;
  }

  const daily = Number(values[i] || 0);
  return `Daily: ${money(daily)}`;
}




            if (currentChart().key !== "net") {
              return `${currentChart().title}: ${money(y)}`;
            }


        // Net worth breakdown (from backend)
        const p = data[i] || {};
        const banks = Number(p.banks || 0);
        const savings = Number(p.savings || 0);
        // backend sends signed cards_balance: negative=debt, positive=surplus
        const cardsBal = Number((p.cards_balance ?? p.cards) || 0);

        return [
          `Net Worth: ${money(y)}`,
          `Banks: ${money(banks)}`,
          `Savings: ${money(savings)}`,
          formatCardBalance(cardsBal, { showLabel: true }),
        ];
      }
    }
  }
},

    interaction: { mode: "index", intersect: false },
    scales: {
      x: isMobile ? {
        ticks: { display: false },
        grid: { display: false }
      } : {
        ticks: { display: true },
        grid: { display: false }
      },
      y: { ticks: { callback: v => v.toLocaleString() } }
    }
  }
});


}

function setActiveMonthButton(btn) {
  document.querySelectorAll("#monthButtons .month-btn").forEach(b => b.classList.remove("active"));
  if (btn) btn.classList.add("active");
}

// -----------------------------
// Month budget card (Home sidebar)
// -----------------------------
async function loadMonthBudget() {
  const safeEl  = document.getElementById("mbSafe");
  const metaEl  = document.getElementById("mbMeta");
  const incEl   = document.getElementById("mbIncome");
  const spentEl = document.getElementById("mbSpent");
  const billsEl = document.getElementById("mbBills");
  const barFill = document.getElementById("mbBarFill");
  const goalEl  = document.getElementById("mbGoal");

  // Card isn't mounted on some pages
  if (!safeEl || !metaEl || !incEl || !spentEl || !billsEl || !barFill) return;

  // Helper: fetch paychecks for a given month using the shared LES profile (localStorage via profile.js)
  async function fetchPaychecks(year, month){
    const profile0 = window.Profile?.get?.() || null;
    if (!profile0?.paygrade) return [];

    const profile = { ...profile0 };

    // normalize a few fields so backend always understands them
    if (profile.paygrade != null){
      profile.paygrade = String(profile.paygrade)
        .toUpperCase()
        .replace(/\s+/g,"")
        .replace("E-","E")
        .replace("-","");
    }
    if (profile.service_start != null){
      profile.service_start = String(profile.service_start);
    }
    if (profile.bah_override === "") profile.bah_override = null;

    const res = await fetch("/les/paychecks", {
      method: "POST",
      headers: { "Content-Type":"application/json" },
      body: JSON.stringify({ year, month, profile })
    });

    if (!res.ok){
      const txt = await res.text().catch(()=> "");
      console.error("Paycheck calc failed:", res.status, txt);
      return [];
    }

    const data = await res.json().catch(()=>null);
    return Array.isArray(data?.events) ? data.events : [];
  }

  const res = await fetch("/month-budget");
  if (!res.ok) {
    console.error("month-budget failed:", res.status);
    safeEl.textContent = "—";
    metaEl.textContent = "Could not load";
    return;
  }

  const j = await res.json();

  // Base values from backend (currently includes interest; paychecks are added below)
  let income = Number(j.income_expected || 0);
  const spent  = Number(j.spent_so_far || 0);
  const bills  = Number(j.bills_remaining || 0);

  // Determine month/year to request paychecks for (use backend month_start if present)
  let year = new Date().getFullYear();
  let month = new Date().getMonth() + 1;
  if (j.month_start && /^\d{4}-\d{2}-\d{2}$/.test(j.month_start)){
    year = Number(j.month_start.slice(0,4));
    month = Number(j.month_start.slice(5,7));
  }

  // Add LES paychecks (if profile exists)
  let payIncome = 0;
  try{
    const payEvents = await fetchPaychecks(year, month);
    const monthKey = `${year}-${String(month).padStart(2,"0")}`;
    for (const e of (payEvents || [])){
      // Only count deposits that actually land *in this calendar month*
      // (ex: Jan 1 payday can deposit on Dec 31 — that's NOT January spendable income)
      const d = String(e?.date || "");
      if (!d.startsWith(monthKey)) continue;

      const amt = Number(e?.amount || 0);
      if (amt > 0) payIncome += amt;
    }
  } catch (err){
    console.warn("Paychecks fetch failed:", err);
  }

  const totalIncome = income + payIncome;

// Apply monthly savings goal (deduct from Safe to spend)
const { goal: savingsGoal, cfg: savingsCfg } = await computeMonthlySavingsGoal(totalIncome);

// Safe to spend is AFTER savings goal
const safe = totalIncome - spent - bills - savingsGoal;

// Total spend budget for the month (after bills + savings goal)
const spendBudget = totalIncome - bills - savingsGoal;

// Remaining spend budget after spending so far
const spendRemaining = spendBudget - spent;

// For the progress bar & meta, compare spend vs spend budget (after bills + savings)
const availableBeforeBills = spendBudget;

  safeEl.textContent = money(safe);
  incEl.textContent = money(totalIncome);
  spentEl.textContent = money(spent);
  billsEl.textContent = money(bills);

// Savings/spend goal line
if (goalEl) {
  if (savingsGoal > 0) {
    const savedStr = (savingsCfg?.mode === "percent")
      ? `${Number(savingsCfg.value || 0)}%`
      : money(savingsGoal);

    // "goal is to spend this month"
    goalEl.textContent = `Spend goal: ${money(Math.max(0, spendBudget))} • Saving ${money(savingsGoal)}` + (savingsCfg?.mode === "percent" ? ` (${savedStr})` : "");
  } else {
    goalEl.textContent = "Spend goal: " + money(Math.max(0, spendBudget));
  }
}

  // Progress: spent vs (income - remaining bills)
  let pct = 0;
  if (availableBeforeBills <= 0) {
    pct = spent > 0 ? 100 : 0;
  } else {
    pct = Math.min(100, Math.max(0, (spent / availableBeforeBills) * 100));
  }

  barFill.style.width = `${pct.toFixed(0)}%`;
  if (spent > availableBeforeBills && availableBeforeBills > 0) barFill.classList.add("over");
  else barFill.classList.remove("over");

  const asOf = j.as_of ? formatMMMdd(j.as_of) : "today";
  metaEl.textContent = `${asOf} • Spent ${money(spent)} of ${money(Math.max(0, availableBeforeBills))}`;
}



// =========================
// Savings goal (DB-persisted)
// Backend contract:
//   GET  /settings/savings-goal -> { mode: "percent"|"amount", value: number }
//   POST /settings/savings-goal -> { ok: true }
// =========================
const SAVINGS_GOAL_ENDPOINT = "/settings/savings-goal";
let _savingsGoalCfg = null;
let _savingsGoalLoaded = false;

function normalizeSavingsCfg(j){
  if (!j) return null;
  const mode = (j.mode === "amount") ? "amount" : (j.mode === "percent" ? "percent" : null);
  const value = Number(j.value);
  if (!mode) return null;
  if (!isFinite(value) || value < 0) return null;
  if (mode === "percent" && value > 100) return null;
  return { mode, value };
}

async function getSavingsGoalConfig(){
  if (_savingsGoalLoaded) return _savingsGoalCfg;
  _savingsGoalLoaded = true;
  try{
    const res = await fetch(SAVINGS_GOAL_ENDPOINT, { cache: "no-store" });
    if (!res.ok) throw new Error("HTTP " + res.status);
    const j = await res.json().catch(()=>null);
    _savingsGoalCfg = normalizeSavingsCfg(j);
  } catch(e){
    console.warn("Savings goal load failed:", e);
    _savingsGoalCfg = null; // treat as 0
  }
  return _savingsGoalCfg;
}

async function computeMonthlySavingsGoal(totalIncome) {
  const cfg = await getSavingsGoalConfig();
  if (!cfg) return { goal: 0, cfg: null };

  if (cfg.mode === "percent") {
    return { goal: Math.max(0, (Number(totalIncome) || 0) * (cfg.value / 100)), cfg };
  }
  return { goal: Math.max(0, cfg.value), cfg };
}

function money(n) {
  const num = Number(n || 0);
  return num.toLocaleString("en-US", { style: "currency", currency: "USD" });
}

// Credit-card balance formatting:
//   negative = you owe (debt)
//   positive = you have a surplus/credit
// Also avoid displaying "-$0.00" from tiny float noise.
function formatCardBalance(n, { showLabel = false } = {}) {
  let x = Number(n || 0);
  // clamp tiny values to 0 to avoid "-0"
  if (Math.abs(x) < 0.005) x = 0;

  const absStr = money(Math.abs(x));

  if (showLabel) {
    if (x < 0) return `Cards: -${absStr}`;
    if (x > 0) return `Cards: +${absStr}`;
    return `Cards: ${money(0)}`;
  }

  if (x < 0) return `-${absStr}`;
  if (x > 0) return `+${absStr}`;
  return money(0);
}

async function loadCategoryTotalsThisMonth() {
  const res = await fetch("/category-totals-month");
  if (!res.ok) {
    console.error("category-totals-month failed:", res.status);
    return;
  }

  const payload = await res.json();
  const data = payload.categories || [];
  const unassignedAllTime = Number(payload.unassigned_all_time || 0);

  const ul = document.getElementById("categoryTotalsList");
  if (!ul) return;

  ul.innerHTML = "";

  // monthly money categories
  if (!data.length) {
    const li = document.createElement("li");
    li.textContent = "No spending yet this month";
    ul.appendChild(li);
  } else {
    data.forEach(row => {
  const li = document.createElement("li");

  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "category-pill";

  const count = Number(row.tx_count || 0);

  btn.innerHTML = `
    <span class="cat-left">
      <span class="cat-name">${row.category}</span>
      <span class="cat-badge" title="${count} transactions">${count}</span>
    </span>
    <span class="cat-amt">${money(row.total)}</span>
  `;

  btn.addEventListener("click", () => {
    window.location.href = `/static/category.html?c=${encodeURIComponent(row.category)}`;
  });

  li.appendChild(btn);
  ul.appendChild(li);
});


  }

// ---- Unassigned section ----
await renderUnknownMerchantRow(ul);
renderUnassignedRow(ul, unassignedAllTime);

}

function renderUnassignedRow(ul, unassignedAllTime) {
  // Remove any existing unassigned row so we can’t ever double-add
  ul.querySelectorAll(".unassigned-row").forEach(n => n.remove());

  const li = document.createElement("li");
  li.className = "unassigned-row";

  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "category-pill";

  btn.innerHTML = `
    <span class="cat-left">
      <span class="cat-name">Unassigned</span>
      <span class="cat-badge" title="${unassignedAllTime} unassigned">${unassignedAllTime}</span>
    </span>
    <span style="display:flex; align-items:center; gap:8px;">
      <span class="cat-amt">+ Rule</span>
    </span>
  `;

  // Clicking anywhere on the row opens the rule modal
  btn.addEventListener("click", openRuleModal);

  li.appendChild(btn);
  ul.appendChild(li);
}


function updatePotentialToggleVisibility() {
  const wrap = document.getElementById("nwPotentialWrap");
  if (!wrap) return;

  const isNet = currentChart().key === "net";
  if (isNet) wrap.classList.remove("is-hidden-reserve");
    else wrap.classList.add("is-hidden-reserve");

  // optional: turn it off when leaving Net Worth
  if (!isNet && showPotentialGrowth) {
    showPotentialGrowth = false;
    localStorage.setItem("showPotentialGrowth", "false");
    const cb = document.getElementById("nwPotentialToggle");
    if (cb) cb.checked = false;
  }
}


let unassignedQueue = [];
let unassignedIndex = 0;

function openBackdrop(show) {
  const el = document.getElementById("ruleModalBackdrop");
  if (!el) return;

  el.style.display = show ? "block" : "none";
  document.body.classList.toggle("modal-open", show);
}


function fillModalFromTx(tx) {
  document.getElementById("ruleTxId").value = tx.id;
  document.getElementById("ruleTxMerchant").textContent = tx.merchant || "(no merchant)";
  document.getElementById("ruleTxAmount").textContent = money(tx.amount);
  document.getElementById("ruleTxDate").textContent = tx.postedDate;

  // ✅ ADD THIS
  document.getElementById("ruleTxAccount").textContent =
    `${tx.bank || ""}${tx.card ? " • " + tx.card : ""}`;

  // reset form
  document.getElementById("ruleCategory").value = "";
  document.getElementById("ruleKeywords").value = "";
  document.getElementById("ruleApplyNow").checked = true;
  document.getElementById("ruleSaveMsg").textContent = "";
}

async function openRuleModal() {
  const res = await fetch(`/unassigned?limit=25&mode=${encodeURIComponent(unassignedMode)}`);

  if (!res.ok) return alert("Failed to load unassigned.");

  unassignedQueue = await res.json();
  unassignedIndex = 0;

  if (!unassignedQueue.length) {
    return alert("No unassigned transactions 🎉");
  }

  openBackdrop(true);
  loadCategoryOptions();
  showUnassignedAt(0);
}

function closeRuleModal() {
  openBackdrop(false);
}

async function saveRule() {
  const category = document.getElementById("ruleCategory").value.trim();
  const keywordsRaw = document.getElementById("ruleKeywords").value;
  const applyNow = document.getElementById("ruleApplyNow").checked;

  const keywords = keywordsRaw
    .split(",")
    .map(s => s.trim())
    .filter(Boolean);

  if (!category) return alert("Enter a category.");
  if (!keywords.length) return alert("Enter at least one keyword.");

  const res = await fetch("/category-rules", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ category, keywords, apply_now: applyNow })
  });

  const out = await res.json();
  if (!out.ok) {
    document.getElementById("ruleSaveMsg").textContent = "Error: " + (out.error || "unknown");
    return;
  }

  document.getElementById("ruleSaveMsg").textContent =
    `Saved. Pattern: /${out.pattern}/. Applied to ${out.applied} tx.`;

  // Refresh sidebar counts + bank totals if you want
  loadCategoryTotalsThisMonth();
    // ✅ Refresh the modal queue so newly-categorized tx disappear
  await refreshUnassignedQueueAfterSave();

}

document.addEventListener("DOMContentLoaded", () => {

// Build the shared chart UI (so Home matches every other page)
mountChartCard("#homeChartMount", {
  ids: HOME_IDS,
  title: "Net Worth",
  toggleText: "Next: Savings ▾",
  breakdownLabel: "Net",
  breakdownValue: "$0",

  // 👇 THIS is the key change
  growthToggleHtml: `
  <div id="nwPotentialWrap">
    <label style="display:flex; align-items:center; gap:8px; user-select:none;">
      <input id="nwPotentialToggle" type="checkbox" />
      Projected growth
    </label>
  </div>
`
});

const closeBtn = document.getElementById("ruleModalClose");
  const saveBtn = document.getElementById("ruleSaveBtn");
  const backdrop = document.getElementById("ruleModalBackdrop");

  if (closeBtn) closeBtn.addEventListener("click", closeRuleModal);
  if (saveBtn) saveBtn.addEventListener("click", saveRule);


    const prevBtn = document.getElementById("rulePrevBtn");
    const nextBtn = document.getElementById("ruleNextBtn");

    if (prevBtn) prevBtn.addEventListener("click", prevUnassigned);
    if (nextBtn) nextBtn.addEventListener("click", nextUnassigned);


  // click outside modal closes
  if (backdrop) {
    backdrop.addEventListener("click", (e) => {
      if (e.target === backdrop) closeRuleModal();
    });
  }initChartControls({
  start: HOME_IDS.start,
  end: HOME_IDS.end,
  yearLabel: HOME_IDS.yearLabel,
  yearBack: HOME_IDS.yearBack,
  yearFwd: HOME_IDS.yearFwd,
  quarters: HOME_IDS.quarters,
  monthButtons: HOME_IDS.monthButtons,
  update: HOME_IDS.update
}, loadChart);
});

document.addEventListener("DOMContentLoaded", () => {
  const startInput = document.getElementById("nw-start");
  const endInput = document.getElementById("nw-end");
  const updateBtn = document.getElementById("nw-chart-btn");
  const toggleBtn = document.getElementById("chartToggleBtn");

  // ✅ If the home chart inputs aren't on this page, this isn't the home page.
  if (!startInput || !endInput) return;

  const today = new Date();
  const firstOfMonth = new Date(today.getFullYear(), today.getMonth(), 1);

  startInput.value = toISODate(firstOfMonth);
  endInput.value = toISODate(today);

  const potentialToggle = document.getElementById("nwPotentialToggle");
  if (potentialToggle) {
    potentialToggle.checked = showPotentialGrowth;

    potentialToggle.addEventListener("change", async () => {
      showPotentialGrowth = potentialToggle.checked;
      localStorage.setItem("showPotentialGrowth", String(showPotentialGrowth));

      const todayIso = isoLocal(new Date());

      if (showPotentialGrowth) {
        if (!sameMonthISO(todayIso, endInput.value) || currentChart().key !== "net") {
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

      await loadChart();
    });
  }

  if (typeof window.bootHome === "function") window.bootHome();

  window.Profile?.ensureUI?.();
  window.Profile?.onChange?.(() => loadMonthBudget());

  if (updateBtn) updateBtn.addEventListener("click", loadChart);
  if (toggleBtn) toggleBtn.addEventListener("click", toggleChart);
});

function updateRuleCounter() {
  const el = document.getElementById("ruleCounter");
  if (!el) return;
  el.textContent = `${unassignedIndex + 1} / ${unassignedQueue.length}`;
}

function showUnassignedAt(index) {
  if (!unassignedQueue.length) return;

  // clamp
  if (index < 0) index = 0;
  if (index >= unassignedQueue.length) index = unassignedQueue.length - 1;

  unassignedIndex = index;
  fillModalFromTx(unassignedQueue[unassignedIndex]);
  updateRuleCounter();

  // optional: disable at ends
  const prevBtn = document.getElementById("rulePrevBtn");
  const nextBtn = document.getElementById("ruleNextBtn");
  if (prevBtn) prevBtn.disabled = (unassignedIndex === 0);
  if (nextBtn) nextBtn.disabled = (unassignedIndex === unassignedQueue.length - 1);
}

function prevUnassigned() {
  if (!unassignedQueue.length) return;
  unassignedIndex = (unassignedIndex - 1 + unassignedQueue.length) % unassignedQueue.length;
  showUnassignedAt(unassignedIndex);
}

function nextUnassigned() {
  if (!unassignedQueue.length) return;
  unassignedIndex = (unassignedIndex + 1) % unassignedQueue.length;
  showUnassignedAt(unassignedIndex);
}

async function loadCategoryOptions() {
  const res = await fetch("/categories");
  if (!res.ok) return;

  const cats = await res.json();
  const dl = document.getElementById("categoryOptions");
  if (!dl) return;

  dl.innerHTML = "";
  cats.forEach(c => {
    const opt = document.createElement("option");
    opt.value = c;
    dl.appendChild(opt);
  });
}

function shortDate(s) {
  if (!s) return "";

  // "12/01/25" -> "12/01"
  if (String(s).includes("/")) {
    const [mm, dd] = String(s).split("/");
    return `${mm}/${dd}`;
  }

  // "YYYY-MM-DD" (date-only) -> "MM/DD" without timezone shifting
  const iso = String(s);
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (m) return `${m[2]}/${m[3]}`;

  // fallback (if you ever pass a full datetime like 2026-01-30T12:34:56Z)
  const d = new Date(iso);
  return d.toLocaleDateString("en-US", { month: "2-digit", day: "2-digit" });
}

function renderTxList(data){
  const list = document.getElementById("txList");
  if (!list) return;

  list.innerHTML = "";

  data.forEach(row => {
    const wrap = document.createElement("div");
    wrap.className = "tx-row";

    // Mark pending transactions
    if (String(row.status || "").toLowerCase() === "pending") {
      wrap.classList.add("is-pending");
    }


    const merchant = (row.merchant || "").toUpperCase();
    const sub = `${row.bank || ""}${row.card ? " • " + row.card : ""}`;
    const amtNum = Number(row.amount || 0);
    const transferText = row.transfer_peer ? (amtNum > 0 ? `To: ${row.transfer_peer}` : `From: ${row.transfer_peer}`) : "";

  const effectiveDate = (row.postedDate && row.postedDate !== "unknown") ? row.postedDate : ((row.purchaseDate && row.purchaseDate !== "unknown") ? row.purchaseDate : row.dateISO);
wrap.dataset.txId = String(row.id ?? "");
wrap.innerHTML = `
  <div class="tx-icon-wrap tx-icon-hit" role="button" tabindex="0" aria-label="Transaction details">
  ${categoryIconHTML(row.category)}
</div>


  <div class="tx-date">${shortDate(effectiveDate)}</div>
  <div class="tx-main">
    <div class="tx-merchant">${merchant}</div>
    <div class="tx-sub">${sub}</div>
    <div class="tx-sub">${(row.category || "").trim()}${transferText ? " • " + transferText : ""}</div>
  </div>
  <div class="tx-amt">${money(row.amount)}</div>
`;


    list.appendChild(wrap);
  });

  // Enable transaction inspect modal when tapping the category icon
  if (typeof window.attachTxInspect === "function") {
    window.attachTxInspect(list);
  }
}

async function loadData() {
  const res = await fetch("/transactions?limit=15");
  if (!res.ok) {
    console.error("Failed to load transactions:", res.status);
    return;
  }

  const data = await res.json();
  renderTxList(data);
}


let unassignedMode = localStorage.getItem("unassignedMode") || "freq";

function initUnassignedToggle() {
  const toggleBtn = document.getElementById("unassignedToggle");
  if (!toggleBtn) return; // ✅ prevents crash on pages without the button

  function setToggleLabel() {
    toggleBtn.textContent = (unassignedMode === "freq")
      ? "Most recent ▾"
      : "Most frequent ▾";
  }

  async function loadUnassigned() {
    const res = await fetch(`/unassigned?limit=25&mode=${encodeURIComponent(unassignedMode)}`);
    if (!res.ok) return;
    const rows = await res.json();
    // render rows...
  }

  toggleBtn.addEventListener("click", () => {
    unassignedMode = (unassignedMode === "freq") ? "recent" : "freq";
    localStorage.setItem("unassignedMode", unassignedMode);
    setToggleLabel();
    loadUnassigned();
  });

  setToggleLabel();
  loadUnassigned();
}

document.addEventListener("DOMContentLoaded", initUnassignedToggle);



async function fetchUnassignedQueue() {
  const res = await fetch(`/unassigned?limit=25&mode=${encodeURIComponent(unassignedMode)}`);
  if (!res.ok) throw new Error("Failed to refresh unassigned");
  return await res.json();
}

async function refreshUnassignedQueueAfterSave() {
  // remember what we were looking at, so we can stay near it after refresh
  const prev = unassignedQueue[unassignedIndex];
  const prevKey = (prev?.merchant || "").toLowerCase();

  // pull fresh list
  unassignedQueue = await fetchUnassignedQueue();

  if (!unassignedQueue.length) {
    // nothing left — keep modal open but show friendly state
    document.getElementById("ruleTxMerchant").textContent = "No unassigned transactions 🎉";
    const acct = document.getElementById("ruleTxAccount"); if (acct) acct.textContent = "";
    document.getElementById("ruleTxAmount").textContent = "";
    document.getElementById("ruleTxDate").textContent = "";
    document.getElementById("ruleCounter").textContent = "0 / 0";
    return;
  }

  // try to keep user near the same merchant after refresh
  let newIndex = 0;
  if (prevKey) {
    const found = unassignedQueue.findIndex(x => (x.merchant || "").toLowerCase() === prevKey);
    if (found >= 0) newIndex = found;
  }

  showUnassignedAt(newIndex);
}

function setBreakdownUI(p) {
  const d  = document.getElementById("nwBDate");
  const b  = document.getElementById("nwBBanks");
  const s  = document.getElementById("nwBSavings");
  const c  = document.getElementById("nwBCards");
  const nw = document.getElementById("nwBNet");

  if (!d || !b || !s || !c || !nw) return;

  d.textContent  = p?.date ? formatMMMdd(p.date) : "—";
  b.textContent  = money(p?.banks ?? 0);
  s.textContent  = money(p?.savings ?? 0);
  const cardsBal = Number((p?.cards_balance ?? p?.cards) || 0);
  c.textContent  = formatCardBalance(cardsBal);
  nw.textContent = money(p?.value ?? 0);
}

async function loadNetWorthBreakdownForEndDate() {
  const end = document.getElementById("nw-end")?.value;
  if (!end) return;

  const res = await fetch(`/net-worth?start=${end}&end=${end}`);
  if (!res.ok) return;

  const arr = await res.json();
  setBreakdownUI(arr && arr.length ? arr[0] : null);
}

function setInlineGrowth(label, valueStr) {
  const l = document.getElementById("chartGrowthLabel");
  const v = document.getElementById("chartGrowthValue");
  if (!l || !v) return;
  l.textContent = label || "% Growth";
  v.textContent = (valueStr == null ? "—" : String(valueStr));
}

function setInlineBreakdown(label, value) {
  const l = document.getElementById("chartBreakdownLabel");
  const v = document.getElementById("chartBreakdownValue");
  if (!l || !v) return;

  l.textContent = label;
  v.textContent = money(value);
}

function isoLocal(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function endOfCurrentMonthISO() {
  const t = new Date();
  const last = new Date(t.getFullYear(), t.getMonth() + 1, 0);
  return isoLocal(last);
}

function sameMonthISO(aIso, bIso) {
  return String(aIso).slice(0, 7) === String(bIso).slice(0, 7);
}

// =========================
// Mini calendar (Next 7 days)
// =========================

function addDays(d, n) {
  const x = new Date(d);
  x.setDate(x.getDate() + n);
  return x;
}

function dayLabel(d) {
  return d.toLocaleDateString("en-US", { weekday: "short" });
}

function shortMD(d) {
  return d.toLocaleDateString("en-US", { month: "2-digit", day: "2-digit" });
}

function signedMoney(n, isIncome) {
  const amt = Math.abs(Number(n || 0));
  const sign = isIncome ? "+" : "-";
  return sign + money(amt);
}

function isIncomeEvent(e) {
  const t = String(e?.type || "").toLowerCase();
  const c = String(e?.cadence || "").toLowerCase();
  return t === "income" || c === "paycheck" || c === "interest";
}

function ellipsize(s, max = 14) {
  s = String(s || "").trim();
  if (s.length <= max) return s;
  return s.slice(0, max - 1) + "…";
}

async function renderUnknownMerchantRow(ul) {
  const res = await fetch("/unknown-merchant-total-month");
  if (!res.ok) return;

  const { total, tx_count } = await res.json();
  const t = Number(total || 0);
  const c = Number(tx_count || 0);

  // If nothing, skip showing it
  if (t <= 0 || c <= 0) return;

  const li = document.createElement("li");
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "category-pill";

  btn.innerHTML = `
    <span class="cat-left">
      <span class="cat-name">Unknown merchant</span>
      <span class="cat-badge" title="${c} transactions">${c}</span>
    </span>
    <span class="cat-amt">${money(t)}</span>
  `;

  // optional click behavior (for now just show a hint)
  btn.addEventListener("click", () => {
  window.location.href = `/static/category.html?c=${encodeURIComponent("Unknown merchant")}`;
});


  li.appendChild(btn);
  ul.appendChild(li);
}

function clamp0(n) {
  n = Number(n || 0);
  return n < 0 ? 0 : n;
}

function mountMonthBudgetCard(mountSel) {
  const mount = document.querySelector(mountSel);
  if (!mount) return;

  // Use your existing "category-box" styling so it matches.
  mount.innerHTML = `
  <aside class="category-box category-box--sidebar" aria-label="This month">
    <div class="category-box__header" style="display:flex; justify-content:space-between;">
      <span>This month</span>
      <span id="mbRange" style="opacity:.7; font-size:.85em;">—</span>
    </div>

    <ul class="category-box__list">
      <li id="mbIncomeRow" class="category-pill" role="button" tabindex="0" style="cursor:pointer;" title="View expected income breakdown">
        <span class="cat-name">Expected income</span>
        <span style="display:flex; align-items:center; gap:6px;">
          <span id="mbIncome" class="cat-amt">—</span>
          <span style="opacity:.45;">›</span>
        </span>
      </li>

      <li class="category-pill">
        <span class="cat-name">Spent so far</span>
        <span id="mbSpent" class="cat-amt">—</span>
      </li>

      <li class="category-pill" style="border-top:1px dashed rgba(0,0,0,.15); padding-top:12px;">
        <span class="cat-name"><strong>Safe to spend</strong></span>
        <span id="mbSafe" class="cat-amt"><strong>—</strong></span>
      </li>
    </ul>

    <div style="margin-top:8px; font-size:11px; opacity:.65;">
      <span id="mbSafeHint">Income − spent − remaining bills</span><br/>
      <span id="mbGoal" style="opacity:.85;">—</span>
    </div>
  </aside>
`;


  // mobile: stack cards
  if (window.matchMedia("(max-width: 900px)").matches) {
    const grid = mount.querySelector("div[style*='grid-template-columns']");
    if (grid) grid.style.gridTemplateColumns = "1fr";
  }

  refreshMonthBudgetCard();

  // In case the Month Budget HTML is static (home.html), bind click too
  bindIncomeRowClick();

  const incomeRow = document.getElementById("mbIncomeRow");
    if (incomeRow) {
      incomeRow.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        openIncomeBreakdown();
      });

      incomeRow.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          openIncomeBreakdown();
        }
      });
    }

}

async function refreshMonthBudgetCard() {
  const rangeEl = document.getElementById("mbRange");
  const incomeEl = document.getElementById("mbIncome");
  const spentEl = document.getElementById("mbSpent");
  const safeEl = document.getElementById("mbSafe");

  const incomeHint = document.getElementById("mbIncomeHint");
  const billsHint = document.getElementById("mbBillsHint");
  const safeHint = document.getElementById("mbSafeHint");

  try {
    const res = await fetch("/month-budget");
    if (!res.ok) throw new Error("month-budget failed: " + res.status);
    const d = await res.json();

    if (rangeEl) rangeEl.textContent = `${formatMMMdd(d.month_start)} – ${formatMMMdd(d.month_end)}`;

    const income = Number(d.income_expected || 0);
    const spent = Number(d.spent_so_far || 0);
    const billsRemaining = Number(d.bills_remaining || 0);

    const safe = Number(d.safe_to_spend || 0);

    if (incomeEl) incomeEl.textContent = money(income);
    if (spentEl) spentEl.textContent = money(spent);

    // Show negative in red-ish by using existing negative class pattern if you want,
    // but keep it simple for now:
    if (safeEl) safeEl.textContent = (safe < 0 ? "-" : "") + money(Math.abs(safe));

    if (incomeHint) incomeHint.textContent = `Expected this month (paychecks + interest)`;
    if (billsHint) billsHint.textContent = `Bills remaining: ${money(billsRemaining)}`;
    if (safeHint) safeHint.textContent = `Income - spent - remaining bills`;

  } catch (e) {
    console.error(e);
    if (rangeEl) rangeEl.textContent = "—";
    if (incomeEl) incomeEl.textContent = "—";
    if (spentEl) spentEl.textContent = "—";
    if (safeEl) safeEl.textContent = "—";
    if (incomeHint) incomeHint.textContent = "Could not load";
    if (billsHint) billsHint.textContent = "";
    if (safeHint) safeHint.textContent = "";
  }


}


// =========================
// Expected Income Breakdown Modal
// =========================


function bindIncomeRowClick() {
  const incomeRow = document.getElementById("mbIncomeRow");
  if (!incomeRow || incomeRow.dataset.bound) return;
  incomeRow.dataset.bound = "1";

  // make it accessible/clickable even if HTML was static
  incomeRow.setAttribute("role", "button");
  incomeRow.setAttribute("tabindex", "0");
  incomeRow.style.cursor = "pointer";

  incomeRow.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    openIncomeBreakdown();
  });
  incomeRow.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      openIncomeBreakdown();
    }
  });
}

function ensureIncomeInspectModal() {
  let root = document.getElementById("incomeInspectRoot");
  if (root) return root;

  root = document.createElement("div");
  root.id = "incomeInspectRoot";
  root.className = "tx-inspect hidden";

  root.innerHTML = `
    <div class="tx-inspect__backdrop" data-income-close></div>

    <div class="tx-inspect__card" role="dialog" aria-modal="true">
      <div class="tx-inspect__head">
        <div>
          <div id="incomeInspectTitle" class="tx-inspect__title">Expected income</div>
          <div id="incomeInspectSub" class="tx-inspect__sub">—</div>
        </div>
        <button class="tx-inspect__close" type="button" data-income-close aria-label="Close">✕</button>
      </div>

      <div id="incomeInspectBody" class="tx-inspect__body"></div>
    </div>
  `;

  document.body.appendChild(root);

  root.addEventListener("click", (e) => {
    if (e.target?.matches?.("[data-income-close]")) closeIncomeInspect();
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeIncomeInspect();
  });

  return root;
}

function closeIncomeInspect() {
  const root = document.getElementById("incomeInspectRoot");
  if (root) root.classList.add("hidden");
}

async function fetchPaychecksForMonth(year, month) {
  const profile0 = window.Profile?.get?.();
  if (!profile0?.paygrade) return { events: [], breakdown: null };

  // normalize a couple fields (same as recurring_page.js)
  const profile = { ...profile0 };
  if (profile.paygrade != null) {
    profile.paygrade = String(profile.paygrade).toUpperCase().replace(/\s+/g, "").replace("E-", "E").replace("-", "");
  }
  if (profile.service_start != null) profile.service_start = String(profile.service_start);
  if (profile.bah_override === "") profile.bah_override = null;

  const res = await fetch("/les/paychecks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ year, month, profile })
  });

  if (!res.ok) {
    const txt = await res.text().catch(() => "");
    throw new Error("Paycheck calc failed: " + res.status + " " + txt);
  }

  const data = await res.json().catch(() => ({}));
  return {
    events: Array.isArray(data?.events) ? data.events : [],
    breakdown: data?.breakdown || null,
  };
}

async function fetchInterestForMonth(year, month) {
  const res = await fetch(`/recurring/calendar?year=${encodeURIComponent(year)}&month=${encodeURIComponent(month)}`);
  if (!res.ok) return [];
  const data = await res.json().catch(() => ({}));
  const events = Array.isArray(data?.events) ? data.events : [];

  // only interest-like income events
  return events.filter(e => {
    const cadence = String(e?.cadence || "").toLowerCase();
    const type = String(e?.type || "").toLowerCase();
    return cadence === "interest" || (type === "income" && cadence !== "paycheck" && String(e?.merchant||"").toLowerCase().includes("interest"));
  });
}

function kvRow(k, v) {
  return `<div class="tx-kv__k">${escapeHtml(k)}</div><div class="tx-kv__v">${escapeHtml(v)}</div>`;
}

async function openIncomeBreakdown() {
  const today = new Date();
  const year = today.getFullYear();
  const month = today.getMonth() + 1;

  const profile0 = window.Profile?.get?.();
  if (!profile0?.paygrade) {
    alert("Set your LES Profile first (top-right Profile button).");
    return;
  }

  const modal = ensureIncomeInspectModal();
  const titleEl = document.getElementById("incomeInspectTitle");
  const subEl = document.getElementById("incomeInspectSub");
  const bodyEl = document.getElementById("incomeInspectBody");

  if (titleEl) titleEl.textContent = "Expected income";
  if (subEl) subEl.textContent = "Loading…";
  if (bodyEl) bodyEl.innerHTML = "";

  modal.classList.remove("hidden");

  try {
    const [{ events: payEventsRaw, breakdown }, interestEventsRaw] = await Promise.all([
      fetchPaychecksForMonth(year, month),
      fetchInterestForMonth(year, month),
    ]);

    // Match the Home "Expected income" number:
    // - Only count items that land inside the displayed month (deposit date)
    // - Only count "IN" that lands in account_id 3 (your spendable account)
    const SPENDABLE_ACCOUNT_ID = 3;
    const monthKey = `${year}-${String(month).padStart(2, "0")}`;

    const payEvents = (payEventsRaw || []).filter(e =>
      String(e?.date || "").startsWith(monthKey + "-") &&
      Number(e?.account_id) === SPENDABLE_ACCOUNT_ID
    );

    const interestEvents = (interestEventsRaw || []).filter(e =>
      String(e?.date || "").startsWith(monthKey + "-") &&
      Number(e?.account_id) === SPENDABLE_ACCOUNT_ID
    );

    const paycheckTotal = payEvents.reduce((s, e) => s + Math.max(0, Number(e?.amount || 0)), 0);
    const interestTotal = interestEvents.reduce((s, e) => s + Math.max(0, Number(e?.amount || 0)), 0);
    const grandTotal = paycheckTotal + interestTotal;

    if (subEl) subEl.textContent = `${money(grandTotal)} • ${today.toLocaleDateString("en-US", { month: "long", year: "numeric" })}`;

    const payList = payEvents
      .slice()
      .sort((a, b) => String(a.date).localeCompare(String(b.date)))
      .map(e => `<div class="tx-kv__k">${escapeHtml(e.date)}</div><div class="tx-kv__v">${escapeHtml(e.merchant || "Paycheck")} • ${money(e.amount)}</div>`)
      .join("");

    const intList = interestEvents
      .slice()
      .sort((a, b) => String(a.date).localeCompare(String(b.date)))
      .map(e => `<div class="tx-kv__k">${escapeHtml(e.date || "")}</div><div class="tx-kv__v">${escapeHtml(e.merchant || "Interest")} • ${money(e.amount)}</div>`)
      .join("");

    let breakdownHtml = "";
    if (breakdown) {
      const ent = breakdown.entitlements || {};
      const ded = breakdown.deductions || {};
      const net = breakdown.net || {};
      const p = breakdown.profile || {};

      breakdownHtml = `
        <div style="margin-bottom:12px; font-weight:700;">How the paychecks are calculated</div>
        <div class="tx-kv">
          ${kvRow("Paygrade", p.paygrade ?? "")}
          ${kvRow("Service start", p.service_start ?? "")}
          ${kvRow("Dependents", (p.has_dependents ? "Yes" : "No"))}

          ${kvRow("Base pay (monthly)", money(ent.base_pay))}
          ${kvRow("BAH (monthly)", money(ent.bah))}
          ${kvRow("BAS (monthly)", money(ent.bas))}
          ${kvRow("Sub pay (monthly)", money(ent.submarine_pay))}
          ${kvRow("Career sea pay (monthly)", money(ent.career_sea_pay))}
          ${kvRow("Spec duty pay (monthly)", money(ent.spec_duty_pay))}

          ${kvRow("Federal taxes", money(ded.federal_taxes))}
          ${kvRow("FICA social security", money(ded.fica_social_security))}
          ${kvRow("FICA medicare", money(ded.fica_medicare))}
          ${kvRow("SGLI", money(ded.sgli))}
          ${kvRow("AFRH", money(ded.afrh))}
          ${kvRow("Roth TSP", money(ded.roth_tsp))}
          ${kvRow("Meal deduction", money(ded.meal_deduction))}
          ${kvRow("Allotments total", money(ded.allotments_total))}
          ${kvRow("Mid-month collections", money(ded.mid_month_collections_total))}

          ${kvRow("Mid-month net pay", money(net.mid_month_pay))}
          ${kvRow("End-of-month net pay", money(net.eom))}
        </div>
      `;
    }

    bodyEl.innerHTML = `
      <div style="display:flex; flex-wrap:wrap; gap:8px; margin-bottom:12px;">
        <span class="category-pill" style="padding:8px 10px;">Paychecks: <strong style="margin-left:6px;">${money(paycheckTotal)}</strong></span>
        <span class="category-pill" style="padding:8px 10px;">Interest: <strong style="margin-left:6px;">${money(interestTotal)}</strong></span>
        <span class="category-pill" style="padding:8px 10px;">Total: <strong style="margin-left:6px;">${money(grandTotal)}</strong></span>
      </div>

      <div style="margin:0 0 12px; opacity:.7; font-size:12px;">
        Only counting deposits <strong>into account 3</strong> that land in <strong>${monthKey}</strong>.
      </div>

      <div style="margin-bottom:14px;">
        <div style="font-weight:700; margin-bottom:6px;">Paychecks in this month</div>
        <div class="tx-kv">${payList || `<div style="opacity:.7;">No paychecks found for this month.</div>`}</div>
      </div>

      <div style="margin-bottom:14px;">
        <div style="font-weight:700; margin-bottom:6px;">Estimated interest in this month</div>
        <div class="tx-kv">${intList || `<div style="opacity:.7;">No interest events found.</div>`}</div>
      </div>

      ${breakdownHtml}
    `;

  } catch (err) {
    console.error(err);
    if (subEl) subEl.textContent = "Failed to load";
    if (bodyEl) bodyEl.innerHTML = `<div style="opacity:.8;">Could not load expected income breakdown.</div>`;
  }
}

function ensureTxInspectModal() {
  let root = document.getElementById("txInspectRoot");
  if (root) return root;

  root = document.createElement("div");
  root.id = "txInspectRoot";
  root.className = "tx-inspect hidden";

  root.innerHTML = `
    <div class="tx-inspect__backdrop" data-tx-close></div>

    <div class="tx-inspect__card" role="dialog" aria-modal="true">
      <div class="tx-inspect__head">
        <div>
          <div id="txInspectTitle" class="tx-inspect__title">Transaction</div>
          <div id="txInspectSub" class="tx-inspect__sub">—</div>
        </div>
        <button class="tx-inspect__close" type="button" data-tx-close aria-label="Close">✕</button>
      </div>

      <div id="txInspectBody" class="tx-inspect__body"></div>
    </div>
  `;

  document.body.appendChild(root);

  root.addEventListener("click", (e) => {
    if (e.target?.matches?.("[data-tx-close]")) closeTxInspect();
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeTxInspect();
  });

  return root;
}

function closeTxInspect() {
  const root = document.getElementById("txInspectRoot");
  if (root) root.classList.add("hidden");
}

function escapeHtml(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function openTxInspect(txId) {
  try {
    const res = await fetch(`/transaction/${encodeURIComponent(txId)}`);
    if (!res.ok) throw new Error("HTTP " + res.status);

    const data = await res.json();
    if (!data.ok) {
      alert("Transaction not found: " + txId);
      return;
    }

    const tx = data.transaction || {};
    const backdrop = ensureTxInspectModal();

    const titleEl = document.getElementById("txInspectTitle");
    const subEl = document.getElementById("txInspectSub");
    const bodyEl = document.getElementById("txInspectBody");

    const merchant = tx.merchant || "(no merchant)";
    const amount = (typeof money === "function") ? money(tx.amount) : String(tx.amount ?? "");
    const bankCard = `${tx.bank || ""}${tx.card ? " • " + tx.card : ""}`.trim();

    if (titleEl) titleEl.textContent = merchant;
    if (subEl) subEl.textContent = `${amount}${bankCard ? " • " + bankCard : ""} • id ${tx.id ?? txId}`;

    const entries = Object.entries(tx);

// Optional: put the most useful fields first
const priority = ["id","status","postedDate","purchaseDate","amount","merchant","bank","card","category","source","time","transfer_peer"];
entries.sort((a,b) => {
  const ai = priority.indexOf(a[0]); const bi = priority.indexOf(b[0]);
  return (ai === -1 ? 999 : ai) - (bi === -1 ? 999 : bi);
});

const kv = entries.map(([k, v]) => {
  const vv =
    v === null ? "null" :
    v === undefined ? "undefined" :
    (typeof v === "object" ? JSON.stringify(v) : String(v));

  return `
    <div class="tx-kv__k">${escapeHtml(k)}</div>
    <div class="tx-kv__v">${escapeHtml(vv)}</div>
  `;
}).join("");

bodyEl.innerHTML = `<div class="tx-kv">${kv}</div>`;


    backdrop.classList.remove("hidden");
  } catch (err) {
    console.error(err);
    alert("Failed to load transaction details.");
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const txList = document.getElementById("txList");
  if (!txList) return;

  if (window.attachTxInspect) window.attachTxInspect(txList);
});