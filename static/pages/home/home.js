import { apiFetch, apiGetJson, apiPostJson, apiPostForm } from "/static/shared/api.module.js";
import { escapeHtml, escapeHtmlAttr, cssEscapeAttr } from "/static/shared/dom.module.js";
import { isoLocal, isoLocalDate, parseISODateLocal, formatMMMdd, formatMonthYearLong, shortDate, fmtISOToShort } from "/static/shared/dates.module.js";
import { money } from "/static/shared/format.module.js";
import { mountUpcomingCard } from "/static/components/cards/upcomingCard.js";

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
let HOME_BOOT_COMPLETE = false;

// =============================
// UI Layout (server-persisted)
// Requires /static/layout.js + /ui-layout backend
// =============================
let UI_LAYOUT = null;

function getSharedRequestCache() {
  if (typeof window === "undefined") return new Map();
  if (!(window.__financeRequestCache instanceof Map)) {
    window.__financeRequestCache = new Map();
  }
  return window.__financeRequestCache;
}

function withSharedCache(key, loader) {
  const cache = getSharedRequestCache();
  if (cache.has(key)) return cache.get(key);
  const p = Promise.resolve()
    .then(loader)
    .catch((err) => {
      cache.delete(key);
      throw err;
    });
  cache.set(key, p);
  return p;
}

async function fetchRecurringCalendarMonthCached(year, month, { minOcc = 3, includeStale = "false" } = {}) {
  const key = `recurring-calendar:${Number(year)}-${Number(month)}:min_occ=${Number(minOcc)}:include_stale=${String(includeStale)}`;
  return withSharedCache(key, async () => {
    try {
      return await apiGetJson(
        `/recurring/calendar?year=${encodeURIComponent(year)}&month=${encodeURIComponent(month)}&min_occ=${encodeURIComponent(minOcc)}&include_stale=${encodeURIComponent(includeStale)}`,
      );
    } catch (_) {
      return { events: [] };
    }
  });
}

function loadJsonCache(key) {
  try { return JSON.parse(localStorage.getItem(key) || "null"); } catch { return null; }
}

function saveJsonCache(key, val) {
  try { localStorage.setItem(key, JSON.stringify(val)); } catch {}
}


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
  const fragment = document.createDocumentFragment();

  for (const key of order) {
    const el = map.get(key);
    if (el && !seen.has(key)) {
      fragment.appendChild(el);
      seen.add(key);
    }
  }
  // append anything not in saved list
  for (const [key, el] of map.entries()) {
    if (!seen.has(key)) fragment.appendChild(el);
  }
  host.appendChild(fragment);
}

function applySidebarOrder() {
  const host = document.getElementById("sidebarStack");
  if (!host) return;

  const nodes = Array.from(host.querySelectorAll("[data-sidebar-section]"));
  const map = new Map(nodes.map(n => [n.dataset.sidebarSection, n]));

  const order = UI_LAYOUT?.sidebar_sections || getDefaultUILayout().sidebar_sections;
  const seen = new Set();
  const fragment = document.createDocumentFragment();

  for (const key of order) {
    const el = map.get(key);
    if (el && !seen.has(key)) {
      fragment.appendChild(el);
      seen.add(key);
    }
  }
  for (const [key, el] of map.entries()) {
    if (!seen.has(key)) fragment.appendChild(el);
  }
  host.appendChild(fragment);
}

function signMoney(n) {
  const x = Number(n || 0);
  if (x < 0) return "-" + money(Math.abs(x));
  return money(x);
}

async function openExtraSavedBreakdown() {
  const root = ensureExtraSavedModal();
  root.classList.remove("hidden");

  const subEl = document.getElementById("extraSavedSub");
  const bodyEl = document.getElementById("extraSavedBody");

  if (subEl) subEl.textContent = "Loading";
  if (bodyEl) bodyEl.innerHTML = "";

  try {
    const d = await apiGetJson("/extra-saved-detail", { cache: "no-store" });
    if (!d.ok) throw new Error("bad payload");

    const days = Array.isArray(d.days) ? d.days : [];
    const total = Number(d.total_extra_saved || 0);

    if (subEl) {
      subEl.textContent = `${fmtISOToShort(d.month_start)}  ${fmtISOToShort(d.today)}  Total: ${signMoney(total)}`;
    }

    if (!days.length) {
      bodyEl.innerHTML = `<div style="opacity:.7;">No daily snapshots found yet.</div>`;
      return;
    }

    // table header
    const header = `
      <div style="display:flex; justify-content:space-between; gap:10px; font-weight:800; padding:8px 0; border-bottom:1px solid rgba(0,0,0,.10);">
        <div style="width:64px;">Date</div>
        <div style="flex:1; text-align:right;">Baseline</div>
        <div style="flex:1; text-align:right;">Spent (free)</div>
        <div style="flex:1; text-align:right;">Leftover</div>
      </div>
    `;

    const rows = days.map(x => {
      const day = fmtISOToShort(x.day);
      const baseline = Number(x.baseline || 0);
      const spentFree = Number(x.spent_today_free || 0);
      const leftover = Number(x.leftover || 0);

      // leftover can be negative (you asked for that)
      const leftoverStyle = leftover < 0 ? "opacity:1; font-weight:900;" : "opacity:.95; font-weight:800;";

      return `
        <div style="display:flex; justify-content:space-between; gap:10px; padding:8px 0; border-bottom:1px solid rgba(0,0,0,.06);">
          <div style="width:64px; opacity:.75;">${escapeHtml(day)}</div>
          <div style="flex:1; text-align:right;">${money(baseline)}</div>
          <div style="flex:1; text-align:right;">${money(spentFree)}</div>
          <div style="flex:1; text-align:right; ${leftoverStyle}">
            ${signMoney(leftover)}
          </div>
        </div>
      `;
    }).join("");

    // optional: small explainer
    const note = `
      <div style="margin-top:10px; font-size:12px; opacity:.7;">
        Leftover = baseline minus spent free. Completed-day leftover is added; overspend pulls from extra saved (never below zero).
      </div>
    `;

    bodyEl.innerHTML = header + rows + note;

  } catch (err) {
    console.error(err);
    if (subEl) subEl.textContent = "Failed to load";
    if (bodyEl) bodyEl.innerHTML = `<div style="opacity:.8;">Could not load extra saved breakdown.</div>`;
  }
}
function bindExtraSavedRowClick() {
  const row = document.getElementById("mbExtraSavedRow");
  if (!row || row.dataset.bound) return;
  row.dataset.bound = "1";

  row.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    openExtraSavedBreakdown();
  });

  row.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      openExtraSavedBreakdown();
    }
  });
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

