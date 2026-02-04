(() => {
  let inflight = 0;

  const SILENT_ENDPOINTS = [
    "/notifications/unread-count",
  ];

  function isSilentRequest(input) {
    const url =
      typeof input === "string"
        ? input
        : input && input.url
        ? input.url
        : "";
    return SILENT_ENDPOINTS.some(p => url.includes(p));
  }

  function ensureUI() {
    if (!document.getElementById("global-loader")) {
      const loader = document.createElement("div");
      loader.id = "global-loader";
      loader.className = "loader hidden";
      loader.innerHTML = `<div class="spinner"></div>`;
      document.body.appendChild(loader);
    }

    if (!document.getElementById("global-error")) {
      const err = document.createElement("div");
      err.id = "global-error";
      err.className = "error hidden";
      err.title = "Failed to load";
      err.textContent = "⚠️";
      // do NOT auto-refresh
      err.addEventListener("click", () => err.classList.add("hidden"));
      document.body.appendChild(err);
    }
  }

  function showLoader() {
    document.getElementById("global-loader")?.classList.remove("hidden");
  }

  function hideLoader() {
    document.getElementById("global-loader")?.classList.add("hidden");
  }

  function showError() {
    document.getElementById("global-error")?.classList.remove("hidden");
  }

  function hideError() {
    document.getElementById("global-error")?.classList.add("hidden");
  }

  const origFetch = window.fetch.bind(window);

  window.fetch = async (...args) => {
    const silent = isSilentRequest(args[0]);

    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", ensureUI, { once: true });
    } else {
      ensureUI();
    }

    if (!silent) {
      inflight++;
      hideError();
      showLoader();
    }

    try {
      const res = await origFetch(...args);

      if (!silent && !res.ok) showError();

      return res;
    } catch (e) {
      if (!silent) showError();
      throw e;
    } finally {
      if (!silent) {
        inflight = Math.max(0, inflight - 1);
        if (inflight === 0) hideLoader();
      }
    }
  };
})();
