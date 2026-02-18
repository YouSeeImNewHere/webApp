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

async function loadTenants() {
  const sel = byId("tenantSelect");
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
    await loadTenants();
    setStatus("Refreshed.");
  });
  byId("loadFootprintBtn")?.addEventListener("click", () => loadFootprint());
  byId("dryRunBtn")?.addEventListener("click", () => runPurge(true));
  byId("purgeBtn")?.addEventListener("click", () => runPurge(false));

  setStatus("Loading...");
  await loadPendingUsers();
  await loadTenants();
  setStatus("Ready.");
});
