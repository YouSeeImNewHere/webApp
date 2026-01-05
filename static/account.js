let chart = null;
let accountId = null;
const TX_MODE = window.TX_MODE || "prod";


const ACCOUNT_CHART_IDS = {
  title: "aChartTitle",
  dots: "aChartDots",
  toggle: "aChartToggle", // will be hidden on this page
  breakLabel: "aBreakLabel",
  breakValue: "aBreakValue",
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
  monthButtons: "aButtons"
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

// ✅ write directly to the card’s breakdown elements
const l = document.getElementById(ACCOUNT_CHART_IDS.breakLabel);
const v = document.getElementById(ACCOUNT_CHART_IDS.breakValue);
if (l) l.textContent = l.textContent || "Balance"; // keep accountType from loadAccountHeader()
if (v) v.textContent = money(last);


  const ctx = document.getElementById("accountChart").getContext("2d");
  if (chart) chart.destroy();

  chart = new Chart(ctx, {
  type: "line",
  data: { labels, datasets: [{ label: "Balance", data: values, tension: 0.2, pointRadius: 0 }] },
  options: {
    responsive: true,
    plugins: { legend: { display: false } }, // ✅ hide legend
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
    showToggle: false
  });
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