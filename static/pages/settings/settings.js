let _monthBudgetSnapshot = null;
let _lastWidgetScript = "";
let _notifSaveTimer = null;

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
    const closeBtn = sheet.querySelector("#widgetManualCopyCloseBtn");
    if (closeBtn) {
      closeBtn.addEventListener("click", () => {
        if (sheet) sheet.classList.remove("open");
      });
    }
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
  const input = document.getElementById(id);
  const raw = String((input && input.value) || "").trim();
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

function formatBackfillLog(out) {
  const summary = out?.summary || {};
  const rows = Array.isArray(out?.rows) ? out.rows : [];
  const head = [
    `lookback_days=${Number(summary.lookback_days || 0)}`,
    `fetched=${Number(summary.fetched || 0)}`,
    `matched=${Number(summary.matched || 0)}`,
    `inserted=${Number(summary.inserted || 0)}`,
    `notified=${Number(summary.notified || 0)}`,
    `skipped=${Number(summary.skipped || 0)}`,
  ].join(" | ");
  const body = rows.map((r) => {
    const ext = r && r.extracted ? r.extracted : null;
    const ex = ext
      ? `amount=${ext.amount} merchant=${ext.merchant} date=${ext.date} time=${ext.time} account_id=${ext.account_id}`
      : "extracted=none";
    return [
      `${r.matched ? "MATCH" : "SKIP"} | inserted=${!!r.inserted} | notified=${!!r.notified} | reason=${r.reason || ""}`,
      `${r.subject || "(no subject)"}`,
      `${r.sender || ""}`,
      ex,
    ].join("\n");
  }).join("\n\n");
  return body ? `${head}\n\n${body}` : `${head}\n\n(no rows)`;
}

function esc(v) {
  return String(v == null ? "" : v)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function renderBackfillRows(out) {
  const host = document.getElementById("emailParserBackfillRows");
  if (!host) return;
  const rows = Array.isArray(out?.rows) ? out.rows : [];
  if (!rows.length) {
    host.innerHTML = "";
    host.style.display = "none";
    return;
  }
  const parts = [];
  for (let i = 0; i < rows.length; i += 1) {
    const r = rows[i] || {};
    const idx = i + 1;
    const cls = r.matched ? "match" : "skip";
    const reason = esc(r.reason || "");
    const hdr = `${r.matched ? "MATCH" : "SKIP"} | inserted=${!!r.inserted} | notified=${!!r.notified}`;
    const body = esc(r.body_excerpt || "");
    const attempts = Array.isArray(r.attempted_parsers) ? r.attempted_parsers : [];
    const attemptsText = attempts.length
      ? attempts.map((a) => [
        `draft_id=${a.draft_id || 0}`,
        `sender_matched=${!!a.sender_matched}`,
        `subject_contains=${a.subject_contains || ""}`,
        `sender_pattern=${a.sender_pattern || ""}`,
        `regex=${a.regex || ""}`,
      ].join(" | ")).join("\n\n")
      : "No parser attempts recorded.";
    parts.push(`
      <div class="backfill-row ${cls}">
        <div class="backfill-row-top">
          <div class="backfill-row-title">#${idx} ${esc(hdr)}</div>
          <div class="backfill-row-reason">${reason}</div>
        </div>
        <div class="backfill-row-meta">${esc(r.subject || "(no subject)")}</div>
        <div class="backfill-row-meta">${esc(r.sender || "")}</div>
        <div class="backfill-row-actions">
          <button type="button" class="settings-btn" data-toggle="body-${idx}">View body</button>
          <button type="button" class="settings-btn" data-toggle="attempts-${idx}">View parser attempts</button>
        </div>
        <pre id="body-${idx}" class="settings-code backfill-detail" style="display:none;">${body}</pre>
        <pre id="attempts-${idx}" class="settings-code backfill-detail" style="display:none;">${esc(attemptsText)}</pre>
      </div>
    `);
  }
  host.innerHTML = parts.join("");
  host.style.display = "";
  host.querySelectorAll("button[data-toggle]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = btn.getAttribute("data-toggle");
      if (!id) return;
      const target = document.getElementById(id);
      if (!target) return;
      target.style.display = target.style.display === "none" ? "" : "none";
    });
  });
}

