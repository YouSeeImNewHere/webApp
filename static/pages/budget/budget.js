import { money } from "/static/shared/format.module.js";
import { formatMonthYearLong } from "/static/shared/dates.module.js";

(function () {
  const $ = (id) => document.getElementById(id);
// -------- Category color mapping (shared between table + pie) --------
// Deterministic HSL from a string so the same category is always the same color.
// -------- Category palette + numbering (shared between table + pie) --------
const CAT_PALETTE = [
  "#E74C3C", "#8E44AD", "#F39C12", "#E91E63", "#2ECC71",
  "#3498DB", "#1ABC9C", "#D35400", "#9B59B6", "#27AE60",
  "#2980B9", "#C0392B", "#16A085", "#7F8C8D"
];

function buildSpentMap(items) {
  const rows = (Array.isArray(items) ? items : [])
    .map(r => ({ category: String(r.category || "").trim(), spent: Math.max(0, Number(r.spent) || 0) }))
    .filter(r => r.category && r.spent > 0)
    .sort((a, b) => (b.spent || 0) - (a.spent || 0)); // biggest first

  const map = new Map();
  rows.forEach((r, i) => {
    map.set(r.category, {
      idx: i + 1,
      color: CAT_PALETTE[i % CAT_PALETTE.length],
    });
  });

  return { rows, map };
}


let spentPieChart = null;

function destroySpentPie() {
  if (spentPieChart) {
    spentPieChart.destroy();
    spentPieChart = null;
  }
}

function renderSpentPie(items, spentMap) {
  const canvas = $("spentPie");
  const mount = canvas ? canvas.closest(".spent-chart") : null;
  if (!canvas) return;

  const rows = spentMap?.rows || [];
  const map = spentMap?.map || new Map();

  if (!rows.length) {
    destroySpentPie();
    if (mount) mount.style.display = "none";
    return;
  }
  if (mount) mount.style.display = "";

  const labels = rows.map(r => r.category);
  const data = rows.map(r => r.spent);
  const colors = rows.map(r => (map.get(r.category)?.color || "#999"));

  // Bulletproof destroy (handles any previous chart on same canvas)
  const existing = Chart.getChart(canvas);
  if (existing) existing.destroy();
  destroySpentPie();

  // Plugin: draw slice numbers
  const sliceNumbers = {
    id: "sliceNumbers",
    afterDatasetsDraw(chart) {
      const { ctx } = chart;
      const meta = chart.getDatasetMeta(0);
      if (!meta || !meta.data) return;

      ctx.save();
      ctx.font = "900 12px Arial";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";

      meta.data.forEach((arc, i) => {
        // Compute a good label point inside the slice (works across Chart.js versions)
        const props = arc.getProps(["x","y","startAngle","endAngle","innerRadius","outerRadius"], true);
        const angle = (props.startAngle + props.endAngle) / 2;
        const r = (props.innerRadius + props.outerRadius) / 2;
        const pos = {
          x: props.x + Math.cos(angle) * r,
          y: props.y + Math.sin(angle) * r
        };

        const n = String(i + 1);

        // small dark bubble
        ctx.fillStyle = "rgba(0,0,0,0.55)";
        ctx.beginPath();
        ctx.arc(pos.x, pos.y, 12, 0, Math.PI * 2);
        ctx.fill();

        // white number
        ctx.fillStyle = "#fff";
        ctx.fillText(n, pos.x, pos.y);
      });

      ctx.restore();
    }
  };

  const ctx = canvas.getContext("2d");
  spentPieChart = new Chart(ctx, {
    type: "pie",
    data: {
      labels,
      datasets: [{
        data,
        backgroundColor: colors,
        borderWidth: 0,
        radius: "100%",
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      layout: { padding: 0 },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            // show "3. Food: $142.89"
            label: (c) => `${c.dataIndex + 1}. ${c.label}: ${money(Number(c.raw || 0))}`
          }
        }
      }
    },
    plugins: [sliceNumbers]
  });
}

    function todayISO() {
    const d = new Date();
    return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
  }

  async function fetchJSON(url, opts) {
    const res = await fetch(url, opts);
    if (!res.ok) {
      const t = await res.text().catch(() => "");
      throw new Error(`${url} -> ${res.status} ${t}`);
    }
    return res.json();
  }

  function parseCats(s) {
    return String(s || "")
      .split(",")
      .map(x => x.trim().toLowerCase())
      .filter(Boolean);
  }

  let pageYear = null;
  let pageMonth = null;
  let payload = null;

  function isCurrentViewedMonth() {
    const now = new Date();
    return pageYear === now.getFullYear() && pageMonth === (now.getMonth() + 1);
  }

  function monthStartDate(year, month) {
    return new Date(year, month - 1, 1);
  }

  function monthEndISO(year, month) {
    const end = new Date(year, month, 0);
    const y = end.getFullYear();
    const m = String(end.getMonth() + 1).padStart(2, "0");
    const d = String(end.getDate()).padStart(2, "0");
    return `${y}-${m}-${d}`;
  }

  function signedMoney(v) {
    const n = Number(v || 0);
    return `${n >= 0 ? "+" : "-"}${money(Math.abs(n))}`;
  }

  function setMonthLabel() {
    const label = $("monthLabel");
    if (label) label.textContent = formatMonthYearLong(monthStartDate(pageYear, pageMonth));
  }

  function syncMonthQuery() {
    try {
      const u = new URL(window.location.href);
      u.searchParams.set("year", String(pageYear));
      u.searchParams.set("month", String(pageMonth));
      window.history.replaceState({}, "", u.toString());
    } catch (_) {}
  }

  function shiftMonth(delta) {
    const base = monthStartDate(pageYear, pageMonth);
    base.setMonth(base.getMonth() + Number(delta || 0));
    pageYear = base.getFullYear();
    pageMonth = base.getMonth() + 1;
    setMonthLabel();
    syncMonthQuery();
  }

  async function renderTrendPanel() {
    const host = $("budgetTrendRows");
    const empty = $("budgetTrendEmpty");
    if (!host || !empty) return;

    host.innerHTML = "";
    empty.textContent = "Loading...";

    const months = [];
    for (let i = 5; i >= 0; i--) {
      const d = monthStartDate(pageYear, pageMonth);
      d.setMonth(d.getMonth() - i);
      months.push({ year: d.getFullYear(), month: d.getMonth() + 1 });
    }

    const payloads = await Promise.all(
      months.map(async (mm) => {
        try {
          const qs = new URLSearchParams({ year: String(mm.year), month: String(mm.month) });
          const d = await fetchJSON("/month-budget?" + qs.toString());
          return { ...mm, monthBudget: d || {} };
        } catch (_) {
          return { ...mm, monthBudget: null };
        }
      })
    );

    const rows = payloads.filter((r) => r.monthBudget && r.monthBudget.ok !== false);
    if (!rows.length) {
      empty.textContent = "No trend data yet.";
      return;
    }

    empty.textContent = "";
    for (const r of rows) {
      const mb = r.monthBudget || {};
      const allocated = Number(mb.allocations_total || 0);
      const spent = Number(mb.budgeted_spent_total || 0);
      const delta = allocated - spent;

      const row = document.createElement("div");
      row.className = "budget-trend-row";
      row.innerHTML = `
        <div>
          <div class="month">${formatMonthYearLong(monthStartDate(r.year, r.month))}</div>
          <div class="budget-muted">Allocated ${money(allocated)} • Spent ${money(spent)}</div>
        </div>
        <div class="delta ${delta >= 0 ? "is-good" : "is-bad"}">${signedMoney(delta)}</div>
      `;
      host.appendChild(row);
    }
  }

  function renderTop(d) {
  const mb = d.month || {};
  $("asOf").textContent = `Viewing ${formatMonthYearLong(monthStartDate(pageYear, pageMonth))}`;

  $("kIncome").textContent = money(mb.expected_income || 0);
  $("kBills").textContent = money(mb.bills_remaining || 0);
  $("kAllocated").textContent = money(mb.allocations_total || 0);
  $("kSafe").textContent = money(mb.safe_to_spend || 0);

  // ✅ NEW: Spent so far value
  const kSpent = $("kSpent");
  if (kSpent) kSpent.textContent = money(mb.spent_so_far || 0);

  // savings goal controls are optional in DOM; guard when hidden/removed
  const sgPercent = $("sgPercent");
  const sgAmount = $("sgAmount");
  const sgValue = $("sgValue");
  const kSavings = $("kSavings");
  const cfg = d.savings_goal_cfg || null;
  if (cfg) {
    if (sgPercent) sgPercent.checked = cfg.mode === "percent";
    if (sgAmount) sgAmount.checked = cfg.mode === "amount";
    if (sgValue) sgValue.value = String(cfg.value ?? "");
    if (kSavings) {
      kSavings.textContent =
        (cfg.mode === "percent") ? `${Number(cfg.value || 0).toFixed(2)}%` : money(mb.savings_goal || 0);
    }
  } else {
    if (sgAmount) sgAmount.checked = true;
    if (sgValue) sgValue.value = "";
    if (kSavings) kSavings.textContent = money(mb.savings_goal || 0);
  }

  // ✅ NEW: make rows clickable
  try { bindIncomeRowClick(); } catch (e) {}
  try { bindBillsRowClick(); } catch (e) {}
  try { bindSpentRowClick(); } catch (e) {}
  try { bindSafeRowClick(); } catch (e) {}

}

  function groupRowEl(row) {
  const wrap = document.createElement("div");
  wrap.className = "budget-table-row budget-table-row--group";
  const isSavingsGoalRow = String(row?.synthetic_kind || "") === "savings_goal";

  function cell(label, el, extraClass = "") {
    const c = document.createElement("div");
    c.className = "budget-cell " + extraClass;
    c.dataset.label = label;
    c.appendChild(el);
    return c;
  }

  const name = document.createElement("input");
  name.className = "budget-input";
  name.placeholder = "Work travel";
  name.value = row.name || "";
  if (isSavingsGoalRow) {
    name.disabled = true;
  }

  const allocated = document.createElement("input");
  allocated.className = "budget-input";
  allocated.inputMode = "decimal";
  allocated.value = String(row.allocated ?? 0);

  const cap = document.createElement("input");
  cap.className = "budget-input";
  cap.inputMode = "decimal";
  cap.placeholder = "optional";
  cap.value = (row.cap == null ? "" : String(row.cap));
  if (isSavingsGoalRow) {
    cap.value = "";
    cap.placeholder = "n/a";
    cap.disabled = true;
  }

  const cats = document.createElement("input");
  cats.className = "budget-input";
  cats.placeholder = "parking, travel";
  cats.value = (row.categories || []).join(", ");
  if (isSavingsGoalRow) {
    cats.value = "";
    cats.placeholder = "No categories";
    cats.disabled = true;
  }

  const spent = document.createElement("div");
  spent.className = "budget-money";
  spent.textContent = money(row.spent || 0);

  const remaining = document.createElement("div");
  remaining.className = "budget-money";
  remaining.textContent = money(row.remaining || 0);
  if (row.over_cap) remaining.classList.add("is-bad");

  const actions = document.createElement("div");
  actions.className = "budget-actions";
  if (isSavingsGoalRow) {
    actions.classList.add("is-savings-goal-actions");
  }

  const saveBtn = document.createElement("button");
  saveBtn.className = "settings-btn primary";
  saveBtn.textContent = isSavingsGoalRow ? "Save goal" : "Save";
  if (isSavingsGoalRow) {
    saveBtn.style.width = "100%";
  }

  const delBtn = document.createElement("button");
  delBtn.className = "settings-btn";
  delBtn.textContent = "Delete";
  if (isSavingsGoalRow) {
    delBtn.style.display = "none";
  }

  saveBtn.addEventListener("click", async () => {
    if (isSavingsGoalRow) {
      const val = Number(allocated.value || 0);
      if (!Number.isFinite(val) || val < 0) return alert("Enter a valid savings goal amount");
      try {
        await fetchJSON("/settings/savings-goal", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ mode: "amount", value: val }),
        });
        await load();
      } catch (e) {
        console.error(e);
        alert("Save goal failed: " + e.message);
      }
      return;
    }

    const nm = (name.value || "").trim();
    if (!nm) return alert("Group name is required");

    const body = {
      year: pageYear,
      month: pageMonth,
      name: nm,
      allocated: Number(allocated.value || 0),
      cap: cap.value === "" ? null : Number(cap.value),
      categories: parseCats(cats.value),
    };

    try {
      await fetchJSON("/budget/groups", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      await load();
    } catch (e) {
      console.error(e);
      alert("Save failed: " + e.message);
    }
  });

  delBtn.addEventListener("click", async () => {
    if (isSavingsGoalRow) return;
    const nm = (name.value || "").trim();
    if (!nm) { wrap.remove(); return; }
    if (!confirm(`Delete group "${nm}"?`)) return;

    try {
      const qs = new URLSearchParams({ year: String(pageYear), month: String(pageMonth), name: nm });
      await fetchJSON("/budget/groups?" + qs.toString(), { method: "DELETE" });
      await load();
    } catch (e) {
      console.error(e);
      alert("Delete failed: " + e.message);
    }
  });

  actions.appendChild(saveBtn);
  if (!isSavingsGoalRow) actions.appendChild(delBtn);

  wrap.appendChild(cell("Group", name));
  wrap.appendChild(cell("Allocated", allocated));
  wrap.appendChild(cell("Cap", cap));
  wrap.appendChild(cell("Categories", cats, "cell-wide"));
  wrap.appendChild(cell("Spent", spent, "is-right"));
  wrap.appendChild(cell("Remaining", remaining, "is-right"));
  wrap.appendChild(cell("", actions, "is-actions"));

  return wrap;
}

  function renderGroups(d) {
  const host = $("groupRows");
  host.innerHTML = "";

  const groups = d.groups || [];
  if (!groups.length) {
    $("groupsEmpty").textContent = "No group budgets yet. Tap Add group to create one.";
    return;
  }
  $("groupsEmpty").textContent = "";

  const sortedGroups = [...groups].sort((a, b) => {
    const aSavings = String(a?.synthetic_kind || "") === "savings_goal";
    const bSavings = String(b?.synthetic_kind || "") === "savings_goal";
    if (aSavings && !bSavings) return -1;
    if (!aSavings && bSavings) return 1;
    return 0;
  });

  for (const g of sortedGroups) host.appendChild(groupRowEl(g));
}


