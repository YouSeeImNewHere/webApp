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
})();

