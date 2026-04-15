import { money } from "/static/shared/format.module.js";
import { formatMMMdd } from "/static/shared/dates.module.js";

let spendingChart = null;
let chartView = 0;
let spendingDayPanelLock = null;

const SPENDING_VIEWS = [
  { title: "Spending" },
  { title: "Spending • Categories" },
  { title: "Unbudgeted vs Daily Safe" },
];

const SPENDING_IDS = {
  title: "spChartTitle",
  dots: "spChartDots",
  toggle: null,
  breakLabel: "spBreakLabel",
  growthLabel: "spGrowthLabel",
  growthValue: "spGrowthValue",
  breakValue: "spBreakValue",
  quarters: "spQuarterButtons",
  yearBack: "spYearBack",
  yearLabel: "spYearLabel",
  yearFwd: "spYearFwd",
  update: "spUpdateBtn",
  start: "sp-start",
  end: "sp-end",
  canvas: "spChart",
  monthButtons: "spMonthButtons",
};

// Cache currently selected date range data so Next can re-render without refetch.
let lastPayload = {
  start: null,
  end: null,
  spendingSeries: [],
  categoryRows: [],
  unbudgetedSafeSeries: [],
};

function renderViewDots() {
  const host = document.getElementById(SPENDING_IDS.dots);
  if (!host) return;
  host.innerHTML = "";
  SPENDING_VIEWS.forEach((_, i) => {
    const dot = document.createElement("span");
    dot.className = "chart-dot" + (i === chartView ? " active" : "");
    host.appendChild(dot);
  });
}

function setTitleForView() {
  const el = document.getElementById(SPENDING_IDS.title);
  if (!el) return;
  el.textContent = SPENDING_VIEWS[chartView]?.title || "Spending";
}

function updateNextBtnLabel() {
  const btn = document.getElementById("spNextBtn");
  if (!btn) return;
  btn.textContent = "Next ▶";
}

function destroyChart() {
  if (!spendingChart) return;
  spendingChart.destroy();
  spendingChart = null;
}

function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function lockBodyForPanel() {
  if (spendingDayPanelLock) return;
  const y = window.scrollY || document.documentElement.scrollTop || 0;
  const body = document.body;
  spendingDayPanelLock = { y, hadModalOpen: body.classList.contains("modal-open") };
  body.classList.add("modal-open");
  body.style.position = "fixed";
  body.style.top = `-${y}px`;
  body.style.left = "0";
  body.style.right = "0";
  body.style.width = "100%";
}

function unlockBodyForPanel() {
  if (!spendingDayPanelLock) return;
  const body = document.body;
  const lock = spendingDayPanelLock;
  spendingDayPanelLock = null;
  if (!lock.hadModalOpen) body.classList.remove("modal-open");
  body.style.position = "";
  body.style.top = "";
  body.style.left = "";
  body.style.right = "";
  body.style.width = "";
  window.scrollTo(0, lock.y || 0);
}

function ensureSpendingDayPanel() {
  let overlay = document.getElementById("spendingDayOverlay");
  let panel = document.getElementById("spendingDayPanel");
  if (overlay && panel) return { overlay, panel };

  overlay = document.createElement("div");
  overlay.id = "spendingDayOverlay";
  overlay.className = "overlay hidden";
  overlay.setAttribute("aria-hidden", "true");

  panel = document.createElement("aside");
  panel.id = "spendingDayPanel";
  panel.className = "side-panel hidden spending-day-panel";
  panel.setAttribute("aria-hidden", "true");
  panel.innerHTML = `
    <div class="panel-header">
      <div>
        <div class="panel-title">Day Purchases</div>
        <div class="panel-subtitle" id="spendingDaySubtitle"></div>
      </div>
      <button class="top-btn" id="spendingDayCloseBtn" type="button" aria-label="Close">✕</button>
    </div>
    <div class="panel-body">
      <div class="spending-day-totals" id="spendingDayTotals"></div>
      <div class="spending-day-list" id="spendingDayList"></div>
    </div>
  `;

  document.body.appendChild(overlay);
  document.body.appendChild(panel);

  const close = () => closeSpendingDayPanel();
  overlay.addEventListener("click", close);
  panel.querySelector("#spendingDayCloseBtn")?.addEventListener("click", close);

  return { overlay, panel };
}

function closeSpendingDayPanel() {
  const overlay = document.getElementById("spendingDayOverlay");
  const panel = document.getElementById("spendingDayPanel");
  if (overlay) {
    overlay.classList.add("hidden");
    overlay.setAttribute("aria-hidden", "true");
  }
  if (panel) {
    panel.classList.add("hidden");
    panel.setAttribute("aria-hidden", "true");
  }
  unlockBodyForPanel();
}

