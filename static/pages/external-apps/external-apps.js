const EXTERNAL_APPS = [
  {
    id: "kwgt_android",
    platform: "android",
    name: "KWGT",
    url: "https://play.google.com/store/apps/details?id=org.kustom.widget&hl=en-US",
    description: "Custom widget builder for Android. Use it to place and run your finance widget on your home screen.",
  },
  {
    id: "pushover_android",
    platform: "android",
    name: "Pushover",
    url: "https://play.google.com/store/apps/details?id=net.superblock.pushover&pli=1",
    description: "Push notification app for Android. Use it to receive alerts from your account.",
  },
  {
    id: "scriptable_ios",
    platform: "ios",
    name: "Scriptable",
    url: "https://apps.apple.com/us/app/scriptable/id1405459188",
    description: "Automation app for iPhone. Use it to run the widget script that displays your finance data.",
  },
  {
    id: "pushover_ios",
    platform: "ios",
    name: "Pushover",
    url: "https://apps.apple.com/us/app/pushover-notifications/id506088175",
    description: "Push notification app for iPhone. Use it to receive alerts from your account.",
  },
];

function detectClientPlatform() {
  const ua = String(navigator.userAgent || "");
  if (/Android/i.test(ua)) return "android";
  if (/iPhone|iPad|iPod/i.test(ua)) return "ios";
  return "desktop";
}

async function loadIsOwner() {
  try {
    const res = await fetch("/settings/view-flags", { cache: "no-store", credentials: "same-origin" });
    if (!res.ok) return false;
    const out = await res.json().catch(() => ({}));
    return !!out?.is_owner;
  } catch (_) {
    return false;
  }
}

function renderAppList(items) {
  const host = document.getElementById("externalAppsList");
  if (!host) return;
  if (!items.length) {
    host.innerHTML = "";
    return;
  }
  host.innerHTML = items.map((app) => `
    <article class="external-apps-item">
      <div class="external-apps-head">
        <div class="external-apps-title">${app.name}</div>
        <div class="external-apps-platform">${app.platform}</div>
      </div>
      <p class="settings-muted external-apps-desc">${app.description}</p>
      <div class="external-apps-actions">
        <a class="settings-btn primary" href="${app.url}" target="_blank" rel="noopener noreferrer">Open Store</a>
      </div>
    </article>
  `).join("");
}

function applyExternalAppsVisibility(platform, isOwner) {
  const listSection = document.getElementById("externalAppsListSection");
  const unavailable = document.getElementById("externalAppsUnavailable");
  const intro = document.getElementById("externalAppsIntro");
  if (!listSection || !unavailable || !intro) return;

  if (platform === "desktop" && !isOwner) {
    listSection.style.display = "none";
    unavailable.style.display = "";
    intro.textContent = "External app downloads are shown on mobile only.";
    return;
  }

  listSection.style.display = "";
  unavailable.style.display = "none";

  if (platform === "android") {
    intro.textContent = "Android setup: install the apps below for widget rendering and push alerts.";
    renderAppList(EXTERNAL_APPS.filter((a) => a.platform === "android"));
    return;
  }
  if (platform === "ios") {
    intro.textContent = "iOS setup: install the apps below for widget rendering and push alerts.";
    renderAppList(EXTERNAL_APPS.filter((a) => a.platform === "ios"));
    return;
  }

  intro.textContent = "Admin desktop view: review all required mobile apps.";
  renderAppList(EXTERNAL_APPS);
}

document.addEventListener("DOMContentLoaded", async () => {
  const platform = detectClientPlatform();
  const isOwner = await loadIsOwner();
  applyExternalAppsVisibility(platform, isOwner);
});
