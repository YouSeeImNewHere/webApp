// /static/theme.js
(function () {
  const KEY = "theme"; // "light" | "dark" | "system"
  const root = document.documentElement;

  function getSystemTheme() {
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  }

  function applyTheme(mode) {
    const theme = (mode === "system") ? getSystemTheme() : mode;
    if (theme === "dark") root.setAttribute("data-theme", "dark");
    else root.removeAttribute("data-theme");

    // optional: update browser UI color on mobile
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", theme === "dark" ? "#0b0d10" : "#ffffff");
  }

  const saved = localStorage.getItem(KEY) || "system";
  applyTheme(saved);

  // Keep in sync if user chose "system"
  if (saved === "system" && window.matchMedia) {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    mq.addEventListener?.("change", () => applyTheme("system"));
  }

  // expose setter for settings page
  window.Theme = {
    get: () => localStorage.getItem(KEY) || "system",
    set: (mode) => {
      localStorage.setItem(KEY, mode);
      applyTheme(mode);
    }
  };
})();
