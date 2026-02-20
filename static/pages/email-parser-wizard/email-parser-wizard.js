(function () {
  const state = {
    accounts: [],
    accountSettings: [],
    samples: [],
    selectedSampleIds: new Set(),
    primarySampleId: "",
    previewRows: [],
    corrRows: [],
    corrSummary: null,
    testRows: [],
    testSummary: null,
    usingMock: false,
    lastParserMode: "guided",
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

  function applyParserModeVisibility() {
    const mode = byId("epwParserMode")?.value || "guided";
    const adv = byId("epwAdvancedFields");
    const guidedFields = byId("epwGuidedFields");
    if (adv) adv.classList.toggle("hidden", mode !== "advanced");
    if (guidedFields) guidedFields.style.display = mode === "guided" ? "" : "none";
  }

  function syncGuidedEndTextInputs() {
    [
      ["epwGuidedAmountEnd", "epwGuidedAmountEndText"],
      ["epwGuidedMerchantEnd", "epwGuidedMerchantEndText"],
      ["epwGuidedDateEnd", "epwGuidedDateEndText"],
      ["epwGuidedTimeEnd", "epwGuidedTimeEndText"],
    ].forEach(([selId, textId]) => {
      const sel = byId(selId);
      const txt = byId(textId);
      if (!sel || !txt) return;
      txt.style.display = String(sel.value || "").toLowerCase() === "text" ? "" : "none";
    });
  }

  function syncSubjectFallbackVisibility() {
    const q = (byId("epwSubjectQuery")?.value || "").trim();
    const wrap = byId("epwSubjectFallbackWrap");
    if (!wrap) return;
    wrap.style.display = q ? "none" : "";
  }

  function saveUiPrefs() {
    const parserMode = (byId("epwParserMode")?.value || "guided").trim();
    try {
      localStorage.setItem(UI_PREFS_KEY, JSON.stringify({
        parser_mode: parserMode,
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
      if (byId("epwSubjectFallback")) byId("epwSubjectFallback").value = subject;
    }
    if (sender) {
      byId("epwSenderQuery").value = sender;
    }
    if (setting.parser_mode && byId("epwParserMode")) byId("epwParserMode").value = String(setting.parser_mode);
    if (setting.parser_slot && byId("epwParserSlot")) byId("epwParserSlot").value = String(setting.parser_slot);
    if (byId("epwPrimaryOverride")) byId("epwPrimaryOverride").checked = !!setting.override_on_primary;
    if (byId("epwBackupAssumeUnknown")) byId("epwBackupAssumeUnknown").checked = !!setting.backup_assume_unknown;
    if (setting.body_regex && byId("epwBodyRegex")) byId("epwBodyRegex").value = String(setting.body_regex);
    if (setting.flags && byId("epwRegexFlags")) byId("epwRegexFlags").value = String(setting.flags);
    const fm = (setting.field_map && typeof setting.field_map === "object") ? setting.field_map : {};
    if (Number(fm.amount_group) > 0) byId("epwMapAmount").value = String(Number(fm.amount_group));
    if (Number(fm.merchant_group) > 0) byId("epwMapMerchant").value = String(Number(fm.merchant_group));
    if (Number(fm.date_group) > 0) byId("epwMapDate").value = String(Number(fm.date_group));
    if (Number(fm.time_group) >= 0) byId("epwMapTime").value = String(Number(fm.time_group));
    const guided = (setting.guided && typeof setting.guided === "object") ? setting.guided : {};
    if (byId("epwGuidedAmountLabel")) byId("epwGuidedAmountLabel").value = String(guided.amount_label || "");
    if (byId("epwGuidedMerchantLabel")) byId("epwGuidedMerchantLabel").value = String(guided.merchant_label || "");
    if (byId("epwGuidedDateLabel")) byId("epwGuidedDateLabel").value = String(guided.date_label || "");
    if (byId("epwGuidedTimeLabel")) byId("epwGuidedTimeLabel").value = String(guided.time_label || "");
    if (byId("epwGuidedMerchantOrder")) byId("epwGuidedMerchantOrder").value = String(Number.isFinite(Number(guided.merchant_order)) ? Number(guided.merchant_order) : 0);
    if (byId("epwGuidedDateOrder")) byId("epwGuidedDateOrder").value = String(Number.isFinite(Number(guided.date_order)) ? Number(guided.date_order) : 0);
    if (byId("epwGuidedAmountOrder")) byId("epwGuidedAmountOrder").value = String(Number.isFinite(Number(guided.amount_order)) ? Number(guided.amount_order) : 0);
    if (byId("epwGuidedTimeOrder")) byId("epwGuidedTimeOrder").value = String(Number.isFinite(Number(guided.time_order)) ? Number(guided.time_order) : 0);
    if (byId("epwGuidedAmountEnd")) byId("epwGuidedAmountEnd").value = String(guided.amount_end || "auto");
    if (byId("epwGuidedMerchantEnd")) byId("epwGuidedMerchantEnd").value = String(guided.merchant_end || "auto");
    if (byId("epwGuidedDateEnd")) byId("epwGuidedDateEnd").value = String(guided.date_end || "auto");
    if (byId("epwGuidedTimeEnd")) byId("epwGuidedTimeEnd").value = String(guided.time_end || "auto");
    if (byId("epwGuidedAmountEndText")) byId("epwGuidedAmountEndText").value = String(guided.amount_end_text || "");
    if (byId("epwGuidedMerchantEndText")) byId("epwGuidedMerchantEndText").value = String(guided.merchant_end_text || "");
    if (byId("epwGuidedDateEndText")) byId("epwGuidedDateEndText").value = String(guided.date_end_text || "");
    if (byId("epwGuidedTimeEndText")) byId("epwGuidedTimeEndText").value = String(guided.time_end_text || "");
    if (byId("epwGuidedAccountBefore")) byId("epwGuidedAccountBefore").value = String(guided.account_before || "");
    if (byId("epwGuidedAccountExact")) byId("epwGuidedAccountExact").value = String(guided.account_exact || "");
    syncGuidedEndTextInputs();
    applyParserModeVisibility();
    syncSubjectFallbackVisibility();
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
      const slot = String(s.parser_slot || "primary").toLowerCase();
      const labelBase = name ? `${subject} - ${name}` : subject;
      const label = `${labelBase} [${slot}]`;
      return `<option value="${escapeHtml(String(s.draft_id || ""))}">${escapeHtml(label)}</option>`;
    }));
    sel.innerHTML = options.join("");
  }

  function renderCorrelationDraftSelectors() {
    const primarySel = byId("epwCorrPrimaryDraft");
    const secondarySel = byId("epwCorrSecondaryDraft");
    if (!primarySel || !secondarySel) return;
    const settings = Array.isArray(state.accountSettings) ? state.accountSettings : [];
    const options = ['<option value="">Select parser</option>'].concat(settings.map((s) => {
      const slot = String(s.parser_slot || "primary");
      const subject = String(s.subject_contains || "").trim() || "(blank subject)";
      const name = String(s.name || "").trim();
      const label = `${subject}${name ? ` - ${name}` : ""} [${slot}]`;
      return `<option value="${escapeHtml(String(s.draft_id || ""))}">${escapeHtml(label)}</option>`;
    }));
    primarySel.innerHTML = options.join("");
    secondarySel.innerHTML = options.join("");

    const primary = settings.find((s) => String(s.parser_slot || "").toLowerCase() === "primary");
    const secondary = settings.find((s) => String(s.parser_slot || "").toLowerCase() === "backup");
    if (primary) primarySel.value = String(primary.draft_id);
    if (secondary) secondarySel.value = String(secondary.draft_id);
  }

  function renderCorrelationPreview() {
    const summaryEl = byId("epwCorrSummary");
    const rowsEl = byId("epwCorrRows");
    if (!summaryEl || !rowsEl) return;
    if (!state.corrSummary) {
      summaryEl.textContent = "No correlation preview run yet.";
      rowsEl.innerHTML = "";
      return;
    }
    const s = state.corrSummary || {};
    summaryEl.textContent = `Pending=${s.pending || 0} | Resolved=${s.resolved || 0} | Immediate notify=${s.notify_immediate || 0} | Skipped notified=${s.skip_already_notified || 0}`;
    const rows = Array.isArray(state.corrRows) ? state.corrRows : [];
    rowsEl.innerHTML = rows.map((r) => {
      const notifyChip = r.notify ? '<span class="epw-chip ok">Notify</span>' : '<span class="epw-chip">No Notify</span>';
      const title = `${r.matched_rule || "none"} | ${r.action || ""} | ${r.tx_action || ""}`;
      const ext = r.extracted || {};
      const line = `amount=${ext.amount || ""} merchant=${ext.merchant || ""} date=${ext.date || ""} time=${ext.time || ""}`;
      return `
        <div class="epw-row">
          <div class="epw-row-head">
            <div class="epw-row-title">${escapeHtml(String(r.subject || "(no subject)"))}</div>
            ${notifyChip}
          </div>
          <div class="epw-row-sub">${escapeHtml(String(r.sender || ""))}</div>
          <div class="epw-row-sub">${escapeHtml(title)}</div>
          <div class="epw-row-sub">${escapeHtml(line)}</div>
        </div>
      `;
    }).join("");
  }

  async function loadAccountSettings() {
    const accountId = Number(byId("epwAccount")?.value || 0);
    state.accountSettings = [];
    state.corrRows = [];
    state.corrSummary = null;
    renderSubjectSettings();
    renderCorrelationPreview();
    if (!accountId || state.usingMock) return;
    try {
      const data = await fetchJson(`/email-parser/trial/account-settings/${accountId}`, { cache: "no-store" });
      state.accountSettings = Array.isArray(data.settings) ? data.settings : [];
      renderSubjectSettings();
      renderCorrelationDraftSelectors();
    } catch (_e) {
      state.accountSettings = [];
      renderSubjectSettings();
      renderCorrelationDraftSelectors();
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

  function extractGuidedDirect(body, guided, receivedAt) {
    const text = String(body || "");
    const amountRe = /(\$?[-]?[\d,]+\.\d{2})/i;
    const dateRe = /([A-Za-z]{3},?\s+[A-Za-z]{3}\s+\d{1,2},\s+\d{4}|[A-Za-z]{3,9}\s+\d{1,2},\s+\d{4}|\d{1,2}\/\d{1,2}\/\d{2,4})/i;
    const timeRe = /([0-1]?\d:[0-5]\d\s*(?:AM|PM)(?:\s*[A-Z]{2,4})?)/i;

    const ord = {
      amount: Number(guided?.amount_order || 0),
      merchant: Number(guided?.merchant_order || 0),
      date: Number(guided?.date_order || 0),
      time: Number(guided?.time_order || 0),
    };
    const ordered = ["amount", "merchant", "date", "time"]
      .filter((k) => Number(ord[k]) > 0)
      .sort((a, b) => Number(ord[a]) - Number(ord[b]));
    if (Number(ord.amount || 0) <= 0 && guidedAmountPresent(text, guided)) return null;
    if (!ordered.length) return null;

    const acctBefore = String(guided?.account_before || "").trim();
    const acctExact = String(guided?.account_exact || "").trim();
    if (acctBefore && acctExact) {
      const bpat = boundaryLabelPattern(acctBefore);
      const epat = escapeRegex(acctExact);
      const guard = new RegExp(`${bpat}\\s*[:\\-]?\\s*[^\\r\\n]*?${epat}`, "i");
      if (!guard.test(text)) return null;
    }

    function ownLineExtract(re, fromIdx) {
      const sub = text.slice(Math.max(0, fromIdx));
      const rx = new RegExp(`(?:^|\\r?\\n)\\s*${re.source}`, "i");
      const m = rx.exec(sub);
      if (!m) return null;
      const fullStart = Math.max(0, fromIdx) + m.index;
      const fullEnd = fullStart + m[0].length;
      return { value: String(m[1] || "").trim(), next: fullEnd };
    }

    function labelExtract(label, re, fromIdx) {
      const sub = text.slice(Math.max(0, fromIdx));
      const lpat = boundaryLabelPattern(label);
      const rx = new RegExp(`${lpat}\\s*[:\\-]?\\s*${re.source}`, "i");
      const m = rx.exec(sub);
      if (!m) return null;
      const fullStart = Math.max(0, fromIdx) + m.index;
      const fullEnd = fullStart + m[0].length;
      return { value: String(m[1] || "").trim(), next: fullEnd };
    }

    function merchantFrom(label, endMode, endText, fromIdx) {
      const sub = text.slice(Math.max(0, fromIdx));
      let startInSub = -1;
      if (label) {
        const lpat = boundaryLabelPattern(label);
        const m = new RegExp(`${lpat}\\s*[:\\-]?\\s*`, "i").exec(sub);
        if (!m) return null;
        startInSub = m.index + m[0].length;
      } else {
        const m = /(?:^|\r?\n)\s*([A-Za-z0-9][^\r\n]{1,140})/.exec(sub);
        if (!m) return null;
        startInSub = m.index + m[0].indexOf(m[1]);
      }
      const after = sub.slice(startInSub);
      const mode = String(endMode || "auto").toLowerCase();
      let end = -1;
      if (mode === "comma" || mode === "auto") end = after.search(/\s*,/);
      if (end < 0 && mode === "period") end = after.search(/\s*\./);
      if (end < 0 && mode === "newline") end = after.search(/\r?\n/);
      if (end < 0 && mode === "sentence_end") end = after.search(/[.!?]/);
      if (end < 0 && mode === "text") {
        const needle = String(endText || "").trim();
        if (needle) {
          const idx = after.toLowerCase().indexOf(needle.toLowerCase());
          if (idx >= 0) end = idx;
        }
      }
      if (end < 0 && mode === "auto") {
        end = after.search(/\s+(?:in\s+the\s+amount\s+of|amount\s+of|on\s+\d{1,2}\/\d{1,2}\/\d{2,4}|on\s+[A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})/i);
      }
      if (end < 0) end = Math.min(after.length, 160);
      const raw = String(after.slice(0, end)).trim();
      const clean = raw.replace(/^[\s,.:;|\-]+|[\s,.:;|\-]+$/g, "").replace(/\s{2,}/g, " ").trim();
      if (!clean || clean.length < 2 || !/[A-Za-z0-9]/.test(clean)) return null;
      return {
        value: clean,
        next: Math.max(0, fromIdx) + startInSub + end,
      };
    }

    const out = { amount: "Unknown", merchant: "Unknown", date: "", time: "" };
    let cursor = 0;
    for (const field of ordered) {
      if (field === "amount") {
        const label = String(guided?.amount_label || "").trim();
        let got = label ? (labelExtract(label, amountRe, cursor) || labelExtract(label, amountRe, 0)) : null;
        if (!got) got = ownLineExtract(amountRe, cursor) || ownLineExtract(amountRe, 0);
        if (!got) {
          const m = amountRe.exec(text);
          if (m) got = { value: String(m[1] || "").trim(), next: (m.index + m[0].length) };
        }
        if (!got) return null;
        out.amount = got.value;
        cursor = got.next;
      } else if (field === "date") {
        const label = String(guided?.date_label || "").trim();
        let got = label ? (labelExtract(label, dateRe, cursor) || labelExtract(label, dateRe, 0)) : null;
        if (!got) got = ownLineExtract(dateRe, cursor) || ownLineExtract(dateRe, 0);
        if (!got) {
          const m = dateRe.exec(text);
          if (m) got = { value: String(m[1] || "").trim(), next: (m.index + m[0].length) };
        }
        if (!got) return null;
        out.date = got.value;
        cursor = got.next;
      } else if (field === "time") {
        const label = String(guided?.time_label || "").trim();
        let got = label ? (labelExtract(label, timeRe, cursor) || labelExtract(label, timeRe, 0)) : null;
        if (!got) got = ownLineExtract(timeRe, cursor) || ownLineExtract(timeRe, 0);
        if (!got) {
          const m = timeRe.exec(text);
          if (m) got = { value: String(m[1] || "").trim(), next: (m.index + m[0].length) };
        }
        if (!got) {
          out.time = timeFromReceivedAt(receivedAt);
          continue;
        }
        out.time = got.value;
        cursor = got.next;
      } else if (field === "merchant") {
        const label = String(guided?.merchant_label || "").trim();
        const endText = String(guided?.merchant_end_text || "").trim();
        let got = merchantFrom(label, guided?.merchant_end, endText, cursor) || merchantFrom(label, guided?.merchant_end, endText, 0);
        if (!got && !label) got = merchantFrom("", guided?.merchant_end, endText, cursor) || merchantFrom("", guided?.merchant_end, endText, 0);
        if (!got) return null;
        let mv = String(got.value || "").trim();
        // For Description-style lines, prefer the trailing segment after " - ".
        if (/description:?/i.test(label) && /\s-\s/.test(mv)) {
          const parts = mv.split(/\s-\s/).map((x) => String(x || "").trim()).filter(Boolean);
          if (parts.length) mv = parts[parts.length - 1];
        }
        out.merchant = mv;
        cursor = got.next;
      }
    }
    if (!out.time) out.time = timeFromReceivedAt(receivedAt);
    if (!out.amount) out.amount = "Unknown";
    return out;
  }

  function safeExtract(body, payload, receivedAt) {
    function guidedAccountGuardPass(text, guided) {
      const acctBefore = String(guided?.account_before || "").trim();
      const acctExact = String(guided?.account_exact || "").trim();
      if (!(acctBefore && acctExact)) return true;
      try {
        const bpat = boundaryLabelPattern(acctBefore);
        const epat = escapeRegex(acctExact);
        const guard = new RegExp(`${bpat}\\s*[:\\-]?\\s*[^\\r\\n]*?${epat}`, "i");
        return guard.test(String(text || ""));
      } catch (_e) {
        return false;
      }
    }

    if (String(payload?.parser_mode || "").toLowerCase() === "guided") {
      const g0 = payload?.guided || {};
      if (Number(g0?.amount_order || 0) <= 0 && guidedAmountPresent(body, g0)) {
        return { matched: false, error: "Amount found but parser is set to unknown amount", extracted: null };
      }
      if (!guidedAccountGuardPass(body, payload?.guided || {})) {
        return { matched: false, error: "Account sequence guard failed", extracted: null };
      }
    }
    let rx = null;
    try {
      rx = compileClientRegex(payload.body_regex || "", payload.flags || "i");
    } catch (e) {
      return { matched: false, error: `Invalid regex: ${e.message}`, extracted: null };
    }
    let m = rx.exec(String(body || ""));
    if (!m) return { matched: false, error: "No match", extracted: null };
    const g = payload.field_map || {};
    const merchantGroup = Number(g.merchant_group) || 0;
    const merchantVal = merchantGroup > 0 ? (m[merchantGroup] || "") : "";
    const out = {
      matched: true,
      error: "",
      extracted: {
        amount: ((Number(g.amount_group) || 0) > 0 ? (m[Number(g.amount_group)] || "") : "") || "Unknown",
        merchant: merchantVal || "Unknown",
        date: m[Number(g.date_group) || 0] || "",
        time: ((Number(g.time_group) || 0) > 0 ? (m[Number(g.time_group)] || "") : "") || timeFromReceivedAt(receivedAt),
      },
    };
    const ext = out.extracted || {};
    ext.amount = String(ext.amount || "").trim();
    ext.date = String(ext.date || "").trim();
    ext.time = String(ext.time || "").trim();
    ext.merchant = String(ext.merchant || "").trim().replace(/^[\s,.:;|\-]+|[\s,.:;|\-]+$/g, "").replace(/\s{2,}/g, " ");
    const merchPrefix = String(payload?.guided?.merchant_label || "").trim().toLowerCase();
    if (merchPrefix && ext.merchant.toLowerCase().startsWith(`${merchPrefix} `)) {
      ext.merchant = ext.merchant.slice(merchPrefix.length).trim();
    }
    if (!ext.merchant || !/[A-Za-z0-9]/.test(ext.merchant) || ext.merchant.length < 2) {
      ext.merchant = "Unknown";
    }
    // Guided rescue pass: if merchant is still unknown, try a direct "text before + ends at" extraction.
    if (ext.merchant === "Unknown" && String(payload?.parser_mode || "").toLowerCase() === "guided") {
      const gcfg = payload?.guided || {};
      const mLabel = String(gcfg.merchant_label || "").trim();
      const mEnd = String(gcfg.merchant_end || "auto").toLowerCase();
      const mEndText = String(gcfg.merchant_end_text || "").trim();
      if (mLabel) {
        const lpat = boundaryLabelPattern(mLabel);
        let direct = null;
        try {
          if (mEnd === "comma" || mEnd === "auto") {
            direct = new RegExp(`${lpat}\\s+([^,\\r\\n]{2,140})(?=\\s*,)`, "i").exec(String(body || ""));
          }
          if (!direct && mEnd === "newline") {
            direct = new RegExp(`${lpat}\\s+([^\\r\\n]{2,140})(?=\\s*\\r?\\n)`, "i").exec(String(body || ""));
          }
          if (!direct && mEnd === "text" && mEndText) {
            direct = new RegExp(`${lpat}\\s+([\\s\\S]{2,140}?)(?=${escapeRegex(mEndText)})`, "i").exec(String(body || ""));
          }
          if (!direct) {
            direct = new RegExp(`${lpat}\\s+([^\\r\\n]{2,140})`, "i").exec(String(body || ""));
          }
        } catch (_e) {
          direct = null;
        }
        if (direct && direct[1]) {
          let mclean = String(direct[1] || "").trim().replace(/^[\s,.:;|\-]+|[\s,.:;|\-]+$/g, "").replace(/\s{2,}/g, " ");
          if (mclean.toLowerCase().startsWith(`${merchPrefix} `)) {
            mclean = mclean.slice(merchPrefix.length).trim();
          }
          if (mclean && /[A-Za-z0-9]/.test(mclean) && mclean.length >= 2) {
            ext.merchant = mclean;
          }
        }
      }
    }
    return out;
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
    syncAdvancedRegexFromGuided();
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

  function renderTestReport() {
    const summaryEl = byId("epwTestSummary");
    const rowsEl = byId("epwTestRows");
    if (!summaryEl || !rowsEl) return;
    if (!state.testSummary) {
      summaryEl.textContent = "No parser test run yet.";
      rowsEl.innerHTML = "";
      return;
    }
    const s = state.testSummary || {};
    summaryEl.textContent = `Parsers ${Number(s.parsers || 0)} | Fetched ${Number(s.fetched || 0)} | Matched ${Number(s.matched || 0)} | Skipped ${Number(s.skipped || 0)} | Would insert ${Number(s.would_insert || 0)} | Would skip insert ${Number(s.would_skip_insert || 0)}`;
    const rows = Array.isArray(state.testRows) ? state.testRows : [];
    rowsEl.innerHTML = rows.map((r) => {
      const ok = !!r.matched;
      const chipClass = ok ? "ok" : "bad";
      const chipLabel = ok ? "Matched" : "Skipped";
      const p = r.parser || {};
      const ext = r.extracted || {};
      const would = r.would_db_row || {};
      const parserLine = ok
        ? `parser=${p.name || "(unnamed)"} [${p.slot || ""}] id=${p.draft_id || ""} account=${p.account_label || p.account_id || ""}`
        : `reason=${r.skip_reason || "no_parser_match"}`;
      const extLine = ok
        ? `amount=${ext.amount || ""} merchant=${ext.merchant || ""} date=${ext.date || ""} time=${ext.time || ""}`
        : "";
      const dbLine = r.would_insert
        ? `DB -> account_id=${would.account_id} amount=${would.amount} merchant=${would.merchant} purchasedate=${would.purchasedate} time=${would.time} source=${would.source}`
        : `DB -> skipped (${r.skip_reason || "no_parser_match"})`;
      return `
        <div class="epw-row ${ok ? "epw-row-match" : "epw-row-no-match"}">
          <div class="epw-row-head">
            <div class="epw-row-title">${escapeHtml(String(r.subject || "(no subject)"))}</div>
            <span class="epw-chip ${chipClass}">${chipLabel}</span>
          </div>
          <div class="epw-row-sub">${escapeHtml(String(r.sender || ""))}</div>
          <div class="epw-row-sub">${escapeHtml(parserLine)}</div>
          ${extLine ? `<div class="epw-row-sub">${escapeHtml(extLine)}</div>` : ""}
          <div class="epw-row-sub">${escapeHtml(dbLine)}</div>
        </div>
      `;
    }).join("");
  }

  function getDraftPayload() {
    const accountId = Number(byId("epwAccount")?.value || 0);
    const senderPattern = (byId("epwSenderQuery")?.value || "").trim();
    const subjectContains = (byId("epwSubjectQuery")?.value || byId("epwSubjectFallback")?.value || "").trim();
    const parserMode = (byId("epwParserMode")?.value || "guided").trim();
    const bodyRegex = (byId("epwBodyRegex")?.value || "").trim();
    const flags = (byId("epwRegexFlags")?.value || "i").trim() || "i";
    const selectedAccount = (state.accounts || []).find((a) => Number(a.id) === Number(accountId));
    const accountLabel = selectedAccount ? `${selectedAccount.institution || "Account"} ${selectedAccount.name || ""}`.trim() : `Account ${accountId}`;
    const name = `${accountLabel} ${subjectContains || "Email Rule"}`.trim();
    const parserSlot = (byId("epwParserSlot")?.value || "primary").trim().toLowerCase();
    const overrideOnPrimary = !!byId("epwPrimaryOverride")?.checked;
    const backupAssumeUnknown = !!byId("epwBackupAssumeUnknown")?.checked;
    const parsingMethod = "guided_blocks";

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
      merchant_order: Number(byId("epwGuidedMerchantOrder")?.value || 0),
      date_order: Number(byId("epwGuidedDateOrder")?.value || 0),
      amount_order: Number(byId("epwGuidedAmountOrder")?.value || 0),
      time_order: Number(byId("epwGuidedTimeOrder")?.value || 0),
      amount_end: (byId("epwGuidedAmountEnd")?.value || "auto").trim(),
      merchant_end: (byId("epwGuidedMerchantEnd")?.value || "auto").trim(),
      date_end: (byId("epwGuidedDateEnd")?.value || "auto").trim(),
      time_end: (byId("epwGuidedTimeEnd")?.value || "auto").trim(),
      amount_end_text: (byId("epwGuidedAmountEndText")?.value || "").trim(),
      merchant_end_text: (byId("epwGuidedMerchantEndText")?.value || "").trim(),
      date_end_text: (byId("epwGuidedDateEndText")?.value || "").trim(),
      time_end_text: (byId("epwGuidedTimeEndText")?.value || "").trim(),
      account_before: (byId("epwGuidedAccountBefore")?.value || "").trim(),
      account_exact: (byId("epwGuidedAccountExact")?.value || "").trim(),
    };

    return {
      name,
      parser_mode: parserMode,
      parsing_method: parsingMethod,
      parser_slot: parserSlot,
      override_on_primary: overrideOnPrimary,
      backup_assume_unknown: backupAssumeUnknown,
      pending_ttl_minutes: 30,
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

  function guidedLabelPattern(v) {
    const parts = String(v || "")
      .trim()
      .split(/\s+/)
      .filter(Boolean)
      .map((p) => escapeRegex(p));
    if (!parts.length) return "";
    // Be tolerant to HTML/text normalization differences in sentence bodies.
    return parts.join("\\s+");
  }

  function boundaryLabelPattern(v) {
    const core = guidedLabelPattern(v);
    if (!core) return "";
    // Use non-word boundaries so labels with punctuation (e.g. "Description:")
    // still match reliably, while short labels like "at" don't match inside "that".
    return `(?<!\\w)${core}(?!\\w)`;
  }

  function guidedAmountPresent(text, guided) {
    const body = String(text || "");
    const label = String(guided?.amount_label || "").trim();
    const amountCore = "\\$?[-]?[\\d,]+\\.\\d{2}";
    try {
      if (label) {
        const lpat = boundaryLabelPattern(label);
        if (lpat) {
          return new RegExp(`${lpat}\\s*[:\\-]?\\s*${amountCore}`, "i").test(body);
        }
      }
      return new RegExp(amountCore, "i").test(body);
    } catch (_e) {
      return new RegExp(amountCore, "i").test(body);
    }
  }

  function buildRegexFromGuided(payload) {
    const g = payload.guided || {};
    const amountL = boundaryLabelPattern(g.amount_label || "");
    const merchantL = boundaryLabelPattern(g.merchant_label || "");
    const dateL = boundaryLabelPattern(g.date_label || "");
    const timeL = boundaryLabelPattern(g.time_label || "");
    const amountPattern = "(\\$?[-]?[\\d,]+\\.\\d{2})";
    const datePattern = "([A-Za-z]{3},?\\s+[A-Za-z]{3}\\s+\\d{1,2},\\s+\\d{4}|[A-Za-z]{3,9}\\s+\\d{1,2},\\s+\\d{4}|\\d{1,2}\\/\\d{1,2}\\/\\d{2,4})";
    const timePattern = "([0-1]?\\d:[0-5]\\d\\s*(?:AM|PM)(?:\\s*[A-Z]{2,4})?)";
    const orderMap = {
      merchant: Number(g.merchant_order || 0),
      date: Number(g.date_order || 0),
      amount: Number(g.amount_order || 0),
      time: Number(g.time_order || 0),
    };

    function prefixFor(labelEscaped) {
      if (!labelEscaped) return "";
      return `${labelEscaped}\\s*[:\\-]?\\s*`;
    }

    function delimSuffix(mode, textVal) {
      const m = String(mode || "auto").toLowerCase();
      if (m === "comma") return "(?=\\s*,)";
      if (m === "period") return "(?=\\s*\\.)";
      if (m === "newline") return "(?=\\s*\\r?\\n)";
      if (m === "sentence_end") return "(?=\\s*[.!?])";
      if (m === "text") {
        const t = String(textVal || "").trim();
        return t ? `(?=${escapeRegex(t)})` : "";
      }
      return "";
    }

    function segmentFor(key) {
      if (key === "amount") {
        if (!amountL) return `(?:^|\\r?\\n)\\s*${amountPattern}(?:\\s*(?:\\r?\\n|$))`;
        return `${prefixFor(amountL)}${amountPattern}${delimSuffix(g.amount_end, g.amount_end_text)}`;
      }
      if (key === "date") {
        if (!dateL) return `(?:^|\\r?\\n)\\s*${datePattern}(?:\\s*(?:\\r?\\n|$))`;
        return `${prefixFor(dateL)}${datePattern}${delimSuffix(g.date_end, g.date_end_text)}`;
      }
      if (key === "time") {
        if (!timeL) return `(?:^|\\r?\\n)\\s*${timePattern}(?:\\s*(?:\\r?\\n|$))`;
        return `${prefixFor(timeL)}${timePattern}${delimSuffix(g.time_end, g.time_end_text)}`;
      }
      if (key === "merchant") {
        const mend = String(g.merchant_end || "auto").toLowerCase();
        if (!merchantL) {
          return "(?:^|\\r?\\n)\\s*([A-Za-z0-9][^\\r\\n]{1,140}?[A-Za-z0-9])(?:\\s*(?:\\r?\\n|$))";
        }
        if (mend === "comma") {
          return `${prefixFor(merchantL)}([^,\\r\\n]{2,140}?)(?=\\s*,)`;
        }
        const sfx = delimSuffix(g.merchant_end, g.merchant_end_text) || "(?=\\r?\\n|\\s*,|\\s+in\\s+the\\s+amount\\s+of|\\s+amount\\s+of|$)";
        return `${prefixFor(merchantL)}([A-Za-z0-9][^\\r\\n]{1,140}?[A-Za-z0-9])${sfx}`;
      }
      return "";
    }

    const ordered = ["merchant", "date", "amount", "time"]
      .filter((k) => Number(orderMap[k]) > 0)
      .sort((a, b) => Number(orderMap[a]) - Number(orderMap[b]));

    if (!ordered.length) {
      throw new Error("Guided order must include at least one field.");
    }

    const fieldMap = { amount_group: 0, merchant_group: 0, date_group: 0, time_group: 0 };
    let groupIdx = 1;
    const segments = [];
    for (const key of ordered) {
      segments.push(segmentFor(key));
      fieldMap[`${key}_group`] = groupIdx;
      groupIdx += 1;
    }

    const bodyRegex = `${segments.join(".*?")}`;
    const amountUnknownGuard = Number(orderMap.amount || 0) <= 0
      ? (() => {
          const amountCore = "\\$?[-]?[\\d,]+\\.\\d{2}";
          const amountLbl = boundaryLabelPattern(g.amount_label || "");
          const guardNeedle = amountLbl
            ? `${amountLbl}\\s*[:\\-]?\\s*${amountCore}`
            : amountCore;
          return `(?![\\s\\S]*${guardNeedle})`;
        })()
      : "";
    const acctBefore = String(g?.account_before || "").trim();
    const acctExact = String(g?.account_exact || "").trim();
    let scopedRegex = `(?is)${amountUnknownGuard}${bodyRegex}`;
    if (acctBefore && acctExact) {
      const bpat = boundaryLabelPattern(acctBefore);
      const epat = escapeRegex(acctExact);
      scopedRegex = `(?is)${amountUnknownGuard}(?=.*?${bpat}\\s*[:\\-]?\\s*[^\\r\\n]*?${epat}).*?${segments.join(".*?")}`;
    }

    return {
      ...payload,
      body_regex: scopedRegex,
      flags: "is",
      field_map: fieldMap,
    };
  }

  function syncAdvancedRegexFromGuided(force = false) {
    const mode = String(byId("epwParserMode")?.value || "guided").trim().toLowerCase();
    if (!force && mode !== "guided") return;
    const payloadRaw = getDraftPayload();
    try {
      const built = buildRegexFromGuided(payloadRaw);
      if (byId("epwBodyRegex")) byId("epwBodyRegex").value = String(built.body_regex || "");
      if (byId("epwRegexFlags")) byId("epwRegexFlags").value = String(built.flags || "is");
      if (byId("epwMapAmount")) byId("epwMapAmount").value = String(Number(built?.field_map?.amount_group || 0));
      if (byId("epwMapMerchant")) byId("epwMapMerchant").value = String(Number(built?.field_map?.merchant_group || 0));
      if (byId("epwMapDate")) byId("epwMapDate").value = String(Number(built?.field_map?.date_group || 0));
      if (byId("epwMapTime")) byId("epwMapTime").value = String(Number(built?.field_map?.time_group || 0));
    } catch (_e) {
      // Keep current advanced values if guided config is temporarily incomplete.
    }
  }

  function buildGuidedGenericFallback(payload) {
    const g = payload?.guided || {};
    const amountPattern = "(\\$?[-]?[\\d,]+\\.\\d{2})";
    const datePattern = "([A-Za-z]{3},?\\s+[A-Za-z]{3}\\s+\\d{1,2},\\s+\\d{4}|[A-Za-z]{3,9}\\s+\\d{1,2},\\s+\\d{4}|\\d{1,2}\\/\\d{1,2}\\/\\d{2,4})";
    const timePattern = "([0-1]?\\d:[0-5]\\d\\s*(?:AM|PM)(?:\\s*[A-Z]{2,4})?)";
    const merchantPattern = "([A-Za-z0-9][^\\n]{1,120}?[A-Za-z0-9])";
    const ord = {
      merchant: Number(g.merchant_order || 0),
      date: Number(g.date_order || 0),
      amount: Number(g.amount_order || 0),
      time: Number(g.time_order || 0),
    };
    const ordered = ["merchant", "date", "amount", "time"]
      .filter((k) => Number(ord[k]) > 0)
      .sort((a, b) => Number(ord[a]) - Number(ord[b]));
    if (!ordered.length) return null;

    const fieldMap = { amount_group: 0, merchant_group: 0, date_group: 0, time_group: 0 };
    let gi = 1;
    const segs = [];
    for (const k of ordered) {
      if (k === "amount") segs.push(amountPattern);
      if (k === "date") segs.push(datePattern);
      if (k === "time") segs.push(timePattern);
      if (k === "merchant") segs.push(merchantPattern);
      fieldMap[`${k}_group`] = gi++;
    }
    const amountUnknownGuard = Number(ord.amount || 0) <= 0
      ? (() => {
          const amountCore = "\\$?[-]?[\\d,]+\\.\\d{2}";
          const amountLbl = boundaryLabelPattern(g.amount_label || "");
          const guardNeedle = amountLbl
            ? `${amountLbl}\\s*[:\\-]?\\s*${amountCore}`
            : amountCore;
          return `(?![\\s\\S]*${guardNeedle})`;
        })()
      : "";
    return {
      ...payload,
      body_regex: `(?is)${amountUnknownGuard}${segs.join(".*?")}`,
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
    const ids = new Set((payload.sample_ids || []).map((x) => String(x)));
    const selected = state.samples.filter((s) => ids.has(String(s.sample_id)));

    for (const s of selected) {
      const body = String(s.body || "");
      const res = safeExtract(body, payload, s.received_at);
      out.push({
        sample_id: s.sample_id,
        matched: !!res.matched,
        extracted: res.extracted || null,
        error: res.matched ? "" : (res.error || "No match"),
      });
    }
    return out;
  }

  async function loadAccounts() {
    try {
      const data = await fetchJson("/email-parser/trial/accounts", { cache: "no-store" });
      state.accounts = data.accounts || [];
      state.usingMock = false;
      setStatus("Connected to parser endpoints.", false);
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
        setStatus("Account endpoint unavailable. Loaded accounts from your workspace.", false);
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
      state.corrRows = [];
      state.corrSummary = null;
      renderSamples();
      renderPreview();
      renderCorrelationPreview();
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

  async function runParserTest() {
    const lookbackDays = 7;
    const limit = 500;
    const tryHtmlOnMissing = !!byId("epwTryHtmlMissing")?.checked;
    if (state.usingMock) {
      setStatus("Parser test requires live parser endpoints.", true);
      return;
    }
    setStatus("Fetching all emails from last 7 days and testing all saved parsers across all accounts...", false);
    try {
      const out = await fetchJson("/email-parser/trial/test-run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          sender_query: "",
          subject_query: "",
          try_html_on_missing_fields: tryHtmlOnMissing,
          lookback_days: lookbackDays,
          limit: limit,
        }),
      });
      state.testSummary = out.summary || {};
      state.testRows = Array.isArray(out.rows) ? out.rows : [];
      renderTestReport();
      setStatus("Parser test complete.", false);
    } catch (e) {
      setStatus(`Parser test failed: ${e.message}`, true);
    }
  }

  async function saveDraft() {
    const payloadRaw = getDraftPayload();
    if (!payloadRaw.name) {
      setStatus("Parser name is required.", true);
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
      setStatus("Parser name is required.", true);
      return;
    }
    payload.status = "trial_inactive";
    payload.parser_mode = payloadRaw.parser_mode;
    payload.guided = payloadRaw.guided;

    setStatus("Saving parser...", false);
    try {
      if (!state.usingMock) {
        await fetchJson("/email-parser/trial/save", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        await loadAccountSettings();
      }
      setStatus(state.usingMock ? "Parser validated locally (mock mode)." : "Parser saved.", false);
    } catch (e) {
      setStatus(`Save failed: ${e.message}`, true);
    }
  }

  async function resetAllDrafts() {
    const ok = window.confirm("Delete all saved parsers and start fresh?");
    if (!ok) return;
    setStatus("Deleting parsers...", false);
    try {
      const data = await fetchJson("/email-parser/trial/drafts/reset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      await loadAccountSettings();
      state.corrRows = [];
      state.corrSummary = null;
      renderCorrelationPreview();
      setStatus(`Deleted ${Number(data.deleted || 0)} parsers.`, false);
    } catch (e) {
      setStatus(`Delete parsers failed: ${e.message}`, true);
    }
  }

  async function runCorrelationPreview() {
    const accountId = Number(byId("epwAccount")?.value || 0);
    const primaryDraftId = Number(byId("epwCorrPrimaryDraft")?.value || 0);
    const secondaryDraftId = Number(byId("epwCorrSecondaryDraft")?.value || 0);
    const sampleIds = Array.from(state.selectedSampleIds || []);
    if (!accountId) {
      setStatus("Select an account first.", true);
      return;
    }
    if (!primaryDraftId || !secondaryDraftId) {
      setStatus("Select both primary and backup parsers.", true);
      return;
    }
    if (!sampleIds.length) {
      setStatus("Select at least one sample.", true);
      return;
    }
    setStatus("Running correlation preview...", false);
    try {
      const data = await fetchJson("/email-parser/trial/correlation-preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          account_id: accountId,
          primary_draft_id: primaryDraftId,
          secondary_draft_id: secondaryDraftId,
          sample_ids: sampleIds,
        }),
      });
      const summary = data.summary || {};
      state.corrRows = Array.isArray(data.rows) ? data.rows : [];
      state.corrSummary = {
        pending: Number(summary.pending || 0),
        resolved: Number(summary.resolved || 0),
        notify_immediate: Number(summary.notify_immediate || 0),
        skip_already_notified: Number(summary.skip_already_notified || 0),
      };
      renderCorrelationPreview();
      setStatus("Correlation preview complete.", false);
    } catch (e) {
      setStatus(`Correlation preview failed: ${e.message}`, true);
    }
  }

  function wireEvents() {
    byId("epwLoadSamplesBtn")?.addEventListener("click", loadSamples);
    byId("epwTestParsersBtn")?.addEventListener("click", runParserTest);
    byId("epwPreviewBtn")?.addEventListener("click", runPreview);
    byId("epwCorrPreviewBtn")?.addEventListener("click", runCorrelationPreview);
    byId("epwSaveDraftBtn")?.addEventListener("click", saveDraft);
    byId("epwResetDraftsBtn")?.addEventListener("click", resetAllDrafts);
    byId("epwSenderQuery")?.addEventListener("change", () => {
      renderLiveCapture();
    });
    byId("epwSubjectQuery")?.addEventListener("input", () => {
      syncSubjectFallbackVisibility();
      renderLiveCapture();
    });
    byId("epwSubjectFallback")?.addEventListener("input", renderLiveCapture);
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
      const prevMode = String(state.lastParserMode || "guided").toLowerCase();
      const nextMode = String(byId("epwParserMode")?.value || "guided").toLowerCase();
      if (prevMode === "guided" && nextMode === "advanced") {
        syncAdvancedRegexFromGuided(true);
      }
      state.lastParserMode = nextMode;
      applyParserModeVisibility();
      saveUiPrefs();
      syncAdvancedRegexFromGuided();
      renderLiveCapture();
    });
    [
      "epwGuidedAmountEnd",
      "epwGuidedMerchantEnd",
      "epwGuidedDateEnd",
      "epwGuidedTimeEnd",
    ].forEach((id) => {
      byId(id)?.addEventListener("change", () => {
        syncGuidedEndTextInputs();
        renderLiveCapture();
      });
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
      "epwGuidedMerchantOrder",
      "epwGuidedDateOrder",
      "epwGuidedAmountOrder",
      "epwGuidedTimeOrder",
      "epwGuidedAmountEnd",
      "epwGuidedMerchantEnd",
      "epwGuidedDateEnd",
      "epwGuidedTimeEnd",
      "epwGuidedAmountEndText",
      "epwGuidedMerchantEndText",
      "epwGuidedDateEndText",
      "epwGuidedTimeEndText",
      "epwGuidedAccountBefore",
      "epwGuidedAccountExact",
    ].forEach((id) => {
      byId(id)?.addEventListener("input", () => {
        syncAdvancedRegexFromGuided();
        renderLiveCapture();
      });
      byId(id)?.addEventListener("change", () => {
        syncAdvancedRegexFromGuided();
        renderLiveCapture();
      });
    });
  }

  async function init() {
    loadUiPrefs();
    wireEvents();
    applyParserModeVisibility();
    state.lastParserMode = String(byId("epwParserMode")?.value || "guided").toLowerCase();
    syncGuidedEndTextInputs();
    syncSubjectFallbackVisibility();
    await loadAccounts();
    await loadAccountSettings();
    renderSamples();
    renderPreview();
    renderTestReport();
    renderCorrelationPreview();
    updateRuleSourceBody();
    syncAdvancedRegexFromGuided();
    renderLiveCapture();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
