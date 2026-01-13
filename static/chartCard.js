// static/chartCard.js
(function () {
  // Builds the same chart card layout used on Home.
  // You can reuse on any page by providing IDs + options.
  window.mountChartCard = function mountChartCard(mountElOrSelector, cfg) {
    const mount =
      typeof mountElOrSelector === "string"
        ? document.querySelector(mountElOrSelector)
        : mountElOrSelector;

    if (!mount) return;

    const ids = cfg.ids;

    const showToggle = cfg.showToggle !== false;

    mount.innerHTML = `
      <section class="chart-card">
        <header class="chart-header chart-header--metrics2">
  <!-- LEFT: % Growth + (optional toggle) + Total -->
  <div class="chart-header-metrics">
<!-- TOTAL first -->
<div class="chart-breakdown chart-breakdown--metric">
  <span id="${ids.breakLabel}">${cfg.breakdownLabel || ""}</span>
  <strong id="${ids.breakValue}">${cfg.breakdownValue || "$0"}</strong>
</div>

<!-- % DIFF second (with toggle under it) -->
<div class="chart-metric-stack">
  ${ids.growthLabel && ids.growthValue ? `
    <div class="chart-breakdown chart-breakdown--metric">
      <span id="${ids.growthLabel}">% Diff</span>
      <strong id="${ids.growthValue}">—</strong>
    </div>

    ${cfg.growthToggleHtml ? `<div class="chart-growth-toggle">${cfg.growthToggleHtml}</div>` : ``}
  ` : ``}
</div>


  <!-- CENTER: Title + dots + Dates/Update -->
<!-- CENTER: title centered on chart -->
<div class="chart-header-center">
  <div class="chart-title-wrap">
    <h2 id="${ids.title}">${cfg.title || ""}</h2>
    <div id="${ids.dots}" class="chart-dots"></div>
  </div>
</div>

<!-- BETWEEN title and Next: Dates -->
<div class="chart-header-dates">
  <div class="chart-dates-inline chart-dates-inline--header">
    <label>Start <input type="date" id="${ids.start}"></label>
    <label>End <input type="date" id="${ids.end}"></label>
  </div>
  <button id="${ids.update}" class="chart-btn primary chart-update--header">
    Update
  </button>
</div>


  <!-- RIGHT: Next button -->
  <div class="chart-header-actions">
    ${
      showToggle
        ? `<button id="${ids.toggle}" class="chart-toggle chart-toggle--header">
            ${cfg.toggleText || ""}
          </button>`
        : ``
    }
  </div>
</header>



<div class="chart-controls chart-controls-grid2">
  <div class="chart-controls-center">
    <div id="${ids.quarters}" class="chart-btn-group chart-quarters"></div>

    <div class="chart-btn-group chart-year-group">
      <button id="${ids.yearBack}" class="chart-btn">◀</button>
      <span id="${ids.yearLabel}" class="chart-year"></span>
      <button id="${ids.yearFwd}" class="chart-btn">▶</button>
    </div>
  </div>

  ${cfg.extraControlsHtml ? `<div class="chart-controls-extra">${cfg.extraControlsHtml}</div>` : ``}
</div>

<div style="margin-top:12px;">
<div class="chart-canvas-box">
          <canvas id="${ids.canvas}"></canvas>
        </div></div>
        ${cfg.afterCanvasHtml ? cfg.afterCanvasHtml : ""}

        ${
          ids.monthSelect
            ? `
            <div class="month-select-wrap" id="${ids.monthSelectWrap || ""}" style="margin-top:12px;">
              <select id="${ids.monthSelect}"></select>
            </div>
          `
            : ``
        }

        ${ ids.monthButtons
  ? `<div id="${ids.monthButtons}" class="month-buttons" style="margin-top:12px;"></div>`
  : ``
}

      </section>
    `;

    // If toggle is hidden, also hide dots area (optional).
    if (!showToggle) {
      const dots = document.getElementById(ids.dots);
      if (dots) dots.style.display = "none";
    }
  };


  // Helper for the inline growth % value
  window.setInlineGrowthByIds = function setInlineGrowthByIds(ids, label, valueStr) {
    const l = document.getElementById(ids.growthLabel);
    const v = document.getElementById(ids.growthValue);
    if (!l || !v) return;
    l.textContent = label || "% Growth";
    v.textContent = valueStr == null ? "—" : String(valueStr);
  };

  // Helper for the inline breakdown value (current chart value)
  window.setInlineBreakdownByIds = function setInlineBreakdownByIds(ids, label, value, moneyFn) {
    const l = document.getElementById(ids.breakLabel);
    const v = document.getElementById(ids.breakValue);
    if (!l || !v) return;
    l.textContent = label;
    v.textContent = (moneyFn ? moneyFn(value) : String(value));
  };
})();
