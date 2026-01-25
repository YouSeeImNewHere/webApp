// /static/notifs.js
// Notifications drawer + badge for the top bar.
// Works even if the top-bar.html is injected via innerHTML (MutationObserver binds when elements appear).

(function () {
  if (window.__notifTopbarLoaded) return;
  window.__notifTopbarLoaded = true;

  const $ = (id) => document.getElementById(id);

  function escHtml(s){
    return String(s ?? "")
      .replaceAll("&","&amp;")
      .replaceAll("<","&lt;")
      .replaceAll(">","&gt;")
      .replaceAll('"',"&quot;")
      .replaceAll("'","&#039;");
  }

  async function api(path, opts){
    const res = await fetch(path, Object.assign({ headers: { "Content-Type":"application/json" } }, opts||{}));
    if (!res.ok){
      const t = await res.text().catch(()=> "");
      throw new Error(res.status + " " + t);
    }
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("application/json")) return res.json();
    return res.text();
  }

  function bindIfPresent(){
    // Avoid binding twice
    if (window.__notifTopbarBound) return;

    const btn = $("topBarNotif");
    const badge = $("topBarNotifBadge");
    const overlay = $("notifOverlay");
    const panel = $("notifPanel");
    const closeBtn = $("notifCloseBtn");
    const refreshBtn = $("notifRefreshBtn");
    const markAllBtn = $("notifMarkAllReadBtn");
    const clearReadBtn = $("notifClearReadBtn");
    const listHost = $("notifList");
    const detail = $("notifDetail");
    const detailMeta = $("notifDetailMeta");
    const detailTitle = $("notifDetailTitle");
    const detailBody = $("notifDetailBody");
    const detailDismiss = $("notifDismissBtn");
    const subtitle = $("notifSubtitle");

    // If the top bar isn't on this page (or hasn't been injected yet), skip for now.
    if (!btn || !badge || !overlay || !panel || !listHost) return;

    window.__notifTopbarBound = true;

    let selectedId = null;

    function setOpen(open){
      const show = !!open;
      overlay.classList.toggle("hidden", !show);
      panel.classList.toggle("hidden", !show);
      overlay.setAttribute("aria-hidden", String(!show));
      panel.setAttribute("aria-hidden", String(!show));
      if (!show){
        selectedId = null;
        detail && detail.classList.add("hidden");
      }
    }

    function renderBadge(n){
      const count = Number(n||0);
      if (count > 0){
        badge.textContent = String(count);
        badge.classList.remove("hidden");
      } else {
        badge.classList.add("hidden");
      }
    }

    function renderList(items){
      listHost.innerHTML = "";
      if (!items || items.length === 0){
        listHost.innerHTML = '<div class="notif-empty">No notifications 🎉</div>';
        if (subtitle) subtitle.textContent = "0 items";
        renderBadge(0);
        return;
      }

      const unreadCount = items.reduce((a,x)=> a + (!x.is_read ? 1 : 0), 0);
      if (subtitle) subtitle.textContent = items.length + " items • " + unreadCount + " unread";
      renderBadge(unreadCount);

      for (const n of items){
        const row = document.createElement("button");
        row.type = "button";
        row.className = "notif-row" + (n.is_read ? "" : " notif-row--unread");
        row.dataset.id = n.id;
        row.innerHTML = `
          <div class="notif-row-top">
            <div class="notif-row-sub">${escHtml(n.sender || "")}</div>
            <div class="notif-row-time">${escHtml(n.created_at_local || "")}</div>
          </div>
          <div class="notif-row-title">${escHtml(n.subject || "(no subject)")}</div>
        `;
        row.addEventListener("click", () => openDetail(n.id));
        listHost.appendChild(row);
      }
    }

    async function refresh(){
      try{
        const data = await api("/notifications", { method:"GET" });
        renderList(data.items || []);
      }catch(e){
        console.error("notif refresh failed:", e);
      }
    }

    async function refreshCount(){
      try{
        const data = await api("/notifications/unread-count", { method:"GET" });
        renderBadge(data.unread || 0);
      }catch(e){
        // If endpoint isn't available, just hide badge.
        console.warn("notif unread-count failed:", e);
        renderBadge(0);
      }
    }

    async function openDetail(id){
      selectedId = id;
      try{
        const data = await api("/notifications/" + encodeURIComponent(id), { method:"GET" });
        if (detailMeta) detailMeta.textContent = (data.sender || "") + (data.created_at_local ? (" • " + data.created_at_local) : "");
        if (detailTitle) detailTitle.textContent = data.subject || "(no subject)";
        if (detailBody) detailBody.textContent = data.body || "";
        detail && detail.classList.remove("hidden");

        // mark read
        await api("/notifications/" + encodeURIComponent(id) + "/read", { method:"POST" }).catch(()=>{});
        // refresh list (so unread style updates + badge updates)
        await refresh();
      }catch(e){
        console.error("openDetail failed:", e);
      }
    }

    async function dismissSelected(){
      if (!selectedId) return;
      const id = selectedId;
      selectedId = null;
      try{
        await api("/notifications/" + encodeURIComponent(id) + "/dismiss", { method:"POST" });
      }catch(e){
        console.error("dismiss failed:", e);
      }
      detail && detail.classList.add("hidden");
      await refresh();
    }

    async function markAllRead(){
      try{
        await api("/notifications/mark-all-read", { method:"POST" });
      }catch(e){
        console.error(e);
      }
      await refresh();
    }

    async function clearRead(){
      try{
        await api("/notifications/clear-read", { method:"POST" });
      }catch(e){
        console.error(e);
      }
      detail && detail.classList.add("hidden");
      await refresh();
    }

    btn.addEventListener("click", async () => {
      const opening = overlay.classList.contains("hidden");
      setOpen(opening);
      if (opening) await refresh();
    });
    overlay.addEventListener("click", () => setOpen(false));
    closeBtn && closeBtn.addEventListener("click", () => setOpen(false));
    refreshBtn && refreshBtn.addEventListener("click", refresh);
    detailDismiss && detailDismiss.addEventListener("click", dismissSelected);
    markAllBtn && markAllBtn.addEventListener("click", markAllRead);
    clearReadBtn && clearReadBtn.addEventListener("click", clearRead);

    // initial badge + periodic refresh
    refreshCount();
    window.__notifTopbarInterval = window.__notifTopbarInterval || setInterval(refreshCount, 30000);
  }

  // Try immediately, then keep watching for the top bar to be injected.
  bindIfPresent();

  const mo = new MutationObserver(() => bindIfPresent());
  mo.observe(document.documentElement, { childList: true, subtree: true });
})();
