let currentReceiptId = null;
let lastOcrDebug = null;

async function copyText(text) {
  // Modern secure-context clipboard
  if (navigator.clipboard && navigator.clipboard.writeText) {
    await navigator.clipboard.writeText(text);
    return true;
  }

  // Fallback for http / older browsers
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.setAttribute("readonly", "");
  ta.style.position = "fixed";
  ta.style.left = "-9999px";
  ta.style.top = "0";
  document.body.appendChild(ta);
  ta.select();

  let ok = false;
  try {
    ok = document.execCommand("copy");
  } catch (e) {
    ok = false;
  }
  document.body.removeChild(ta);
  return ok;
}


async function api(url, opts={}) {
  const res = await fetch(url, opts);
  if (!res.ok) {
    const t = await res.text();
    throw new Error(`HTTP ${res.status}: ${t}`);
  }
  return res.json();
}

function el(id){ return document.getElementById(id); }

function isoToMMDDYY(iso){
  // iso: YYYY-MM-DD
  if (!iso || typeof iso !== "string") return "";
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!m) return "";
  const yy = m[1].slice(-2);
  return `${m[2]}/${m[3]}/${yy}`;
}

function fmtReceiptDate(r){
  // Prefer already-mmddyy field if present
  if (r && r.parsed_json && r.parsed_json.purchase_date_mmddyy) return r.parsed_json.purchase_date_mmddyy;
  if (r && r.purchase_date) return isoToMMDDYY(r.purchase_date) || r.purchase_date;
  return "";
}

async function loadReceipts() {
  const q = el("q").value.trim();

  const params = new URLSearchParams();
  if (q) params.set("q", q);

  const data = await api(`/receipts?${params.toString()}`);
  const list = el("list");
  list.innerHTML = "";

  for (const r of data.receipts) {
    const div = document.createElement("div");
    div.className = "card grid";
    div.innerHTML = `
      <div>
        <div style="font-weight:700;">
          ${r.merchant_name || "(unknown merchant)"}
          <span class="pill">${r.parse_status}</span>
        </div>
        <div class="muted">
          ${fmtReceiptDate(r) || "no date"} • ${r.total != null ? "$" + r.total.toFixed(2) : "no total"} • ${r.original_filename || ""}
        </div>
        <div class="muted">confidence: ${r.confidence ?? "—"}</div>
      </div>
      <div class="row" style="justify-content:flex-end;">
        <button class="btn" data-open="${r.id}">Open</button>
        <button class="btn" data-reprocess="${r.id}">Reprocess</button>
        <button class="btn primary" data-verify="${r.id}">Verify/Attach</button>
      </div>
    `;
    list.appendChild(div);
  }

  list.querySelectorAll("[data-open]").forEach(btn => {
    btn.addEventListener("click", () => {
      const id = btn.getAttribute("data-open");
      window.open(`/receipts/${id}/image`, "_blank");
    });
  });

  list.querySelectorAll("[data-verify]").forEach(btn => {
    btn.addEventListener("click", () => openVerify(btn.getAttribute("data-verify")));
  });

  list.querySelectorAll("[data-reprocess]").forEach(btn => {
    btn.addEventListener("click", async () => {
      const id = btn.getAttribute("data-reprocess");
      btn.disabled = true;
      btn.textContent = "Reprocessing…";
      try {
        await api(`/receipts/${id}/reprocess`, { method: "POST" });
        await loadReceipts();
      } catch (e) {
        alert("Reprocess failed: " + e.message);
      } finally {
        btn.disabled = false;
        btn.textContent = "Reprocess";
      }
    });
  });
}

async function uploadReceipt() {
  const f = el("file").files[0];
  if (!f) return alert("Choose a receipt image first.");

  const fd = new FormData();
  fd.append("file", f);

  el("uploadBtn").disabled = true;
  try {
    const out = await api("/receipts/upload", { method: "POST", body: fd });
    await loadReceipts();
    // jump straight into verify UI
    await openVerify(out.receipt_id);
  } finally {
    el("uploadBtn").disabled = false;
    el("file").value = "";
  }
}

