(function () {
  const $ = (id) => document.getElementById(id);

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
    $("kDaily").textContent = `${money(mb.daily_limit || 0)} / day`;

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
  wrap.style.gridTemplateColumns = "1fr .7fr .7fr 1.4fr .7fr .7fr auto";

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

  function renderSpent(d) {
    const host = $("spentRows");
    host.innerHTML = "";

    const items = d.spent_categories || [];
    if (!items.length) {
      $("spentEmpty").textContent = "No spending found yet for this month.";
      return;
    }
    $("spentEmpty").textContent = "";

    for (const it of items) {
  const row = document.createElement("div");
  row.className = "budget-table-row budget-table-row--spent";
  row.style.gridTemplateColumns = "1fr .7fr";

  const c1 = document.createElement("div");
  c1.className = "budget-cell";
  c1.dataset.label = "Category";
  c1.textContent = it.category || "";

  const c2 = document.createElement("div");
  c2.className = "budget-cell is-right";
  c2.dataset.label = "Spent";

  const spent = document.createElement("div");
  spent.className = "budget-money";
  spent.textContent = money(it.spent || 0);
  c2.appendChild(spent);

  row.appendChild(c1);
  row.appendChild(c2);
  host.appendChild(row);
}
  }

  async function load() {
    const qs = new URLSearchParams({ year: String(pageYear), month: String(pageMonth) });
    payload = await fetchJSON("/page/budget?" + qs.toString());
    renderTop(payload);
    renderGroups(payload);
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

  window.addEventListener("DOMContentLoaded", async () => {
    initMonth();

    $("sgSave").addEventListener("click", onSaveSavingsGoal);

    $("addGroupBtn").addEventListener("click", () => {
      const host = $("groupRows");
      $("groupsEmpty").textContent = "";
      host.appendChild(groupRowEl({ name: "", allocated: 0, cap: null, categories: [], spent: 0, remaining: 0 }));
    });

    try {
      await load();
    } catch (e) {
      console.error(e);
      alert("Budget page failed to load: " + e.message);
    }
  });
})();
