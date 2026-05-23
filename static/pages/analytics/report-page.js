import { apiGetJson } from "/static/shared/api.module.js";
import { money } from "/static/shared/format.module.js";

function esc(v) {
  return String(v == null ? "" : v)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function setStatus(msg, isErr = false) {
  const el = document.getElementById("reportStatus");
  if (!el) return;
  el.textContent = String(msg || "");
  el.style.color = isErr ? "#b42318" : "";
}

function thisMonthValue() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function fmtMonth(yyyyMm) {
  const m = /^(\d{4})-(\d{2})$/.exec(String(yyyyMm || ""));
  if (!m) return String(yyyyMm || "Monthly Report");
  const d = new Date(Number(m[1]), Number(m[2]) - 1, 1);
  return d.toLocaleString("en-US", { month: "long", year: "numeric" });
}

function postClientSignal(source, message) {
  try {
    const payload = {
      source: String(source || "analytics_client"),
      message: String(message || ""),
      page_url: String(window.location.href || "").slice(0, 1000),
      route: `${window.location.pathname || "/"}${window.location.search || ""}`,
      status_code: 0,
    };
    if (navigator?.sendBeacon) {
      const blob = new Blob([JSON.stringify(payload)], { type: "application/json" });
      navigator.sendBeacon("/admin/error-notifications/client", blob);
      return;
    }
    fetch("/admin/error-notifications/client", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      keepalive: true,
    }).catch(() => {});
  } catch (_) {}
}

function renderLoadingScaffold() {
  const ids = [
    "summaryGrid",
    "categoryBreakdown",
    "savingsSummary",
    "liquidSummary",
    "debtSummary",
    "biggestTransactions",
    "recurringHits",
    "budgetPerformance",
    "changesVsPrev",
  ];
  ids.forEach((id) => {
    const el = document.getElementById(id);
    if (!el || el.dataset.loaded === "1") return;
    el.innerHTML = `<div class="analytics-empty">Loading...</div>`;
  });
}

function renderDataUnavailableFallback() {
  const ids = [
    "summaryGrid",
    "categoryBreakdown",
    "savingsSummary",
    "liquidSummary",
    "debtSummary",
    "biggestTransactions",
    "recurringHits",
    "budgetPerformance",
    "changesVsPrev",
  ];
  ids.forEach((id) => {
    const el = document.getElementById(id);
    if (!el || el.dataset.loaded === "1") return;
    el.innerHTML = `<div class="analytics-empty">Could not load data.</div>`;
  });
  postClientSignal("analytics_empty_render", "Analytics fallback rendered due to missing payload.");
}

function markLoaded(ids) {
  ids.forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.dataset.loaded = "1";
  });
}

function renderHero(month, s, c) {
  const m = document.getElementById("heroMonth");
  const n = document.getElementById("heroNet");
  const ch = document.getElementById("heroChips");
  if (m) m.textContent = fmtMonth(month);
  if (n) n.textContent = `Net ${money((s && s.net) || 0)}`;
  if (!ch) return;

  const ip = Number((c && c.income_change_pct) || 0);
  const sp = Number((c && c.spending_change_pct) || 0);
  ch.innerHTML =
    `<span class="hero-chip">Income ${esc(money((s && s.income) || 0))}</span>` +
    `<span class="hero-chip">Spending ${esc(money((s && s.spending) || 0))}</span>` +
    `<span class="hero-chip ${ip >= 0 ? "up" : "down"}">${ip >= 0 ? "Income up " : "Income down "}${esc((ip > 0 ? "+" : "") + ip.toFixed(1) + "%")}</span>` +
    `<span class="hero-chip ${sp <= 0 ? "up" : "down"}">${sp <= 0 ? "Spending down " : "Spending up "}${esc((sp > 0 ? "+" : "") + sp.toFixed(1) + "%")}</span>`;
}

function renderSummary(s) {
  const h = document.getElementById("summaryGrid");
  if (!h) return;
  h.innerHTML = [
    ["Income", s && s.income, "is-income"],
    ["Spending", s && s.spending, "is-spending"],
    ["Net", s && s.net, "is-net"],
    ["Starting Balance", s && s.starting_balance, "is-starting"],
    ["Ending Balance", s && s.ending_balance, "is-ending"],
  ].map((r) => `<div class="metric ${r[2]}"><div class="label">${esc(r[0])}</div><div class="value">${esc(money(r[1]))}</div></div>`).join("");
  markLoaded(["summaryGrid"]);
}

