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

let ALL = [];

function render(list){
  const el = document.getElementById("allTxList");
  if (!el) return;

  el.innerHTML = "";

  if (!list.length){
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

  // ✅ compute effective date OUTSIDE the template
  const effectiveDate =
    row.postedDate && row.postedDate !== "unknown"
      ? row.postedDate
      : row.purchaseDate && row.purchaseDate !== "unknown"
        ? row.purchaseDate
        : row.dateISO;

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

  if (typeof attachTxInspect === 'function') attachTxInspect(el);
}

function applySearch(){
  const q = (document.getElementById("txSearch")?.value || "").trim().toLowerCase();
  if (!q) return render(ALL);

  const filtered = ALL.filter(r => {
    const hay = [
      r.merchant || "",
      r.bank || "",
      r.card || "",
      r.postedDate || ""
    ].join(" ").toLowerCase();
    return hay.includes(q);
  });

  render(filtered);
}

async function init(){
  const el = document.getElementById("allTxList");
  if (el) el.innerHTML = `<div style="padding:10px;">Loading…</div>`;

  // If your backend already has /transactions, use it:
  const res = await fetch("/transactions-all?limit=10000", { cache: "no-store" });

  if (!res.ok) throw new Error("Failed to load /transactions");

  ALL = await res.json();
  if (!Array.isArray(ALL)) ALL = [];

  render(ALL);

  const input = document.getElementById("txSearch");
  if (input){
    input.addEventListener("input", applySearch);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  init().catch(err => {
    console.error(err);
    const el = document.getElementById("allTxList");
    if (el) el.innerHTML = `<div style="padding:10px;">Failed to load transactions.</div>`;
  });
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

