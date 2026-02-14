export function isoLocalDate() {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export function isoLocal(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export function isoToday() {
  return isoLocal(new Date());
}

export function parseISODateLocal(iso) {
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

export function formatMMMdd(iso) {
  const d = toDate(iso);
  return d.toLocaleDateString("en-US", { month: "short", day: "2-digit" });
}

export function formatMMDD(iso) {
  const d = toDate(iso);
  return d.toLocaleDateString("en-US", { month: "2-digit", day: "2-digit" });
}

export function formatMMDDYY(iso) {
  const d = toDate(iso);
  return d.toLocaleDateString("en-US", { month: "2-digit", day: "2-digit", year: "2-digit" });
}

export function formatWeekdayShort(iso) {
  const d = toDate(iso);
  return d.toLocaleDateString("en-US", { weekday: "short" });
}

export function formatDateLong(iso) {
  const d = toDate(iso);
  return d.toLocaleDateString("en-US", {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

export function formatMonthYearLong(iso) {
  const d = toDate(iso);
  return d.toLocaleDateString("en-US", { month: "long", year: "numeric" });
}

export function shortDate(s) {
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

export function fmtISOToShort(iso) {
  const m = String(iso || "").match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!m) return String(iso || "");
  return `${m[2]}/${m[3]}`;
}