// ---- Sinking Fund modal helpers ----
let sfModalState = { mode: "create", fund: null };

function sfEl(id){ return document.getElementById(id); }

function openSfModal(opts){
  const modal = sfEl("sfModal");
  if (!modal) return alert("Modal missing: sfModal");
  const f = (opts && opts.fund) ? opts.fund : null;
  sfModalState = { mode: (opts && opts.mode) ? opts.mode : (f ? "edit" : "create"), fund: f };

  // Title
  const title = sfEl("sfTitle");
  if (title) title.textContent = (sfModalState.mode === "edit") ? "Edit Sinking Fund" : "Add Sinking Fund";

  // Defaults / populate
  sfEl("sfErr").textContent = "";
  sfEl("sfName").value = (f && f.name) ? String(f.name) : "";
  sfEl("sfTarget").value = (f && (f.target_amount != null)) ? String(f.target_amount || "") : "";
  sfEl("sfDate").value = (f && f.target_date) ? String(f.target_date) : "";
  sfEl("sfCadence").value = (f && f.cadence) ? String(f.cadence).toLowerCase() : "monthly";
  sfEl("sfContrib").value = (f && (f.contrib_amount != null)) ? String(f.contrib_amount || 0) : "";

  // show
  modal.classList.remove("hidden");
  modal.setAttribute("aria-hidden", "false");

  // focus
  setTimeout(() => { try { sfEl("sfName").focus(); } catch(e){} }, 0);
}

