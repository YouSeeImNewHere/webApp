function money(n){
  const num = Number(n || 0);
  return num.toLocaleString("en-US", { style:"currency", currency:"USD" });
}

function shortDate(mmddyyOrIso) {
  if (!mmddyyOrIso) return "";
  const s = String(mmddyyOrIso);
  if (s.includes("/")) {
    const [m,d] = s.split("/");
    return `${m}/${d}`;
  }
  const d = new Date(s);
  return d.toLocaleDateString("en-US", { month:"2-digit", day:"2-digit" });
}

function parseNum(x){
  if (x == null) return null;
  const s = String(x).trim();
  if (!s) return null;
  const v = Number(s.replace(/[^0-9.\-]/g, ""));
  return Number.isFinite(v) ? v : null;
}

function getEffectiveDate(row){
  return (row.postedDate && row.postedDate !== "unknown")
    ? row.postedDate
    : (row.purchaseDate && row.purchaseDate !== "unknown")
      ? row.purchaseDate
      : row.dateISO;
}

const PAGE_SIZE = 50;

let OFFSET = 0;
let LOADING = false;
let DONE = false;
let LAST_REQ_KEY = "";

function setStatus(msg){
  const el = document.getElementById("txStatus");
  if (el) el.textContent = msg || "";
}

function clearList(){
  const el = document.getElementById("allTxList");
  if (el) el.innerHTML = "";
}

function renderAppend(list){
  const el = document.getElementById("allTxList");
  if (!el) return;

  if (!list.length && OFFSET === 0){
    el.innerHTML = `<div style="padding:10px;">No matching transactions.</div>`;
    return;
  }

  list.forEach(row => {
    const wrap = document.createElement("div");
    wrap.className = "tx-row";
    wrap.dataset.txId = String(row.id ?? "");

    if (String(row.status || "").toLowerCase() === "pending") {
      wrap.classList.add("is-pending");
    }

    const sub = [row.bank, row.card].filter(Boolean).join(" • ");
    const amtNum = Number(row.amount || 0);
    const transferText = row.transfer_peer ? (amtNum > 0 ? `To: ${row.transfer_peer}` : `From: ${row.transfer_peer}`) : "";
    const effectiveDate = getEffectiveDate(row);

    wrap.innerHTML = `
      <div class="tx-icon-wrap tx-icon-hit" role="button" tabindex="0" aria-label="Transaction details">
        ${categoryIconHTML(row.category)}
      </div>
      <div class="tx-date">${shortDate(effectiveDate)}</div>
      <div class="tx-main">
        <div class="tx-merchant">${(row.merchant || "").toUpperCase()}</div>
        <div class="tx-sub">${sub}</div>
        <div class="tx-sub">${(row.category || "").trim()}${transferText ? " • " + transferText : ""}</div>
      </div>
      <div class="tx-amt">${money(row.amount)}</div>
    `;

    el.appendChild(wrap);
  });

  if (typeof window.attachTxInspect === 'function') window.attachTxInspect(el);
}

function buildQueryParams(){
  const q = (document.getElementById("txSearch")?.value || "").trim();
  const start = (document.getElementById("dateFrom")?.value || "").trim(); // YYYY-MM-DD
  const end = (document.getElementById("dateTo")?.value || "").trim();     // YYYY-MM-DD

  const mode = (document.getElementById("amtMode")?.value || "any").trim();
  const a = parseNum(document.getElementById("amtA")?.value);
  const b = parseNum(document.getElementById("amtB")?.value);
  const abs = !!document.getElementById("amtAbs")?.checked;

  let amt_min = null;
  let amt_max = null;

  if (mode === "exact" && a != null){
    amt_min = a; amt_max = a;
  } else if (mode === "min" && a != null){
    amt_min = a;
  } else if (mode === "max" && a != null){
    amt_max = a;
  } else if (mode === "between"){
    if (a != null) amt_min = a;
    if (b != null) amt_max = b;
    // if user swapped them, fix
    if (amt_min != null && amt_max != null && amt_min > amt_max){
      const t = amt_min; amt_min = amt_max; amt_max = t;
    }
  }

  const params = new URLSearchParams();
  params.set("limit", String(PAGE_SIZE));
  params.set("offset", String(OFFSET));

  if (q) params.set("q", q);
  if (start) params.set("start", start);
  if (end) params.set("end", end);

  if (mode !== "any") params.set("amt_mode", mode);
  if (amt_min != null) params.set("amt_min", String(amt_min));
  if (amt_max != null) params.set("amt_max", String(amt_max));
  if (abs) params.set("amt_abs", "1");

  return params;
}