async function loadOcrDebug(receiptId) {
  try {
    const r = await api(`/receipts/${receiptId}/ocr_debug`);
    const o = r && r.ocr;
    lastOcrDebug = o;

    // If we don't have debug data, keep the panel blank (no hard errors).
    if (!o || !o.variants || !o.runs) {
      if (el("dbgMeta")) el("dbgMeta").textContent = "No OCR debug loaded.";
      if (el("dbgText")) el("dbgText").value = "";
      if (el("dbgFused")) el("dbgFused").value = "";
      if (el("dbgThumbs")) el("dbgThumbs").innerHTML = "";
      return;
    }

    // pick winner run
    const w = o.winner || {};
    const winnerRun = o.runs.find(x => x.variant === w.variant && x.config === w.config) || o.runs[0];

    // set main image
    const imgUrl = (o.variants[w.variant] && o.variants[w.variant].img_url) || (o.variants[0] && o.variants[0].img_url);
    if (imgUrl) el("dbgImg").src = imgUrl;

    // meta + text
    el("dbgMeta").textContent = `winner: variant ${w.variant}, score ${w.score}, config: ${w.config}`;
    el("dbgText").value = (winnerRun && winnerRun.text) || "";

    // combined (fused) text (server-side heuristic)
    if (el("dbgFused")) {
      el("dbgFused").value = o.fused_text || "";
    }

    // fused text (server-side heuristic)
    if (el("dbgFused")) el("dbgFused").value = o.fused_text || "";

    // thumbs
    const thumbs = el("dbgThumbs");
    thumbs.innerHTML = "";

    // Option B: overlay image with fused line boxes
    if (o.overlay_url) {
      const b = document.createElement("button");
      b.className = "btn";
      b.textContent = "overlay";
      b.onclick = () => {
        el("dbgImg").src = o.overlay_url;
        el("dbgMeta").textContent = "overlay: fused line boxes";
      };
      thumbs.appendChild(b);
    }

    o.variants.forEach(v => {
      if (!v.img_url) return;
      const b = document.createElement("button");
      b.className = "btn";
      b.textContent = `v${v.variant}`;
      b.onclick = () => {
        el("dbgImg").src = v.img_url;
        // show best run for this variant (highest score)
        const bestForV = o.runs
          .filter(x => x.variant === v.variant && x.text)
          .sort((a,b) => (b.score||0) - (a.score||0))[0];
        el("dbgText").value = (bestForV && bestForV.text) || "";
        el("dbgMeta").textContent = `variant ${v.variant} best score ${(bestForV && bestForV.score) || 0} config ${(bestForV && bestForV.config) || ""}`;
      };
      thumbs.appendChild(b);
    });
  } catch (e) {
    // ok to ignore
  }
}


