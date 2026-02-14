// /static/shared/dates.js
(function (global) {
  "use strict";

  function isoLocalDate() {
    const d = new Date();
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  }

  function isoLocal(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  }

  function isoToday() {
    return isoLocal(new Date());
  }

  function parseISODateLocal(iso) {
    const parts = String(iso || "").split("-").map(Number);
    const y = parts[0] || 0;
    const m = parts[1] || 1;
    const d = parts[2] || 1;
    return new Date(y, m - 1, d);
  }

  function toDate(input) {
    if (input instanceof Date) return input;
    const raw = String(input || "");
    if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) return parseISODateLocal(raw);
    return new Date(raw);
  }

  function formatMMMdd(iso) {
    const d = toDate(iso);
    return d.toLocaleDateString("en-US", { month: "short", day: "2-digit" });
  }

  function formatMMDD(iso) {
    const d = toDate(iso);
    return d.toLocaleDateString("en-US", { month: "2-digit", day: "2-digit" });
  }

  function formatMMDDYY(iso) {
    const d = toDate(iso);
    return d.toLocaleDateString("en-US", { month: "2-digit", day: "2-digit", year: "2-digit" });
  }

  function formatWeekdayShort(iso) {
    const d = toDate(iso);
    return d.toLocaleDateString("en-US", { weekday: "short" });
  }

  function formatDateLong(iso) {
    const d = toDate(iso);
    return d.toLocaleDateString("en-US", {
      weekday: "long",
      year: "numeric",
      month: "long",
      day: "numeric",
    });
  }

  function formatMonthYearLong(iso) {
    const d = toDate(iso);
    return d.toLocaleDateString("en-US", { month: "long", year: "numeric" });
  }

  function shortDate(s) {
    if (!s) return "";
    const raw = String(s);
    if (raw.toLowerCase() === "unknown") return "";
    if (raw.includes("/")) {
      const parts = raw.split("/");
      return `${parts[0]}/${parts[1]}`;
    }

    const m = raw.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (m) return `${m[2]}/${m[3]}`;

    const d = new Date(raw);
    return d.toLocaleDateString("en-US", { month: "2-digit", day: "2-digit" });
  }

  function fmtISOToShort(iso) {
    const m = String(iso || "").match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (!m) return String(iso || "");
    return `${m[2]}/${m[3]}`;
  }

  global.SharedDates = Object.assign(global.SharedDates || {}, {
    isoLocal,
    isoToday,
    isoLocalDate,
    parseISODateLocal,
    formatMMMdd,
    formatMMDD,
    formatMMDDYY,
    formatWeekdayShort,
    formatDateLong,
    formatMonthYearLong,
    shortDate,
    fmtISOToShort,
  });

  if (!global.isoLocal) global.isoLocal = isoLocal;
  if (!global.isoToday) global.isoToday = isoToday;
  if (!global.isoLocalDate) global.isoLocalDate = isoLocalDate;
  if (!global.parseISODateLocal) global.parseISODateLocal = parseISODateLocal;
  if (!global.formatMMMdd) global.formatMMMdd = formatMMMdd;
  if (!global.formatMMDD) global.formatMMDD = formatMMDD;
  if (!global.formatMMDDYY) global.formatMMDDYY = formatMMDDYY;
  if (!global.formatWeekdayShort) global.formatWeekdayShort = formatWeekdayShort;
  if (!global.formatDateLong) global.formatDateLong = formatDateLong;
  if (!global.formatMonthYearLong) global.formatMonthYearLong = formatMonthYearLong;
  if (!global.shortDate) global.shortDate = shortDate;
  if (!global.fmtISOToShort) global.fmtISOToShort = fmtISOToShort;
})(window);
