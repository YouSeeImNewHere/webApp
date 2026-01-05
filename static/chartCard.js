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
        <header class="chart-header">
          <h2 id="${ids.title}">${cfg.title || ""}</h2>
          <div id="${ids.dots}" class="chart-dots" aria-label="Chart indicator"></div>
          ${
            showToggle
              ? `<button id="${ids.toggle}" type="button">${cfg.toggleText || ""}</button>`
              : `<div></div>`
          }
        </header>

<div class="chart-controls">

  <!-- Breakdown -->
  <div class="chart-breakdown">
    <span id="${ids.breakLabel}">${cfg.breakdownLabel || ""}</span>
    <strong id="${ids.breakValue}">${cfg.breakdownValue || "$0"}</strong>
  </div>

  <div id="${ids.quarters}" class="chart-btn-group"></div>

  <div class="chart-btn-group">
    <button id="${ids.yearBack}" class="chart-btn">◀</button>
    <span id="${ids.yearLabel}" class="chart-year"></span>
    <button id="${ids.yearFwd}" class="chart-btn">▶</button>
  </div>

  <div class="chart-dates-inline">
    <label>Start <input type="date" id="${ids.start}"></label>
    <label>End <input type="date" id="${ids.end}"></label>
  </div>

  <button id="${ids.update}" class="chart-btn primary">Update</button>
</div>



        <div style="margin-top:12px;">
          <canvas id="${ids.canvas}"></canvas>
        </div>

        ${
          ids.monthSelect
            ? `
            <div class="month-select-wrap" id="${ids.monthSelectWrap || ""}" style="margin-top:12px;">
              <select id="${ids.monthSelect}"></select>
            </div>
          `
            : ``
        }

        ${
          ids.monthButtons
            ? `<div id="${ids.monthButtons}" style="display:flex; flex-wrap:wrap; gap:8px; justify-content:center; margin-top:12px;"></div>`
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

  // Helper for the inline breakdown value (current chart value)
  window.setInlineBreakdownByIds = function setInlineBreakdownByIds(ids, label, value, moneyFn) {
    const l = document.getElementById(ids.breakLabel);
    const v = document.getElementById(ids.breakValue);
    if (!l || !v) return;
    l.textContent = label;
    v.textContent = (moneyFn ? moneyFn(value) : String(value));
  };
})();
