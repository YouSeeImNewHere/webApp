// /static/pages/category-rules/category-rules.js
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
const RULES_PAGE_SIZE = 50;
let _rulesOffset = 0;
let _rulesHasMore = false;
let _rulesLoading = false;

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

function sleepMs(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitForRuleApplyJob(jobId, { timeoutMs = 10 * 60 * 1000, pollMs = 1500, onTick } = {}) {
  const started = Date.now();
  const id = Number(jobId || 0);
  if (!id) throw new Error("invalid_job_id");

  while ((Date.now() - started) < timeoutMs) {
    const res = await fetch(`/category-rules/jobs/${encodeURIComponent(String(id))}`, { cache: "no-store" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data?.ok === false) {
      throw new Error(data?.detail || data?.error || `job_status_failed_${res.status}`);
    }
    const job = data?.job || {};
    if (typeof onTick === "function") onTick(job);
    const status = String(job.status || "").toLowerCase();
    if (status === "completed") return job;
    if (status === "failed") throw new Error(job.error || "apply_failed");
    await sleepMs(pollMs);
  }
  throw new Error("job_timeout");
}

function renderCheckResults(data) {
  const host = document.getElementById("rulesCheckResults");
  if (!host) return;
  const rows = Array.isArray(data?.rows) ? data.rows : [];
  const checkedAt = data?.checked_at ? new Date(data.checked_at).toLocaleString() : "";
  const limitRows = rows.slice(0, 80);

  host.hidden = false;
  host.innerHTML = `
    <div>
      <b>Full check complete</b>
      <span class="settings-muted" style="margin-left:8px;">${esc(checkedAt)}</span>
      <span class="settings-muted" style="margin-left:8px;">Rules: ${esc(data?.rule_count ?? 0)}</span>
      <span class="settings-muted" style="margin-left:8px;">All matches: ${esc(data?.total_matches_all_rules ?? 0)}</span>
      <span class="settings-muted" style="margin-left:8px;">Uncategorized matches: ${esc(data?.total_uncategorized_matches_all_rules ?? 0)}</span>
      <span class="settings-muted" style="margin-left:8px;">Applied: ${esc(data?.total_applied ?? 0)}</span>
    </div>
    ${
      !limitRows.length
        ? `<div class="settings-muted">No rules found.</div>`
        : limitRows
            .map((r) => {
              const sampleTxt = (Array.isArray(r.samples) ? r.samples : [])
                .map((s) => `#${s.id} ${s.merchant}`)
                .join(" | ");
              const err = r.regex_error ? ` | error: ${esc(r.regex_error)}` : "";
              return `
                <div class="mono" style="font-size:12px; line-height:1.45;">
                  #${esc(r.id)} ${esc(r.category)} | matches=${esc(r.matches)} | total=${esc(r.total_matches)} | uncategorized=${esc(r.uncategorized_matches)} | applied=${esc(r.applied ?? 0)}${err}
                  ${sampleTxt ? `<div class="settings-muted" style="font-size:11px;">samples: ${esc(sampleTxt)}</div>` : ""}
                </div>
              `;
            })
            .join("")
    }
    ${rows.length > limitRows.length ? `<div class="settings-muted">Showing first ${limitRows.length} rules.</div>` : ""}
  `;
}

async function runFullCheck() {
  const btn = document.getElementById("runRulesCheckBtn");
  const onlyUncat = !!document.getElementById("checkUncategorizedOnly")?.checked;
  if (!btn) return;

  btn.disabled = true;
  setStatus("Running full rule check...");
  try {
    const p = new URLSearchParams();
    p.set("include_inactive", "1");
    p.set("uncategorized_only", onlyUncat ? "1" : "0");
    p.set("sample_limit", "2");
    p.set("apply_now", "1");
    const res = await fetch(`/category-rules/check-all?${p.toString()}`, { cache: "no-store" });
    const data = await res.json();
    if (!res.ok || data?.ok === false) {
      setStatus(data?.error || "Rule check failed", true);
      return;
    }
    renderCheckResults(data);
    setStatus(`Check complete: ${data?.rule_count || 0} rules, applied ${data?.total_applied || 0}`);
    await loadRules(true);
  } catch {
    setStatus("Rule check failed", true);
  } finally {
    btn.disabled = false;
  }
}

function isMobileRules() {
  return window.matchMedia && window.matchMedia("(max-width: 900px)").matches;
}

function ensureCardsHost() {
  const host = document.getElementById("rulesCards");
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
          <div class="test-badge">${r.matched ? "MATCH" : "-"}</div>
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

function getRuleFilters() {
  return {
    ruleId: (document.getElementById("ruleSearchId")?.value || "").trim(),
    keyword: (document.getElementById("ruleSearchKeyword")?.value || "").trim(),
    category: (document.getElementById("ruleSearchCategory")?.value || "").trim(),
  };
}

function updateLoadMoreButton() {
  const btn = document.getElementById("rulesLoadMoreBtn");
  if (!btn) return;
  btn.hidden = !_rulesHasMore;
  btn.disabled = _rulesLoading;
}

function clearRulesView() {
  const tbody = document.querySelector("#rulesTable tbody");
  const cardsHost = document.getElementById("rulesCards");
  if (tbody) tbody.innerHTML = "";
  if (cardsHost) cardsHost.innerHTML = "";
}

function getRenderTargets() {
  const tbody = document.querySelector("#rulesTable tbody");
  const cardsHost = document.getElementById("rulesCards");
  const mobile = isMobileRules();
  if (cardsHost) cardsHost.hidden = !mobile;
  return { tbody, cardsHost, mobile };
}

async function fetchRulesPage(offset, limit) {
  const f = getRuleFilters();
  const p = new URLSearchParams();
  p.set("include_inactive", "1");
  p.set("with_counts", "1");
  p.set("offset", String(offset));
  p.set("limit", String(limit));
  if (f.ruleId) p.set("rule_id", f.ruleId);
  if (f.keyword) p.set("keyword", f.keyword);
  if (f.category) p.set("category", f.category);

  const res = await fetch(`/category-rules/list?${p.toString()}`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error("Failed to load rules");
  return await res.json();
}

function attachRuleHandlers({ root, id, pattern, flags }) {
  const input = root.querySelector("input.settings-input");
  const saveBtn = root.querySelector(".save-btn");
  const testBtn = root.querySelector(".test-btn");
  const delBtn = root.querySelector(".delete-btn");
  const activeToggle = root.querySelector(".active-toggle");

  if (saveBtn && input) {
    saveBtn.onclick = async () => {
      saveBtn.disabled = true;

      try {
        const resp = await fetch(`/category-rules/${id}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            category: input.value,
            reapply_existing: true,
          }),
        });

        const data = await resp.json();
        if (!resp.ok || data?.ok === false) {
          setStatus(data?.error || "Save failed", true);
          return;
        }

        const jobId = Number(data?.apply_job?.id || 0);
        if (jobId > 0) {
          setStatus(`Saved. Re-apply queued (job #${jobId})...`);
          await loadRules(true);
          (async () => {
            try {
              const job = await waitForRuleApplyJob(jobId, {
                onTick: (j) => {
                  const st = String(j?.status || "").toLowerCase();
                  if (st === "in_progress") {
                    setStatus(`Re-applying in background (job #${jobId})...`);
                  }
                },
              });
              setStatus(`Saved + re-applied (${Number(job?.total_applied || 0)} transactions)`);
              await loadRules(true);
            } catch (err) {
              setStatus(`Saved, but re-apply failed: ${err?.message || "unknown"}`, true);
            }
          })();
          return;
        }

        setStatus(`Saved + re-applied (${data?.applied || 0} transactions)`);

        await loadRules(true);
      } catch (e) {
        setStatus("Save failed", true);
      } finally {
        saveBtn.disabled = false;
      }
    };
  }

  if (activeToggle) {
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
  }

  if (testBtn) {
    testBtn.onclick = () => {
      openTestModal({ pattern, flags: flags || "i", ruleId: id });
    };
  }

  if (delBtn) {
    delBtn.onclick = async () => {
      delBtn.disabled = true;
      try {
        const resp = await fetch(`/category-rules/${id}`, { method: "DELETE" });
        const data = await resp.json();
        if (!resp.ok || data?.ok === false) {
          setStatus(data?.error || "Delete failed", true);
          return;
        }
        root.remove();
        setStatus("Rule deleted");
      } catch (e) {
        setStatus("Delete failed", true);
      } finally {
        delBtn.disabled = false;
      }
    };
  }
}

