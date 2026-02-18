(function () {
  async function api(path, opts) {
    const res = await fetch(path, Object.assign({ headers: { "Content-Type": "application/json" } }, opts || {}));
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
  const addAccountBtnEl = document.getElementById("addAccountBtn");
  const cancelEditBtnEl = document.getElementById("cancelEditBtn");

  let editingAccountId = null;
  let latestAccounts = [];

  function pill(ok, label) {
    const cls = ok ? "ok" : "todo";
    const txt = ok ? "Done" : "Pending";
    return `<span class="setup-pill ${cls}">${txt}</span>${label}`;
  }

  function updateAccountFieldHints() {
    const accountType = (document.getElementById("accounttype").value || "").trim().toLowerCase();
    const creditEl = document.getElementById("creditLimit");
    const apyEl = document.getElementById("apyPercent");
    const benefitsWrap = document.getElementById("creditBenefitsWrap");
    const addBenefitBtn = document.getElementById("addBenefitBtn");
    const benefitInputs = document.querySelectorAll(".benefit-input");
    const creditMode = accountType === "credit";
    if (creditEl) {
      creditEl.disabled = !creditMode;
      if (!creditMode) creditEl.value = "";
    }
    if (apyEl) {
      apyEl.disabled = creditMode;
      if (creditMode) apyEl.value = "";
    }
    if (benefitsWrap) benefitsWrap.style.opacity = creditMode ? "1" : "0.55";
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
    setEditMode(true, a);
    updateAccountFieldHints();
    addResultEl.textContent = `Editing account #${a.id}.`;
  }

  function renderAccountsList() {
    if (!accountsListEl) return;
    if (!latestAccounts.length) {
      accountsListEl.innerHTML = `<div class="setup-muted">No accounts yet.</div>`;
      return;
    }
    accountsListEl.innerHTML = `
      <div class="setup-list">
        ${latestAccounts.map((a) => `
          <div class="setup-list-row">
            <div>
              <div><strong>${String(a.institution || "")} - ${String(a.name || "")}</strong> <span class="setup-list-meta">(${String(a.accounttype || "").toLowerCase()})</span></div>
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
      renderAccountsList();
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

  async function fetchEmailsNow() {
    if (!pushoverResultEl) return;
    pushoverResultEl.textContent = "Starting email fetch...";
    try {
      const out = await api("/gmail/fetch-now", { method: "POST", body: "{}" });
      pushoverResultEl.textContent = out.status === "already_running"
        ? "Email fetch is already running."
        : "Email fetch started. Check logs for results.";
    } catch (e) {
      pushoverResultEl.textContent = `Fetch failed: ${e.message}`;
    }
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
  document.getElementById("completeBtn").addEventListener("click", markComplete);
  document.getElementById("accounttype").addEventListener("change", updateAccountFieldHints);
  const savePushoverKeyBtn = document.getElementById("savePushoverKeyBtn");
  if (savePushoverKeyBtn) savePushoverKeyBtn.addEventListener("click", savePushoverUserKey);
  const sendPushoverTestBtn = document.getElementById("sendPushoverTestBtn");
  if (sendPushoverTestBtn) sendPushoverTestBtn.addEventListener("click", sendPushoverTest);
  const fetchEmailsNowBtn = document.getElementById("fetchEmailsNowBtn");
  if (fetchEmailsNowBtn) fetchEmailsNowBtn.addEventListener("click", fetchEmailsNow);

  resetAccountForm();
  setEditMode(false, null);
  refreshStatus();
})();

