let _lastWidgetScript = "";
let _lastAndroidWidgetUrl = "";

function detectClientPlatform() {
  const ua = String(navigator.userAgent || "");
  if (/Android/i.test(ua)) return "android";
  if (/iPhone|iPad|iPod/i.test(ua)) return "ios";
  return "desktop";
}

function money(n) {
  const v = Number(n || 0);
  return v.toLocaleString(undefined, { style: "currency", currency: "USD" });
}

function money0(n) {
  const v = Number(n || 0);
  return v.toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 0 });
}

async function copyToClipboard(text) {
  const val = String(text || "");
  if (!val) throw new Error("empty_text");

  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(val);
      return;
    } catch (_) {
      // Fall through to legacy selection-based copy path.
    }
  }

  const ta = document.createElement("textarea");
  ta.value = val;
  ta.setAttribute("readonly", "readonly");
  ta.style.position = "fixed";
  ta.style.top = "12px";
  ta.style.left = "12px";
  ta.style.width = "1px";
  ta.style.height = "1px";
  ta.style.opacity = "0.01";
  document.body.appendChild(ta);
  ta.focus();
  ta.select();
  ta.setSelectionRange(0, val.length);
  const ok = document.execCommand("copy");
  document.body.removeChild(ta);
  if (!ok) throw new Error("clipboard_copy_failed");
}

function selectManualCopyText() {
  const ta = document.getElementById("widgetManualCopyText");
  if (!ta) return;
  ta.focus();
  ta.select();
  ta.setSelectionRange(0, ta.value.length);
}

function openManualCopySheet(text) {
  const script = String(text || "");
  if (!script) return;

  let sheet = document.getElementById("widgetManualCopySheet");
  if (!sheet) {
    sheet = document.createElement("div");
    sheet.id = "widgetManualCopySheet";
    sheet.className = "widget-manual-copy-sheet";
    sheet.innerHTML = `
      <div class="widget-manual-copy-card">
        <div class="widget-manual-copy-title">Manual Copy (iPhone)</div>
        <div class="widget-manual-copy-sub">If auto-copy fails, tap Select All, then Copy.</div>
        <textarea id="widgetManualCopyText" readonly></textarea>
        <div class="widget-manual-copy-actions">
          <button type="button" class="settings-btn primary" id="widgetManualCopySelectAllBtn">Select All</button>
          <button type="button" class="settings-btn" id="widgetManualCopyTryCopyBtn">Try Copy</button>
          <button type="button" class="settings-btn" id="widgetManualCopyCloseBtn">Close</button>
        </div>
        <div id="widgetManualCopyStatus" class="settings-muted"></div>
      </div>
    `;
    document.body.appendChild(sheet);
    const closeBtn = sheet.querySelector("#widgetManualCopyCloseBtn");
    const selectBtn = sheet.querySelector("#widgetManualCopySelectAllBtn");
    const tryCopyBtn = sheet.querySelector("#widgetManualCopyTryCopyBtn");
    const statusEl = sheet.querySelector("#widgetManualCopyStatus");
    if (closeBtn) {
      closeBtn.addEventListener("click", () => sheet.classList.remove("open"));
    }
    if (selectBtn) {
      selectBtn.addEventListener("click", () => {
        selectManualCopyText();
        if (statusEl) statusEl.textContent = "Text selected.";
      });
    }
    if (tryCopyBtn) {
      tryCopyBtn.addEventListener("click", async () => {
        const val = String(sheet.querySelector("#widgetManualCopyText")?.value || "");
        if (!val) return;
        try {
          await copyToClipboard(val);
          if (statusEl) statusEl.textContent = "Copied.";
        } catch (_) {
          selectManualCopyText();
          if (statusEl) statusEl.textContent = "Copy blocked. Text selected for manual copy.";
        }
      });
    }
  }

  const ta = sheet.querySelector("#widgetManualCopyText");
  const statusEl = sheet.querySelector("#widgetManualCopyStatus");
  if (ta) {
    ta.value = script;
    selectManualCopyText();
  }
  if (statusEl) statusEl.textContent = "";
  sheet.classList.add("open");
}

