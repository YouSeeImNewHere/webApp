let chart = null;
let accountId = null;
const TX_MODE = window.TX_MODE || "prod";


const ACCOUNT_CHART_IDS = {
  title: "aChartTitle",
  dots: "aChartDots",
  toggle: "aChartToggle", // will be hidden on this page
  breakLabel: "aBreakLabel",
  breakValue: "aBreakValue",
  growthLabel: "aGrowthLabel",
  growthValue: "aGrowthValue",
  quarters: "aQuarterButtons",
  yearBack: "a-yearBack",
  yearLabel: "aYearLabel",
  yearFwd: "a-yearFwd",
  update: "a-update",
  start: "a-start",
  end: "a-end",
  canvas: "accountChart",
  monthSelect: "aMonthSelect",
  monthSelectWrap: "aSelectWrap",
  monthButtons: "aButtons",
};


function qs(name){
  return new URLSearchParams(window.location.search).get(name);
}
function toISODate(d){ return d.toISOString().split("T")[0]; }
function money(n){
  const num = Number(n || 0);
  return num.toLocaleString("en-US", { style:"currency", currency:"USD" });
}
function formatMMMdd(iso){
  const d = new Date(iso);
  return d.toLocaleDateString("en-US", { month:"short", day:"2-digit" });
}
function firstDayOfMonth(y,m){ return new Date(y,m,1); }
function lastDayOfMonth(y,m){ return new Date(y,m+1,0); }

let showPotentialGrowth = (localStorage.getItem("showPotentialGrowth") === "true");
let endBeforePotential = null;

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

async function loadAccountHeader(accountId){
  if (TX_MODE === "test") return;

  const res = await fetch(`/account/${accountId}`);
  const a = await res.json();

  // ✅ Put title inside the chart card header (like home)
  const titleEl = document.getElementById(ACCOUNT_CHART_IDS.title);
  if (titleEl) titleEl.textContent = `${a.institution} — ${a.name}`;

  // ✅ Use the inline breakdown label for account type (optional, looks nice)
  const breakLabel = document.getElementById(ACCOUNT_CHART_IDS.breakLabel);
  if (breakLabel) breakLabel.textContent = a.accountType || "Balance";
}

