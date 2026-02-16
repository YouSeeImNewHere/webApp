let _monthBudgetSnapshot = null;

function money(n) {
  const v = Number(n || 0);
  return v.toLocaleString(undefined, { style: "currency", currency: "USD" });
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
});
