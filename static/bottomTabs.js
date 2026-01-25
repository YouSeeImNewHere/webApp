// /static/bottomTabs.js
(async function () {
  const host = document.getElementById("bottomTabs");
  if (!host) return;

  // 1) Inject shared tabs markup
  const res = await fetch("/static/partials/bottom-tabs.html", { cache: "no-store" });
  if (!res.ok) {
    console.error("Failed to load bottom tabs:", res.status);
    return;
  }
  host.innerHTML = await res.text();

  // 2) Compute active tab
  const path = window.location.pathname || "";

  let active = null;
  if (path === "/") active = "home";
  else if (path.includes("spending.html")) active = "spending";
  else if (path.includes("all-transactions.html")) active = "all";
  else if (path.includes("recurring.html")) active = "recurring";
  else if (path.includes("receipts.html")) active = "receipts";
  // NOTE: Settings is NOT a bottom tab anymore → no active tab on /settings

  // 3) Apply active class
  if (active) {
    const tab = host.querySelector(`.mobile-tab[data-tab="${active}"]`);
    if (tab) tab.classList.add("active");
  }
})();