function renderRulesChunk(rules) {
  const { tbody, cardsHost, mobile } = getRenderTargets();

  for (const r of rules) {
    const id = r.id;
    const isActive = !!r.is_active;
    const matchCount = Number(r.match_count || 0);

    if (mobile && cardsHost) {
      const card = document.createElement("div");
      card.className = "rule-card";
      card.innerHTML = `
        <div class="rule-regex">#${esc(r.id)} - ${esc(r.pattern)}</div>
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
            <span class="settings-muted">Always re-applies to existing</span>
          </div>

          <div class="rule-actions">
            <button class="settings-btn small save-btn">Save</button>
            <button class="settings-btn small test-btn">Test</button>
            <button class="settings-btn small danger delete-btn">Delete</button>
          </div>
        </div>
      `;

      attachRuleHandlers({ root: card, id, pattern: r.pattern, flags: r.flags });
      cardsHost.appendChild(card);
      continue;
    }

    if (!tbody) continue;

    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td class="mono">#${esc(r.id)} - ${esc(r.pattern)}</td>
      <td>
        <input
          class="settings-input"
          list="categoryOptions"
          value="${esc(r.category)}"
          data-id="${esc(r.id)}"
        />
        <div class="rule-subrow"><span class="settings-muted">Always re-applies to existing</span></div>
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

    attachRuleHandlers({ root: tr, id, pattern: r.pattern, flags: r.flags });
    tbody.appendChild(tr);
  }
}

