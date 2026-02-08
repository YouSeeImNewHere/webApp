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

function isMobileRules() {
  return window.matchMedia && window.matchMedia("(max-width: 900px)").matches;
}

function ensureCardsHost() {
  let host = document.getElementById("rulesCards");
  if (!host) return null;
  return host;
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
  const cardsHost = document.getElementById("rulesCards");

  // Helpers (inline so this function is copy/paste safe)
  const isMobile = () =>
    window.matchMedia && window.matchMedia("(max-width: 900px)").matches;

  // Clear both render targets
  if (tbody) tbody.innerHTML = "";
  if (cardsHost) cardsHost.innerHTML = "";

  // Show/hide the right container
  if (cardsHost) cardsHost.hidden = !isMobile();

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
      const id = r.id;
      const isActive = !!r.is_active;
      const matchCount = Number(r.match_count || 0);

      // =========================
      // MOBILE: card layout
      // =========================
      if (isMobile() && cardsHost) {
        const card = document.createElement("div");
        card.className = "rule-card";
        card.innerHTML = `
          <div class="rule-regex">${esc(r.pattern)}</div>

          <div class="rule-row">
            <div class="rule-field">
              <label>Category</label>
              <input
                class="settings-input"
                list="categoryOptions"
                value="${esc(r.category)}"
              />
            </div>

            <div class="rule-meta">
              <div>
                <span class="settings-muted" style="margin:0;">Matches</span>
                <span class="pill mono" style="margin-left:8px;">${esc(matchCount)}</span>
              </div>

              <label class="switch" title="Enable/disable rule" style="margin:0;">
                <input type="checkbox" class="active-toggle" ${isActive ? "checked" : ""} />
                <span class="slider"></span>
              </label>
            </div>

            <div class="rule-toggles">
              <label class="toggle">
                <input type="checkbox" class="reapply-toggle" />
                <span>Re-apply to existing</span>
              </label>
            </div>

            <div class="rule-actions">
              <button class="settings-btn small save-btn">Save</button>
              <button class="settings-btn small test-btn">Test</button>
              <button class="settings-btn small danger delete-btn">Delete</button>
            </div>
          </div>
        `;

        const input = card.querySelector("input.settings-input");
        const saveBtn = card.querySelector(".save-btn");
        const testBtn = card.querySelector(".test-btn");
        const delBtn  = card.querySelector(".delete-btn");
        const activeToggle = card.querySelector(".active-toggle");
        const reapplyToggle = card.querySelector(".reapply-toggle");

        // Save (optionally re-apply)
        saveBtn.onclick = async () => {
          const reapply = !!reapplyToggle.checked;
          saveBtn.disabled = true;

          try {
            const resp = await fetch(`/category-rules/${id}`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                category: input.value,
                reapply_existing: reapply,
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

            await loadRules();
          } catch (e) {
            setStatus("Save failed", true);
          } finally {
            saveBtn.disabled = false;
          }
        };

        // Active toggle
        activeToggle.onchange = async (ev) => {
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
        testBtn.onclick = () => {
          openTestModal({ pattern: r.pattern, flags: r.flags || "i", ruleId: id });
        };

        // Delete
        delBtn.onclick = async () => {
          delBtn.disabled = true;
          try {
            const resp = await fetch(`/category-rules/${id}`, { method: "DELETE" });
            const data = await resp.json();
            if (!resp.ok || data?.ok === false) {
              setStatus(data?.error || "Delete failed", true);
              return;
            }
            card.remove();
            setStatus("Rule deleted");
          } catch (e) {
            setStatus("Delete failed", true);
          } finally {
            delBtn.disabled = false;
          }
        };

        cardsHost.appendChild(card);
        continue; // skip desktop row
      }

      // =========================
      // DESKTOP: table layout
      // =========================
      if (!tbody) continue;

      const tr = document.createElement("tr");
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
        <td><span class="pill mono">${esc(matchCount)}</span></td>
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
              reapply_existing: !!reapply,
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