async function openVerify(receiptId) {
  currentReceiptId = receiptId;
  el("modalBack").style.display = "flex";
  el("imgPrev").src = `/receipts/${receiptId}/image`;

  // Always reset fields so you don't see stale data if a call fails
  el("mMerchant").value = "";
  el("mDate").value = "";
  el("mTotal").value = "";
  el("mConf").textContent = "status: — • confidence: —";
  el("itemsBox").innerHTML = `<div class="muted">No items parsed.</div>`;
  if (el("addrBox")) el("addrBox").textContent = "";
  if (el("addrCard")) el("addrCard").style.display = "none";

  // Reset OCR debug panel (avoid stale data)
  if (el("dbgMeta")) el("dbgMeta").textContent = "No OCR debug loaded yet.";
  if (el("dbgText")) el("dbgText").value = "";
  if (el("dbgFused")) el("dbgFused").value = "";
  if (el("dbgThumbs")) el("dbgThumbs").innerHTML = "";
  if (el("dbgImg")) el("dbgImg").src = "";

  // 1) Load base receipt row (may fail or be null)
  let r = null;
  try {
    r = await api(`/receipts/${receiptId}`);
  } catch (e) {
    console.warn("Failed to load /receipts/{id}", e);
  }

  // 2) Load parsed payload from dedicated endpoint (more reliable)
  let parsedWrap = null;
  try {
    parsedWrap = await api(`/receipts/${receiptId}/parsed`);
  } catch (e) {
    console.warn("Failed to load /receipts/{id}/parsed", e);
  }

  const parsed = (parsedWrap && parsedWrap.parsed) ? parsedWrap.parsed : (r && r.parsed_json ? r.parsed_json : {});

  // Address (optional)
  const addr = parsed.address || parsed.store_address || null;
  if (el("addrCard")) el("addrCard").style.display = addr ? "block" : "none";
  if (el("addrBox")) el("addrBox").textContent = addr ? formatAddress(addr) : "";

  // Fill UI using best available source
  el("mMerchant").value = (r && r.merchant_name) || parsed.merchant_name || "";
  // Prefer MM/DD/YY for user input
  el("mDate").value = parsed.purchase_date_mmddyy || isoToMMDDYY((r && r.purchase_date) || parsed.purchase_date) || "";
  el("mTotal").value = ((r && r.total != null) ? r.total : (parsed.total != null ? parsed.total : "")) ?? "";

  const status = (r && r.parse_status) || (parsed ? "parsed" : "—");
  const conf = (r && (r.confidence != null ? r.confidence : null)) ?? parsed.confidence ?? "—";
  el("mConf").textContent = `status: ${status} • confidence: ${conf}`;

  // Render items
  const itemsBox = el("itemsBox");
  const items = (parsed && parsed.items) ? parsed.items : [];
  if (!items.length) {
    itemsBox.innerHTML = `<div class="muted">No items parsed.</div>`;
  } else {
    itemsBox.innerHTML = items.map(it => {
      const name = (it && (it.name || it.desc || it.description)) || "";
      const price = Number((it && it.price) != null ? it.price : 0);
      const meta = (it && it.meta && Array.isArray(it.meta) && it.meta.length) ? it.meta.join(" • ") : "";
      return `
        <div style="padding:6px 0; border-bottom:1px solid #eee;">
          <div style="display:flex; justify-content:space-between; gap:10px;">
            <div>${name}</div>
            <div style="font-weight:700;">$${price.toFixed(2)}</div>
          </div>
          ${meta ? `<div class=\"muted\" style=\"margin-top:2px;\">${meta}</div>` : ""}
        </div>
      `;
    }).join("");
  }

  // Load OCR debug regardless of whether we have any transaction candidates
  await loadOcrDebug(receiptId);

  await loadCandidates(receiptId);
}

async function loadCandidates(receiptId) {
  const data = await api(`/receipts/${receiptId}/candidates`);
  const wrap = el("candidates");
  wrap.innerHTML = "";

  if (!data.candidates.length) {
    wrap.innerHTML = `<div class="muted" style="margin-top:10px;">No candidates found (try saving verified first).</div>`;
    // Still show OCR debug (it previously disappeared due to this return)
    await loadOcrDebug(receiptId);
    return;
  }

  for (const tx of data.candidates) {
    const div = document.createElement("div");
    div.className = "cand";
    div.innerHTML = `
      <div style="font-weight:700;">
        ${tx.merchant || "(unknown)"} — $${Number(tx.amount).toFixed(2)}
        <span class="pill">score ${tx._match_score ?? "—"}</span>
      </div>
      <div class="muted">
        purchase: ${isoToMMDDYY(tx.purchaseDate) || tx.purchaseDate || "—"} • posted: ${isoToMMDDYY(tx.postedDate) || tx.postedDate || "—"} • category: ${tx.category || "—"}
      </div>
      <div class="muted">id: ${tx.id}</div>
    `;
    div.addEventListener("click", async () => {
      await attachToTx(tx.id);
    });
    wrap.appendChild(div);
  }
}

async function reprocessReceipt() {
  if (!currentReceiptId) return;

  el("reparseBtn").disabled = true;
  el("mConf").textContent = "status: reprocessing…";

  try {
    await api(`/receipts/${currentReceiptId}/reprocess`, {
      method: "POST"
    });

    // Reload modal data so you see new results
    await openVerify(currentReceiptId);
  } catch (e) {
    alert("Re-run failed: " + e.message);
  } finally {
    el("reparseBtn").disabled = false;
  }
}

async function saveVerified() {
  if (!currentReceiptId) return;

  const body = {
    merchant_name: el("mMerchant").value.trim() || null,
    purchase_date: el("mDate").value.trim() || null,
    total: el("mTotal").value.trim() ? Number(el("mTotal").value.trim()) : null
  };

  await api(`/receipts/${currentReceiptId}/verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });

  await loadCandidates(currentReceiptId);
  await loadReceipts();
}

async function attachToTx(txId) {
  if (!currentReceiptId) return;
  await api(`/transactions/${txId}/attach-receipt/${currentReceiptId}`, { method: "POST" });
  alert("Attached!");
  el("modalBack").style.display = "none";
  currentReceiptId = null;
  await loadReceipts();
}

function init() {
  el("uploadBtn").addEventListener("click", uploadReceipt);
  el("refreshBtn").addEventListener("click", loadReceipts);
  el("q").addEventListener("keydown", (e) => { if (e.key === "Enter") loadReceipts(); });

  el("closeModal").addEventListener("click", () => {
    el("modalBack").style.display = "none";
    currentReceiptId = null;
  });

  el("saveVerify").addEventListener("click", saveVerified);
  el("reparseBtn").addEventListener("click", reprocessReceipt);
el("copyOcrDebug").addEventListener("click", async () => {
  if (!lastOcrDebug) return alert("No OCR debug loaded yet.");
  const text = JSON.stringify(lastOcrDebug, null, 2);
  const ok = await copyText(text);
  if (ok) alert("Copied OCR debug JSON.");
  else alert("Copy failed — your browser blocked it. Open DevTools → Network → /ocr_debug and copy response.");
});
  loadReceipts().catch(err => alert(err.message));
}

document.addEventListener("DOMContentLoaded", init);


function formatAddress(a) {
  // Accepts {store_name, street, city, state, zip, website}
  const lines = [];
  const store = (a.store_name || a.name || "").trim();
  if (store) lines.push(store);

  const street = (a.street || a.line1 || "").trim();
  if (street) lines.push(street);

  const city = (a.city || "").trim();
  const state = (a.state || "").trim();
  const zip = (a.zip || a.postal_code || "").toString().trim();
  const csz = [city, state].filter(Boolean).join(", ") + (zip ? (" " + zip) : "");
  if (csz.trim()) lines.push(csz.trim());

  const web = (a.website || a.url || "").trim();
  if (web) lines.push(web);

  return lines.join("\n");
}
