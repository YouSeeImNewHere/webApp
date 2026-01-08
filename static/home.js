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

async function loadBankTotals() {
  const res = await fetch("/bank-totals");
  if (!res.ok) {
    console.error("bank-totals failed:", res.status);
    return;
  }

  const data = await res.json();

  const container = document.getElementById("bankTotals");
  container.innerHTML = "";

  renderCategory(container, "Checking", data.checking);
  renderCategory(container, "Card Balances", data.credit);
  renderCategory(container, "Savings", data.savings);
  renderCategory(container, "Investments", data.investment);
}


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

  monthButtons: "monthButtons",
  monthSelect: "monthSelect",
  monthSelectWrap: "monthSelectWrap"
};

let netWorthChartInstance = null;
const DEBUG_SPENDING = false;
let showPotentialGrowth = (localStorage.getItem("showPotentialGrowth") === "true");
let endBeforePotential = null;
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

  const sd = new Date(s);
  const ed = new Date(e);

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


function toISODate(d) {
  return d.toISOString().split("T")[0];
}

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
  const d = new Date(isoDateStr);
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

    const calRes = await fetch(
      `/recurring/calendar?year=${encodeURIComponent(y)}&month=${encodeURIComponent(m)}&min_occ=${encodeURIComponent(minOcc)}&include_stale=${includeStale}`
    );

    const calJson = calRes.ok ? await calRes.json() : { events: [] };
    const events = Array.isArray(calJson?.events) ? calJson.events : [];

    // 2) Build daily delta map for remaining days in month (after today)
    const deltaByDate = {}; // { "YYYY-MM-DD": number }
    for (const e of events) {
      const d = String(e.date || "");
      if (!d) continue;

      // Only dates after today (projection forward)
      if (d <= todayIso) continue;

      const amt = Number(e.amount) || 0;

      // Income rules:
      // - paychecks show as cadence="paycheck" and type="income"
      // - interest etc may have type="income"
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

  const isMobile = window.matchMedia("(max-width: 900px)").matches;


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

function renderCategory(container, title, payload) {
  const total = payload?.total ?? 0;
  const accounts = payload?.accounts ?? [];
  const isCardBalances = title === "Card Balances";
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
      <span>${title}<span class="bank-accordion__meta">${accounts.length} acct</span></span>
      <span>${isCardBalances ? formatCardBalance(displayTotal) : money(displayTotal)} ▾</span>
    `;

    const panel = document.createElement("div");
    panel.className = "bank-accordion__panel";
    panel.hidden = true;

    if (accounts.length) {
      const ul = document.createElement("ul");
      ul.className = "bank-sublist";

      accounts.forEach(a => {
        const li = document.createElement("li");
        const pill = document.createElement("button");
        pill.type = "button";
        pill.className = "account-pill";

        const amt = a.total;
        pill.innerHTML = `<span>${a.name}</span><span>${isCardBalances ? formatCardBalance(amt) : money(amt)}</span>`;

        pill.addEventListener("click", () => {
          window.location.href = `/account?account_id=${a.id}`;
        });

        li.appendChild(pill);
        ul.appendChild(li);
      });

      panel.appendChild(ul);
    }

    btn.addEventListener("click", () => {
      panel.hidden = !panel.hidden;
      btn.querySelector("span:last-child").textContent =
        `${isCardBalances ? formatCardBalance(displayTotal) : money(displayTotal)} ${panel.hidden ? "▾" : "▴"}`;
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
  right.textContent = isCardBalances ? formatCardBalance(displayTotal) : money(displayTotal);

  head.appendChild(left);
  head.appendChild(right);
  card.appendChild(head);

  if (accounts.length) {
    const ul = document.createElement("ul");
    ul.className = "bank-sublist";

    accounts.forEach(a => {
      const li = document.createElement("li");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "account-pill";

      const amt = a.total;
      btn.innerHTML = `<span>${a.name}</span><span>${isCardBalances ? formatCardBalance(amt) : money(amt)}</span>`;

      btn.addEventListener("click", () => {
        window.location.href = `/account?account_id=${a.id}`;
      });

      li.appendChild(btn);
      ul.appendChild(li);
    });

    card.appendChild(ul);
  }

  container.appendChild(card);
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

  // divider-ish spacing (optional)
  const spacer = document.createElement("li");
  spacer.style.borderBottom = "none";
  spacer.style.paddingTop = "10px";
  spacer.style.opacity = "0.7";
  spacer.innerHTML = `<span>Unassigned</span><span>${unassignedAllTime} tx (all-time)</span>`;
await renderUnknownMerchantRow(ul);
  renderUnassignedRow(ul, unassignedAllTime);
}

function renderUnassignedRow(ul, unassignedAllTime) {
  const li = document.createElement("li");
  li.innerHTML = `
    <span style="display:flex; align-items:center; gap:8px;">
      <strong>Unassigned</strong>
      <button id="addRuleBtn" type="button" style="padding:2px 8px;">+ Rule</button>
    </span>
    <span>${unassignedAllTime}</span>
  `;
  ul.appendChild(li);

  const btn = li.querySelector("#addRuleBtn");
  btn.addEventListener("click", openRuleModal);
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
  document.getElementById("ruleModalBackdrop").style.display = show ? "block" : "none";
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

    // Only applies to Net Worth + current month
    const startInput = document.getElementById("nw-start");
    const endInput = document.getElementById("nw-end");
    const todayIso = isoLocal(new Date());

    if (!startInput || !endInput) return;

    if (showPotentialGrowth) {
      // force: current month only
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




  setChartHeaderUI();
  loadChart();
  loadBankTotals();
  loadCategoryTotalsThisMonth();
  loadData();
mountUpcomingCard("#upcomingMount", { daysAhead: 30 });


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

function shortDate(mmddyyOrIso) {
  if (!mmddyyOrIso) return "";
  // "12/01/25" -> "12/01"
  if (mmddyyOrIso.includes("/")) {
    const parts = mmddyyOrIso.split("/");
    return `${parts[0]}/${parts[1]}`;
  }
  const d = new Date(mmddyyOrIso);
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

wrap.innerHTML = `
  ${categoryIconHTML(row.category)}
  <div class="tx-date">${shortDate(row.postedDate)}</div>
  <div class="tx-main">
        <div class="tx-merchant">${merchant}</div>
        <div class="tx-sub">${sub}</div>
      </div>
      <div class="tx-amt">${money(row.amount)}</div>
    `;

    list.appendChild(wrap);
  });
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

const toggleBtn = document.getElementById("unassignedToggle"); // add this button in HTML

function setToggleLabel() {
  // show what you'll switch TO
  toggleBtn.textContent = (unassignedMode === "freq")
    ? "Most recent ▾"
    : "Most frequent ▾";
}

async function loadUnassigned() {
  const res = await fetch(`/unassigned?limit=25&mode=${encodeURIComponent(unassignedMode)}`);
  const rows = await res.json();

  // render rows...
  // if mode === "freq", rows include usage_count — show it if you want
}

toggleBtn.addEventListener("click", () => {
  unassignedMode = (unassignedMode === "freq") ? "recent" : "freq";
  localStorage.setItem("unassignedMode", unassignedMode);
  setToggleLabel();
  loadUnassigned();
});

// on page load
setToggleLabel();
loadUnassigned();


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