function currentRequestKey(){
  // Used to detect filter changes between loads
  const p = buildQueryParams();
  // normalize offset out of key for "same filter"
  p.delete("offset");
  return p.toString();
}

async function loadNextPage(){
  if (LOADING || DONE) return;

  const reqKey = currentRequestKey();

  // If filters changed between page loads, don't continue the old stream
  if (LAST_REQ_KEY && LAST_REQ_KEY !== reqKey){
    return;
  }
  LAST_REQ_KEY = reqKey;

  LOADING = true;
  setStatus(OFFSET === 0 ? "Loading…" : "Loading more…");

  try{
    const params = buildQueryParams();
    const res = await fetch(`/transactions-all?${params.toString()}`, { cache: "no-store" });
    if (!res.ok) throw new Error(`Failed /transactions-all (${res.status})`);

    let rows = await res.json();
    if (!Array.isArray(rows)) rows = [];

    renderAppend(rows);

    if (rows.length < PAGE_SIZE){
      DONE = true;
      setStatus(rows.length ? "End of list." : "");
    } else {
      setStatus("");
    }

    OFFSET += rows.length;
  } finally {
    LOADING = false;
  }
}

function resetAndReload(){
  OFFSET = 0;
  DONE = false;
  LOADING = false;
  LAST_REQ_KEY = currentRequestKey();
  clearList();
  setStatus("");
  loadNextPage().catch(err => {
    console.error(err);
    setStatus("Failed to load transactions.");
  });
}

function debounce(fn, ms){
  let t = null;
  return (...args) => {
    if (t) clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
}

function initInfiniteScroll(){
  const sentinel = document.getElementById("txSentinel");
  if (!sentinel) return;

  const io = new IntersectionObserver((entries) => {
    for (const e of entries){
      if (e.isIntersecting){
        loadNextPage().catch(err => console.error(err));
      }
    }
  }, { root: null, rootMargin: "800px 0px", threshold: 0.01 });

  io.observe(sentinel);
}

function initFilters(){
  const onChange = debounce(() => resetAndReload(), 250);

  const ids = ["txSearch","dateFrom","dateTo","amtMode","amtA","amtB","amtAbs"];
  ids.forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    el.addEventListener("input", onChange);
    el.addEventListener("change", onChange);
  });

  const clearBtn = document.getElementById("clearFilters");
  if (clearBtn){
    clearBtn.addEventListener("click", () => {
      const txSearch = document.getElementById("txSearch");
      const dateFrom = document.getElementById("dateFrom");
      const dateTo = document.getElementById("dateTo");
      const amtMode = document.getElementById("amtMode");
      const amtA = document.getElementById("amtA");
      const amtB = document.getElementById("amtB");
      const amtAbs = document.getElementById("amtAbs");

      if (txSearch) txSearch.value = "";
      if (dateFrom) dateFrom.value = "";
      if (dateTo) dateTo.value = "";
      if (amtMode) amtMode.value = "any";
      if (amtA) amtA.value = "";
      if (amtB) amtB.value = "";
      if (amtAbs) amtAbs.checked = true;

      resetAndReload();
    });
  }

  // show/hide amtB depending on mode
  const amtModeEl = document.getElementById("amtMode");
  const amtBEl = document.getElementById("amtB");
  if (amtModeEl && amtBEl){
    const sync = () => {
      const mode = (amtModeEl.value || "any");
      amtBEl.disabled = (mode !== "between");
      amtBEl.style.opacity = (mode === "between") ? "1" : "0.55";
    };
    amtModeEl.addEventListener("change", sync);
    sync();
  }
}

document.addEventListener("DOMContentLoaded", () => {
  initInfiniteScroll();
  initFilters();
  resetAndReload();
});
