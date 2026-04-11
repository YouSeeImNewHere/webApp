// /static/shared/notifs.js
// Notifications drawer + badge for the top bar.
// Supports General notifications and owner-only Errors feed.

(function () {
  if (window.__notifTopbarLoaded) return;
  window.__notifTopbarLoaded = true;

  const $ = (id) => document.getElementById(id);

  function escHtml(s) {
    return String(s ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function formatWhen(iso) {
    if (!iso) return "";
    try {
      const d = new Date(iso);
      if (Number.isNaN(d.getTime())) return String(iso);
      return d.toLocaleString();
    } catch {
      return String(iso);
    }
  }

  async function api(path, opts) {
    const baseHeaders = new Headers((opts && opts.headers) || {});
    if (!baseHeaders.has("Content-Type")) baseHeaders.set("Content-Type", "application/json");
    try {
      const preview = String(localStorage.getItem("settings_view_non_admin_preview") || "").trim();
      if (preview === "1") baseHeaders.set("X-Non-Admin-Preview", "1");
    } catch {}
    const merged = Object.assign({}, opts || {}, { headers: baseHeaders });
    const res = await fetch(path, merged);
    if (!res.ok) {
      const t = await res.text().catch(() => "");
      const err = new Error(res.status + " " + t);
      err.status = res.status;
      err.body = t;
      throw err;
    }
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("application/json")) return res.json();
    return res.text();
  }

  function bindIfPresent() {
    if (window.__notifTopbarBound) return;

    const btn = $("topBarNotif");
    const badge = $("topBarNotifBadge");
    const overlay = $("notifOverlay");
    const panel = $("notifPanel");
    const closeBtn = $("notifCloseBtn");
    const refreshBtn = $("notifRefreshBtn");
    const markAllBtn = $("notifMarkAllReadBtn");
    const clearReadBtn = $("notifClearReadBtn");
    const clearErrorsBtn = $("notifClearErrorsBtn");
    const listHost = $("notifList");
    const detail = $("notifDetail");
    const detailDismiss = $("notifDismissBtn");
    const subtitle = $("notifSubtitle");
    const tabGeneral = $("notifTabGeneral");
    const tabErrors = $("notifTabErrors");
    const tabsHost = $("notifTabs");
    const errorsCount = $("notifErrorsCount");

    const modal = $("notifModal");
    const modalTitle = $("notifModalTitle");
    const modalMeta = $("notifModalMeta");
    const modalBody = $("notifModalBody");
    const modalClose = $("notifModalClose");
    const modalOk = $("notifModalOk");
    const modalDismiss = $("notifModalDismiss");
    let modalApprove = $("notifModalApprove");

    if (!btn || !badge || !overlay || !panel || !listHost) return;

    window.__notifTopbarBound = true;

    const state = {
      selectedId: null,
      selectedPendingUserId: null,
      activeTab: "general",
      canViewErrors: false,
      generalItems: [],
      errorItems: [],
    };

    function ensureApproveButton() {
      if (modalApprove) return modalApprove;
      if (!modalDismiss || !modalDismiss.parentElement) return null;
      const b = document.createElement("button");
      b.id = "notifModalApprove";
      b.className = "settings-btn hidden";
      b.type = "button";
      b.textContent = "Approve";
      modalDismiss.parentElement.insertBefore(b, modalDismiss);
      modalApprove = b;
      return modalApprove;
    }

    function setApproveButtonForUser(userId) {
      const b = ensureApproveButton();
      if (!b) return;
      if (userId) {
        b.classList.remove("hidden");
        b.disabled = false;
      } else {
        b.classList.add("hidden");
        b.disabled = false;
      }
    }

    function setModalDismissVisible(show, text) {
      if (!modalDismiss) return;
      modalDismiss.classList.toggle("hidden", !show);
      modalDismiss.disabled = false;
      modalDismiss.textContent = text || "Dismiss";
    }

    function parsePendingSignupBody(body) {
      const text = String(body || "");
      const idMatch = text.match(/User ID:\s*(\d+)/i);
      const emailMatch = text.match(/Email:\s*([^\s]+)/i);
      return {
        userId: idMatch ? Number(idMatch[1]) : null,
        email: emailMatch ? emailMatch[1] : null,
      };
    }

    async function resolvePendingUserIdFromEmail(email) {
      if (!email) return null;
      try {
        const data = await api("/admin/pending-users", { method: "GET" });
        const items = Array.isArray(data.items) ? data.items : [];
        const wanted = String(email).trim().toLowerCase();
        const match = items.find((x) => String(x.email || "").trim().toLowerCase() === wanted);
        return match ? Number(match.id) : null;
      } catch (_e) {
        return null;
      }
    }

    function openModal() {
      if (!modal) return;
      modal.classList.remove("hidden");
      modal.setAttribute("aria-hidden", "false");
    }

    function closeModal() {
      if (!modal) return;
      modal.classList.add("hidden");
      modal.setAttribute("aria-hidden", "true");
      state.selectedId = null;
      state.selectedPendingUserId = null;
      setApproveButtonForUser(null);
      setModalDismissVisible(true, "Dismiss");
    }

    function setOpen(open) {
      const show = !!open;
      overlay.classList.toggle("hidden", !show);
      panel.classList.toggle("hidden", !show);
      overlay.setAttribute("aria-hidden", String(!show));
      panel.setAttribute("aria-hidden", String(!show));
      if (!show) {
        state.selectedId = null;
        detail && detail.classList.add("hidden");
      }
    }

    function renderBadge(n) {
      const count = Number(n || 0);
      if (count > 0) {
        badge.textContent = String(count);
        badge.classList.remove("hidden");
      } else {
        badge.classList.add("hidden");
      }
    }

    function updateErrorCountBadge() {
      if (!errorsCount) return;
      const count = Array.isArray(state.errorItems) ? state.errorItems.length : 0;
      errorsCount.textContent = String(count);
      errorsCount.classList.toggle("hidden", count <= 0);
    }

    function updateTabsUI() {
      const showErrors = state.canViewErrors !== false;
      if (tabsHost) {
        tabsHost.classList.toggle("hidden", !showErrors);
      }
      if (tabGeneral) {
        const active = state.activeTab === "general";
        tabGeneral.classList.toggle("is-active", active);
        tabGeneral.setAttribute("aria-selected", String(active));
      }
      if (tabErrors) {
        tabErrors.classList.toggle("hidden", !showErrors);
        const active = showErrors && state.activeTab === "errors";
        tabErrors.classList.toggle("is-active", active);
        tabErrors.setAttribute("aria-selected", String(active));
      }
      if (markAllBtn) markAllBtn.classList.toggle("hidden", state.activeTab !== "general");
      if (clearReadBtn) clearReadBtn.classList.toggle("hidden", state.activeTab !== "general");
      if (clearErrorsBtn) clearErrorsBtn.classList.toggle("hidden", state.activeTab !== "errors");
    }

    function setTab(nextTab) {
      const wanted = String(nextTab || "general");
      if (wanted === "errors" && state.canViewErrors === false) {
        state.activeTab = "general";
      } else if (wanted === "errors") {
        state.activeTab = "errors";
      } else {
        state.activeTab = "general";
      }
      updateTabsUI();
      refreshActive();
    }

    function renderGeneralList(items) {
      listHost.innerHTML = "";
      const rows = Array.isArray(items) ? items : [];
      if (!rows.length) {
        listHost.innerHTML = '<div class="notif-empty">No notifications.</div>';
        if (subtitle) subtitle.textContent = "0 items";
        renderBadge(0);
        return;
      }

      const unreadCount = rows.reduce((a, x) => a + (!x.is_read ? 1 : 0), 0);
      if (subtitle) subtitle.textContent = `${rows.length} items, ${unreadCount} unread`;
      renderBadge(unreadCount);

      for (const n of rows) {
        const row = document.createElement("button");
        row.type = "button";
        row.className = "notif-row" + (n.is_read ? "" : " notif-row--unread");
        row.dataset.id = String(n.id);
        row.innerHTML = `
          <div class="notif-row-top">
            <div class="notif-row-sub">${escHtml(n.sender || "")}</div>
            <div class="notif-row-time">${escHtml(n.created_at_local || "")}</div>
          </div>
          <div class="notif-row-title">${escHtml(n.subject || "(no subject)")}</div>
        `;
        row.addEventListener("click", () => openGeneralDetail(n.id));
        listHost.appendChild(row);
      }
    }

    function renderErrorsList(items) {
      listHost.innerHTML = "";
      const rows = Array.isArray(items) ? items : [];
      if (!rows.length) {
        listHost.innerHTML = '<div class="notif-empty">No captured errors.</div>';
        if (subtitle) subtitle.textContent = "0 errors";
        return;
      }

      if (subtitle) subtitle.textContent = `${rows.length} errors`;
      for (const it of rows) {
        const req = `${it.method || ""} ${it.path || ""}${it.query_string ? ("?" + it.query_string) : ""}`.trim();
        const row = document.createElement("button");
        row.type = "button";
        row.className = "notif-row notif-row--error";
        row.dataset.id = String(it.id || "");
        row.innerHTML = `
          <div class="notif-row-top">
            <div class="notif-row-sub">${escHtml((it.status_code ? String(it.status_code) + " " : "") + (req || "(request unknown)"))}</div>
            <div class="notif-row-time">${escHtml(formatWhen(it.created_at))}</div>
          </div>
          <div class="notif-row-title">${escHtml(it.error_message || "Server error")}</div>
          <div class="notif-row-sub">${escHtml(it.user_email || "unknown user")}</div>
        `;
        row.addEventListener("click", () => openErrorDetail(it.id));
        listHost.appendChild(row);
      }
    }

    async function refreshGeneral() {
      const data = await api("/notifications", { method: "GET" });
      state.generalItems = Array.isArray(data.items) ? data.items : [];
      return state.generalItems;
    }

    async function refreshErrors() {
      try {
        const data = await api("/admin/error-notifications?limit=200", { method: "GET" });
        state.canViewErrors = true;
        state.errorItems = Array.isArray(data.items) ? data.items : [];
      } catch (e) {
        if (e && (e.status === 401 || e.status === 403)) {
          state.canViewErrors = false;
          state.errorItems = [];
        } else {
          throw e;
        }
      }
      updateErrorCountBadge();
      updateTabsUI();
      return state.errorItems;
    }

    async function refreshActive() {
      try {
        if (state.activeTab === "errors") {
          await refreshErrors();
          renderErrorsList(state.errorItems);
          return;
        }
        await refreshGeneral();
        renderGeneralList(state.generalItems);
      } catch (e) {
        console.error("notifications refresh failed:", e);
        if (subtitle) subtitle.textContent = "Failed to load notifications";
      }
    }

    async function refreshCount() {
      try {
        const data = await api("/notifications/unread-count", { method: "GET" });
        renderBadge(data.unread || 0);
      } catch (e) {
        console.warn("notif unread-count failed:", e);
        renderBadge(0);
      }
    }

    async function openGeneralDetail(id) {
      state.selectedId = id;
      try {
        const data = await api("/notifications/" + encodeURIComponent(id), { method: "GET" });

        if (modalTitle) modalTitle.textContent = data.subject || "(no subject)";
        if (modalMeta) modalMeta.textContent = (data.sender || "") + (data.created_at_local ? (" | " + data.created_at_local) : "");
        if (modalBody) modalBody.textContent = data.body || "";

        if (data.kind === "user_signup_pending") {
          const parsed = parsePendingSignupBody(data.body || "");
          state.selectedPendingUserId = parsed.userId || null;
          if (!state.selectedPendingUserId && parsed.email) {
            state.selectedPendingUserId = await resolvePendingUserIdFromEmail(parsed.email);
          }
        } else {
          state.selectedPendingUserId = null;
        }
        setApproveButtonForUser(state.selectedPendingUserId);
        setModalDismissVisible(true, "Dismiss");
        openModal();

        await api("/notifications/" + encodeURIComponent(id) + "/read", { method: "POST" }).catch(() => {});
        await refreshGeneral();
        if (state.activeTab === "general") renderGeneralList(state.generalItems);
      } catch (e) {
        console.error("openGeneralDetail failed:", e);
      }
    }

    async function openErrorDetail(id) {
      const hit = (state.errorItems || []).find((x) => String(x.id) === String(id));
      if (!hit) return;
      state.selectedId = String(hit.id || "");
      state.selectedPendingUserId = null;
      setApproveButtonForUser(null);
      setModalDismissVisible(false);
      if (modalTitle) {
        const req = `${hit.method || ""} ${hit.path || ""}`.trim();
        modalTitle.textContent = `${hit.status_code || ""} ${req || "Error"}`.trim();
      }
      if (modalMeta) modalMeta.textContent = `${formatWhen(hit.created_at)} | ${hit.user_email || "unknown user"}`;
      if (modalBody) {
        const lines = [
          `message: ${hit.error_message || ""}`,
          `request: ${(hit.method || "")} ${(hit.path || "")}${hit.query_string ? ("?" + hit.query_string) : ""}`,
          `page: ${hit.page_url || "-"}`,
          `referer: ${hit.referer || "-"}`,
          `tenant_id: ${hit.tenant_id ?? "-"}`,
          `ip: ${hit.client_ip || "-"}`,
          `request_id: ${hit.request_id || "-"}`,
          `user_agent: ${hit.user_agent || "-"}`,
        ];
        modalBody.textContent = lines.join("\n");
      }
      openModal();
    }

    async function dismissSelected() {
      if (!state.selectedId || state.activeTab !== "general") return;
      const id = state.selectedId;
      state.selectedId = null;
      try {
        await api("/notifications/" + encodeURIComponent(id) + "/dismiss", { method: "POST" });
      } catch (e) {
        console.error("dismiss failed:", e);
      }
      detail && detail.classList.add("hidden");
      await refreshGeneral();
      if (state.activeTab === "general") renderGeneralList(state.generalItems);
    }

    async function markAllRead() {
      if (state.activeTab !== "general") return;
      try {
        await api("/notifications/mark-all-read", { method: "POST" });
      } catch (e) {
        console.error(e);
      }
      await refreshGeneral();
      if (state.activeTab === "general") renderGeneralList(state.generalItems);
    }

    async function clearRead() {
      if (state.activeTab !== "general") return;
      try {
        await api("/notifications/clear-read", { method: "POST" });
      } catch (e) {
        console.error(e);
      }
      detail && detail.classList.add("hidden");
      await refreshGeneral();
      if (state.activeTab === "general") renderGeneralList(state.generalItems);
    }

    async function clearErrors() {
      if (state.activeTab !== "errors") return;
      const ok = window.confirm("Clear all captured errors?");
      if (!ok) return;
      try {
        await api("/admin/error-notifications/clear", { method: "POST", body: "{}" });
        await refreshErrors();
        renderErrorsList(state.errorItems);
      } catch (e) {
        console.error("clear errors failed:", e);
      }
    }

    btn.addEventListener("click", async () => {
      const opening = overlay.classList.contains("hidden");
      setOpen(opening);
      if (!opening) return;
      await refreshCount();
      await refreshErrors().catch(() => {});
      updateTabsUI();
      await refreshActive();
    });

    tabGeneral && tabGeneral.addEventListener("click", () => setTab("general"));
    tabErrors && tabErrors.addEventListener("click", () => setTab("errors"));
    overlay.addEventListener("click", () => setOpen(false));
    closeBtn && closeBtn.addEventListener("click", () => setOpen(false));
    refreshBtn && refreshBtn.addEventListener("click", refreshActive);
    detailDismiss && detailDismiss.addEventListener("click", dismissSelected);
    markAllBtn && markAllBtn.addEventListener("click", markAllRead);
    clearReadBtn && clearReadBtn.addEventListener("click", clearRead);
    clearErrorsBtn && clearErrorsBtn.addEventListener("click", clearErrors);

    modalClose && modalClose.addEventListener("click", closeModal);
    modalOk && modalOk.addEventListener("click", closeModal);
    modal && modal.addEventListener("click", (e) => {
      if (e.target === modal) closeModal();
    });

    modalDismiss && modalDismiss.addEventListener("click", async () => {
      if (state.activeTab !== "general" || !state.selectedId) return;
      try {
        await api("/notifications/" + encodeURIComponent(state.selectedId) + "/dismiss", { method: "POST" });
      } catch (e) {
        console.error("dismiss failed:", e);
      }
      closeModal();
      await refreshGeneral();
      if (state.activeTab === "general") renderGeneralList(state.generalItems);
    });

    const modalApproveBtn = ensureApproveButton();
    modalApproveBtn && modalApproveBtn.addEventListener("click", async () => {
      if (!state.selectedId || !state.selectedPendingUserId) return;
      const notifId = state.selectedId;
      const userId = state.selectedPendingUserId;
      modalApproveBtn.disabled = true;
      try {
        await api("/admin/pending-users/" + encodeURIComponent(userId) + "/approve", {
          method: "POST",
          body: JSON.stringify({}),
        });
        await api("/notifications/" + encodeURIComponent(notifId) + "/dismiss", { method: "POST" }).catch(() => {});
        closeModal();
        await refreshGeneral();
        if (state.activeTab === "general") renderGeneralList(state.generalItems);
      } catch (e) {
        console.error("approve failed:", e);
        modalApproveBtn.disabled = false;
      }
    });

    updateTabsUI();
    refreshCount();
    window.__notifTopbarInterval = window.__notifTopbarInterval || setInterval(refreshCount, 30000);
  }

  bindIfPresent();

  const mo = new MutationObserver(() => bindIfPresent());
  mo.observe(document.documentElement, { childList: true, subtree: true });
})();
