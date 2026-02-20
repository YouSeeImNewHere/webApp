// Scriptable Finance Widget (repo-managed)
// Copy/paste this file into Scriptable.
// Optimized to reduce backend/Neon CPU:
// - Widget rendering prefers local cache.
// - Network refresh happens in Shortcut mode (or first run with no cache).

// ===== TOGGLE =====
const WIDGET_ENABLED = true;

// ===== CONFIG =====
const BASE_URL = "https://webapp-pe3q.onrender.com";
const WIDGET_TOKEN = ""; // Create via POST /settings/widget-token from an OAuth-authenticated session.
const ENDPOINT = "/widget/summary";

const fm = FileManager.local();
const CACHE_PATH = fm.joinPath(fm.documentsDirectory(), "finance_widget_cache.json");

function finish(widget, output = "Widget refreshed") {
  try { Script.setShortcutOutput(output); } catch (_) {}
  if (widget) Script.setWidget(widget);
  Script.complete();
  return;
}

function saveCache(obj) {
  const now = Date.now();
  try { fm.writeString(CACHE_PATH, JSON.stringify({ ts: now, data: obj })); } catch (_) {}
}
function loadCache() {
  if (!fm.fileExists(CACHE_PATH)) return null;
  try { return JSON.parse(fm.readString(CACHE_PATH)); } catch (_) { return null; }
}
function cacheAgeMinutes(cache) {
  if (!cache || !cache.ts) return Infinity;
  return (Date.now() - cache.ts) / 60000;
}

function isValidPayload(payload) {
  return !!(
    payload &&
    payload.ok === true &&
    payload.today &&
    typeof payload.today.remaining_today !== "undefined"
  );
}

function normalizedWidgetToken() {
  return String(WIDGET_TOKEN || "").trim();
}

async function fetchFresh() {
  const req = new Request(BASE_URL + ENDPOINT);
  const token = normalizedWidgetToken();
  if (!token) throw new Error("widget_token_required");
  const headers = { "x-widget-token": token };
  req.headers = headers;
  req.timeoutInterval = 10;
  const payload = await req.loadJSON();
  if (!isValidPayload(payload)) {
    throw new Error("invalid_widget_payload");
  }
  return payload;
}

function colorGreen()  { return Color.dynamic(new Color("#34C759"), new Color("#30D158")); }
function colorOrange() { return Color.dynamic(new Color("#FF9F0A"), new Color("#FF9F0A")); }
function colorRed()    { return Color.dynamic(new Color("#FF453A"), new Color("#FF453A")); }

function creditColor(pct) {
  if (pct < 0.3) return colorGreen();
  if (pct < 0.6) return colorOrange();
  return colorRed();
}

