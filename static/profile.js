// /static/profile.js
// LES Profile: localStorage cache + DB-backed persistence via /les-profile (so it stays the same across devices).
(function () {
  const KEY = "les_profile_v1";
  const SERVER_KEY = "default";

  const DEFAULTS = {
    // identity
    paygrade: "E-5",
    service_start: "2020-01-01",
    has_dependents: true,

    // entitlements / special pays
    bas: 460.25,
    bah_override: null,
    submarine_pay: 0,
    career_sea_pay: 0,
    spec_duty_pay: 0,

    // W-4 (monthly withholding calc uses these)
    filing_status: "S",            // S | MFJ | HOH
    step2_multiple_jobs: false,
    dep_under17: 0,
    other_dep: 0,
    other_income_annual: 0,
    other_deductions_annual: 0,
    extra_withholding: 0,

    // mid-month / deductions / toggles
    tsp_rate: 0.0,                 // 0.05 = 5%
    fica_include_special_pays: false,

    meal_rate: 13.30,
    meal_end_day: 31,
    meal_deduction_enabled: false,
    meal_deduction_start: null,    // YYYY-MM-DD or null

    mid_month_fraction: 0.50,      // default split, resets each month
    allotments_total: 0.0,
    mid_month_collections_total: 0.0,
  };

  function _clone(x){ return (typeof structuredClone === "function") ? structuredClone(x) : JSON.parse(JSON.stringify(x)); }

  function _loadLocal() {
    try {
      const raw = localStorage.getItem(KEY);
      if (!raw) return _clone(DEFAULTS);
      const parsed = JSON.parse(raw);
      return { ..._clone(DEFAULTS), ...(parsed || {}) };
    } catch {
      return _clone(DEFAULTS);
    }
  }

  function _saveLocal(profile) {
    const merged = { ..._clone(DEFAULTS), ...(profile || {}) };
    try { localStorage.setItem(KEY, JSON.stringify(merged)); } catch {}
    return merged;
  }

  // in-memory cache so callers can stay sync
  let _cache = _loadLocal();

  const listeners = new Set();
  function _emit(p) {
    for (const fn of listeners) {
      try { fn(p); } catch (_) {}
    }
  }

  // ---- server sync ----
  let _initPromise = null;
  let _saveTimer = null;
  let _lastServerWrite = 0;

  async function _fetchServer() {
    const res = await fetch(`/les-profile?key=${encodeURIComponent(SERVER_KEY)}`, { cache: "no-store" });
    if (!res.ok) throw new Error("les-profile fetch failed");
    return await res.json();
  }

  async function _writeServer(profile) {
    // tiny debounce so typing doesn't hammer the server
    if (_saveTimer) clearTimeout(_saveTimer);
    _saveTimer = setTimeout(async () => {
      try {
        _lastServerWrite = Date.now();
        await fetch("/les-profile", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ key: SERVER_KEY, profile })
        });
      } catch (e) {
        // keep silent; localStorage is still the source of truth offline
        console.warn("LES profile save failed:", e);
      }
    }, 250);
  }

  async function init() {
    if (_initPromise) return _initPromise;
    _initPromise = (async () => {
      // always start from local cache immediately
      _cache = _saveLocal(_cache);

      // then try to hydrate from server; if server empty but local has values, push local up
      try {
        const out = await _fetchServer();
        const serverProfile = (out && out.profile) ? out.profile : {};
        const serverHasAny = serverProfile && Object.keys(serverProfile).length > 0;

        if (serverHasAny) {
          _cache = _saveLocal({ ..._cache, ...serverProfile });
          _emit(_cache);
        } else {
          // if server is blank, push our local cache so other devices can see it
          await _writeServer(_cache);
        }
      } catch (e) {
        // offline / server down — ok
      }
    })();
    return _initPromise;
  }

  function get() {
    // sync getter — returns local cache immediately
    if (!_cache) _cache = _loadLocal();
    return _cache;
  }

  function set(patch) {
    const next = _saveLocal({ ...get(), ...(patch || {}) });
    _cache = next;
    _emit(next);
    _writeServer(next);
    return next;
  }

  function replace(profile) {
    const next = _saveLocal({ ..._clone(DEFAULTS), ...(profile || {}) });
    _cache = next;
    _emit(next);
    _writeServer(next);
    return next;
  }

  function onChange(fn) {
    listeners.add(fn);

    // storage sync across tabs (same device)
    const onStorage = (e) => {
      if (e.key === KEY) {
        try {
          _cache = _loadLocal();
          fn(_cache);
        } catch {}
      }
    };
    window.addEventListener("storage", onStorage);

    // fire immediately with current state
    try { fn(get()); } catch {}

    return () => {
      listeners.delete(fn);
      window.removeEventListener("storage", onStorage);
    };
  }

  // ---- UI (inline editor) ----
  function mountEditor(mountSelectorOrEl) {
    const mount =
      (typeof mountSelectorOrEl === "string")
        ? document.querySelector(mountSelectorOrEl)
        : mountSelectorOrEl;

    if (!mount) return () => {};

    // ensure we pull server state ASAP (but don't block initial render)
    init().catch(() => {});

    mount.innerHTML = `
      <div class="settings-card">
        <form id="profileForm" class="les-form" autocomplete="off">
          <div class="les-grid">
            <label class="les-field">
              <span>Paygrade</span>
              <input name="paygrade" type="text" placeholder="E-5" />
            </label>

            <label class="les-field">
              <span>Service start (YYYY-MM-DD)</span>
              <input name="service_start" type="text" placeholder="2020-01-01" />
            </label>

            <label class="les-field">
              <span>Dependents</span>
              <select name="has_dependents">
                <option value="true">Yes</option>
                <option value="false">No</option>
              </select>
            </label>

            <label class="les-field">
              <span>BAH override (blank = auto)</span>
              <input name="bah_override" type="number" step="0.01" placeholder="" />
            </label>

            <label class="les-field">
              <span>BAS</span>
              <input name="bas" type="number" step="0.01" />
            </label>

            <label class="les-field">
              <span>TSP rate (0.05 = 5%)</span>
              <input name="tsp_rate" type="number" step="0.01" />
            </label>

            <label class="les-field">
              <span>Mid-month fraction</span>
              <input name="mid_month_fraction" type="number" step="0.01" />
            </label>

            <label class="les-field">
              <span>FICA include special pays</span>
              <select name="fica_include_special_pays">
                <option value="true">Yes</option>
                <option value="false">No</option>
              </select>
            </label>

            <label class="les-field">
              <span>Submarine pay</span>
              <input name="submarine_pay" type="number" step="0.01" />
            </label>

            <label class="les-field">
              <span>Career sea pay</span>
              <input name="career_sea_pay" type="number" step="0.01" />
            </label>

            <label class="les-field">
              <span>Special duty pay</span>
              <input name="spec_duty_pay" type="number" step="0.01" />
            </label>

            <label class="les-field">
              <span>Extra withholding (per month)</span>
              <input name="extra_withholding" type="number" step="0.01" />
            </label>

            <label class="les-field">
              <span>Meal deduction enabled</span>
              <select name="meal_deduction_enabled">
                <option value="true">Yes</option>
                <option value="false">No</option>
              </select>
            </label>

            <label class="les-field">
              <span>Meal deduction start (YYYY-MM-DD)</span>
              <input name="meal_deduction_start" type="text" placeholder="" />
            </label>

            <label class="les-field">
              <span>Meal rate (per day)</span>
              <input name="meal_rate" type="number" step="0.01" />
            </label>

            <label class="les-field">
              <span>Meal end day</span>
              <input name="meal_end_day" type="number" step="1" min="1" max="31" />
            </label>

            <label class="les-field">
              <span>Allotments total</span>
              <input name="allotments_total" type="number" step="0.01" />
            </label>

            <label class="les-field">
              <span>Mid-month collections total</span>
              <input name="mid_month_collections_total" type="number" step="0.01" />
            </label>

            <label class="les-field">
              <span>Filing status</span>
              <select name="filing_status">
                <option value="S">Single</option>
                <option value="MFJ">Married filing jointly</option>
                <option value="HOH">Head of household</option>
              </select>
            </label>

            <label class="les-field">
              <span>Step 2: multiple jobs</span>
              <select name="step2_multiple_jobs">
                <option value="true">Yes</option>
                <option value="false">No</option>
              </select>
            </label>

            <label class="les-field">
              <span>Dependents under 17</span>
              <input name="dep_under17" type="number" step="1" />
            </label>

            <label class="les-field">
              <span>Other dependents</span>
              <input name="other_dep" type="number" step="1" />
            </label>

            <label class="les-field">
              <span>Other income (annual)</span>
              <input name="other_income_annual" type="number" step="0.01" />
            </label>

            <label class="les-field">
              <span>Other deductions (annual)</span>
              <input name="other_deductions_annual" type="number" step="0.01" />
            </label>
          </div>

          <div class="settings-row" style="margin-top:12px;">
            <button class="settings-btn primary" id="les_saveBtn" type="submit">Save</button>
            <button class="settings-btn" id="les_resetBtn" type="button">Reset to defaults</button>
            <span id="les_saveMsg" class="settings-muted" style="margin-left:auto;"></span>
          </div>
        </form>
      </div>
    `;

    const form = mount.querySelector("#profileForm");
    const msg = mount.querySelector("#les_saveMsg");

    function hydrate(p) {
      if (!form) return;
      const prof = p || {};
      for (const [k, v] of Object.entries({ ..._clone(DEFAULTS), ...(prof || {}) })) {
        const el = form.elements.namedItem(k);
        if (!el) continue;

        if (el.tagName === "SELECT") {
          if (typeof v === "boolean") el.value = v ? "true" : "false";
          else el.value = (v === null || v === undefined) ? "" : String(v);
        } else {
          el.value = (v === null || v === undefined) ? "" : String(v);
        }
      }
    }

    // initial paint from local cache
    hydrate(get());

    // if init() pulls a newer server value, onChange will re-hydrate
    const off = onChange((p) => hydrate(p));

    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const fd = new FormData(form);
      const next = {};

      for (const [k, v0] of fd.entries()) {
        let v = v0;

        // empty -> null for some nullable fields
        if (v === "") {
          if (k === "bah_override" || k === "meal_deduction_start") v = null;
          else v = "";
        }

        // coerce types
        if (["bas","tsp_rate","mid_month_fraction","submarine_pay","career_sea_pay","spec_duty_pay","extra_withholding","meal_rate","allotments_total","mid_month_collections_total","other_income_annual","other_deductions_annual"].includes(k)) {
          v = (v === null || v === "") ? 0 : Number(v);
        }
        if (["meal_end_day","dep_under17","other_dep"].includes(k)) {
          v = (v === null || v === "") ? 0 : parseInt(String(v), 10);
        }
        if (["has_dependents","fica_include_special_pays","meal_deduction_enabled","step2_multiple_jobs"].includes(k)) {
          v = (String(v) === "true");
        }

        next[k] = v;
      }

      const saved = replace({ ...get(), ...next });
      msg.textContent = "Saved ✅";
      setTimeout(() => (msg.textContent = ""), 1500);
      hydrate(saved);
    });

    mount.querySelector("#les_resetBtn").addEventListener("click", () => {
      const next = replace(_clone(DEFAULTS));
      hydrate(next);
      msg.textContent = "Reset to defaults ✅";
      setTimeout(() => (msg.textContent = ""), 1500);
    });

    return () => off();
  }

  // Kick init in the background for any page that loads profile.js
  try { init(); } catch {}

  window.Profile = { init, get, set, replace, onChange, mountEditor };
})();
