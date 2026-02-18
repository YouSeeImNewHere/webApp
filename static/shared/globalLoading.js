(() => {
  let inflight = 0;
  let progress = 0;
  let progressTimer = null;

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
    if (!document.getElementById("global-progress")) {
      const bar = document.createElement("div");
      bar.id = "global-progress";
      bar.className = "global-progress hidden";
      bar.innerHTML = `<div id="global-progress-fill" class="global-progress__fill"></div>`;
      document.body.appendChild(bar);
    }
    mountProgressBar();

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

  function mountProgressBar() {
    const bar = document.getElementById("global-progress");
    if (!bar) return;

    const tabs = document.querySelector("#bottomTabs .mobile-tabs, .mobile-tabs");
    if (tabs) {
      if (bar.parentElement !== tabs) tabs.appendChild(bar);
      bar.classList.add("global-progress--tabs");
      return;
    }

    if (bar.parentElement !== document.body) document.body.appendChild(bar);
    bar.classList.remove("global-progress--tabs");
  }

  function setProgress(value) {
    const pct = Math.max(0, Math.min(100, value));
    progress = pct;
    const fill = document.getElementById("global-progress-fill");
    if (fill) fill.style.width = `${pct}%`;
  }

  function startProgress() {
    mountProgressBar();
    const bar = document.getElementById("global-progress");
    if (!bar) return;
    bar.classList.remove("hidden");

    if (progressTimer) return;
    if (progress <= 0 || progress >= 95) setProgress(8);

    progressTimer = setInterval(() => {
      if (inflight <= 0) return;
      const remaining = 95 - progress;
      if (remaining <= 0) return;
      const step = Math.max(0.4, remaining * 0.08);
      setProgress(progress + step);
    }, 140);
  }

  function completeProgress() {
    const bar = document.getElementById("global-progress");
    if (!bar) return;

    if (progressTimer) {
      clearInterval(progressTimer);
      progressTimer = null;
    }

    setProgress(100);
    setTimeout(() => {
      bar.classList.add("hidden");
      setProgress(0);
    }, 220);
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
      startProgress();
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
        if (inflight === 0) completeProgress();
      }
    }
  };
})();
