(function () {
  const INCOME_TYPE_KEY = "income_wizard_type";
  let monthBudgetSnapshot = null;

  function money(n) {
    const v = Number(n || 0);
    return v.toLocaleString(undefined, { style: "currency", currency: "USD" });
  }

  function readPointValue(id, fallback) {
    const input = document.getElementById(id);
    const raw = String((input && input.value) || "").trim();
    const n = Number(raw);
    if (!Number.isFinite(n) || n <= 0) return fallback;
    return Math.max(1, Math.round(n));
  }

  function normalizeKeywordLines(raw) {
    const lines = String(raw || "")
      .split(/\r?\n/g)
      .map((s) => s.trim().toLowerCase())
      .filter(Boolean);
    const seen = new Set();
    const out = [];
    for (const line of lines) {
      const v = line.length > 64 ? line.slice(0, 64) : line;
      if (seen.has(v)) continue;
      seen.add(v);
      out.push(v);
      if (out.length >= 20) break;
    }
    return out;
  }

  async function loadPaycheckMatchers() {
    const input = document.getElementById("paycheckKeywords");
    const saveBtn = document.getElementById("savePaycheckMatchersBtn");
    const statusEl = document.getElementById("paycheckMatchersStatus");
    if (!input || !saveBtn) return;

    try {
      const res = await fetch("/settings/paycheck-matchers", { cache: "no-store" });
      if (res.ok) {
        const d = await res.json();
        const keywords = Array.isArray(d?.keywords) ? d.keywords : [];
        input.value = keywords.join("\n");
      }
    } catch (_err) {
      if (statusEl) statusEl.textContent = "Failed to load paycheck matchers.";
    }

    saveBtn.addEventListener("click", async () => {
      const keywords = normalizeKeywordLines(input.value);
      saveBtn.disabled = true;
      if (statusEl) statusEl.textContent = "Saving...";
      try {
        const res = await fetch("/settings/paycheck-matchers", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ keywords }),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const d = await res.json().catch(() => ({}));
        const saved = Array.isArray(d?.keywords) ? d.keywords : keywords;
        input.value = saved.join("\n");
        if (statusEl) statusEl.textContent = "Saved.";
        setTimeout(() => {
          if (statusEl) statusEl.textContent = "";
        }, 1500);
      } catch (_err) {
        if (statusEl) statusEl.textContent = "Failed to save.";
      } finally {
        saveBtn.disabled = false;
      }
    });
  }

  function renderDailyWeightsPreview() {
    const el = document.getElementById("dailyWeightsPreview");
    if (!el || !monthBudgetSnapshot) return;

    const weekdayPoints = readPointValue("weekdayPoints", 1);
    const weekendPoints = readPointValue("weekendPoints", 2);

    const safe = Number(monthBudgetSnapshot.safe_to_spend || 0);
    const weekdayDays = Number(monthBudgetSnapshot.weekday_days_left || 0);
    const weekendDays = Number(monthBudgetSnapshot.weekend_days_left || 0);
    const totalPoints = (weekdayDays * weekdayPoints) + (weekendDays * weekendPoints);
    const pointValue = totalPoints > 0 ? (safe / totalPoints) : 0;
    const weekdayLimit = pointValue * weekdayPoints;
    const weekendLimit = pointValue * weekendPoints;

    const todayDow = new Date().getDay();
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
        monthBudgetSnapshot = await budgetRes.json();
      }

      renderDailyWeightsPreview();
    } catch (_err) {
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
      } catch (_err) {
        if (statusEl) statusEl.textContent = "Failed to save.";
      } finally {
        saveBtn.disabled = false;
      }
    });
  }

  function setActiveIncomeType(type) {
    const t = String(type || "les").toLowerCase();
    const map = {
      les: "incomePanelLes",
      salary: "incomePanelSalary",
      hourly: "incomePanelHourly",
    };
    const activeType = map[t] ? t : "les";

    document.querySelectorAll(".income-type-btn").forEach((btn) => {
      const selected = btn.getAttribute("data-income-type") === activeType;
      btn.classList.toggle("active", selected);
      btn.setAttribute("aria-selected", selected ? "true" : "false");
    });

    Object.entries(map).forEach(([k, id]) => {
      const panel = document.getElementById(id);
      if (!panel) return;
      const on = k === activeType;
      panel.classList.toggle("hidden", !on);
      panel.setAttribute("aria-hidden", on ? "false" : "true");
    });

    try {
      localStorage.setItem(INCOME_TYPE_KEY, activeType);
    } catch (_e) {}
  }

  function bindIncomeTypePicker() {
    document.querySelectorAll(".income-type-btn").forEach((btn) => {
      btn.addEventListener("click", () => setActiveIncomeType(btn.getAttribute("data-income-type") || "les"));
    });

    let preferred = "les";
    try {
      preferred = localStorage.getItem(INCOME_TYPE_KEY) || "les";
    } catch (_e) {}
    setActiveIncomeType(preferred);
  }

  document.addEventListener("DOMContentLoaded", () => {
    if (window.Profile) {
      window.Profile.mountEditor("#lesProfileMount");
    }
    bindIncomeTypePicker();
    loadPaycheckMatchers().catch(() => {});
    loadDailyWeightsSettings().catch(() => {});
  });
})();