async function loadAccountChart(accountId){
  const start = document.getElementById("a-start").value;
  const end   = document.getElementById("a-end").value;
  if (!start || !end) return;

  const seriesUrl = TX_MODE === "test" ? "/transactions-test-series" : "/account-series";
  const res = await fetch(`${seriesUrl}?account_id=${accountId}&start=${start}&end=${end}`);
  const data = await res.json();

  const labels = data.map(d => formatMMMdd(d.date));
  const values = data.map(d => Number(d.value));
  const last = values.length ? values[values.length - 1] : 0;

  // --- Potential growth projection (Account page, current month only) ---
  let potentialSeries = null;
  let potentialEOM = null;

  if (showPotentialGrowth) {
    const today = new Date();
    const todayIso = isoLocal(today);

    // Only project for current month (and when the selected end is in current month)
    if (sameMonthISO(todayIso, end)) {
      const y = today.getFullYear();
      const m = today.getMonth() + 1;

      // match recurring page defaults
      const minOcc = 3;
      const includeStale = "false";

      const calRes = await fetch(
        `/recurring/calendar?year=${encodeURIComponent(y)}&month=${encodeURIComponent(m)}&min_occ=${encodeURIComponent(minOcc)}&include_stale=${includeStale}`
      );

      const calJson = calRes.ok ? await calRes.json() : { events: [] };
      let events = Array.isArray(calJson?.events) ? calJson.events : [];

      // ✅ If calendar events include account_id, filter to this account
      // (If not provided, we keep them all so paychecks still work if your backend doesn’t tag them yet.)
      // ✅ Always filter for this specific account.
// (If backend marks unknown/multi-account as -1, exclude those here.)
events = events.filter(e => Number(e.account_id) === Number(accountId));


      // Build delta map for remaining days
      const deltaByDate = {}; // { "YYYY-MM-DD": number }
      for (const e of events) {
        const d = String(e.date || "");
        if (!d) continue;
        if (d <= todayIso) continue; // only future days

        const amt = Number(e.amount) || 0;

        // Income rules:
        // - paychecks show cadence="paycheck"
        // - other income: type="income"
        const isIncome =
          (String(e.type || "").toLowerCase() === "income") ||
          (String(e.cadence || "") === "paycheck");

        const delta = isIncome ? amt : -Math.abs(amt);
        deltaByDate[d] = (deltaByDate[d] || 0) + delta;
      }

      // Align to your account series dates
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

  // % Growth (use potentialEOM when toggle is on)
  let growthStr = "—";
  if (values.length >= 2 && Math.abs(values[0]) > 1e-9) {
    const startVal = Number(values[0] || 0);
    const endValActual = Number(values[values.length - 1] || 0);
    const endValForGrowth =
      (showPotentialGrowth && typeof potentialEOM === "number") ? Number(potentialEOM) : endValActual;

    const pct = ((endValForGrowth - startVal) / Math.abs(startVal)) * 100;
    growthStr = (pct > 0 ? "+" : "") + pct.toFixed(2) + "%";
  }
  setInlineGrowthByIds(ACCOUNT_CHART_IDS, "% Growth", growthStr);

  // Inline breakdown
  const l = document.getElementById(ACCOUNT_CHART_IDS.breakLabel);
  const v = document.getElementById(ACCOUNT_CHART_IDS.breakValue);
  if (l) l.textContent = l.textContent || "Balance";
  if (v) v.textContent = money(last);

  const ctx = document.getElementById("accountChart").getContext("2d");
  if (chart) chart.destroy();

  const datasets = (() => {
    const base = { label: "Balance", data: values, tension: 0.2, pointRadius: 0, pointHitRadius: 12, pointHoverRadius: 4 };
    if (showPotentialGrowth && Array.isArray(potentialSeries)) {
      return [
        base,
        {
          label: "Projected",
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

  chart = new Chart(ctx, {
    type: "line",
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      devicePixelRatio: window.devicePixelRatio || 1,
      plugins: { legend: { display: false } },
      interaction: { mode:"index", intersect:false },
      scales: { y: { ticks: { callback: v => v.toLocaleString() } } }
    }
  });
}

function shortDate(mmddyyOrIso) {
  if (!mmddyyOrIso) return "";
  if (mmddyyOrIso.includes("/")) {
    const [m,d] = mmddyyOrIso.split("/");
    return `${m}/${d}`;
  }
  const d = new Date(mmddyyOrIso);
  return d.toLocaleDateString("en-US", { month:"2-digit", day:"2-digit" });
}

async function loadAccountTransactions(accountId){
  const start = document.getElementById("a-start").value;
  const end   = document.getElementById("a-end").value;
  if (!start || !end) return;

  const baseUrl =
  TX_MODE === "test"
    ? "/transactions-test-range"
    : "/account-transactions-range";

    const res = await fetch(
      `${baseUrl}?account_id=${accountId}&start=${start}&end=${end}&limit=500`,
      { cache: "no-store" }
    );


  if (!res.ok) {
    console.error("account-transactions-range failed:", res.status);
    const list = document.getElementById("txList");
    if (list) list.innerHTML = `<div style="padding:10px;">Failed to load (${res.status}).</div>`;
    return;
  }

  const payload = await res.json();
  const data = payload.transactions || [];

  const list = document.getElementById("txList");
  if (!list) return;

  list.innerHTML = "";

  if (!Array.isArray(data) || data.length === 0) {
    list.innerHTML = `<div style="padding:10px;">No transactions found in this range.</div>`;
    return;
  }

  data.forEach(row => {
    const wrap = document.createElement("div");
    wrap.className = "tx-row";

    wrap.innerHTML = `
      <div class="tx-date">${shortDate(row.effectiveDate || row.dateISO)}</div>
      <div class="tx-main">
        <div class="tx-merchant">${(row.merchant || "").toUpperCase()}</div>
        <div class="tx-sub"></div>
      </div>
      <div class="tx-right">
        <div class="tx-amt">${money(row.amount)}</div>
        <div class="tx-bal">${money(row.balance_after)}</div>
      </div>
    `;

    list.appendChild(wrap);
  });
}

function setActiveQuickButton(container, btn){
  container.querySelectorAll(".month-btn").forEach(b => b.classList.remove("active"));
  if (btn) btn.classList.add("active");
}

window.addEventListener("load", async () => {
  accountId = Number(qs("account_id"));
  if (!accountId) return alert("Missing account_id");

  // 1) mount the shared card FIRST
mountChartCard("#chartMount", {
  ids: ACCOUNT_CHART_IDS,
  title: "Balance",
  showToggle: false,

  // ✅ add this
  growthToggleHtml: `
    <div id="acctPotentialWrap">
      <label style="display:flex; align-items:center; gap:8px; user-select:none;">
        <input id="acctPotentialToggle" type="checkbox" />
        Projected growth
      </label>
    </div>
  `
});

const potentialToggle = document.getElementById("acctPotentialToggle");
if (potentialToggle) {
  potentialToggle.checked = showPotentialGrowth;

  potentialToggle.addEventListener("change", async () => {
    showPotentialGrowth = potentialToggle.checked;
    localStorage.setItem("showPotentialGrowth", String(showPotentialGrowth));

    const endInput = document.getElementById("a-end");
    if (!endInput) return;

    const todayIso = isoLocal(new Date());

    if (showPotentialGrowth) {
      // force projection to run through EOM (only meaningful for current month)
      if (!sameMonthISO(todayIso, endInput.value)) {
        // if they’re not viewing current month, just turn it back off
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

    await loadAccountChart(accountId);
  });
}


initChartControls(ACCOUNT_CHART_IDS, async () => {
  await loadAccountChart(accountId);
  await loadAccountTransactions(accountId);
});


  // 6) wire update button
  document.getElementById(ACCOUNT_CHART_IDS.update).addEventListener("click", async () => {
    await loadAccountChart(accountId);
    await loadAccountTransactions(accountId);
  });

  // 7) load content
  await loadAccountHeader(accountId);
  await loadAccountChart(accountId);
  await loadAccountTransactions(accountId);
});