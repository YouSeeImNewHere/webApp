// /static/shared/topBar.js
(async function () {
  const host = document.getElementById("topBar");
  if (!host) return;
  // If shared.html already contains top bar markup, skip fetch.
  if (!host.querySelector("#topBarTitle")) {
    const v = (window.BUILD_ID ? `?v=${encodeURIComponent(window.BUILD_ID)}` : "");
    const res = await fetch(`/static/partials/top-bar.html${v}`, { cache: "force-cache" });
    if (!res.ok) {
      console.error("Failed to load top bar:", res.status);
      return;
    }
    host.innerHTML = await res.text();
  }

  // 2) Title: prefer body[data-page-title], else document.title, else fallback
  const titleEl = host.querySelector("#topBarTitle");
  const bodyTitle = document.body?.dataset?.pageTitle;
  if (titleEl) titleEl.textContent = bodyTitle || document.title || "Page";

  // Keep title centered between Settings and Notifications on mobile.
  const centerTitleBetweenIcons = () => {
    if (!titleEl) return;
    if (!window.matchMedia("(max-width: 900px)").matches) {
      titleEl.style.removeProperty("left");
      return;
    }
    const inner = host.querySelector(".top-bar-inner");
    const settingsBtn = inner?.querySelector('a.top-btn[href="/settings"]');
    const notifBtn = inner?.querySelector("#topBarNotif");
    if (!inner || !settingsBtn || !notifBtn) return;

    const innerRect = inner.getBoundingClientRect();
    const settingsRect = settingsBtn.getBoundingClientRect();
    const notifRect = notifBtn.getBoundingClientRect();
    const settingsCx = settingsRect.left + (settingsRect.width / 2);
    const notifCx = notifRect.left + (notifRect.width / 2);
    const mid = ((settingsCx + notifCx) / 2) - innerRect.left;
    titleEl.style.setProperty("left", `${mid}px`, "important");
  };
  centerTitleBetweenIcons();
  window.addEventListener("resize", centerTitleBetweenIcons);

  // Enforce consistent mobile icon styling even when a stale CSS bundle is cached.
  const applyMobileTopBtnStyles = () => {
    const mobile = window.matchMedia("(max-width: 900px)").matches;
    const btns = host.querySelectorAll(".top-bar .top-btn");
    btns.forEach((b) => {
      if (mobile) {
        b.style.setProperty("border", "0", "important");
        b.style.setProperty("background", "transparent", "important");
        b.style.setProperty("box-shadow", "none", "important");
        b.style.setProperty("border-radius", "0", "important");
        b.style.setProperty("width", "42px", "important");
        b.style.setProperty("height", "42px", "important");
        b.style.setProperty("font-size", "20px", "important");
      } else {
        b.style.removeProperty("border");
        b.style.removeProperty("background");
        b.style.removeProperty("box-shadow");
        b.style.removeProperty("border-radius");
        b.style.removeProperty("width");
        b.style.removeProperty("height");
        b.style.removeProperty("font-size");
      }
    });
  };
  applyMobileTopBtnStyles();
  window.addEventListener("resize", applyMobileTopBtnStyles);



})();