async function loadExtraSaved() {
  try {
    const j = await apiGetJson("/extra-saved");
    if (!j.ok) return;

    const el = document.getElementById("mbExtraSaved");
    if (el) el.textContent = money(j.extra_saved);
  } catch (e) {
    console.error("extra-saved failed", e);
  }
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
      draggable: "li[data-account-id]",
      forceFallback: true,
      fallbackOnBody: true,
      delayOnTouchOnly: true,
      delay: 120,
      touchStartThreshold: 4,
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
    await apiPostJson(
      "/notifications/push",
      { kind, dedupe_key, subject, sender, body },
      { skipAuthRedirect: true },
    );
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

  // Your "allowed" limit is 30% of total
  const capLimit = limitSum * CREDIT_UTILIZATION_CAP;

  // How much of the 30% cap remains
  const available = Math.max(0, capLimit - usedSum);

  // % used should be based on the 30% cap (your "limit"), not the full limit
  const pctUsed = (capLimit > 0)
    ? Math.round((usedSum / capLimit) * 100)
    : 0;

  return { limitSum, capLimit, usedSum, available, pctUsed };
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

async function loadBankTotals(dataOverride = null) {
  let data = dataOverride;
  if (!data) {
    try {
      data = await apiGetJson("/bank-totals");
    } catch (err) {
      console.error("bank-totals failed:", err);
      return;
    }
  }

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
  const fragment = document.createDocumentFragment();

  for (const typeKey of keys) {
    const entry = map[typeKey];
    if (!entry || seen.has(typeKey)) continue;
    seen.add(typeKey);

    const wrap = document.createElement("div");
    wrap.className = "bank-type-block";
    wrap.dataset.typeKey = typeKey;

    await renderCategory(wrap, typeKey, entry.title, entry.payload);
    fragment.appendChild(wrap);
  }
  container.appendChild(fragment);

  if (document.body.classList.contains("is-customizing")) {
    initBankSortablesOnly();
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
  const yieldToMain = () => new Promise((resolve) => setTimeout(resolve, 0));
  const payload = await apiGetJson("/page/home?tx_limit=15");

  //  Recent transactions
  if (Array.isArray(payload.transactions)) {
    renderTxList(payload.transactions);   // < this exists in your file
    await yieldToMain();
  }

  //  Category totals (this month)
  if (payload.category_totals_month) {
    await loadCategoryTotalsThisMonth(payload.category_totals_month, payload.unknown_merchant_total_month);
    await yieldToMain();
  }

  //  Unread badge
  if (payload.notifications_unread && typeof payload.notifications_unread.unread === "number") {
    // setUnreadBadge was missing in your earlier errors sometimes; guard it.
    if (typeof window.setUnreadBadge === "function") {
      window.setUnreadBadge(payload.notifications_unread.unread);
    }
  }

  //  Bank totals
  if (payload.bank_totals) {
    await loadBankTotals(payload.bank_totals);
  }

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
      ${isCardBalances ? formatCardBalance(displayTotal) : money(displayTotal)} 
    </div>

    ${isCardBalances && showCreditSummary ? `
      <div class="bank-accordion__sub">
  Limit ${money(creditSummary.capLimit)}  ${creditSummary.pctUsed}% used
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
    `${isCardBalances ? formatCardBalance(displayTotal) : money(displayTotal)} ${panel.hidden ? "" : ""}`;
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
        <span>Limit ${money(creditSummary.capLimit)}</span>
<span class="dot"></span>
<span>Used ${money(creditSummary.usedSum)}</span>
<span class="dot"></span>
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
    let pageHomePayload = null;

    // Start payload work after first paint to reduce startup layout contention.
    const tasks = [
      Promise.resolve().then(
        () =>
          new Promise((resolve) => {
            window.requestAnimationFrame(() => setTimeout(resolve, 0));
          }),
      ).then(async () => {
        pageHomePayload = await loadHomePayload();
      }),
    ];

    const results = await Promise.allSettled(tasks);

    for (const r of results) {
      if (r.status === "rejected") console.warn("Home task failed:", r.reason);
    }
    if (document.getElementById("mbSafe")) {
      refreshMonthBudgetCard(false, pageHomePayload);
    }

    bindIncomeRowClick();
    bindSpentRowClick();
    bindExtraSavedRowClick();
    if (window.requestIdleCallback) {
      window.requestIdleCallback(() => { try { mountMonthBudgetCard("#monthBudgetMount"); } catch (_) {} }, { timeout: 1200 });
    } else {
      window.requestAnimationFrame(() => {
        setTimeout(() => { try { mountMonthBudgetCard("#monthBudgetMount"); } catch (_) {} }, 0);
      });
    }
    if (window.requestIdleCallback) {
      window.requestIdleCallback(() => { mountUpcomingCard("#upcomingMount", { daysAhead: 30 }).catch(() => {}); }, { timeout: 1200 });
    } else {
      window.requestAnimationFrame(() => {
        setTimeout(() => { mountUpcomingCard("#upcomingMount", { daysAhead: 30 }).catch(() => {}); }, 0);
      });
    }
  } catch (err) {
    console.error("bootHome failed:", err);

    setChartHeaderUI();
    scheduleInitialChartLoad();
    loadBankTotals();
    refreshMonthBudgetCard(false);
    bindIncomeRowClick();
    bindSpentRowClick();
    loadCategoryTotalsThisMonth();
    loadData();
    if (window.requestIdleCallback) {
      window.requestIdleCallback(() => { mountUpcomingCard("#upcomingMount", { daysAhead: 30 }).catch(() => {}); }, { timeout: 1200 });
    } else {
      window.requestAnimationFrame(() => {
        setTimeout(() => { mountUpcomingCard("#upcomingMount", { daysAhead: 30 }).catch(() => {}); }, 0);
      });
    }
  }
  HOME_BOOT_COMPLETE = true;
}

window.bootHome = bootHome; //  make it globally callable if other files want it



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

let initialChartLoadState = "not_scheduled";
let initialChartVisible = false;
let initialChartPending = false;
let initialChartObserver = null;

function startInitialChartWhenVisible() {
  if (initialChartVisible) return;
  initialChartVisible = true;
  if (initialChartObserver) {
    initialChartObserver.disconnect();
    initialChartObserver = null;
  }
  if (initialChartPending) {
    initialChartPending = false;
    scheduleInitialChartLoad();
  }
}

function observeInitialChartVisibility() {
  if (initialChartVisible || initialChartObserver) return;
  const target = document.getElementById(HOME_IDS.canvas) || document.getElementById("homeChartMount");
  if (!target) {
    startInitialChartWhenVisible();
    return;
  }
  if ("IntersectionObserver" in window) {
    initialChartObserver = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          startInitialChartWhenVisible();
          break;
        }
      }
    }, { threshold: 0.05 });
    initialChartObserver.observe(target);
  } else {
    // Legacy fallback: avoid sync geometry reads that force layout.
    window.requestAnimationFrame(() => startInitialChartWhenVisible());
  }
}

function scheduleInitialChartLoad() {
  if (initialChartLoadState === "done") {
    return loadChart();
  }
  if (!initialChartVisible) {
    initialChartPending = true;
    return;
  }
  if (initialChartLoadState === "scheduled" || initialChartLoadState === "running") {
    return;
  }

  initialChartLoadState = "scheduled";
  window.requestAnimationFrame(() => {
    const run = async () => {
      initialChartLoadState = "running";
      try {
        await loadChart({ isInitialLoad: true });
      } finally {
        initialChartLoadState = "done";
      }
    };
    if (window.requestIdleCallback) {
      window.requestIdleCallback(run, { timeout: 1000 });
    } else {
      setTimeout(run, 0);
    }
  });
}


async function loadChart({ isInitialLoad = false } = {}) {
  const start = document.getElementById("nw-start").value;
  const end = document.getElementById("nw-end").value;
  if (!start || !end) return;

  const { endpoint, title } = currentChart();

  let data;
  try {
    data = await apiGetJson(`${endpoint}?start=${start}&end=${end}`);
  } catch (err) {
    alert(`Error fetching ${title}`);
    return;
  }

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
      fetchRecurringCalendarMonthCached(y, m, { minOcc, includeStale })
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
  console.group(" Spending chart  raw backend data");
  console.table(data.map(d => ({
    date: d.date,
    value: Number(d.value)
  })));
  console.groupEnd();
}


  const labels = data.map(d => formatMMMdd(d.date));
  const values = data.map(d => Number(d.value)); // < use unified key "value"

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

  let growthStr = "";
  if (values.length >= 2 && Math.abs(startVal) > 1e-9) {
    const pct = ((endValForGrowth - startVal) / Math.abs(startVal)) * 100;
    growthStr = (pct > 0 ? "+" : "") + pct.toFixed(2) + "%";
  }

  setInlineGrowth("% Growth", growthStr);


    // Running total (cumulative) for spending
let running = 0;
const cumulative = values.map(v => (running += (Number(v) || 0)));

if (DEBUG_SPENDING && currentChart().key === "spending") {
  console.group(" Spending chart  cumulative calculation");
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
  resizeDelay: isInitialLoad ? 300 : 120,
  animation: isInitialLoad ? false : undefined,
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

  if (!safeEl || !metaEl || !incEl || !spentEl || !billsEl || !barFill) return;

  let j;
  try {
    j = await apiGetJson("/month-budget", { cache: "no-store" });
  } catch (err) {
    console.error("month-budget failed:", err);
    safeEl.textContent = "";
    metaEl.textContent = "Could not load";
    if (goalEl) goalEl.textContent = "";
    barFill.style.width = "0%";
    return;
  }

  //  backend is source of truth
  const income        = Number(j.expected_income ?? 0);
  const spent         = Number(j.spent_so_far ?? 0);
  const bills         = Number(j.bills_remaining ?? 0);
  const safe          = Number(j.safe_to_spend ?? 0);
  const savingsGoal   = Number(j.savings_goal ?? 0);

  // NEW: backend provides these (used to make bar match "free spending")
  const budgetedSpent = Number(j.budgeted_spent_total ?? 0);

  // NEW: daily + days left (what you want consistent across pages)
  const dailyLimit    = Number(j.daily_limit ?? 0);
  const daysLeft      = Number(j.days_left ?? 0);

  safeEl.textContent  = money(safe);
  incEl.textContent   = money(income);
  spentEl.textContent = money(spent);
  billsEl.textContent = money(bills);

  // Only show savings goal (no "Spend goal" text)


  // Progress bar: "free spending" only (spent minus budgeted categories),
  // because safe_to_spend is "FREE spending after allocations"
  const spentFree = Math.max(0, spent - budgetedSpent);
  const safePos   = Math.max(0, safe);
  const denom     = spentFree + safePos;

  const pct = denom > 0 ? Math.min(100, (spentFree / denom) * 100) : 0;
  barFill.style.width = `${pct.toFixed(0)}%`;

  // If you're overspent (safe < 0), visually mark it
  barFill.classList.toggle("over", safe < 0);

  const asOf = j.as_of ? formatMMMdd(j.as_of) : "today";

  // Meta: show $/day + days left (consistent concept)
  const dayText = daysLeft === 1 ? "day left" : "days left";
  metaEl.innerHTML =
    `${asOf}
     <span class="mb-dot"></span>
     <span class="mb-pill">${money(dailyLimit)}/day</span>
     <span class="mb-dot"></span>
     ${daysLeft} ${dayText}`;
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
    const j = await apiGetJson(SAVINGS_GOAL_ENDPOINT, { cache: "no-store" });
    _savingsGoalCfg = normalizeSavingsCfg(j);
  } catch(e){
    console.warn("Savings goal load failed:", e);
    _savingsGoalCfg = null; // treat as 0
  }
  return _savingsGoalCfg;
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

async function loadCategoryTotalsThisMonth(payloadOverride = null, unknownPayloadOverride = null) {
  let payload = payloadOverride;
  if (!payload) {
    try {
      payload = await apiGetJson("/category-totals-month");
    } catch (err) {
      console.error("category-totals-month failed:", err);
      return;
    }
  }
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
    window.location.href = `/static/pages/category/category.html?c=${encodeURIComponent(row.category)}`;
  });

  li.appendChild(btn);
  ul.appendChild(li);
});


  }

// ---- Unassigned section ----
await renderUnknownMerchantRow(ul, unknownPayloadOverride);
renderUnassignedRow(ul, unassignedAllTime);

}

function renderUnassignedRow(ul, unassignedAllTime) {
  // Remove any existing unassigned row so we cant ever double-add
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

  //  ADD THIS
  document.getElementById("ruleTxAccount").textContent =
    `${tx.bank || ""}${tx.card ? "  " + tx.card : ""}`;

  // reset form
  document.getElementById("ruleCategory").value = "";
  document.getElementById("ruleKeywords").value = "";
  document.getElementById("ruleApplyNow").checked = true;
  document.getElementById("ruleSaveMsg").textContent = "";
}

async function openRuleModal() {
  try {
    unassignedQueue = await apiGetJson(`/unassigned?limit=25&mode=${encodeURIComponent(unassignedMode)}`);
  } catch (err) {
    alert("Failed to load unassigned.");
    return;
  }
  unassignedIndex = 0;

  if (!unassignedQueue.length) {
    return alert("No unassigned transactions ");
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

  let out;
  try {
    out = await apiPostJson("/category-rules", { category, keywords, apply_now: applyNow });
  } catch (err) {
    document.getElementById("ruleSaveMsg").textContent = "Error: " + (err?.message || "unknown");
    return;
  }
  if (!out.ok) {
    document.getElementById("ruleSaveMsg").textContent = "Error: " + (out.error || "unknown");
    return;
  }

  document.getElementById("ruleSaveMsg").textContent =
    `Saved. Pattern: /${out.pattern}/. Applied to ${out.applied} tx.`;

  // Refresh sidebar counts + bank totals if you want
  loadCategoryTotalsThisMonth();
    //  Refresh the modal queue so newly-categorized tx disappear
  await refreshUnassignedQueueAfterSave();

}

document.addEventListener("DOMContentLoaded", () => {
const btn = document.getElementById("goBudgetBtn");
  if (btn) btn.addEventListener("click", () => (window.location.href = "/budget"));
// Build the shared chart UI (so Home matches every other page)
mountChartCard("#homeChartMount", {
  ids: HOME_IDS,
  title: "Net Worth",
  toggleText: "Next: Savings ▾",
  breakdownLabel: "Net",
  breakdownValue: "$0",

  //  THIS is the key change
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
}, scheduleInitialChartLoad);
});

document.addEventListener("DOMContentLoaded", () => {
  const startInput = document.getElementById("nw-start");
  const endInput = document.getElementById("nw-end");
  const updateBtn = document.getElementById("nw-chart-btn");
  const toggleBtn = document.getElementById("chartToggleBtn");

  //  If the home chart inputs aren't on this page, this isn't the home page.
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
  observeInitialChartVisibility();

  window.Profile?.ensureUI?.();
  window.Profile?.onChange?.(() => {
    if (!HOME_BOOT_COMPLETE) return;
    refreshMonthBudgetCard(false);
  });

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
  let cats;
  try {
    cats = await apiGetJson("/categories");
  } catch (_) {
    return;
  }
  const dl = document.getElementById("categoryOptions");
  if (!dl) return;

  dl.innerHTML = "";
  cats.forEach(c => {
    const opt = document.createElement("option");
    opt.value = c;
    dl.appendChild(opt);
  });
}

function renderTxList(data){
  const list = document.getElementById("txList");
  if (!list) return;

  list.innerHTML = "";
  const fragment = document.createDocumentFragment();

  const rows = Array.isArray(data) ? data : [];

  // split pending vs posted
  const pending = [];
  const posted = [];
  for (const r of rows) {
    const isPending = String(r.status || "").toLowerCase() === "pending";
    (isPending ? pending : posted).push(r);
  }

  // render pending first (without a separate header)
  if (pending.length) {
    pending.forEach(row => fragment.appendChild(renderOneTxRow(row)));
  }

  // then render the rest (your existing behavior)
  posted.forEach(row => fragment.appendChild(renderOneTxRow(row)));
  list.appendChild(fragment);

  if (typeof window.attachTxInspect === 'function') window.attachTxInspect(list);

  // --- local helper that returns the built tx-row element ---
  function renderOneTxRow(row){
    const wrap = document.createElement("div");
    wrap.className = "tx-row";

    if (String(row.status || "").toLowerCase() === "pending") {
      wrap.classList.add("is-pending");
    }

    const merchant = (row.merchant || "").toUpperCase();
    const sub = `${row.bank || ""}${row.card ? "  " + row.card : ""}`;
    const amtNum = Number(row.amount || 0);
    const transferText = row.transfer_peer ? (amtNum > 0 ? `To: ${row.transfer_peer}` : `From: ${row.transfer_peer}`) : "";
    const roundupCents = Number(row.roundup_cents || 0);
    const roundupBadge = roundupCents > 0
      ? `<div class="tx-roundup-badge" title="Round-up cents used on this transaction">¢ ${roundupCents}</div>`
      : "";

    const effectiveDate =
      (row.postedDate && row.postedDate !== "unknown") ? row.postedDate :
      ((row.purchaseDate && row.purchaseDate !== "unknown") ? row.purchaseDate : row.dateISO);

    wrap.dataset.txId = String(row.id ?? "");
    wrap.innerHTML = `
      <div class="tx-icon-wrap tx-icon-hit" role="button" tabindex="0" aria-label="Transaction details">
        ${categoryIconHTML(row.category)}
      </div>
      <div class="tx-date">${shortDate(effectiveDate)}</div>
      <div class="tx-main">
        <div class="tx-merchant">${merchant}</div>
        <div class="tx-sub">${sub}${transferText ? "  " + transferText : ""}</div>
        <div class="tx-sub">${(row.category || "").trim()}</div>
      </div>
      <div class="tx-amt">${money(row.amount)}</div>
      ${roundupBadge}
    `;
    return wrap;
  }
}

async function loadData() {
  let data;
  try {
    data = await apiGetJson("/transactions?limit=15");
  } catch (err) {
    console.error("Failed to load transactions:", err);
    return;
  }
  renderTxList(data);
}


let unassignedMode = localStorage.getItem("unassignedMode") || "freq";

function initUnassignedToggle() {
  const toggleBtn = document.getElementById("unassignedToggle");
  if (!toggleBtn) return; //  prevents crash on pages without the button

  function setToggleLabel() {
    toggleBtn.textContent = (unassignedMode === "freq")
      ? "Most recent "
      : "Most frequent ";
  }

  async function loadUnassigned() {
    let rows;
    try {
      rows = await apiGetJson(`/unassigned?limit=25&mode=${encodeURIComponent(unassignedMode)}`);
    } catch (_) {
      return;
    }
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

document.addEventListener("DOMContentLoaded", () => {
  const btn = document.getElementById("csvUploadBtn");
  if (btn) btn.addEventListener("click", openCsvUploadModal);

  const params = new URLSearchParams(window.location.search || "");
  const openCsvImport = String(params.get("openCsvImport") || "").toLowerCase();
  if (["1", "true", "yes"].includes(openCsvImport)) {
    openCsvUploadModal();
    params.delete("openCsvImport");
    const q = params.toString();
    const next = `${window.location.pathname}${q ? `?${q}` : ""}${window.location.hash || ""}`;
    window.history.replaceState({}, "", next);
  }
});


async function fetchUnassignedQueue() {
  try {
    return await apiGetJson(`/unassigned?limit=25&mode=${encodeURIComponent(unassignedMode)}`);
  } catch (err) {
    throw new Error("Failed to refresh unassigned");
  }
}

async function refreshUnassignedQueueAfterSave() {
  // remember what we were looking at, so we can stay near it after refresh
  const prev = unassignedQueue[unassignedIndex];
  const prevKey = (prev?.merchant || "").toLowerCase();

  // pull fresh list
  unassignedQueue = await fetchUnassignedQueue();

  if (!unassignedQueue.length) {
    // nothing left  keep modal open but show friendly state
    document.getElementById("ruleTxMerchant").textContent = "No unassigned transactions ";
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

  d.textContent  = p?.date ? formatMMMdd(p.date) : "";
  b.textContent  = money(p?.banks ?? 0);
  s.textContent  = money(p?.savings ?? 0);
  const cardsBal = Number((p?.cards_balance ?? p?.cards) || 0);
  c.textContent  = formatCardBalance(cardsBal);
  nw.textContent = money(p?.value ?? 0);
}

async function loadNetWorthBreakdownForEndDate() {
  const end = document.getElementById("nw-end")?.value;
  if (!end) return;

  let arr;
  try {
    arr = await apiGetJson(`/net-worth?start=${end}&end=${end}`);
  } catch (_) {
    return;
  }
  setBreakdownUI(arr && arr.length ? arr[0] : null);
}

function setInlineGrowth(label, valueStr) {
  const l = document.getElementById("chartGrowthLabel");
  const v = document.getElementById("chartGrowthValue");
  if (!l || !v) return;
  l.textContent = label || "% Growth";
  v.textContent = (valueStr == null ? "" : String(valueStr));
}

function setInlineBreakdown(label, value) {
  const l = document.getElementById("chartBreakdownLabel");
  const v = document.getElementById("chartBreakdownValue");
  if (!l || !v) return;

  l.textContent = label;
  v.textContent = money(value);
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
  return s.slice(0, max - 1) + "";
}

async function renderUnknownMerchantRow(ul, payloadOverride = null) {
  let payload = payloadOverride;
  if (!payload) {
    try {
      payload = await apiGetJson("/unknown-merchant-total-month");
    } catch (_) {
      return;
    }
  }
  const { total, tx_count } = payload || {};
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
      <span class="cat-name">Unknown merchants</span>
      <span class="cat-badge" title="${c} transactions">${c}</span>
    </span>
    <span class="cat-amt">${money(t)}</span>
  `;

  // optional click behavior (for now just show a hint)
  btn.addEventListener("click", () => {
    window.location.href = `/static/pages/category/category.html?c=${encodeURIComponent("Unknown merchants")}`;
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
      <span id="mbRange" style="opacity:.7; font-size:.85em;"></span>
    </div>

    <ul class="category-box__list">
      <li id="mbIncomeRow" class="category-pill" role="button" tabindex="0" style="cursor:pointer;" title="View expected income breakdown">
        <span class="cat-name">Expected income</span>
        <span style="display:flex; align-items:center; gap:6px;">
          <span id="mbIncome" class="cat-amt"></span>
          <span style="opacity:.45;"></span>
        </span>
      </li>

      <li id="mbSpentRow" class="category-pill" role="button" tabindex="0"
    style="cursor:pointer;" title="View spent breakdown">
  <span class="cat-name">Spent so far</span>
  <span style="display:flex; align-items:center; gap:6px;">
    <span id="mbSpent" class="cat-amt"></span>
    <span style="opacity:.45;"></span>
  </span>
</li>


      <li class="category-pill" style="border-top:1px dashed rgba(0,0,0,.15); padding-top:12px;">
        <span class="cat-name"><strong>Safe to spend</strong></span>
        <span id="mbSafe" class="cat-amt"><strong></strong></span>
      </li>
    </ul>

    <!--  NEW: Daily limit (locked once/day) -->
    <div style="margin-top:8px; font-size:11px; opacity:.65;">
      <span id="mbSafeHint">Income  spent  remaining bills</span><br/>

      <div style="display:flex; align-items:center; justify-content:space-between; gap:10px; margin-top:6px;">
        <span style="opacity:.85;">Limit today:</span>
        <span style="display:flex; align-items:center; gap:8px;">
          <span id="mbDaily" style="font-weight:800; opacity:.95;"></span>
          <button id="mbRecalcDaily" class="settings-btn" type="button" style="padding:6px 10px; font-size:12px;">
            Recalc
          </button>
        </span>
      </div>

      <div id="mbDailyMeta" style="margin-top:4px; opacity:.6;"></div>
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
  bindSpentRowClick();

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

async function refreshMonthBudgetCard(forceRecalcDaily = false, prefetched = null) {
  const safeEl = document.getElementById("mbSafe");
  const metaEl = document.getElementById("mbMeta");
  const goalEl = document.getElementById("mbGoal");

  const incomeEl = document.getElementById("mbIncome");
  const spentEl  = document.getElementById("mbSpent");
  const billsEl  = document.getElementById("mbBills"); // if you have it; ok if null

  // Daily limit UI (Home)
  const dailyEl     = document.getElementById("mbDaily");
  const dailyMetaEl = document.getElementById("mbDailyMeta");
  const recalcBtn   = document.getElementById("mbRecalcDaily");
  const dailyBarFill = document.getElementById("mbDailyBarFill");

  // Bind once
  if (recalcBtn && !recalcBtn.dataset.bound) {
    recalcBtn.dataset.bound = "1";
    recalcBtn.addEventListener("click", () => refreshMonthBudgetCard(true));
  }

  try {
    // 1) Month budget numbers
    const d = prefetched?.month_budget || await apiGetJson("/month-budget", { cache: "no-store" });

    const safe  = Number(d.safe_to_spend || 0);
    const asOf  = d.as_of ? String(d.as_of) : "";
    const days  = Number(d.days_left || 0);

    const income = Number(d.expected_income || 0);
    const spent  = Number(d.spent_so_far || 0);
    const bills  = Number(d.bills_remaining || 0);

    if (safeEl) safeEl.textContent = (safe < 0 ? "-" : "") + money(Math.abs(safe));
    if (incomeEl) incomeEl.textContent = money(income);
    if (spentEl)  spentEl.textContent  = money(spent);
    if (billsEl)  billsEl.textContent  = money(bills);

    // We'll fill mbMeta after we fetch /day-limit (so baseline is the locked value)

    // 2) Daily limit (locked baseline + live remaining)
    const dl = forceRecalcDaily
      ? await apiGetJson("/day-limit?recalc=1", { cache: "no-store" })
      : (prefetched?.day_limit || await apiGetJson("/day-limit", { cache: "no-store" }));

    const baseline  = Number(dl.baseline || 0);
    const remaining = Number(dl.remaining_today || 0);
    const spentFree = Number(dl.spent_today_free || 0);
    if (dailyBarFill) {
      const pct = (baseline > 0) ? (Math.max(0, remaining) / baseline) * 100 : 0;
      dailyBarFill.style.width = `${Math.max(0, Math.min(100, pct))}%`;
    }

    if (dailyEl) dailyEl.textContent = money(remaining);
    if (dailyMetaEl) {
      dailyMetaEl.textContent =
        `Baseline: ${money(baseline)}\n` +
        `Spent Today: ${money(spentFree)}`;
    }
    // Refresh after /day-limit so today's snapshot is present for extra-saved math.
    loadExtraSaved();


    // Keep your existing meta style: "Feb 07  $45.71/day  22 days left"
    // BUT use the locked baseline from /day-limit, not the constantly-recomputed /month-budget daily_limit.
    function formatDdMmmFromISO(iso) {
  // expects "YYYY-MM-DD"
  const d = String(iso || "");
  if (!/^\d{4}-\d{2}-\d{2}$/.test(d)) return "";
  const [y, m, day] = d.split("-").map(Number);
  const dt = new Date(y, (m || 1) - 1, day || 1);
  const dd = String(dt.getDate()).padStart(2, "0");
  const mmm = dt.toLocaleString("en-US", { month: "short" });
  return `${dd}-${mmm}`;
}

if (metaEl) {
  const ddMmm = asOf ? formatDdMmmFromISO(asOf) : "";
  metaEl.textContent = ddMmm
    ? `${ddMmm}\n${days} days left`
    : `${days} days left`;
}


    // If you already compute/show savings goal elsewhere, keep it.
    // goalEl can stay as-is if you set it in another function; otherwise set it here if you have the value.
    // if (goalEl) goalEl.textContent = `Savings goal: ${money(Number(d.savings_goal || 0))}`;

  } catch (e) {
    console.error(e);
    if (safeEl) safeEl.textContent = "";
    if (metaEl) metaEl.textContent = "";
    if (dailyEl) dailyEl.textContent = "";
    if (dailyMetaEl) dailyMetaEl.textContent = "";
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
          <div id="incomeInspectSub" class="tx-inspect__sub"></div>
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
  const key = `les-paychecks:${Number(year)}-${Number(month)}`;
  return withSharedCache(key, async () => {
    const profile0 = window.Profile?.get?.();
    if (!profile0?.paygrade) return { events: [], breakdown: null };

    // normalize a couple fields (same as recurring_page.js)
    const profile = { ...profile0 };
    if (profile.paygrade != null) {
      profile.paygrade = String(profile.paygrade).toUpperCase().replace(/\s+/g, "").replace("E-", "E").replace("-", "");
    }
    if (profile.service_start != null) profile.service_start = String(profile.service_start);
    if (profile.bah_override === "") profile.bah_override = null;

    const res = await apiFetch("/les/paychecks", {
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
  });
}

async function fetchInterestForMonth(year, month) {
  const data = await fetchRecurringCalendarMonthCached(year, month, { minOcc: 3, includeStale: "false" });
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
  if (subEl) subEl.textContent = "Loading";
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

    if (subEl) subEl.textContent = `${money(grandTotal)}  ${formatMonthYearLong(today)}`;

    const payList = payEvents
      .slice()
      .sort((a, b) => String(a.date).localeCompare(String(b.date)))
      .map(e => `<div class="tx-kv__k">${escapeHtml(e.date)}</div><div class="tx-kv__v">${escapeHtml(e.merchant || "Paycheck")}  ${money(e.amount)}</div>`)
      .join("");

    const intList = interestEvents
      .slice()
      .sort((a, b) => String(a.date).localeCompare(String(b.date)))
      .map(e => `<div class="tx-kv__k">${escapeHtml(e.date || "")}</div><div class="tx-kv__v">${escapeHtml(e.merchant || "Interest")}  ${money(e.amount)}</div>`)
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

function ensureExtraSavedModal() {
  let root = document.getElementById("extraSavedRoot");
  if (root) return root;

  root = document.createElement("div");
  root.id = "extraSavedRoot";
  root.className = "tx-inspect hidden";

  root.innerHTML = `
    <div class="tx-inspect__backdrop" data-extra-close></div>

    <div class="tx-inspect__card" role="dialog" aria-modal="true">
      <div class="tx-inspect__head">
        <div>
          <div id="extraSavedTitle" class="tx-inspect__title">Extra saved</div>
          <div id="extraSavedSub" class="tx-inspect__sub"></div>
        </div>
        <button class="tx-inspect__close" type="button" data-extra-close aria-label="Close">✕</button>
      </div>

      <div id="extraSavedBody" class="tx-inspect__body"></div>
    </div>
  `;

  document.body.appendChild(root);

  root.addEventListener("click", (e) => {
    if (e.target?.matches?.("[data-extra-close]")) closeExtraSavedModal();
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeExtraSavedModal();
  });

  return root;
}

// =========================
// CSV Upload Modal (preview + mapped import)
// =========================

const CSV_MODAL_STATE = {
  file: null,
  columns: [],
  accounts: [],
  activePreset: null,
  activePresetAccountId: 0,
  dropGuardBound: false,
};

const CSV_ACCOUNT_PRESET_KEY = "__account__";

const CSV_MAPPING_FIELD_LABELS = {
  csvMapPurchase: "Transaction date",
  csvMapPosted: "Posted date",
  csvMapAmount: "Amount",
  csvMapMerchant: "Merchant",
  csvMapIndicator: "Credit/Debit indicator",
};

function csvSelectHasOption(id, val) {
  const el = document.getElementById(id);
  if (!el) return false;
  const sval = String(val);
  return Array.from(el.options || []).some(o => String(o.value) === sval);
}

function ensureCsvMappingOption(id, val) {
  const el = document.getElementById(id);
  if (!el || val === null || val === undefined) return;
  if (csvSelectHasOption(id, val)) return;
  const n = Number(val);
  const colLabel = Number.isInteger(n) && n >= 0 ? `column ${n + 1}` : `value ${String(val)}`;
  const friendly = CSV_MAPPING_FIELD_LABELS[id] || "Saved mapping";
  const opt = document.createElement("option");
  opt.value = String(val);
  opt.textContent = `${friendly}: ${colLabel} (saved)`;
  el.appendChild(opt);
}

function ensureCsvUploadModal() {
  let root = document.getElementById("csvUploadRoot");
  if (root) return root;

  root = document.createElement("div");
  root.id = "csvUploadRoot";
  root.className = "tx-inspect hidden";
  root.innerHTML = `
    <div class="tx-inspect__backdrop" data-csv-close></div>
    <div class="tx-inspect__card" role="dialog" aria-modal="true" aria-label="Import file">
      <div class="tx-inspect__head">
        <div>
          <div class="tx-inspect__title">Import CSV/Excel</div>
          <div id="csvUploadSub" class="tx-inspect__sub">Drop a CSV or Excel file, preview it, map columns, then import.</div>
        </div>
        <button class="tx-inspect__close" type="button" data-csv-close aria-label="Close">✕</button>
      </div>
      <div class="tx-inspect__body">
        <div id="csvDropZone" style="border:1px dashed rgba(0,0,0,.25); border-radius:12px; padding:12px; margin-bottom:10px;">
          <div style="font-weight:700;">Drag and drop CSV/Excel here</div>
          <div style="opacity:.75; font-size:12px; margin-top:4px;">or choose a file manually</div>
          <div style="margin-top:8px; display:flex; gap:8px; align-items:center;">
            <button id="csvPickFileBtn" class="settings-btn" type="button">Choose file</button>
            <div id="csvPickedName" style="font-size:12px; opacity:.75;">No file selected</div>
          </div>
          <input id="csvFileInput" type="file" accept=".csv,text/csv,.xlsx,.xls,.xlsm,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel.sheet.macroEnabled.12" style="display:none;" />
        </div>

        <div style="display:grid; grid-template-columns:1fr 1fr; gap:10px;">
          <label style="font-size:12px; font-weight:700;">Account
            <select id="csvAccountId" style="width:100%; margin-top:4px;"></select>
          </label>
          <label style="font-size:12px; font-weight:700;">Delimiter
            <select id="csvDelimiter" style="width:100%; margin-top:4px;">
              <option value="auto">Auto-detect</option>
              <option value=",">Comma</option>
              <option value=";">Semicolon</option>
              <option value="	">Tab</option>
              <option value="|">Pipe</option>
            </select>
          </label>
          <label style="font-size:12px; font-weight:700;">Header row
            <input id="csvHeaderRow" type="number" min="1" value="1" style="width:100%; margin-top:4px;" />
          </label>
          <label style="font-size:12px; font-weight:700;">First data row
            <input id="csvDataStartRow" type="number" min="1" value="2" style="width:100%; margin-top:4px;" />
          </label>
        </div>

        <div style="display:flex; gap:10px; margin-top:12px; justify-content:flex-end;">
          <button id="csvPreviewBtn" class="settings-btn" type="button">Preview File</button>
          <button id="csvDryRunBtn" class="settings-btn" type="button">Dry run</button>
          <button id="csvSavePresetBtn" class="settings-btn" type="button">Save mapping</button>
          <button id="csvUploadCancel" class="settings-btn" type="button">Cancel</button>
          <button id="csvUploadDone" class="settings-btn" type="button">Done</button>
          <button id="csvUploadRun" class="settings-btn primary" type="button">Import</button>
        </div>

        <div style="margin-top:12px;">
          <div style="font-weight:800; margin-bottom:6px;">Map columns</div>
          <div style="display:grid; grid-template-columns:1fr 1fr; gap:10px;">
            <label style="font-size:12px;">Transaction date*<select id="csvMapPurchase" style="width:100%; margin-top:4px;"></select></label>
            <label style="font-size:12px;">Posted date<select id="csvMapPosted" style="width:100%; margin-top:4px;"></select></label>
            <label style="font-size:12px;">Amount*<select id="csvMapAmount" style="width:100%; margin-top:4px;"></select></label>
            <label style="font-size:12px;">Merchant*<select id="csvMapMerchant" style="width:100%; margin-top:4px;"></select></label>
            <label style="font-size:12px;">Credit/Debit indicator<select id="csvMapIndicator" style="width:100%; margin-top:4px;"></select></label>
          </div>
          <div style="display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-top:8px;">
            <label style="font-size:12px;">Indicator value treated as credit
              <input id="csvCreditIndicatorValue" type="text" value="credit" style="width:100%; margin-top:4px;" />
            </label>
            <label style="font-size:12px; display:flex; align-items:center; gap:8px; margin-top:18px;">
              <input id="csvInvertAmount" type="checkbox" />
              Invert all amounts
            </label>
          </div>
        </div>

        <div style="margin-top:12px;">
          <div style="font-weight:800; margin-bottom:6px;">Preview</div>
          <div id="csvPreviewWrap" style="max-height:220px; overflow:auto; border:1px solid rgba(0,0,0,.12); border-radius:10px; padding:6px;"></div>
        </div>

        <div id="csvUploadMsg" style="margin-top:12px; font-size:12px; white-space:pre-wrap; opacity:.85;"></div>
      </div>
    </div>
  `;

  document.body.appendChild(root);
  root.addEventListener("click", (e) => { if (e.target?.matches?.("[data-csv-close]")) closeCsvUploadModal(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeCsvUploadModal(); });
  root.querySelector("#csvUploadCancel")?.addEventListener("click", closeCsvUploadModal);
  root.querySelector("#csvUploadDone")?.addEventListener("click", closeCsvUploadModal);
  root.querySelector("#csvPreviewBtn")?.addEventListener("click", refreshCsvPreview);
  root.querySelector("#csvDryRunBtn")?.addEventListener("click", runCsvDryRun);
  root.querySelector("#csvSavePresetBtn")?.addEventListener("click", saveCsvPreset);
  root.querySelector("#csvUploadRun")?.addEventListener("click", runCsvIngestMapped);
  root.querySelector("#csvPickFileBtn")?.addEventListener("click", () => root.querySelector("#csvFileInput")?.click());
  root.querySelector("#csvFileInput")?.addEventListener("change", () => {
    const f = root.querySelector("#csvFileInput")?.files?.[0];
    if (!f) return;
    setCsvFileForModal(f);
  });
  root.querySelector("#csvAccountId")?.addEventListener("change", () => { loadCsvPreset().catch(console.error); });

  const drop = root.querySelector("#csvDropZone");
  if (drop) {
    drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.style.background = "rgba(0,0,0,.03)"; });
    drop.addEventListener("dragleave", () => { drop.style.background = ""; });
    drop.addEventListener("drop", (e) => {
      e.preventDefault();
      drop.style.background = "";
      const f = e.dataTransfer?.files?.[0];
      if (!f) return;
      CSV_MODAL_STATE.file = f;
      const input = root.querySelector("#csvFileInput");
      if (input) {
        const dt = new DataTransfer();
        dt.items.add(f);
        input.files = dt.files;
      }
      setCsvFileForModal(f);
    });
  }

  if (!CSV_MODAL_STATE.dropGuardBound) {
    CSV_MODAL_STATE.dropGuardBound = true;
    const hasFiles = (e) => Array.from(e?.dataTransfer?.types || []).includes("Files");
    window.addEventListener("dragover", (e) => {
      const csvRoot = document.getElementById("csvUploadRoot");
      if (!csvRoot || csvRoot.classList.contains("hidden")) return;
      if (!hasFiles(e)) return;
      e.preventDefault();
    });
    window.addEventListener("drop", (e) => {
      const csvRoot = document.getElementById("csvUploadRoot");
      if (!csvRoot || csvRoot.classList.contains("hidden")) return;
      if (!hasFiles(e)) return;
      const inDropZone = !!e?.target?.closest?.("#csvDropZone");
      if (!inDropZone) {
        e.preventDefault();
        const sub = document.getElementById("csvUploadSub");
        if (sub) sub.textContent = "Use the upload box above: drag a file there or click Choose file.";
      }
    });
  }
  return root;
}

function closeCsvUploadModal() {
  document.getElementById("csvUploadRoot")?.classList.add("hidden");
}

function openCsvUploadModal() {
  const root = ensureCsvUploadModal();
  const msg = document.getElementById("csvUploadMsg");
  const sub = document.getElementById("csvUploadSub");
  const preview = document.getElementById("csvPreviewWrap");
  CSV_MODAL_STATE.columns = [];
  CSV_MODAL_STATE.activePreset = null;
  CSV_MODAL_STATE.activePresetAccountId = 0;
  if (msg) msg.textContent = "";
  if (sub) sub.textContent = "Drop a CSV or Excel file, preview it, map columns, then import.";
  if (preview) preview.innerHTML = `<div style="opacity:.65; padding:6px;">No preview yet.</div>`;
  populateCsvMappingSelects([]);
  loadCsvAccounts().catch(console.error);
  updateCsvPickedName();
  root.classList.remove("hidden");
}

function buildCsvPresetPayload() {
  return {
    delimiter: document.getElementById("csvDelimiter")?.value || "auto",
    header_row: Math.max(1, Number(document.getElementById("csvHeaderRow")?.value || 1)),
    data_start_row: Math.max(1, Number(document.getElementById("csvDataStartRow")?.value || 2)),
    purchase_col: csvGetSelectInt("csvMapPurchase"),
    posted_col: csvGetSelectInt("csvMapPosted"),
    amount_col: csvGetSelectInt("csvMapAmount"),
    merchant_col: csvGetSelectInt("csvMapMerchant"),
    indicator_col: csvGetSelectInt("csvMapIndicator"),
    credit_indicator_value: String(document.getElementById("csvCreditIndicatorValue")?.value || "credit"),
    invert_amount: !!document.getElementById("csvInvertAmount")?.checked,
  };
}

function applyCsvPreset(preset) {
  if (!preset || typeof preset !== "object") return;
  CSV_MODAL_STATE.activePreset = preset;
  const setIf = (id, val) => {
    const el = document.getElementById(id);
    if (!el || val === null || val === undefined) return;
    if (id in CSV_MAPPING_FIELD_LABELS) ensureCsvMappingOption(id, val);
    el.value = String(val);
  };
  setIf("csvDelimiter", preset.delimiter);
  setIf("csvHeaderRow", preset.header_row);
  setIf("csvDataStartRow", preset.data_start_row);
  setIf("csvMapPurchase", preset.purchase_col);
  setIf("csvMapPosted", preset.posted_col);
  setIf("csvMapAmount", preset.amount_col);
  setIf("csvMapMerchant", preset.merchant_col);
  setIf("csvMapIndicator", preset.indicator_col);
  setIf("csvCreditIndicatorValue", preset.credit_indicator_value);
  const invert = document.getElementById("csvInvertAmount");
  if (invert && typeof preset.invert_amount === "boolean") invert.checked = preset.invert_amount;
}

function selectedCsvAccountMeta() {
  const accountId = Number(document.getElementById("csvAccountId")?.value || 0);
  const meta = (CSV_MODAL_STATE.accounts || []).find(a => Number(a.id) === accountId);
  return { accountId, meta };
}

async function loadCsvPreset(preferredAccountId = null) {
  const sub = document.getElementById("csvUploadSub");
  const accountSel = document.getElementById("csvAccountId");
  const accountId = Number(preferredAccountId || accountSel?.value || 0);
  if (!accountId) {
    CSV_MODAL_STATE.activePreset = null;
    CSV_MODAL_STATE.activePresetAccountId = 0;
    return false;
  }
  try {
    const q = `/csv/mapping-presets?account_id=${encodeURIComponent(accountId)}&institution_key=${encodeURIComponent(CSV_ACCOUNT_PRESET_KEY)}`;
    const out = await apiGetJson(q, { cache: "no-store" });
    if (out?.ok && out?.found && out?.preset) {
      applyCsvPreset(out.preset);
      CSV_MODAL_STATE.activePresetAccountId = accountId;
      if (sub) sub.textContent = "Saved mapping loaded for selected account.";
      return true;
    }
  } catch (e) {
    console.error(e);
  }
  CSV_MODAL_STATE.activePreset = null;
  CSV_MODAL_STATE.activePresetAccountId = 0;
  return false;
}

async function saveCsvPreset() {
  const sub = document.getElementById("csvUploadSub");
  const { accountId } = selectedCsvAccountMeta();
  if (!accountId) {
    if (sub) sub.textContent = "Choose account before saving mapping.";
    return;
  }
  try {
    await apiPostJson("/csv/mapping-presets", {
      account_id: accountId,
      institution_key: CSV_ACCOUNT_PRESET_KEY,
      preset: buildCsvPresetPayload(),
    });
    CSV_MODAL_STATE.activePreset = buildCsvPresetPayload();
    CSV_MODAL_STATE.activePresetAccountId = accountId;
    if (sub) sub.textContent = "Mapping saved for selected account.";
  } catch (e) {
    console.error(e);
    if (sub) sub.textContent = `Mapping save failed: ${e?.message || e}`;
  }
}

function setCsvFileForModal(f) {
  if (!f) return;
  CSV_MODAL_STATE.file = f;
  CSV_MODAL_STATE.columns = [];
  const { accountId } = selectedCsvAccountMeta();
  updateCsvPickedName();
  populateCsvMappingSelects([]);
  if (CSV_MODAL_STATE.activePreset && CSV_MODAL_STATE.activePresetAccountId === accountId) {
    applyCsvPreset(CSV_MODAL_STATE.activePreset);
  }
  const preview = document.getElementById("csvPreviewWrap");
  const sub = document.getElementById("csvUploadSub");
  const msg = document.getElementById("csvUploadMsg");
  if (preview) preview.innerHTML = `<div style="opacity:.65; padding:6px;">No preview yet.</div>`;
  if (msg) msg.textContent = "";
  if (sub) sub.textContent = "File selected. Click Preview File when ready.";
}

function updateCsvPickedName() {
  const el = document.getElementById("csvPickedName");
  if (!el) return;
  const f = CSV_MODAL_STATE.file;
  el.textContent = f ? `${f.name} (${Math.round(f.size / 1024)} KB)` : "No file selected";
}

function csvGetSelectInt(id) {
  const el = document.getElementById(id);
  if (!el) return null;
  const v = String(el.value || "").trim();
  if (!v || v === "-1") return null;
  const n = Number(v);
  return Number.isInteger(n) ? n : null;
}

function guessCsvColumn(columns, candidates) {
  const terms = candidates.map(s => s.toLowerCase());
  for (const c of columns) {
    const label = String(c.label || "").toLowerCase();
    if (terms.some(t => label.includes(t))) return c.index;
  }
  return null;
}

function populateCsvMappingSelects(columns) {
  const ids = ["csvMapPurchase", "csvMapPosted", "csvMapAmount", "csvMapMerchant", "csvMapIndicator"];
  const opts = ['<option value="-1">Not mapped</option>']
    .concat((columns || []).map(c => `<option value="${c.index}">${escapeHtml(c.label)} (col ${c.index + 1})</option>`))
    .join("");
  ids.forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.innerHTML = opts;
  });
  const guesses = {
    csvMapPurchase: ["transaction date", "trans date", "date"],
    csvMapPosted: ["posted date", "post date", "posting date"],
    csvMapAmount: ["amount", "transaction amount"],
    csvMapMerchant: ["description", "merchant", "payee", "transaction description"],
    csvMapIndicator: ["credit/debit", "credit debit", "indicator", "type"],
  };
  Object.entries(guesses).forEach(([id, terms]) => {
    const guess = guessCsvColumn(columns || [], terms);
    const el = document.getElementById(id);
    if (el && guess !== null) el.value = String(guess);
  });
}

function renderCsvPreview(previewRows, columns) {
  const wrap = document.getElementById("csvPreviewWrap");
  if (!wrap) return;
  if (!columns?.length || !previewRows?.length) {
    wrap.innerHTML = `<div style="opacity:.65; padding:6px;">No rows to preview.</div>`;
    return;
  }
  const head = columns.map(c => `<th style="text-align:left; border-bottom:1px solid rgba(0,0,0,.15); padding:4px 6px;">${escapeHtml(c.label)}</th>`).join("");
  const body = previewRows.map((r) => {
    const cells = columns.map((c, i) => `<td style="padding:4px 6px; border-bottom:1px solid rgba(0,0,0,.06);">${escapeHtml((r.cells && r.cells[i]) || "")}</td>`).join("");
    return `<tr>${cells}</tr>`;
  }).join("");
  wrap.innerHTML = `<table style="width:100%; border-collapse:collapse; font-size:12px;"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

async function loadCsvAccounts() {
  const sel = document.getElementById("csvAccountId");
  if (!sel) return;
  try {
    const info = await apiGetJson("/bank-info", { cache: "no-store" });
    const rows = [];
    for (const a of (info.accounts || [])) rows.push({ id: a.account_id, label: `${a.bank} - ${a.name}`, institution: a.bank });
    for (const c of (info.credit_cards || [])) rows.push({ id: c.card_id, label: `${c.bank} - ${c.name} (credit)`, institution: c.bank });
    CSV_MODAL_STATE.accounts = rows;
    sel.innerHTML = rows.map(r => `<option value="${r.id}">${escapeHtml(r.label)}</option>`).join("");
    await loadCsvPreset();
  } catch (e) {
    console.error(e);
    sel.innerHTML = `<option value="">Failed to load accounts</option>`;
  }
}

async function refreshCsvPreview() {
  const msg = document.getElementById("csvUploadMsg");
  const sub = document.getElementById("csvUploadSub");
  const btn = document.getElementById("csvPreviewBtn");
  if (msg) msg.textContent = "";
  if (!CSV_MODAL_STATE.file) {
    if (sub) sub.textContent = "Pick a file first.";
    return;
  }
  if (sub) sub.textContent = "Building preview...";
  if (btn) btn.disabled = true;

  try {
    const fd = new FormData();
    fd.append("file", CSV_MODAL_STATE.file, CSV_MODAL_STATE.file.name);
    fd.append("delimiter", document.getElementById("csvDelimiter")?.value || "auto");
    fd.append("has_header", "true");
    fd.append("header_row", String(Math.max(1, Number(document.getElementById("csvHeaderRow")?.value || 1))));
    fd.append("data_start_row", String(Math.max(1, Number(document.getElementById("csvDataStartRow")?.value || 2))));
    fd.append("max_rows", "12");

    const out = await apiPostForm("/csv/preview", fd);
    if (!out?.ok) throw new Error("Preview failed");
    CSV_MODAL_STATE.columns = Array.isArray(out.columns) ? out.columns : [];
    populateCsvMappingSelects(CSV_MODAL_STATE.columns);
    await loadCsvPreset();
    renderCsvPreview(out.preview_rows || [], CSV_MODAL_STATE.columns);
    if (sub) sub.textContent = `Preview loaded (${out.row_count || 0} rows).`;
  } catch (e) {
    console.error(e);
    if (sub) sub.textContent = "Preview failed";
    if (msg) msg.textContent = String(e?.message || e);
  } finally {
    if (btn) btn.disabled = false;
  }
}

function appendCsvMappingFields(fd, accountId, requireAccount = true) {
  const purchaseCol = csvGetSelectInt("csvMapPurchase");
  const amountCol = csvGetSelectInt("csvMapAmount");
  const merchantCol = csvGetSelectInt("csvMapMerchant");
  if ((requireAccount && !accountId) || purchaseCol === null || amountCol === null || merchantCol === null) {
    throw new Error(requireAccount
      ? "Map required fields: transaction date, amount, merchant, and account."
      : "Map required fields: transaction date, amount, and merchant.");
  }
  if (requireAccount) fd.append("account_id", String(accountId));
  fd.append("purchase_col", String(purchaseCol));
  fd.append("amount_col", String(amountCol));
  fd.append("merchant_col", String(merchantCol));
  fd.append("delimiter", document.getElementById("csvDelimiter")?.value || "auto");
  fd.append("has_header", "true");
  fd.append("header_row", String(Math.max(1, Number(document.getElementById("csvHeaderRow")?.value || 1))));
  fd.append("data_start_row", String(Math.max(1, Number(document.getElementById("csvDataStartRow")?.value || 2))));
  fd.append("credit_indicator_value", String(document.getElementById("csvCreditIndicatorValue")?.value || "credit"));
  fd.append("invert_amount", document.getElementById("csvInvertAmount")?.checked ? "true" : "false");
  const posted = csvGetSelectInt("csvMapPosted");
  const indicator = csvGetSelectInt("csvMapIndicator");
  if (posted !== null) fd.append("posted_col", String(posted));
  if (indicator !== null) fd.append("indicator_col", String(indicator));
}

async function runCsvDryRun(fromPreview = false) {
  const msg = document.getElementById("csvUploadMsg");
  const sub = document.getElementById("csvUploadSub");
  const btn = document.getElementById("csvDryRunBtn");
  if (!fromPreview && msg) msg.textContent = "";
  if (!CSV_MODAL_STATE.file) {
    if (sub) sub.textContent = "Pick a file first.";
    return;
  }
  const accountId = Number(document.getElementById("csvAccountId")?.value || 0);
  if (!accountId) {
    if (sub) sub.textContent = "Choose an account first.";
    return;
  }
  if (sub) sub.textContent = fromPreview ? "Building compare preview..." : "Running dry run...";
  if (btn) btn.disabled = true;

  try {
    const fd = new FormData();
    fd.append("file", CSV_MODAL_STATE.file, CSV_MODAL_STATE.file.name);
    fd.append("account_id", String(accountId));
    appendCsvMappingFields(fd, 0, false);

    const out = await apiPostForm("/csv/ingest-mapped/dry-run", fd);
    if (!out?.ok) throw new Error("Dry run failed");
    const s = out.summary || {};
    if (sub) sub.textContent = `Dry run: ${s.valid_rows || 0} valid, ${s.invalid_rows || 0} invalid (${s.total_rows || 0} total).`;
    const compare = out.compare || null;
    if (compare) {
      openCsvDryRunCompareModal(compare, s);
      if (!fromPreview && msg) msg.textContent = "Dry run compare opened.";
    } else if (msg) {
      const samples = Array.isArray(s.sample_errors) ? s.sample_errors.slice(0, 10) : [];
      msg.textContent = samples.length ? JSON.stringify(samples, null, 2) : "No sample errors.";
    }
  } catch (e) {
    console.error(e);
    if (sub) sub.textContent = "Dry run failed";
    if (msg) msg.textContent = String(e?.message || e);
  } finally {
    if (btn) btn.disabled = false;
  }
}

let CSV_IMPORT_PROGRESS_TIMER = null;
let CSV_IMPORT_PROGRESS_PCT = 0;

function stopCsvImportProgress() {
  if (CSV_IMPORT_PROGRESS_TIMER) {
    clearInterval(CSV_IMPORT_PROGRESS_TIMER);
    CSV_IMPORT_PROGRESS_TIMER = null;
  }
}

function renderCsvImportProgress() {
  const sub = document.getElementById("csvUploadSub");
  if (!sub) return;
  const pct = Math.max(0, Math.min(99, Math.round(CSV_IMPORT_PROGRESS_PCT)));
  sub.textContent = `Importing... ${pct}%`;
}

function startCsvImportProgress() {
  stopCsvImportProgress();
  CSV_IMPORT_PROGRESS_PCT = 4;
  renderCsvImportProgress();
  CSV_IMPORT_PROGRESS_TIMER = setInterval(() => {
    if (CSV_IMPORT_PROGRESS_PCT >= 96) return;
    const remaining = 96 - CSV_IMPORT_PROGRESS_PCT;
    const step = Math.max(0.6, remaining * 0.08);
    CSV_IMPORT_PROGRESS_PCT += step;
    renderCsvImportProgress();
  }, 180);
}

function completeCsvImportProgress() {
  stopCsvImportProgress();
  CSV_IMPORT_PROGRESS_PCT = 100;
  const sub = document.getElementById("csvUploadSub");
  if (sub) sub.textContent = "Importing... 100%";
}

async function runCsvIngestMapped() {
  const msg = document.getElementById("csvUploadMsg");
  const sub = document.getElementById("csvUploadSub");
  const runBtn = document.getElementById("csvUploadRun");
  const doneBtn = document.getElementById("csvUploadDone");
  const cancelBtn = document.getElementById("csvUploadCancel");
  if (msg) msg.textContent = "";

  if (!CSV_MODAL_STATE.file) {
    if (sub) sub.textContent = "Pick a file first.";
    return;
  }
  const accountId = Number(document.getElementById("csvAccountId")?.value || 0);
  if (!accountId) {
    if (sub) sub.textContent = "Choose an account first.";
    return;
  }
  startCsvImportProgress();
  if (runBtn) runBtn.disabled = true;
  if (doneBtn) doneBtn.disabled = true;
  if (cancelBtn) cancelBtn.disabled = true;

  try {
    const fd = new FormData();
    fd.append("file", CSV_MODAL_STATE.file, CSV_MODAL_STATE.file.name);
    appendCsvMappingFields(fd, accountId);

    const out = await apiPostForm("/csv/ingest-mapped", fd);
    if (!out?.ok) throw new Error("Import failed");
    completeCsvImportProgress();
    const errCount = Array.isArray(out.errors) ? out.errors.length : 0;
    if (sub) sub.textContent = `Imported ${out.inserted || 0}, updated ${out.updated || 0}, skipped ${out.skipped || 0}${errCount ? `, ${errCount} row errors` : ""}.`;
    if (msg) msg.textContent = errCount ? JSON.stringify(out.errors, null, 2) : "Import complete.";

    try { loadBankTotals(); } catch (_) {}
    try { loadData(); } catch (_) {}
    try { refreshMonthBudgetCard(false); } catch (_) {}
  } catch (e) {
    console.error(e);
    stopCsvImportProgress();
    if (sub) sub.textContent = "Import failed";
    if (msg) msg.textContent = String(e?.message || e);
  } finally {
    stopCsvImportProgress();
    if (runBtn) runBtn.disabled = false;
    if (doneBtn) doneBtn.disabled = false;
    if (cancelBtn) cancelBtn.disabled = false;
  }
}

function ensureCsvDryRunCompareModal() {
  let root = document.getElementById("csvDryRunCompareRoot");
  if (root) return root;

  root = document.createElement("div");
  root.id = "csvDryRunCompareRoot";
  root.className = "tx-inspect hidden";
  root.innerHTML = `
    <div class="tx-inspect__backdrop" data-csv-dry-close></div>
    <div class="tx-inspect__card" role="dialog" aria-modal="true" aria-label="CSV dry run comparison">
      <div class="tx-inspect__head">
        <div>
          <div class="tx-inspect__title">CSV Dry Run Comparison</div>
          <div id="csvDryRunCompareSub" class="tx-inspect__sub"></div>
        </div>
        <button class="tx-inspect__close" type="button" data-csv-dry-close aria-label="Close">✕</button>
      </div>
      <div id="csvDryRunCompareBody" class="tx-inspect__body csv-dryrun__body"></div>
    </div>
  `;
  document.body.appendChild(root);
  root.addEventListener("click", (e) => {
    if (e.target?.matches?.("[data-csv-dry-close]")) root.classList.add("hidden");
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") root.classList.add("hidden");
  });
  return root;
}

function _csvDryMoney(n) {
  return money(Number(n || 0));
}

function _csvDryRowsTable(rows, { showMatch = false, showId = false } = {}) {
  const list = Array.isArray(rows) ? rows : [];
  if (!list.length) {
    return `<div class="csv-dryrun__empty">None</div>`;
  }
  const matchHead = showMatch ? `<th>Match</th>` : "";
  const idHead = showId ? `<th>ID</th>` : "";
  const body = list.map((r) => {
    const date = escapeHtml(String(r.purchaseDate || ""));
    const amt = _csvDryMoney(r.amount);
    const merch = escapeHtml(String(r.merchant || ""));
    const matchCell = showMatch
      ? `<td class="csv-dryrun__mono">${escapeHtml(String(r.match_id || ""))}</td>`
      : "";
    const idCell = showId
      ? `<td class="csv-dryrun__mono">${escapeHtml(String(r.id || ""))}</td>`
      : "";
    return `<tr><td>${date}</td><td class="csv-dryrun__num">${amt}</td><td>${merch}</td>${matchCell}${idCell}</tr>`;
  }).join("");
  return `
    <div class="csv-dryrun__table-wrap">
      <table class="csv-dryrun__table">
        <thead>
          <tr>
            <th>Date</th>
            <th class="csv-dryrun__num">Amount</th>
            <th>Merchant</th>
            ${matchHead}
            ${idHead}
          </tr>
        </thead>
        <tbody>${body}</tbody>
      </table>
    </div>
  `;
}

function openCsvDryRunCompareModal(compare, summary) {
  const root = ensureCsvDryRunCompareModal();
  const sub = document.getElementById("csvDryRunCompareSub");
  const body = document.getElementById("csvDryRunCompareBody");
  if (!root || !sub || !body) return;

  const s = summary || {};
  const updExact = Array.isArray(compare?.would_update_exact) ? compare.would_update_exact : [];
  const updTip = Array.isArray(compare?.would_update_tip) ? compare.would_update_tip : [];
  const toInsert = Array.isArray(compare?.would_insert) ? compare.would_insert : [];
  const matchedIds = new Set(
    [...updExact, ...updTip]
      .map(r => String(r?.match_id || "").trim())
      .filter(Boolean)
  );
  const pendingAll = Array.isArray(compare?.pending) ? compare.pending : [];
  const pending = pendingAll.filter(r => !matchedIds.has(String(r?.id || "").trim()));
  const subLine = `Valid ${s.valid_rows || 0}  Invalid ${s.invalid_rows || 0}  Start ${compare?.import_start_date || "none"}  Pending ${pending.length}`;
  sub.textContent = subLine;

  const skippedBefore = Number(compare?.skipped_before_start || 0);
  const skippedAfter = Number(compare?.skipped_after_end || 0);
  const summaryCards = `
    <div class="csv-dryrun__summary">
      <div class="csv-dryrun__card">
        <div class="csv-dryrun__k">Update exact</div>
        <div class="csv-dryrun__v">${updExact.length}</div>
      </div>
      <div class="csv-dryrun__card csv-dryrun__card--tip">
        <div class="csv-dryrun__k">Update tip</div>
        <div class="csv-dryrun__v">${updTip.length}</div>
      </div>
      <div class="csv-dryrun__card">
        <div class="csv-dryrun__k">Insert</div>
        <div class="csv-dryrun__v">${toInsert.length}</div>
      </div>
      <div class="csv-dryrun__card">
        <div class="csv-dryrun__k">Pending now</div>
        <div class="csv-dryrun__v">${pending.length}</div>
      </div>
    </div>
  `;

  const skippedNoteParts = [];
  if (skippedBefore > 0) skippedNoteParts.push(`Skipped before import start date: <strong>${skippedBefore}</strong>`);
  if (skippedAfter > 0) skippedNoteParts.push(`Skipped after import end date: <strong>${skippedAfter}</strong>`);
  const skippedNote = skippedNoteParts.length
    ? `<div class="csv-dryrun__note">${skippedNoteParts.join("<br/>")}</div>`
    : "";

  body.innerHTML = `
    ${summaryCards}
    ${skippedNote}

    <section class="csv-dryrun__section">
      <header class="csv-dryrun__section-head"><h4>Will Update (Exact)</h4><span>${updExact.length}</span></header>
      ${_csvDryRowsTable(updExact.slice(0, 250), { showMatch: true })}
    </section>

    <section class="csv-dryrun__section">
      <header class="csv-dryrun__section-head"><h4>Will Update (Tip Adjust)</h4><span>${updTip.length}</span></header>
      ${_csvDryRowsTable(updTip.slice(0, 250), { showMatch: true })}
    </section>

    <section class="csv-dryrun__section">
      <header class="csv-dryrun__section-head"><h4>Will Insert</h4><span>${toInsert.length}</span></header>
      ${_csvDryRowsTable(toInsert.slice(0, 250))}
    </section>

    <section class="csv-dryrun__section">
      <header class="csv-dryrun__section-head"><h4>Current Pending Email Transactions</h4><span>${pending.length}</span></header>
      ${_csvDryRowsTable(pending.slice(0, 500), { showId: true })}
    </section>
  `;
  root.classList.remove("hidden");
}

function closeExtraSavedModal() {
  const root = document.getElementById("extraSavedRoot");
  if (root) root.classList.add("hidden");
}


// =========================
// Spent So Far Breakdown Modal (Excluded + Included + Accordion tx list)
// =========================

function bindSpentRowClick() {
  const row = document.getElementById("mbSpentRow");
  if (!row || row.dataset.bound) return;
  row.dataset.bound = "1";

  row.setAttribute("role", "button");
  row.setAttribute("tabindex", "0");
  row.style.cursor = "pointer";

  row.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    openSpentBreakdown();
  });

  row.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      openSpentBreakdown();
    }
  });
}

function ensureSpentInspectModal() {
  let root = document.getElementById("spentInspectRoot");
  if (root) return root;

  root = document.createElement("div");
  root.id = "spentInspectRoot";
  root.className = "tx-inspect hidden";

  root.innerHTML = `
    <div class="tx-inspect__backdrop" data-spent-close></div>

    <div class="tx-inspect__card" role="dialog" aria-modal="true">
      <div class="tx-inspect__head">
        <div>
          <div id="spentInspectTitle" class="tx-inspect__title">Spent so far</div>
          <div id="spentInspectSub" class="tx-inspect__sub"></div>
        </div>
        <button class="tx-inspect__close" type="button" data-spent-close aria-label="Close">✕</button>
      </div>

      <div id="spentInspectBody" class="tx-inspect__body"></div>
    </div>
  `;

  document.body.appendChild(root);

  root.addEventListener("click", (e) => {
    if (e.target?.matches?.("[data-spent-close]")) closeSpentInspect();
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeSpentInspect();
  });

  return root;
}

function closeSpentInspect() {
  const root = document.getElementById("spentInspectRoot");
  if (root) root.classList.add("hidden");
}

async function openSpentBreakdown() {
  const root = ensureSpentInspectModal();
  root.classList.remove("hidden");

  const titleEl = document.getElementById("spentInspectTitle");
  const subEl   = document.getElementById("spentInspectSub");
  const bodyEl  = document.getElementById("spentInspectBody");

  if (titleEl) titleEl.textContent = "Spent so far";
  if (subEl) subEl.textContent = "Loading";
  if (bodyEl) bodyEl.innerHTML = "";

  // current month range (local)
  const now = new Date();
  const start = new Date(now.getFullYear(), now.getMonth(), 1);
  const startISO = `${start.getFullYear()}-${String(start.getMonth()+1).padStart(2,"0")}-${String(start.getDate()).padStart(2,"0")}`;
  const endISO   = isoLocalDate();

  try {
    const d = await apiGetJson(
      `/spent-so-far-breakdown?start=${encodeURIComponent(startISO)}&end=${encodeURIComponent(endISO)}`,
      { cache: "no-store" }
    );

    if (subEl) subEl.textContent = `${d.start}  ${d.end}  Total: ${money(Number(d.total || 0))}`;

    const excluded = Array.isArray(d.excluded) ? d.excluded : [];
    const included = Array.isArray(d.included) ? d.included : [];

    const excludedHtml = `
      <div style="font-weight:800; margin-bottom:6px;">Excluded categories</div>
      <div style="border-top:1px solid rgba(0,0,0,.08); margin:8px 0;"></div>
      ${excluded.map(x => `
        <div style="display:flex; justify-content:space-between; padding:6px 0;">
          <div style="opacity:.85;">${escapeHtml(x.category)}</div>
          <div style="font-weight:800;">${money(Number(x.total || 0))}</div>
        </div>
      `).join("") || `<div style="opacity:.7;">None</div>`}
      <div style="border-top:1px solid rgba(0,0,0,.08); margin:10px 0;"></div>
    `;

    const includedRows = included.map(x => `
      <div style="border:1px solid rgba(0,0,0,.10); border-radius:10px; margin:8px 0; overflow:hidden;">
        <button type="button"
          data-spent-acc-btn="1"
          data-cat="${escapeHtmlAttr(x.category)}"
          aria-expanded="false"
          style="width:100%; text-align:left; padding:10px 12px; display:flex; justify-content:space-between; gap:12px; background:rgba(0,0,0,.02); border:0; cursor:pointer;">
          <span style="font-weight:750;">${escapeHtml(x.category)}</span>
          <span style="display:flex; align-items:center; gap:10px;">
            <span style="font-weight:800;">${money(Number(x.total || 0))}</span>
            <span style="opacity:.45;"></span>
          </span>
        </button>
        <div data-spent-acc-pane="${escapeHtmlAttr(x.category)}" style="display:none; padding:10px 12px;"></div>
      </div>
    `).join("");

    const includedHtml = `
      <div style="font-weight:800; margin-bottom:6px;">Included categories</div>
      <div style="opacity:.7; font-size:12px; margin-bottom:8px;">Tap a category to see the transactions included in the total.</div>
      <div>${includedRows || `<div style="opacity:.7;">No spending yet.</div>`}</div>
    `;

    bodyEl.innerHTML = excludedHtml + includedHtml;

    // one handler for the accordion
    if (!bodyEl.dataset.spentAccBound) {
      bodyEl.dataset.spentAccBound = "1";
      bodyEl.addEventListener("click", async (e) => {
        const btn = e.target.closest?.("button[data-spent-acc-btn]");
        if (!btn) return;

        const cat = btn.getAttribute("data-cat") || "";
        const pane = bodyEl.querySelector(`[data-spent-acc-pane="${cssEscapeAttr(cat)}"]`);
        if (!pane) return;

        const isOpen = btn.getAttribute("aria-expanded") === "true";
        btn.setAttribute("aria-expanded", String(!isOpen));
        pane.style.display = isOpen ? "none" : "block";

        if (isOpen) return; // closing
        if (pane.dataset.loaded === "1") return;

        pane.dataset.loaded = "1";
        pane.innerHTML = `<div style="opacity:.7;">Loading</div>`;

        try {
          const txData = await apiGetJson(
            `/spent-so-far-transactions?category=${encodeURIComponent(cat)}&start=${encodeURIComponent(startISO)}&end=${encodeURIComponent(endISO)}`,
            { cache: "no-store" }
          );
          const tx = (txData && txData.transactions) || [];

          if (!tx.length) {
            pane.innerHTML = `<div style="opacity:.7;">No transactions.</div>`;
            return;
          }

          pane.innerHTML = tx.map(r => `
            <div style="display:flex; justify-content:space-between; gap:12px; padding:8px 0; border-bottom:1px solid rgba(0,0,0,.06);">
              <div style="min-width:0;">
                <div style="font-weight:750; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${escapeHtml(r.merchant || "")}</div>
                <div style="opacity:.65; font-size:12px;">${escapeHtml(r.date || "")}${(r.bank || r.card) ? "  " + escapeHtml(`${r.bank || ""}${r.card ? "  " + r.card : ""}`.trim()) : ""}</div>
              </div>
              <div style="font-weight:800; white-space:nowrap;">${money(Number(r.amount || 0))}</div>
            </div>
          `).join("");
        } catch (err) {
          console.error(err);
          pane.innerHTML = `<div style="opacity:.8;">Failed to load transactions.</div>`;
        }
      });
    }
  } catch (err) {
    console.error(err);
    if (subEl) subEl.textContent = "Failed to load";
    if (bodyEl) bodyEl.innerHTML = `<div style="opacity:.8;">Could not load spent breakdown.</div>`;
  }
}

async function fetchCategoryTx(category, start, end, limit = 500) {
  const catParam = (String(category || "") === "")
    ? "__NULL__"
    : String(category);

  const url =
    `/category-transactions?category=${encodeURIComponent(catParam)}&start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}&limit=${encodeURIComponent(limit)}`;

  const rows = await apiGetJson(url, { cache: "no-store" });
  return Array.isArray(rows) ? rows : [];
}

function renderSpentSection(title, items, { muted = false } = {}) {
  const rows = (items || []).map(x => `
    <div style="display:flex; justify-content:space-between; gap:12px; padding:6px 0; border-bottom:1px solid rgba(0,0,0,.06);">
      <div style="opacity:${muted ? ".75" : "1"};">${escapeHtml(x.category || "")}</div>
      <div style="font-weight:700; opacity:${muted ? ".75" : "1"};">${money(Number(x.total || 0))}</div>
    </div>
  `).join("");

  return `
    <div style="font-weight:800; margin-bottom:6px;">${escapeHtml(title)}</div>
    <div>${rows || `<div style="opacity:.7;">None</div>`}</div>
  `;
}

function renderIncludedAccordion(included, { start, end }) {
  const rows = (included || []).map(x => `
    <div style="border:1px solid rgba(0,0,0,.10); border-radius:10px; margin:8px 0; overflow:hidden;">
      <button type="button"
        data-spent-acc-btn
        data-cat-key="${escapeHtmlAttr(x.key)}"
        aria-expanded="false"
        style="width:100%; text-align:left; padding:10px 12px; display:flex; justify-content:space-between; gap:12px; background:rgba(0,0,0,.02); border:0; cursor:pointer;">
        <span style="font-weight:750;">${escapeHtml(x.label)}</span>
        <span style="display:flex; align-items:center; gap:10px;">
          <span style="font-weight:800;">${money(x.total)}</span>
          <span style="opacity:.45;"></span>
        </span>
      </button>
      <div data-spent-acc-pane="${escapeHtmlAttr(x.key)}" style="display:none; padding:10px 12px;"></div>
    </div>
  `).join("");

  return `
    <div style="font-weight:800; margin-bottom:6px;">Included categories</div>
    <div style="opacity:.7; font-size:12px; margin-bottom:8px;">Tap a category to see the transactions included in the total.</div>
    <div>${rows || `<div style="opacity:.7;">No spending yet.</div>`}</div>
  `;
}

function renderTxMiniList(rows) {
  const tx = Array.isArray(rows) ? rows : [];
  if (!tx.length) return `<div style="opacity:.7;">No transactions.</div>`;

  // same effective date behavior you use elsewhere
  const lines = tx.map(r => {
    const d = r.postedDate || r.dateISO || "";
    const m = (r.merchant || "").toString();
    const amt = Number(r.amount || 0);
    const bank = r.bank || "";
    const card = r.card || "";
    const sub = `${bank}${card ? "  " + card : ""}`.trim();

    return `
      <div style="display:flex; justify-content:space-between; gap:12px; padding:8px 0; border-bottom:1px solid rgba(0,0,0,.06);">
        <div style="min-width:0;">
          <div style="font-weight:750; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${escapeHtml(m || "")}</div>
          <div style="opacity:.65; font-size:12px;">${escapeHtml(d)}${sub ? "  " + escapeHtml(sub) : ""}</div>
        </div>
        <div style="font-weight:800; white-space:nowrap;">${money(amt)}</div>
      </div>
    `;
  }).join("");

  return `<div>${lines}</div>`;
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
          <div id="txInspectSub" class="tx-inspect__sub"></div>
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

async function openTxInspect(txId) {
  try {
    const data = await apiGetJson(`/transaction/${encodeURIComponent(txId)}`);
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
    const bankCard = `${tx.bank || ""}${tx.card ? "  " + tx.card : ""}`.trim();

    if (titleEl) titleEl.textContent = merchant;
    if (subEl) subEl.textContent = `${amount}${bankCard ? "  " + bankCard : ""}  id ${tx.id ?? txId}`;

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



