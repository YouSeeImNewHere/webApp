// /static/profile.js
// Shared LES Profile UI + persistence (localStorage)
// This is injected on every page so changing the profile once updates everywhere.

(function () {
  "use strict";

  const STORAGE_KEY = "les_profile_v1";
  const STYLE_ID = "lesProfileStyleV1";
  const MOUNT_ID = "lesProfileMountV1";

  function _safeJsonParse(s) {
    try { return JSON.parse(s); } catch { return null; }
  }

  function get() {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? _safeJsonParse(raw) : null;
  }

  function set(p) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(p || {}));
    // notify listeners in-page
    window.dispatchEvent(new CustomEvent("les:profile-changed", { detail: { profile: p || {} } }));
  }

  function _ensureStyle() {
    if (document.getElementById(STYLE_ID)) return;

    const css = `
/* --- Shared Profile button (top-right) --- */
.profile-btn{
  position:fixed;
  top:12px;
  right:12px;
  z-index:1200;
  padding:10px 14px;
  border-radius:999px;
  border:1px solid rgba(0,0,0,0.12);
  background:#fff;
  box-shadow:0 6px 18px rgba(0,0,0,0.10);
  font:600 14px/1 system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
  cursor:pointer;
}
.profile-btn:hover{ box-shadow:0 10px 28px rgba(0,0,0,0.14); }
.profile-btn:active{ transform:translateY(1px); }

/* --- Modal --- */
.profile-modal{ position:fixed; inset:0; z-index:1400; }
.profile-modal.hidden{ display:none; }
.profile-backdrop{ position:absolute; inset:0; background:rgba(0,0,0,0.35); }
.profile-card{
  position: fixed;
  top: 14px;
  left: 14px;
  right: auto;
  bottom: auto;
  transform: none;

  max-width: 620px;
  width: min(620px, calc(100% - 28px));
  max-height: calc(100vh - 28px);
  overflow: auto;

  background:#fff;
  border-radius:18px;
  box-shadow:0 18px 60px rgba(0,0,0,0.20);
  padding:16px;
}

.profile-head{
  display:flex;
  justify-content:space-between;
  align-items:center;
  gap:12px;
  margin-bottom:10px;
}
.profile-title{ font:700 16px/1.2 system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; }
.profile-x{
  border:0;
  background:transparent;
  font-size:18px;
  cursor:pointer;
  padding:6px 10px;
  border-radius:10px;
}
.profile-x:hover{ background:rgba(0,0,0,0.06); }

.profile-form{
  display:grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap:10px 12px;
}
.profile-field{ display:flex; flex-direction:column; gap:6px; }
.profile-field label{ font-size:12px; opacity:0.8; }
.profile-field input, .profile-field select{
  padding:9px 10px;
  border-radius:12px;
  border:1px solid rgba(0,0,0,0.12);
  background:#fff;
  outline:none;
}
.profile-field input:focus, .profile-field select:focus{
  border-color: rgba(0,0,0,0.25);
  box-shadow:0 0 0 3px rgba(0,0,0,0.06);
}

.profile-fieldset{
  grid-column:1 / -1;
  border:1px solid rgba(0,0,0,0.08);
  border-radius:14px;
  padding:12px;
}
.profile-fieldset legend{
  padding:0 8px;
  font-size:12px;
  opacity:0.8;
}
.profile-actions{
  grid-column:1 / -1;
  display:flex;
  justify-content:flex-end;
  gap:10px;
  margin-top:6px;
}
.profile-actions button{
  padding:10px 14px;
  border-radius:12px;
  border:1px solid rgba(0,0,0,0.12);
  background:#fff;
  cursor:pointer;
  font-weight:600;
}
.profile-actions button.primary{
  background:#111;
  color:#fff;
  border-color:#111;
}
.profile-actions button:hover{ filter:brightness(0.98); }
.profile-actions button:active{ transform:translateY(1px); }

@media (max-width: 900px){
  .profile-form{ grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 560px){
  .profile-form{ grid-template-columns: 1fr; }
  .profile-card{ margin:4vh 10px; }
}
    `.trim();

    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = css;
    document.head.appendChild(style);
  }

  function _markup() {
    // The markup is centralized here so every page stays in sync.
    return `
<button id="profileBtn" class="profile-btn" type="button" aria-label="Open profile">Profile</button>

<div id="profileModal" class="profile-modal hidden" role="dialog" aria-modal="true" aria-labelledby="profileTitle">
  <div class="profile-backdrop" data-profile-close="1"></div>
  <div class="profile-card">
    <div class="profile-head">
      <div id="profileTitle" class="profile-title">LES Profile</div>
      <button class="profile-x" type="button" data-profile-close="1" aria-label="Close">✕</button>
    </div>

    <form id="profileForm" class="profile-form">
      <div class="profile-field">
        <label for="paygrade">Paygrade</label>
        <input id="paygrade" name="paygrade" placeholder="E5" autocomplete="off" />
      </div>

      <div class="profile-field">
        <label for="service_start">Service start (YYYY-MM-DD)</label>
        <input id="service_start" name="service_start" placeholder="2021-06-30" autocomplete="off" />
      </div>

      <div class="profile-field">
        <label for="has_dependents">Has dependents</label>
        <select id="has_dependents" name="has_dependents">
          <option value="false">No</option>
          <option value="true">Yes</option>
        </select>
      </div>

      <fieldset class="profile-fieldset">
        <legend>Entitlements / Special Pays</legend>

        <div class="profile-form">
          <div class="profile-field">
            <label for="bah_override">BAH override (optional)</label>
            <input id="bah_override" name="bah_override" placeholder="" />
          </div>

          <div class="profile-field">
            <label for="bas">BAS</label>
            <input id="bas" name="bas" placeholder="0" />
          </div>

          <div class="profile-field">
            <label for="submarine_pay">Sub pay</label>
            <input id="submarine_pay" name="submarine_pay" placeholder="0" />
          </div>

          <div class="profile-field">
            <label for="career_sea_pay">Career sea pay</label>
            <input id="career_sea_pay" name="career_sea_pay" placeholder="0" />
          </div>

          <div class="profile-field">
            <label for="spec_duty_pay">Spec duty pay</label>
            <input id="spec_duty_pay" name="spec_duty_pay" placeholder="0" />
          </div>

          <div class="profile-field">
            <label for="tsp_rate">Roth TSP rate</label>
            <input id="tsp_rate" name="tsp_rate" placeholder="0.05" />
          </div>
        </div>
      </fieldset>

      <fieldset class="profile-fieldset">
        <legend>Meal deduction (optional)</legend>

        <div class="profile-form">
          <div class="profile-field">
            <label for="meal_deduction_enabled">Apply meal deduction?</label>
            <select id="meal_deduction_enabled" name="meal_deduction_enabled">
              <option value="false">No</option>
              <option value="true">Yes</option>
            </select>
          </div>

          <div class="profile-field">
            <label for="meal_deduction_start">Start date</label>
            <input id="meal_deduction_start" name="meal_deduction_start" type="date" />
          </div>
        </div>



        <div class="profile-form">
          <div class="profile-field">
            <label for="meal_rate">Meal rate (per day)</label>
            <input id="meal_rate" name="meal_rate" placeholder="13.30" />
          </div>

          <div class="profile-field">
            <label for="meal_end_day">Meal end day (1–31)</label>
            <input id="meal_end_day" name="meal_end_day" placeholder="31" />
          </div>
        </div>
      </fieldset>

      <fieldset class="profile-fieldset">
        <legend>Mid-month / Allotments</legend>

        <div class="profile-form">
          <div class="profile-field">
            <label for="mid_month_fraction">Mid-month fraction</label>
            <input id="mid_month_fraction" name="mid_month_fraction" placeholder="0.5" />
          </div>

          <div class="profile-field">
            <label for="allotments_total">Allotments total</label>
            <input id="allotments_total" name="allotments_total" placeholder="0" />
          </div>

          <div class="profile-field">
            <label for="mid_month_collections_total">Mid-month collections</label>
            <input id="mid_month_collections_total" name="mid_month_collections_total" placeholder="0" />
          </div>
        </div>
      </fieldset>

      <fieldset class="profile-fieldset">
        <legend>W-4</legend>

        <div class="profile-form">
          <div class="profile-field">
            <label for="filing_status">Filing status</label>
            <select id="filing_status" name="filing_status">
              <option value="S">Single</option>
              <option value="M">Married</option>
              <option value="H">Head of household</option>
            </select>
          </div>

          <div class="profile-field">
            <label for="step2_multiple_jobs">Step 2 (multiple jobs)</label>
            <select id="step2_multiple_jobs" name="step2_multiple_jobs">
              <option value="false">No</option>
              <option value="true">Yes</option>
            </select>
          </div>

          <div class="profile-field">
            <label for="dep_under17">Dependents under 17</label>
            <input id="dep_under17" name="dep_under17" placeholder="0" />
          </div>

          <div class="profile-field">
            <label for="other_dep">Other dependents</label>
            <input id="other_dep" name="other_dep" placeholder="0" />
          </div>

          <div class="profile-field">
            <label for="other_income_annual">Other income (annual)</label>
            <input id="other_income_annual" name="other_income_annual" placeholder="0" />
          </div>

          <div class="profile-field">
            <label for="other_deductions_annual">Other deductions (annual)</label>
            <input id="other_deductions_annual" name="other_deductions_annual" placeholder="0" />
          </div>

          <div class="profile-field">
            <label for="extra_withholding">Extra withholding (per pay)</label>
            <input id="extra_withholding" name="extra_withholding" placeholder="0" />
          </div>
        </div>
      </fieldset>

      <div class="profile-actions">
        <button type="button" data-profile-close="1">Cancel</button>
        <button class="primary" type="submit">Save</button>
      </div>
    </form>
  </div>
</div>
    `.trim();
  }

  function open() {
    const modal = document.getElementById("profileModal");
    if (!modal) return;
    modal.classList.remove("hidden");
  }

  function close() {
    const modal = document.getElementById("profileModal");
    if (!modal) return;
    modal.classList.add("hidden");
  }

  function _coerceValue(key, v) {
    // Keep behavior consistent with your existing recurring_page.js parsing.
    if (v === "true") return true;
    if (v === "false") return false;

    // ints
    if (key.endsWith("_day") || key.startsWith("dep_") || key === "other_dep") {
      const n = Number(v);
      return Number.isFinite(n) ? n : 0;
    }

    // floats (including 0.05)
    const n = Number(v);
    if (v !== "" && Number.isFinite(n)) return n;

    return v;
  }

  function _hydrateForm(form, p) {
    if (!form) return;
    const prof = p || {};
    for (const [k, v] of Object.entries(prof)) {
      const el = form.elements.namedItem(k);
      if (!el) continue;
            if (v === null || v === undefined) {
        el.value = "";
      } else {
        el.value = String(v);
      }
    }
  }

  function _bind() {
    const btn = document.getElementById("profileBtn");
    const modal = document.getElementById("profileModal");
    const form = document.getElementById("profileForm");
    if (!btn || !modal || !form) return;

    if (!btn.__profileBound) {
      btn.__profileBound = true;
      btn.addEventListener("click", () => {
        _hydrateForm(form, get());
        open();
      });
    }

    if (!modal.__profileBound) {
      modal.__profileBound = true;

      modal.addEventListener("click", (e) => {
        if (e.target && e.target.dataset && e.target.dataset.profileClose) close();
      });

      modal.querySelectorAll("[data-profile-close]").forEach((el) => {
        el.addEventListener("click", close);
      });

      form.addEventListener("submit", (e) => {
        e.preventDefault();

        const fd = new FormData(form);
        const prev = get() || {};
        const p2 = { ...prev }; // keep existing fields

        fd.forEach((val, key) => {
          p2[key] = _coerceValue(key, String(val));
        });

        // empty overrides -> null
        if (p2.bah_override === "" || p2.bah_override === undefined) p2.bah_override = null;
        if (p2.meal_deduction_start === "" || p2.meal_deduction_start === undefined) p2.meal_deduction_start = null;

        set(p2);
        close();
      });
    }
  }

  function ensureUI() {
    _ensureStyle();

    // If markup doesn't exist yet, inject at end of <body>.
    if (!document.getElementById(MOUNT_ID)) {
      const mount = document.createElement("div");
      mount.id = MOUNT_ID;
      mount.innerHTML = _markup();
      document.body.appendChild(mount);
    }

    _bind();
  }

  function onChange(fn) {
    window.addEventListener("les:profile-changed", (e) => fn?.(e.detail?.profile || get() || {}));
    // Also update if changed from another tab/window
    window.addEventListener("storage", (e) => {
      if (e.key === STORAGE_KEY) fn?.(get() || {});
    });
  }

  // expose
  window.Profile = { get, set, open, close, ensureUI, onChange };

  // auto-mount
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", ensureUI);
  } else {
    ensureUI();
  }
})();