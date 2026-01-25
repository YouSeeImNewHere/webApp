// /static/categoryRules.js
// UI for viewing/updating CategoryRules (regex -> category)
//
// Features:
// - Edit category per rule
// - Show match counts
// - Enable/disable rule
// - Delete rule
// - Re-apply rule to existing transactions
// - Test regex against recent merchants

let _categories = [];

function esc(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function setStatus(msg, isError = false) {
  const el = document.getElementById("rulesStatus");
  if (!el) return;
  el.textContent = msg || "";
  el.style.opacity = msg ? "0.9" : "0.0";
  el.style.color = isError ? "var(--danger)" : "var(--text-muted)";
}

async function fetchCategories() {
  try {
    const res = await fetch("/categories", { cache: "no-store" });
    if (!res.ok) return;
    _categories = await res.json();
    const dl = document.getElementById("categoryOptions");
    if (dl) {
      dl.innerHTML = (_categories || [])
        .map((c) => `<option value="${esc(c)}"></option>`)
        .join("");
    }
  } catch {}
}

function openTestModal({ pattern = "", flags = "i", ruleId = null } = {}) {
  const modal = document.getElementById("ruleTestModal");
  if (!modal) return;

  modal.hidden = false;
  modal.dataset.ruleId = ruleId ?? "";
  document.getElementById("testPattern").value = pattern;
  document.getElementById("testFlags").value = flags || "i";
  document.getElementById("testLimit").value = "50";
  document.getElementById("testResults").innerHTML = "";
  document.getElementById("testSubtitle").textContent =
    ruleId ? `Rule #${ruleId}` : "Ad-hoc test";
}

function closeTestModal() {
  const modal = document.getElementById("ruleTestModal");
  if (!modal) return;
  modal.hidden = true;
  modal.dataset.ruleId = "";
}

function renderTestResults(data) {
  const host = document.getElementById("testResults");
  if (!host) return;

  const tested = data?.tested ?? [];
  const matched = tested.filter((x) => x.matched).length;

  host.innerHTML = `
    <div class="test-summary">
      <div><b>${matched}</b> / ${tested.length} matched</div>
      <div class="settings-muted" style="margin:0;">Showing recent distinct merchants (with counts)</div>
    </div>
    <div class="test-list">
      ${tested
        .map(
          (r) => `
        <div class="test-row ${r.matched ? "hit" : "miss"}">
          <div class="test-merchant">${esc(r.merchant)}</div>
          <div class="test-count mono">x${esc(r.count)}</div>
          <div class="test-badge">${r.matched ? "MATCH" : "—"}</div>
        </div>
      `
        )
        .join("")}
    </div>
  `;
}

async function runTest() {
  const pattern = document.getElementById("testPattern").value || "";
  const flags = document.getElementById("testFlags").value || "i";
  const limit = parseInt(document.getElementById("testLimit").value || "50", 10) || 50;

  const btn = document.getElementById("runTestBtn");
  btn.disabled = true;

  try {
    const res = await fetch("/category-rules/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pattern, flags, limit }),
    });

    const data = await res.json();
    if (!res.ok || data?.ok === false) {
      renderTestResults({ tested: [] });
      setStatus(data?.error || "Test failed", true);
      return;
    }
    renderTestResults(data);
  } catch (e) {
    setStatus("Test failed", true);
  } finally {
    btn.disabled = false;
  }
}

