// /static/topBar.js
(async function () {
  const host = document.getElementById("topBar");
  if (!host) return;

  // 1) Inject shared top bar markup
  const res = await fetch("/static/partials/top-bar.html", { cache: "no-store" });
  if (!res.ok) {
    console.error("Failed to load top bar:", res.status);
    return;
  }
  host.innerHTML = await res.text();

  // 2) Title: prefer body[data-page-title], else document.title, else fallback
  const titleEl = host.querySelector("#topBarTitle");
  const bodyTitle = document.body?.dataset?.pageTitle;
  if (titleEl) titleEl.textContent = bodyTitle || document.title || "Page";

  // 3) Back button: ONLY show on pages not reachable from bottom tabs
  const path = window.location.pathname || "";

  // These are the pages you can access from bottom tabs (NO back button)
  const tabPaths = new Set([
    "/", // Home
    "/static/spending.html",
    "/static/all-transactions.html",
    "/static/recurring.html",
    "/static/receipts.html",
  ]);

  const backBtn = host.querySelector("#topBarBack");

  const shouldShowBack = !tabPaths.has(path);
  if (backBtn) {
    backBtn.style.visibility = shouldShowBack ? "visible" : "hidden";

    backBtn.addEventListener("click", () => {
      // Prefer browser back if possible; otherwise go home
      if (window.history.length > 1) window.history.back();
      else window.location.href = "/";
    });
  }
})();
