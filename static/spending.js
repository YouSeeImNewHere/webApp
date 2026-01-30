let spendingChart = null;

// 0 = line (spending), 1 = pie (categories)
let chartView = 0;

// cache for the currently-selected date range so Next can re-render without refetch
let lastPayload = {
  start: null,
  end: null,
  spendingSeries: [],
  categoryRows: []
};

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

function money(n) {
  const v = Number(n);
  if (!Number.isFinite(v)) return "—";
  return v.toLocaleString("en-US", { style: "currency", currency: "USD" });
}

function setTitleForView() {
  const t = document.getElementById(SPENDING_IDS.title);
  if (!t) return;
  t.textContent = chartView === 0 ? "Spending" : "Spending • Categories";
}

function updateNextBtnLabel() {
  const btn = document.getElementById("spNextBtn");
  if (!btn) return;
  // show where Next will take you
  btn.textContent = chartView === 0 ? "Next ▶" : "◀ Back";
}

async function fetchCategoryTotalsWithUnknown(start, end) {
  const res = await fetch(`/category-totals-range?start=${start}&end=${end}`);
  const data = await res.json();

  const rows = (Array.isArray(data) ? data : [])
    .map(r => ({ category: String(r.category ?? ""), total: Number(r.total ?? 0) }))
    .filter(r => r.category && Number.isFinite(r.total));

  const unkRes = await fetch(`/unknown-merchant-total-range?start=${start}&end=${end}`);
  if (unkRes.ok) {
    const { total, tx_count } = await unkRes.json();
    const t = Number(total || 0);
    const c = Number(tx_count || 0);
    if (t > 0 && c > 0) {
      rows.push({ category: `Unknown merchant (${c})`, total: t, _linkCategory: "Unknown merchant" });
    }
  }

  rows.sort((a, b) => (Number(b.total) || 0) - (Number(a.total) || 0));
  return rows;
}

function renderSpendingCategoryList(rows) {
  const wrap = document.getElementById("spendingCategoryList");
  if (!wrap) return;
  wrap.innerHTML = "";

  rows.forEach(r => {
    const btn = document.createElement("button");
    btn.className = "category-pill";
    btn.innerHTML = `<span>${r.category}</span><span>${money(r.total)}</span>`;

    const catForLink = r._linkCategory || r.category;
    btn.onclick = () => {
      location.href = `/static/category.html?c=${encodeURIComponent(catForLink)}`;
    };

    wrap.appendChild(btn);
  });
}

function destroyChart() {
  if (spendingChart) {
    spendingChart.destroy();
    spendingChart = null;
  }
}

function renderLineChartFromPayload() {
  const series = lastPayload.spendingSeries || [];
  const labels = series.map(d => formatMMMdd(d.date));

  const values = series.map(d => {
    const raw = String(d.value ?? 0);
    const cleaned = raw.replace(/[^0-9.-]/g, "");
    const num = parseFloat(cleaned);
    return Number.isFinite(num) ? num : 0;
  });

  const total = values.reduce((sum, v) => sum + (Number(v) || 0), 0);

  // growth
  let growthStr = "—";
  if (values.length >= 2 && Math.abs(values[0]) > 1e-9) {
    const pct = ((values[values.length - 1] - values[0]) / Math.abs(values[0])) * 100;
    growthStr = (pct > 0 ? "+" : "") + pct.toFixed(2) + "%";
  }

  document.getElementById(SPENDING_IDS.breakLabel).textContent = "Total";
  document.getElementById(SPENDING_IDS.breakValue).textContent = money(total);
  setInlineGrowthByIds(SPENDING_IDS, "% Growth", growthStr);

  const ctx = document.getElementById(SPENDING_IDS.canvas).getContext("2d");
  destroyChart();

  spendingChart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [{
        data: values,
        tension: 0.25,
        pointRadius: 0,
        pointHitRadius: 12
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      devicePixelRatio: window.devicePixelRatio || 1,
      plugins: { legend: { display: false } },
      interaction: { mode: "index", intersect: false },
      scales: {
        y: { ticks: { callback: v => money(v) } }
      }
    }
  });
}

