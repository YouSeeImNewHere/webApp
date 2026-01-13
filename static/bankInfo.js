function isoToday(){
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function money(v){
  if (v === null || v === undefined) return "—";
  const n = Number(v);
  if (Number.isNaN(n)) return String(v);
  return n.toLocaleString(undefined, { style:"currency", currency:"USD" });
}

function pct(v){
  if (v === null || v === undefined) return "—";
  const n = Number(v);
  if (Number.isNaN(n)) return String(v);
  return (n).toFixed(2) + "%";
}

function openBankPanel(){
  document.getElementById("bankInfoOverlay").classList.remove("hidden");
  document.getElementById("bankInfoPanel").classList.remove("hidden");
}

function closeBankPanel(){
  document.getElementById("bankInfoOverlay").classList.add("hidden");
  document.getElementById("bankInfoPanel").classList.add("hidden");
}

async function loadBankInfo(){
  const subtitle = document.getElementById("bankInfoSubtitle");
  const body = document.getElementById("bankInfoBody");
  subtitle.textContent = "Loading…";
  body.innerHTML = "";
  body.innerHTML = `
  <div class="bank-rate-editor">
    <div class="bank-rate-editor__title">Set a new rate</div>

    <div class="bank-rate-editor__row">
      <label>Account</label>
      <select id="rateAccount"></select>
    </div>

    <div class="bank-rate-editor__row">
      <label>Rate (%)</label>
      <input id="ratePercent" type="number" step="0.01" placeholder="e.g. 3.54" />
    </div>

    <div class="bank-rate-editor__row">
      <label>Effective date</label>
      <input id="rateDate" type="date" />
    </div>

    <div class="bank-rate-editor__row">
      <label>Note</label>
      <input id="rateNote" type="text" placeholder="optional" />
    </div>

    <div class="bank-rate-editor__actions">
      <button id="rateSaveBtn" class="btn">Save rate</button>
      <div id="rateSaveMsg" class="mini-note"></div>
    </div>

    <hr class="section-divider" style="margin:14px 0;" />
  </div>
`;


  const res = await fetch("/bank-info");
  if (!res.ok){
    subtitle.textContent = "Failed to load.";
    body.innerHTML = `<div class="mini-note">Server returned ${res.status}</div>`;
    return;
  }

  const data = await res.json();
  subtitle.textContent = `Last updated: ${data.last_updated || "—"}`;
  // Populate account dropdown (accounts + credit cards)
const sel = document.getElementById("rateAccount");
const dateEl = document.getElementById("rateDate");
dateEl.value = isoToday();

const opts = [];
(data.accounts || []).forEach(a => {
  opts.push({
    id: a.account_id,
    label: `${a.bank} — ${a.name} (APY)`
  });
});
(data.credit_cards || []).forEach(c => {
  opts.push({
    id: c.card_id,
    label: `${c.bank} — ${c.name} (APR)`
  });
});

sel.innerHTML = opts.map(o => `<option value="${o.id}">${o.label}</option>`).join("");

// Save handler
document.getElementById("rateSaveBtn").onclick = async () => {
  const msg = document.getElementById("rateSaveMsg");
  msg.textContent = "";

  const accountId = Number(sel.value);
  const ratePercent = Number(document.getElementById("ratePercent").value);
  const effectiveDate = document.getElementById("rateDate").value || isoToday();
  const note = document.getElementById("rateNote").value || "";

  if (!accountId || Number.isNaN(accountId)){
    msg.textContent = "Pick an account.";
    return;
  }
  if (Number.isNaN(ratePercent)){
    msg.textContent = "Enter a rate percent (example: 3.54).";
    return;
  }

  const res = await fetch("/interest-rate", {
    method: "POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify({
      account_id: accountId,
      rate_percent: ratePercent,
      effective_date: effectiveDate,
      note: note
    })
  });

  if (!res.ok){
    msg.textContent = `Save failed (HTTP ${res.status}).`;
    return;
  }

  const out = await res.json();
  if (!out.ok){
    msg.textContent = out.error || "Save failed.";
    return;
  }

  msg.textContent = "Saved.";
  await loadBankInfo(); // refresh panel values
};


  // Accounts (deposit/interest-bearing)
  // Accounts (savings / checking)
const accounts = data.accounts || [];
if (accounts.length){
  const section = document.createElement("div");
  section.className = "bank-section";

  section.innerHTML = `
    <div class="bank-section__header">
      <h2>Accounts</h2>
      <div class="bank-section__sub">Savings & checking</div>
    </div>
  `;

  accounts.forEach(a => {
    const card = document.createElement("div");
    card.className = "bank-card";

    card.innerHTML = `
      <div class="bank-card__title">
        ${a.bank} — ${a.name || ("Account " + a.account_id)}
      </div>

      <div class="kv kv--spaced">
        <div class="k">Type</div><div class="v">${a.type || "—"}</div>
        <div class="k">APY</div><div class="v apy">${pct(a.apy)}</div>
      </div>

      ${a.notes ? `<div class="mini-note">${a.notes}</div>` : ``}
    `;

    section.appendChild(card);
  });

  body.appendChild(section);
}

  // Credit cards
const cards = data.credit_cards || [];
if (cards.length){
  const section = document.createElement("div");
  section.className = "bank-section";

  section.innerHTML = `
    <div class="bank-section__header">
      <h2>Credit cards</h2>
      <div class="bank-section__sub">APR, limits & rewards</div>
    </div>
  `;

  cards.forEach(c => {
    const card = document.createElement("div");
    card.className = "bank-card";

    const benefits = (c.benefits || []).map(b => {
      const cats = (b.categories || []).join(", ");
      return `
        <div class="kv kv--benefit">
          <div class="k">${cats || "Cash back"}</div>
          <div class="v">${pct(b.cashback_percent)}</div>
        </div>
      `;
    }).join("");

    card.innerHTML = `
      <div class="bank-card__title">
        ${c.bank} — ${c.name || ("Card " + c.card_id)}
      </div>

      <div class="kv kv--spaced">
        <div class="k">APR</div><div class="v">${pct(c.apr)}</div>
        <div class="k">Limit</div><div class="v">${money(c.credit_limit)}</div>
      </div>

      ${benefits || `<div class="mini-note">No benefits saved.</div>`}
    `;

    section.appendChild(card);
  });

  body.appendChild(section);
}


  if (!accounts.length && !cards.length){
    body.innerHTML = `<div class="mini-note">No bank info saved yet.</div>`;
  }
}

function refreshInterestRates(){
  // just jump to the editor at top
  const el = document.querySelector(".bank-rate-editor");
  if (el) el.scrollIntoView({behavior:"smooth", block:"start"});
}

document.addEventListener("DOMContentLoaded", () => {
  const btn = document.getElementById("bankInfoBtn");
  const close = document.getElementById("bankInfoClose");
  const overlay = document.getElementById("bankInfoOverlay");
  const refreshBtn = document.getElementById("bankRatesRefreshBtn");

  if (!btn) return;

  btn.addEventListener("click", async () => {
    openBankPanel();
    await loadBankInfo();
  });

  close.addEventListener("click", closeBankPanel);
  overlay.addEventListener("click", closeBankPanel);
  refreshBtn.addEventListener("click", refreshInterestRates);

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeBankPanel();
  });
});