function closeSfModal(){
  const modal = sfEl("sfModal");
  if (!modal) return;
  modal.classList.add("hidden");
  modal.setAttribute("aria-hidden", "true");
}

function parseMoneyInput(v){
  const s = String(v || "").trim();
  if (!s) return 0;
  const n = Number(s.replace(/[^0-9.\-]/g, ""));
  return Number.isFinite(n) ? n : 0;
}

// ---------------- Sinking Funds ----------------
function daysBetween(a, b) {
  // a,b are Date objects (local)
  const ms = b.getTime() - a.getTime();
  return Math.ceil(ms / 86400000);
}

function fundNeededLine(f) {
  const bal = Number(f.reserved_balance || 0);
  const tgt = Number(f.target_amount || 0);

  const dateStr = (f.target_date || "").trim();
  if (!dateStr || !tgt || tgt <= bal) return "";

  const today = new Date();
  const due = new Date(dateStr + "T00:00:00");
  if (Number.isNaN(due.getTime())) return "";

  const days = Math.max(1, daysBetween(today, due));
  const remain = Math.max(0, tgt - bal);
  const perDay = remain / days;

  return `${money(perDay)} / day to hit by ${dateStr}`;
}

function fundCardEl(f) {
  const card = document.createElement("div");
  card.className = "fund-card";

  const name = (f.name || "").trim() || "Untitled";
  const bal = Number(f.reserved_balance || 0);
  const tgt = Number(f.target_amount || 0);

  const top = document.createElement("div");
  top.className = "fund-top";

  const left = document.createElement("div");
  left.className = "fund-name";
  left.textContent = name;

  const right = document.createElement("div");
  right.className = "fund-bal";
  right.textContent = money(bal);

  top.appendChild(left);
  top.appendChild(right);

  const sub = document.createElement("div");
  sub.className = "fund-sub";
  sub.textContent = tgt ? `${money(bal)} / ${money(tgt)}` : `${money(bal)} set aside`;

  const pct = tgt > 0 ? Math.max(0, Math.min(1, bal / tgt)) : 0;

  const bar = document.createElement("div");
  bar.className = "fund-bar";

  const fill = document.createElement("div");
  fill.className = "fund-bar__fill";
  fill.style.width = `${Math.round(pct * 100)}%`;

  bar.appendChild(fill);

  const needed = fundNeededLine(f);
  const meta = document.createElement("div");
  meta.className = "fund-meta";
  meta.textContent = needed || (f.target_date ? `Target date: ${f.target_date}` : "");

  const actions = document.createElement("div");
  actions.className = "fund-actions";

  const btn = (label, cls) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "settings-btn" + (cls ? " " + cls : "");
    b.textContent = label;
    return b;
  };

  const addBtn = btn("Add money");
  const useBtn = btn("Use money");
  const editBtn = btn("Edit");
  const delBtn = btn("Delete");

  addBtn.addEventListener("click", async () => {
    const amt = prompt(`Add how much to "${name}"?`, "50");
    if (amt == null) return;
    const n = Number(String(amt).replace(/[^0-9.\-]/g, ""));
    if (!Number.isFinite(n) || n <= 0) return alert("Enter a positive number.");
    await fetchJSON(`/funds/${f.id}/adjust`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ amount: n, note: "manual add" }),
    });
    await load();
  });

  useBtn.addEventListener("click", async () => {
    const amt = prompt(`Use how much from "${name}"?`, "50");
    if (amt == null) return;
    const n = Number(String(amt).replace(/[^0-9.\-]/g, ""));
    if (!Number.isFinite(n) || n <= 0) return alert("Enter a positive number.");
    await fetchJSON(`/funds/${f.id}/adjust`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ amount: -n, note: "manual use" }),
    });
    await load();
  });

  editBtn.addEventListener("click", () => {
    openSfModal({ mode: "edit", fund: f });
  });

  delBtn.addEventListener("click", async () => {
    if (!confirm(`Delete "${name}"?`)) return;
    await fetchJSON(`/funds/${f.id}`, { method: "DELETE" });
    await load();
  });

  actions.appendChild(addBtn);
  actions.appendChild(useBtn);
  actions.appendChild(editBtn);
  actions.appendChild(delBtn);

  card.appendChild(top);
  card.appendChild(sub);
  card.appendChild(bar);
  if (meta.textContent) card.appendChild(meta);
  card.appendChild(actions);

  return card;
}

function renderFunds(d) {
  const host = $("fundsRows");
  const empty = $("fundsEmpty");
  if (!host || !empty) return;

  host.innerHTML = "";
  const funds = (d.funds || []).filter((x) => x && x.is_active !== false);

  if (!funds.length) {
    empty.textContent = "No sinking funds yet. Tap Add fund to create one.";
    return;
  }
  empty.textContent = "";

  for (const f of funds) host.appendChild(fundCardEl(f));
}

