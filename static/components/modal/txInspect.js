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

  function removeAnyVisibleTxRows(txId) {
    const rows = document.querySelectorAll(
      `.tx-row[data-tx-id="${CSS.escape(String(txId))}"]`
    );
    rows.forEach((row) => row.remove());

    window.dispatchEvent(
      new CustomEvent("tx:deleted", { detail: { txId } })
    );
  }

  function updateAnyVisibleTxRowsMeta(txId, nextStatus) {
    const rows = document.querySelectorAll(
      `.tx-row[data-tx-id="${CSS.escape(String(txId))}"]`
    );
    const isPending = String(nextStatus || "").toLowerCase() === "pending";
    rows.forEach((row) => {
      row.classList.toggle("is-pending", isPending);
    });

    window.dispatchEvent(
      new CustomEvent("tx:meta-updated", { detail: { txId, status: nextStatus } })
    );
  }

  function _formatMoney(n) {
    const v = Number(n || 0);
    if (typeof window.money === "function") return window.money(v);
    try {
      return v.toLocaleString(undefined, { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 });
    } catch {
      return String(v);
    }
  }

  function updateAnyVisibleTxRowsAmount(txId, nextAmount) {
    const rows = document.querySelectorAll(
      `.tx-row[data-tx-id="${CSS.escape(String(txId))}"]`
    );
    rows.forEach((row) => {
      const amtEl = row.querySelector(".tx-amt");
      if (amtEl) amtEl.textContent = _formatMoney(nextAmount);
      row.dataset.amount = String(nextAmount);
    });

    window.dispatchEvent(
      new CustomEvent("tx:amount-updated", { detail: { txId, amount: Number(nextAmount || 0) } })
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
      "category","category_rule_id","category_rule_pattern","subcategory",
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
            <div class="tx-inline-edit" style="gap:10px;">
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
              <button
                id="txInspectDelete"
                class="tx-edit-btn"
                type="button"
                style="background:#ff3b30;color:#fff;"
              >Delete</button>
            </div>
            <div id="txInspectCategoryStatus" class="tx-edit-status" aria-live="polite"></div>
          </div>
        `;
      }

      const val = (v === null || v === undefined || v === "") ? "—" : esc(v);
      return `<div class="tx-k">${esc(k)}</div><div class="tx-v">${val}</div>`;
    }).join("");

    const currentStatus = String(obj?.status ?? "").trim();
    const currentPosted = String(obj?.postedDate ?? "").trim();
    grid.innerHTML += `
      <div class="tx-k">edit</div>
      <div class="tx-v">
        <button id="txInspectMetaEditToggle" class="tx-edit-btn" type="button">Edit status/date</button>
        <button id="txInspectInvertAmount" class="tx-edit-btn" type="button" style="margin-left:8px;">Invert amount</button>
        <div id="txInspectMetaEditPanel" style="display:none; margin-top:10px;">
          <div class="tx-inline-edit" style="gap:10px; flex-wrap:wrap;">
            <label style="display:flex; align-items:center; gap:6px;">
              <span>Status</span>
              <select id="txInspectStatusInput" class="tx-edit-input">
                <option value="posted"${currentStatus.toLowerCase() === "posted" ? " selected" : ""}>posted</option>
                <option value="pending"${currentStatus.toLowerCase() === "pending" ? " selected" : ""}>pending</option>
              </select>
            </label>
            <label style="display:flex; align-items:center; gap:6px;">
              <span>Posted Date</span>
              <input
                id="txInspectPostedDateInput"
                class="tx-edit-input"
                type="text"
                inputmode="numeric"
                placeholder="MM/DD/YYYY or unknown"
                value="${esc(currentPosted)}"
              />
            </label>
            <button id="txInspectMetaSave" class="tx-edit-btn" type="button">Save</button>
            <button id="txInspectMetaCancel" class="tx-edit-btn" type="button">Cancel</button>
          </div>
          <div id="txInspectMetaStatus" class="tx-edit-status" aria-live="polite"></div>
        </div>
        <div id="txInspectAmountStatus" class="tx-edit-status" aria-live="polite"></div>
      </div>
    `;

    const btn = document.getElementById("txInspectCategorySave");
    const input = document.getElementById("txInspectCategoryInput");
    const status = document.getElementById("txInspectCategoryStatus");
    const delBtn = document.getElementById("txInspectDelete");
    const metaToggle = document.getElementById("txInspectMetaEditToggle");
    const metaPanel = document.getElementById("txInspectMetaEditPanel");
    const metaSave = document.getElementById("txInspectMetaSave");
    const metaCancel = document.getElementById("txInspectMetaCancel");
    const metaStatus = document.getElementById("txInspectMetaStatus");
    const amountStatus = document.getElementById("txInspectAmountStatus");
    const statusInput = document.getElementById("txInspectStatusInput");
    const postedInput = document.getElementById("txInspectPostedDateInput");
    const invertBtn = document.getElementById("txInspectInvertAmount");

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
    if (metaToggle && metaPanel && statusInput && postedInput) {
      metaToggle.onclick = () => {
        metaPanel.style.display = "block";
        metaToggle.style.display = "none";
      };
      if (metaCancel) {
        metaCancel.onclick = () => {
          statusInput.value = (obj?.status == null ? "" : String(obj.status)).toLowerCase() || "posted";
          postedInput.value = obj?.postedDate == null ? "" : String(obj.postedDate);
          if (metaStatus) metaStatus.textContent = "";
          metaPanel.style.display = "none";
          metaToggle.style.display = "";
        };
      }
      if (metaSave) {
        metaSave.onclick = async () => {
          const nextStatus = String(statusInput.value || "posted").toLowerCase();
          const nextPosted = String(postedInput.value || "").trim();
          metaSave.disabled = true;
          if (metaCancel) metaCancel.disabled = true;
          statusInput.disabled = true;
          postedInput.disabled = true;
          if (metaStatus) metaStatus.textContent = "Saving...";
          try {
            const res = await fetch(`/transaction/${encodeURIComponent(txId)}/meta`, {
              method: "PATCH",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                status: nextStatus,
                postedDate: nextPosted,
              }),
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const out = await res.json();
            obj.status = out?.status ?? nextStatus;
            obj.postedDate = out?.postedDate ?? nextPosted;
            updateAnyVisibleTxRowsMeta(txId, obj.status);
            if (metaStatus) metaStatus.textContent = "Saved";
            renderTxInspect(obj, txId);
          } catch (e) {
            console.error(e);
            if (metaStatus) metaStatus.textContent = "Failed to save";
            metaSave.disabled = false;
            if (metaCancel) metaCancel.disabled = false;
            statusInput.disabled = false;
            postedInput.disabled = false;
          }
        };
      }
    }
    if (invertBtn) {
      invertBtn.onclick = async () => {
        const ok = confirm("Invert this transaction amount?");
        if (!ok) return;
        invertBtn.disabled = true;
        if (amountStatus) amountStatus.textContent = "Saving...";
        try {
          const res = await fetch(`/transaction/${encodeURIComponent(txId)}/invert-amount`, {
            method: "POST",
          });
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          const out = await res.json();
          const nextAmount = Number(out?.amount || 0);
          obj.amount = nextAmount;
          updateAnyVisibleTxRowsAmount(txId, nextAmount);
          if (amountStatus) amountStatus.textContent = "Saved";
          renderTxInspect(obj, txId);
        } catch (e) {
          console.error(e);
          if (amountStatus) amountStatus.textContent = "Failed to invert";
          invertBtn.disabled = false;
        }
      };
    }
    if (delBtn) {
      delBtn.onclick = async () => {
        const ok = confirm("Delete this transaction? This cannot be undone.");
        if (!ok) return;

        delBtn.disabled = true;
        if (status) status.textContent = "Deleting…";

        try {
          const res = await fetch(`/transaction/${encodeURIComponent(txId)}`, {
            method: "DELETE",
          });
          if (!res.ok) throw new Error(`HTTP ${res.status}`);

          removeAnyVisibleTxRows(txId);

          // close modal
          const backdrop = document.getElementById("txInspectBackdrop");
          const modal = document.getElementById("txInspectModal");
          if (backdrop) backdrop.style.display = "none";
          if (modal) modal.style.display = "none";
        } catch (e) {
          console.error(e);
          if (status) status.textContent = "Failed to delete";
          delBtn.disabled = false;
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
