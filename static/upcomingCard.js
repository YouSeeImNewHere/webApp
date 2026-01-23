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

  function longLabel(d) {
    return d.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric", year: "numeric" });
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

  function ellipsize(s, max = 18) {
    s = String(s || "").trim();
    if (s.length <= max) return s;
    return s.slice(0, max - 1) + "…";
  }

  // ✅ Robust category getter (handles backend naming differences)
  function getCategory(e) {
    const v =
      e?.type ??
      e?.category ??
      "";

    const s = String(v || "").trim();
    if (s) return s;

    // If backend doesn't send category for income-like events, make it nicer:
    //if (isIncomeEvent(e)) return "Income";

    return "Unassigned";
  }


// ---------------- Paychecks (LES) ----------------
// Pulls paycheck events from /les/paychecks using the saved Profile (localStorage via profile.js).
function getProfile() {
  return window.Profile?.get?.() || null;
}

async function fetchPaychecks(year, month) {
  const profile0 = getProfile();
  if (!profile0) return [];
  if (!profile0?.paygrade) {
    console.warn("LES profile missing paygrade; skipping paycheck calc.");
    return [];
  }

  // Normalize a few fields so the backend always understands them
  const profile = { ...profile0 };
  if (profile.paygrade != null) {
    profile.paygrade = String(profile.paygrade)
      .toUpperCase()
      .replace(/\s+/g, "")
      .replace("E-", "E")
      .replace("-", "");
  }
  if (profile.service_start != null) {
    profile.service_start = String(profile.service_start);
  }
  if (profile.bah_override === "") profile.bah_override = null;

  const res = await fetch("/les/paychecks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ year, month, profile }),
  });

  if (!res.ok) {
    const txt = await res.text().catch(() => "");
    console.error("Paycheck calc failed:", res.status, txt);
    return [];
  }

  const data = await res.json().catch(() => null);
  return Array.isArray(data?.events) ? data.events : [];
}

