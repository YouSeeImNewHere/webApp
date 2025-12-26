let categoryChartInstance = null;

function money(n) {
  const num = Number(n || 0);
  return num.toLocaleString("en-US", { style: "currency", currency: "USD" });
}

function getCategoryFromURL() {
  const params = new URLSearchParams(window.location.search);
  return params.get("c") || "";
}

function setCategoryInURL(category) {
  const url = new URL(window.location.href);
  url.searchParams.set("c", category);
  window.history.pushState({}, "", url);
}

function setActivePeriod(period) {
  document.querySelectorAll(".period-btn").forEach(b => {
    b.classList.toggle("active", b.dataset.p === period);
  });
}

function shortDate(mmddyyOrIso) {
  if (!mmddyyOrIso) return "";
  if (String(mmddyyOrIso).includes("/")) {
    const [m, d] = String(mmddyyOrIso).split("/");
    return `${m}/${d}`;
  }
  const d = new Date(mmddyyOrIso);
  return d.toLocaleDateString("en-US", { month: "2-digit", day: "2-digit" });
}

async function loadTrend(category, period) {
  window.__period = period;

  const res = await fetch(
    `/category-trend?category=${encodeURIComponent(category)}&period=${encodeURIComponent(period)}`,
    { cache: "no-store" }
  );
  if (!res.ok) throw new Error("trend failed");

  const payload = await res.json();
  const series = payload.series || [];

  const labels = series.map(p => {
    const d = new Date(p.date);
    return d.toLocaleDateString("en-US", { month: "short", day: "2-digit" });
  });

  const values = series.map(p => Number(p.amount || 0));

  const canvas = document.getElementById("catChart");
  if (!canvas) return;

  const ctx = canvas.getContext("2d");
  if (categoryChartInstance) categoryChartInstance.destroy();

  categoryChartInstance = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [{
        label: `${category} (daily total)`,
        data: values,
        tension: 0.2,
        pointRadius: 0,
        pointHitRadius: 12,
        pointHoverRadius: 4
      }]
    },
    options: {
      responsive: true,
      plugins: { legend: { display: true } },
      interaction: { mode: "index", intersect: false },
      scales: {
        y: { ticks: { callback: v => Number(v).toLocaleString() } }
      }
    }
  });
}

async function loadCategoryTransactions(category) {
  const list = document.getElementById("catTxList");
  if (!list) {
    console.warn("catTxList not found (did you update category.html?)");
    return;
  }

  list.innerHTML = "";

  const res = await fetch(
    `/category-transactions?category=${encodeURIComponent(category)}&limit=500`,
    { cache: "no-store" }
  );
  if (!res.ok) throw new Error("tx failed");

  const data = await res.json();

  if (!Array.isArray(data) || data.length === 0) {
    list.innerHTML = `<div style="padding:10px;">No transactions found.</div>`;
    return;
  }

  data.forEach(row => {
    const wrap = document.createElement("div");
    wrap.className = "tx-row";

    wrap.innerHTML = `
      <div class="tx-date">${shortDate(row.postedDate)}</div>
      <div class="tx-main">
        <div class="tx-merchant">${(row.merchant || "").toUpperCase()}</div>
        <div class="tx-sub">${[row.bank, row.card].filter(Boolean).join(" • ")}</div>
      </div>
      <div class="tx-amt">${money(row.amount)}</div>
    `;

    list.appendChild(wrap);
  });
}

async function loadLifetimeSidebar(activeCategory) {
  const tbody = document.querySelector("#catSideTable tbody");
  if (!tbody) {
    console.warn("catSideTable tbody not found");
    return;
  }

  const res = await fetch("/category-totals-lifetime", { cache: "no-store" });
  if (!res.ok) throw new Error("lifetime totals failed");

  const rows = await res.json(); // [{category,total},...]
  tbody.innerHTML = "";

  rows.forEach(r => {
    const tr = document.createElement("tr");
    tr.className = "cat-side-row" + (r.category === activeCategory ? " active" : "");
    tr.innerHTML = `
      <td>${r.category}</td>
      <td style="text-align:right;">${money(r.total)}</td>
    `;

    tr.addEventListener("click", async () => {
      const newCat = r.category;

      document.getElementById("catTitle").textContent = newCat;
      setCategoryInURL(newCat);

      await loadLifetimeSidebar(newCat);
      await loadTrend(newCat, window.__period || "1m");
      await loadCategoryTransactions(newCat);
    });

    tbody.appendChild(tr);
  });
}

async function init() {
  let category = getCategoryFromURL();
  if (!category) category = "Uncategorized";

  const title = document.getElementById("catTitle");
  if (title) title.textContent = category;

  let period = "1m";
  window.__period = period;
  setActivePeriod(period);

  // LEFT sidebar first
  await loadLifetimeSidebar(category);

  // RIGHT side
  await loadTrend(category, period);
  await loadCategoryTransactions(category);

  // period buttons
  document.querySelectorAll(".period-btn").forEach(btn => {
    btn.addEventListener("click", async () => {
      period = btn.dataset.p;
      window.__period = period;
      setActivePeriod(period);

      const currentCat = getCategoryFromURL() || category;
      await loadTrend(currentCat, period);
      // transactions do not depend on period, so no need to reload them here
    });
  });

  // If user uses browser back/forward and category changes in URL
  window.addEventListener("popstate", async () => {
    const currentCat = getCategoryFromURL() || "Uncategorized";
    if (title) title.textContent = currentCat;

    await loadLifetimeSidebar(currentCat);
    await loadTrend(currentCat, window.__period || "1m");
    await loadCategoryTransactions(currentCat);
  });
}

document.addEventListener("DOMContentLoaded", () => {
  init().catch(err => console.error(err));
});
