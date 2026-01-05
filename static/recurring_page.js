let __mainData = [];
let __reopenIgnoredAfterOcc = false;

function money(n){
  const x = Number(n || 0);
  return x.toLocaleString(undefined, { style:"currency", currency:"USD" });
}

function shortDateISO(iso){
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { month:"2-digit", day:"2-digit", year:"2-digit" });
}

function esc(s){
  return String(s ?? "")
    .replaceAll("&","&amp;")
    .replaceAll("<","&lt;")
    .replaceAll(">","&gt;")
    .replaceAll('"',"&quot;")
    .replaceAll("'","&#39;");
}

let __lastData = []; // keep the fetched data for modal lookups

function merchantHTML(g){
  const m = (g.merchant || "").toUpperCase();
  const date = shortDateISO(g.last_seen);

  return `
    <div class="rec-merchant">
      <div>
        <div class="rec-merchant-name" title="${esc(m)}">${esc(m)}</div>
        <div class="rec-merchant-sub">${esc(date)}</div>
      </div>

      <div class="rec-merchant-actions">
        <button class="ignore-btn" onclick="mergeMerchantPrompt('${esc(g.merchant)}')">Merge</button>
        <button class="ignore-btn" onclick="ignoreMerchant('${esc(g.merchant)}')">Ignore</button>
      </div>
    </div>
  `;
}

function patternHTML(gIdx, pIdx, p){
  const freq = p.cadence || "irregular";
  const date = shortDateISO(p.last_seen);
  const occ  = `x${p.occurrences || 0}`;

  const merchant = p.merchant ?? __lastData[gIdx]?.merchant ?? "";
  const amount = p.amount;
  const accountId = p.account_id ?? -1; // optional if you include it from backend

  return `
    <div class="tx-row">
      <div class="occ-ico-wrap">
        <div class="occ-ico" title="Show transactions" onclick="openOccModal(${gIdx}, ${pIdx})">i</div>
      </div>

      <div class="tx-date">${esc(freq)}</div>

      <div class="tx-main">
        <div class="rec-sub">${esc(date)} • ${esc(occ)}</div>
        <div style="display:flex; gap:8px; margin-top:6px; flex-wrap:wrap;">
          <button class="ignore-btn" onclick="ignorePattern('${esc(merchant)}', ${Number(amount)}, ${Number(accountId)})">Ignore this</button>

          <select onchange="overrideCadence('${esc(merchant)}', ${Number(amount)}, this.value, ${Number(accountId)})">
            <option value="">Set cadence…</option>
            <option value="weekly">weekly</option>
            <option value="monthly">monthly</option>
            <option value="quarterly">quarterly</option>
            <option value="yearly">yearly</option>
            <option value="irregular">irregular</option>
          </select>
        </div>
      </div>

      <div class="tx-amt">${money(p.amount)}</div>
    </div>
  `;
}

function merchantHTMLIgnored(g){
  const m = (g.merchant || "").toUpperCase();
  const date = shortDateISO(g.last_seen);

  return `
    <div class="rec-merchant">
      <div>
        <div class="rec-merchant-name" title="${esc(m)}">${esc(m)}</div>
        <div class="rec-merchant-sub">${esc(date)}</div>
      </div>
      <div style="display:flex; gap:8px;">
        <button class="ignore-btn" onclick="mergeMerchantPrompt('${esc(g.merchant)}')">Merge</button>
        <button class="ignore-btn" onclick="unignoreMerchant('${esc(g.merchant)}')">Unignore</button>
      </div>
    </div>
  `;
}

function patternHTMLIgnored(gIdx, pIdx, p){
  const freq = p.cadence || "irregular";
  const date = shortDateISO(p.last_seen);
  const occ  = `x${p.occurrences || 0}`;

  const merchant = p.merchant ?? window.__ignoredData?.[gIdx]?.merchant ?? "";
  const amount = p.amount;
  const accountId = p.account_id ?? -1;

  return `
    <div class="tx-row">
      <div class="occ-ico-wrap">
        <div class="occ-ico" title="Show transactions" onclick="openOccFromIgnored(${gIdx}, ${pIdx})">i</div>
      </div>

      <div class="tx-date">${esc(freq)}</div>

      <div class="tx-main">
        <div class="rec-sub">${esc(date)} • ${esc(occ)}</div>
        <div style="display:flex; gap:8px; margin-top:6px; flex-wrap:wrap;">
          <button class="ignore-btn" onclick="ignorePattern('${esc(merchant)}', ${Number(amount)}, ${Number(accountId)})">Ignore this</button>

          <select onchange="overrideCadence('${esc(merchant)}', ${Number(amount)}, this.value, ${Number(accountId)})">
            <option value="">Set cadence…</option>
            <option value="weekly">weekly</option>
            <option value="monthly">monthly</option>
            <option value="quarterly">quarterly</option>
            <option value="yearly">yearly</option>
            <option value="irregular">irregular</option>
          </select>
        </div>
      </div>

      <div class="tx-amt">${money(p.amount)}</div>
    </div>
  `;
}

async function loadRecurring(){
  const list = document.getElementById("recurringList");
  const minOcc = document.getElementById("minOcc");
  const includeStale = document.getElementById("includeStale")?.checked ? "true" : "false";

  if (!list) return;

  list.innerHTML = `<div style="padding:12px; opacity:.7;">Loading…</div>`;

  const n = Number(minOcc?.value || 3);
  const res = await fetch(`/recurring?min_occ=${encodeURIComponent(n)}&include_stale=${includeStale}`);

  if (!res.ok){
    list.innerHTML = `<div style="padding:12px; color:#b00;">Failed to load (/recurring)</div>`;
    return;
  }

  const data = await res.json();
  __lastData = Array.isArray(data) ? data : [];
  __mainData = __lastData;


  if (!__lastData.length){
    list.innerHTML = `<div style="padding:12px; opacity:.7;">No recurring items found.</div>`;
    return;
  }

  list.innerHTML = __lastData.map((g, gi) => (
    merchantHTML(g) + (g.patterns || []).map((p, pi) => patternHTML(gi, pi, p)).join("")
  )).join("");
}

