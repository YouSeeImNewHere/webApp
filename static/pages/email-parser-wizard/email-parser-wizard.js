(function () {
  const state = {
    accounts: [],
    accountSettings: [],
    samples: [],
    selectedSampleIds: new Set(),
    primarySampleId: "",
    previewRows: [],
    usingMock: false,
  };
  const UI_PREFS_KEY = "epw:ui-prefs:v2";

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

  function updateParsingMethodLabel() {
    const toggle = byId("epwParsingMethodToggle");
    const label = byId("epwParsingMethodLabel");
    if (!toggle || !label) return;
    label.textContent = toggle.checked ? "Anchor-based parsing" : "Flexible parsing";
  }

  function setHelpOpen(open) {
    const panel = byId("epwGuideHelpPanel");
    const btn = byId("epwHelpToggleBtn");
    if (!panel || !btn) return;
    panel.classList.toggle("hidden", !open);
    btn.setAttribute("aria-expanded", open ? "true" : "false");
  }

  function applyParserModeVisibility() {
    const mode = byId("epwParserMode")?.value || "guided";
    const adv = byId("epwAdvancedFields");
    const guidedLayout = byId("epwGuidedLayout")?.closest(".epw-field");
    const parsingMethod = byId("epwParsingMethodToggle")?.closest(".epw-field");
    const parsingTypeHelp = byId("epwParsingTypeHelp");
    const guidedFields = byId("epwGuidedFields");
    if (adv) adv.classList.toggle("hidden", mode !== "advanced");
    if (guidedLayout) guidedLayout.style.display = mode === "guided" ? "" : "none";
    if (parsingMethod) parsingMethod.style.display = mode === "guided" ? "" : "none";
    if (parsingTypeHelp) parsingTypeHelp.style.display = mode === "guided" ? "" : "none";
    if (guidedFields) guidedFields.style.display = mode === "guided" ? "" : "none";
  }

  function saveUiPrefs() {
    const parserMode = (byId("epwParserMode")?.value || "guided").trim();
    const guidedLayout = (byId("epwGuidedLayout")?.value || "list").trim();
    const parsingMethod = byId("epwParsingMethodToggle")?.checked ? "anchor" : "flexible";
    try {
      localStorage.setItem(UI_PREFS_KEY, JSON.stringify({
        parser_mode: parserMode,
        guided_layout: guidedLayout,
        parsing_method: parsingMethod,
      }));
    } catch (_e) {
      // Ignore storage failures in private mode or restricted contexts.
    }
  }

  function loadUiPrefs() {
    let prefs = null;
    try {
      prefs = JSON.parse(localStorage.getItem(UI_PREFS_KEY) || "null");
    } catch (_e) {
      prefs = null;
    }
    if (!prefs || typeof prefs !== "object") return;
    if (prefs.parser_mode && byId("epwParserMode")) {
      byId("epwParserMode").value = String(prefs.parser_mode);
    }
    if (prefs.guided_layout && byId("epwGuidedLayout")) {
      byId("epwGuidedLayout").value = String(prefs.guided_layout);
    }
    if (byId("epwParsingMethodToggle")) {
      byId("epwParsingMethodToggle").checked = String(prefs.parsing_method || "anchor") === "anchor";
    }
  }

  function renderAccounts() {
    const sel = byId("epwAccount");
    if (!sel) return;
    const options = ['<option value="">Select account</option>'].concat(state.accounts.map((a) => {
      const hasSetting = !!a.has_parser_setting;
      const marker = hasSetting ? "🟢" : "🟠";
      const status = hasSetting ? "configured" : "needs setup";
      const label = `${marker} ${a.institution || "Unknown"} - ${a.name || "Account"} (#${a.id}) [${status}]`;
      return `<option value="${a.id}">${escapeHtml(label)}</option>`;
    }));
    sel.innerHTML = options.join("");
    if (!sel.value && state.accounts.length) {
      sel.value = String(state.accounts[0].id);
    }
  }

  function applySettingToForm(setting) {
    if (!setting || typeof setting !== "object") return;
    const subject = String(setting.subject_contains || "").trim();
    const sender = String(setting.sender_pattern || "").trim();
    if (subject) {
      byId("epwSubjectQuery").value = subject;
    }
    if (sender) {
      byId("epwSenderQuery").value = sender;
    }
    if (setting.parser_mode && byId("epwParserMode")) byId("epwParserMode").value = String(setting.parser_mode);
    if (setting.parsing_method && byId("epwParsingMethodToggle")) {
      byId("epwParsingMethodToggle").checked = String(setting.parsing_method).toLowerCase() === "anchor";
      updateParsingMethodLabel();
    }
    if (setting.body_regex && byId("epwBodyRegex")) byId("epwBodyRegex").value = String(setting.body_regex);
    if (setting.flags && byId("epwRegexFlags")) byId("epwRegexFlags").value = String(setting.flags);
    const fm = (setting.field_map && typeof setting.field_map === "object") ? setting.field_map : {};
    if (Number(fm.amount_group) > 0) byId("epwMapAmount").value = String(Number(fm.amount_group));
    if (Number(fm.merchant_group) > 0) byId("epwMapMerchant").value = String(Number(fm.merchant_group));
    if (Number(fm.date_group) > 0) byId("epwMapDate").value = String(Number(fm.date_group));
    if (Number(fm.time_group) >= 0) byId("epwMapTime").value = String(Number(fm.time_group));
    const guided = (setting.guided && typeof setting.guided === "object") ? setting.guided : {};
    if (guided.amount_label) byId("epwGuidedAmountLabel").value = String(guided.amount_label);
    if (guided.merchant_label) byId("epwGuidedMerchantLabel").value = String(guided.merchant_label);
    if (guided.date_label) byId("epwGuidedDateLabel").value = String(guided.date_label);
    if (guided.time_label) byId("epwGuidedTimeLabel").value = String(guided.time_label);
    if (guided.layout_type && byId("epwGuidedLayout")) byId("epwGuidedLayout").value = String(guided.layout_type);
    applyParserModeVisibility();
    renderLiveCapture();
  }

  function renderSubjectSettings() {
    const wrap = byId("epwSubjectSettingWrap");
    const sel = byId("epwSubjectSetting");
    if (!wrap || !sel) return;
    const settings = Array.isArray(state.accountSettings) ? state.accountSettings : [];
    if (!settings.length) {
      wrap.style.display = "none";
      sel.innerHTML = "";
      return;
    }
    if (settings.length === 1) {
      wrap.style.display = "none";
      sel.innerHTML = "";
      applySettingToForm(settings[0]);
      return;
    }
    wrap.style.display = "";
    const options = ['<option value="">Select subject setting</option>'].concat(settings.map((s) => {
      const subject = String(s.subject_contains || "").trim() || "(blank subject)";
      const name = String(s.name || "").trim();
      const label = name ? `${subject} - ${name}` : subject;
      return `<option value="${escapeHtml(String(s.draft_id || ""))}">${escapeHtml(label)}</option>`;
    }));
    sel.innerHTML = options.join("");
  }

  async function loadAccountSettings() {
    const accountId = Number(byId("epwAccount")?.value || 0);
    state.accountSettings = [];
    renderSubjectSettings();
    if (!accountId || state.usingMock) return;
    try {
      const data = await fetchJson(`/email-parser/trial/account-settings/${accountId}`, { cache: "no-store" });
      state.accountSettings = Array.isArray(data.settings) ? data.settings : [];
      renderSubjectSettings();
    } catch (_e) {
      state.accountSettings = [];
      renderSubjectSettings();
    }
  }

  function updateRuleSourceBody() {
    const bodyEl = byId("epwRuleSourceBody");
    const id = String(state.primarySampleId || "").trim();
    const s = (state.samples || []).find((x) => String(x.sample_id) === id);
    if (!bodyEl) {
      renderLiveCapture();
      return;
    }
    if (!s) {
      bodyEl.textContent = "Select a candidate in Step 2 to view its body here.";
      renderLiveCapture();
      return;
    }
    bodyEl.textContent = String(s.body || "");
    renderLiveCapture();
  }

  function buildLivePayload() {
    const payloadRaw = getDraftPayload();
    if (payloadRaw.parser_mode === "guided") {
      try {
        return { payload: buildRegexFromGuided(payloadRaw), error: "" };
      } catch (e) {
        return { payload: null, error: e?.message || "Invalid guided parser config." };
      }
    }
    if (!payloadRaw.body_regex) {
      return { payload: null, error: "Body regex is required in advanced mode." };
    }
    return { payload: payloadRaw, error: "" };
  }

  function timeFromReceivedAt(receivedAt) {
    const s = String(receivedAt || "").trim();
    if (!s) return "";
    const d = new Date(s);
    if (Number.isNaN(d.getTime())) return "";
    try {
      return new Intl.DateTimeFormat("en-US", {
        hour: "2-digit",
        minute: "2-digit",
        hour12: true,
        timeZoneName: "short",
      }).format(d).replace(",", "");
    } catch (_e) {
      return d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: true });
    }
  }

  function compileClientRegex(rawRegex, rawFlags) {
    let source = String(rawRegex || "");
    const merged = new Set(String(rawFlags || "i").split("").filter(Boolean));
    const m = source.match(/^\(\?([a-zA-Z]+)\)/);
    if (m) {
      source = source.slice(m[0].length);
      for (const ch of String(m[1] || "").toLowerCase()) {
        if ("ims".includes(ch)) merged.add(ch);
      }
    }
    const flags = Array.from(merged).filter((ch) => "dgimsuy".includes(ch)).join("");
    return new RegExp(source, flags || "i");
  }

  function safeExtract(body, payload, receivedAt) {
    let rx = null;
    try {
      rx = compileClientRegex(payload.body_regex || "", payload.flags || "i");
    } catch (e) {
      return { matched: false, error: `Invalid regex: ${e.message}`, extracted: null };
    }
    const m = rx.exec(String(body || ""));
    if (!m) return { matched: false, error: "No match", extracted: null };
    const g = payload.field_map || {};
    return {
      matched: true,
      error: "",
      extracted: {
        amount: m[Number(g.amount_group) || 0] || "",
        merchant: m[Number(g.merchant_group) || 0] || "",
        date: m[Number(g.date_group) || 0] || "",
        time: ((Number(g.time_group) || 0) > 0 ? (m[Number(g.time_group)] || "") : "") || timeFromReceivedAt(receivedAt),
      },
    };
  }

  function highlightCapturedBody(body, extracted) {
    const text = String(body || "");
    const lower = text.toLowerCase();
    const needles = [
      String(extracted?.amount || "").trim(),
      String(extracted?.merchant || "").trim(),
      String(extracted?.date || "").trim(),
      String(extracted?.time || "").trim(),
    ].filter(Boolean);
    if (!needles.length) return escapeHtml(text);

    const ranges = [];
    const overlaps = (s, e) => ranges.some((r) => !(e <= r.s || s >= r.e));
    for (const rawNeedle of needles) {
      const needle = rawNeedle.toLowerCase();
      let from = 0;
      while (from < lower.length) {
        const idx = lower.indexOf(needle, from);
        if (idx < 0) break;
        const s = idx;
        const e = idx + needle.length;
        from = idx + 1;
        if (!overlaps(s, e)) {
          ranges.push({ s, e });
          break;
        }
      }
    }
    if (!ranges.length) return escapeHtml(text);

    ranges.sort((a, b) => a.s - b.s);
    let out = "";
    let pos = 0;
    for (const r of ranges) {
      if (r.s > pos) out += escapeHtml(text.slice(pos, r.s));
      out += `<mark class="epw-live-mark">${escapeHtml(text.slice(r.s, r.e))}</mark>`;
      pos = r.e;
    }
    if (pos < text.length) out += escapeHtml(text.slice(pos));
    return out;
  }

  function renderLiveCapture() {
    const statusEl = byId("epwLiveCaptureStatus");
    const fieldsEl = byId("epwLiveCaptureFields");
    const bodyEl = byId("epwLiveCaptureBody");
    if (!statusEl || !fieldsEl || !bodyEl) return;

    const id = String(state.primarySampleId || "").trim();
    const s = (state.samples || []).find((x) => String(x.sample_id) === id);
    if (!s) {
      statusEl.textContent = "Select a candidate in Step 2 to preview captures.";
      fieldsEl.innerHTML = "";
      bodyEl.textContent = "";
      return;
    }

    const fullBody = String(s.body || "");
    const displayBody = fullBody.slice(0, 12000);
    const truncated = fullBody.length > displayBody.length;
    const { payload, error } = buildLivePayload();
    if (!payload) {
      statusEl.textContent = error || "Fill rule fields to preview captures.";
      fieldsEl.innerHTML = "";
      bodyEl.textContent = displayBody;
      return;
    }

    const result = safeExtract(displayBody, payload, s.received_at);
    if (!result.matched) {
      statusEl.textContent = result.error || "No match";
      fieldsEl.innerHTML = "";
      bodyEl.textContent = displayBody;
      return;
    }

    const ext = result.extracted || {};
    statusEl.textContent = truncated ? "Matched (body preview truncated)." : "Matched live preview.";
    fieldsEl.innerHTML = `
      <div class="epw-live-grid">
        <div class="epw-live-item"><strong>Amount</strong><div>${escapeHtml(ext.amount || "")}</div></div>
        <div class="epw-live-item"><strong>Merchant</strong><div>${escapeHtml(ext.merchant || "")}</div></div>
        <div class="epw-live-item"><strong>Date</strong><div>${escapeHtml(ext.date || "")}</div></div>
        <div class="epw-live-item"><strong>Time</strong><div>${escapeHtml(ext.time || "")}</div></div>
      </div>
    `;
    bodyEl.innerHTML = highlightCapturedBody(displayBody, ext);
  }

  function previewRowById() {
    const map = new Map();
    for (const r of (state.previewRows || [])) {
      const id = String(r?.sample_id || "").trim();
      if (id) map.set(id, r);
    }
    return map;
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

    const previewById = previewRowById();
    host.innerHTML = state.samples.map((s) => {
      const sid = String(s.sample_id || "");
      const pr = previewById.get(sid);
      const hasResult = !!pr;
      const rowClass = !hasResult ? "" : (pr.matched ? "epw-row-match" : "epw-row-no-match");
      const resultChip = !hasResult
        ? ""
        : `<span class="epw-chip ${pr.matched ? "ok" : "bad"}">${pr.matched ? "Matched" : "No Match"}</span>`;
      const resultLine = !hasResult
        ? ""
        : `<div class="epw-row-sub">${escapeHtml(pr.matched ? "Passed preview rules" : (pr.error || "Did not match preview rules"))}</div>`;
      const checked = state.selectedSampleIds.has(String(s.sample_id)) ? "checked" : "";
      const primary = String(state.primarySampleId) === String(s.sample_id) ? "checked" : "";
      const subj = s.subject || "(no subject)";
      const sender = s.sender || "";
      const dt = s.received_at || "";
      const snip = s.snippet || "";
      const body = s.body || "";
      return `
        <label class="epw-row ${rowClass}" style="display:block; cursor:pointer;">
          <div class="epw-row-head">
            <div class="epw-row-title">${escapeHtml(subj)}</div>
            <div style="display:flex; align-items:center; gap:8px;">
              ${resultChip}
              <div class="epw-row-sub" style="margin-top:0;">${escapeHtml(dt)}</div>
            </div>
          </div>
          <div class="epw-row-sub">${escapeHtml(sender)}</div>
          ${resultLine}
          <div class="epw-snippet">${escapeHtml(snip)}</div>
          <div style="margin-top:8px;">
            <input type="checkbox" class="epw-sample-check" data-sample-id="${escapeHtml(String(s.sample_id))}" ${checked}>
            Include in preview
            <span style="margin-left:12px;">
              <input type="radio" name="epwPrimarySample" class="epw-primary-sample" data-sample-id="${escapeHtml(String(s.sample_id))}" ${primary}>
              Use in rule builder
            </span>
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
        else {
          state.selectedSampleIds.delete(id);
          if (String(state.primarySampleId) === id) {
            state.primarySampleId = Array.from(state.selectedSampleIds)[0] || "";
          }
        }
        meta.textContent = `${state.samples.length} samples loaded. ${state.selectedSampleIds.size} selected for preview.`;
        updateRuleSourceBody();
      });
    });

    host.querySelectorAll(".epw-primary-sample").forEach((node) => {
      node.addEventListener("change", () => {
        const id = String(node.getAttribute("data-sample-id") || "");
        if (!id || !node.checked) return;
        state.primarySampleId = id;
        state.selectedSampleIds.add(id);
        host.querySelectorAll(".epw-sample-check").forEach((c) => {
          if (String(c.getAttribute("data-sample-id") || "") === id) c.checked = true;
        });
        meta.textContent = `${state.samples.length} samples loaded. ${state.selectedSampleIds.size} selected for preview.`;
        updateRuleSourceBody();
      });
    });
    updateRuleSourceBody();
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
    const senderPattern = (byId("epwSenderQuery")?.value || "").trim();
    const subjectContains = (byId("epwSubjectQuery")?.value || "").trim();
    const parserMode = (byId("epwParserMode")?.value || "guided").trim();
    const bodyRegex = (byId("epwBodyRegex")?.value || "").trim();
    const flags = (byId("epwRegexFlags")?.value || "i").trim() || "i";
    const selectedAccount = (state.accounts || []).find((a) => Number(a.id) === Number(accountId));
    const accountLabel = selectedAccount ? `${selectedAccount.institution || "Account"} ${selectedAccount.name || ""}`.trim() : `Account ${accountId}`;
    const name = `${accountLabel} ${subjectContains || "Email Rule"}`.trim();
    const guidedLayout = (byId("epwGuidedLayout")?.value || "list").trim();
    const parsingMethod = byId("epwParsingMethodToggle")?.checked ? "anchor" : "flexible";

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
      layout_type: guidedLayout,
    };

    return {
      name,
      parser_mode: parserMode,
      parsing_method: parsingMethod,
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
    const layout = String(g.layout_type || "list").toLowerCase();
    const parsingMethod = String(payload.parsing_method || "anchor").toLowerCase();
    const strict = parsingMethod === "anchor";
    const amountL = escapeRegex(g.amount_label || "Amount");
    const merchantL = escapeRegex(g.merchant_label || "Merchant");
    const dateL = escapeRegex(g.date_label || "Date");
    const timeL = escapeRegex(g.time_label || "Time");
    const amountPattern = "(\\$?[-]?[\\d,]+\\.\\d{2})";
    const datePattern = "([A-Za-z]{3},?\\s+[A-Za-z]{3}\\s+\\d{1,2},\\s+\\d{4}|[A-Za-z]{3,9}\\s+\\d{1,2},\\s+\\d{4}|\\d{1,2}\\/\\d{1,2}\\/\\d{2,4})";
    const timePattern = "([0-1]?\\d:[0-5]\\d\\s*(?:AM|PM)(?:\\s*[A-Z]{2,4})?)";
    let bodyRegex = "";
    let fieldMap = { amount_group: 1, merchant_group: 2, date_group: 3, time_group: 4 };

    if (layout === "list") {
      if (strict) {
        bodyRegex =
          `(?is)(?=.*?${amountL}\\s*[:\\-]?\\s*${amountPattern})` +
          `(?=.*?${merchantL}\\s*[:\\-]?\\s*(.+?)(?:\\r?\\n|$))` +
          `(?=.*?${dateL}\\s*[:\\-]?\\s*${datePattern})` +
          (g.time_label ? `(?=.*?${timeL}\\s*[:\\-]?\\s*${timePattern})?` : "") +
          ".*";
      } else {
        bodyRegex =
          `(?is)(?=.*?(?:${amountL}\\s*[:\\-]?\\s*)?${amountPattern})` +
          `(?=.*?${merchantL}\\s*[:\\-]?\\s*(.+?)(?:\\r?\\n|$))` +
          `(?=.*?(?:${dateL}\\s*[:\\-]?\\s*)?${datePattern})` +
          ".*";
      }
    } else if (layout === "sentence") {
      bodyRegex =
        `(?is)(?:transaction\\s+for\\s+)?${amountPattern}.*?\\bat\\s+(.+?)\\s+` +
        `(?:at\\s+${timePattern}\\s+)?on\\s+${datePattern}`;
      fieldMap = { amount_group: 1, merchant_group: 2, date_group: 4, time_group: 3 };
    } else if (layout === "no_anchor") {
      bodyRegex =
        `(?is)(?:^|\\n)\\s*([^\\n$]{2,80})\\s*(?:\\r?\\n)+\\s*` +
        `${amountPattern}\\*?\\s*(?:\\r?\\n)+\\s*${datePattern}` +
        `(?:\\s+${timePattern})?`;
      fieldMap = { amount_group: 2, merchant_group: 1, date_group: 3, time_group: 4 };
    } else {
      throw new Error("Unsupported guided layout type.");
    }

    return {
      ...payload,
      body_regex: bodyRegex,
      flags: "is",
      field_map: fieldMap,
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
      rx = compileClientRegex(payload.body_regex || "", payload.flags || "i");
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
      const timeGroup = Number(g.time_group) || 0;
      const fallbackTime = timeFromReceivedAt(s.received_at);
      out.push({
        sample_id: s.sample_id,
        matched: true,
        extracted: {
          amount: m[g.amount_group] || "",
          merchant: m[g.merchant_group] || "",
          date: m[g.date_group] || "",
          time: (timeGroup > 0 ? (m[timeGroup] || "") : "") || fallbackTime,
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
    const subjectQuery = (byId("epwSubjectQuery")?.value || "").trim();
    const accountId = Number(byId("epwAccount")?.value || 0);
    const lookbackDays = Number(byId("epwLookbackDays")?.value || 30);
    const limit = Number(byId("epwSampleLimit")?.value || 40);
    const tryHtmlOnMissing = !!byId("epwTryHtmlMissing")?.checked;
    setStatus("Loading samples...", false);
    if (!accountId) {
      setStatus("Select an account first.", true);
      return;
    }
    if (!senderQuery) {
      setStatus("Enter a sender filter.", true);
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
          subject_query: subjectQuery,
          try_html_on_missing_fields: tryHtmlOnMissing,
          lookback_days: lookbackDays,
          limit: limit,
        }),
      });
      items = data.items || [];

      state.samples = items || [];
      state.selectedSampleIds = new Set((state.samples || []).map((s) => String(s.sample_id)));
      state.primarySampleId = state.samples.length ? String(state.samples[0].sample_id) : "";
      state.previewRows = [];
      renderSamples();
      renderPreview();
      setStatus(`Loaded ${items.length} samples.`, false);
    } catch (e) {
      renderSamples();
      setStatus(`Could not load samples from server (${e.message}).`, true);
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
      renderSamples();
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

  function wireEvents() {
    byId("epwLoadSamplesBtn")?.addEventListener("click", loadSamples);
    byId("epwPreviewBtn")?.addEventListener("click", runPreview);
    byId("epwSaveDraftBtn")?.addEventListener("click", saveDraft);
    byId("epwSenderQuery")?.addEventListener("change", () => {
      renderLiveCapture();
    });
    byId("epwAccount")?.addEventListener("change", async () => {
      await loadAccountSettings();
    });
    byId("epwSubjectSetting")?.addEventListener("change", () => {
      const id = String(byId("epwSubjectSetting")?.value || "").trim();
      if (!id) return;
      const s = (state.accountSettings || []).find((x) => String(x.draft_id) === id);
      if (s) applySettingToForm(s);
    });
    byId("epwParserMode")?.addEventListener("change", () => {
      applyParserModeVisibility();
      saveUiPrefs();
      renderLiveCapture();
    });
    byId("epwGuidedLayout")?.addEventListener("change", () => {
      saveUiPrefs();
      renderLiveCapture();
    });
    byId("epwParsingMethodToggle")?.addEventListener("change", () => {
      updateParsingMethodLabel();
      saveUiPrefs();
      renderLiveCapture();
    });
    [
      "epwBodyRegex",
      "epwRegexFlags",
      "epwMapAmount",
      "epwMapMerchant",
      "epwMapDate",
      "epwMapTime",
      "epwGuidedAmountLabel",
      "epwGuidedMerchantLabel",
      "epwGuidedDateLabel",
      "epwGuidedTimeLabel",
    ].forEach((id) => {
      byId(id)?.addEventListener("input", renderLiveCapture);
    });
    byId("epwHelpToggleBtn")?.addEventListener("click", () => {
      const isOpen = byId("epwHelpToggleBtn")?.getAttribute("aria-expanded") === "true";
      setHelpOpen(!isOpen);
    });
    byId("epwHelpCloseBtn")?.addEventListener("click", () => setHelpOpen(false));
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") setHelpOpen(false);
    });
  }

  async function init() {
    loadUiPrefs();
    wireEvents();
    applyParserModeVisibility();
    updateParsingMethodLabel();
    setHelpOpen(false);
    await loadAccounts();
    await loadAccountSettings();
    renderSamples();
    renderPreview();
    updateRuleSourceBody();
    renderLiveCapture();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