function renderTable(hostId, rows, headers, emptyText) {
  const h = document.getElementById(hostId);
  if (!h) return;
  if (!rows || !rows.length) {
    h.innerHTML = `<div class="analytics-empty">${esc(emptyText)}</div>`;
    markLoaded([hostId]);
    return;
  }
  h.innerHTML = `<table class="analytics-table"><thead><tr>${headers.map((x) => `<th class="${esc(x.cls || "")}">${esc(x.label)}</th>`).join("")}</tr></thead><tbody>${rows.map((r) => `<tr>${headers.map((x) => {
    const raw = typeof x.get === "function" ? x.get(r) : r[x.key];
    const val = x.money ? money(Number(raw || 0)) : raw;
    return `<td class="${esc(x.cls || "")}">${esc(val == null ? "" : val)}</td>`;
  }).join("")}</tr>`).join("")}</tbody></table>`;
  markLoaded([hostId]);
}

function renderCategory(rows) {
  const h = document.getElementById("categoryBreakdown");
  if (!h) return;
  if (!rows || !rows.length) {
    h.innerHTML = '<div class="analytics-empty">No category spending in this month.</div>';
    markLoaded(["categoryBreakdown"]);
    return;
  }
  let max = 0;
  rows.forEach((r) => { max = Math.max(max, Number((r && r.amount) || 0)); });
  h.innerHTML = `<table class="analytics-table"><thead><tr><th>Category</th><th>Share</th><th class="align-right">Spent</th></tr></thead><tbody>${rows.map((r) => {
    const a = Number((r && r.amount) || 0);
    const w = max > 0 ? Math.max(5, Math.round((a / max) * 100)) : 0;
    return `<tr><td>${esc((r && r.category) || "Uncategorized")}</td><td class="bar-cell"><div class="bar-wrap"><div class="bar-fill" style="width:${w}%"></div></div></td><td class="align-right mono">${esc(money(a))}</td></tr>`;
  }).join("")}</tbody></table>`;
  markLoaded(["categoryBreakdown"]);
}

function renderChanges(ch) {
  const h = document.getElementById("changesVsPrev");
  if (!h) return;
  const ip = Number((ch && ch.income_change_pct) || 0);
  const sp = Number((ch && ch.spending_change_pct) || 0);
  h.innerHTML = `<table class="analytics-table"><thead><tr><th>Metric</th><th class="align-right">Prev Month</th><th class="align-right">Change</th><th class="align-right">% Change</th></tr></thead><tbody>
  <tr><td>Income</td><td class="align-right mono">${esc(money(Number((ch && ch.income_prev_month) || 0)))}</td><td class="align-right mono">${esc(money(Number((ch && ch.income_change_abs) || 0)))}</td><td class="align-right mono"><span class="pill ${ip >= 0 ? "up" : "down"}">${esc((ip > 0 ? "+" : "") + ip.toFixed(1) + "%")}</span></td></tr>
  <tr><td>Spending</td><td class="align-right mono">${esc(money(Number((ch && ch.spending_prev_month) || 0)))}</td><td class="align-right mono">${esc(money(Number((ch && ch.spending_change_abs) || 0)))}</td><td class="align-right mono"><span class="pill ${sp <= 0 ? "up" : "down"}">${esc((sp > 0 ? "+" : "") + sp.toFixed(1) + "%")}</span></td></tr>
  </tbody></table>`;
  markLoaded(["changesVsPrev"]);
}

