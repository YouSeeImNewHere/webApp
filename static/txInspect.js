// static/txInspect.js
(function () {
  function esc(s) {
    return String(s ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function ensureTxInspectModal() {
    if (document.getElementById("txInspectBackdrop")) return;

    const backdrop = document.createElement("div");
    backdrop.id = "txInspectBackdrop";
    backdrop.className = "tx-inspect-backdrop";
    backdrop.style.display = "none";

    const modal = document.createElement("div");
    modal.id = "txInspectModal";
    modal.className = "tx-inspect-modal";
    modal.style.display = "none";

    modal.innerHTML = `
      <div class="tx-inspect-header">
        <div class="tx-inspect-title">Transaction</div>
        <button class="tx-inspect-close" type="button" aria-label="Close">✕</button>
      </div>
      <div class="tx-inspect-body">
        <div class="tx-inspect-grid" id="txInspectGrid"></div>
      </div>
    `;

    function close() {
      backdrop.style.display = "none";
      modal.style.display = "none";
    }

    backdrop.addEventListener("click", close);
    modal.querySelector(".tx-inspect-close").addEventListener("click", close);
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") close();
    });

    document.body.appendChild(backdrop);
    document.body.appendChild(modal);
  }

  function renderTxInspect(obj) {
    const grid = document.getElementById("txInspectGrid");
    if (!grid) return;

    // Order keys nicely (fallback shows any extra keys at end)
    const preferred = [
      "id", "status",
      "purchaseDate", "postedDate", "dateISO", "time",
      "merchant", "amount",
      "bank", "card", "accountType", "account_id",
      "category", "subcategory",
      "where", "source",
      "transfer_peer",
      "notes"
    ];

    const keys = new Set(Object.keys(obj || {}));
    const ordered = [];
    preferred.forEach(k => { if (keys.has(k)) { ordered.push(k); keys.delete(k); } });
    [...keys].sort().forEach(k => ordered.push(k));

    grid.innerHTML = ordered.map(k => {
      const v = obj[k];
      const val = (v === null || v === undefined || v === "") ? "—" : esc(v);
      return `<div class="tx-k">${esc(k)}</div><div class="tx-v">${val}</div>`;
    }).join("");
  }

  async function openTxInspect(txId) {
    ensureTxInspectModal();

    const backdrop = document.getElementById("txInspectBackdrop");
    const modal = document.getElementById("txInspectModal");
    const grid = document.getElementById("txInspectGrid");

    backdrop.style.display = "block";
    modal.style.display = "block";
    grid.innerHTML = `<div class="tx-inspect-loading">Loading…</div>`;

    // ✅ Your API should be /transaction/{tx_id} (path param), not query params.
    const res = await fetch(`/transaction/${encodeURIComponent(txId)}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const data = await res.json();
    renderTxInspect(data);
  }

  // Event delegation: call this once per list container
  function attachTxInspect(container) {
    if (!container || container.__txInspectBound) return;
    container.__txInspectBound = true;

    container.addEventListener("click", async (e) => {
      const hit = e.target.closest(".tx-icon-hit");
      if (!hit || !container.contains(hit)) return;

      const row = hit.closest(".tx-row");
      const txId = row?.dataset?.txId;
      if (!txId) return;

      try {
        await openTxInspect(txId);
      } catch (err) {
        console.error("openTxInspect failed:", err);
      }
    });

    // keyboard support (Enter/Space) on focused icon
    container.addEventListener("keydown", async (e) => {
      if (e.key !== "Enter" && e.key !== " ") return;
      const hit = e.target.closest(".tx-icon-hit");
      if (!hit || !container.contains(hit)) return;

      e.preventDefault();
      const row = hit.closest(".tx-row");
      const txId = row?.dataset?.txId;
      if (!txId) return;

      try {
        await openTxInspect(txId);
      } catch (err) {
        console.error("openTxInspect failed:", err);
      }
    });
  }

  // expose globally so page scripts can call attachTxInspect(...)
  window.attachTxInspect = attachTxInspect;
})();
