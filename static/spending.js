let spendingChart = null;

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

function money(n){
  const v = Number(n);
  if (!Number.isFinite(v)) return "—"; // don't silently turn NaN into $0.00
  return v.toLocaleString("en-US", { style: "currency", currency: "USD" });
}



async function renderSpending(start, end) {
  const res = await fetch(`/spending?start=${start}&end=${end}`);
  const data = await res.json();

  const labels = data.map(d => formatMMMdd(d.date));

  const values = data.map(d => {
  const raw = String(d.value ?? 0);
  const cleaned = raw.replace(/[^0-9.-]/g, ""); // strips $ and commas
  const num = parseFloat(cleaned);
  return Number.isFinite(num) ? num : 0;
});

const total = values.reduce((sum, v) => sum + (Number(v) || 0), 0);


      // % Growth
  let growthStr = "—";
  if (values.length >= 2 && Math.abs(values[0]) > 1e-9) {
    const pct = ((values[values.length - 1] - values[0]) / Math.abs(values[0])) * 100;
    growthStr = (pct > 0 ? "+" : "") + pct.toFixed(2) + "%";
  }
  setInlineGrowthByIds(SPENDING_IDS, "% Growth", growthStr);


  document.getElementById("spBreakLabel").textContent = "Total";
  document.getElementById("spBreakValue").textContent = money(total);

  const ctx = document.getElementById("spChart").getContext("2d");
  if (spendingChart) spendingChart.destroy();

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

  loadSpendingCategories(start, end);
}

async function loadSpendingCategories(start, end) {
  const res = await fetch(`/category-totals-range?start=${start}&end=${end}`);
  const data = await res.json();

  const wrap = document.getElementById("spendingCategoryList");
  wrap.innerHTML = "";

  // Normal categories
  data.forEach(r => {
    const btn = document.createElement("button");
    btn.className = "category-pill";
    btn.innerHTML = `<span>${r.category}</span><span>${money(r.total)}</span>`;
    btn.onclick = () =>
      location.href = `/static/category.html?c=${encodeURIComponent(r.category)}`;
    wrap.appendChild(btn);
  });

  // -----------------------------
  // Unknown merchant (synthetic category)
  // -----------------------------
  const unkRes = await fetch(
    `/unknown-merchant-total-range?start=${start}&end=${end}`
  );

  if (!unkRes.ok) return;

  const { total, tx_count } = await unkRes.json();
  const t = Number(total || 0);
  const c = Number(tx_count || 0);

  if (t <= 0 || c <= 0) return;

  const btn = document.createElement("button");
  btn.className = "category-pill";
  btn.innerHTML = `
    <span>Unknown merchant (${c})</span>
    <span>${money(t)}</span>
  `;

  btn.onclick = () => {
  location.href = `/static/category.html?c=${encodeURIComponent("Unknown merchant")}`;
};


  wrap.appendChild(btn);
}


document.addEventListener("DOMContentLoaded", () => {
    mountChartCard("#chartMount", {
      ids: SPENDING_IDS,
      title: "Spending",
      showToggle: false
    });


  const back = document.getElementById("spBackBtn");
  if (back) {
    back.addEventListener("click", () => {
      // Prefer browser back if they came from another page
      if (window.history.length > 1) window.history.back();
      else window.location.href = "/";
    });
  }

  initChartControls(SPENDING_IDS, renderSpending);


});