async function loadReport() {
  const mEl = document.getElementById("reportMonth");
  const month = String((mEl && mEl.value) || "").trim() || thisMonthValue();
  setStatus("Loading report...");
  renderLoadingScaffold();
  try {
    const out = await apiGetJson(`/reports/monthly?month=${encodeURIComponent(month)}`, { cache: "no-store" });
    const summary = (out && out.summary) || {};
    const changes = (out && out.changes_vs_previous_month) || {};
    const accounts = Array.isArray(out && out.account_summary) ? out.account_summary : [];

    renderHero((out && out.month) || month, summary, changes);
    renderSummary(summary);
    renderCategory((out && out.category_breakdown) || []);

    renderTable(
      "savingsSummary",
      accounts.filter((r) => String((r && r.account_type) || "").toLowerCase() === "savings"),
      [
        { label: "Account", get: (r) => `${(r && r.bank) || ""} ${(r && r.name) || ""}`.trim() },
        { label: "Start", cls: "align-right mono", key: "start_balance", money: true },
        { label: "End", cls: "align-right mono", key: "end_balance", money: true },
        { label: "Change", cls: "align-right mono", key: "change", money: true },
      ],
      "No savings accounts found.",
    );

    renderTable(
      "liquidSummary",
      accounts.filter((r) => {
        const t = String((r && r.account_type) || "").toLowerCase();
        return t === "checking" || t === "debit" || t === "cash";
      }),
      [
        { label: "Account", get: (r) => `${(r && r.bank) || ""} ${(r && r.name) || ""}`.trim() },
        { label: "Start", cls: "align-right mono", key: "start_balance", money: true },
        { label: "End", cls: "align-right mono", key: "end_balance", money: true },
        { label: "Change", cls: "align-right mono", key: "change", money: true },
      ],
      "No liquid accounts found.",
    );

    renderTable(
      "debtSummary",
      accounts.filter((r) => String((r && r.account_type) || "").toLowerCase() === "credit"),
      [
        { label: "Account", get: (r) => `${(r && r.bank) || ""} ${(r && r.name) || ""}`.trim() },
        { label: "Start", cls: "align-right mono", key: "start_balance", money: true },
        { label: "End", cls: "align-right mono", key: "end_balance", money: true },
        { label: "Change", cls: "align-right mono", key: "change", money: true },
      ],
      "No debt accounts found.",
    );

    const tx = (out && out.biggest_transactions) || {};
    renderTable(
      "biggestTransactions",
      [...(Array.isArray(tx.outflows) ? tx.outflows : []), ...(Array.isArray(tx.inflows) ? tx.inflows : [])],
      [
        { label: "Date", key: "date" },
        { label: "Merchant", key: "merchant" },
        { label: "Category", key: "category" },
        { label: "Amount", cls: "align-right mono", key: "amount", money: true },
      ],
      "No transactions in this month.",
    );

    renderTable(
      "recurringHits",
      (out && out.recurring_subscriptions) || [],
      [
        { label: "Merchant", key: "merchant" },
        { label: "Category", key: "category" },
        { label: "Hits", cls: "align-right mono", key: "hits" },
        { label: "Total", cls: "align-right mono", key: "total", money: true },
      ],
      "No recurring/subscription hits detected this month.",
    );

    renderTable(
      "budgetPerformance",
      [((out && out.budget_performance) || {})],
      [
        { label: "Planned", cls: "align-right mono", key: "planned_allocations", money: true },
        { label: "Actual", cls: "align-right mono", key: "actual_spent_on_allocated", money: true },
        { label: "Remaining", cls: "align-right mono", key: "remaining_allocated", money: true },
        { label: "Free Spend", cls: "align-right mono", key: "free_spend_so_far", money: true },
      ],
      "No budget data.",
    );

    renderChanges(changes);
    setStatus(`Loaded ${(out && out.month) || month} report.`);
  } catch (err) {
    console.error(err);
    setStatus("Failed to load report.", true);
    renderDataUnavailableFallback();
  }
}

function bind() {
  const monthEl = document.getElementById("reportMonth");
  if (monthEl && !monthEl.value) monthEl.value = thisMonthValue();
  const refreshBtn = document.getElementById("reportRefreshBtn");
  if (refreshBtn) refreshBtn.addEventListener("click", loadReport);
  const pdfBtn = document.getElementById("reportDownloadPdfBtn");
  if (pdfBtn) pdfBtn.addEventListener("click", () => window.print());
}

function boot() {
  window.__analyticsBootRan = true;
  bind();
  setStatus("Ready.");
  loadReport();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", boot, { once: true });
} else {
  boot();
}
