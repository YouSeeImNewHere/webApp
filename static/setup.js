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

  function pill(ok, label) {
    const cls = ok ? "ok" : "todo";
    const txt = ok ? "Done" : "Pending";
    return `<span class="setup-pill ${cls}">${txt}</span>${label}`;
  }

  function updateAccountFieldHints() {
    const accountType = (document.getElementById("accounttype").value || "").trim().toLowerCase();
    const creditEl = document.getElementById("creditLimit");
    const apyEl = document.getElementById("apyPercent");
    if (creditEl) {
      creditEl.disabled = accountType !== "credit";
      if (accountType !== "credit") creditEl.value = "";
    }
    if (apyEl) {
      apyEl.disabled = accountType === "credit";
      if (accountType === "credit") apyEl.value = "";
    }
  }

  async function refreshStatus() {
    try {
      const s = await api("/onboarding/status");
      statusEl.innerHTML = `
        <div>${pill(!!s.steps.accounts_added, "Accounts Added")}</div>
        <div>${pill(!!s.steps.starting_balances_added, "Starting Balances Added")}</div>
        <div>${pill(!!s.steps.transactions_imported, "Transactions Imported")}</div>
        <div style="margin-top:8px;" class="muted">
          Accounts: ${s.counts.accounts} | Starting Balances: ${s.counts.starting_balances} | Transactions: ${s.counts.transactions}
        </div>
      `;
    } catch (e) {
      statusEl.textContent = `Status failed: ${e.message}`;
    }
  }

  async function addAccount() {
    addResultEl.textContent = "";
    const body = {
      institution: document.getElementById("institution").value.trim(),
      name: document.getElementById("name").value.trim(),
      accounttype: document.getElementById("accounttype").value.trim().toLowerCase(),
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
    };
    try {
      const out = await api("/onboarding/accounts", { method: "POST", body: JSON.stringify(body) });
      addResultEl.textContent = `Added account id ${out.account_id}.`;
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

  document.getElementById("refreshBtn").addEventListener("click", refreshStatus);
  document.getElementById("addAccountBtn").addEventListener("click", addAccount);
  document.getElementById("completeBtn").addEventListener("click", markComplete);
  document.getElementById("accounttype").addEventListener("change", updateAccountFieldHints);

  updateAccountFieldHints();
  refreshStatus();
})();
