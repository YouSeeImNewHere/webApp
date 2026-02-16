// /static/shared/shared.js
(async function () {
  const v = (window.BUILD_ID ? `?v=${encodeURIComponent(window.BUILD_ID)}` : "");

  // 1) Load shared chrome HTML
  const res = await fetch(`/static/shared/shared.html${v}`, { cache: "force-cache" });
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

  // 4) Load your existing shared behavior
  try {
    await loadScript("/static/topBar.js");
    await loadScript("/static/bottomTabs.js");
    await loadScript("/static/notifs.js");
  } catch (e) {
    console.error("Failed loading shared scripts", e);
  }
})();