function dedupeEvents(evts) {
  const out = [];
  const seen = new Set();
  for (const e of evts || []) {
    const key = [
      String(e?.date || ""),
      String(e?.pay_target || ""),
      String(e?.merchant || ""),
      String(e?.cadence || ""),
      String(Number(e?.amount || 0)),
      String(Number(e?.account_id || "")),
    ].join("|");
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(e);
  }
  return out;
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

  // ---------------- Modal ----------------
  function ensureModal() {
    let backdrop = document.getElementById("upcomingDayBackdrop");
    if (backdrop) return backdrop;

    backdrop = document.createElement("div");
    backdrop.id = "upcomingDayBackdrop";
    backdrop.className = "upcoming-day-backdrop";
    backdrop.innerHTML = `
      <div class="upcoming-day-modal" role="dialog" aria-modal="true" aria-label="Upcoming day details">
        <div class="upcoming-day-modal__head">
          <div class="upcoming-day-modal__title" id="upcomingDayTitle"></div>
          <button class="upcoming-day-modal__close" type="button" aria-label="Close">✕</button>
        </div>
        <div class="upcoming-day-modal__body" id="upcomingDayBody"></div>
      </div>
    `;

    document.body.appendChild(backdrop);

    const closeBtn = backdrop.querySelector(".upcoming-day-modal__close");
    closeBtn?.addEventListener("click", () => (backdrop.style.display = "none"));

    // click outside modal closes
    backdrop.addEventListener("click", (e) => {
      if (e.target === backdrop) backdrop.style.display = "none";
    });

    // esc closes
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") backdrop.style.display = "none";
    });

    return backdrop;
  }

  function openDayModal(dateObj, events) {
    const backdrop = ensureModal();
    const title = document.getElementById("upcomingDayTitle");
    const body = document.getElementById("upcomingDayBody");
    if (!title || !body) return;

    title.textContent = longLabel(dateObj);

    const items = (events || []).slice();
    items.sort((a, b) => {
      const ai = isIncomeEvent(a) ? 0 : 1;
      const bi = isIncomeEvent(b) ? 0 : 1;
      if (ai !== bi) return ai - bi;
      return Math.abs(Number(b?.amount || 0)) - Math.abs(Number(a?.amount || 0));
    });

    if (!items.length) {
      body.innerHTML = `<div style="opacity:.6;">No upcoming items.</div>`;
    } else {
      body.innerHTML = "";
      items.forEach((e) => {
        const row = document.createElement("div");
        row.className = "upcoming-day-row";

        const left = document.createElement("div");
        left.className = "upcoming-day-row__left";

        const merch = document.createElement("div");
        merch.className = "upcoming-day-row__merchant";
        merch.textContent = e?.merchant ? String(e.merchant) : "(unknown)";

        const sub = document.createElement("div");
        sub.className = "upcoming-day-row__sub";
        sub.textContent = getCategory(e);

        left.appendChild(merch);
        left.appendChild(sub);

        const right = document.createElement("div");
        right.className = "upcoming-day-row__amt";
        right.textContent = signedMoney(e?.amount, isIncomeEvent(e));

        row.appendChild(left);
        row.appendChild(right);
        body.appendChild(row);
      });
    }

    backdrop.style.display = "flex";
  }

  // ---------------- Day cards (mini-calendar) ----------------
  function renderDayCard({ dateObj, events }) {
    const cell = document.createElement("div");
    cell.className = "upcoming-day-card";

    const head = document.createElement("div");
    head.className = "upcoming-day-card__head";
    head.innerHTML = `
      <div class="upcoming-day-card__dow">${dayLabel(dateObj)}</div>
      <div class="upcoming-day-card__md">${shortMD(dateObj)}</div>
    `;

    const list = document.createElement("div");
    list.className = "upcoming-day-card__list";

    const items = (events || []).slice();
    if (!items.length) {
      const empty = document.createElement("div");
      empty.className = "upcoming-day-card__empty";
      empty.textContent = "—";
      list.appendChild(empty);
    } else {
      // Group by category
      const map = new Map();
      for (const e of items) {
        const cat = getCategory(e);
        const cur = map.get(cat) || { cat, total: 0, count: 0, anyIncome: false };
        cur.total += Math.abs(Number(e?.amount || 0));
        cur.count += 1;
        if (isIncomeEvent(e)) cur.anyIncome = true;
        map.set(cat, cur);
      }

      const groups = Array.from(map.values());
      groups.sort((a, b) => b.total - a.total);

      // Show top 3 categories; rest in modal
      const top = groups.slice(0, 3);
      const more = groups.length - top.length;

      top.forEach((g) => {
        const line = document.createElement("div");
        line.className = "upcoming-day-card__line";

        const left = document.createElement("div");
        left.className = "upcoming-day-card__cat";
        left.textContent = `${ellipsize(g.cat, 18)}${g.count > 1 ? ` (${g.count})` : ""}`;

        const right = document.createElement("div");
        right.className = "upcoming-day-card__sum";
        right.textContent = (g.anyIncome ? "+" : "-") + money(g.total);
        right.style.fontWeight = "700";

        line.appendChild(left);
        line.appendChild(right);
        list.appendChild(line);
      });

      if (more > 0) {
        const m = document.createElement("div");
        m.className = "upcoming-day-card__more";
        m.textContent = `+${more} more`;
        list.appendChild(m);
      }
    }

    cell.appendChild(head);
    cell.appendChild(list);

    // click opens modal with full merchants list
    cell.addEventListener("click", () => openDayModal(dateObj, items));

    return cell;
  }

  async function mountUpcomingCard(mountSelector, { daysAhead = 30, accountId = null } = {}) {
    const mount = document.querySelector(mountSelector);
    if (!mount) {
      console.warn("mountUpcomingCard: mount not found:", mountSelector);
      return;
    }

    mount.innerHTML = buildCardHTML();
    const body = mount.querySelector("[data-upcoming-body]");
    if (!body) return;

    const today = new Date();
    const startIso = isoLocal(today);
    const endD = addDays(today, Math.max(1, Number(daysAhead) || 30) - 1);
    const endIso = isoLocal(endD);

    const months = computeMonthsBetween(today, endD);

    let events = [];
    for (const mm of months) {
  const json = await fetchRecurringCalendarMonth(mm.y, mm.m, { minOcc: 3, includeStale: "false" });
  if (Array.isArray(json?.events)) events = events.concat(json.events);

  // ✅ Add DFAS paycheck events (if Profile is set)
  const pay = await fetchPaychecks(mm.y, mm.m);
  if (pay.length) events = events.concat(pay);
}

    if (accountId != null) {
      const aid = Number(accountId);
      events = events.filter((e) => Number(e?.account_id) === aid);
    }


    // De-dupe across month fetches (spillover paycheck deposits can appear in adjacent months)
    events = dedupeEvents(events);

    const byDate = {};
    for (const e of events || []) {
      const d = String(e?.date || "");
      if (!d) continue;
      if (d < startIso || d > endIso) continue;
      (byDate[d] ||= []).push(e);
    }

    body.innerHTML = "";
    for (let i = 0; i < (Number(daysAhead) || 30); i++) {
      const dObj = addDays(today, i);
      const iso = isoLocal(dObj);
      body.appendChild(renderDayCard({ dateObj: dObj, events: byDate[iso] || [] }));
    }
  }

  window.mountUpcomingCard = mountUpcomingCard;
})();
