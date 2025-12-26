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

    const sub = [row.bank, row.card].filter(Boolean).join(" • ");

    wrap.innerHTML = `
      <div class="tx-date">${shortDate(row.postedDate)}</div>
      <div class="tx-main">
        <div class="tx-merchant">${(row.merchant || "").toUpperCase()}</div>
        <div class="tx-sub">${sub}</div>
      </div>
      <div class="tx-amt">${money(row.amount)}</div>
    `;

    el.appendChild(wrap);
  });
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