function renderPieChartFromPayload() {
  const rows = (lastPayload.categoryRows || [])
  .map(r => ({ ...r, total: Math.max(0, Number(r.total) || 0) }))
  .filter(r => r.total > 0);

  const total = rows.reduce((s, r) => s + (Number(r.total) || 0), 0);

  document.getElementById(SPENDING_IDS.breakLabel).textContent = "Total";
  document.getElementById(SPENDING_IDS.breakValue).textContent = money(total);

  // show “Top” in the % slot (since pie view doesn't have growth)
  let topStr = "—";
  if (rows.length && total > 0) {
    const top = rows[0];
    const pct = (Number(top.total) / total) * 100;
    topStr = `${top.category} ${pct.toFixed(1)}%`;
  }
  setInlineGrowthByIds(SPENDING_IDS, "Top", topStr);

  const labels = rows.map(r => r.category);
  const values = rows.map(r => Number(r.total) || 0);

  const ctx = document.getElementById(SPENDING_IDS.canvas).getContext("2d");
  destroyChart();

    const isMobile = window.matchMedia("(max-width: 700px)").matches;

  spendingChart = new Chart(ctx, {
    type: "pie",
    data: {
      labels,
      datasets: [{
        data: values,
        borderWidth: 0,
        // Make the pie fill more of the existing chart rectangle
        radius: "92%",
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      devicePixelRatio: window.devicePixelRatio || 1,

      // Keep the pie nicely centered with a bit of breathing room
      layout: { padding: 10 },

      plugins: {
        legend: {
          display: true,
          // ✅ Key change: don't steal vertical height on desktop
          position: isMobile ? "bottom" : "right",
          align: "center",
          labels: {
            boxWidth: 10,
            boxHeight: 10,
            padding: 10
          }
        },
        tooltip: {
          callbacks: {
            label: function (context) {
              const v = Number(context.raw || 0);
              const pct = total > 0 ? (v / total) * 100 : 0;
              return `${context.label}: ${money(v)} (${pct.toFixed(1)}%)`;
            }
          }
        }
      }
    }
  });
}

function renderCurrentView() {
  setTitleForView();
  updateNextBtnLabel();

  if (chartView === 0) renderLineChartFromPayload();
  else renderPieChartFromPayload();
}

async function renderSpending(start, end) {
  // fetch both datasets once for this date range
  const [spRes, catRows] = await Promise.all([
    fetch(`/spending?start=${start}&end=${end}`).then(r => r.json()),
    fetchCategoryTotalsWithUnknown(start, end),
  ]);

  lastPayload = {
    start,
    end,
    spendingSeries: Array.isArray(spRes) ? spRes : [],
    categoryRows: Array.isArray(catRows) ? catRows : []
  };

  // update the category pills list (always visible under the chart)
  renderSpendingCategoryList(lastPayload.categoryRows);

  // render whichever view we’re currently on
  renderCurrentView();
}

document.addEventListener("DOMContentLoaded", () => {
  mountChartCard("#chartMount", {
    ids: SPENDING_IDS,
    title: "Spending",
    showToggle: false,
    headerActionsHtml: `<button id="spNextBtn" class="chart-btn">Next ▶</button>`
  });

  // Next toggles the SAME card between line and pie
  const nextBtn = document.getElementById("spNextBtn");
  if (nextBtn) {
    nextBtn.addEventListener("click", () => {
      chartView = chartView === 0 ? 1 : 0;
      // don’t refetch — use cached payload for current date range
      renderCurrentView();
    });
  }

  const back = document.getElementById("spBackBtn");
  if (back) {
    back.addEventListener("click", () => {
      if (window.history.length > 1) window.history.back();
      else window.location.href = "/";
    });
  }

  initChartControls(SPENDING_IDS, renderSpending);
});
