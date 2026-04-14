// /static/shared/shared.js
(async function () {
  const rawBuild = String(window.BUILD_ID || "").trim();
  const unresolvedTemplate = rawBuild.includes("{") || rawBuild.includes("}");
  const cacheBuster = (rawBuild && !unresolvedTemplate) ? rawBuild : String(Date.now());
  const v = `?v=${encodeURIComponent(cacheBuster)}`;

  // 1) Load shared chrome HTML
  const res = await fetch(`/static/shared/shared.html${v}`, { cache: "no-store" });
  if (!res.ok) {
    console.error("Failed to load shared.html", res.status);
    return;
  }
  const html = await res.text();

  // 2) Inject into a single mount point (recommended)
  const mount = document.getElementById("sharedChrome");
  if (!mount) {
    console.error('Missing <div id="sharedChrome"></div> on page');
    return;
  }
  mount.innerHTML = html;

  // 3) Helper to load scripts in sequence
  function loadScript(src) {
    return new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = src + v;
      s.defer = true;
      s.onload = resolve;
      s.onerror = reject;
      document.body.appendChild(s);
    });
  }

  // 4) Load shared behavior scripts in parallel to reduce time-to-interactive.
  try {
    await Promise.all([
      loadScript("/static/shared/topBar.js"),
      loadScript("/static/shared/bottomTabs.js"),
      loadScript("/static/shared/notifs.js"),
    ]);
  } catch (e) {
    console.error("Failed loading shared scripts", e);
  }

  // 4.5) Client-side error tracking for pages that do not import api.module.js.
  (function installGlobalClientErrorTracking() {
    if (window.__clientErrorTrackingInstalled) return;
    window.__clientErrorTrackingInstalled = true;

    const ENDPOINT = "/admin/error-notifications/client";
    const MAX_EVENTS = 30;
    const DEDUPE_MS = 20000;
    let sentCount = 0;
    const recent = new Map();

    function shouldSend(key) {
      if (!key) return false;
      if (sentCount >= MAX_EVENTS) return false;
      const now = Date.now();
      const prev = Number(recent.get(key) || 0);
      if (prev > 0 && (now - prev) < DEDUPE_MS) return false;
      recent.set(key, now);
      sentCount += 1;
      return true;
    }

    function report(payload, dedupeKey) {
      const key = String(dedupeKey || payload?.message || "client_error").slice(0, 300);
      if (!shouldSend(key)) return;
      let body = "{}";
      try {
        body = JSON.stringify(payload || {});
      } catch {
        body = JSON.stringify({ source: "client_report_json_error", message: "Failed to serialize payload" });
      }

      try {
        if (navigator && typeof navigator.sendBeacon === "function") {
          const blob = new Blob([body], { type: "application/json" });
          navigator.sendBeacon(ENDPOINT, blob);
          return;
        }
      } catch {}

      try {
        fetch(ENDPOINT, {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json" },
          body,
          keepalive: true,
        }).catch(() => {});
      } catch {}
    }

    window.addEventListener("error", (evt) => {
      try {
        const target = evt && evt.target;
        const isResourceError = !!(target && target !== window);
        const message = isResourceError
          ? `resource_load_failed: ${String(target?.tagName || "unknown")}`
          : String(evt?.message || "window_error");
        const stack = String(evt?.error?.stack || "").slice(0, 3000);
        const requestUrl = String(evt?.filename || target?.src || target?.href || "").slice(0, 1000);
        const source = isResourceError ? "resource_error" : "window_error";
        report(
          {
            source,
            message: message.slice(0, 1000),
            stack,
            page_url: String(window.location.href || "").slice(0, 1000),
            route: `${window.location.pathname || "/"}${window.location.search || ""}`,
            request_url: requestUrl || null,
            request_method: "CLIENT",
            status_code: 0,
            user_agent: String(navigator?.userAgent || "").slice(0, 500),
          },
          `${source}:${message}:${requestUrl}`,
        );
      } catch {}
    }, true);

    window.addEventListener("unhandledrejection", (evt) => {
      try {
        const reason = evt?.reason;
        const msg = (reason && (reason.message || String(reason))) || "unhandled_rejection";
        const stack = String(reason?.stack || "").slice(0, 3000);
        report(
          {
            source: "unhandled_rejection",
            message: String(msg).slice(0, 1000),
            stack,
            page_url: String(window.location.href || "").slice(0, 1000),
            route: `${window.location.pathname || "/"}${window.location.search || ""}`,
            request_method: "CLIENT",
            status_code: 0,
            user_agent: String(navigator?.userAgent || "").slice(0, 500),
          },
          `unhandled_rejection:${String(msg).slice(0, 200)}`,
        );
      } catch {}
    });
  })();

  // 4.75) Show a single "what changed" popup after deploys/new commits.
  (async function installAppUpdateSummary() {
    if (window.__appUpdateSummaryInstalled) return;
    window.__appUpdateSummaryInstalled = true;

    const STORAGE_KEY = "app_updates_last_seen_id";
    const SESSION_KEY = "app_updates_last_seen_id_session";
    const AUTO_SUPPRESS_SESSION_KEY = "app_updates_auto_suppressed_session";

    function escHtml(s) {
      return String(s ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
    }

    function formatWhen(tsSeconds) {
      const n = Number(tsSeconds || 0);
      if (!Number.isFinite(n) || n <= 0) return "";
      try {
        return new Date(n * 1000).toLocaleString();
      } catch {
        return "";
      }
    }

    function splitSubjectLines(subject) {
      const s = String(subject || "").replace(/\s+/g, " ").trim();
      if (!s) return [];

      let parts = s.split(/\s+\|\s+|;\s+/).map((x) => x.trim()).filter(Boolean);
      if (parts.length > 1) return parts;

      parts = s
        .split(/\s+(?=(?:Added|Fixed|Fix|Removed|Updated|Moved|Made|Improved|Implemented|Refactored|User can now|CSV importer|Budget page|Minor))/gi)
        .map((x) => x.trim())
        .filter(Boolean);
      return parts.length > 1 ? parts : [s];
    }

    function renderSubjectHtml(subject) {
      const lines = splitSubjectLines(subject);
      if (lines.length <= 1) {
        return `<div class="app-update-item__subject">${escHtml(lines[0] || "Update")}</div>`;
      }
      return `
        <ul class="app-update-item__bullets">
          ${lines.map((line) => `<li>${escHtml(line)}</li>`).join("")}
        </ul>
      `;
    }

    function ensureModal() {
      let root = document.getElementById("appUpdatesModal");
      if (root) return root;

      root = document.createElement("div");
      root.id = "appUpdatesModal";
      root.className = "notif-modal hidden";
      root.setAttribute("aria-hidden", "true");
      root.innerHTML = `
        <div class="notif-modal-card" role="dialog" aria-modal="true" aria-label="App updates">
          <div class="notif-modal-header">
            <div id="appUpdatesModalTitle" class="notif-modal-title">What Changed</div>
            <button id="appUpdatesModalClose" class="icon-btn" type="button" aria-label="Close">&#10005;</button>
          </div>
          <div id="appUpdatesModalMeta" class="notif-modal-meta"></div>
          <div id="appUpdatesModalBody" class="notif-modal-body"></div>
          <div class="notif-modal-actions">
            <button id="appUpdatesModalOk" class="settings-btn primary" type="button">Got it</button>
          </div>
        </div>
      `;
      document.body.appendChild(root);
      return root;
    }

    function getLastSeenId() {
      let local = "";
      let session = "";
      const mem = String(window.__appUpdatesLastSeenMem || "").trim();
      try { local = String(localStorage.getItem(STORAGE_KEY) || "").trim(); } catch {}
      try { session = String(sessionStorage.getItem(SESSION_KEY) || "").trim(); } catch {}
      // Prefer in-memory/session values for this tab so a stale localStorage
      // value cannot force repeated reopen loops.
      return mem || session || local;
    }

    function markSeen(id) {
      const v = String(id || "").trim();
      if (!v) return;
      window.__appUpdatesLastSeenMem = v;
      try { localStorage.setItem(STORAGE_KEY, v); } catch {}
      try { sessionStorage.setItem(SESSION_KEY, v); } catch {}
    }

    function isAutoSuppressedForSession() {
      try {
        return String(sessionStorage.getItem(AUTO_SUPPRESS_SESSION_KEY) || "").trim() === "1";
      } catch {
        return false;
      }
    }

    function suppressAutoForSession() {
      try { sessionStorage.setItem(AUTO_SUPPRESS_SESSION_KEY, "1"); } catch {}
    }

    function openModalWithRows(rows, latestIdForDismiss) {
      if (window.__appUpdatesModalOpen) return Promise.resolve();
      const root = ensureModal();
      const meta = document.getElementById("appUpdatesModalMeta");
      const body = document.getElementById("appUpdatesModalBody");
      const closeBtn = document.getElementById("appUpdatesModalClose");
      const okBtn = document.getElementById("appUpdatesModalOk");
      if (!root || !body || !okBtn) return Promise.resolve();

      const safeRows = Array.isArray(rows) ? rows : [];
      if (meta) meta.textContent = `${safeRows.length} update${safeRows.length === 1 ? "" : "s"} since your last visit`;
      body.innerHTML = `
        <div class="app-update-list">
          ${safeRows.map((r) => {
        const sid = escHtml(r?.short_id || "");
        const when = escHtml(formatWhen(r?.ts));
        return `
          <article class="app-update-item">
            <div class="app-update-item__meta">${sid}${when ? ` • ${when}` : ""}</div>
            ${renderSubjectHtml(r?.subject)}
          </article>
        `;
      }).join("")}
        </div>
      `;

      root.classList.remove("hidden");
      root.setAttribute("aria-hidden", "false");
      window.__appUpdatesModalOpen = true;

      return new Promise((resolve) => {
        const finish = () => {
          if (latestIdForDismiss) {
            window.__appUpdatesDismissedLatestId = String(latestIdForDismiss).trim();
            markSeen(latestIdForDismiss);
            suppressAutoForSession();
          }
          root.classList.add("hidden");
          root.setAttribute("aria-hidden", "true");
          window.__appUpdatesModalOpen = false;
          closeBtn?.removeEventListener("click", finish);
          okBtn.removeEventListener("click", finish);
          root.removeEventListener("click", onBackdropClick);
          document.removeEventListener("keydown", onKeydown);
          resolve();
        };
        const onBackdropClick = (e) => {
          if (e.target === root) finish();
        };
        const onKeydown = (e) => {
          if (e.key === "Escape") finish();
        };
        closeBtn?.addEventListener("click", finish);
        okBtn.addEventListener("click", finish);
        root.addEventListener("click", onBackdropClick);
        document.addEventListener("keydown", onKeydown);
      });
    }

    async function fetchUpdates() {
      const res = await fetch(`/app/updates${v}`, { cache: "no-store" });
      if (!res.ok) {
        console.warn("app updates fetch failed:", res.status);
        return null;
      }
      return res.json();
    }

    window.openLatestAppUpdatesModal = async function openLatestAppUpdatesModal() {
      try {
        const data = await fetchUpdates();
        const updates = Array.isArray(data?.updates) ? data.updates : [];
        if (!updates.length) return;
        await openModalWithRows([updates[0]]);
      } catch (_err) {
        // non-fatal
      }
    };

    try {
      const data = await fetchUpdates();
      const updates = Array.isArray(data?.updates) ? data.updates : [];
      const latestId = String(data?.latest_id || updates?.[0]?.id || data?.build_id || "").trim();
      if (!latestId) return;

      let lastSeen = getLastSeenId();
      if (isAutoSuppressedForSession()) {
        markSeen(latestId);
        return;
      }

      let unseen = [];
      if (!lastSeen) {
        // First run on this browser: still show the latest update so users
        // always get an initial "what changed" message.
        unseen = updates.slice(0, Math.min(1, updates.length));
      } else if (lastSeen !== latestId) {
        const idx = updates.findIndex((u) => String(u?.id || "") === lastSeen);
        if (idx >= 0) unseen = updates.slice(0, idx);
        else unseen = updates.slice(0, Math.min(25, updates.length));
      } else {
        unseen = [];
      }

      if (!unseen.length) {
        markSeen(latestId);
        return;
      }

      // If already dismissed in this tab/session, don't reopen in a loop.
      if (String(window.__appUpdatesDismissedLatestId || "").trim() === latestId) {
        markSeen(latestId);
        return;
      }

      // Show oldest->newest so stacked updates read like a changelog.
      unseen = unseen.slice().reverse();
      await openModalWithRows(unseen, latestId);
      markSeen(latestId);
    } catch (_err) {
      // Non-fatal: app should continue even if updates feed is unavailable.
    }
  })();

  // 5) Mobile pull-to-refresh (global across shared-chrome pages).
  (function installPullToRefresh() {
    if (window.__mobilePullToRefreshInstalled) return;
    window.__mobilePullToRefreshInstalled = true;

    const isMobile = () => window.matchMedia("(max-width: 900px)").matches;
    const canStartFromTop = () =>
      isMobile() &&
      (window.scrollY || document.documentElement.scrollTop || 0) <= 0;

    const isInteractiveTarget = (el) => {
      const tag = String(el?.tagName || "").toLowerCase();
      return tag === "input" || tag === "textarea" || tag === "select" || el?.isContentEditable;
    };

    const isBottomTabsTarget = (el) => {
      return !!el?.closest?.("#bottomTabs, .mobile-tabs, .mobile-tab");
    };

    let startY = 0;
    let pullPx = 0;
    let pulling = false;
    let triggered = false;
    const THRESHOLD_PX = 90;
    const MAX_PULL_PX = 140;
    const DRAG_RESISTANCE = 0.55;
    const START_DRAG_PX = 12;

    const indicator = document.createElement("div");
    indicator.id = "mobilePullRefreshIndicator";
    indicator.setAttribute("aria-hidden", "true");
    indicator.style.position = "fixed";
    indicator.style.left = "50%";
    indicator.style.top = "0";
    indicator.style.transform = "translate(-50%, -56px)";
    indicator.style.zIndex = "10050";
    indicator.style.pointerEvents = "none";
    indicator.style.opacity = "0";
    indicator.style.transition = "transform 140ms ease, opacity 140ms ease";
    indicator.style.padding = "8px 12px";
    indicator.style.borderRadius = "999px";
    indicator.style.border = "1px solid rgba(0,0,0,0.15)";
    indicator.style.background = "var(--card, #fff)";
    indicator.style.color = "var(--text, #111)";
    indicator.style.boxShadow = "0 6px 20px rgba(0,0,0,0.18)";
    indicator.style.fontSize = "12px";
    indicator.style.fontWeight = "700";
    indicator.style.lineHeight = "1";
    indicator.textContent = "Pull to refresh";
    document.body.appendChild(indicator);

    function setPullVisual(offsetPx, ready) {
      const y = Math.max(0, Math.min(MAX_PULL_PX, Number(offsetPx || 0)));
      pullPx = y;
      document.body.style.transition = "none";
      if (y > 0) {
        document.body.style.transform = `translateY(${y}px)`;
      } else {
        document.body.style.removeProperty("transform");
      }

      if (y <= 0) {
        indicator.style.opacity = "0";
        indicator.style.transform = "translate(-50%, -56px)";
        indicator.textContent = "Pull to refresh";
        return;
      }

      indicator.style.opacity = "1";
      indicator.style.transform = `translate(-50%, ${Math.max(6, y - 42)}px)`;
      indicator.textContent = ready ? "Release to refresh" : "Pull to refresh";
    }

    function resetPullVisual(animated) {
      if (animated) document.body.style.transition = "transform 180ms ease";
      document.body.style.transform = "translateY(0)";
      pullPx = 0;
      indicator.style.opacity = "0";
      indicator.style.transform = "translate(-50%, -56px)";
      indicator.textContent = "Pull to refresh";
      if (animated) {
        window.setTimeout(() => {
          document.body.style.removeProperty("transform");
          document.body.style.transition = "";
        }, 220);
      } else {
        document.body.style.removeProperty("transform");
        document.body.style.transition = "";
      }
    }

    window.addEventListener(
      "touchstart",
      (e) => {
        if (!canStartFromTop()) return;
        if (!e.touches || e.touches.length !== 1) return;
        if (isInteractiveTarget(e.target)) return;
        if (isBottomTabsTarget(e.target)) return;
        startY = e.touches[0].clientY;
        pulling = true;
        triggered = false;
        pullPx = 0;
      },
      { passive: true }
    );

    window.addEventListener(
      "touchmove",
      (e) => {
        if (!pulling || triggered) return;
        if (!e.touches || e.touches.length !== 1) return;
        const dy = e.touches[0].clientY - startY;
        if (dy <= 0) return;
        if (dy < START_DRAG_PX) return;
        if (!canStartFromTop()) {
          pulling = false;
          resetPullVisual(false);
          return;
        }
        const visualPull = Math.min(MAX_PULL_PX, dy * DRAG_RESISTANCE);
        setPullVisual(visualPull, visualPull >= THRESHOLD_PX);
        // Prevent elastic overscroll while user is pulling down.
        e.preventDefault();
      },
      { passive: false }
    );

    window.addEventListener(
      "touchend",
      (e) => {
        if (!pulling || triggered) return;
        const changed = e.changedTouches && e.changedTouches[0];
        const endY = changed ? changed.clientY : startY;
        const dy = endY - startY;
        pulling = false;
        const visualPull = Math.min(MAX_PULL_PX, Math.max(0, dy) * DRAG_RESISTANCE);
        if (visualPull < THRESHOLD_PX) {
          resetPullVisual(true);
          return;
        }
        triggered = true;
        indicator.style.opacity = "1";
        indicator.style.transform = "translate(-50%, 16px)";
        indicator.textContent = "Refreshing...";
        document.body.style.transition = "transform 120ms ease";
        document.body.style.transform = "translateY(56px)";
        window.setTimeout(() => window.location.reload(), 90);
      },
      { passive: true }
    );

    window.addEventListener(
      "touchcancel",
      () => {
        pulling = false;
        triggered = false;
        resetPullVisual(true);
      },
      { passive: true }
    );
  })();
})();

