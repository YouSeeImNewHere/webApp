let _monthBudgetSnapshot = null;
let _lastWidgetScript = "";

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
    await navigator.clipboard.writeText(val);
    return;
  }

  const ta = document.createElement("textarea");
  ta.value = val;
  ta.setAttribute("readonly", "readonly");
  ta.style.position = "fixed";
  ta.style.top = "-1000px";
  ta.style.left = "-1000px";
  document.body.appendChild(ta);
  ta.focus();
  ta.select();
  const ok = document.execCommand("copy");
  document.body.removeChild(ta);
  if (!ok) throw new Error("clipboard_copy_failed");
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
        <div class="widget-manual-copy-sub">Press and hold inside the text, then tap Select All and Copy.</div>
        <textarea id="widgetManualCopyText" readonly></textarea>
        <div class="settings-row">
          <button type="button" class="settings-btn" id="widgetManualCopyCloseBtn">Close</button>
        </div>
      </div>
    `;
    document.body.appendChild(sheet);
    sheet.querySelector("#widgetManualCopyCloseBtn")?.addEventListener("click", () => {
      sheet?.classList.remove("open");
    });
  }

  const ta = sheet.querySelector("#widgetManualCopyText");
  if (ta) {
    ta.value = script;
    ta.focus();
    ta.setSelectionRange(0, Math.min(script.length, 65535));
  }
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
    if (statusEl) statusEl.textContent = "Generating code...";
    try {
      const script = await fetchWidgetScript();
      await copyToClipboard(script);
      if (statusEl) statusEl.textContent = "Copied. Paste into Scriptable as a new script.";
    } catch (err) {
      try {
        const fallbackScript = _lastWidgetScript || await fetchWidgetScript();
        openManualCopySheet(fallbackScript);
        if (statusEl) statusEl.textContent = "iPhone blocked clipboard. Manual copy sheet opened.";
      } catch (_) {
        if (statusEl) statusEl.textContent = "Failed to prepare widget code.";
      }
    } finally {
      copyBtn.disabled = false;
    }
  });
}

function readPointValue(id, fallback) {
  const raw = (document.getElementById(id)?.value || "").trim();
  const n = Number(raw);
  if (!Number.isFinite(n) || n <= 0) return fallback;
  return Math.max(1, Math.round(n));
}

function renderDailyWeightsPreview() {
  const el = document.getElementById("dailyWeightsPreview");
  if (!el || !_monthBudgetSnapshot) return;

  const weekdayPoints = readPointValue("weekdayPoints", 1);
  const weekendPoints = readPointValue("weekendPoints", 2);

  const safe = Number(_monthBudgetSnapshot.safe_to_spend || 0);
  const weekdayDays = Number(_monthBudgetSnapshot.weekday_days_left || 0);
  const weekendDays = Number(_monthBudgetSnapshot.weekend_days_left || 0);
  const totalPoints = (weekdayDays * weekdayPoints) + (weekendDays * weekendPoints);
  const pointValue = totalPoints > 0 ? (safe / totalPoints) : 0;
  const weekdayLimit = pointValue * weekdayPoints;
  const weekendLimit = pointValue * weekendPoints;

  const todayDow = new Date().getDay(); // 0=Sun..6=Sat
  const isWeekendToday = (todayDow === 0 || todayDow === 6);
  const todayLimit = isWeekendToday ? weekendLimit : weekdayLimit;

  el.textContent =
    `Safe to spend: ${money(safe)}\n` +
    `Days left: ${weekdayDays} weekday, ${weekendDays} weekend\n` +
    `Weekday limit: ${money(weekdayLimit)}\n` +
    `Weekend limit: ${money(weekendLimit)}\n` +
    `Today (${isWeekendToday ? "weekend" : "weekday"}) limit: ${money(todayLimit)}`;
}

async function loadDailyWeightsSettings() {
  const statusEl = document.getElementById("dailyWeightsStatus");
  const weekdayEl = document.getElementById("weekdayPoints");
  const weekendEl = document.getElementById("weekendPoints");
  const saveBtn = document.getElementById("saveDailyWeightsBtn");
  if (!weekdayEl || !weekendEl || !saveBtn) return;

  try {
    const [weightsRes, budgetRes] = await Promise.all([
      fetch("/settings/daily-weights", { cache: "no-store" }),
      fetch("/month-budget", { cache: "no-store" }),
    ]);

    if (weightsRes.ok) {
      const w = await weightsRes.json();
      weekdayEl.value = String(Math.max(1, Math.round(Number(w.weekday_points || 1))));
      weekendEl.value = String(Math.max(1, Math.round(Number(w.weekend_points || 2))));
    }

    if (budgetRes.ok) {
      _monthBudgetSnapshot = await budgetRes.json();
    }

    renderDailyWeightsPreview();
  } catch (err) {
    if (statusEl) statusEl.textContent = "Failed to load daily weight settings.";
  }

  const onInput = () => renderDailyWeightsPreview();
  const onBlurNormalize = (el, fallback) => {
    if (!el) return;
    el.value = String(readPointValue(el.id, fallback));
  };
  weekdayEl.addEventListener("input", onInput);
  weekdayEl.addEventListener("change", onInput);
  weekdayEl.addEventListener("blur", () => onBlurNormalize(weekdayEl, 1));
  weekendEl.addEventListener("input", onInput);
  weekendEl.addEventListener("change", onInput);
  weekendEl.addEventListener("blur", () => onBlurNormalize(weekendEl, 2));

  saveBtn.addEventListener("click", async () => {
    const weekdayPoints = readPointValue("weekdayPoints", 1);
    const weekendPoints = readPointValue("weekendPoints", 2);
    saveBtn.disabled = true;
    if (statusEl) statusEl.textContent = "Saving...";
    try {
      const res = await fetch("/settings/daily-weights", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ weekday_points: weekdayPoints, weekend_points: weekendPoints }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await fetch("/day-limit?recalc=1", { cache: "no-store" });
      if (statusEl) statusEl.textContent = "Saved.";
      setTimeout(() => {
        if (statusEl) statusEl.textContent = "";
      }, 1500);
    } catch (err) {
      if (statusEl) statusEl.textContent = "Failed to save.";
    } finally {
      saveBtn.disabled = false;
    }
  });
}

document.addEventListener("DOMContentLoaded", () => {
  if (window.Profile) {
    window.Profile.mountEditor("#lesProfileMount");
  } else {
    console.error("Profile failed to load");
  }

  const btn = document.getElementById("resetHomeLayoutBtn");
  if (btn && window.LayoutStore) {
    btn.addEventListener("click", async () => {
      const msg = document.getElementById("layoutMsg");
      if (msg) msg.textContent = "Resetting...";
      await window.LayoutStore.save("home", {});
      if (msg) msg.textContent = "Reset";
      setTimeout(() => {
        if (msg) msg.textContent = "";
      }, 1500);
    });
  }

  const sel = document.getElementById("themeSelect");
  if (sel && window.Theme) {
    sel.value = window.Theme.get();
    sel.addEventListener("change", () => window.Theme.set(sel.value));
  }

  loadDailyWeightsSettings().catch((err) => console.error(err));
  loadWidgetPreview().catch((err) => console.error(err));
  bindWidgetActions();
});
