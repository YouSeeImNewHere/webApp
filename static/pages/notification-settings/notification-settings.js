let _notifSaveTimer = null;

const NOTIF_TOGGLES = [
  { id: "notifDisableAllToggle", key: "disable_all" },
  { id: "notifCreditUsageToggle", key: "credit_usage" },
  { id: "notifCreditUsageTotalToggle", key: "credit_usage_total" },
  { id: "notifBudgetOverToggle", key: "budget_over" },
  { id: "notifSafeToSpendDailyToggle", key: "safe_to_spend_daily" },
  { id: "notifCategoryDriftToggle", key: "category_drift" },
  { id: "notifRunwayWarningToggle", key: "runway_warning" },
  { id: "notifSavingsStreakToggle", key: "savings_streak" },
  { id: "notifSubscriptionCreepToggle", key: "subscription_creep" },
  { id: "notifHighSpendCooldownToggle", key: "high_spend_cooldown" },
  { id: "notifSmallWinReinforcementToggle", key: "small_win_reinforcement" },
  { id: "notifUserSignupPendingToggle", key: "user_signup_pending" },
  { id: "notifCronErrorToggle", key: "cron_error" },
  { id: "notifIosPushToggle", key: "ios_push" },
];

function syncDisableAllUi() {
  const disableAll = !!document.getElementById("notifDisableAllToggle")?.checked;
  for (const item of NOTIF_TOGGLES) {
    if (item.key === "disable_all") continue;
    const el = document.getElementById(item.id);
    if (el) el.disabled = disableAll;
  }
}

function setNotifStatus(message, isError = false) {
  const el = document.getElementById("notifSettingsStatus");
  if (!el) return;
  el.textContent = String(message || "");
  el.style.opacity = isError ? "1" : "";
}

function applyPushoverKeyToUi(userKey) {
  const el = document.getElementById("settingsPushoverUserKey");
  if (!el) return;
  const key = String(userKey || "").trim();
  el.textContent = key || "Not set";
}

function setNotifInputsDisabled(disabled) {
  for (const item of NOTIF_TOGGLES) {
    const el = document.getElementById(item.id);
    if (el) el.disabled = !!disabled;
  }
}

function readNotifPrefsFromUi() {
  const payload = {};
  for (const item of NOTIF_TOGGLES) {
    const el = document.getElementById(item.id);
    payload[item.key] = !!el?.checked;
  }
  return payload;
}

function applyNotifPrefsToUi(prefs) {
  const p = prefs || {};
  for (const item of NOTIF_TOGGLES) {
    const el = document.getElementById(item.id);
    if (!el) continue;
    if (item.key === "disable_all") el.checked = p.disable_all === true;
    else el.checked = p[item.key] !== false;
  }
  syncDisableAllUi();
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
    syncDisableAllUi();
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
    syncDisableAllUi();
  }
}

function queueNotificationSettingsSave() {
  if (_notifSaveTimer) {
    window.clearTimeout(_notifSaveTimer);
    _notifSaveTimer = null;
  }
  _notifSaveTimer = window.setTimeout(() => {
    saveNotificationSettings().catch(() => {});
  }, 120);
}

function bindNotificationSettings() {
  for (const item of NOTIF_TOGGLES) {
    const el = document.getElementById(item.id);
    if (!el) continue;
    el.addEventListener("change", () => {
      if (item.key === "disable_all") syncDisableAllUi();
      queueNotificationSettingsSave();
    });
  }
}

document.addEventListener("DOMContentLoaded", () => {
  loadNotificationSettings().catch((err) => console.error(err));
  bindNotificationSettings();
});