function renderSpent(d) {
  const host = $("spentRows");
  host.innerHTML = "";

  const items = d.spent_categories || [];
  if (!items.length) {
    $("spentEmpty").textContent = "No spending found yet for this month.";
    renderSpentPie([]);
    return;
  }
  $("spentEmpty").textContent = "";

  // Keep the chart in sync with the table.
  const spentMap = buildSpentMap(items);
renderSpentPie(items, spentMap);


  for (const it of spentMap.rows) {
  const category = it.category;
  const spent = it.spent;

  const info = spentMap.map.get(category) || { idx: 0, color: "#999" };

  const row = document.createElement("div");
  row.className = "budget-table-row budget-table-row--spent";
  row.setAttribute("role", "button");
  row.setAttribute("tabindex", "0");

  const cat = document.createElement("div");
  cat.className = "budget-cell";
  cat.dataset.label = "Category";

  // Number badge + color dot + label
  // Number badge + label (color encoded by badge)
    const chip = document.createElement("div");
    chip.className = "cat-chip";

    const num = document.createElement("span");
    num.className = "cat-num";
    num.style.background = info.color;
    num.textContent = String(info.idx);

    const label = document.createElement("span");
    label.textContent = category;

    chip.appendChild(num);
    chip.appendChild(label);
    cat.appendChild(chip);


  const spentCell = document.createElement("div");
  spentCell.className = "budget-cell is-right";
  spentCell.dataset.label = "Spent";

  const spentEl = document.createElement("div");
  spentEl.className = "budget-money";
  spentEl.textContent = money(spent);
  spentCell.appendChild(spentEl);

  const go = () => {
    if (!category) return;
    window.location.href = `/static/pages/category/category.html?c=${encodeURIComponent(category)}`;
  };

  row.addEventListener("click", go);
  row.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      go();
    }
  });

  row.appendChild(cat);
  row.appendChild(spentCell);
  host.appendChild(row);
}

}

  async function load() {
    setMonthLabel();
    syncMonthQuery();
    const qs = new URLSearchParams({ year: String(pageYear), month: String(pageMonth) });
    payload = await fetchJSON("/page/budget?" + qs.toString());
    renderTop(payload);
    renderGroups(payload);
    renderFunds(payload);
    renderSpent(payload);
    bindIncomeRowClick();
    bindBillsRowClick();
bindSpentRowClick();
bindSafeRowClick();
    await renderTrendPanel();

  }

  function initMonth() {
    const d = new Date();
    const u = new URL(window.location.href);
    const y = Number(u.searchParams.get("year"));
    const m = Number(u.searchParams.get("month"));
    pageYear = Number.isInteger(y) && y > 1900 ? y : d.getFullYear();
    pageMonth = Number.isInteger(m) && m >= 1 && m <= 12 ? m : (d.getMonth() + 1);
    setMonthLabel();
    syncMonthQuery();
  }

  async function onSaveSavingsGoal() {
    if (!$("sgValue")) return;
    const mode = $("sgPercent").checked ? "percent" : "amount";
    const val = Number(($("sgValue").value || "").trim());
    if (!Number.isFinite(val) || val < 0) return alert("Enter a valid number");

    $("sgStatus").textContent = "Saving...";
    try {
      await fetchJSON("/settings/savings-goal", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode, value: val }),
      });
      $("sgStatus").textContent = "Saved";
      await load();
      setTimeout(() => { $("sgStatus").textContent = ""; }, 1200);
    } catch (e) {
      console.error(e);
      $("sgStatus").textContent = "";
      alert("Save failed: " + e.message);
    }
  }

  async function loadRoundupSettings() {
    const cb = $("roundupEnabled");
    const status = $("roundupStatus");
    if (!cb) return;
    try {
      const j = await fetchJSON("/settings/round-ups", { cache: "no-store" });
      cb.checked = !!j.enabled;
      if (status) status.textContent = "";
    } catch (e) {
      console.error(e);
      if (status) status.textContent = "Failed to load round-up setting.";
    }
  }

  async function saveRoundupSettings() {
    const cb = $("roundupEnabled");
    const status = $("roundupStatus");
    if (!cb) return;
    if (status) status.textContent = "Saving...";
    try {
      await fetchJSON("/settings/round-ups", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: !!cb.checked }),
      });
      if (status) status.textContent = "Saved";
      await load();
      await loadDayLimit(true);
      setTimeout(() => {
        if (status && status.textContent === "Saved") status.textContent = "";
      }, 1200);
    } catch (e) {
      console.error(e);
      if (status) status.textContent = "Save failed";
      alert("Round-up save failed: " + e.message);
    }
  }

    async function loadDayLimit(forceRecalc = false) {
      const recalcBtn = $("recalcTodayBtn");
      if (!isCurrentViewedMonth()) {
        if (recalcBtn) recalcBtn.disabled = true;
        $("kTodayLeft").textContent = "—";
        $("kTodayMeta").textContent = "Left Today is available for the current month only.";
        return;
      }
      if (recalcBtn) recalcBtn.disabled = false;
      const dl = await fetchJSON(`/day-limit${forceRecalc ? "?recalc=1" : ""}`);

      // Left Today KPI
      $("kTodayLeft").textContent = money(dl.remaining_today || 0);

      // Meta line under Left Today
      const spentFree = Number(dl.spent_today_free || 0);
      const baseline = Number(dl.baseline || 0);
      $("kTodayMeta").textContent = `Spent today ${money(spentFree)} • Baseline ${money(baseline)} / day`;
    }

// =========================
// Shared modal helpers (same behavior as Home page)
// =========================
function escapeHtml(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
function escapeHtmlAttr(s) {
  return String(s || "")
    .replaceAll("&", "&amp;")
    .replaceAll('"', "&quot;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}
function cssEscapeAttr(s) {
  return String(s || "").replaceAll('"', "&quot;");
}

function ensureTxInspectModal() {
  let root = document.getElementById("txInspectRoot");
  if (root) return root;

  root = document.createElement("div");
  root.id = "txInspectRoot";
  root.className = "tx-inspect hidden";

  root.innerHTML = `
    <div class="tx-inspect__backdrop" data-tx-close></div>

    <div class="tx-inspect__card" role="dialog" aria-modal="true">
      <div class="tx-inspect__head">
        <div>
          <div id="txInspectTitle" class="tx-inspect__title">Transaction</div>
          <div id="txInspectSub" class="tx-inspect__sub">—</div>
        </div>
        <button class="tx-inspect__close" type="button" data-tx-close aria-label="Close">✕</button>
      </div>

      <div id="txInspectBody" class="tx-inspect__body"></div>
    </div>
  `;

  document.body.appendChild(root);

  root.addEventListener("click", (e) => {
    if (e.target?.matches?.("[data-tx-close]")) closeTxInspect();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeTxInspect();
  });

  return root;
}
function closeTxInspect() {
  const root = document.getElementById("txInspectRoot");
  if (root) root.classList.add("hidden");
}

// =========================
// Last month's income popup (same as Home)
// =========================
function bindIncomeRowClick() {
  const incomeRow = document.getElementById("mbIncomeRow");
  if (!incomeRow || incomeRow.dataset.bound) return;
  incomeRow.dataset.bound = "1";

  incomeRow.setAttribute("role", "button");
  incomeRow.setAttribute("tabindex", "0");
  incomeRow.style.cursor = "pointer";

  incomeRow.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    openIncomeBreakdown();
  });
  incomeRow.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      openIncomeBreakdown();
    }
  });
}

function ensureIncomeInspectModal() {
  let root = document.getElementById("incomeInspectRoot");
  if (root) return root;

  root = document.createElement("div");
  root.id = "incomeInspectRoot";
  root.className = "tx-inspect hidden";

  root.innerHTML = `
    <div class="tx-inspect__backdrop" data-income-close></div>

    <div class="tx-inspect__card" role="dialog" aria-modal="true">
      <div class="tx-inspect__head">
        <div>
          <div id="incomeInspectTitle" class="tx-inspect__title">Last month's income</div>
          <div id="incomeInspectSub" class="tx-inspect__sub">—</div>
        </div>
        <button class="tx-inspect__close" type="button" data-income-close aria-label="Close">✕</button>
      </div>

      <div id="incomeInspectBody" class="tx-inspect__body"></div>
    </div>
  `;

  document.body.appendChild(root);

  root.addEventListener("click", (e) => {
    if (e.target?.matches?.("[data-income-close]")) closeIncomeInspect();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeIncomeInspect();
  });

  return root;
}
function closeIncomeInspect() {
  const root = document.getElementById("incomeInspectRoot");
  if (root) root.classList.add("hidden");
}
// =========================
// Safe to spend popup (show calculation)
// =========================
function bindSafeRowClick() {
  const row = document.getElementById("mbSafeRow");
  if (!row || row.dataset.bound) return;
  row.dataset.bound = "1";

  row.setAttribute("role", "button");
  row.setAttribute("tabindex", "0");
  row.style.cursor = "pointer";

  row.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    openSafeBreakdown();
  });
  row.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      openSafeBreakdown();
    }
  });
}

