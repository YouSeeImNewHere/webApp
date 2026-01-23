let categoryChartInstance = null;

const CATEGORY_CHART_IDS = {
  title: "catChartTitle",
  dots: "catChartDots",
  toggle: "catChartToggle", // hidden
  growthLabel: "catGrowthLabel",
  growthValue: "catGrowthValue",
  breakLabel: "catBreakLabel",
  breakValue: "catBreakValue",
  quarters: "catQuarterButtons",
  yearBack: "catYearBack",
  yearLabel: "catYearLabel",
  yearFwd: "catYearFwd",
  update: "catUpdateBtn",
  start: "cat-start",
  end: "cat-end",
  canvas: "catChart",
  monthButtons: "catMonthButtons",
  // (no dropdown on category page unless you want it)
};

function openCatDrawer() {
  document.getElementById("catDrawer")?.classList.add("is-open");
  document.getElementById("catDrawerBackdrop")?.classList.add("is-open");
}

function closeCatDrawer() {
  document.getElementById("catDrawer")?.classList.remove("is-open");
  document.getElementById("catDrawerBackdrop")?.classList.remove("is-open");
}

function bindCatDrawerUI() {
  const btn = document.getElementById("catDrawerBtn");
  const backdrop = document.getElementById("catDrawerBackdrop");

  if (btn) btn.addEventListener("click", () => {
    const drawer = document.getElementById("catDrawer");
    const isOpen = drawer?.classList.contains("is-open");
    if (isOpen) closeCatDrawer();
    else openCatDrawer();
  });

  if (backdrop) backdrop.addEventListener("click", closeCatDrawer);
}


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

function shortDate(mmddyyOrIso) {
  if (!mmddyyOrIso) return "";
  if (String(mmddyyOrIso).includes("/")) {
    const [m, d] = String(mmddyyOrIso).split("/");
    return `${m}/${d}`;
  }
  const d = parseISODateLocal(mmddyyOrIso);
  return d.toLocaleDateString("en-US", { month: "2-digit", day: "2-digit" });
}


async function loadCategoryChart() {
  const category = getCategoryFromURL() || "Uncategorized";
const t = document.getElementById(CATEGORY_CHART_IDS.title);
if (t) t.textContent = category;
  const start = document.getElementById("cat-start")?.value;
  const end   = document.getElementById("cat-end")?.value;
  if (!start || !end) return;

  const res = await fetch(
    `/category-trend?category=${encodeURIComponent(category)}&period=all`,
    { cache: "no-store" }
  );
  if (!res.ok) throw new Error("category chart failed");

  const payload = await res.json();
  const series = payload.series || [];

  // filter to selected range
  const filtered = series.filter(p => p.date >= start && p.date <= end);

  const labels = filtered.map(p => formatMMMdd(p.date));

  const values = filtered.map(p => Number(p.amount || 0));

  // % Growth
  let growthStr = "—";
  if (values.length >= 2 && Math.abs(values[0]) > 1e-9) {
    const pct = ((values[values.length - 1] - values[0]) / Math.abs(values[0])) * 100;
    growthStr = (pct > 0 ? "+" : "") + pct.toFixed(2) + "%";
  }
  setInlineGrowthByIds(CATEGORY_CHART_IDS, "% Growth", growthStr);

  const last = values.length ? values[values.length - 1] : 0;

  const l = document.getElementById(CATEGORY_CHART_IDS.breakLabel);
  const v = document.getElementById(CATEGORY_CHART_IDS.breakValue);
  if (l) l.textContent = category;
  if (v) v.textContent = money(last);


  setInlineGrowthByIds(CATEGORY_CHART_IDS, "% Growth", growthStr);

  const canvas = document.getElementById("catChart");
  if (!canvas) return;

  const ctx = canvas.getContext("2d");
  if (categoryChartInstance) categoryChartInstance.destroy();

  categoryChartInstance = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [{
        label: `${category} (daily)`,
        data: values,
        tension: 0.2,
        pointRadius: 0,
        pointHitRadius: 12,
        pointHoverRadius: 4
      }]
    },
    options: {
      responsive: true,
  maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      interaction: { mode: "index", intersect: false },
      scales: {
        y: { ticks: { callback: v => Number(v).toLocaleString() } }
      }
    }
  });
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
    return formatMMMdd(p.date);
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
  if (!list) return;

  const start = document.getElementById("cat-start")?.value;
  const end   = document.getElementById("cat-end")?.value;
  if (!start || !end) return;

  list.innerHTML = "";

  const res = await fetch(
    `/category-transactions?category=${encodeURIComponent(category)}&start=${start}&end=${end}&limit=500`,
    { cache: "no-store" }
  );
  if (!res.ok) throw new Error("tx failed");

  const data = await res.json();

  if (!Array.isArray(data) || data.length === 0) {
    list.innerHTML = `<div style="padding:10px;">No transactions in this range.</div>`;
    return;
  }

  data.forEach(row => {
    const wrap = document.createElement("div");
    wrap.className = "tx-row";


    wrap.dataset.txId = String(row.id ?? "");
wrap.innerHTML = `
      <div class="tx-icon-wrap tx-icon-hit" role="button" tabindex="0" aria-label="Transaction details">
        ${categoryIconHTML(row.category)}
      </div>
      <div class="tx-date">${shortDate(row.postedDate)}</div>
      <div class="tx-main">
        <div class="tx-merchant">${(row.merchant || "").toUpperCase()}</div>
        <div class="tx-sub">${[row.bank, row.card].filter(Boolean).join(" • ")}</div>
      </div>
      <div class="tx-amt">${money(row.amount)}</div>
    `;

    list.appendChild(wrap);
  });

  if (typeof attachTxInspect === 'function') attachTxInspect(list);
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

  const titleEl = document.getElementById("catTitle");
  if (titleEl) titleEl.textContent = newCat;

  setCategoryInURL(newCat); // ✅ this is the missing piece

  await loadLifetimeSidebar(newCat);
  await loadCategoryChart();              // now reads the new ?c=
  await loadCategoryTransactions(newCat);

  closeCatDrawer();
});


    tbody.appendChild(tr);
  });
}

