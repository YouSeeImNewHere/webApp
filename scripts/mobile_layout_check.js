#!/usr/bin/env node
/* eslint-disable no-console */
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const BASE = (process.env.LAYOUT_BASE_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");
const OUT_DIR = process.env.LAYOUT_OUT_DIR || path.join(process.cwd(), "tmp_mobile_layout");
const SECRET = String(process.env.LAYOUT_SECRET || process.env.SMOKE_SECRET || "").trim();
const STATE_FILE = process.env.LAYOUT_STATE_FILE || path.join(OUT_DIR, "auth-state.json");
const USE_CHROME_PROFILE = String(process.env.LAYOUT_USE_CHROME_PROFILE || "").trim() === "1";
const USER_DATA_DIR = process.env.LAYOUT_USER_DATA_DIR || path.join(process.env.LOCALAPPDATA || "", "Google", "Chrome", "User Data");
const CHROME_CHANNEL = process.env.LAYOUT_CHROME_CHANNEL || "chrome";

const TARGETS = [
  { name: "home", url: "/static/pages/home/home.html" },
  { name: "analytics", url: "/static/pages/analytics/analytics.html" },
  { name: "budget", url: "/static/pages/budget/budget.html" },
  { name: "account", url: "/static/pages/account/account.html?account_id=1" },
];

function ensureDir(dir) {
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
}

async function loginIfConfigured(page) {
  if (!SECRET) return { attempted: false, ok: false };
  await page.goto(`${BASE}/login`, { waitUntil: "domcontentloaded", timeout: 30000 });
  const inputPrimary = page.locator('input[name="secret_field_1"]');
  const inputFallback = page.locator('input[name="secret"]');
  if (await inputPrimary.count()) {
    await inputPrimary.fill(SECRET);
  } else if (await inputFallback.count()) {
    await inputFallback.fill(SECRET);
  } else {
    return { attempted: true, ok: false };
  }
  await page.locator('button[type="submit"]').click();
  await page.waitForTimeout(600);
  return { attempted: true, ok: true };
}

async function pageLooksLikeLogin(page) {
  const loginInput = page.locator('input[name="secret"]');
  if (await loginInput.count()) return true;
  const loginInputAlt = page.locator('input[name="secret_field_1"]');
  if (await loginInputAlt.count()) return true;
  const title = await page.title().catch(() => "");
  if (String(title || "").trim().toLowerCase() === "login") return true;
  return false;
}

async function run() {
  ensureDir(OUT_DIR);
  console.log(`[mobile-check] base=${BASE}`);
  console.log(`[mobile-check] out=${OUT_DIR}`);
  console.log(`[mobile-check] useChromeProfile=${USE_CHROME_PROFILE}`);
  if (USE_CHROME_PROFILE) {
    console.log(`[mobile-check] userDataDir=${USER_DATA_DIR}`);
    console.log(`[mobile-check] channel=${CHROME_CHANNEL}`);
  }
  let browser = null;
  let context = null;
  let page = null;
  if (USE_CHROME_PROFILE) {
    console.log("[mobile-check] launching persistent browser context...");
    context = await chromium.launchPersistentContext(USER_DATA_DIR, {
      headless: true,
      channel: CHROME_CHANNEL,
      viewport: { width: 390, height: 844 },
      deviceScaleFactor: 2,
    });
    console.log("[mobile-check] browser context started");
    page = context.pages()[0] || (await context.newPage());
  } else {
    console.log("[mobile-check] launching isolated browser...");
    browser = await chromium.launch({ headless: true });
    context = await browser.newContext({
      viewport: { width: 390, height: 844 },
      deviceScaleFactor: 2,
      storageState: fs.existsSync(STATE_FILE) ? STATE_FILE : undefined,
    });
    page = await context.newPage();
    await loginIfConfigured(page);
  }
  const results = [];

  for (const t of TARGETS) {
    console.log(`[mobile-check] checking ${t.name}...`);
    const fullUrl = `${BASE}${t.url}`;
    let status = 0;
    let navError = null;
    try {
      const res = await page.goto(fullUrl, { waitUntil: "domcontentloaded", timeout: 30000 });
      status = res ? (res.status() || 0) : 0;
      await page.waitForTimeout(1800);
      const isLogin = await pageLooksLikeLogin(page);
      if (isLogin) {
        const shot = path.join(OUT_DIR, `${t.name}.png`);
        await page.screenshot({ path: shot, fullPage: true });
        results.push({
          page: t.name,
          url: fullUrl,
          status,
          overflow: null,
          auth_required: true,
          screenshot: shot,
          error: SECRET ? "Authentication failed or session not established." : "Unauthenticated: set LAYOUT_SECRET to capture real page.",
        });
        continue;
      }
      const m = await page.evaluate(() => ({
        width: window.innerWidth,
        docScrollWidth: document.documentElement.scrollWidth,
        bodyScrollWidth: document.body ? document.body.scrollWidth : 0,
        overflow: document.documentElement.scrollWidth > window.innerWidth + 2,
        statusText: (document.getElementById("reportStatus") && document.getElementById("reportStatus").textContent) || "",
      }));
      const finalUrl = page.url();
      if (!String(finalUrl).startsWith(BASE)) {
        const shot = path.join(OUT_DIR, `${t.name}.png`);
        await page.screenshot({ path: shot, fullPage: true });
        results.push({
          page: t.name,
          url: fullUrl,
          finalUrl,
          status,
          overflow: null,
          auth_required: true,
          screenshot: shot,
          error: `Redirected off-origin to ${finalUrl}`,
        });
        continue;
      }
      const shot = path.join(OUT_DIR, `${t.name}.png`);
      await page.screenshot({ path: shot, fullPage: true });
      results.push({
        page: t.name,
        url: fullUrl,
        finalUrl,
        status,
        overflow: !!m.overflow,
        width: m.width,
        docScrollWidth: m.docScrollWidth,
        bodyScrollWidth: m.bodyScrollWidth,
        statusText: m.statusText,
        screenshot: shot,
      });
    } catch (err) {
      navError = String(err && err.message ? err.message : err);
      results.push({
        page: t.name,
        url: fullUrl,
        status,
        overflow: null,
        error: navError,
      });
    }
  }

  await context.close();
  if (browser) await browser.close();
  const outPath = path.join(OUT_DIR, "report.json");
  fs.writeFileSync(outPath, JSON.stringify(results, null, 2), "utf8");

  console.log("Mobile layout check results:");
  for (const r of results) {
    if (r.error) {
      console.log(`- ${r.page}: ERROR ${r.error}`);
      continue;
    }
    console.log(`- ${r.page}: status=${r.status} overflow=${r.overflow} doc=${r.docScrollWidth} vw=${r.width}`);
  }
  console.log(`Report: ${outPath}`);

  const hasHardFailure = results.some((r) => r.error || r.overflow === true || r.auth_required === true);
  process.exit(hasHardFailure ? 1 : 0);
}

run().catch((err) => {
  console.error("mobile_layout_check failed:", err);
  process.exit(2);
});