function ensureSafeInspectModal() {
  let root = document.getElementById("safeInspectRoot");
  if (root) return root;

  root = document.createElement("div");
  root.id = "safeInspectRoot";
  root.className = "tx-inspect hidden";

  root.innerHTML = `
    <div class="tx-inspect__backdrop" data-safe-close></div>

    <div class="tx-inspect__card" role="dialog" aria-modal="true">
      <div class="tx-inspect__head">
        <div>
          <div id="safeInspectTitle" class="tx-inspect__title">Safe to spend</div>
          <div id="safeInspectSub" class="tx-inspect__sub">—</div>
        </div>
        <button class="tx-inspect__close" type="button" data-safe-close aria-label="Close">✕</button>
      </div>

      <div id="safeInspectBody" class="tx-inspect__body"></div>
    </div>
  `;

  document.body.appendChild(root);

  root.addEventListener("click", (e) => {
    if (e.target?.matches?.("[data-safe-close]")) closeSafeInspect();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeSafeInspect();
  });

  return root;
}

function closeSafeInspect() {
  const root = document.getElementById("safeInspectRoot");
  if (root) root.classList.add("hidden");
}

function openSafeBreakdown() {
  const mb = (payload && payload.month) ? payload.month : {};

  const root = ensureSafeInspectModal();
  const titleEl = document.getElementById("safeInspectTitle");
  const subEl   = document.getElementById("safeInspectSub");
  const bodyEl  = document.getElementById("safeInspectBody");

  if (titleEl) titleEl.textContent = "Safe to spend (free)";
  if (subEl) subEl.textContent = `${money(Number(mb.safe_to_spend || 0))} • As of ${escapeHtml(mb.as_of || todayISO())}`;

  const expected_income = Number(mb.expected_income || 0);
  const base_income = Number(mb.base_income || 0);
  const les_income = Number(mb.les_income || 0);
  const savings_goal = Number(mb.savings_goal || 0);
  const spend_goal = Number(mb.spend_goal || 0);
  const allocations_total = Number(mb.allocations_total || 0);
  const budgeted_spent_total = Number(mb.budgeted_spent_total || 0);
  const free_spend_goal = Number(mb.free_spend_goal || 0);
  const spent_so_far = Number(mb.spent_so_far || 0);
  const spent_free = Number(mb.spent_free || 0);
  const safe_to_spend = Number(mb.safe_to_spend || 0);

  const stepsHtml = `
    <div class="calc">
      <div class="calc__title">Calculation</div>

      <div class="calc__section">
        <div class="calc__sectionTitle">Income</div>
        <div class="tx-kv calc__grid">
          ${kvRow("Last month's income (total)", money(expected_income))}
          ${kvRow("Base income", money(base_income), { kClass: "is-sub" })}
          ${kvRow("LES income", money(les_income), { kClass: "is-sub" })}
        </div>
      </div>

      <div class="calc__section">
        <div class="calc__sectionTitle">Goals</div>
        <div class="tx-kv calc__grid">
          ${kvRow("Savings goal", money(savings_goal))}
          ${kvRow("Spend goal", money(spend_goal), { kClass: "is-formula" })}
        </div>
        <div class="calc__formula">Spend goal = income − savings</div>
      </div>

      <div class="calc__section">
        <div class="calc__sectionTitle">Allocations</div>
        <div class="tx-kv calc__grid">
          ${kvRow("Allocations total (all groups incl. Bills)", money(allocations_total))}
          ${kvRow("Free spend goal", money(free_spend_goal), { kClass: "is-formula" })}
        </div>
        <div class="calc__formula">Free spend goal = spend goal − allocations</div>
      </div>

      <div class="calc__section">
        <div class="calc__sectionTitle">Spending</div>
        <div class="tx-kv calc__grid">
          ${kvRow("Budgeted spent (inside groups)", money(budgeted_spent_total))}
          ${kvRow("Spent so far (free)", money(spent_so_far))}
          ${kvRow("Spent free", money(spent_free), { kClass: "is-formula" })}
        </div>
        <div class="calc__formula">Spent free should match “spent so far (free)”</div>
      </div>

      <div class="calc__result">
        <div class="calc__resultLabel">Safe to spend</div>
        <div class="calc__resultValue">${escapeHtml(money(safe_to_spend))}</div>
      </div>
      <div class="calc__formula">Safe to spend = free spend goal − spent free</div>

      <div class="calc__note">
        Safe to spend is only your <b>free</b> spending after subtracting all group allocations
        (including the auto Bills group), and after removing spending that happened inside those groups
        so we don’t double-count it.
      </div>
    </div>
  `;

  if (bodyEl) bodyEl.innerHTML = stepsHtml;
  root.classList.remove("hidden");
}

async function fetchPaychecksForMonth(year, month) {
  const profile0 = window.Profile?.get?.();
  if (!profile0?.paygrade) return { events: [], breakdown: null };

  const profile = { ...profile0 };
  if (profile.paygrade != null) {
    profile.paygrade = String(profile.paygrade).toUpperCase().replace(/\s+/g, "").replace("E-", "E").replace("-", "");
  }
  if (profile.service_start != null) profile.service_start = String(profile.service_start);
  if (profile.bah_override === "") profile.bah_override = null;

  const res = await fetch("/les/paychecks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ year, month, profile })
  });

  if (!res.ok) {
    const txt = await res.text().catch(() => "");
    throw new Error("Paycheck calc failed: " + res.status + " " + txt);
  }

  const data = await res.json().catch(() => ({}));
  return {
    events: Array.isArray(data?.events) ? data.events : [],
    breakdown: data?.breakdown || null,
  };
}

async function fetchInterestForMonth(year, month) {
  const res = await fetch(`/recurring/calendar?year=${encodeURIComponent(year)}&month=${encodeURIComponent(month)}`);
  if (!res.ok) return [];
  const data = await res.json().catch(() => ({}));
  const events = Array.isArray(data?.events) ? data.events : [];

  return events.filter(e => {
    const cadence = String(e?.cadence || "").toLowerCase();
    const type = String(e?.type || "").toLowerCase();
    return cadence === "interest" || (type === "income" && cadence !== "paycheck" && String(e?.merchant||"").toLowerCase().includes("interest"));
  });
}

function kvRow(k, v, opts = {}) {
  const kClass = (opts && opts.kClass) ? String(opts.kClass) : "";
  const vClass = (opts && opts.vClass) ? String(opts.vClass) : "";
  return `<div class="tx-kv__k ${escapeHtmlAttr(kClass)}">${escapeHtml(k)}</div>` +
         `<div class="tx-kv__v ${escapeHtmlAttr(vClass)}">${escapeHtml(v)}</div>`;
}