async function init() {
  let category = getCategoryFromURL();
  if (!category) category = "Uncategorized";

  const title = document.getElementById("catTitle");
  if (title) title.textContent = category;
  bindCatDrawerUI();

mountChartCard("#chartMount", {
  ids: CATEGORY_CHART_IDS,
  title: "Category",
  showToggle: false,
});
    initChartControls(CATEGORY_CHART_IDS, async () => {
    await loadCategoryChart();
     await loadCategoryTransactions(getCategoryFromURL() || "Uncategorized");
});

const chartTitle = document.getElementById(CATEGORY_CHART_IDS.title);
if (chartTitle) chartTitle.textContent = category;




  // LEFT sidebar first
  await loadLifetimeSidebar(category);

  // RIGHT side
  await loadCategoryChart();

  await loadCategoryTransactions(category);

  // If user uses browser back/forward and category changes in URL
  window.addEventListener("popstate", async () => {
    const currentCat = getCategoryFromURL() || "Uncategorized";
    if (title) title.textContent = currentCat;

    await loadLifetimeSidebar(currentCat);
    await loadCategoryChart();

    await loadCategoryTransactions(currentCat);
  });
}

document.addEventListener("DOMContentLoaded", () => {
  init().catch(err => console.error(err));
});



/* =============================================================================
   Transaction Inspect (shared)
   ============================================================================= */

function ensureTxInspectModal(){
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
    if (e.target && e.target.matches && e.target.matches("[data-tx-close]")) {
      closeTxInspect();
    }
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeTxInspect();
  });

  return root;
}

function closeTxInspect(){
  const root = document.getElementById("txInspectRoot");
  if (root) root.classList.add("hidden");
}

function _txEsc(s){
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function openTxInspect(txId){
  const root = ensureTxInspectModal();
  root.classList.remove("hidden");

  const titleEl = document.getElementById("txInspectTitle");
  const subEl = document.getElementById("txInspectSub");
  const bodyEl = document.getElementById("txInspectBody");
  if (bodyEl) bodyEl.innerHTML = `<div style="opacity:.65;font-weight:700;">Loading…</div>`;

  const res = await fetch(`/transaction/${encodeURIComponent(txId)}`, { cache: "no-store" });
  if (!res.ok) throw new Error("HTTP " + res.status);

  const data = await res.json();
  const tx = data.transaction || data || {};

  const merchant = tx.merchant || "(no merchant)";
  if (titleEl) titleEl.textContent = String(merchant).toUpperCase();
  if (subEl) subEl.textContent = `id ${tx.id ?? txId}`;

  const entries = Object.entries(tx);

  // useful fields first, rest alphabetical
  const priority = ["id","status","postedDate","purchaseDate","dateISO","time","amount","merchant","bank","card","accountType","account_id","category","source","transfer_peer","transfer_dir","where","notes","balance_after"];
  entries.sort((a,b) => {
    const ai = priority.indexOf(a[0]); const bi = priority.indexOf(b[0]);
    if (ai === -1 && bi === -1) return String(a[0]).localeCompare(String(b[0]));
    if (ai === -1) return 1;
    if (bi === -1) return -1;
    return ai - bi;
  });

  const kv = entries.map(([k,v]) => {
    const vv =
      v === null ? "null" :
      v === undefined ? "undefined" :
      (typeof v === "object" ? JSON.stringify(v) : String(v));
    return `<div class="tx-kv__k">${_txEsc(k)}</div><div class="tx-kv__v">${_txEsc(vv)}</div>`;
  }).join("");

  if (bodyEl) bodyEl.innerHTML = `<div class="tx-kv">${kv}</div>`;
}

function attachTxInspect(container){
  if (!container || container.__txInspectBound) return;
  container.__txInspectBound = true;

  container.addEventListener("click", async (e) => {
    const hit = e.target.closest && e.target.closest(".tx-icon-hit");
    if (!hit) return;
    const row = hit.closest && hit.closest(".tx-row");
    const txId = row && row.dataset ? row.dataset.txId : "";
    if (!txId) return;

    try { await openTxInspect(txId); }
    catch (err) { console.error(err); }
  });

  container.addEventListener("keydown", async (e) => {
    if (e.key !== "Enter" && e.key !== " ") return;
    const hit = e.target.closest && e.target.closest(".tx-icon-hit");
    if (!hit) return;
    e.preventDefault();
    const row = hit.closest && hit.closest(".tx-row");
    const txId = row && row.dataset ? row.dataset.txId : "";
    if (!txId) return;

    try { await openTxInspect(txId); }
    catch (err) { console.error(err); }
  });
}

