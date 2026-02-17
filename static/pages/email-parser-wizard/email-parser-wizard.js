(function () {
  const state = {
    accounts: [],
    samples: [],
    selectedSampleIds: new Set(),
    previewRows: [],
    usingMock: false,
  };

  function byId(id) {
    return document.getElementById(id);
  }

  function setStatus(msg, isError) {
    const el = byId("epwStatus");
    if (!el) return;
    el.textContent = msg || "";
    el.style.color = isError ? "#cc5a5a" : "";
  }

  async function fetchJson(url, options) {
    const res = await fetch(url, options || {});
    const text = await res.text();
    let body = {};
    try {
      body = text ? JSON.parse(text) : {};
    } catch (_e) {
      body = { raw: text };
    }
    if (!res.ok) {
      const msg = body.detail || body.error || `HTTP ${res.status}`;
      const err = new Error(msg);
      err.status = res.status;
      throw err;
    }
    return body;
  }

  function renderAccounts() {
    const sel = byId("epwAccount");
    if (!sel) return;
    const options = ['<option value="">Select account</option>'].concat(state.accounts.map((a) => {
      const label = `${a.institution || "Unknown"} - ${a.name || "Account"} (#${a.id})`;
      return `<option value="${a.id}">${escapeHtml(label)}</option>`;
    }));
    sel.innerHTML = options.join("");
    if (!sel.value && state.accounts.length) {
      sel.value = String(state.accounts[0].id);
    }
  }

  function renderSamples() {
    const host = byId("epwSamplesList");
    const meta = byId("epwSamplesMeta");
    if (!host || !meta) return;

    if (!state.samples.length) {
      meta.textContent = "No samples loaded yet.";
      host.innerHTML = "";
      return;
    }

    const selectedCount = state.selectedSampleIds.size;
    meta.textContent = `${state.samples.length} samples loaded. ${selectedCount} selected for preview.`;

    host.innerHTML = state.samples.map((s) => {
      const checked = state.selectedSampleIds.has(String(s.sample_id)) ? "checked" : "";
      const subj = s.subject || "(no subject)";
      const sender = s.sender || "";
      const dt = s.received_at || "";
      const snip = s.snippet || "";
      const body = s.body || "";
      return `
        <label class="epw-row" style="display:block; cursor:pointer;">
          <div class="epw-row-head">
            <div class="epw-row-title">${escapeHtml(subj)}</div>
            <div class="epw-row-sub">${escapeHtml(dt)}</div>
          </div>
          <div class="epw-row-sub">${escapeHtml(sender)}</div>
          <div class="epw-snippet">${escapeHtml(snip)}</div>
          <div style="margin-top:8px;">
            <input type="checkbox" class="epw-sample-check" data-sample-id="${escapeHtml(String(s.sample_id))}" ${checked}>
            Include in preview
          </div>
          <details class="epw-body-wrap">
            <summary>View full body</summary>
            <pre class="epw-body">${escapeHtml(body)}</pre>
          </details>
        </label>
      `;
    }).join("");

    host.querySelectorAll(".epw-sample-check").forEach((node) => {
      node.addEventListener("change", () => {
        const id = String(node.getAttribute("data-sample-id") || "");
        if (!id) return;
        if (node.checked) state.selectedSampleIds.add(id);
        else state.selectedSampleIds.delete(id);
        meta.textContent = `${state.samples.length} samples loaded. ${state.selectedSampleIds.size} selected for preview.`;
      });
    });
  }

  function renderPreview() {
    const host = byId("epwPreviewRows");
    const summary = byId("epwPreviewSummary");
    if (!host || !summary) return;

    if (!state.previewRows.length) {
      summary.textContent = "No preview run yet.";
      host.innerHTML = "";
      return;
    }

    const matched = state.previewRows.filter((r) => !!r.matched).length;
    summary.textContent = `Matched ${matched}/${state.previewRows.length} samples.`;

    host.innerHTML = state.previewRows.map((r) => {
      const chipClass = r.matched ? "ok" : "bad";
      const chipLabel = r.matched ? "Matched" : "No Match";
      const ext = r.extracted || {};
      const extLine = r.matched
        ? `amount=${ext.amount || ""} | merchant=${ext.merchant || ""} | date=${ext.date || ""} | time=${ext.time || ""}`
        : (r.error || "Regex did not match");
      return `
        <div class="epw-row">
          <div class="epw-row-head">
            <div class="epw-row-title">Sample ${escapeHtml(String(r.sample_id || ""))}</div>
            <span class="epw-chip ${chipClass}">${chipLabel}</span>
          </div>
          <div class="epw-row-sub">${escapeHtml(extLine)}</div>
        </div>
      `;
    }).join("");
  }

  function getDraftPayload() {
    const accountId = Number(byId("epwAccount")?.value || 0);
    const senderPattern = (byId("epwSenderPattern")?.value || "").trim();
    const subjectContains = (byId("epwSubjectContains")?.value || "").trim();
    const parserMode = (byId("epwParserMode")?.value || "guided").trim();
    const bodyRegex = (byId("epwBodyRegex")?.value || "").trim();
    const flags = (byId("epwRegexFlags")?.value || "i").trim() || "i";
    const name = (byId("epwDraftName")?.value || "").trim();

    const fieldMap = {
      amount_group: Number(byId("epwMapAmount")?.value || 0),
      merchant_group: Number(byId("epwMapMerchant")?.value || 0),
      date_group: Number(byId("epwMapDate")?.value || 0),
      time_group: Number(byId("epwMapTime")?.value || 0),
    };

    const guided = {
      amount_label: (byId("epwGuidedAmountLabel")?.value || "").trim(),
      merchant_label: (byId("epwGuidedMerchantLabel")?.value || "").trim(),
      date_label: (byId("epwGuidedDateLabel")?.value || "").trim(),
      time_label: (byId("epwGuidedTimeLabel")?.value || "").trim(),
    };

    return {
      name,
      parser_mode: parserMode,
      account_id: accountId,
      sender_pattern: senderPattern,
      subject_contains: subjectContains,
      body_regex: bodyRegex,
      flags,
      field_map: fieldMap,
      guided,
      sample_ids: Array.from(state.selectedSampleIds),
    };
  }

  function escapeRegex(v) {
    return String(v || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function buildRegexFromGuided(payload) {
    const g = payload.guided || {};
    if (!g.amount_label || !g.merchant_label || !g.date_label) {
      throw new Error("Guided mode requires Amount, Merchant, and Date labels.");
    }
    const amountL = escapeRegex(g.amount_label || "Amount");
    const merchantL = escapeRegex(g.merchant_label || "Merchant");
    const dateL = escapeRegex(g.date_label || "Date");
    const timeL = escapeRegex(g.time_label || "Time");

    const bodyRegex =
      `${amountL}\\s*[:\\-]?\\s*(\\$?[-]?[\\d,]+\\.\\d{2}).*?` +
      `${merchantL}\\s*[:\\-]?\\s*(.+?)\\s*(?:\\r?\\n|${dateL}\\s*[:\\-]?|${timeL}\\s*[:\\-]?|$).*?` +
      `${dateL}\\s*[:\\-]?\\s*([A-Za-z]{3,9}\\s+\\d{1,2},\\s+\\d{4}|\\d{1,2}\\/\\d{1,2}\\/\\d{2,4})` +
      `(?:.*?${timeL}\\s*[:\\-]?\\s*([0-1]?\\d:[0-5]\\d\\s*(?:AM|PM)))?`;

    return {
      ...payload,
      body_regex: bodyRegex,
      flags: "is",
      field_map: {
        amount_group: 1,
        merchant_group: 2,
        date_group: 3,
        time_group: 4,
      },
    };
  }

  function escapeHtml(v) {
    return String(v || "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function localPreview(payload) {
    const out = [];
    let rx = null;
    try {
      rx = new RegExp(payload.body_regex || "", payload.flags || "i");
    } catch (e) {
      return state.samples.map((s) => ({
        sample_id: s.sample_id,
        matched: false,
        extracted: null,
        error: `Invalid regex: ${e.message}`,
      }));
    }

    const ids = new Set((payload.sample_ids || []).map((x) => String(x)));
    const selected = state.samples.filter((s) => ids.has(String(s.sample_id)));

    for (const s of selected) {
      const body = String(s.body || "");
      const m = rx.exec(body);
      if (!m) {
        out.push({ sample_id: s.sample_id, matched: false, extracted: null, error: "No match" });
        continue;
      }
      const g = payload.field_map || {};
      out.push({
        sample_id: s.sample_id,
        matched: true,
        extracted: {
          amount: m[g.amount_group] || "",
          merchant: m[g.merchant_group] || "",
          date: m[g.date_group] || "",
          time: g.time_group > 0 ? (m[g.time_group] || "") : "",
        },
      });
    }
    return out;
  }

  async function loadAccounts() {
    try {
      const data = await fetchJson("/email-parser/trial/accounts", { cache: "no-store" });
      state.accounts = data.accounts || [];
      state.usingMock = false;
      setStatus("Connected to trial endpoints.", false);
    } catch (_e) {
      try {
        const bankInfo = await fetchJson("/bank-info", { cache: "no-store" });
        const checkingSavings = (bankInfo.accounts || []).map((a) => ({
          id: Number(a.account_id),
          institution: a.bank,
          name: a.name,
        }));
        const credits = (bankInfo.credit_cards || []).map((c) => ({
          id: Number(c.card_id),
          institution: c.bank,
          name: c.name,
        }));
        state.accounts = checkingSavings.concat(credits).filter((a) => Number.isFinite(a.id) && a.id > 0);
        state.usingMock = true;
        setStatus("Trial account endpoint unavailable. Loaded accounts from your workspace.", false);
      } catch (_e2) {
        state.accounts = [];
        state.usingMock = true;
        setStatus("No accounts found. Add accounts in Setup Wizard first.", true);
      }
    }
    renderAccounts();
  }

  async function loadSamples() {
    const senderQuery = (byId("epwSenderQuery")?.value || "").trim();
    const accountId = Number(byId("epwAccount")?.value || 0);
    const lookbackDays = Number(byId("epwLookbackDays")?.value || 30);
    const limit = Number(byId("epwSampleLimit")?.value || 40);
    setStatus("Loading samples...", false);
    if (!accountId) {
      setStatus("Select an account first.", true);
      return;
    }

    try {
      let items = [];
      const data = await fetchJson("/email-parser/trial/samples", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          account_id: accountId,
          sender_query: senderQuery,
          lookback_days: lookbackDays,
          limit: limit,
        }),
      });
      items = data.items || [];

      state.samples = items || [];
      if (!state.selectedSampleIds.size) {
        state.selectedSampleIds = new Set((state.samples || []).map((s) => String(s.sample_id)));
      }
      state.previewRows = [];
      renderSamples();
      renderPreview();
      setStatus(`Loaded ${items.length} samples.`, false);
    } catch (e) {
      renderSamples();
      setStatus(`Could not load samples from server (${e.message}). You can still add a manual sample below for testing.`, true);
    }
  }

  async function runPreview() {
    const payloadRaw = getDraftPayload();
    if (!payloadRaw.sample_ids.length) {
      setStatus("Select at least one sample.", true);
      return;
    }
    let payload;
    try {
      payload = payloadRaw.parser_mode === "guided"
        ? buildRegexFromGuided(payloadRaw)
        : payloadRaw;
    } catch (e) {
      setStatus(e.message || "Invalid guided parser config.", true);
      return;
    }
    if (!payload.body_regex) {
      setStatus("Body regex is required in advanced mode.", true);
      return;
    }

    setStatus("Running preview...", false);
    try {
      let rows;
      if (!state.usingMock) {
        const data = await fetchJson("/email-parser/trial/preview", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        rows = data.rows || [];
      } else {
        rows = localPreview(payload);
      }
      state.previewRows = rows;
      renderPreview();
      setStatus("Preview complete.", false);
    } catch (e) {
      setStatus(`Preview failed: ${e.message}`, true);
    }
  }

  async function saveDraft() {
    const payloadRaw = getDraftPayload();
    if (!payloadRaw.name) {
      setStatus("Draft name is required.", true);
      return;
    }
    if (!payloadRaw.account_id) {
      setStatus("Select an account.", true);
      return;
    }
    let payload;
    try {
      payload = payloadRaw.parser_mode === "guided"
        ? buildRegexFromGuided(payloadRaw)
        : payloadRaw;
    } catch (e) {
      setStatus(e.message || "Invalid guided parser config.", true);
      return;
    }
    if (!payloadRaw.name) {
      setStatus("Draft name is required.", true);
      return;
    }
    payload.status = "trial_inactive";
    payload.parser_mode = payloadRaw.parser_mode;
    payload.guided = payloadRaw.guided;

    setStatus("Saving draft...", false);
    try {
      if (!state.usingMock) {
        await fetchJson("/email-parser/trial/save", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
      }
      setStatus(state.usingMock ? "Draft validated locally (mock mode)." : "Draft saved as inactive trial config.", false);
    } catch (e) {
      setStatus(`Save failed: ${e.message}`, true);
    }
  }

  function addManualSample() {
    const body = (byId("epwManualBody")?.value || "").trim();
    if (!body) {
      setStatus("Paste a sample email body first.", true);
      return;
    }
    const subject = (byId("epwManualSubject")?.value || "").trim() || "(manual sample)";
    const sender = (byId("epwManualSender")?.value || "").trim() || (byId("epwSenderQuery")?.value || "").trim();
    const id = `manual_${Date.now()}`;
    const snippet = body.slice(0, 240);
    state.samples.unshift({
      sample_id: id,
      sender,
      subject,
      received_at: new Date().toISOString(),
      snippet,
      body,
    });
    state.selectedSampleIds.add(String(id));
    renderSamples();
    byId("epwManualBody").value = "";
    setStatus("Manual sample added.", false);
  }

  function wireEvents() {
    byId("epwLoadSamplesBtn")?.addEventListener("click", loadSamples);
    byId("epwPreviewBtn")?.addEventListener("click", runPreview);
    byId("epwSaveDraftBtn")?.addEventListener("click", saveDraft);
    byId("epwSenderQuery")?.addEventListener("change", () => {
      byId("epwSenderPattern").value = (byId("epwSenderQuery")?.value || "").trim();
    });
    byId("epwAddManualSampleBtn")?.addEventListener("click", addManualSample);
    byId("epwParserMode")?.addEventListener("change", () => {
      const mode = byId("epwParserMode")?.value || "guided";
      const adv = byId("epwAdvancedFields");
      if (adv) adv.classList.toggle("hidden", mode !== "advanced");
    });
  }

  async function init() {
    wireEvents();
    await loadAccounts();
    const adv = byId("epwAdvancedFields");
    if (adv) adv.classList.add("hidden");
    renderSamples();
    renderPreview();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