async function openIncomeBreakdownLegacy() {
  const year = pageYear;
  const month = pageMonth;
  const monthDate = monthStartDate(year, month);

  const profile0 = window.Profile?.get?.();
if (!profile0) {
  alert("Profile still loading — try again in a second.");
  return;
}
if (!profile0.paygrade) {
  alert("Your LES Profile is missing paygrade. Open Profile and resave.");
  return;
}


  const modal = ensureIncomeInspectModal();
  const titleEl = document.getElementById("incomeInspectTitle");
  const subEl = document.getElementById("incomeInspectSub");
  const bodyEl = document.getElementById("incomeInspectBody");

  if (titleEl) titleEl.textContent = "Last month's income";
  if (subEl) subEl.textContent = "Loading…";
  if (bodyEl) bodyEl.innerHTML = "";

  modal.classList.remove("hidden");

  try {
    const [{ events: payEventsRaw, breakdown }, interestEventsRaw] = await Promise.all([
      fetchPaychecksForMonth(year, month),
      fetchInterestForMonth(year, month),
    ]);

    const SPENDABLE_ACCOUNT_ID = 3;
    const monthKey = `${year}-${String(month).padStart(2, "0")}`;

    const payEvents = (payEventsRaw || []).filter(e =>
      String(e?.date || "").startsWith(monthKey + "-") &&
      Number(e?.account_id) === SPENDABLE_ACCOUNT_ID
    );

    const interestEvents = (interestEventsRaw || []).filter(e =>
      String(e?.date || "").startsWith(monthKey + "-") &&
      Number(e?.account_id) === SPENDABLE_ACCOUNT_ID
    );

    const paycheckTotal = payEvents.reduce((s, e) => s + Math.max(0, Number(e?.amount || 0)), 0);
    const interestTotal = interestEvents.reduce((s, e) => s + Math.max(0, Number(e?.amount || 0)), 0);
    const grandTotal = paycheckTotal + interestTotal;

  if (subEl) subEl.textContent = `${money(grandTotal)} • ${formatMonthYearLong(monthDate)}`;

    const payList = payEvents
      .slice()
      .sort((a, b) => String(a.date).localeCompare(String(b.date)))
      .map(e => `<div class="tx-kv__k">${escapeHtml(e.date)}</div><div class="tx-kv__v">${escapeHtml(e.merchant || "Paycheck")} • ${money(e.amount)}</div>`)
      .join("");

    const intList = interestEvents
      .slice()
      .sort((a, b) => String(a.date).localeCompare(String(b.date)))
      .map(e => `<div class="tx-kv__k">${escapeHtml(e.date || "")}</div><div class="tx-kv__v">${escapeHtml(e.merchant || "Interest")} • ${money(e.amount)}</div>`)
      .join("");

    let breakdownHtml = "";
    if (breakdown) {
      const ent = breakdown.entitlements || {};
      const ded = breakdown.deductions || {};
      const net = breakdown.net || {};
      const p = breakdown.profile || {};

      breakdownHtml = `
        <div style="margin-bottom:12px; font-weight:700;">How the paychecks are calculated</div>
        <div class="tx-kv">
          ${kvRow("Paygrade", p.paygrade ?? "")}
          ${kvRow("Service start", p.service_start ?? "")}
          ${kvRow("Dependents", (p.has_dependents ? "Yes" : "No"))}

          ${kvRow("Base pay (monthly)", money(ent.base_pay))}
          ${kvRow("BAH (monthly)", money(ent.bah))}
          ${kvRow("BAS (monthly)", money(ent.bas))}
          ${kvRow("Sub pay (monthly)", money(ent.submarine_pay))}
          ${kvRow("Career sea pay (monthly)", money(ent.career_sea_pay))}
          ${kvRow("Spec duty pay (monthly)", money(ent.spec_duty_pay))}

          ${kvRow("Federal taxes", money(ded.federal_taxes))}
          ${kvRow("FICA social security", money(ded.fica_social_security))}
          ${kvRow("FICA medicare", money(ded.fica_medicare))}
          ${kvRow("SGLI", money(ded.sgli))}
          ${kvRow("AFRH", money(ded.afrh))}
          ${kvRow("Roth TSP", money(ded.roth_tsp))}
          ${kvRow("Meal deduction", money(ded.meal_deduction))}
          ${kvRow("Allotments total", money(ded.allotments_total))}
          ${kvRow("Mid-month collections", money(ded.mid_month_collections_total))}

          ${kvRow("Mid-month net pay", money(net.mid_month_pay))}
          ${kvRow("End-of-month net pay", money(net.eom))}
        </div>
      `;
    }

    bodyEl.innerHTML = `
      <div style="display:flex; flex-wrap:wrap; gap:8px; margin-bottom:12px;">
        <span class="category-pill" style="padding:8px 10px;">Paychecks: <strong style="margin-left:6px;">${money(paycheckTotal)}</strong></span>
        <span class="category-pill" style="padding:8px 10px;">Interest: <strong style="margin-left:6px;">${money(interestTotal)}</strong></span>
        <span class="category-pill" style="padding:8px 10px;">Total: <strong style="margin-left:6px;">${money(grandTotal)}</strong></span>
      </div>

      <div style="margin:0 0 12px; opacity:.7; font-size:12px;">
        Only counting deposits <strong>into account 3</strong> that land in <strong>${monthKey}</strong>.
      </div>

      <div style="margin-bottom:14px;">
        <div style="font-weight:700; margin-bottom:6px;">Paychecks in this month</div>
        <div class="tx-kv">${payList || `<div style="opacity:.7;">No paychecks found for this month.</div>`}</div>
      </div>

      <div style="margin-bottom:14px;">
        <div style="font-weight:700; margin-bottom:6px;">Estimated interest in this month</div>
        <div class="tx-kv">${intList || `<div style="opacity:.7;">No interest events found.</div>`}</div>
      </div>

      ${breakdownHtml}
    `;
  } catch (err) {
    console.error(err);
    if (subEl) subEl.textContent = "Failed to load";
    if (bodyEl) bodyEl.innerHTML = `<div style="opacity:.8;">Could not load last month's income breakdown.</div>`;
  }
}

async function openIncomeBreakdown() {
  const year = pageYear;
  const month = pageMonth;
  const monthDate = monthStartDate(year, month);

  const modal = ensureIncomeInspectModal();
  const titleEl = document.getElementById("incomeInspectTitle");
  const subEl = document.getElementById("incomeInspectSub");
  const bodyEl = document.getElementById("incomeInspectBody");

  if (titleEl) titleEl.textContent = "Last month's income";
  if (subEl) subEl.textContent = "Loading...";
  if (bodyEl) bodyEl.innerHTML = "";

  modal.classList.remove("hidden");

  try {
    const mb = payload?.month || {};
    const basis = mb.income_basis_month || {};
    const basisRows = Array.isArray(mb.income_basis_paychecks) ? mb.income_basis_paychecks : [];
    const basisTotal = Number(mb.income_basis_total || 0);
    const recurringIncome = Number(mb.base_income || 0);
    const grandTotal = Number(mb.expected_income || (basisTotal + recurringIncome));
    const basisLabel = (basis.year && basis.month)
      ? `${Number(basis.year)}-${String(Number(basis.month)).padStart(2, "0")}`
      : "previous month";

    if (subEl) subEl.textContent = `${money(grandTotal)} • ${formatMonthYearLong(monthDate)}`;

    const payList = basisRows
      .slice()
      .sort((a, b) => String(a?.date || "").localeCompare(String(b?.date || "")))
      .map((e) => `<div class="tx-kv__k">${escapeHtml(e?.date || "")}</div><div class="tx-kv__v">${escapeHtml(e?.merchant || "Paycheck")} • ${money(e?.amount || 0)}</div>`)
      .join("");

    bodyEl.innerHTML = `
      <div style="display:flex; flex-wrap:wrap; gap:8px; margin-bottom:12px;">
        <span class="category-pill" style="padding:8px 10px;">Last month paychecks used: <strong style="margin-left:6px;">${money(basisTotal)}</strong></span>
        <span class="category-pill" style="padding:8px 10px;">Other recurring income: <strong style="margin-left:6px;">${money(recurringIncome)}</strong></span>
        <span class="category-pill" style="padding:8px 10px;">Last month's income total: <strong style="margin-left:6px;">${money(grandTotal)}</strong></span>
      </div>

      <div style="margin:0 0 12px; opacity:.7; font-size:12px;">
        Budget basis for ${escapeHtml(formatMonthYearLong(monthDate))}: actual paycheck deposits from <strong>${escapeHtml(basisLabel)}</strong>.
      </div>

      <div style="margin-bottom:14px;">
        <div style="font-weight:700; margin-bottom:6px;">Paychecks used from ${escapeHtml(basisLabel)}</div>
        <div class="tx-kv">${payList || `<div style="opacity:.7;">No paycheck deposits found for that month.</div>`}</div>
      </div>
    `;
  } catch (err) {
    console.error(err);
    if (subEl) subEl.textContent = "Failed to load";
    if (bodyEl) bodyEl.innerHTML = `<div style="opacity:.8;">Could not load last month's income breakdown.</div>`;
  }
}