async function openSpendingDayPanel(dayIso) {
  const { overlay, panel } = ensureSpendingDayPanel();
  const subtitle = panel.querySelector("#spendingDaySubtitle");
  const totals = panel.querySelector("#spendingDayTotals");
  const list = panel.querySelector("#spendingDayList");
  if (subtitle) subtitle.textContent = String(dayIso || "");
  if (totals) totals.textContent = "Loading...";
  if (list) list.innerHTML = "";

  overlay.classList.remove("hidden");
  panel.classList.remove("hidden");
  overlay.setAttribute("aria-hidden", "false");
  panel.setAttribute("aria-hidden", "false");
  lockBodyForPanel();

  try {
    const res = await fetch(`/spending-unbudgeted-day?day=${encodeURIComponent(dayIso)}`, {
      cache: "no-store",
      credentials: "same-origin",
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const out = await res.json().catch(() => ({}));
    const purchases = Array.isArray(out?.purchases) ? out.purchases : [];
    const day = String(out?.day || dayIso || "");
    const total = Number(out?.totals?.unbudgeted_spend || 0);
    const safe = Number(out?.totals?.daily_safe_to_spend || 0);

    if (subtitle) subtitle.textContent = day;
    if (totals) {
      totals.innerHTML = `
        <div class="spending-day-chip">Unbudgeted: <strong>${money(total)}</strong></div>
        <div class="spending-day-chip">Safe/day: <strong>${money(safe)}</strong></div>
      `;
    }

    if (list) {
      if (!purchases.length) {
        list.innerHTML = `<div class="spending-day-empty">No purchases for this day.</div>`;
      } else {
        list.innerHTML = purchases
          .map((p) => {
            const kind = String(p?.kind || "purchase");
            const merchant = escapeHtml(p?.merchant || "(no merchant)");
            const category = escapeHtml(p?.category || "Unassigned");
            const bank = escapeHtml(p?.bank || "");
            const account = escapeHtml(p?.account || "");
            const amount = money(Number(p?.amount || 0));
            return `
              <div class="spending-day-row ${kind === "roundup" ? "is-roundup" : ""}">
                <div class="spending-day-row-main">
                  <div class="spending-day-row-merchant">${merchant}</div>
                  <div class="spending-day-row-sub">${category}${bank || account ? ` • ${bank}${account ? ` / ${account}` : ""}` : ""}</div>
                </div>
                <div class="spending-day-row-amt">${amount}</div>
              </div>
            `;
          })
          .join("");
      }
    }
  } catch (_) {
    if (totals) totals.textContent = "Failed to load.";
    if (list) list.innerHTML = `<div class="spending-day-empty">Could not load day purchases.</div>`;
  }
}

async function fetchCategoryTotalsWithUnknown(start, end) {
  const res = await fetch(`/category-totals-range?start=${start}&end=${end}`);
  const data = await res.json();

  const rows = (Array.isArray(data) ? data : [])
    .map((r) => ({ category: String(r.category ?? ""), total: Number(r.total ?? 0) }))
    .filter((r) => r.category && Number.isFinite(r.total));

  const unkRes = await fetch(`/unknown-merchant-total-range?start=${start}&end=${end}`);
  if (unkRes.ok) {
    const payload = await unkRes.json();
    const total = Number(payload?.total || 0);
    const txCount = Number(payload?.tx_count || 0);
    if (total > 0 && txCount > 0) {
      rows.push({
        category: `Unknown merchant (${txCount})`,
        total,
        _linkCategory: "Unknown merchant",
      });
    }
  }

  rows.sort((a, b) => (Number(b.total) || 0) - (Number(a.total) || 0));
  return rows;
}

async function fetchUnbudgetedVsSafeSeries(start, end) {
  const res = await fetch(`/spending-unbudgeted-safe-range?start=${start}&end=${end}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const out = await res.json().catch(() => ({}));
  return Array.isArray(out?.series) ? out.series : [];
}

function renderSpendingCategoryList(rows) {
  const wrap = document.getElementById("spendingCategoryList");
  if (!wrap) return;
  wrap.innerHTML = "";

  rows.forEach((r) => {
    const btn = document.createElement("button");
    btn.className = "category-pill";
    btn.innerHTML = `<span>${r.category}</span><span>${money(r.total)}</span>`;

    const catForLink = r._linkCategory || r.category;
    btn.onclick = () => {
      location.href = `/static/pages/category/category.html?c=${encodeURIComponent(catForLink)}`;
    };

    wrap.appendChild(btn);
  });
}

function computeMultiMonthGrowthFromDailySeries(series) {
  const monthTotals = new Map();
  (Array.isArray(series) ? series : []).forEach((d) => {
    const iso = String(d?.date || "");
    if (!/^\d{4}-\d{2}-\d{2}$/.test(iso)) return;
    const key = iso.slice(0, 7);
    const amt = Number(d?.value ?? 0);
    if (!Number.isFinite(amt)) return;
    monthTotals.set(key, (monthTotals.get(key) || 0) + amt);
  });
  const keys = Array.from(monthTotals.keys()).sort();
  if (keys.length < 2) return null;
  const first = Number(monthTotals.get(keys[0]) || 0);
  const last = Number(monthTotals.get(keys[keys.length - 1]) || 0);
  if (Math.abs(first) <= 1e-9) return null;
  return ((last - first) / Math.abs(first)) * 100;
}

function renderSpendingBarChartFromPayload() {
  const series = lastPayload.spendingSeries || [];
  const labels = series.map((d) => formatMMMdd(d.date));
  const values = series.map((d) => {
    const n = Number(d?.value ?? 0);
    return Number.isFinite(n) ? n : 0;
  });

  const total = values.reduce((sum, v) => sum + Number(v || 0), 0);
  let growthStr = "—";
  if (values.length >= 2 && Math.abs(values[0]) > 1e-9) {
    const pct = ((values[values.length - 1] - values[0]) / Math.abs(values[0])) * 100;
    growthStr = `${pct > 0 ? "+" : ""}${pct.toFixed(2)}%`;
  }
  // Only show growth when comparing across multiple months.
  const monthlyPct = computeMultiMonthGrowthFromDailySeries(series);
  growthStr = "—";
  if (typeof monthlyPct === "number" && Number.isFinite(monthlyPct)) {
    growthStr = `${monthlyPct > 0 ? "+" : ""}${monthlyPct.toFixed(2)}%`;
  }

  document.getElementById(SPENDING_IDS.breakLabel).textContent = "Total";
  document.getElementById(SPENDING_IDS.breakValue).textContent = money(total);
  setInlineGrowthByIds(SPENDING_IDS, "% Growth", growthStr);

  const ctx = document.getElementById(SPENDING_IDS.canvas)?.getContext("2d");
  if (!ctx) return;
  destroyChart();

  spendingChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label: "Daily spending",
          data: values,
          backgroundColor: "rgba(59, 130, 246, 0.52)",
          borderColor: "rgba(59, 130, 246, 0.95)",
          borderWidth: 1,
          barPercentage: 0.9,
          categoryPercentage: 0.82,
          borderRadius: 4,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      devicePixelRatio: window.devicePixelRatio || 1,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label(context) {
              return `Daily spending: ${money(context.parsed?.y || 0)}`;
            },
          },
        },
      },
      interaction: { mode: "index", intersect: false },
      scales: {
        y: { ticks: { callback: (v) => money(v) } },
      },
    },
  });
}

function renderCategoryBarChartFromPayload() {
  const rows = (lastPayload.categoryRows || [])
    .map((r) => ({ ...r, total: Math.max(0, Number(r.total) || 0) }))
    .filter((r) => r.total > 0);
  const total = rows.reduce((s, r) => s + Number(r.total || 0), 0);

  document.getElementById(SPENDING_IDS.breakLabel).textContent = "Total";
  document.getElementById(SPENDING_IDS.breakValue).textContent = money(total);

  let topStr = "—";
  if (rows.length && total > 0) {
    const top = rows[0];
    const pct = (Number(top.total) / total) * 100;
    topStr = `${top.category} ${pct.toFixed(1)}%`;
  }
  setInlineGrowthByIds(SPENDING_IDS, "Top", topStr);

  const labels = rows.map((r) => r.category);
  const values = rows.map((r) => Number(r.total) || 0);
  const ctx = document.getElementById(SPENDING_IDS.canvas)?.getContext("2d");
  if (!ctx) return;
  destroyChart();

  const isMobile = window.matchMedia("(max-width: 700px)").matches;
  spendingChart = new Chart(ctx, {
    type: "pie",
    data: {
      labels,
      datasets: [{ data: values, borderWidth: 0, radius: "92%" }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      devicePixelRatio: window.devicePixelRatio || 1,
      layout: { padding: 10 },
      plugins: {
        legend: {
          display: true,
          position: isMobile ? "bottom" : "right",
          align: "center",
          labels: { boxWidth: 10, boxHeight: 10, padding: 10 },
        },
        tooltip: {
          callbacks: {
            label(context) {
              const v = Number(context.raw || 0);
              const pct = total > 0 ? (v / total) * 100 : 0;
              return `${context.label}: ${money(v)} (${pct.toFixed(1)}%)`;
            },
          },
        },
      },
    },
  });
}

function renderUnbudgetedSafeChartFromPayload() {
  const series = lastPayload.unbudgetedSafeSeries || [];
  const labels = series.map((d) => formatMMMdd(d.date));
  const unbudgeted = series.map((d) => {
    const n = Number(d?.unbudgeted_spend ?? 0);
    return Number.isFinite(n) ? n : 0;
  });
  const safe = series.map((d) => {
    const n = Number(d?.daily_safe_to_spend ?? 0);
    return Number.isFinite(n) ? n : 0;
  });

  const totalUnbudgeted = unbudgeted.reduce((sum, v) => sum + Number(v || 0), 0);
  const latestSafe = safe.length ? safe[safe.length - 1] : 0;

  document.getElementById(SPENDING_IDS.breakLabel).textContent = "Unbudgeted total";
  document.getElementById(SPENDING_IDS.breakValue).textContent = money(totalUnbudgeted);
  setInlineGrowthByIds(SPENDING_IDS, "Latest safe/day", money(latestSafe));

  const ctx = document.getElementById(SPENDING_IDS.canvas)?.getContext("2d");
  if (!ctx) return;
  destroyChart();

  spendingChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label: "Unbudgeted spending",
          data: unbudgeted,
          backgroundColor: "rgba(239, 68, 68, 0.72)",
          borderColor: "rgba(239, 68, 68, 0.95)",
          borderWidth: 1,
          grouped: false,
          order: 2,
          barPercentage: 0.9,
          categoryPercentage: 0.7,
          borderRadius: 4,
        },
        {
          label: "Daily safe to spend",
          data: safe,
          backgroundColor: "rgba(34, 197, 94, 0.42)",
          borderColor: "rgba(34, 197, 94, 0.95)",
          borderWidth: 1,
          grouped: false,
          order: 1,
          barPercentage: 0.9,
          categoryPercentage: 0.7,
          borderRadius: 4,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      devicePixelRatio: window.devicePixelRatio || 1,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: true },
        tooltip: {
          callbacks: {
            label(context) {
              return `${context.dataset?.label || "Value"}: ${money(context.parsed?.y || 0)}`;
            },
          },
        },
      },
      scales: {
        y: { ticks: { callback: (v) => money(v) } },
      },
      onClick(_evt, elements) {
        if (!elements || !elements.length) return;
        const idx = Number(elements[0].index);
        if (!Number.isInteger(idx) || idx < 0 || idx >= series.length) return;
        const dayIso = series[idx]?.date;
        if (!dayIso) return;
        openSpendingDayPanel(dayIso).catch(() => {});
      },
    },
  });
}

function renderCurrentView() {
  setTitleForView();
  renderViewDots();
  updateNextBtnLabel();

  if (chartView === 0) {
    renderSpendingBarChartFromPayload();
    return;
  }
  if (chartView === 1) {
    renderCategoryBarChartFromPayload();
    return;
  }
  renderUnbudgetedSafeChartFromPayload();
}

async function renderSpending(start, end) {
  const [spRes, catRows, unbudgetedSafe] = await Promise.all([
    fetch(`/spending?start=${start}&end=${end}`).then((r) => r.json()),
    fetchCategoryTotalsWithUnknown(start, end),
    fetchUnbudgetedVsSafeSeries(start, end).catch(() => []),
  ]);

  lastPayload = {
    start,
    end,
    spendingSeries: Array.isArray(spRes) ? spRes : [],
    categoryRows: Array.isArray(catRows) ? catRows : [],
    unbudgetedSafeSeries: Array.isArray(unbudgetedSafe) ? unbudgetedSafe : [],
  };

  renderSpendingCategoryList(lastPayload.categoryRows);
  renderCurrentView();
}

document.addEventListener("DOMContentLoaded", () => {
  mountChartCard("#chartMount", {
    ids: SPENDING_IDS,
    title: "Spending",
    showToggle: false,
    hideDotsWhenNoToggle: false,
    nextFirst: true,
    headerActionsHtml: `<button id="spNextBtn" class="chart-btn">Next ▶</button>`,
  });

  const nextBtn = document.getElementById("spNextBtn");
  if (nextBtn) {
    nextBtn.addEventListener("click", () => {
      chartView = (chartView + 1) % SPENDING_VIEWS.length;
      renderCurrentView();
    });
  }

  initChartControls(SPENDING_IDS, renderSpending);
});
