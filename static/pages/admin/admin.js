import { apiGetJson, apiPostJson } from "/static/shared/api.module.js";

let TENANTS = [];

function byId(id) {
  return document.getElementById(id);
}

function setStatus(msg) {
  const el = byId("statusMsg");
  if (el) el.textContent = msg || "";
}

function fmtJson(obj) {
  try {
    return JSON.stringify(obj, null, 2);
  } catch (_) {
    return String(obj);
  }
}

function selectedTenant() {
  const sel = byId("tenantSelect");
  if (!sel) return null;
  const id = Number(sel.value || 0);
  if (!id) return null;
  return TENANTS.find((t) => Number(t.id) === id) || null;
}

async function loadPendingUsers() {
  const box = byId("pendingUsersList");
  if (!box) return;
  box.innerHTML = "";
  let data;
  try {
    data = await apiGetJson("/admin/pending-users", { cache: "no-store" });
  } catch (err) {
    box.textContent = "Failed to load pending users.";
    return;
  }

  const items = Array.isArray(data?.items) ? data.items : [];
  if (!items.length) {
    box.textContent = "No pending users.";
    return;
  }

  for (const u of items) {
    const row = document.createElement("div");
    row.className = "admin-user";
    row.innerHTML = `
      <div>
        <div><strong>${u.email || ""}</strong></div>
        <div class="admin-muted">id=${u.id} created=${u.created_at || ""}</div>
      </div>
      <button class="settings-btn primary" type="button">Approve</button>
    `;
    const btn = row.querySelector("button");
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      try {
        await apiPostJson(`/admin/pending-users/${encodeURIComponent(u.id)}/approve`, {});
        setStatus(`Approved user ${u.email || u.id}`);
        await loadPendingUsers();
        await loadTenants();
      } catch (err) {
        setStatus(`Failed approving user ${u.email || u.id}`);
        btn.disabled = false;
      }
    });
    box.appendChild(row);
  }
}

function escHtml(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function shortWhen(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return String(iso);
    return d.toLocaleString();
  } catch {
    return String(iso);
  }
}

function emailParseTenantFilter() {
  const raw = String(byId("emailParseTenantSelect")?.value || "").trim();
  if (!raw) return null;
  const n = Number(raw);
  if (!Number.isFinite(n) || n <= 0) return null;
  return Math.floor(n);
}

function formatEmailSent(whenRaw) {
  const raw = String(whenRaw || "").trim();
  if (!raw) return "-";
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return raw;
  return d.toLocaleString();
}

async function loadAdminErrorFeed() {
  const box = byId("adminErrorList");
  if (!box) return;
  box.innerHTML = "";
  let data;
  try {
    data = await apiGetJson("/admin/error-notifications?limit=150", { cache: "no-store" });
  } catch (err) {
    box.textContent = "Failed to load admin notifications.";
    return;
  }
  const items = Array.isArray(data?.items) ? data.items : [];
  if (!items.length) {
    box.textContent = "No server errors captured.";
    return;
  }
  for (const it of items) {
    const reqLine = `${it.method || ""} ${it.path || ""}${it.query_string ? ("?" + it.query_string) : ""}`.trim();
    const row = document.createElement("div");
    row.className = "admin-error";
    row.innerHTML = `
      <div class="admin-error__head">
        <span>${escHtml(String(it.status_code || ""))}  ${escHtml(reqLine || "(request unknown)")}</span>
        <span>${escHtml(shortWhen(it.created_at))}</span>
      </div>
      <div class="admin-error__msg">${escHtml(it.error_message || "Server error")}</div>
      <div class="admin-error__meta">User: ${escHtml(it.user_email || "-")}  Tenant: ${escHtml(String(it.tenant_id ?? "-"))}  IP: ${escHtml(it.client_ip || "-")}</div>
      <div class="admin-error__meta">Page: ${escHtml(it.page_url || it.referer || "-")}</div>
    `;
    box.appendChild(row);
  }
}

