// /static/shared/topBar.js
(async function () {
  const host = document.getElementById("topBar");
  if (!host) return;
  // If shared.html already contains top bar markup, skip fetch.
  if (!host.querySelector("#topBarTitle")) {
    const v = (window.BUILD_ID ? `?v=${encodeURIComponent(window.BUILD_ID)}` : "");
    const res = await fetch(`/static/partials/top-bar.html${v}`, { cache: "force-cache" });
    if (!res.ok) {
      console.error("Failed to load top bar:", res.status);
      return;
    }
    host.innerHTML = await res.text();
  }

  // 2) Title: prefer body[data-page-title], else document.title, else fallback
  const titleEl = host.querySelector("#topBarTitle");
  const bodyTitle = document.body?.dataset?.pageTitle;
  if (titleEl) titleEl.textContent = bodyTitle || document.title || "Page";

  // 3) Back button: ONLY show on pages not reachable from bottom tabs
  const path = window.location.pathname || "";

  // These are the pages you can access from bottom tabs (NO back button)
  const tabPaths = new Set([
    "/", // Home
    "/static/pages/spending/spending.html",
    "/static/pages/all-transactions/all-transactions.html",
    "/static/pages/recurring/recurring.html",
    "/static/pages/receipts/receipts.html",
  ]);

  const backBtn = host.querySelector("#topBarBack");
  const noBackPaths = new Set([
    ...tabPaths,
    "/settings",
    "/static/pages/settings/settings.html",
  ]);
  const shouldShowBack = !noBackPaths.has(path);
  if (backBtn) {
    backBtn.style.visibility = shouldShowBack ? "visible" : "hidden";

    backBtn.addEventListener("click", () => {
      // Prefer browser back if possible; otherwise go home
      if (window.history.length > 1) window.history.back();
      else window.location.href = "/";
    });
  }

  // Keep title centered between Settings and Notifications on mobile.
  const centerTitleBetweenIcons = () => {
    if (!titleEl) return;
    if (!window.matchMedia("(max-width: 900px)").matches) {
      titleEl.style.removeProperty("left");
      return;
    }
    const inner = host.querySelector(".top-bar-inner");
    const settingsBtn = inner?.querySelector('a.top-btn[href="/settings"]');
    const notifBtn = inner?.querySelector("#topBarNotif");
    if (!inner || !settingsBtn || !notifBtn) return;

    const innerRect = inner.getBoundingClientRect();
    const settingsRect = settingsBtn.getBoundingClientRect();
    const notifRect = notifBtn.getBoundingClientRect();
    const settingsCx = settingsRect.left + (settingsRect.width / 2);
    const notifCx = notifRect.left + (notifRect.width / 2);
    const mid = ((settingsCx + notifCx) / 2) - innerRect.left;
    titleEl.style.setProperty("left", `${mid}px`, "important");
  };
  centerTitleBetweenIcons();
  window.addEventListener("resize", centerTitleBetweenIcons);

    // ======================================================
  // HARD REFRESH BUTTON (bypass iOS PWA cache)
  // ======================================================
  // HARD REFRESH (works in iOS webapp)
const refreshBtn = host.querySelector("#hardRefreshBtn");
if (refreshBtn) {
  refreshBtn.addEventListener("click", () => {
    const url = new URL(window.location.href);

    // Remove old cache-busters so it stays clean
    url.searchParams.delete("v");
    url.searchParams.delete("refresh");

    // Add a new cache-buster
    url.searchParams.set("v", String(Date.now()));

    // iOS webapp: replace() is more reliable than reload()
    window.location.replace(url.toString());
  });
}



})();