async function ignoreMerchant(name){
  await fetch(`/recurring/ignore/merchant?name=${encodeURIComponent(name)}`, { method: "POST" });
  loadRecurring();
}

/* ---------- Modal ---------- */

function openOccModal(groupIndex, patternIndex){
  const g = __lastData[groupIndex];
  const p = g?.patterns?.[patternIndex];
  if (!g || !p) return;

  const modal = document.getElementById("occModal");
  const title = document.getElementById("occTitle");
  const sub   = document.getElementById("occSub");
  const body  = document.getElementById("occBody");

  const merch = (g.merchant || "").toUpperCase();
  const freq  = p.cadence || "irregular";
  const occ   = `x${p.occurrences || 0}`;

  title.textContent = merch;
  sub.textContent = `${freq} • ${shortDateISO(p.last_seen)} • ${occ} • ${money(p.amount)}`;

  const tx = Array.isArray(p.tx) ? p.tx : [];
  body.innerHTML = tx.map(t => `
    <div class="occ-tx">
      <div class="occ-left">
        <div class="occ-date">${esc(shortDateISO(t.date))}</div>
        <div class="occ-merchant">${esc((t.merchant || "").toUpperCase())}</div>
        <div class="occ-meta">${esc(t.category || "")}${t.account_id ? " • acct " + esc(t.account_id) : ""}</div>
      </div>
      <div class="occ-amt">${money(t.amount)}</div>
    </div>
  `).join("") || `<div style="opacity:.7; padding:8px 0;">No transactions found.</div>`;

  modal.classList.remove("hidden");
}

function openOccFromIgnored(groupIndex, patternIndex){
  if (Array.isArray(window.__ignoredData)) {
    __reopenIgnoredAfterOcc = true;
    closeIgnoredModal();
    __lastData = window.__ignoredData;
    openOccModal(groupIndex, patternIndex);
  }
}


function closeOccModal(){
  document.getElementById("occModal")?.classList.add("hidden");

  if (__reopenIgnoredAfterOcc){
    __reopenIgnoredAfterOcc = false;
    openIgnoredModal(); // re-open the ignored modal after closing details
  }
}


document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    closeOccModal();
    closeIgnoredModal();
  }
});

async function ignorePattern(merchant, amount, accountId){
  await fetch(`/recurring/ignore/pattern?merchant=${encodeURIComponent(merchant)}&amount=${encodeURIComponent(amount)}&account_id=${encodeURIComponent(accountId ?? -1)}`, {
    method: "POST"
  });
  loadRecurring();
}

async function overrideCadence(merchant, amount, cadence, accountId){
  await fetch(`/recurring/override-cadence?merchant=${encodeURIComponent(merchant)}&amount=${encodeURIComponent(amount)}&cadence=${encodeURIComponent(cadence)}&account_id=${encodeURIComponent(accountId ?? -1)}`, {
    method: "POST"
  });
  loadRecurring();
}

document.getElementById("reloadRecurring")?.addEventListener("click", loadRecurring);
document.getElementById("includeStale")?.addEventListener("change", loadRecurring);
loadRecurring();

async function mergeMerchantPrompt(alias){
  const canonical = prompt(
    `Merge merchant:\n\n${alias}\n\nInto canonical merchant (type name exactly as shown):`
  );
  if (!canonical) return;

  await fetch(
    `/recurring/merchant-alias?alias=${encodeURIComponent(alias)}&canonical=${encodeURIComponent(canonical)}`,
    { method: "POST" }
  );

  loadRecurring();
}

function closeIgnoredModal(){
  document.getElementById("ignoredModal")?.classList.add("hidden");
}

async function openIgnoredModal(){
  const modal = document.getElementById("ignoredModal");
  const body  = document.getElementById("ignoredBody");
  if (!modal || !body) return;

  body.innerHTML = `<div style="opacity:.7; padding:8px 0;">Loading…</div>`;
  modal.classList.remove("hidden");

  const n = Number(document.getElementById("minOcc")?.value || 3);
  const includeStale = document.getElementById("includeStale")?.checked ? "true" : "false";

  const res = await fetch(`/recurring/ignored-preview?min_occ=${encodeURIComponent(n)}&include_stale=${includeStale}`);
  if (!res.ok){
    body.innerHTML = `<div style="color:#b00;">Failed to load ignored preview.</div>`;
    return;
  }

  const data = await res.json();
  const groups = Array.isArray(data) ? data : [];

  if (!groups.length){
    body.innerHTML = `<div style="opacity:.7; padding:8px 0;">No ignored merchants (or none match min occurrences).</div>`;
    return;
  }

    // store for modal drilldown
  window.__ignoredData = groups;

  body.innerHTML = groups.map((g, gi) => (
    merchantHTMLIgnored(g) + (g.patterns || []).map((p, pi) => patternHTMLIgnored(gi, pi, p)).join("")
  )).join("");


  // store for modal drilldown
  window.__ignoredData = groups;
}

async function unignoreMerchant(name){
  await fetch(`/recurring/unignore/merchant?name=${encodeURIComponent(name)}`, { method: "POST" });
  await openIgnoredModal(); // refresh ignored list
  loadRecurring();          // refresh main list
}

document.getElementById("reviewIgnored")?.addEventListener("click", openIgnoredModal);