(function () {
  window.initChartControls = function initChartControls(ids, onUpdate) {
    let selectedYear = new Date().getFullYear();

    const startInput = document.getElementById(ids.start);
    const endInput   = document.getElementById(ids.end);
    const yearLabel  = document.getElementById(ids.yearLabel);
    const backBtn    = document.getElementById(ids.yearBack);
    const fwdBtn     = document.getElementById(ids.yearFwd);
    const qWrap      = document.getElementById(ids.quarters);
    const mWrap      = document.getElementById(ids.monthButtons);
    const updateBtn  = document.getElementById(ids.update);

    const today = new Date();
    const cy = today.getFullYear();
    const cm = today.getMonth();

    const iso = d => d.toISOString().split("T")[0];
    const firstDay = (y,m) => new Date(y,m,1);
    const lastDay  = (y,m) => new Date(y,m+1,0);

    function setRange(start, end) {
      startInput.value = iso(start);
      endInput.value   = iso(end);
    }

    function refresh() {
      onUpdate(startInput.value, endInput.value);
    }

    function setYear(y) {
      selectedYear = y;
      yearLabel.textContent = String(y);

      // clamp forward button
      if (fwdBtn) {
        fwdBtn.disabled = (y >= cy);
        fwdBtn.style.opacity = fwdBtn.disabled ? "0.5" : "";
      }
    }

    // ---------- Year arrows ----------
    backBtn?.addEventListener("click", () => {
      setYear(selectedYear - 1);
      setRange(new Date(selectedYear,0,1), new Date(selectedYear,11,31));
      buildMonths();
      buildQuarters();
      refresh();
    });

    fwdBtn?.addEventListener("click", () => {
      if (selectedYear >= cy) return;
      setYear(selectedYear + 1);
      setRange(
        new Date(selectedYear,0,1),
        selectedYear === cy ? today : new Date(selectedYear,11,31)
      );
      buildMonths();
      buildQuarters();
      refresh();
    });

    // ---------- Quarters ----------
    function buildQuarters() {
      if (!qWrap) return;
      qWrap.innerHTML = "";

      const quarters = [
        ["Q1",0,2], ["Q2",3,5], ["Q3",6,8], ["Q4",9,11]
      ];

      quarters.forEach(([label, m1, m2]) => {
        const b = document.createElement("button");
        b.className = "month-btn";
        b.textContent = label;

        b.onclick = () => {
          let end = lastDay(selectedYear,m2);
          if (selectedYear === cy && m2 === Math.floor(cm/3)*3+2) end = today;
          setRange(firstDay(selectedYear,m1), end);
          refresh();
        };

        qWrap.appendChild(b);
      });
    }

    // ---------- Months + Annual ----------
    function buildMonths() {
      if (!mWrap) return;
      mWrap.innerHTML = "";

      const names = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

      names.forEach((n,i) => {
        const b = document.createElement("button");
        b.className = "month-btn";
        b.textContent = n;

        b.onclick = () => {
          let end = lastDay(selectedYear,i);
          if (selectedYear === cy && i === cm) end = today;
          setRange(firstDay(selectedYear,i), end);
          refresh();
        };

        mWrap.appendChild(b);
      });

      // ✅ Annual
      const annual = document.createElement("button");
      annual.className = "month-btn is-annual";
      annual.textContent = "Annual";
      annual.onclick = () => {
        setRange(
          new Date(selectedYear,0,1),
          selectedYear === cy ? today : new Date(selectedYear,11,31)
        );
        refresh();
      };
      mWrap.appendChild(annual);
    }

    // ---------- Update button ----------
    updateBtn?.addEventListener("click", refresh);

    // ---------- Initial state ----------
    setYear(cy);
    setRange(new Date(cy, cm, 1), today);
    buildQuarters();
    buildMonths();
    refresh();
  };
})();