async function loadRules(reset = false) {
  if (_rulesLoading) return;

  if (reset) {
    _rulesOffset = 0;
    _rulesHasMore = false;
    clearRulesView();
  }

  _rulesLoading = true;
  updateLoadMoreButton();
  setStatus(_rulesOffset === 0 ? "Loading rules..." : "Loading more...");

  try {
    const payload = await fetchRulesPage(_rulesOffset, RULES_PAGE_SIZE);
    const rules = Array.isArray(payload)
      ? payload
      : (Array.isArray(payload.rows) ? payload.rows : []);

    _rulesHasMore = !Array.isArray(payload) && !!payload?.has_more;

    if (_rulesOffset === 0 && !rules.length) {
      setStatus("No matching rules");
      updateLoadMoreButton();
      return;
    }

    renderRulesChunk(rules);
    _rulesOffset += rules.length;
    setStatus(`Loaded ${_rulesOffset}${_rulesHasMore ? "+" : ""} rule(s)`);
  } catch (e) {
    setStatus("Failed to load rules", true);
  } finally {
    _rulesLoading = false;
    updateLoadMoreButton();
  }
}

function debounce(fn, ms) {
  let t = null;
  return (...args) => {
    if (t) clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
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
  const refreshBtn = document.getElementById("refreshRulesBtn");
  if (refreshBtn) {
    refreshBtn.onclick = () => loadRules(true);
  }

  const loadMoreBtn = document.getElementById("rulesLoadMoreBtn");
  if (loadMoreBtn) {
    loadMoreBtn.onclick = () => loadRules(false);
  }
  const runCheckBtn = document.getElementById("runRulesCheckBtn");
  if (runCheckBtn) {
    runCheckBtn.onclick = runFullCheck;
  }

  const onSearch = debounce(() => loadRules(true), 250);
  ["ruleSearchId", "ruleSearchKeyword", "ruleSearchCategory"].forEach((id) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.addEventListener("input", onSearch);
    el.addEventListener("change", onSearch);
  });

  const host = ensureCardsHost();
  if (host) {
    const mm = window.matchMedia("(max-width: 900px)");
    const onModeChange = () => loadRules(true);
    if (typeof mm.addEventListener === "function") {
      mm.addEventListener("change", onModeChange);
    } else if (typeof mm.addListener === "function") {
      mm.addListener(onModeChange);
    }
  }
}

(async function boot() {
  initModal();
  initToolbar();
  await fetchCategories();
  await loadRules(true);
})();