function bindEmailParserBackfill() {
  const btn = document.getElementById("runEmailParserBackfillBtn");
  const daysEl = document.getElementById("emailParserBackfillDays");
  const includeEl = document.getElementById("emailParserIncludeProcessed");
  const statusEl = document.getElementById("emailParserBackfillStatus");
  const logEl = document.getElementById("emailParserBackfillLog");
  const rowsEl = document.getElementById("emailParserBackfillRows");
  if (!btn || !daysEl || !includeEl || !statusEl || !logEl) return;

  btn.addEventListener("click", async () => {
    const daysRaw = Number(daysEl.value || 7);
    const days = Math.max(1, Math.min(60, Number.isFinite(daysRaw) ? Math.trunc(daysRaw) : 7));
    daysEl.value = String(days);
    const includeProcessed = !!includeEl.checked;
    btn.disabled = true;
    statusEl.textContent = "Running parser backfill...";
    logEl.style.display = "none";
    logEl.textContent = "";
    if (rowsEl) {
      rowsEl.innerHTML = "";
      rowsEl.style.display = "none";
    }
    try {
      const res = await fetch("/settings/email-parser/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ days, include_processed: includeProcessed, max_emails: 5000 }),
      });
      const out = await res.json().catch(() => ({}));
      if (!res.ok || !out?.ok) {
        const detail = out?.detail || `HTTP ${res.status}`;
        throw new Error(String(detail));
      }
      statusEl.textContent = "Backfill complete.";
      logEl.textContent = formatBackfillLog(out);
      logEl.style.display = "";
      renderBackfillRows(out);
    } catch (err) {
      statusEl.textContent = `Backfill failed: ${err?.message || err}`;
    } finally {
      btn.disabled = false;
      loadInitialSetupProgress().catch(() => {});
    }
  });
}

function renderInitialSetupProgress(out) {
  const pct = Math.max(0, Math.min(100, Number(out?.percent || 0)));
  const counts = out?.counts || {};
  const fillEl = document.getElementById("initialSetupProgressFill");
  const textEl = document.getElementById("initialSetupProgressText");
  const subEl = document.getElementById("initialSetupProgressSub");
  const trackEl = document.querySelector(".setup-progress-track");
  if (fillEl) fillEl.style.width = `${pct}%`;
  if (trackEl) trackEl.setAttribute("aria-valuenow", String(pct));
  if (textEl) {
    textEl.textContent = `${pct}% complete (${Number(counts.requirements_done || 0)}/${Number(counts.requirements_total || 0)} setup checks)`;
  }
  if (!subEl) return;
  const bits = [
    `CSV mapping: ${Number(counts.accounts_with_csv_mapping || 0)}/${Number(counts.accounts_total || 0)}`,
    `Email parser: ${Number(counts.accounts_with_parser || 0)}/${Number(counts.accounts_expect_email || 0)}`,
  ];
  subEl.textContent = bits.join(" | ");
}