async function loadEmailParseLogs() {
  const box = byId("emailParseLogList");
  if (!box) return;
  box.innerHTML = "";
  let data;
  try {
    const tenantId = emailParseTenantFilter();
    const q = tenantId ? `&tenant_id=${encodeURIComponent(tenantId)}` : "";
    data = await apiGetJson(`/admin/email-parse-events?limit=200${q}`, { cache: "no-store" });
  } catch (err) {
    box.textContent = "Failed to load email parser logs.";
    return;
  }
  const items = Array.isArray(data?.items) ? data.items : [];
  if (!items.length) {
    box.textContent = "No parser logs captured yet.";
    return;
  }
  for (const it of items) {
    const row = document.createElement("div");
    row.className = "admin-parse";
    const isServerLine = String(it.status || "").trim().toLowerCase() === "server_log";
    const subject = String(it.subject || "").trim() || "(no subject)";
    const reason = String(it.reason || "").trim() || (it.matched ? "matched" : "skipped");
    const parserLabel = it.parser_draft_id
      ? `draft=${it.parser_draft_id}${it.parser_slot ? ` (${it.parser_slot})` : ""}`
      : "parser=none";
    const txBits = [
      it.account_label || (it.account_id ? `Account ${it.account_id}` : ""),
      it.merchant ? `merchant=${it.merchant}` : "",
      (it.amount !== null && it.amount !== undefined) ? `amount=${it.amount}` : "",
    ].filter(Boolean).join("  ");
    if (isServerLine) {
      row.innerHTML = `
      <div class="admin-error__head">
        <span>${escHtml(it.run_source || "server")}  LOG</span>
        <span>${escHtml(shortWhen(it.created_at))}</span>
      </div>
      <div class="admin-parse__subject">${escHtml(reason || "(log line)")}</div>
      <div class="admin-error__meta">User: ${escHtml(it.user_email || "-")}  Tenant: ${escHtml(String(it.tenant_id ?? "-"))}</div>
    `;
      box.appendChild(row);
      continue;
    }
    row.innerHTML = `
      <div class="admin-error__head">
        <span>${escHtml(it.matched ? "MATCHED" : "SKIPPED")}  ${escHtml(reason)}</span>
        <span>${escHtml(shortWhen(it.created_at))}</span>
      </div>
      <div class="admin-parse__subject">${escHtml(subject)}</div>
      <div class="admin-error__meta">Email sent: ${escHtml(formatEmailSent(it.received_at))}</div>
      <div class="admin-error__meta">Source: ${escHtml(it.run_source || "-")}  ${escHtml(parserLabel)}  inserted=${it.inserted ? "yes" : "no"} notified=${it.notified ? "yes" : "no"}  imap_id=${escHtml(it.imap_id || "-")}</div>
      <div class="admin-error__meta">Sender: ${escHtml(it.sender || "-")}  User: ${escHtml(it.user_email || "-")}  Tenant: ${escHtml(String(it.tenant_id ?? "-"))}</div>
      <div class="admin-error__meta">${escHtml(txBits || "No extracted transaction details.")}</div>
    `;
    box.appendChild(row);
  }
}

async function loadTenants() {
  const sel = byId("tenantSelect");
  const emailSel = byId("emailParseTenantSelect");
  if (!sel) return;
  let data;
  try {
    data = await apiGetJson("/admin/tenants", { cache: "no-store" });
  } catch (err) {
    setStatus("Failed to load tenants.");
    return;
  }
  TENANTS = Array.isArray(data?.items) ? data.items : [];
  sel.innerHTML = "";
  if (emailSel) {
    const prev = String(emailSel.value || "");
    emailSel.innerHTML = `<option value="">All tenants</option>`;
    for (const t of TENANTS) {
      const opt = document.createElement("option");
      opt.value = String(t.id);
      opt.textContent = `${t.id} | ${t.slug} | ${t.name || ""}`.trim();
      emailSel.appendChild(opt);
    }
    emailSel.value = prev;
  }
  for (const t of TENANTS) {
    const opt = document.createElement("option");
    opt.value = String(t.id);
    opt.textContent = `${t.id} | ${t.slug} | users=${t.users_count} tx=${t.transactions_count}`;
    sel.appendChild(opt);
  }
}

