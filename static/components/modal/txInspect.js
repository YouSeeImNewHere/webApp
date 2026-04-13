// static/txInspect.js
(function () {
  let _scrollLockY = 0;
  let _isScrollLocked = false;

  function lockBodyScroll() {
    if (_isScrollLocked) return;
    _scrollLockY = window.scrollY || window.pageYOffset || 0;
    document.documentElement.style.overflow = "hidden";
    document.body.style.overflow = "hidden";
    _isScrollLocked = true;
  }

  function unlockBodyScroll() {
    if (!_isScrollLocked) return;
    document.documentElement.style.overflow = "";
    document.body.style.overflow = "";
    window.scrollTo(0, _scrollLockY || 0);
    _isScrollLocked = false;
  }

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
        <button class="tx-inspect-close" type="button" aria-label="Close">&times;</button>
      </div>
      <div class="tx-inspect-body">
        <div class="tx-inspect-grid" id="txInspectGrid"></div>
        <datalist id="txInspectCategoryOptions"></datalist>
      </div>
    `;

    function close() {
      backdrop.style.display = "none";
      modal.style.display = "none";
      unlockBodyScroll();
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
      try {
        const iconWrap = row.querySelector(".tx-icon-wrap");
        if (iconWrap && typeof window.categoryIconHTML === "function") {
          iconWrap.innerHTML = window.categoryIconHTML(newCategory);
        }
      } catch {}

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
      return v.toLocaleString(undefined, {
        style: "currency",
        currency: "USD",
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      });
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

    const normalizeKey = (k) => String(k || "").toLowerCase().replace(/[^a-z0-9]/g, "");
    const isEmpty = (v) => v == null || String(v).trim() === "";

    const grouped = new Map();
    Object.entries(obj || {}).forEach(([key, value]) => {
      const norm = normalizeKey(key);
      if (!grouped.has(norm)) grouped.set(norm, []);
      grouped.get(norm).push({ key, value });
    });

    const read = (...aliases) => {
      for (const alias of aliases) {
        const arr = grouped.get(normalizeKey(alias));
        if (!arr || !arr.length) continue;
        const nonEmpty = arr.find((x) => !isEmpty(x.value));
        return nonEmpty ? nonEmpty.value : arr[0].value;
      }
      return "";
    };

    const summaryNorms = new Set([
      "merchant", "amount", "status", "time",
      "purchasedate", "posteddate", "bank", "card", "accounttype", "category",
    ]);

    const rawAmount = read("amount");
    const summaryRows = [
      ["merchant", read("merchant")],
      ["amount", rawAmount === "" || rawAmount == null ? "" : _formatMoney(rawAmount)],
      ["status", read("status")],
      ["time", read("time")],
      ["purchase date", read("purchaseDate", "purchasedate")],
      ["posted date", read("postedDate", "posteddate")],
      ["bank", read("bank")],
      ["card", read("card")],
      ["account type", read("accountType", "account_type")],
    ];

    const currentCategory = String(read("category") ?? "");
    const currentStatus = String(read("status") ?? "").trim().toLowerCase() || "posted";
    const currentPosted = String(read("postedDate", "posteddate") ?? "").trim();
    const useCategoryList = !window.matchMedia("(max-width: 900px)").matches;
    const categoryListAttr = useCategoryList ? `list="txInspectCategoryOptions"` : "";

    const extraFields = [];
    grouped.forEach((arr, norm) => {
      if (norm === "tenantid") return;
      if (summaryNorms.has(norm)) return;
      const picked = arr.find((x) => !isEmpty(x.value)) || arr[0];
      if (!picked) return;
      extraFields.push({
        key: picked.key,
        value: picked.value,
      });
    });
    extraFields.sort((a, b) => a.key.localeCompare(b.key));

    const extraHtml = extraFields
      .map(({ key, value }) => {
        const val = (value === null || value === undefined || value === "") ? "—" : esc(value);
        return `<div class="tx-tech-k">${esc(key)}</div><div class="tx-tech-v">${val}</div>`;
      })
      .join("");

    grid.innerHTML = `
      ${summaryRows
        .map(([k, v]) => {
          const val = (v === null || v === undefined || v === "") ? "—" : esc(v);
          return `<div class="tx-k">${esc(k)}</div><div class="tx-v">${val}</div>`;
        })
        .join("")}

      <div class="tx-k">category</div>
      <div class="tx-v">
        <div class="tx-inline-edit tx-inline-edit--category">
          <input
            id="txInspectCategoryInput"
            class="tx-edit-input"
            type="text"
            ${categoryListAttr}
            placeholder="Set category"
            value="${esc(currentCategory)}"
            autocomplete="off"
          />
          <button id="txInspectCategorySave" class="tx-edit-btn" type="button">Save</button>
        </div>
        <div id="txInspectCategoryStatus" class="tx-edit-status" aria-live="polite"></div>
      </div>

      <div class="tx-k">edit</div>
      <div class="tx-v">
        <div class="tx-inline-edit tx-inline-edit--toolbar tx-inline-edit--toolbar-fixed">
          <button id="txInspectMetaEditToggle" class="tx-edit-btn" type="button">Edit status/date</button>
          <button id="txInspectInvertAmount" class="tx-edit-btn" type="button">Invert amount</button>
          <button id="txInspectDelete" class="tx-edit-btn tx-edit-btn--danger" type="button">Delete</button>
        </div>
        <div id="txInspectDeleteStatus" class="tx-edit-status tx-edit-status--danger" aria-live="polite"></div>

        <div id="txInspectMetaEditPanel" class="tx-edit-panel" style="display:none;">
          <div class="tx-inline-edit tx-inline-edit--meta">
            <label class="tx-inline-field">
              <span>Status</span>
              <select id="txInspectStatusInput" class="tx-edit-input">
                <option value="posted"${currentStatus === "posted" ? " selected" : ""}>posted</option>
                <option value="pending"${currentStatus === "pending" ? " selected" : ""}>pending</option>
              </select>
            </label>
            <label class="tx-inline-field">
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
          </div>
          <div class="tx-inline-edit tx-inline-edit--toolbar">
            <button id="txInspectMetaSave" class="tx-edit-btn" type="button">Save</button>
            <button id="txInspectMetaCancel" class="tx-edit-btn tx-edit-btn--quiet" type="button">Cancel</button>
          </div>
          <div id="txInspectMetaStatus" class="tx-edit-status" aria-live="polite"></div>
        </div>
        <div id="txInspectAmountStatus" class="tx-edit-status" aria-live="polite"></div>
      </div>

      <div class="tx-k">details</div>
      <div class="tx-v">
        <section class="tx-tech-details">
          <div class="tx-tech-grid">
            ${extraHtml || `<div class="tx-tech-v">No additional fields.</div>`}
          </div>
        </section>
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
    const deleteStatus = document.getElementById("txInspectDeleteStatus");
    const amountStatus = document.getElementById("txInspectAmountStatus");
    const statusInput = document.getElementById("txInspectStatusInput");
    const postedInput = document.getElementById("txInspectPostedDateInput");
    const invertBtn = document.getElementById("txInspectInvertAmount");

    if (btn && input) {
      btn.onclick = async () => {
        const next = (input.value || "").trim();
        btn.disabled = true;
        input.disabled = true;
        if (status) status.textContent = "Saving...";

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
        const opening = metaPanel.style.display !== "block";
        metaPanel.style.display = opening ? "block" : "none";
        metaToggle.textContent = opening ? "Close edit" : "Edit status/date";
      };

      if (metaCancel) {
        metaCancel.onclick = () => {
          statusInput.value = (obj?.status == null ? "" : String(obj.status)).toLowerCase() || "posted";
          postedInput.value = obj?.postedDate == null ? "" : String(obj.postedDate);
          if (metaStatus) metaStatus.textContent = "";
          if (deleteStatus) deleteStatus.textContent = "";
          metaPanel.style.display = "none";
          metaToggle.textContent = "Edit status/date";
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
        if (deleteStatus) deleteStatus.textContent = "Deleting...";

        try {
          const res = await fetch(`/transaction/${encodeURIComponent(txId)}`, {
            method: "DELETE",
          });
          if (!res.ok) throw new Error(`HTTP ${res.status}`);

          removeAnyVisibleTxRows(txId);

          const backdrop = document.getElementById("txInspectBackdrop");
          const modal = document.getElementById("txInspectModal");
          if (backdrop) backdrop.style.display = "none";
          if (modal) modal.style.display = "none";
        } catch (e) {
          console.error(e);
          if (deleteStatus) deleteStatus.textContent = "Failed to delete";
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
    modal.style.display = "flex";
    lockBodyScroll();
    grid.innerHTML = `<div class="tx-inspect-loading">Loading...</div>`;

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

      try {
        await openTxInspect(txId);
      } catch (err) {
        console.error(err);
      }
    });
  }

  window.attachTxInspect = attachTxInspect;
})();