// =========================
// Remaining bills popup (paid vs upcoming for the month)
// Uses month payload fields: bills_paid, bills_remaining, bills_paid_items, bills_future_items
// =========================
function bindBillsRowClick() {
  const row = document.getElementById("mbBillsRow");
  if (!row || row.dataset.bound) return;
  row.dataset.bound = "1";

  row.setAttribute("role", "button");
  row.setAttribute("tabindex", "0");
  row.style.cursor = "pointer";

  row.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    openBillsBreakdown();
  });

  row.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      openBillsBreakdown();
    }
  });
}

function billsItemRow(it) {
  const d = escapeHtml(it?.date || "");
  const m = escapeHtml(it?.merchant || "—");
  const c = escapeHtml(it?.category || "");
  const a = money(Number(it?.amount || 0));
  return `
    <div class="bills-row">
      <div class="bills-row__left">
        <div class="bills-row__merchant" title="${m}">${m}</div>
        <div class="bills-row__meta">${d}${c ? " • " + c : ""}</div>
      </div>
      <div class="bills-row__amt">${a}</div>
    </div>
  `;
}

function openBillsBreakdown() {
  const root = ensureTxInspectModal();
  const titleEl = document.getElementById("txInspectTitle");
  const subEl = document.getElementById("txInspectSub");
  const bodyEl = document.getElementById("txInspectBody");

  const mb = payload?.month || {};
  const paid = Number(mb.bills_paid || 0);
  const remaining = Number(mb.bills_remaining || 0);
  const total = Number(mb.bills_total || 0);

  const paidItems = Array.isArray(mb.bills_paid_items) ? mb.bills_paid_items : [];
  const futureItems = Array.isArray(mb.bills_future_items) ? mb.bills_future_items : [];

  if (titleEl) titleEl.textContent = "Remaining bills";
  if (subEl) subEl.textContent = `${money(remaining)} remaining • ${money(paid)} paid • ${money(total)} total`;


if (bodyEl) {
    const paidCount = paidItems.length;
    const futureCount = futureItems.length;

    bodyEl.innerHTML = `
      <div class="bills-metrics">
        <div class="bills-metric">
          <div class="bills-metric__label">Paid</div>
          <div class="bills-metric__value">${money(paid)}</div>
        </div>
        <div class="bills-metric">
          <div class="bills-metric__label">Remaining</div>
          <div class="bills-metric__value">${money(remaining)}</div>
        </div>
        <div class="bills-metric">
          <div class="bills-metric__label">Total</div>
          <div class="bills-metric__value">${money(total)}</div>
        </div>
      </div>

      <div class="bills-section">
        <div class="bills-section__hdr">
          <div class="bills-section__title">Paid bills</div>
          <div class="bills-section__count">${paidCount ? `${paidCount} item${paidCount === 1 ? "" : "s"}` : "—"}</div>
        </div>
        <div class="bills-list">
          ${paidItems.length ? paidItems.map(billsItemRow).join("") : `<div class="bills-empty">None yet.</div>`}
        </div>
      </div>

      <div class="bills-section" style="margin-top:14px;">
        <div class="bills-section__hdr">
          <div class="bills-section__title">Upcoming bills</div>
          <div class="bills-section__count">${futureCount ? `${futureCount} item${futureCount === 1 ? "" : "s"}` : "—"}</div>
        </div>
        <div class="bills-list">
          ${futureItems.length ? futureItems.map(billsItemRow).join("") : `<div class="bills-empty">None remaining.</div>`}
        </div>
      </div>
    `;
  }

  root.classList.remove("hidden");
}

// =========================
// Spent so far popup (same as Home)
// =========================
function bindSpentRowClick() {
  const row = document.getElementById("mbSpentRow");
  if (!row || row.dataset.bound) return;
  row.dataset.bound = "1";

  row.setAttribute("role", "button");
  row.setAttribute("tabindex", "0");
  row.style.cursor = "pointer";

  row.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    openSpentBreakdown();
  });

  row.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      openSpentBreakdown();
    }
  });
}