async function loadFootprint() {
  const t = selectedTenant();
  const box = byId("footprintBox");
  if (!box) return;
  if (!t) {
    box.textContent = "Select a tenant.";
    return;
  }
  try {
    const data = await apiGetJson(`/admin/tenants/${encodeURIComponent(t.id)}/footprint`, { cache: "no-store" });
    box.textContent = fmtJson(data);
  } catch (err) {
    box.textContent = "Failed loading footprint.";
  }
}

function purgeBody(dryRun) {
  return {
    dry_run: !!dryRun,
    delete_tenant: !!byId("deleteTenantRow")?.checked,
    delete_users: true,
  };
}

async function runPurge(dryRun) {
  const t = selectedTenant();
  const box = byId("purgeResultBox");
  if (!box) return;
  if (!t) {
    box.textContent = "Select a tenant.";
    return;
  }
  const confirmSlug = String(byId("confirmInput")?.value || "").trim().toLowerCase();
  if (!dryRun && confirmSlug !== String(t.slug || "").trim().toLowerCase()) {
    box.textContent = "Confirmation mismatch. Type the exact tenant slug.";
    return;
  }

  try {
    const data = await apiPostJson(
      `/admin/tenants/${encodeURIComponent(t.id)}/purge`,
      purgeBody(dryRun),
    );
    box.textContent = fmtJson(data);
    await loadTenants();
    await loadPendingUsers();
  } catch (err) {
    box.textContent = `Purge failed: ${String(err?.message || err)}`;
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  byId("refreshBtn")?.addEventListener("click", async () => {
    setStatus("Refreshing...");
    await loadPendingUsers();
    await loadAdminErrorFeed();
    await loadEmailParseLogs();
    await loadTenants();
    setStatus("Refreshed.");
  });
  byId("refreshAdminErrorsBtn")?.addEventListener("click", async () => {
    setStatus("Refreshing admin notifications...");
    await loadAdminErrorFeed();
    setStatus("Refreshed.");
  });
  byId("clearAdminErrorsBtn")?.addEventListener("click", async () => {
    const ok = confirm("Clear all admin notifications?");
    if (!ok) return;
    try {
      await apiPostJson("/admin/error-notifications/clear", {});
      await loadAdminErrorFeed();
      setStatus("Admin notifications cleared.");
    } catch (err) {
      setStatus("Failed clearing admin notifications.");
    }
  });
  byId("refreshEmailParseLogsBtn")?.addEventListener("click", async () => {
    setStatus("Refreshing email parser logs...");
    await loadEmailParseLogs();
    setStatus("Refreshed.");
  });
  byId("emailParseTenantSelect")?.addEventListener("change", async () => {
    await loadEmailParseLogs();
  });
  byId("clearEmailParseLogsBtn")?.addEventListener("click", async () => {
    const tenantId = emailParseTenantFilter();
    const scope = tenantId ? ` for tenant ${tenantId}` : "";
    const ok = confirm(`Clear email parser logs${scope || " for all tenants"}?`);
    if (!ok) return;
    try {
      await apiPostJson("/admin/email-parse-events/clear", {
        tenant_id: tenantId,
      });
      await loadEmailParseLogs();
      setStatus(`Email parser logs cleared${scope}.`);
    } catch (err) {
      setStatus("Failed clearing email parser logs.");
    }
  });
  byId("loadFootprintBtn")?.addEventListener("click", () => loadFootprint());
  byId("dryRunBtn")?.addEventListener("click", () => runPurge(true));
  byId("purgeBtn")?.addEventListener("click", () => runPurge(false));

  setStatus("Loading...");
  await loadPendingUsers();
  await loadAdminErrorFeed();
  await loadTenants();
  await loadEmailParseLogs();
  setStatus("Ready.");
});