async function loadRules() {
  setStatus("Loading rules…");
  const tbody = document.querySelector("#rulesTable tbody");
  if (!tbody) return;

  tbody.innerHTML = "";

  try {
    const res = await fetch("/category-rules/list?include_inactive=1&with_counts=1", {
      cache: "no-store",
    });
    const rules = await res.json();

    if (!Array.isArray(rules)) {
      setStatus("Failed to load rules", true);
      return;
    }

    for (const r of rules) {
      const tr = document.createElement("tr");

      const isActive = !!r.is_active;
      const matchCount = Number(r.match_count || 0);

      tr.innerHTML = `
        <td class="mono">${esc(r.pattern)}</td>
        <td>
          <input
            class="settings-input"
            list="categoryOptions"
            value="${esc(r.category)}"
            data-id="${esc(r.id)}"
          />
          <div class="rule-subrow">
            <label class="toggle">
              <input type="checkbox" class="reapply-toggle" />
              <span>Re-apply to existing</span>
            </label>
          </div>
        </td>
        <td>
          <span class="pill mono">${esc(matchCount)}</span>
        </td>
        <td>
          <label class="switch" title="Enable/disable rule">
            <input type="checkbox" class="active-toggle" ${isActive ? "checked" : ""} />
            <span class="slider"></span>
          </label>
        </td>
        <td>
          <div class="rule-actions">
            <button class="settings-btn small save-btn">Save</button>
            <button class="settings-btn small test-btn">Test</button>
            <button class="settings-btn small danger delete-btn">Delete</button>
          </div>
        </td>
      `;

      const id = r.id;

      // Save (optionally re-apply)
     tr.querySelector(".save-btn").onclick = async () => {
  const input = tr.querySelector("input.settings-input");
  const reapply = tr.querySelector(".reapply-toggle").checked;
  const btn = tr.querySelector(".save-btn");

  btn.disabled = true;

  try {
    const resp = await fetch(`/category-rules/${id}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        category: input.value,
        reapply_existing: !!reapply
      }),
    });

    const data = await resp.json();
    if (!resp.ok || data?.ok === false) {
      setStatus(data?.error || "Save failed", true);
      return;
    }

    setStatus(
      reapply
        ? `Saved + re-applied (${data?.applied || 0} transactions)`
        : "Saved"
    );

    // 🔥 THIS LINE IS THE KEY
    await loadRules();

  } catch (e) {
    setStatus("Save failed", true);
  } finally {
    btn.disabled = false;
  }
};

      // Active toggle
      tr.querySelector(".active-toggle").onchange = async (ev) => {
        const desired = !!ev.target.checked;
        try {
          const resp = await fetch(`/category-rules/${id}/active`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ is_active: desired }),
          });
          const data = await resp.json();
          if (!resp.ok || data?.ok === false) {
            setStatus(data?.error || "Failed to update rule", true);
            ev.target.checked = !desired;
            return;
          }
          setStatus(desired ? "Rule enabled" : "Rule disabled");
        } catch (e) {
          setStatus("Failed to update rule", true);
          ev.target.checked = !desired;
        }
      };

      // Test
      tr.querySelector(".test-btn").onclick = () => {
        openTestModal({ pattern: r.pattern, flags: r.flags || "i", ruleId: id });
      };

      // Delete
      tr.querySelector(".delete-btn").onclick = async () => {
        const btn = tr.querySelector(".delete-btn");
        btn.disabled = true;
        try {
          const resp = await fetch(`/category-rules/${id}`, { method: "DELETE" });
          const data = await resp.json();
          if (!resp.ok || data?.ok === false) {
            setStatus(data?.error || "Delete failed", true);
            return;
          }
          tr.remove();
          setStatus("Rule deleted");
        } catch (e) {
          setStatus("Delete failed", true);
        } finally {
          btn.disabled = false;
        }
      };

      tbody.appendChild(tr);
    }

    setStatus(`Loaded ${rules.length} rules`);
  } catch (e) {
    setStatus("Failed to load rules", true);
  }
}

function initModal() {
  const modal = document.getElementById("ruleTestModal");
  if (!modal) return;

  document.getElementById("closeTestModal").onclick = closeTestModal;
  document.getElementById("runTestBtn").onclick = runTest;

  // click outside closes
  modal.addEventListener("click", (e) => {
    if (e.target === modal) closeTestModal();
  });

  // escape closes
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !modal.hidden) closeTestModal();
  });
}

function initToolbar() {
  const btn = document.getElementById("refreshRulesBtn");
  if (btn) btn.onclick = loadRules;
}

(async function boot() {
  initModal();
  initToolbar();
  await fetchCategories();
  await loadRules();
})();
