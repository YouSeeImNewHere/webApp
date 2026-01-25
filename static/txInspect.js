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
        <datalist id="txInspectCategoryOptions"></datalist>
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

  let _cachedCategories = null;
  async function getCategories() {
    if (Array.isArray(_cachedCategories)) return _cachedCategories;
    try {
      const res = await fetch("/categories");
      if (!res.ok) return [];
      const cats = await res.json();
      _cachedCategories = Array.isArray(cats) ? cats : [];
      return _cachedCategories;
    } catch {
      return [];
    }
  }

  function ensureCategoryDatalist(categories) {
    const dl = document.getElementById("txInspectCategoryOptions");
    if (!dl) return;
    dl.innerHTML = "";
    (categories || []).forEach((c) => {
      const opt = document.createElement("option");
      opt.value = String(c);
      dl.appendChild(opt);
    });
  }

  function updateAnyVisibleTxRows(txId, newCategory) {
    const rows = document.querySelectorAll(
      `.tx-row[data-tx-id="${CSS.escape(String(txId))}"]`
    );

    rows.forEach((row) => {
      // icon
      try {
        const iconWrap = row.querySelector(".tx-icon-wrap");
        if (iconWrap && typeof window.categoryIconHTML === "function") {
          iconWrap.innerHTML = window.categoryIconHTML(newCategory);
        }
      } catch {}

      // category label (usually last .tx-sub)
      const subs = row.querySelectorAll(".tx-sub");
      if (subs && subs.length) {
        const catEl = subs[subs.length - 1];
        const prev = (catEl.textContent || "").trim();
        let tail = "";
        const parts = prev.split(" • ");
        if (parts.length > 1) tail = " • " + parts.slice(1).join(" • ");
        catEl.textContent = `${(newCategory || "").trim()}${tail}`.trim();
      }

      row.dataset.category = (newCategory || "").trim();
    });

    window.dispatchEvent(
      new CustomEvent("tx:category-updated", { detail: { txId, category: newCategory } })
    );
  }

  function renderTxInspect(obj, txId) {
    const grid = document.getElementById("txInspectGrid");
    if (!grid) return;

    const preferred = [
      "id","status",
      "purchaseDate","postedDate","dateISO","time",
      "merchant","amount",
      "bank","card","accountType","account_id",
      "category","subcategory",
      "where","source",
      "transfer_peer",
      "notes"
    ];

    const keys = new Set(Object.keys(obj || {}));
    const ordered = [];
    preferred.forEach(k => { if (keys.has(k)) { ordered.push(k); keys.delete(k); } });
    [...keys].sort().forEach(k => ordered.push(k));

    grid.innerHTML = ordered.map((k) => {
      const v = obj[k];

      if (k === "category") {
        const cur = (v ?? "");
        return `
          <div class="tx-k">${esc(k)}</div>
          <div class="tx-v">
            <div class="tx-inline-edit">
              <input
                id="txInspectCategoryInput"
                class="tx-edit-input"
                type="text"
                list="txInspectCategoryOptions"
                placeholder="Set category"
                value="${esc(cur)}"
                autocomplete="off"
              />
              <button id="txInspectCategorySave" class="tx-edit-btn" type="button">Save</button>
            </div>
            <div id="txInspectCategoryStatus" class="tx-edit-status" aria-live="polite"></div>
          </div>
        `;
      }

      const val = (v === null || v === undefined || v === "") ? "—" : esc(v);
      return `<div class="tx-k">${esc(k)}</div><div class="tx-v">${val}</div>`;
    }).join("");

    const btn = document.getElementById("txInspectCategorySave");
    const input = document.getElementById("txInspectCategoryInput");
    const status = document.getElementById("txInspectCategoryStatus");

    if (btn && input) {
      btn.onclick = async () => {
        const next = (input.value || "").trim();
        btn.disabled = true;
        input.disabled = true;
        if (status) status.textContent = "Saving…";

        try {
          const res = await fetch(`/transaction/${encodeURIComponent(txId)}/category`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ category: next }),
          });
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          const out = await res.json();
          const saved = (out && out.category != null) ? String(out.category) : next;

          updateAnyVisibleTxRows(txId, saved);
          if (status) status.textContent = "Saved";
        } catch (e) {
          console.error(e);
          if (status) status.textContent = "Failed to save";
        } finally {
          btn.disabled = false;
          input.disabled = false;
        }
      };
    }
  }

  async function openTxInspect(txId) {
    ensureTxInspectModal();

    const backdrop = document.getElementById("txInspectBackdrop");
    const modal = document.getElementById("txInspectModal");
    const grid = document.getElementById("txInspectGrid");

    backdrop.style.display = "block";
    modal.style.display = "block";
    grid.innerHTML = `<div class="tx-inspect-loading">Loading…</div>`;

    const [cats, res] = await Promise.all([
      getCategories(),
      fetch(`/transaction/${encodeURIComponent(txId)}`),
    ]);

    ensureCategoryDatalist(cats);

    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const tx = (data && data.transaction) ? data.transaction : data;

    renderTxInspect(tx, txId);
  }

  function attachTxInspect(container) {
    if (!container || container.__txInspectBound) return;
    container.__txInspectBound = true;

    container.addEventListener("click", async (e) => {
      const hit = e.target.closest(".tx-icon-hit");
      if (!hit || !container.contains(hit)) return;

      const row = hit.closest(".tx-row");
      const txId = row?.dataset?.txId;
      if (!txId) return;

      try { await openTxInspect(txId); } catch (err) { console.error(err); }
    });
  }

  window.attachTxInspect = attachTxInspect;
})();
