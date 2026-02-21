(function () {
  async function api(path, opts) {
    const res = await fetch(path, Object.assign({ headers: { "Content-Type": "application/json" } }, opts || {}));
    const text = await res.text();
    let body = null;
    try { body = text ? JSON.parse(text) : {}; } catch (_e) { body = { raw: text }; }
    if (!res.ok) throw new Error((body && (body.detail || body.error)) || `${res.status}`);
    return body;
  }

  async function apiGetJson(path) {
    const res = await fetch(path, { cache: "no-store" });
    const text = await res.text();
    let body = null;
    try { body = text ? JSON.parse(text) : {}; } catch (_e) { body = { raw: text }; }
    if (!res.ok) throw new Error((body && (body.detail || body.error)) || `${res.status}`);
    return body;
  }

  async function apiPostForm(path, formData) {
    const res = await fetch(path, { method: "POST", body: formData });
    const text = await res.text();
    let body = null;
    try { body = text ? JSON.parse(text) : {}; } catch (_e) { body = { raw: text }; }
    if (!res.ok) throw new Error((body && (body.detail || body.error)) || `${res.status}`);
    return body;
  }

  const statusEl = document.getElementById("status");
  const addResultEl = document.getElementById("addResult");
  const pushoverResultEl = document.getElementById("pushoverResult");
  const accountsListEl = document.getElementById("accountsList");
  const accountsCountChipEl = document.getElementById("accountsCountChip");
  const addAccountBtnEl = document.getElementById("addAccountBtn");
  const cancelEditBtnEl = document.getElementById("cancelEditBtn");

  let editingAccountId = null;
  let latestAccounts = [];
  let canSetStartingBalance = false;
  let csvPreferredAccountId = 0;
  let csvMappingSaved = false;
  const CSV_MODAL_STATE = {
    file: null,
    columns: [],
    previewRows: [],
    accounts: [],
    selectedAccountId: 0,
    activePreset: null,
    activePresetAccountId: 0,
  };
  const CSV_ACCOUNT_PRESET_KEY = "__account__";
  const CSV_MAPPING_FIELD_LABELS = {
    csvMapPurchase: "Transaction date",
    csvMapPosted: "Posted date",
    csvMapAmount: "Amount",
    csvMapDebit: "Debit amount",
    csvMapCredit: "Credit amount",
    csvMapMerchant: "Merchant",
    csvMapIndicator: "Credit/Debit indicator",
  };
  let CSV_IMPORT_PROGRESS_TIMER = null;
  let CSV_IMPORT_PROGRESS_PCT = 0;

  function pill(ok, label) {
    const cls = ok ? "ok" : "todo";
    const txt = ok ? "Done" : "Pending";
    return `<span class="setup-pill ${cls}">${txt}</span>${label}`;
  }

  function csvEscapeHtml(v) {
    return String(v == null ? "" : v)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function csvMoney(n) {
    const v = Number(n || 0);
    return v.toLocaleString(undefined, { style: "currency", currency: "USD" });
  }

  function updateAccountFieldHints() {
    const accountType = (document.getElementById("accounttype").value || "").trim().toLowerCase();
    const creditEl = document.getElementById("creditLimit");
    const apyEl = document.getElementById("apyPercent");
    const creditLimitRow = document.getElementById("creditLimitRow");
    const apyRow = document.getElementById("apyRow");
    const benefitsWrap = document.getElementById("creditBenefitsWrap");
    const addBenefitBtn = document.getElementById("addBenefitBtn");
    const benefitInputs = document.querySelectorAll(".benefit-input");
    const creditMode = accountType === "credit";
    const apyMode = accountType === "checking" || accountType === "savings" || accountType === "investment";

    if (creditLimitRow) creditLimitRow.style.display = creditMode ? "" : "none";
    if (apyRow) apyRow.style.display = apyMode ? "" : "none";
    if (benefitsWrap) benefitsWrap.style.display = creditMode ? "" : "none";

    if (creditEl) {
      creditEl.disabled = !creditMode;
      if (!creditMode) creditEl.value = "";
    }
    if (apyEl) {
      apyEl.disabled = !apyMode;
      if (!apyMode) apyEl.value = "";
    }
    if (addBenefitBtn) addBenefitBtn.disabled = !creditMode;
    benefitInputs.forEach((el) => {
      el.disabled = !creditMode;
      if (!creditMode) el.value = "";
    });
  }

  function resetAccountForm() {
    document.getElementById("institution").value = "";
    document.getElementById("name").value = "";
    document.getElementById("accounttype").value = "checking";
    document.getElementById("startingBalance").value = "";
    document.getElementById("startingDate").value = "";
    document.getElementById("creditLimit").value = "";
    document.getElementById("apyPercent").value = "";
    document.getElementById("interestPostDay").value = "";
    document.getElementById("receivesEmails").checked = true;
    document.getElementById("isPaycheckAccount").checked = false;
    document.getElementById("benefitRows").innerHTML = "";
    addBenefitRow("", "");
    updateAccountFieldHints();
    applyStartingBalanceVisibility();
  }

  function setEditMode(on, account) {
    editingAccountId = on && account ? Number(account.id) : null;
    if (addAccountBtnEl) addAccountBtnEl.textContent = editingAccountId ? "Save Account Changes" : "Add Account";
    if (cancelEditBtnEl) cancelEditBtnEl.style.display = editingAccountId ? "" : "none";
  }

  function startEditAccount(accountId) {
    const a = (latestAccounts || []).find((x) => Number(x.id) === Number(accountId));
    if (!a) return;
    document.getElementById("institution").value = String(a.institution || "");
    document.getElementById("name").value = String(a.name || "");
    document.getElementById("accounttype").value = String(a.accounttype || "checking").toLowerCase();
    document.getElementById("creditLimit").value = (a.credit_limit ?? "") === null ? "" : String(a.credit_limit ?? "");
    document.getElementById("interestPostDay").value = (a.interest_post_day ?? "") === null ? "" : String(a.interest_post_day ?? "");
    document.getElementById("receivesEmails").checked = !!a.receives_emails;
    document.getElementById("isPaycheckAccount").checked = !!a.is_paycheck_account;
    // Keep Step 2 import target in sync with the account selected in Step 1.
    csvPreferredAccountId = Number(a.id || 0);
    CSV_MODAL_STATE.selectedAccountId = Number(a.id || 0);
    syncCsvSelectedAccount();
    loadCsvPreset(Number(a.id || 0)).catch(console.error);
    setEditMode(true, a);
    updateAccountFieldHints();
    addResultEl.textContent = `Editing account #${a.id}.`;
  }

  function renderAccountsList() {
    if (!accountsListEl) return;
    if (accountsCountChipEl) accountsCountChipEl.textContent = String(latestAccounts.length || 0);
    if (!latestAccounts.length) {
      accountsListEl.innerHTML = `<div class="setup-muted">No accounts yet.</div>`;
      return;
    }
    accountsListEl.innerHTML = `
      <div class="setup-list">
        ${latestAccounts.map((a) => `
          <div class="setup-list-row">
            <div>
              <div>
                <strong>${String(a.institution || "")} - ${String(a.name || "")}</strong>
                <span class="setup-list-meta">(${String(a.accounttype || "").toLowerCase()})</span>
              </div>
              <div class="setup-list-meta" style="margin-top:4px;">
                ${(() => {
                  const setup = a && typeof a.setup === "object" ? a.setup : null;
                  const complete = !!(setup && setup.complete);
                  const missing = Array.isArray(setup?.missing) ? setup.missing : [];
                  if (complete) return `<span class="setup-pill ok">Complete</span>`;
                  const missingTxt = missing.length ? `Missing: ${missing.join(", ")}` : "Missing setup";
                  return `<span class="setup-pill todo">Pending</span>${csvEscapeHtml(missingTxt)}`;
                })()}
              </div>
              <div class="setup-list-meta">
                Receives emails: ${a.receives_emails ? "Yes" : "No"} | Paycheck account: ${a.is_paycheck_account ? "Yes" : "No"}
              </div>
            </div>
            <div class="setup-list-actions">
              <button type="button" class="secondary setup-edit-account" data-account-id="${Number(a.id)}">Edit</button>
            </div>
          </div>
        `).join("")}
      </div>
    `;
    accountsListEl.querySelectorAll(".setup-edit-account").forEach((btn) => {
      btn.addEventListener("click", () => startEditAccount(Number(btn.getAttribute("data-account-id") || 0)));
    });
  }

  function applyStartingBalanceVisibility() {
    const row = document.getElementById("startingBalanceWrap");
    const input = document.getElementById("startingBalance");
    if (!row || !input) return;
    row.style.display = canSetStartingBalance ? "" : "none";
    input.disabled = !canSetStartingBalance;
    if (!canSetStartingBalance) input.value = "";
  }

  function addBenefitRow(initialCategory, initialPercent) {
    const host = document.getElementById("benefitRows");
    if (!host) return;
    const row = document.createElement("div");
    row.className = "setup-row3 benefit-row";
    row.innerHTML = `
      <input class="benefit-input benefit-category" placeholder="Category (e.g. Groceries)" value="${initialCategory || ""}" />
      <input class="benefit-input benefit-percent" type="number" step="0.01" min="0" max="100" placeholder="Cashback % (e.g. 3)" value="${initialPercent || ""}" />
      <button type="button" class="secondary benefit-remove">Remove</button>
    `;
    host.appendChild(row);
    const removeBtn = row.querySelector(".benefit-remove");
    if (removeBtn) {
      removeBtn.addEventListener("click", () => {
        row.remove();
      });
    }
    updateAccountFieldHints();
  }

  function csvSelectHasOption(id, val) {
    const el = document.getElementById(id);
    if (!el) return false;
    const sval = String(val);
    return Array.from(el.options || []).some((o) => String(o.value) === sval);
  }

  function ensureCsvMappingOption(id, val) {
    const el = document.getElementById(id);
    if (!el || val === null || val === undefined) return;
    if (csvSelectHasOption(id, val)) return;
    const n = Number(val);
    const colLabel = Number.isInteger(n) && n >= 0 ? `column ${n + 1}` : `value ${String(val)}`;
    const friendly = CSV_MAPPING_FIELD_LABELS[id] || "Saved mapping";
    const opt = document.createElement("option");
    opt.value = String(val);
    opt.textContent = `${friendly}: ${colLabel} (saved)`;
    el.appendChild(opt);
  }

  function csvGetSelectInt(id) {
    const el = document.getElementById(id);
    if (!el) return null;
    const v = String(el.value || "").trim();
    if (!v || v === "-1") return null;
    const n = Number(v);
    return Number.isInteger(n) ? n : null;
  }

  function guessCsvColumn(columns, candidates) {
    const terms = candidates.map((s) => s.toLowerCase());
    for (const c of columns) {
      const label = String(c.label || "").toLowerCase();
      if (terms.some((t) => label.includes(t))) return c.index;
    }
    return null;
  }

  function csvLooksLikeDate(v) {
    const s = String(v || "").trim();
    if (!s) return false;
    if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return true;
    if (/^\d{1,2}\/\d{1,2}\/\d{2,4}$/.test(s)) return true;
    if (/^\d{1,2}-\d{1,2}-\d{2,4}$/.test(s)) return true;
    return false;
  }

  function csvParseNumberLike(v) {
    const s0 = String(v || "").trim();
    if (!s0) return null;
    const negParen = s0.startsWith("(") && s0.endsWith(")");
    let s = negParen ? s0.slice(1, -1) : s0;
    s = s.replaceAll("$", "").replaceAll(",", "").trim();
    if (s.endsWith("-")) s = `-${s.slice(0, -1).trim()}`;
    const n = Number(s);
    return Number.isFinite(n) ? n : null;
  }

  function guessCsvColumnsByValues(columns, previewRows) {
    const cols = Array.isArray(columns) ? columns : [];
    const rows = Array.isArray(previewRows) ? previewRows : [];
    if (!cols.length || !rows.length) return {};

    const scores = cols.map(() => ({ date: 0, amount: 0, text: 0 }));
    for (const r of rows) {
      const cells = Array.isArray(r?.cells) ? r.cells : [];
      for (let i = 0; i < cols.length; i += 1) {
        const raw = String(cells[i] ?? "").trim();
        if (!raw) continue;
        if (csvLooksLikeDate(raw)) scores[i].date += 1;
        const num = csvParseNumberLike(raw);
        if (num !== null) scores[i].amount += 1;
        if (num === null && !csvLooksLikeDate(raw)) scores[i].text += 1;
      }
    }

    function pickBest(kind, blocked = new Set()) {
      let bestIdx = null;
      let bestScore = -1;
      for (let i = 0; i < scores.length; i += 1) {
        if (blocked.has(i)) continue;
        const s = Number(scores[i][kind] || 0);
        if (s > bestScore) {
          bestScore = s;
          bestIdx = i;
        }
      }
      if (bestIdx === null || bestScore <= 0) return null;
      return bestIdx;
    }

    const used = new Set();
    const purchase = pickBest("date", used);
    if (purchase !== null) used.add(purchase);
    const amount = pickBest("amount", used);
    if (amount !== null) used.add(amount);
    const merchant = pickBest("text", used);

    return { csvMapPurchase: purchase, csvMapAmount: amount, csvMapMerchant: merchant };
  }

  function csvHasHeaderEnabled() {
    return !!document.getElementById("csvHasHeader")?.checked;
  }

  function updateCsvHeaderModeUi() {
    const hasHeader = csvHasHeaderEnabled();
    const headerEl = document.getElementById("csvHeaderRow");
    const dataEl = document.getElementById("csvDataStartRow");
    if (headerEl) {
      if (!hasHeader) headerEl.value = "1";
      headerEl.disabled = !hasHeader;
    }
    if (dataEl) {
      if (!hasHeader) {
        dataEl.value = "1";
      } else if (Number(dataEl.value || 0) < 2) {
        dataEl.value = "2";
      }
    }
  }

  function populateCsvMappingSelects(columns) {
    const ids = ["csvMapPurchase", "csvMapPosted", "csvMapAmount", "csvMapDebit", "csvMapCredit", "csvMapMerchant", "csvMapIndicator"];
    const opts = ['<option value="-1">Not mapped</option>']
      .concat((columns || []).map((c) => `<option value="${c.index}">${csvEscapeHtml(c.label)} (col ${c.index + 1})</option>`))
      .join("");
    ids.forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.innerHTML = opts;
    });
    const guesses = {
      csvMapPurchase: ["transaction date", "trans date", "date"],
      csvMapPosted: ["posted date", "post date", "posting date"],
      csvMapAmount: ["amount", "transaction amount"],
      csvMapDebit: ["debit", "withdrawal", "charge"],
      csvMapCredit: ["credit", "payment", "deposit", "refund"],
      csvMapMerchant: ["description", "merchant", "payee", "transaction description"],
      csvMapIndicator: ["credit/debit", "credit debit", "indicator", "type"],
    };
    Object.entries(guesses).forEach(([id, terms]) => {
      const guess = guessCsvColumn(columns || [], terms);
      const el = document.getElementById(id);
      if (el && guess !== null) el.value = String(guess);
    });
    if (!csvHasHeaderEnabled()) {
      const byValues = guessCsvColumnsByValues(columns || [], CSV_MODAL_STATE.previewRows || []);
      Object.entries(byValues).forEach(([id, idx]) => {
        const el = document.getElementById(id);
        if (el && idx !== null && idx !== undefined) el.value = String(idx);
      });
    }
    const debitGuess = csvGetSelectInt("csvMapDebit");
    const creditGuess = csvGetSelectInt("csvMapCredit");
    const amountEl = document.getElementById("csvMapAmount");
    if (amountEl && debitGuess !== null && creditGuess !== null) {
      amountEl.value = "-1";
    }
    updateCsvAmountModeUi();
  }

  function renderCsvPreview(previewRows, columns) {
    const wrap = document.getElementById("csvPreviewWrap");
    if (!wrap) return;
    if (!columns?.length || !previewRows?.length) {
      wrap.innerHTML = `<div style="opacity:.65; padding:6px;">No rows to preview.</div>`;
      return;
    }
    const head = columns.map((c) => `<th style="text-align:left; border-bottom:1px solid rgba(0,0,0,.15); padding:4px 6px;">${csvEscapeHtml(c.label)}</th>`).join("");
    const body = previewRows.map((r) => {
      const cells = columns.map((c, i) => `<td style="padding:4px 6px; border-bottom:1px solid rgba(0,0,0,.06);">${csvEscapeHtml((r.cells && r.cells[i]) || "")}</td>`).join("");
      return `<tr>${cells}</tr>`;
    }).join("");
    wrap.innerHTML = `<table style="width:100%; border-collapse:collapse; font-size:12px;"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
  }

  function updateCsvIndicatorTypesHint() {
    const hintEl = document.getElementById("csvIndicatorTypesHint");
    if (!hintEl) return;
    const indicatorInput = document.getElementById("csvMapIndicator");
    if (indicatorInput && indicatorInput.disabled) {
      hintEl.style.display = "none";
      hintEl.textContent = "";
      return;
    }
    const indicatorCol = csvGetSelectInt("csvMapIndicator");
    if (indicatorCol === null) {
      hintEl.style.display = "none";
      hintEl.textContent = "";
      return;
    }

    const rows = Array.isArray(CSV_MODAL_STATE.previewRows) ? CSV_MODAL_STATE.previewRows : [];
    const uniq = new Set();
    rows.forEach((r) => {
      const cells = Array.isArray(r?.cells) ? r.cells : [];
      const raw = String(cells[indicatorCol] ?? "").trim();
      if (raw) uniq.add(raw);
    });
    const vals = Array.from(uniq.values());
    if (!vals.length) {
      hintEl.style.display = "";
      hintEl.textContent = "No indicator values found in current preview rows.";
      return;
    }
    hintEl.style.display = "";
    hintEl.textContent = `Detected indicator values: ${vals.join(", ")}`;
  }

  function selectedCsvAccountMeta() {
    const accountId = Number(CSV_MODAL_STATE.selectedAccountId || 0);
    const meta = (CSV_MODAL_STATE.accounts || []).find((a) => Number(a.id) === accountId);
    return { accountId, meta };
  }

  function syncCsvSelectedAccount() {
    const summaryEl = document.getElementById("csvAccountSummary");
    const rows = Array.isArray(latestAccounts) ? latestAccounts : [];
    CSV_MODAL_STATE.accounts = rows.map((a) => ({
      id: Number(a.id),
      label: `${String(a.institution || "")} - ${String(a.name || "")}`,
    }));

    if (!CSV_MODAL_STATE.accounts.length) {
      CSV_MODAL_STATE.selectedAccountId = 0;
      if (summaryEl) summaryEl.textContent = "Using account: none (add one in Step 1)";
      return;
    }

    const validIds = new Set(CSV_MODAL_STATE.accounts.map((a) => Number(a.id)));
    const preferred = Number(csvPreferredAccountId || 0);
    const current = Number(CSV_MODAL_STATE.selectedAccountId || 0);
    if (preferred && validIds.has(preferred)) {
      CSV_MODAL_STATE.selectedAccountId = preferred;
    } else if (current && validIds.has(current)) {
      CSV_MODAL_STATE.selectedAccountId = current;
    } else {
      CSV_MODAL_STATE.selectedAccountId = Number(CSV_MODAL_STATE.accounts[0].id || 0);
    }

    const selected = CSV_MODAL_STATE.accounts.find((a) => Number(a.id) === Number(CSV_MODAL_STATE.selectedAccountId));
    if (summaryEl) summaryEl.textContent = selected ? `Using account: ${selected.label}` : "Using account: none";
  }

  function buildCsvPresetPayload() {
    return {
      delimiter: document.getElementById("csvDelimiter")?.value || "auto",
      has_header: csvHasHeaderEnabled(),
      header_row: Math.max(1, Number(document.getElementById("csvHeaderRow")?.value || 1)),
      data_start_row: Math.max(1, Number(document.getElementById("csvDataStartRow")?.value || 2)),
      purchase_col: csvGetSelectInt("csvMapPurchase"),
      posted_col: csvGetSelectInt("csvMapPosted"),
      amount_col: csvGetSelectInt("csvMapAmount"),
      debit_col: csvGetSelectInt("csvMapDebit"),
      credit_col: csvGetSelectInt("csvMapCredit"),
      merchant_col: csvGetSelectInt("csvMapMerchant"),
      indicator_col: csvGetSelectInt("csvMapIndicator"),
      credit_indicator_value: String(document.getElementById("csvCreditIndicatorValue")?.value || "credit"),
      invert_amount: !!document.getElementById("csvInvertAmount")?.checked,
    };
  }

  function applyCsvPreset(preset) {
    if (!preset || typeof preset !== "object") return;
    CSV_MODAL_STATE.activePreset = preset;
    const setIf = (id, val) => {
      const el = document.getElementById(id);
      if (!el || val === null || val === undefined) return;
      if (id in CSV_MAPPING_FIELD_LABELS) ensureCsvMappingOption(id, val);
      el.value = String(val);
    };
    setIf("csvDelimiter", preset.delimiter);
    const hasHeaderEl = document.getElementById("csvHasHeader");
    if (hasHeaderEl && typeof preset.has_header === "boolean") hasHeaderEl.checked = !!preset.has_header;
    updateCsvHeaderModeUi();
    setIf("csvHeaderRow", preset.header_row);
    setIf("csvDataStartRow", preset.data_start_row);
    setIf("csvMapPurchase", preset.purchase_col);
    setIf("csvMapPosted", preset.posted_col);
    setIf("csvMapAmount", preset.amount_col);
    setIf("csvMapDebit", preset.debit_col);
    setIf("csvMapCredit", preset.credit_col);
    setIf("csvMapMerchant", preset.merchant_col);
    setIf("csvMapIndicator", preset.indicator_col);
    setIf("csvCreditIndicatorValue", preset.credit_indicator_value);
    const invert = document.getElementById("csvInvertAmount");
    if (invert && typeof preset.invert_amount === "boolean") invert.checked = preset.invert_amount;
    updateCsvAmountModeUi();
    updateCsvIndicatorTypesHint();
  }

  async function loadCsvPreset(preferredAccountId = null) {
    const sub = document.getElementById("csvUploadSub");
    const accountId = Number(preferredAccountId || CSV_MODAL_STATE.selectedAccountId || 0);
    if (!accountId) {
      CSV_MODAL_STATE.activePreset = null;
      CSV_MODAL_STATE.activePresetAccountId = 0;
      return false;
    }
    try {
      const q = `/csv/mapping-presets?account_id=${encodeURIComponent(accountId)}&institution_key=${encodeURIComponent(CSV_ACCOUNT_PRESET_KEY)}`;
      const out = await apiGetJson(q);
      if (out?.ok && out?.found && out?.preset) {
        applyCsvPreset(out.preset);
        CSV_MODAL_STATE.activePresetAccountId = accountId;
        if (sub) sub.textContent = "Saved mapping loaded for selected account.";
        return true;
      }
    } catch (e) {
      console.error(e);
    }
    CSV_MODAL_STATE.activePreset = null;
    CSV_MODAL_STATE.activePresetAccountId = 0;
    return false;
  }

  async function saveCsvPreset() {
    const sub = document.getElementById("csvUploadSub");
    const { accountId } = selectedCsvAccountMeta();
    if (!accountId) {
      if (sub) sub.textContent = "Choose account before saving mapping.";
      return;
    }
    const mappingCheck = validateCsvAmountMapping();
    if (!mappingCheck.ok) {
      if (sub) sub.textContent = mappingCheck.error;
      return;
    }
    try {
      await api("/csv/mapping-presets", {
        method: "POST",
        body: JSON.stringify({
          account_id: accountId,
          institution_key: CSV_ACCOUNT_PRESET_KEY,
          preset: buildCsvPresetPayload(),
        }),
      });
      CSV_MODAL_STATE.activePreset = buildCsvPresetPayload();
      CSV_MODAL_STATE.activePresetAccountId = accountId;
      csvMappingSaved = true;
      const runBtn = document.getElementById("csvUploadRun");
      if (runBtn) runBtn.disabled = false;
      if (sub) sub.textContent = "Mapping saved for selected account.";
    } catch (e) {
      console.error(e);
      if (sub) sub.textContent = `Mapping save failed: ${e?.message || e}`;
    }
  }

  function updateCsvPickedName() {
    const el = document.getElementById("csvPickedName");
    if (!el) return;
    const f = CSV_MODAL_STATE.file;
    el.textContent = f ? `${f.name} (${Math.round(f.size / 1024)} KB)` : "No file selected";
  }

  function setCsvFileForPanel(f) {
    if (!f) return;
    CSV_MODAL_STATE.file = f;
    CSV_MODAL_STATE.columns = [];
    const { accountId } = selectedCsvAccountMeta();
    updateCsvPickedName();
    populateCsvMappingSelects([]);
    if (CSV_MODAL_STATE.activePreset && CSV_MODAL_STATE.activePresetAccountId === accountId) {
      applyCsvPreset(CSV_MODAL_STATE.activePreset);
    }
    const preview = document.getElementById("csvPreviewWrap");
    const sub = document.getElementById("csvUploadSub");
    const msg = document.getElementById("csvUploadMsg");
    if (preview) preview.innerHTML = `<div style="opacity:.65; padding:6px;">No preview yet.</div>`;
    if (msg) msg.textContent = "";
    if (sub) sub.textContent = "File selected. Click Preview File when ready.";
    updateCsvAmountModeUi();
  }

  async function refreshCsvPreview() {
    const msg = document.getElementById("csvUploadMsg");
    const sub = document.getElementById("csvUploadSub");
    const btn = document.getElementById("csvPreviewBtn");
    const mapArea = document.getElementById("csvMapArea");
    const finalizeActions = document.getElementById("csvFinalizeActions");
    const runBtn = document.getElementById("csvUploadRun");
    if (mapArea) mapArea.style.display = "";
    if (finalizeActions) finalizeActions.style.display = "flex";
    csvMappingSaved = false;
    if (runBtn) runBtn.disabled = true;
    if (msg) msg.textContent = "";
    if (!CSV_MODAL_STATE.file) {
      if (sub) sub.textContent = "Pick a file first.";
      return;
    }
    if (sub) sub.textContent = "Building preview...";
    if (btn) btn.disabled = true;
    try {
      const fd = new FormData();
      fd.append("file", CSV_MODAL_STATE.file, CSV_MODAL_STATE.file.name);
      fd.append("delimiter", document.getElementById("csvDelimiter")?.value || "auto");
      fd.append("has_header", csvHasHeaderEnabled() ? "true" : "false");
      fd.append("header_row", String(Math.max(1, Number(document.getElementById("csvHeaderRow")?.value || 1))));
      fd.append("data_start_row", String(Math.max(1, Number(document.getElementById("csvDataStartRow")?.value || 2))));
      fd.append("max_rows", "12");
      const out = await apiPostForm("/csv/preview", fd);
      if (!out?.ok) throw new Error("Preview failed");
      CSV_MODAL_STATE.columns = Array.isArray(out.columns) ? out.columns : [];
      CSV_MODAL_STATE.previewRows = Array.isArray(out.preview_rows) ? out.preview_rows : [];
      populateCsvMappingSelects(CSV_MODAL_STATE.columns);
      await loadCsvPreset();
      renderCsvPreview(out.preview_rows || [], CSV_MODAL_STATE.columns);
      updateCsvAmountModeUi();
      updateCsvIndicatorTypesHint();
      if (sub) sub.textContent = `Preview loaded (${out.row_count || 0} rows).`;
    } catch (e) {
      console.error(e);
      if (sub) sub.textContent = "Preview failed";
      if (msg) msg.textContent = String(e?.message || e);
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  function validateCsvAmountMapping() {
    const amountCol = csvGetSelectInt("csvMapAmount");
    const debitCol = csvGetSelectInt("csvMapDebit");
    const creditCol = csvGetSelectInt("csvMapCredit");
    const hasAnyPair = (debitCol !== null || creditCol !== null);
    if (!hasAnyPair && amountCol === null) {
      return { ok: false, error: "Map Amount, or map both Debit and Credit columns." };
    }
    if (hasAnyPair && (debitCol === null || creditCol === null)) {
      return { ok: false, error: "Map both Debit and Credit columns when using split amounts." };
    }
    if (amountCol !== null && hasAnyPair) {
      return { ok: false, error: "Use either Amount, or Debit/Credit pair. Not both." };
    }
    return { ok: true, mode: hasAnyPair ? "pair" : "single", amountCol, debitCol, creditCol };
  }

  function updateCsvAmountModeUi() {
    const hintEl = document.getElementById("csvAmountModeHint");
    const indicatorEl = document.getElementById("csvMapIndicator");
    const creditValueEl = document.getElementById("csvCreditIndicatorValue");
    if (!hintEl) return;
    const check = validateCsvAmountMapping();
    const usingPair = check.ok && check.mode === "pair";
    if (indicatorEl) indicatorEl.disabled = !!usingPair;
    if (creditValueEl) creditValueEl.disabled = !!usingPair;
    if (usingPair) {
      hintEl.style.display = "";
      hintEl.textContent = "Using split amount mode (Debit positive, Credit negative). Indicator mapping is ignored.";
      return;
    }
    if (!check.ok) {
      hintEl.style.display = "";
      hintEl.textContent = check.error;
      return;
    }
    hintEl.style.display = "none";
    hintEl.textContent = "";
  }

  function appendCsvMappingFields(fd, accountId, requireAccount = true) {
    const purchaseCol = csvGetSelectInt("csvMapPurchase");
    const merchantCol = csvGetSelectInt("csvMapMerchant");
    const amountCheck = validateCsvAmountMapping();
    if ((requireAccount && !accountId) || purchaseCol === null || merchantCol === null || !amountCheck.ok) {
      throw new Error(requireAccount
        ? `Map required fields: transaction date, merchant, and account. ${amountCheck.error || ""}`.trim()
        : `Map required fields: transaction date and merchant. ${amountCheck.error || ""}`.trim());
    }
    if (requireAccount) fd.append("account_id", String(accountId));
    fd.append("purchase_col", String(purchaseCol));
    if (amountCheck.mode === "single" && amountCheck.amountCol !== null) {
      fd.append("amount_col", String(amountCheck.amountCol));
    }
    if (amountCheck.mode === "pair") {
      fd.append("debit_col", String(amountCheck.debitCol));
      fd.append("credit_col", String(amountCheck.creditCol));
    }
    fd.append("merchant_col", String(merchantCol));
    fd.append("delimiter", document.getElementById("csvDelimiter")?.value || "auto");
    fd.append("has_header", csvHasHeaderEnabled() ? "true" : "false");
    fd.append("header_row", String(Math.max(1, Number(document.getElementById("csvHeaderRow")?.value || 1))));
    fd.append("data_start_row", String(Math.max(1, Number(document.getElementById("csvDataStartRow")?.value || 2))));
    fd.append("credit_indicator_value", String(document.getElementById("csvCreditIndicatorValue")?.value || "credit"));
    fd.append("invert_amount", document.getElementById("csvInvertAmount")?.checked ? "true" : "false");
    const posted = csvGetSelectInt("csvMapPosted");
    const indicator = csvGetSelectInt("csvMapIndicator");
    if (posted !== null) fd.append("posted_col", String(posted));
    if (amountCheck.mode === "single" && indicator !== null) fd.append("indicator_col", String(indicator));
  }

  function ensureCsvDryRunCompareModal() {
    let root = document.getElementById("csvDryRunCompareRoot");
    if (root) return root;
    root = document.createElement("div");
    root.id = "csvDryRunCompareRoot";
    root.className = "tx-inspect hidden";
    root.innerHTML = `
      <div class="tx-inspect__backdrop" data-csv-dry-close></div>
      <div class="tx-inspect__card" role="dialog" aria-modal="true" aria-label="CSV dry run comparison">
        <div class="tx-inspect__head">
          <div>
            <div class="tx-inspect__title">CSV Dry Run Comparison</div>
            <div id="csvDryRunCompareSub" class="tx-inspect__sub"></div>
          </div>
          <button class="tx-inspect__close" type="button" data-csv-dry-close aria-label="Close">X</button>
        </div>
        <div id="csvDryRunCompareBody" class="tx-inspect__body csv-dryrun__body"></div>
      </div>
    `;
    document.body.appendChild(root);
    root.addEventListener("click", (e) => {
      if (e.target?.matches?.("[data-csv-dry-close]")) root.classList.add("hidden");
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") root.classList.add("hidden");
    });
    return root;
  }

  function csvDryRowsTable(rows, { showMatch = false, showId = false } = {}) {
    const list = Array.isArray(rows) ? rows : [];
    if (!list.length) return `<div class="csv-dryrun__empty">None</div>`;
    const matchHead = showMatch ? `<th>Match</th>` : "";
    const idHead = showId ? `<th>ID</th>` : "";
    const body = list.map((r) => {
      const date = csvEscapeHtml(String(r.purchaseDate || ""));
      const amt = csvMoney(r.amount);
      const merch = csvEscapeHtml(String(r.merchant || ""));
      const matchCell = showMatch ? `<td class="csv-dryrun__mono">${csvEscapeHtml(String(r.match_id || ""))}</td>` : "";
      const idCell = showId ? `<td class="csv-dryrun__mono">${csvEscapeHtml(String(r.id || ""))}</td>` : "";
      return `<tr><td>${date}</td><td class="csv-dryrun__num">${amt}</td><td>${merch}</td>${matchCell}${idCell}</tr>`;
    }).join("");
    return `<div class="csv-dryrun__table-wrap"><table class="csv-dryrun__table"><thead><tr><th>Date</th><th class="csv-dryrun__num">Amount</th><th>Merchant</th>${matchHead}${idHead}</tr></thead><tbody>${body}</tbody></table></div>`;
  }

  function openCsvDryRunCompareModal(compare, summary) {
    const root = ensureCsvDryRunCompareModal();
    const sub = document.getElementById("csvDryRunCompareSub");
    const body = document.getElementById("csvDryRunCompareBody");
    if (!root || !sub || !body) return;
    const s = summary || {};
    const updExact = Array.isArray(compare?.would_update_exact) ? compare.would_update_exact : [];
    const updTip = Array.isArray(compare?.would_update_tip) ? compare.would_update_tip : [];
    const toInsert = Array.isArray(compare?.would_insert) ? compare.would_insert : [];
    const matchedIds = new Set([...updExact, ...updTip].map((r) => String(r?.match_id || "").trim()).filter(Boolean));
    const pendingAll = Array.isArray(compare?.pending) ? compare.pending : [];
    const pending = pendingAll.filter((r) => !matchedIds.has(String(r?.id || "").trim()));
    sub.textContent = `Valid ${s.valid_rows || 0}  Invalid ${s.invalid_rows || 0}  Start ${compare?.import_start_date || "none"}  Pending ${pending.length}`;
    body.innerHTML = `
      <div class="csv-dryrun__summary">
        <div class="csv-dryrun__card"><div class="csv-dryrun__k">Update exact</div><div class="csv-dryrun__v">${updExact.length}</div></div>
        <div class="csv-dryrun__card csv-dryrun__card--tip"><div class="csv-dryrun__k">Update tip</div><div class="csv-dryrun__v">${updTip.length}</div></div>
        <div class="csv-dryrun__card"><div class="csv-dryrun__k">Insert</div><div class="csv-dryrun__v">${toInsert.length}</div></div>
        <div class="csv-dryrun__card"><div class="csv-dryrun__k">Pending now</div><div class="csv-dryrun__v">${pending.length}</div></div>
      </div>
      <section class="csv-dryrun__section"><header class="csv-dryrun__section-head"><h4>Will Update (Exact)</h4><span>${updExact.length}</span></header>${csvDryRowsTable(updExact.slice(0, 250), { showMatch: true })}</section>
      <section class="csv-dryrun__section"><header class="csv-dryrun__section-head"><h4>Will Update (Tip Adjust)</h4><span>${updTip.length}</span></header>${csvDryRowsTable(updTip.slice(0, 250), { showMatch: true })}</section>
      <section class="csv-dryrun__section"><header class="csv-dryrun__section-head"><h4>Will Insert</h4><span>${toInsert.length}</span></header>${csvDryRowsTable(toInsert.slice(0, 250))}</section>
      <section class="csv-dryrun__section"><header class="csv-dryrun__section-head"><h4>Current Pending Email Transactions</h4><span>${pending.length}</span></header>${csvDryRowsTable(pending.slice(0, 500), { showId: true })}</section>
    `;
    root.classList.remove("hidden");
  }

  async function runCsvDryRun() {
    const msg = document.getElementById("csvUploadMsg");
    const sub = document.getElementById("csvUploadSub");
    const btn = document.getElementById("csvDryRunBtn");
    if (msg) msg.textContent = "";
    if (!CSV_MODAL_STATE.file) {
      if (sub) sub.textContent = "Pick a file first.";
      return;
    }
    const accountId = Number(CSV_MODAL_STATE.selectedAccountId || 0);
    if (!accountId) {
      if (sub) sub.textContent = "Choose an account first.";
      return;
    }
    if (sub) sub.textContent = "Running dry run...";
    if (btn) btn.disabled = true;
    try {
      const fd = new FormData();
      fd.append("file", CSV_MODAL_STATE.file, CSV_MODAL_STATE.file.name);
      fd.append("account_id", String(accountId));
      appendCsvMappingFields(fd, 0, false);
      const out = await apiPostForm("/csv/ingest-mapped/dry-run", fd);
      if (!out?.ok) throw new Error("Dry run failed");
      const s = out.summary || {};
      if (sub) sub.textContent = `Dry run: ${s.valid_rows || 0} valid, ${s.invalid_rows || 0} invalid (${s.total_rows || 0} total).`;
      const compare = out.compare || null;
      if (compare) {
        openCsvDryRunCompareModal(compare, s);
        if (msg) msg.textContent = "Dry run compare opened.";
      } else {
        const samples = Array.isArray(s.sample_errors) ? s.sample_errors.slice(0, 10) : [];
        if (msg) msg.textContent = samples.length ? JSON.stringify(samples, null, 2) : "No sample errors.";
      }
    } catch (e) {
      console.error(e);
      if (sub) sub.textContent = "Dry run failed";
      if (msg) msg.textContent = String(e?.message || e);
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  function stopCsvImportProgress() {
    if (CSV_IMPORT_PROGRESS_TIMER) {
      clearInterval(CSV_IMPORT_PROGRESS_TIMER);
      CSV_IMPORT_PROGRESS_TIMER = null;
    }
  }

  function renderCsvImportProgress() {
    const sub = document.getElementById("csvUploadSub");
    if (!sub) return;
    const pct = Math.max(0, Math.min(99, Math.round(CSV_IMPORT_PROGRESS_PCT)));
    sub.textContent = `Importing... ${pct}%`;
  }

  function startCsvImportProgress() {
    stopCsvImportProgress();
    CSV_IMPORT_PROGRESS_PCT = 4;
    renderCsvImportProgress();
    CSV_IMPORT_PROGRESS_TIMER = setInterval(() => {
      if (CSV_IMPORT_PROGRESS_PCT >= 96) return;
      const remaining = 96 - CSV_IMPORT_PROGRESS_PCT;
      const step = Math.max(0.6, remaining * 0.08);
      CSV_IMPORT_PROGRESS_PCT += step;
      renderCsvImportProgress();
    }, 180);
  }

  function completeCsvImportProgress() {
    stopCsvImportProgress();
    CSV_IMPORT_PROGRESS_PCT = 100;
    const sub = document.getElementById("csvUploadSub");
    if (sub) sub.textContent = "Importing... 100%";
  }

  async function runCsvIngestMapped() {
    const msg = document.getElementById("csvUploadMsg");
    const sub = document.getElementById("csvUploadSub");
    const runBtn = document.getElementById("csvUploadRun");
    if (msg) msg.textContent = "";
    if (!csvMappingSaved) {
      if (sub) sub.textContent = "Save mapping before importing.";
      if (msg) msg.textContent = "Import is disabled until mapping is saved.";
      if (runBtn) runBtn.disabled = true;
      return;
    }
    if (!CSV_MODAL_STATE.file) {
      if (sub) sub.textContent = "Pick a file first.";
      return;
    }
    const accountId = Number(CSV_MODAL_STATE.selectedAccountId || 0);
    if (!accountId) {
      if (sub) sub.textContent = "Choose an account first.";
      return;
    }
    startCsvImportProgress();
    if (runBtn) runBtn.disabled = true;
    try {
      const fd = new FormData();
      fd.append("file", CSV_MODAL_STATE.file, CSV_MODAL_STATE.file.name);
      appendCsvMappingFields(fd, accountId);
      const out = await apiPostForm("/csv/ingest-mapped", fd);
      if (!out?.ok) throw new Error("Import failed");
      completeCsvImportProgress();
      const errCount = Array.isArray(out.errors) ? out.errors.length : 0;
      if (sub) sub.textContent = `Imported ${out.inserted || 0}, updated ${out.updated || 0}, skipped ${out.skipped || 0}${errCount ? `, ${errCount} row errors` : ""}.`;
      if (msg) msg.textContent = errCount ? JSON.stringify(out.errors, null, 2) : "Import complete.";
      await refreshStatus();
    } catch (e) {
      console.error(e);
      stopCsvImportProgress();
      if (sub) sub.textContent = "Import failed";
      if (msg) msg.textContent = String(e?.message || e);
    } finally {
      stopCsvImportProgress();
      if (runBtn) runBtn.disabled = false;
    }
  }

  function resetCsvPanel() {
    CSV_MODAL_STATE.file = null;
    CSV_MODAL_STATE.columns = [];
    CSV_MODAL_STATE.previewRows = [];
    const input = document.getElementById("csvFileInput");
    const preview = document.getElementById("csvPreviewWrap");
    const sub = document.getElementById("csvUploadSub");
    const msg = document.getElementById("csvUploadMsg");
    const mapArea = document.getElementById("csvMapArea");
    const finalizeActions = document.getElementById("csvFinalizeActions");
    const indicatorHint = document.getElementById("csvIndicatorTypesHint");
    const amountModeHint = document.getElementById("csvAmountModeHint");
    const runBtn = document.getElementById("csvUploadRun");
    if (input) input.value = "";
    if (preview) preview.innerHTML = `<div style="opacity:.65; padding:6px;">No preview yet.</div>`;
    if (msg) msg.textContent = "";
    if (sub) sub.textContent = "Drop a CSV or Excel file, preview it, map columns, then import.";
    const hasHeaderEl = document.getElementById("csvHasHeader");
    if (hasHeaderEl) hasHeaderEl.checked = true;
    if (mapArea) mapArea.style.display = "none";
    if (finalizeActions) finalizeActions.style.display = "none";
    if (indicatorHint) {
      indicatorHint.style.display = "none";
      indicatorHint.textContent = "";
    }
    if (amountModeHint) {
      amountModeHint.style.display = "none";
      amountModeHint.textContent = "";
    }
    csvMappingSaved = false;
    if (runBtn) runBtn.disabled = true;
    populateCsvMappingSelects([]);
    updateCsvHeaderModeUi();
    updateCsvAmountModeUi();
    updateCsvPickedName();
  }

  function markCsvMappingDirty() {
    csvMappingSaved = false;
    const runBtn = document.getElementById("csvUploadRun");
    if (runBtn) runBtn.disabled = true;
  }

  function bindCsvInlineImporter() {
    const pickBtn = document.getElementById("csvPickFileBtn");
    const input = document.getElementById("csvFileInput");
    const previewBtn = document.getElementById("csvPreviewBtn");
    const dryRunBtn = document.getElementById("csvDryRunBtn");
    const savePresetBtn = document.getElementById("csvSavePresetBtn");
    const runBtn = document.getElementById("csvUploadRun");
    const drop = document.getElementById("csvDropZone");
    const mappingInputIds = [
      "csvDelimiter",
      "csvHasHeader",
      "csvHeaderRow",
      "csvDataStartRow",
      "csvMapPurchase",
      "csvMapPosted",
      "csvMapAmount",
      "csvMapDebit",
      "csvMapCredit",
      "csvMapMerchant",
      "csvMapIndicator",
      "csvCreditIndicatorValue",
      "csvInvertAmount",
    ];

    if (pickBtn && input) pickBtn.addEventListener("click", () => input.click());
    if (input) {
      input.addEventListener("change", () => {
        const f = input.files?.[0];
        if (f) setCsvFileForPanel(f);
        markCsvMappingDirty();
      });
    }
    if (previewBtn) previewBtn.addEventListener("click", refreshCsvPreview);
    if (dryRunBtn) dryRunBtn.addEventListener("click", runCsvDryRun);
    if (savePresetBtn) savePresetBtn.addEventListener("click", saveCsvPreset);
    if (runBtn) runBtn.addEventListener("click", runCsvIngestMapped);

    if (drop) {
      drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.style.background = "rgba(0,0,0,.03)"; });
      drop.addEventListener("dragleave", () => { drop.style.background = ""; });
      drop.addEventListener("drop", (e) => {
        e.preventDefault();
        drop.style.background = "";
        const f = e.dataTransfer?.files?.[0];
        if (!f) return;
        if (input) {
          const dt = new DataTransfer();
          dt.items.add(f);
          input.files = dt.files;
        }
        setCsvFileForPanel(f);
        markCsvMappingDirty();
      });
    }

    mappingInputIds.forEach((id) => {
      const el = document.getElementById(id);
      if (!el) return;
      const ev = (id === "csvCreditIndicatorValue" || id === "csvHeaderRow" || id === "csvDataStartRow") ? "input" : "change";
      el.addEventListener(ev, () => {
        markCsvMappingDirty();
        if (id === "csvHasHeader") updateCsvHeaderModeUi();
        updateCsvAmountModeUi();
      });
      if (id === "csvMapIndicator") {
        el.addEventListener("change", updateCsvIndicatorTypesHint);
      }
      if (id === "csvMapDebit" || id === "csvMapCredit" || id === "csvMapAmount") {
        el.addEventListener("change", updateCsvIndicatorTypesHint);
      }
    });

    resetCsvPanel();
    syncCsvSelectedAccount();
    loadCsvPreset().catch(console.error);
  }

  function collectBenefits() {
    const rows = document.querySelectorAll(".benefit-row");
    const benefits = [];
    for (const row of rows) {
      const category = (row.querySelector(".benefit-category")?.value || "").trim();
      const percentRaw = (row.querySelector(".benefit-percent")?.value || "").trim();
      if (!category && !percentRaw) continue;
      const percent = Number(percentRaw);
      if (!category) throw new Error("Each benefit row needs a category.");
      if (!Number.isFinite(percent) || percent < 0 || percent > 100) {
        throw new Error("Benefit cashback percent must be between 0 and 100.");
      }
      benefits.push({ benefit_type: category, cashback_percent: percent });
    }
    return benefits;
  }

  async function refreshStatus() {
    try {
      const s = await api("/onboarding/status");
      statusEl.innerHTML = `
        <div>${pill(!!s.steps.accounts_added, "Accounts Added")}</div>
        <div>${pill(!!s.steps.starting_balances_added, "Starting Balances Added")}</div>
        <div>${pill(!!s.steps.transactions_imported, "Transactions Imported")}</div>
        <div>${pill(!!s.steps.pushover_user_key_set, "Pushover User Key Saved")}</div>
        <div style="margin-top:8px;" class="muted">
          Accounts: ${s.counts.accounts} | Starting Balances: ${s.counts.starting_balances} | Transactions: ${s.counts.transactions}
        </div>
      `;
      latestAccounts = Array.isArray(s.accounts) ? s.accounts : [];
      canSetStartingBalance = !!s.can_set_starting_balance;
      applyStartingBalanceVisibility();
      renderAccountsList();
      syncCsvSelectedAccount();
      loadCsvPreset().catch(console.error);
    } catch (e) {
      statusEl.textContent = `Status failed: ${e.message}`;
    }
  }

  async function addAccount() {
    addResultEl.textContent = "";
    const accounttype = document.getElementById("accounttype").value.trim().toLowerCase();
    let benefits = [];
    try {
      benefits = collectBenefits();
    } catch (e) {
      addResultEl.textContent = e.message || "Invalid credit benefit rows.";
      return;
    }
    if (accounttype !== "credit" && benefits.length) {
      addResultEl.textContent = "Credit benefits can only be added for credit accounts.";
      return;
    }
    const body = {
      institution: document.getElementById("institution").value.trim(),
      name: document.getElementById("name").value.trim(),
      accounttype: accounttype,
      starting_balance: (() => {
        const v = document.getElementById("startingBalance").value.trim();
        return v ? Number(v) : null;
      })(),
      starting_date: document.getElementById("startingDate").value.trim() || null,
      credit_limit: (() => {
        const v = document.getElementById("creditLimit").value.trim();
        return v ? Number(v) : null;
      })(),
      apy_percent: (() => {
        const v = document.getElementById("apyPercent").value.trim();
        return v ? Number(v) : null;
      })(),
      interest_post_day: (() => {
        const v = document.getElementById("interestPostDay").value.trim();
        return v ? Number(v) : null;
      })(),
      receives_emails: !!document.getElementById("receivesEmails")?.checked,
      is_paycheck_account: !!document.getElementById("isPaycheckAccount")?.checked,
    };
    if (!editingAccountId || accounttype === "credit") {
      body.card_benefits = benefits;
    }
    try {
      const out = editingAccountId
        ? await api(`/onboarding/accounts/${Number(editingAccountId)}`, { method: "PUT", body: JSON.stringify(body) })
        : await api("/onboarding/accounts", { method: "POST", body: JSON.stringify(body) });
      addResultEl.textContent = editingAccountId
        ? `Updated account id ${out.account_id}.`
        : `Added account id ${out.account_id}.`;
      csvPreferredAccountId = Number(out.account_id || 0);
      setEditMode(false, null);
      resetAccountForm();
      await refreshStatus();
    } catch (e) {
      addResultEl.textContent = `Add failed: ${e.message}`;
    }
  }

  async function markComplete() {
    try {
      await api("/onboarding/complete", { method: "POST", body: JSON.stringify({ completed: true }) });
      await refreshStatus();
      alert("Wizard marked complete.");
    } catch (e) {
      alert(`Failed: ${e.message}`);
    }
  }

  async function savePushoverUserKey() {
    if (!pushoverResultEl) return;
    pushoverResultEl.textContent = "";
    const userKeyEl = document.getElementById("pushoverUserKey");
    const user_key = (userKeyEl && userKeyEl.value ? userKeyEl.value : "").trim();
    try {
      const out = await api("/onboarding/pushover-key", {
        method: "POST",
        body: JSON.stringify({ user_key }),
      });
      pushoverResultEl.textContent = out.user_key_set ? "Pushover user key saved." : "Pushover user key cleared.";
      await refreshStatus();
    } catch (e) {
      pushoverResultEl.textContent = `Save failed: ${e.message}`;
    }
  }

  async function sendPushoverTest() {
    if (!pushoverResultEl) return;
    pushoverResultEl.textContent = "";
    const userKeyEl = document.getElementById("pushoverUserKey");
    const user_key = (userKeyEl && userKeyEl.value ? userKeyEl.value : "").trim();
    try {
      await api("/onboarding/pushover-test", {
        method: "POST",
        body: JSON.stringify({ user_key }),
      });
      pushoverResultEl.textContent = "Test notification sent.";
    } catch (e) {
      pushoverResultEl.textContent = `Test failed: ${e.message}`;
    }
  }

  function openParserWizard() {
    window.location.href = "/email-parser-wizard";
  }

  document.getElementById("refreshBtn").addEventListener("click", refreshStatus);
  document.getElementById("addAccountBtn").addEventListener("click", addAccount);
  document.getElementById("addBenefitBtn").addEventListener("click", () => addBenefitRow("", ""));
  if (cancelEditBtnEl) {
    cancelEditBtnEl.addEventListener("click", () => {
      setEditMode(false, null);
      resetAccountForm();
      addResultEl.textContent = "Edit cancelled.";
    });
  }
  const openParserWizardBtn = document.getElementById("openParserWizardBtn");
  if (openParserWizardBtn) openParserWizardBtn.addEventListener("click", openParserWizard);
  document.getElementById("accounttype").addEventListener("change", updateAccountFieldHints);
  const savePushoverKeyBtn = document.getElementById("savePushoverKeyBtn");
  if (savePushoverKeyBtn) savePushoverKeyBtn.addEventListener("click", savePushoverUserKey);
  const sendPushoverTestBtn = document.getElementById("sendPushoverTestBtn");
  if (sendPushoverTestBtn) sendPushoverTestBtn.addEventListener("click", sendPushoverTest);
  bindCsvInlineImporter();

  resetAccountForm();
  setEditMode(false, null);
  refreshStatus();
})();