async function openSpentBreakdown() {
  const root = ensureTxInspectModal();

  const titleEl = document.getElementById("txInspectTitle");
  const subEl   = document.getElementById("txInspectSub");
  const bodyEl  = document.getElementById("txInspectBody");

  if (titleEl) titleEl.textContent = "Spent so far";
  if (subEl) subEl.textContent = "Loading…";
  if (bodyEl) bodyEl.innerHTML = "";

  const start = monthStartDate(pageYear, pageMonth);
  const startISO = `${start.getFullYear()}-${String(start.getMonth()+1).padStart(2,"0")}-${String(start.getDate()).padStart(2,"0")}`;
  const endISO = isCurrentViewedMonth() ? todayISO() : monthEndISO(pageYear, pageMonth);

  try {
    const res = await fetch(`/spent-so-far-breakdown?start=${encodeURIComponent(startISO)}&end=${encodeURIComponent(endISO)}`, { cache: "no-store" });
    if (!res.ok) throw new Error("HTTP " + res.status);
    const d = await res.json();

    if (subEl) subEl.textContent = `${d.start} → ${d.end} · Total: ${money(Number(d.total || 0))}`;

    const excluded = Array.isArray(d.excluded) ? d.excluded : [];
    const included = Array.isArray(d.included) ? d.included : [];

    const excludedHtml = `
      <div style="font-weight:800; margin-bottom:6px;">Excluded categories</div>
      <div style="border-top:1px solid rgba(0,0,0,.08); margin:8px 0;"></div>
      ${excluded.map(x => `
        <div style="display:flex; justify-content:space-between; padding:6px 0;">
          <div style="opacity:.85;">${escapeHtml(x.category)}</div>
          <div style="font-weight:800;">${money(Number(x.total || 0))}</div>
        </div>
      `).join("") || `<div style="opacity:.7;">None</div>`}
      <div style="border-top:1px solid rgba(0,0,0,.08); margin:10px 0;"></div>
    `;

    const includedRows = included.map(x => `
      <div style="border:1px solid rgba(0,0,0,.10); border-radius:10px; margin:8px 0; overflow:hidden;">
        <button type="button"
          data-spent-acc-btn="1"
          data-cat="${escapeHtmlAttr(x.category)}"
          aria-expanded="false"
          style="width:100%; text-align:left; padding:10px 12px; display:flex; justify-content:space-between; gap:12px; background:rgba(0,0,0,.02); border:0; cursor:pointer;">
          <span style="font-weight:750;">${escapeHtml(x.category)}</span>
          <span style="display:flex; align-items:center; gap:10px;">
            <span style="font-weight:800;">${money(Number(x.total || 0))}</span>
            <span style="opacity:.45;">▾</span>
          </span>
        </button>
        <div data-spent-acc-pane="${escapeHtmlAttr(x.category)}" style="display:none; padding:10px 12px;"></div>
      </div>
    `).join("");

    const includedHtml = `
      <div style="font-weight:800; margin-bottom:6px;">Included categories</div>
      <div style="opacity:.7; font-size:12px; margin-bottom:8px;">Tap a category to see the transactions included in the total.</div>
      <div>${includedRows || `<div style="opacity:.7;">No spending yet.</div>`}</div>
    `;

    bodyEl.innerHTML = excludedHtml + includedHtml;

    if (!bodyEl.dataset.spentAccBound) {
      bodyEl.dataset.spentAccBound = "1";
      bodyEl.addEventListener("click", async (e) => {
        const btn = e.target.closest?.("button[data-spent-acc-btn]");
        if (!btn) return;

        const cat = btn.getAttribute("data-cat") || "";
        const pane = bodyEl.querySelector(`[data-spent-acc-pane="${cssEscapeAttr(cat)}"]`);
        if (!pane) return;

        const isOpen = btn.getAttribute("aria-expanded") === "true";
        btn.setAttribute("aria-expanded", String(!isOpen));
        pane.style.display = isOpen ? "none" : "block";

        if (isOpen) return;

        if (pane.dataset.loaded === "1") return;
        pane.dataset.loaded = "1";
        pane.innerHTML = `<div style="opacity:.7;">Loading…</div>`;

        try {
          const txRes = await fetch(`/spent-so-far-transactions?category=${encodeURIComponent(cat)}&start=${encodeURIComponent(startISO)}&end=${encodeURIComponent(endISO)}`, { cache: "no-store" });
          if (!txRes.ok) throw new Error("HTTP " + txRes.status);
          const txData = await txRes.json();
          const tx = (txData && txData.transactions) || [];

          if (!tx.length) {
            pane.innerHTML = `<div style="opacity:.7;">No transactions.</div>`;
            return;
          }

          pane.innerHTML = tx.map(r => `
            <div style="display:flex; justify-content:space-between; gap:12px; padding:8px 0; border-bottom:1px solid rgba(0,0,0,.06);">
              <div style="min-width:0;">
                <div style="font-weight:750; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">
                  ${escapeHtml(r.merchant || "—")}
                </div>
                <div style="opacity:.65; font-size:12px;">
                  ${escapeHtml(r.date || "")}${(r.bank || r.card) ? " • " + escapeHtml(`${r.bank || ""}${r.card ? " • " + r.card : ""}`.trim()) : ""}
                </div>
              </div>
              <div style="font-weight:800; white-space:nowrap;">${money(Number(r.amount || 0))}</div>
            </div>
          `).join("");
        } catch (err) {
          console.error(err);
          pane.innerHTML = `<div style="opacity:.8;">Failed to load transactions.</div>`;
        }
      });
    }

    root.classList.remove("hidden");
  } catch (err) {
    console.error(err);
    if (subEl) subEl.textContent = "Failed to load";
    if (bodyEl) bodyEl.innerHTML = `<div style="opacity:.8;">Could not load spent breakdown.</div>`;
    root.classList.remove("hidden");
  }
}

  window.addEventListener("DOMContentLoaded", async () => {
    initMonth();

    const prevBtn = $("prevMonthBtn");
    if (prevBtn) {
      prevBtn.addEventListener("click", async () => {
        shiftMonth(-1);
        await load();
        await loadDayLimit(false);
      });
    }

    const nextBtn = $("nextMonthBtn");
    if (nextBtn) {
      nextBtn.addEventListener("click", async () => {
        shiftMonth(1);
        await load();
        await loadDayLimit(false);
      });
    }

    const sgSaveBtn = $("sgSave");
    if (sgSaveBtn) sgSaveBtn.addEventListener("click", onSaveSavingsGoal);
    const ru = $("roundupEnabled");
    if (ru) ru.addEventListener("change", saveRoundupSettings);

    $("addGroupBtn").addEventListener("click", () => {
      const host = $("groupRows");
      $("groupsEmpty").textContent = "";
      host.appendChild(groupRowEl({ name: "", allocated: 0, cap: null, categories: [], spent: 0, remaining: 0 }));
    });


    const addFundBtn = $("addFundBtn");
    if (addFundBtn) {
      addFundBtn.addEventListener("click", () => {
        openSfModal({ mode: "create" });
      });
    }

    // wire modal close + submit once
    const sfModal = document.getElementById("sfModal");
    if (sfModal && !sfModal.__wired) {
      sfModal.__wired = true;

      // close handlers
      sfModal.addEventListener("click", (e) => {
        const t = e.target;
        if (t && (t.hasAttribute("data-sf-close"))) closeSfModal();
      });

      // ESC closes
      window.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && !sfModal.classList.contains("hidden")) closeSfModal();
      });

      // submit
      const form = document.getElementById("sfForm");
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const err = document.getElementById("sfErr");
        err.textContent = "";

        const name = (sfEl("sfName").value || "").trim();
        if (!name) { err.textContent = "Name is required."; return; }

        const tgt = parseMoneyInput(sfEl("sfTarget").value);
        const date = (sfEl("sfDate").value || "").trim(); // native date picker => YYYY-MM-DD or ""
        const cadence = (sfEl("sfCadence").value || "monthly").trim().toLowerCase();
        const contrib = parseMoneyInput(sfEl("sfContrib").value);

        const payload = {
          name,
          target_amount: Number.isFinite(tgt) ? tgt : 0,
          target_date: date,
          cadence,
          contrib_amount: Number.isFinite(contrib) ? contrib : 0,
        };

        const saveBtn = document.getElementById("sfSaveBtn");
        const oldTxt = saveBtn ? saveBtn.textContent : "";
        if (saveBtn) { saveBtn.disabled = true; saveBtn.textContent = "Saving…"; }

        try {
          if (sfModalState.mode === "edit" && sfModalState.fund && sfModalState.fund.id) {
            await fetchJSON(`/funds/${sfModalState.fund.id}`, {
              method: "PATCH",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(payload),
            });
          } else {
            await fetchJSON("/funds", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(payload),
            });
          }

          closeSfModal();
          await load();
        } catch (ex) {
          console.error(ex);
          err.textContent = "Save failed: " + (ex && ex.message ? ex.message : String(ex));
        } finally {
          if (saveBtn) { saveBtn.disabled = false; saveBtn.textContent = oldTxt; }
        }
      });
    }
try {
          await load();
          await loadRoundupSettings();
          await loadDayLimit(false);

          const btn = $("recalcTodayBtn");
          if (btn) {
            btn.disabled = !isCurrentViewedMonth();
            btn.addEventListener("click", async () => {
              const old = btn.textContent;
              btn.disabled = true;
              btn.textContent = "Recalc...";
              try {
                await loadDayLimit(true);
              } catch (e) {
                console.error(e);
                alert("Recalc failed: " + e.message);
              } finally {
                btn.disabled = !isCurrentViewedMonth();
                btn.textContent = old;
              }
            });
          }
        } catch (e) {
          console.error(e);
          alert("Budget page failed to load: " + e.message);
        }

  });
})();

