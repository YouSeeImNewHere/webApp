let chart = null;

const TX_MODE = window.TX_MODE || "prod";


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
  // ✅ In test mode, keep the hardcoded header in transactions_test_account.html
  if (TX_MODE === "test") return;

  const res = await fetch(`/account/${accountId}`);
  const a = await res.json();
  document.getElementById("accountTitle").textContent = `${a.institution} — ${a.name}`;
  document.getElementById("accountMeta").textContent = `Type: ${a.accountType}`;
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

function buildQuickButtons(accountId){
  const el = document.getElementById("aButtons");
  const today = new Date();
  const year = today.getFullYear();

  const add = (label, start, end, makeActive=false) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "month-btn";
    b.textContent = label;

    b.addEventListener("click", async () => {
      document.getElementById("a-start").value = toISODate(start);
      document.getElementById("a-end").value   = toISODate(end);
      setActiveQuickButton(el, b);
      await loadAccountChart(accountId);
      await loadAccountTransactions(accountId);
    });

    el.appendChild(b);

    if (makeActive) setActiveQuickButton(el, b);
    return b;
  };

  el.innerHTML = "";

  // Default active: This Month
  add("This Month", new Date(year, today.getMonth(), 1), today, true);

  add("YTD", new Date(year, 0, 1), today);

  const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  months.forEach((m, i) => add(m, firstDayOfMonth(year, i), lastDayOfMonth(year, i)));
}


window.addEventListener("load", async () => {
  const accountId = Number(qs("account_id"));
  if (!accountId) return alert("Missing account_id");

  const today = new Date();
  const firstOfMonth = new Date(today.getFullYear(), today.getMonth(), 1);

  document.getElementById("a-start").value = toISODate(firstOfMonth);
  document.getElementById("a-end").value   = toISODate(today);

  await loadAccountHeader(accountId);
  buildQuickButtons(accountId);

  document.getElementById("a-update").addEventListener("click", async () => {
    await loadAccountChart(accountId);
    await loadAccountTransactions(accountId);
  });

  await loadAccountChart(accountId);
  await loadAccountTransactions(accountId);
});

function buildQuickButtons(accountId){
  const btnWrap = document.getElementById("aButtons");
  const sel = document.getElementById("aMonthSelect");

  const today = new Date();
  const year = today.getFullYear();

  btnWrap.innerHTML = "";
  if (sel) sel.innerHTML = "";

  // helper: apply range + refresh
  const applyRange = async (start, end, activeBtn=null) => {
    document.getElementById("a-start").value = toISODate(start);
    document.getElementById("a-end").value   = toISODate(end);

    // buttons active state
    btnWrap.querySelectorAll(".month-btn").forEach(b => b.classList.remove("active"));
    if (activeBtn) activeBtn.classList.add("active");

    await loadAccountChart(accountId);
    await loadAccountTransactions(accountId);
  };

  // define options once, used by BOTH UI types
  const options = [];
  options.push({ label: "This Month", start: new Date(year, today.getMonth(), 1), end: today, makeActive: true });
  options.push({ label: "YTD",        start: new Date(year, 0, 1),               end: today });

  const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  months.forEach((m, i) => {
    options.push({ label: m, start: firstDayOfMonth(year, i), end: lastDayOfMonth(year, i) });
  });

  // build DESKTOP buttons
  options.forEach(opt => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "month-btn";
    b.textContent = opt.label;

    b.addEventListener("click", () => applyRange(opt.start, opt.end, b));
    btnWrap.appendChild(b);

    if (opt.makeActive) b.classList.add("active");
  });

  // build MOBILE dropdown
  if (sel){
    options.forEach((opt, idx) => {
      const o = document.createElement("option");
      o.value = String(idx);
      o.textContent = opt.label;
      sel.appendChild(o);
    });

    // default selection: "This Month"
    sel.value = "0";

    sel.addEventListener("change", async () => {
      const opt = options[Number(sel.value)];
      await applyRange(opt.start, opt.end, null);
    });
  }

  // ensure default loads match "This Month"
  // (your window.load already sets dates + loads, so this is optional)
}
