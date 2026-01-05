let spendingChart = null;

const SPENDING_IDS = {
  title: "spChartTitle",
  dots: "spChartDots",
  toggle: null,
  breakLabel: "spBreakLabel",
  breakValue: "spBreakValue",
  quarters: "spQuarterButtons",
  yearBack: "spYearBack",
  yearLabel: "spYearLabel",
  yearFwd: "spYearFwd",
  update: "spUpdateBtn",
  start: "sp-start",
  end: "sp-end",
  canvas: "spChart",
  monthButtons: "spMonthButtons"
};

function money(n){
  return Number(n || 0).toLocaleString("en-US", {
    style: "currency",
    currency: "USD"
  });
}

async function renderSpending(start, end) {
  const res = await fetch(`/spending?start=${start}&end=${end}`);
  const data = await res.json();

  const labels = data.map(d =>
    new Date(d.date).toLocaleDateString("en-US", {
      month: "short",
      day: "2-digit"
    })
  );

  const values = data.map(d => Number(d.value || 0));
  const total = values.reduce((a, b) => a + b, 0);

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

  data.forEach(r => {
    const btn = document.createElement("button");
    btn.className = "category-pill";
    btn.innerHTML = `<span>${r.category}</span><span>${money(r.total)}</span>`;
    btn.onclick = () =>
      location.href = `/static/category.html?c=${encodeURIComponent(r.category)}`;
    wrap.appendChild(btn);
  });
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