async function fetchWidgetScript() {
  const res = await fetch("/settings/widget-script", { method: "POST" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const payload = await res.json();
  const script = String(payload.script || "");
  if (!script) throw new Error("script_missing");
  _lastWidgetScript = script;
  return script;
}

async function fetchWidgetToken() {
  const res = await fetch("/settings/widget-token", { method: "POST" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const payload = await res.json();
  const token = String(payload.widget_token || "").trim();
  if (!token) throw new Error("widget_token_missing");
  return token;
}

function buildAndroidWidgetUrlFromToken(token) {
  const base = `${window.location.origin}/widget/summary`;
  const qs = new URLSearchParams({
    widget_token: String(token || ""),
    widget_script_version: "3",
  });
  return `${base}?${qs.toString()}`;
}

function buildKwgtFormula(url, path) {
  return `$wg("${String(url || "")}", json, "${String(path || "")}")$`;
}

function fillAndroidFormulaSamples(url) {
  const today = document.getElementById("androidFormulaToday");
  const safe = document.getElementById("androidFormulaSafe");
  const daily = document.getElementById("androidFormulaDaily");
  const creditPct = document.getElementById("androidFormulaCreditPct");
  if (today) today.textContent = buildKwgtFormula(url, ".today.remaining_today");
  if (safe) safe.textContent = buildKwgtFormula(url, ".safe_to_spend");
  if (daily) daily.textContent = buildKwgtFormula(url, ".today.daily_limit");
  if (creditPct) creditPct.textContent = buildKwgtFormula(url, ".credit.pct");
}

function setAndroidWidgetStatus(msg) {
  const el = document.getElementById("androidWidgetStatus");
  if (el) el.textContent = String(msg || "");
}

function setAndroidWidgetUrl(url) {
  const el = document.getElementById("androidWidgetUrl");
  if (el) el.value = String(url || "");
  fillAndroidFormulaSamples(String(url || ""));
}

async function ensureAndroidWidgetUrl({ forceRotate = false } = {}) {
  if (_lastAndroidWidgetUrl && !forceRotate) return _lastAndroidWidgetUrl;
  const token = await fetchWidgetToken();
  _lastAndroidWidgetUrl = buildAndroidWidgetUrlFromToken(token);
  setAndroidWidgetUrl(_lastAndroidWidgetUrl);
  return _lastAndroidWidgetUrl;
}

async function verifyAndroidWidgetUrl(url) {
  const res = await fetch(String(url || ""), { cache: "no-store" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const payload = await res.json();
  if (!payload || payload.ok !== true) throw new Error("bad_payload");
  return payload;
}

function formatPreviewTime(d) {
  return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function clamp01(v) {
  const n = Number(v || 0);
  if (!Number.isFinite(n)) return 0;
  if (n < 0) return 0;
  if (n > 1) return 1;
  return n;
}

function setFillWidth(id, ratio) {
  const el = document.getElementById(id);
  if (!el) return;
  el.style.width = `${Math.round(clamp01(ratio) * 100)}%`;
}

async function loadWidgetPreview() {
  const updatedEl = document.getElementById("widgetPreviewUpdated");
  if (!updatedEl) return;

  updatedEl.textContent = "Loading...";
  try {
    const [monthRes, dayRes, bankRes] = await Promise.all([
      fetch("/month-budget", { cache: "no-store" }),
      fetch("/day-limit", { cache: "no-store" }),
      fetch("/bank-totals", { cache: "no-store" }),
    ]);
    if (!monthRes.ok || !dayRes.ok || !bankRes.ok) throw new Error("preview_fetch_failed");
    const month = await monthRes.json();
    const day = await dayRes.json();
    const bank = await bankRes.json();

    const safe = Number(month.safe_to_spend || 0);
    const monthGoal = Number(month.free_spend_goal || 0);
    const baseline = Number(day.baseline || 0);
    const leftToday = Number(day.remaining_today || 0);

    const creditAccounts = ((bank.credit || {}).accounts || []);
    let limitSum = 0;
    let usedSum = 0;
    for (const acc of creditAccounts) {
      const lim = Number(acc.credit_limit || 0);
      if (lim > 0) limitSum += lim;
      const bal = Number(acc.total || 0);
      usedSum += Math.max(0, -bal);
    }
    const capLimit = limitSum * 0.3;
    const creditPct = capLimit > 0 ? clamp01(usedSum / capLimit) : 0;
    const creditAvail = Math.max(0, capLimit - usedSum);
    const safePct = monthGoal > 0 ? clamp01(safe / monthGoal) : 0;
    const dayPct = baseline > 0 ? clamp01(leftToday / baseline) : 0;

    const setText = (id, value) => {
      const el = document.getElementById(id);
      if (el) el.textContent = value;
    };

    setText("widgetPreviewCreditPct", `${Math.round(creditPct * 100)}%`);
    setText("widgetPreviewCreditAvail", money(creditAvail));
    setText("widgetPreviewMonthGoal", money(monthGoal));
    setText("widgetPreviewSafeValue", money(safe));
    setText("widgetPreviewBaseline", money(baseline));
    setText("widgetPreviewToday", money(leftToday));
    setText("widgetPreviewChecking", money(((bank.checking || {}).total || 0)));
    setText("widgetPreviewSavings", money(((bank.savings || {}).total || 0)));

    setFillWidth("widgetPreviewCreditFill", creditPct);
    setFillWidth("widgetPreviewSafeFill", safePct);
    setFillWidth("widgetPreviewDayFill", dayPct);

    setText("widgetPreviewInline", `Left ${money0(leftToday)}`);
    setText("widgetPreviewCircular", money0(leftToday));
    setText("widgetPreviewRectToday", money(leftToday));
    setText("widgetPreviewRectPct", `${Math.round(creditPct * 100)}%`);
    setText("widgetPreviewRectBase", `Base ${money(baseline)}/day`);
    setText("widgetPreviewRectSafe", `Safe ${money(safe)}`);

    updatedEl.textContent = `Updated ${formatPreviewTime(new Date())}`;
  } catch (_) {
    const ids = [
      "widgetPreviewCreditPct",
      "widgetPreviewCreditAvail",
      "widgetPreviewMonthGoal",
      "widgetPreviewSafeValue",
      "widgetPreviewBaseline",
      "widgetPreviewToday",
      "widgetPreviewChecking",
      "widgetPreviewSavings",
      "widgetPreviewInline",
      "widgetPreviewCircular",
      "widgetPreviewRectToday",
      "widgetPreviewRectPct",
      "widgetPreviewRectBase",
      "widgetPreviewRectSafe",
    ];
    for (const id of ids) {
      const el = document.getElementById(id);
      if (el) el.textContent = "Unavailable";
    }
    setFillWidth("widgetPreviewCreditFill", 0);
    setFillWidth("widgetPreviewSafeFill", 0);
    setFillWidth("widgetPreviewDayFill", 0);
    updatedEl.textContent = "Retry";
  }
}

function bindWidgetActions() {
  const copyBtn = document.getElementById("copyWidgetCodeBtn");
  const refreshBtn = document.getElementById("refreshWidgetPreviewBtn");
  const statusEl = document.getElementById("widgetCodeStatus");

  if (refreshBtn) {
    refreshBtn.addEventListener("click", () => {
      loadWidgetPreview().catch(() => {});
    });
  }

  if (!copyBtn) return;
  copyBtn.addEventListener("click", async () => {
    copyBtn.disabled = true;
    if (statusEl) statusEl.textContent = "Preparing code...";
    try {
      let script = _lastWidgetScript;
      if (!script) script = await fetchWidgetScript();
      await copyToClipboard(script);
      if (statusEl) statusEl.textContent = "Copied. Paste into Scriptable as a new script.";
      // Refresh token/script in the background for the next copy without blocking user gesture copy.
      fetchWidgetScript().catch(() => {});
    } catch (_) {
      try {
        const fallbackScript = _lastWidgetScript || await fetchWidgetScript();
        openManualCopySheet(fallbackScript);
        if (statusEl) statusEl.textContent = "Clipboard was blocked. Manual copy tools opened.";
      } catch (_) {
        if (statusEl) statusEl.textContent = "Failed to prepare widget code.";
      }
    } finally {
      copyBtn.disabled = false;
    }
  });
}

function bindAndroidWidgetActions() {
  const generateBtn = document.getElementById("androidWidgetGenerateBtn");
  const regenerateBtn = document.getElementById("androidWidgetRegenerateBtn");
  const openBtn = document.getElementById("androidWidgetOpenBtn");
  const formulaButtons = Array.from(document.querySelectorAll("[data-copy-formula]"));

  const withBusy = async (btn, fn) => {
    if (!btn) return fn();
    btn.disabled = true;
    try {
      await fn();
    } finally {
      btn.disabled = false;
    }
  };

  if (generateBtn) {
    generateBtn.addEventListener("click", () => withBusy(generateBtn, async () => {
      setAndroidWidgetStatus("Generating secure URL...");
      try {
        const url = await ensureAndroidWidgetUrl({ forceRotate: false });
        await copyToClipboard(url);
        const check = await verifyAndroidWidgetUrl(url);
        const tail = check?.warming ? " (cache warming, retry in a few seconds)." : ".";
        setAndroidWidgetStatus(`Copied data URL. KWGT can connect${tail}`);
      } catch (err) {
        console.error(err);
        setAndroidWidgetStatus("Failed to generate/copy URL.");
      }
    }));
  }

  if (regenerateBtn) {
    regenerateBtn.addEventListener("click", () => withBusy(regenerateBtn, async () => {
      setAndroidWidgetStatus("Regenerating token...");
      try {
        const url = await ensureAndroidWidgetUrl({ forceRotate: true });
        await copyToClipboard(url);
        setAndroidWidgetStatus("Token rotated. New URL copied. Update existing KWGT formulas.");
      } catch (err) {
        console.error(err);
        setAndroidWidgetStatus("Failed to rotate token.");
      }
    }));
  }

  if (openBtn) {
    openBtn.addEventListener("click", async () => {
      try {
        const url = await ensureAndroidWidgetUrl({ forceRotate: false });
        window.open(url, "_blank", "noopener,noreferrer");
      } catch (err) {
        console.error(err);
        setAndroidWidgetStatus("Generate URL first.");
      }
    });
  }

  formulaButtons.forEach((btn) => {
    btn.addEventListener("click", async () => {
      const kind = String(btn.getAttribute("data-copy-formula") || "");
      const pathByKind = {
        today: ".today.remaining_today",
        safe: ".safe_to_spend",
        daily: ".today.daily_limit",
        credit_pct: ".credit.pct",
      };
      const path = pathByKind[kind];
      if (!path) return;
      try {
        const url = await ensureAndroidWidgetUrl({ forceRotate: false });
        await copyToClipboard(buildKwgtFormula(url, path));
        setAndroidWidgetStatus(`Copied formula: ${path}`);
      } catch (err) {
        console.error(err);
        setAndroidWidgetStatus("Failed to copy formula.");
      }
    });
  });
}

function setActivePlatform(platform) {
  const tabs = Array.from(document.querySelectorAll(".widget-platform-tab"));
  const panes = Array.from(document.querySelectorAll("[data-platform-pane]"));

  tabs.forEach((t) => {
    const isActive = t.getAttribute("data-platform") === platform;
    t.classList.toggle("active", isActive);
    t.setAttribute("aria-selected", isActive ? "true" : "false");
  });

  panes.forEach((p) => {
    const isActive = p.getAttribute("data-platform-pane") === platform;
    p.classList.toggle("hidden", !isActive);
  });

  if (platform === "ios") {
    loadWidgetPreview().catch(() => {});
  }
}

function bindPlatformTabs() {
  const tabs = Array.from(document.querySelectorAll(".widget-platform-tab"));
  tabs.forEach((t) => {
    t.addEventListener("click", () => {
      setActivePlatform(t.getAttribute("data-platform") || "ios");
    });
  });
}

function initPlatformView() {
  const params = new URLSearchParams(window.location.search);
  const requested = String(params.get("platform") || "").toLowerCase();
  const requestedPlatform = requested === "ios" || requested === "android" ? requested : "";
  const detected = detectClientPlatform();
  const lockedPlatform = requestedPlatform || (detected === "ios" || detected === "android" ? detected : "");

  if (lockedPlatform) {
    const switcher = document.getElementById("widgetPlatformSwitcherSection");
    if (switcher) switcher.style.display = "none";
    setActivePlatform(lockedPlatform);
    return lockedPlatform;
  }

  setActivePlatform("ios");
  return "";
}

document.addEventListener("DOMContentLoaded", () => {
  const lockedPlatform = initPlatformView();
  if (!lockedPlatform) bindPlatformTabs();
  bindWidgetActions();
  bindAndroidWidgetActions();
});
