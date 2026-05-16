function money(v) {
  const fn = window && window.SharedFormat && window.SharedFormat.money;
  if (typeof fn === "function") return fn(v);
  const n = Number(v || 0);
  return n.toLocaleString("en-US", { style: "currency", currency: "USD" });
}

async function apiGetJson(url, options = {}) {
  const fn = window && window.SharedApi && window.SharedApi.apiGetJson;
  if (typeof fn === "function") return fn(url, options);
  const res = await fetch(url, { cache: options.cache || "no-store", credentials: "same-origin" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

function esc(v) {
  return String(v == null ? "" : v)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function fmtPct(v) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return "n/a";
  const n = Number(v);
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(1)}%`;
}

function fmtMonth(yyyyMm) {
  const txt = String(yyyyMm || "");
  const m = /^(\d{4})-(\d{2})$/.exec(txt);
  if (!m) return txt || "Monthly Report";
  const year = Number(m[1]);
  const month = Number(m[2]);
  const d = new Date(year, month - 1, 1);
  return d.toLocaleString("en-US", { month: "long", year: "numeric" });
}

function renderHero(month, summary, changes) {
  const monthEl = document.getElementById("heroMonth");
  const netEl = document.getElementById("heroNet");
  const chipsEl = document.getElementById("heroChips");
  if (monthEl) monthEl.textContent = fmtMonth(month);
  if (netEl) netEl.textContent = `Net ${money(Number((summary && summary.net) || 0))}`;
  if (!chipsEl) return;

  const spendingPct = fmtPct(changes && changes.spending_change_pct);
  const incomePct = fmtPct(changes && changes.income_change_pct);
  const spendUp = Number((changes && changes.spending_change_abs) || 0) > 0;
  const incomeUp = Number((changes && changes.income_change_abs) || 0) > 0;

  chipsEl.innerHTML = [
    `<span class="hero-chip">Income ${esc(money(Number((summary && summary.income) || 0)))}</span>`,
    `<span class="hero-chip">Spending ${esc(money(Number((summary && summary.spending) || 0)))}</span>`,
    `<span class="hero-chip ${incomeUp ? "up" : "down"}">${esc(incomeUp ? "Income up" : "Income down")} ${esc(incomePct)}</span>`,
    `<span class="hero-chip ${spendUp ? "down" : "up"}">${esc(spendUp ? "Spending up" : "Spending down")} ${esc(spendingPct)}</span>`,
  ].join("");
}

function setStatus(msg, isErr = false) {
  const el = document.getElementById("reportStatus");
  if (!el) return;
  el.textContent = String(msg || "");
  el.style.color = isErr ? "#b42318" : "";
}

function thisMonthValue() {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  return `${y}-${m}`;
}

function renderSummary(summary) {
  const host = document.getElementById("summaryGrid");
  if (!host) return;
  const ending = Number((summary && summary.ending_balance) || 0);
  const starting = Number((summary && summary.starting_balance) || 0);
  const deltaBal = ending - starting;
  const items = [
    ["Income", money(Number((summary && summary.income) || 0)), "is-income", ""],
    ["Spending", money(Number((summary && summary.spending) || 0)), "is-spending", ""],
    ["Net", money(Number((summary && summary.net) || 0)), "is-net", ""],
    ["Starting Balance", money(starting), "is-starting", ""],
    ["Ending Balance", money(ending), "is-ending", `${deltaBal >= 0 ? "+" : ""}${money(deltaBal)} vs start`],
  ];
  host.innerHTML = items.map(([label, value, klass, sub]) => `
    <div class="metric ${klass}">
      <div class="label">${esc(label)}</div>
      <div class="value">${esc(value)}</div>
      ${sub ? `<div class="sub">${esc(sub)}</div>` : ""}
    </div>
  `).join("");
}

function renderCategoryBreakdown(rows) {
  const host = document.getElementById("categoryBreakdown");
  if (!host) return;
  const list = Array.isArray(rows) ? rows : [];
  if (!list.length) {
    host.innerHTML = `<div class="analytics-empty">No category spending in this month.</div>`;
    return;
  }
  let maxAmount = 0;
  for (let i = 0; i < list.length; i += 1) {
    const a = Number((list[i] && list[i].amount) || 0);
    if (a > maxAmount) maxAmount = a;
  }
  host.innerHTML = `
    <table class="analytics-table">
      <thead>
        <tr><th>Category</th><th>Share</th><th class="align-right">Amount</th></tr>
      </thead>
      <tbody>
        ${list.map((r) => `
          <tr>
            <td>${esc((r && r.category) || "Uncategorized")}</td>
            <td class="bar-cell">
              <div class="bar-wrap">
                <div class="bar-fill" style="width:${maxAmount > 0 ? Math.max(5, Math.round((Number((r && r.amount) || 0) / maxAmount) * 100)) : 0}%"></div>
              </div>
            </td>
            <td class="align-right mono">${esc(money(Number((r && r.amount) || 0)))}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
}

function renderAccountSummary(rows) {
  const host = document.getElementById("accountSummary");
  if (!host) return;
  const raw = Array.isArray(rows) ? rows : [];
  const list = raw.filter((r) => {
    const t = String((r && r.account_type) || "").toLowerCase();
    return t === "credit" || t === "savings";
  });
  if (!list.length) {
    host.innerHTML = `<div class="analytics-empty">No credit or savings accounts found.</div>`;
    return;
  }
  function moneyCR(v) {
    const n = Number(v || 0);
    if (n < 0) return `${money(Math.abs(n))} CR`;
    return money(n);
  }
  host.innerHTML = `
    <table class="analytics-table">
      <thead>
        <tr>
          <th>Account</th>
          <th>Category</th>
          <th class="align-right">Start</th>
          <th class="align-right">End</th>
          <th class="align-right">Change</th>
        </tr>
      </thead>
      <tbody>
        ${list.map((r) => `
          <tr>
            <td>${esc(`${(r && r.bank) || ""} ${(r && r.name) || ""}`.trim())}</td>
            <td>${esc(String((r && r.account_type) || "").toLowerCase() === "credit" ? "Debt" : "Savings")}</td>
            <td class="align-right mono">${esc(moneyCR(Number((r && r.start_balance) || 0)))}</td>
            <td class="align-right mono">${esc(moneyCR(Number((r && r.end_balance) || 0)))}</td>
            <td class="align-right mono">${esc(moneyCR(Number((r && r.change) || 0)))}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
}

function renderBiggestTransactions(block) {
  const host = document.getElementById("biggestTransactions");
  if (!host) return;
  const outflows = Array.isArray(block && block.outflows) ? block.outflows : [];
  const inflows = Array.isArray(block && block.inflows) ? block.inflows : [];

  const renderRows = (rows, title) => {
    if (!rows.length) return `<div class="analytics-empty">${esc(title)}: none</div>`;
    return `
      <div style="margin-bottom:10px;">
        <div style="font-weight:600; margin-bottom:4px;">${esc(title)}</div>
        <table class="analytics-table">
          <thead><tr><th>Date</th><th>Merchant</th><th>Category</th><th class="align-right">Amount</th></tr></thead>
          <tbody>
            ${rows.map((r) => `
              <tr>
                <td>${esc((r && r.date) || "")}</td>
                <td>${esc((r && r.merchant) || "")}</td>
                <td>${esc((r && r.category) || "")}</td>
                <td class="align-right mono">${esc(money(Number((r && r.amount) || 0)))}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    `;
  };

  host.innerHTML = `${renderRows(outflows, "Top Outflows")}${renderRows(inflows, "Top Inflows")}`;
}

function renderRecurring(rows) {
  const host = document.getElementById("recurringHits");
  if (!host) return;
  const list = Array.isArray(rows) ? rows : [];
  if (!list.length) {
    host.innerHTML = `<div class="analytics-empty">No recurring/subscription hits detected this month.</div>`;
    return;
  }
  host.innerHTML = `
    <table class="analytics-table">
      <thead>
        <tr><th>Merchant</th><th>Category</th><th class="align-right">Hits</th><th class="align-right">Total</th></tr>
      </thead>
      <tbody>
        ${list.map((r) => `
          <tr>
            <td>${esc((r && r.merchant) || "")}</td>
            <td>${esc((r && r.category) || "")}</td>
            <td class="align-right mono">${esc(Number((r && r.hits) || 0))}</td>
            <td class="align-right mono">${esc(money(Number((r && r.total) || 0)))}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
}

function renderBudget(block) {
  const host = document.getElementById("budgetPerformance");
  if (!host) return;
  const planned = Number((block && block.planned_allocations) || 0);
  const actual = Number((block && block.actual_spent_on_allocated) || 0);
  const remaining = Number((block && block.remaining_allocated) || 0);
  const freeSpend = Number((block && block.free_spend_so_far) || 0);
  host.innerHTML = `
    <div class="analytics-metric-grid">
      <div class="metric"><div class="label">Planned Allocations</div><div class="value">${esc(money(planned))}</div></div>
      <div class="metric"><div class="label">Actual on Allocated</div><div class="value">${esc(money(actual))}</div></div>
      <div class="metric"><div class="label">Remaining Allocated</div><div class="value">${esc(money(remaining))}</div></div>
      <div class="metric"><div class="label">Free Spend So Far</div><div class="value">${esc(money(freeSpend))}</div></div>
    </div>
  `;
}

function renderChanges(block) {
  const host = document.getElementById("changesVsPrev");
  if (!host) return;
  const incomeDelta = Number((block && block.income_change_abs) || 0);
  const spendDelta = Number((block && block.spending_change_abs) || 0);
  host.innerHTML = `
    <table class="analytics-table">
      <thead><tr><th>Metric</th><th class="align-right">Prev Month</th><th class="align-right">Change</th><th class="align-right">% Change</th></tr></thead>
      <tbody>
        <tr>
          <td>Income</td>
          <td class="align-right mono">${esc(money(Number((block && block.income_prev_month) || 0)))}</td>
          <td class="align-right mono">${esc(money(Number((block && block.income_change_abs) || 0)))}</td>
          <td class="align-right mono"><span class="pill ${incomeDelta >= 0 ? "up" : "down"}">${esc(fmtPct(block && block.income_change_pct))}</span></td>
        </tr>
        <tr>
          <td>Spending</td>
          <td class="align-right mono">${esc(money(Number((block && block.spending_prev_month) || 0)))}</td>
          <td class="align-right mono">${esc(money(Number((block && block.spending_change_abs) || 0)))}</td>
          <td class="align-right mono"><span class="pill ${spendDelta <= 0 ? "up" : "down"}">${esc(fmtPct(block && block.spending_change_pct))}</span></td>
        </tr>
      </tbody>
    </table>
  `;
}

async function loadReport() {
  const monthEl = document.getElementById("reportMonth");
  const month = String((monthEl && monthEl.value) || "").trim() || thisMonthValue();
  setStatus("Loading report...");
  try {
    const out = await apiGetJson(`/reports/monthly?month=${encodeURIComponent(month)}`, { cache: "no-store" });
    renderSummary((out && out.summary) || {});
    renderHero((out && out.month) || month, (out && out.summary) || {}, (out && out.changes_vs_previous_month) || {});
    renderCategoryBreakdown((out && out.category_breakdown) || []);
    renderAccountSummary((out && out.account_summary) || []);
    renderBiggestTransactions((out && out.biggest_transactions) || {});
    renderRecurring((out && out.recurring_subscriptions) || []);
    renderBudget((out && out.budget_performance) || {});
    renderChanges((out && out.changes_vs_previous_month) || {});
    setStatus(`Loaded ${(out && out.month) || month} report.`);
  } catch (err) {
    console.error(err);
    setStatus("Failed to load monthly report.", true);
  }
}

function bind() {
  setStatus("Ready.");
  const monthEl = document.getElementById("reportMonth");
  if (monthEl && !monthEl.value) monthEl.value = thisMonthValue();

  const refreshBtn = document.getElementById("reportRefreshBtn");
  if (refreshBtn) {
    refreshBtn.addEventListener("click", function () {
      loadReport();
    });
  }
  const downloadBtn = document.getElementById("reportDownloadPdfBtn");
  if (downloadBtn) {
    downloadBtn.addEventListener("click", function () {
      window.print();
    });
  }
}

function boot() {
  try {
    bind();
    loadReport();
  } catch (err) {
    console.error(err);
    setStatus("Analytics boot failed.", true);
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", boot, { once: true });
} else {
  boot();
}