async function loadInitialSetupProgress() {
  const textEl = document.getElementById("initialSetupProgressText");
  const subEl = document.getElementById("initialSetupProgressSub");
  if (textEl) textEl.textContent = "Loading setup progress...";
  if (subEl) subEl.textContent = "";
  let timer = null;
  try {
    const ctrl = (typeof AbortController !== "undefined") ? new AbortController() : null;
    timer = ctrl ? window.setTimeout(() => ctrl.abort(), 10000) : null;
    const res = await fetch("/settings/initial-setup-status", {
      cache: "no-store",
      credentials: "same-origin",
      signal: ctrl ? ctrl.signal : undefined,
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const out = await res.json();
    renderInitialSetupProgress(out || {});
  } catch (_) {
    if (textEl) textEl.textContent = "Setup progress unavailable";
    if (subEl) subEl.textContent = "Could not load setup completion status.";
  } finally {
    if (timer) window.clearTimeout(timer);
  }
}

function setNotifStatus(message, isError = false) {
  const el = document.getElementById("notifSettingsStatus");
  if (!el) return;
  el.textContent = String(message || "");
  el.style.opacity = isError ? "1" : "";
}

function setNotifInputsDisabled(disabled) {
  const ids = ["notifCreditUsageToggle", "notifCreditUsageTotalToggle", "notifBudgetOverToggle"];
  for (const id of ids) {
    const el = document.getElementById(id);
    if (el) el.disabled = !!disabled;
  }
}

function readNotifPrefsFromUi() {
  return {
    credit_usage: !!document.getElementById("notifCreditUsageToggle")?.checked,
    credit_usage_total: !!document.getElementById("notifCreditUsageTotalToggle")?.checked,
    budget_over: !!document.getElementById("notifBudgetOverToggle")?.checked,
  };
}

function applyNotifPrefsToUi(prefs) {
  const p = prefs || {};
  const creditUsageEl = document.getElementById("notifCreditUsageToggle");
  const creditUsageTotalEl = document.getElementById("notifCreditUsageTotalToggle");
  const budgetOverEl = document.getElementById("notifBudgetOverToggle");
  // Missing keys should default to enabled; only explicit false disables.
  if (creditUsageEl) creditUsageEl.checked = p.credit_usage !== false;
  if (creditUsageTotalEl) creditUsageTotalEl.checked = p.credit_usage_total !== false;
  if (budgetOverEl) budgetOverEl.checked = p.budget_over !== false;
}

function applyPushoverKeyToUi(userKey) {
  const el = document.getElementById("settingsPushoverUserKey");
  if (!el) return;
  const key = String(userKey || "").trim();
  el.textContent = key || "Not set";
}

async function loadNotificationSettings() {
  setNotifStatus("Loading...");
  setNotifInputsDisabled(true);
  try {
    const res = await fetch("/settings/notifications", { cache: "no-store", credentials: "same-origin" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const out = await res.json();
    applyNotifPrefsToUi(out.prefs || {});
    applyPushoverKeyToUi(out.pushover_user_key || "");
    setNotifStatus("");
  } catch (_) {
    setNotifStatus("Failed to load notification settings.", true);
  } finally {
    setNotifInputsDisabled(false);
  }
}

async function saveNotificationSettings() {
  const payload = readNotifPrefsFromUi();
  setNotifInputsDisabled(true);
  setNotifStatus("Saving...");
  try {
    const res = await fetch("/settings/notifications", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const out = await res.json().catch(() => ({}));
    applyNotifPrefsToUi(out.prefs || payload);
    setNotifStatus("Saved.");
    setTimeout(() => setNotifStatus(""), 1200);
  } catch (_) {
    setNotifStatus("Failed to save notification settings.", true);
  } finally {
    setNotifInputsDisabled(false);
  }
}

function queueNotificationSettingsSave() {
  if (_notifSaveTimer) {
    window.clearTimeout(_notifSaveTimer);
    _notifSaveTimer = null;
  }
  saveNotificationSettings().catch(() => {});
}

function bindNotificationSettings() {
  const ids = ["notifCreditUsageToggle", "notifCreditUsageTotalToggle", "notifBudgetOverToggle"];
  for (const id of ids) {
    const el = document.getElementById(id);
    if (!el) continue;
    el.addEventListener("change", () => queueNotificationSettingsSave());
  }
}

async function loadAdminVisibility() {
  const adminSection = document.getElementById("settingsAdminSection");
  if (!adminSection) return;
  adminSection.style.display = "none";
  try {
    const res = await fetch("/settings/view-flags", { cache: "no-store" });
    if (!res.ok) return;
    const out = await res.json().catch(() => ({}));
    adminSection.style.display = out?.is_owner ? "" : "none";
  } catch (_) {
    adminSection.style.display = "none";
  }
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
  loadInitialSetupProgress().catch((err) => console.error(err));
  loadNotificationSettings().catch((err) => console.error(err));
  loadAdminVisibility().catch((err) => console.error(err));
  loadWidgetPreview().catch((err) => console.error(err));
  bindWidgetActions();
  bindEmailParserBackfill();
  bindNotificationSettings();
});
