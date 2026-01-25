// /static/layout.js
// Loads/saves UI layout JSON to the backend.
//
// Backend contract:
//   GET  /ui-layout?key=<key> -> { "key": "<key>", "layout": {...} } (404 if missing is OK)
//   POST /ui-layout           -> { "key": "<key>", "layout": {...} }

(function () {
  function deepMerge(defaults, incoming) {
    if (!incoming || typeof incoming !== "object") return structuredClone(defaults);

    const out = structuredClone(defaults);

    for (const [k, v] of Object.entries(incoming)) {
      if (Array.isArray(v)) {
        out[k] = v.slice();
      } else if (v && typeof v === "object") {
        out[k] = { ...(out[k] || {}), ...v };
      } else {
        out[k] = v;
      }
    }
    return out;
  }

  async function load(key, defaults) {
    const def = defaults || {};
    try {
      const res = await fetch(`/ui-layout?key=${encodeURIComponent(key)}`, {
        method: "GET",
        headers: { "Accept": "application/json" }
      });

      if (res.status === 404) return structuredClone(def);
      if (!res.ok) throw new Error(`GET /ui-layout failed: ${res.status}`);

      const data = await res.json();
      const incoming = data?.layout ?? data; // accept either shape
      const merged = deepMerge(def, incoming);

      if (!merged.bank_account_order) merged.bank_account_order = {};
      return merged;
    } catch (err) {
      console.warn("LayoutStore.load fallback to defaults:", err);
      return structuredClone(def);
    }
  }

  async function save(key, layout) {
    try {
      const res = await fetch(`/ui-layout`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Accept": "application/json" },
        body: JSON.stringify({ key, layout })
      });
      if (!res.ok) throw new Error(`POST /ui-layout failed: ${res.status}`);
      const data = await res.json();
      return data?.layout ?? layout;
    } catch (err) {
      console.error("LayoutStore.save failed:", err);
      return layout; // keep UI usable even if save fails
    }
  }

  window.LayoutStore = { load, save };
})();
