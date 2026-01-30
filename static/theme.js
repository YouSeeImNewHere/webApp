// /static/theme.js
(function () {
  const KEY = "theme";
  const root = document.documentElement;

  function getSystemTheme() {
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  }

  function applyTheme(mode) {
    const m = (mode || "system").toLowerCase();

    // Used only for mobile browser UI tinting
    const resolved = (m === "system") ? getSystemTheme() : m;

    // Apply:
    // - system => no attribute (default tokens)
    // - light  => no attribute (default tokens)
    // - anything else => data-theme = that exact value (dark/solarized/forest/midnight/etc)
    if (m === "system" || m === "light") {
      root.removeAttribute("data-theme");
    } else {
      root.setAttribute("data-theme", m);
    }

    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", resolved === "dark" ? "#0b0d10" : "#ffffff");
  }

  const saved = (localStorage.getItem(KEY) || "system").toLowerCase();
  applyTheme(saved);

  // Keep in sync if user chose "system"
  if (saved === "system" && window.matchMedia) {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    mq.addEventListener?.("change", () => applyTheme("system"));
  }

  window.Theme = {
    get: () => (localStorage.getItem(KEY) || "system").toLowerCase(),
    set: (mode) => {
      localStorage.setItem(KEY, mode);
      applyTheme(mode);
    }
  };
})();
