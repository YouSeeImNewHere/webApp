import { money } from "/static/shared/format.module.js";
import { shortDate } from "/static/shared/dates.module.js";

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
let ADD_TX_ACCOUNTS_LOADED = false;
let FILTER_OPTIONS_LOADED = false;

function setStatus(msg){
  const el = document.getElementById("txStatus");
  if (el) el.textContent = msg || "";
}

function updateLoadMoreButton(){
  const btn = document.getElementById("txLoadMoreBtn");
  if (!btn) return;
  btn.hidden = DONE;
  btn.disabled = LOADING || DONE;
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
    if (!!row?.is_ignored) {
      wrap.classList.add("is-ignored");
      wrap.dataset.ignored = "1";
    }

    if (String(row.status || "").toLowerCase() === "pending") {
      wrap.classList.add("is-pending");
    }

    const sub = [row.bank, row.card].filter(Boolean).join(" • ");
    const amtNum = Number(row.amount || 0);
    const transferText = row.transfer_peer ? (amtNum > 0 ? `To: ${row.transfer_peer}` : `From: ${row.transfer_peer}`) : "";
    const effectiveDate = getEffectiveDate(row);
    const roundupCents = Number(row.roundup_cents || 0);
    const roundupBadge = roundupCents > 0
      ? `<div class="tx-roundup-badge" title="Round-up cents used on this transaction">¢ ${roundupCents}</div>`
      : "";

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
      ${roundupBadge}
    `;

    el.appendChild(wrap);
  });

  if (typeof window.attachTxInspect === "function") window.attachTxInspect(el);
}

function buildQueryParams(){
  const merchant = (document.getElementById("qMerchant")?.value || "").trim();
  const card = (document.getElementById("qCard")?.value || "").trim();
  const category = (document.getElementById("qCategory")?.value || "").trim();

  const start = (document.getElementById("dateFrom")?.value || "").trim();
  const end = (document.getElementById("dateTo")?.value || "").trim();

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
    if (amt_min != null && amt_max != null && amt_min > amt_max){
      const t = amt_min; amt_min = amt_max; amt_max = t;
    }
  }

  const params = new URLSearchParams();
  params.set("limit", String(PAGE_SIZE));
  params.set("offset", String(OFFSET));

  if (merchant) params.set("merchant", merchant);
  if (card) params.set("card", card);
  if (category) params.set("category", category);
  if (start) params.set("start", start);
  if (end) params.set("end", end);

  if (mode !== "any") params.set("amt_mode", mode);
  if (amt_min != null) params.set("amt_min", String(amt_min));
  if (amt_max != null) params.set("amt_max", String(amt_max));
  if (abs) params.set("amt_abs", "1");

  return params;
}

function isoTodayLocal(){
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function currentRequestKey(){
  const p = buildQueryParams();
  p.delete("offset");
  return p.toString();
}

async function loadNextPage(){
  if (LOADING || DONE) return;

  const reqKey = currentRequestKey();
  if (LAST_REQ_KEY && LAST_REQ_KEY !== reqKey){
    return;
  }
  LAST_REQ_KEY = reqKey;

  LOADING = true;
  updateLoadMoreButton();
  setStatus(OFFSET === 0 ? "Loading..." : "Loading more...");

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
    updateLoadMoreButton();
  }
}

function resetAndReload(){
  OFFSET = 0;
  DONE = false;
  LOADING = false;
  LAST_REQ_KEY = currentRequestKey();
  clearList();
  setStatus("");
  updateLoadMoreButton();
  loadNextPage().catch(err => {
    console.error(err);
    setStatus("Failed to load transactions.");
  });
}

function initLoadMoreButton(){
  const btn = document.getElementById("txLoadMoreBtn");
  if (!btn) return;
  btn.addEventListener("click", () => {
    loadNextPage().catch(err => console.error(err));
  });
}

function setAddTxMessage(msg, isError = false){
  const el = document.getElementById("addTxMsg");
  if (!el) return;
  el.textContent = msg || "";
  el.classList.toggle("is-error", !!isError);
}

async function loadAddTxAccounts(){
  if (ADD_TX_ACCOUNTS_LOADED) return;
  const sel = document.getElementById("addTxAccount");
  if (!sel) return;

  sel.innerHTML = `<option value="">Loading accounts...</option>`;
  sel.disabled = true;
  try {
    const res = await fetch("/bank-info", { cache: "no-store" });
    if (!res.ok) throw new Error(`bank-info failed (${res.status})`);
    const payload = await res.json();
    const entries = [];
    (payload.accounts || []).forEach(a => {
      entries.push({
        id: Number(a.account_id),
        label: `${a.bank || ""} - ${a.name || ""}`.trim(),
        group: "Accounts",
      });
    });
    (payload.credit_cards || []).forEach(c => {
      entries.push({
        id: Number(c.card_id),
        label: `${c.bank || ""} - ${c.name || ""}`.trim(),
        group: "Cards",
      });
    });
    const rows = entries.filter(e => Number.isFinite(e.id) && e.id > 0);
    if (!rows.length) throw new Error("No accounts found");

    const groups = new Map();
    rows.forEach(r => {
      if (!groups.has(r.group)) groups.set(r.group, []);
      groups.get(r.group).push(r);
    });

    sel.innerHTML = "";
    groups.forEach((items, name) => {
      const og = document.createElement("optgroup");
      og.label = name;
      items.sort((a, b) => String(a.label).localeCompare(String(b.label)));
      items.forEach(item => {
        const opt = document.createElement("option");
        opt.value = String(item.id);
        opt.textContent = item.label || `Account ${item.id}`;
        og.appendChild(opt);
      });
      sel.appendChild(og);
    });
    sel.disabled = false;
    ADD_TX_ACCOUNTS_LOADED = true;
  } catch (err) {
    console.error(err);
    sel.innerHTML = `<option value="">Failed to load accounts</option>`;
    sel.disabled = true;
  }
}

function initAddTransactionUI(){
  const panel = document.getElementById("addTxPanel");
  const openBtn = document.getElementById("addTxBtn");
  const cancelBtn = document.getElementById("addTxCancelBtn");
  const saveBtn = document.getElementById("addTxSaveBtn");
  const dateEl = document.getElementById("addTxDate");
  const statusEl = document.getElementById("addTxStatus");
  const merchantEl = document.getElementById("addTxMerchant");
  const amountEl = document.getElementById("addTxAmount");
  const accountEl = document.getElementById("addTxAccount");

  if (!panel || !openBtn || !cancelBtn || !saveBtn) return;

  const open = async () => {
    panel.hidden = false;
    if (dateEl && !dateEl.value) dateEl.value = isoTodayLocal();
    setAddTxMessage("");
    await loadAddTxAccounts();
  };

  const close = () => {
    panel.hidden = true;
    setAddTxMessage("");
  };

  openBtn.addEventListener("click", () => { open().catch(err => console.error(err)); });
  cancelBtn.addEventListener("click", close);

  saveBtn.addEventListener("click", async () => {
    const accountId = Number(accountEl?.value || 0);
    const amount = parseNum(amountEl?.value);
    const merchant = (merchantEl?.value || "").trim();
    const status = (statusEl?.value || "posted").trim().toLowerCase();
    const date = (dateEl?.value || "").trim();

    if (!accountId) {
      setAddTxMessage("Pick an account.", true);
      return;
    }
    if (amount == null) {
      setAddTxMessage("Enter a valid amount.", true);
      return;
    }
    if (!date) {
      setAddTxMessage("Pick a date.", true);
      return;
    }

    saveBtn.disabled = true;
    setAddTxMessage("Saving...");
    try {
      const res = await fetch("/transaction", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          account_id: accountId,
          amount,
          merchant,
          status,
          date,
          source: "Manual",
        }),
      });
      let out = {};
      try { out = await res.json(); } catch (_) {}
      if (!res.ok || !out?.ok) {
        const errText = out?.detail?.error || out?.error || `Save failed (${res.status})`;
        throw new Error(String(errText));
      }

      if (amountEl) amountEl.value = "";
      if (merchantEl) merchantEl.value = "";
      close();
      resetAndReload();
    } catch (err) {
      console.error(err);
      setAddTxMessage(err?.message || "Failed to save transaction.", true);
    } finally {
      saveBtn.disabled = false;
    }
  });
}

function populateSelectOptions(selectEl, options, emptyLabel){
  if (!selectEl) return;
  const current = String(selectEl.value || "");
  const uniq = Array.from(new Set((options || []).map(v => String(v || "").trim()).filter(Boolean)));
  uniq.sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }));

  selectEl.innerHTML = "";
  const empty = document.createElement("option");
  empty.value = "";
  empty.textContent = emptyLabel || "Any";
  selectEl.appendChild(empty);

  uniq.forEach(v => {
    const opt = document.createElement("option");
    opt.value = v;
    opt.textContent = v;
    selectEl.appendChild(opt);
  });

  if (current && uniq.includes(current)) {
    selectEl.value = current;
  }
}

async function loadFilterOptions(){
  if (FILTER_OPTIONS_LOADED) return;
  const cardSel = document.getElementById("qCard");
  const categorySel = document.getElementById("qCategory");
  if (!cardSel || !categorySel) return;

  try {
    const [bankRes, categoriesRes] = await Promise.all([
      fetch("/bank-info", { cache: "no-store" }),
      fetch("/categories", { cache: "no-store" }),
    ]);

    const bankPayload = bankRes.ok ? await bankRes.json() : {};
    const categoriesPayload = categoriesRes.ok ? await categoriesRes.json() : [];

    const accountNames = []
      .concat((bankPayload?.accounts || []).map(a => String(a?.name || "").trim()))
      .concat((bankPayload?.credit_cards || []).map(c => String(c?.name || "").trim()))
      .filter(Boolean);
    const categories = Array.isArray(categoriesPayload)
      ? categoriesPayload.map(c => String(c || "").trim()).filter(Boolean)
      : [];

    populateSelectOptions(cardSel, accountNames, "Any account");
    populateSelectOptions(categorySel, categories, "Any category");
    FILTER_OPTIONS_LOADED = true;
  } catch (err) {
    console.error("Failed to load transaction filter options", err);
    populateSelectOptions(cardSel, [], "Any account");
    populateSelectOptions(categorySel, [], "Any category");
  }
}

function initFilters(){
  const searchBtn = document.getElementById("searchFilters");
  if (searchBtn) {
    searchBtn.addEventListener("click", () => {
      resetAndReload();
    });
  }

  const clearBtn = document.getElementById("clearFilters");
  if (clearBtn){
    clearBtn.addEventListener("click", () => {
      const qMerchant = document.getElementById("qMerchant");
      const qCard = document.getElementById("qCard");
      const qCategory = document.getElementById("qCategory");
      const dateFrom = document.getElementById("dateFrom");
      const dateTo = document.getElementById("dateTo");
      const amtMode = document.getElementById("amtMode");
      const amtA = document.getElementById("amtA");
      const amtB = document.getElementById("amtB");
      const amtAbs = document.getElementById("amtAbs");

      if (qMerchant) qMerchant.value = "";
      if (qCard) qCard.value = "";
      if (qCategory) qCategory.value = "";
      if (dateFrom) dateFrom.value = "";
      if (dateTo) dateTo.value = "";
      if (amtMode) amtMode.value = "any";
      if (amtA) amtA.value = "";
      if (amtB) amtB.value = "";
      if (amtAbs) amtAbs.checked = true;

      resetAndReload();
    });
  }

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
  loadFilterOptions().catch(err => console.error(err));
  initLoadMoreButton();
  initFilters();
  initAddTransactionUI();
  resetAndReload();
});