function money0(n) {
  n = Number(n || 0);
  const sign = n < 0 ? "-" : "";
  n = Math.abs(n);
  return sign + "$" + n.toLocaleString(undefined, { maximumFractionDigits: 0 });
}
function money2(n) {
  n = Number(n || 0);
  const sign = n < 0 ? "-" : "";
  n = Math.abs(n);
  return sign + "$" + n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
function clamp01(x) {
  x = Number(x || 0);
  if (x < 0) return 0;
  if (x > 1) return 1;
  return x;
}

function progressBar(pct, width = 170, height = 12, label = "") {
  pct = clamp01(pct);
  const ctx = new DrawContext();
  ctx.size = new Size(width, height);
  ctx.opaque = false;
  ctx.respectScreenScale = true;

  const track = new Color("#FFFFFF", 0.25);
  const fill = creditColor(pct);
  const r = height / 2;

  function fillRounded(rect, radius) {
    const p = new Path();
    if (typeof p.addRoundedRect === "function") {
      p.addRoundedRect(rect, radius, radius);
      ctx.addPath(p);
      ctx.fillPath();
      return true;
    }
    return false;
  }

  ctx.setFillColor(track);
  const trackRect = new Rect(0, 0, width, height);
  const roundedOk = fillRounded(trackRect, r);

  const fillW = Math.max(1, Math.floor(width * pct));
  ctx.setFillColor(fill);
  const fillRect = new Rect(0, 0, fillW, height);
  if (roundedOk) fillRounded(fillRect, r);
  else {
    ctx.fillRect(trackRect);
    ctx.setFillColor(fill);
    ctx.fillRect(fillRect);
  }

  if (label && (width - fillW) >= 30) {
    const fs = 9;
    ctx.setFont(Font.boldSystemFont(fs));
    ctx.setTextAlignedCenter();
    const textRect = new Rect(fillW, Math.round((height - fs) / 2) - 1, width - fillW, fs + 2);
    ctx.setTextColor(new Color("#000000", 0.65));
    const offsets = [[-1,0],[1,0],[0,-1],[0,1],[-1,-1],[1,-1],[-1,1],[1,1]];
    for (const [dx, dy] of offsets) {
      ctx.drawTextInRect(label, new Rect(textRect.x + dx, textRect.y + dy, textRect.width, textRect.height));
    }
    ctx.setTextColor(new Color("#8EC5FF", 0.95));
    ctx.drawTextInRect(label, textRect);
  }

  return ctx.getImage();
}

function dailyBarWithText(remaining, baseline, width = 170, height = 12) {
  const b = Number(baseline || 0);
  const r = Number(remaining || 0);
  let pctRem = b > 0 ? (r / b) : 0;
  pctRem = clamp01(pctRem);

  let fillColor = colorGreen();
  if (r < 0) fillColor = colorRed();
  else if (pctRem < 0.3) fillColor = colorOrange();

  const ctx = new DrawContext();
  ctx.size = new Size(width, height);
  ctx.opaque = false;
  ctx.respectScreenScale = true;

  const trackColor = new Color("#FFFFFF", 0.22);
  const rad = height / 2;

  function fillRounded(rect, radius) {
    const p = new Path();
    if (typeof p.addRoundedRect === "function") {
      p.addRoundedRect(rect, radius, radius);
      ctx.addPath(p);
      ctx.fillPath();
      return true;
    }
    return false;
  }

  ctx.setFillColor(trackColor);
  const trackRect = new Rect(0, 0, width, height);
  const roundedOk = fillRounded(trackRect, rad);

  const fillW = Math.max(1, Math.floor(width * pctRem));
  ctx.setFillColor(fillColor);
  const fillRect = new Rect(0, 0, fillW, height);

  if (roundedOk) fillRounded(fillRect, rad);
  else {
    ctx.fillRect(trackRect);
    ctx.setFillColor(fillColor);
    ctx.fillRect(fillRect);
  }

  const txt = money2(r);
  const fs = 9;
  ctx.setFont(Font.boldSystemFont(fs));
  ctx.setTextAlignedCenter();
  const textRect = new Rect(0, Math.round((height - fs) / 2) - 1, width, fs + 2);

  ctx.setTextColor(new Color("#000000", 0.65));
  const offsets = [[-1,0],[1,0],[0,-1],[0,1],[-1,-1],[1,-1],[-1,1],[1,1]];
  for (const [dx, dy] of offsets) {
    ctx.drawTextInRect(txt, new Rect(textRect.x + dx, textRect.y + dy, textRect.width, textRect.height));
  }

  ctx.setTextColor(new Color("#FFFFFF", 0.95));
  ctx.drawTextInRect(txt, textRect);
  return ctx.getImage();
}

function monthElapsedPct() {
  const now = new Date();
  const y = now.getFullYear();
  const m = now.getMonth();
  const daysInMonth = new Date(y, m + 1, 0).getDate();
  const fracDay = (now.getHours() + now.getMinutes() / 60) / 24;
  return clamp01(((now.getDate() - 1) + fracDay) / daysInMonth);
}

function paceColorForRemaining(remaining, total) {
  const r = Number(remaining || 0);
  const t = Number(total || 0);
  if (t <= 0) return colorGreen();
  const elapsed = monthElapsedPct();
  const expectedRemaining = t * (1 - elapsed);
  const tol = Math.max(t * 0.05, 25);
  if (r > expectedRemaining + tol) return colorGreen();
  if (r < expectedRemaining - tol) return colorRed();
  return colorOrange();
}

function remainingBarWithText(pctRemaining, fillColor, remainingText, width = 170, height = 12) {
  pctRemaining = clamp01(pctRemaining);
  const ctx = new DrawContext();
  ctx.size = new Size(width, height);
  ctx.opaque = false;
  ctx.respectScreenScale = true;

  const trackColor = new Color("#FFFFFF", 0.22);
  const rad = height / 2;

  function fillRounded(rect, radius) {
    const p = new Path();
    if (typeof p.addRoundedRect === "function") {
      p.addRoundedRect(rect, radius, radius);
      ctx.addPath(p);
      ctx.fillPath();
      return true;
    }
    return false;
  }

  ctx.setFillColor(trackColor);
  const trackRect = new Rect(0, 0, width, height);
  const roundedOk = fillRounded(trackRect, rad);

  const fillW = Math.max(1, Math.floor(width * pctRemaining));
  ctx.setFillColor(fillColor);
  const fillRect = new Rect(0, 0, fillW, height);
  if (roundedOk) fillRounded(fillRect, rad);
  else {
    ctx.fillRect(trackRect);
    ctx.setFillColor(fillColor);
    ctx.fillRect(fillRect);
  }

  if (remainingText) {
    const fs = 9;
    ctx.setFont(Font.boldSystemFont(fs));
    ctx.setTextAlignedCenter();
    const textRect = new Rect(0, Math.round((height - fs) / 2) - 1, width, fs + 2);
    ctx.setTextColor(new Color("#000000", 0.65));
    const offsets = [[-1,0],[1,0],[0,-1],[0,1],[-1,-1],[1,-1],[-1,1],[1,1]];
    for (const [dx, dy] of offsets) {
      ctx.drawTextInRect(remainingText, new Rect(textRect.x + dx, textRect.y + dy, textRect.width, textRect.height));
    }
    ctx.setTextColor(new Color("#FFFFFF", 0.95));
    ctx.drawTextInRect(remainingText, textRect);
  }
  return ctx.getImage();
}

if (!WIDGET_ENABLED) {
  const w = new ListWidget();
  w.addText("Finance widget paused");
  w.addText("Open Scriptable to enable");
  return finish(w, "Paused");
}

const fam = String(config.widgetFamily || "");

// Shortcut mode: refresh network + cache, no widget draw needed.
if (!fam) {
  try {
    const fresh = await fetchFresh();
    saveCache(fresh);
    return finish(null, "Refreshed");
  } catch (e) {
    return finish(null, "Refresh failed");
  }
}

// Widget mode: prefer cache; do periodic network refresh.
let payload = null;
let usedCache = true;
let cacheAgeMin = Infinity;

const cache = loadCache();
if (cache && isValidPayload(cache.data)) {
  payload = cache.data;
  cacheAgeMin = cacheAgeMinutes(cache);
}

if (!payload) {
  try {
    payload = await fetchFresh();
    usedCache = false;
    saveCache({
      ...payload,
      widget_version: Number.isFinite(Number(payload.widget_version)) ? Number(payload.widget_version) : null,
    });
    cacheAgeMin = 0;
  } catch (e) {
    const w = new ListWidget();
    w.setPadding(14, 14, 14, 14);
    w.addText("FINANCE").font = Font.boldSystemFont(12);
    w.addSpacer(6);
    w.addText("No cached data yet").font = Font.boldSystemFont(14);
    w.addText("Run shortcut once while online.").font = Font.systemFont(11);
    return finish(w, "No cache");
  }
}

const data = payload || {};
const credit = data.credit || {};
const totals = data.totals || {};

const safe = Number(data.safe_to_spend || 0);
const monthTotal = Number((data.month && data.month.free_spend_goal) || 0);
const today = data.today || {};
const baseline = Number(today.baseline || 0);
const leftToday = Number(today.remaining_today || 0);

const used = Number(credit.used || 0);
const cap = Number(credit.cap || 0);
const pct = cap > 0 ? (used / cap) : 0;

if (fam === "accessoryInline") {
  const w = new ListWidget();
  w.addText(`Left ${money0(leftToday)}`);
  return finish(w);
}

if (fam === "accessoryCircular") {
  const w = new ListWidget();
  w.addText(money0(leftToday)).font = Font.boldSystemFont(12);
  return finish(w);
}

if (fam === "accessoryRectangular") {
  const w = new ListWidget();
  w.setPadding(6, 10, 6, 10);

  const row1 = w.addStack();
  row1.layoutHorizontally();
  row1.centerAlignContent();
  const main = row1.addText(money2(leftToday));
  main.font = Font.boldSystemFont(22);
  main.minimumScaleFactor = 0.6;
  row1.addSpacer();
  const p = row1.addText(`${Math.round(clamp01(pct) * 100)}%`);
  p.font = Font.boldSystemFont(12);
  p.textColor = creditColor(pct);

  w.addSpacer(2);
  const base = w.addText(`Base ${money0(baseline)}/day`);
  base.font = Font.systemFont(12);
  base.textOpacity = 0.75;

  w.addSpacer(2);
  const safeLine = w.addText(`Safe ${money0(safe)}`);
  safeLine.font = Font.systemFont(12);
  safeLine.textOpacity = 0.75;

  return finish(w);
}

// Home screen (small/medium/large)
const w = new ListWidget();
w.setPadding(14, 14, 14, 14);

const row = w.addStack();
row.layoutHorizontally();

const left = row.addStack();
left.layoutVertically();
left.spacing = 6;
left.size = new Size(170, 0);

const cuHead = left.addStack();
cuHead.layoutHorizontally();
cuHead.centerAlignContent();
const cuLabel = cuHead.addText("CREDIT USAGE");
cuLabel.font = Font.boldSystemFont(10);
cuLabel.textOpacity = 0.55;
cuHead.addSpacer(6);
const cuPct = cuHead.addText(`${Math.round(clamp01(pct) * 100)}%`);
cuPct.font = Font.boldSystemFont(10);
cuPct.textColor = creditColor(pct);

const barStack = left.addStack();
const bar = barStack.addImage(progressBar(pct, 170, 12, money0(credit.available)));
bar.imageSize = new Size(170, 12);

left.addSpacer(4);
const safeHead = left.addStack();
safeHead.layoutHorizontally();
safeHead.centerAlignContent();
const safeLabel = safeHead.addText("SAFE TO SPEND");
safeLabel.font = Font.boldSystemFont(10);
safeLabel.textOpacity = 0.55;
safeHead.addSpacer();
const safeTotal = safeHead.addText(money0(monthTotal));
safeTotal.font = Font.boldSystemFont(12);

const pctRemainingMonth = monthTotal > 0 ? (safe / monthTotal) : 0;
const paceCol = paceColorForRemaining(safe, monthTotal);
const safeBarStack = left.addStack();
const safeBar = safeBarStack.addImage(remainingBarWithText(pctRemainingMonth, paceCol, money2(safe), 170, 12));
safeBar.imageSize = new Size(170, 12);

left.addSpacer(4);
const dlHead = left.addStack();
dlHead.layoutHorizontally();
dlHead.centerAlignContent();
const dlLabel = dlHead.addText("DAILY LIMIT");
dlLabel.font = Font.boldSystemFont(10);
dlLabel.textOpacity = 0.55;
dlHead.addSpacer();
const dlBase = dlHead.addText(money0(baseline));
dlBase.font = Font.boldSystemFont(12);

const dlBarStack = left.addStack();
const dlBar = dlBarStack.addImage(dailyBarWithText(leftToday, baseline, 170, 12));
dlBar.imageSize = new Size(170, 12);

row.addSpacer(16);
const right = row.addStack();
right.layoutVertically();
right.spacing = 8;

function kv(label, value) {
  const s = right.addStack();
  s.layoutHorizontally();
  const l = s.addText(label);
  l.font = Font.systemFont(12);
  l.textOpacity = 0.75;
  s.addSpacer();
  const v = s.addText(value);
  v.font = Font.boldSystemFont(12);
}

kv("Checking", money2(totals.checking));
kv("Savings", money2(totals.savings));

w.addSpacer(8);
const footer = w.addText(
  usedCache
    ? `Cache ${Math.round(cacheAgeMin)}m`
    : "Live"
);
footer.font = Font.systemFont(10);
footer.textOpacity = 0.6;

return finish(w);
