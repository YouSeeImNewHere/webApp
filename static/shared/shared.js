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

    let startY = 0;
    let pullPx = 0;
    let pulling = false;
    let triggered = false;
    const THRESHOLD_PX = 90;
    const MAX_PULL_PX = 140;
    const DRAG_RESISTANCE = 0.55;

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

