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

  // 2) Compute active tab (same logic you had in home.html)
  const path = window.location.pathname || "";

  let active = "home";
  if (path.includes("all-transactions.html")) active = "all";
  else if (path.includes("recurring.html")) active = "recurring";
  else if (path.includes("spending.html")) active = "spending";
  else active = "home";

  // 3) Apply active class
  const tab = host.querySelector(`.mobile-tab[data-tab="${active}"]`);
  if (tab) tab.classList.add("active");
})();
