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

  function money(n) {
    const x = Number(n || 0);
    const sign = x < 0 ? "-" : "";
    return sign + "$" + Math.abs(x).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
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

  function renderTop(d) {
    const mb = d.month || {};
    $("asOf").textContent = `As of ${todayISO()}`;

    $("kIncome").textContent = money(mb.expected_income || 0);
    $("kBills").textContent = money(mb.bills_remaining || 0);
    $("kAllocated").textContent = money(mb.allocations_total || 0);
    $("kSafe").textContent = money(mb.safe_to_spend || 0);

    const cfg = d.savings_goal_cfg || null;
    if (cfg) {
      $("sgPercent").checked = cfg.mode === "percent";
      $("sgAmount").checked = cfg.mode === "amount";
      $("sgValue").value = String(cfg.value ?? "");
      $("kSavings").textContent = (cfg.mode === "percent") ? `${Number(cfg.value || 0).toFixed(2)}%` : money(mb.savings_goal || 0);
    } else {
      $("sgAmount").checked = true;
      $("sgValue").value = "";
      $("kSavings").textContent = money(mb.savings_goal || 0);
    }
  }

  function groupRowEl(row) {
  const wrap = document.createElement("div");
  wrap.className = "budget-table-row budget-table-row--group";

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

  const allocated = document.createElement("input");
  allocated.className = "budget-input";
  allocated.inputMode = "decimal";
  allocated.value = String(row.allocated ?? 0);

  const cap = document.createElement("input");
  cap.className = "budget-input";
  cap.inputMode = "decimal";
  cap.placeholder = "optional";
  cap.value = (row.cap == null ? "" : String(row.cap));

  const cats = document.createElement("input");
  cats.className = "budget-input";
  cats.placeholder = "parking, travel";
  cats.value = (row.categories || []).join(", ");

  const spent = document.createElement("div");
  spent.className = "budget-money";
  spent.textContent = money(row.spent || 0);

  const remaining = document.createElement("div");
  remaining.className = "budget-money";
  remaining.textContent = money(row.remaining || 0);
  if (row.over_cap) remaining.classList.add("is-bad");

  const actions = document.createElement("div");
  actions.className = "budget-actions";

  const saveBtn = document.createElement("button");
  saveBtn.className = "settings-btn primary";
  saveBtn.textContent = "Save";

  const delBtn = document.createElement("button");
  delBtn.className = "settings-btn";
  delBtn.textContent = "Delete";

  saveBtn.addEventListener("click", async () => {
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
  actions.appendChild(delBtn);

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

  for (const g of groups) host.appendChild(groupRowEl(g));
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
    window.location.href = `/static/category.html?c=${encodeURIComponent(category)}`;
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
    const qs = new URLSearchParams({ year: String(pageYear), month: String(pageMonth) });
    payload = await fetchJSON("/page/budget?" + qs.toString());
    renderTop(payload);
    renderGroups(payload);
    renderFunds(payload);
    renderSpent(payload);
  }

  function initMonth() {
    const d = new Date();
    pageYear = d.getFullYear();
    pageMonth = d.getMonth() + 1;
  }

  async function onSaveSavingsGoal() {
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

    async function loadDayLimit(forceRecalc = false) {
      const dl = await fetchJSON(`/day-limit${forceRecalc ? "?recalc=1" : ""}`);

      // Left Today KPI
      $("kTodayLeft").textContent = money(dl.remaining_today || 0);

      // Meta line under Left Today
      const spentFree = Number(dl.spent_today_free || 0);
      const baseline = Number(dl.baseline || 0);
      $("kTodayMeta").textContent = `Spent today ${money(spentFree)} • Baseline ${money(baseline)} / day`;
    }


  window.addEventListener("DOMContentLoaded", async () => {
    initMonth();

    $("sgSave").addEventListener("click", onSaveSavingsGoal);

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
          await loadDayLimit(false);

          const btn = $("recalcTodayBtn");
          if (btn) {
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
                btn.disabled = false;
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
