// static/upcomingCard.js
// Shared "Upcoming transactions" scroller card for Home + Account pages.
//
// Usage:
//   mountUpcomingCard("#upcomingMount", { daysAhead: 30 });
//   mountUpcomingCard("#upcomingMount", { daysAhead: 30, accountId: 5 });

(function () {
  function isoLocal(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  }

  function addDays(d, n) {
    const x = new Date(d);
    x.setDate(x.getDate() + n);
    return x;
  }

  function dayLabel(d) {
    return d.toLocaleDateString("en-US", { weekday: "short" });
  }

  function shortMD(d) {
    return d.toLocaleDateString("en-US", { month: "2-digit", day: "2-digit" });
  }

  function money(n) {
    const num = Number(n || 0);
    return num.toLocaleString("en-US", { style: "currency", currency: "USD" });
  }

  function signedMoney(n, isIncome) {
    const amt = Math.abs(Number(n || 0));
    const sign = isIncome ? "+" : "-";
    return sign + money(amt);
  }

  function isIncomeEvent(e) {
    const t = String(e?.type || "").toLowerCase();
    const c = String(e?.cadence || "").toLowerCase();
    return t === "income" || c === "paycheck" || c === "interest";
  }

  function ellipsize(s, max = 14) {
    s = String(s || "").trim();
    if (s.length <= max) return s;
    return s.slice(0, max - 1) + "…";
  }

  async function fetchRecurringCalendarMonth(year, month, { minOcc = 3, includeStale = "false" } = {}) {
    const res = await fetch(
      `/recurring/calendar?year=${encodeURIComponent(year)}&month=${encodeURIComponent(month)}&min_occ=${encodeURIComponent(minOcc)}&include_stale=${includeStale}`,
      { cache: "no-store" }
    );
    if (!res.ok) return { events: [] };
    return await res.json();
  }

  function computeMonthsBetween(startDate, endDate) {
    const months = [];
    let cur = new Date(startDate.getFullYear(), startDate.getMonth(), 1);
    const endMonth = new Date(endDate.getFullYear(), endDate.getMonth(), 1);
    while (cur <= endMonth) {
      months.push({ y: cur.getFullYear(), m: cur.getMonth() + 1 });
      cur = new Date(cur.getFullYear(), cur.getMonth() + 1, 1);
    }
    return months;
  }

  function buildCardHTML() {
    return `
      <section aria-label="Upcoming transactions" style="margin-top:14px;">
        <div class="category-box">
          <div class="category-box__header">Upcoming transactions</div>
          <div class="mini-calendar" data-upcoming-body></div>
        </div>
      </section>
    `;
  }

  function renderDayCard({ dateObj, iso, events }) {
    const cell = document.createElement("div");
    cell.style.border = "1px solid #eee";
    cell.style.borderRadius = "12px";
    cell.style.padding = "10px";
    cell.style.minHeight = "86px";

    const head = document.createElement("div");
    head.style.display = "flex";
    head.style.justifyContent = "space-between";
    head.style.alignItems = "baseline";
    head.style.gap = "8px";
    head.innerHTML = `
      <div style="font-weight:700;">${dayLabel(dateObj)}</div>
      <div style="opacity:.75; font-size:.9em;">${shortMD(dateObj)}</div>
    `;

    const list = document.createElement("div");
    list.style.marginTop = "8px";
    list.style.display = "flex";
    list.style.flexDirection = "column";
    list.style.gap = "6px";

    // If you want each day to be scrollable vertically (lots of items):
    list.style.maxHeight = "84px";
    list.style.overflowY = "auto";

    const items = (events || []).slice();

    // Sort: income first, then bigger abs amount
    items.sort((a, b) => {
      const ai = isIncomeEvent(a) ? 0 : 1;
      const bi = isIncomeEvent(b) ? 0 : 1;
      if (ai !== bi) return ai - bi;
      return Math.abs(Number(b?.amount || 0)) - Math.abs(Number(a?.amount || 0));
    });

    if (!items.length) {
      const empty = document.createElement("div");
      empty.textContent = "—";
      empty.style.opacity = "0.35";
      list.appendChild(empty);
    } else {
      // Show all items (since each day list scrolls), no "+N more"
      items.forEach((e) => {
        const line = document.createElement("div");
        line.style.display = "flex";
        line.style.justifyContent = "space-between";
        line.style.gap = "8px";
        line.style.fontSize = "0.9em";

        const inc = isIncomeEvent(e);

        const left = document.createElement("div");
        left.textContent = ellipsize(e?.merchant || "(unknown)", 16);
        left.style.opacity = "0.9";

        const right = document.createElement("div");
        right.textContent = signedMoney(e?.amount, inc);
        right.style.fontWeight = "700";

        line.appendChild(left);
        line.appendChild(right);
        list.appendChild(line);
      });
    }

    cell.appendChild(head);
    cell.appendChild(list);
    return cell;
  }

  async function mountUpcomingCard(mountSelector, { daysAhead = 30, accountId = null } = {}) {
    const mount = document.querySelector(mountSelector);
    if (!mount) {
      console.warn("mountUpcomingCard: mount not found:", mountSelector);
      return;
    }

    // Render card skeleton
    mount.innerHTML = buildCardHTML();
    const body = mount.querySelector("[data-upcoming-body]");
    if (!body) return;

    const today = new Date();
    const startIso = isoLocal(today);
    const endD = addDays(today, Math.max(1, Number(daysAhead) || 30) - 1);
    const endIso = isoLocal(endD);

    // Pull months that cover the date range
    const months = computeMonthsBetween(today, endD);

    // Fetch events for all required months
    let events = [];
    for (const mm of months) {
      const json = await fetchRecurringCalendarMonth(mm.y, mm.m, { minOcc: 3, includeStale: "false" });
      if (Array.isArray(json?.events)) events = events.concat(json.events);
    }

    // Optional filter by account
    if (accountId != null) {
      const aid = Number(accountId);
      events = events.filter((e) => Number(e?.account_id) === aid);
      // Note: this requires backend events to include `account_id`.
      // If paychecks/interest are global (no account_id), they will be excluded here.
    }

    // Group by ISO date within range
    const byDate = {};
    for (const e of events || []) {
      const d = String(e?.date || "");
      if (!d) continue;
      if (d < startIso || d > endIso) continue;
      (byDate[d] ||= []).push(e);
    }

    // Render day cards
    body.innerHTML = "";
    for (let i = 0; i < (Number(daysAhead) || 30); i++) {
      const dObj = addDays(today, i);
      const iso = isoLocal(dObj);
      const dayEvents = byDate[iso] || [];
      body.appendChild(renderDayCard({ dateObj: dObj, iso, events: dayEvents }));
    }
  }

  // export
  window.mountUpcomingCard = mountUpcomingCard;
})();
