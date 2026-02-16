// /static/shared/bottomTabs.js
(async function () {
  const host = document.getElementById("bottomTabs");
  if (!host) return;
  // If shared.html already contains tab markup, skip fetch.
  if (!host.querySelector(".mobile-tab")) {
    const v = (window.BUILD_ID ? `?v=${encodeURIComponent(window.BUILD_ID)}` : "");
    const res = await fetch(`/static/partials/bottom-tabs.html${v}`, { cache: "force-cache" });
    if (!res.ok) {
      console.error("Failed to load bottom tabs:", res.status);
      return;
    }
    host.innerHTML = await res.text();
  }

  // 2) Compute active tab
  const path = window.location.pathname || "";

  let active = null;
  if (path === "/") active = "home";
  else if (path.includes("spending.html")) active = "spending";
  else if (path.includes("all-transactions.html")) active = "all";
  else if (path.includes("pages/recurring/recurring.html") || path.includes("recurring.html")) active = "recurring";
  else if (path.includes("receipts.html")) active = "receipts";
  // NOTE: Settings is NOT a bottom tab anymore → no active tab on /settings

  // 3) Apply active class
  if (active) {
    const tab = host.querySelector(`.mobile-tab[data-tab="${active}"]`);
    if (tab) tab.classList.add("active");
  }
})();

