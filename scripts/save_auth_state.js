#!/usr/bin/env node
/* eslint-disable no-console */
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const BASE = (process.env.LAYOUT_BASE_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");
const OUT_DIR = process.env.LAYOUT_OUT_DIR || path.join(process.cwd(), "tmp_mobile_layout");
const STATE_FILE = process.env.LAYOUT_STATE_FILE || path.join(OUT_DIR, "auth-state.json");

function ensureDir(dir) {
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
}

(async () => {
  ensureDir(OUT_DIR);
  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();

  console.log(`Open page: ${BASE}`);
  console.log("Log in fully (including Google if prompted), then press Enter here.");
  await page.goto(BASE, { waitUntil: "domcontentloaded", timeout: 60000 });

  process.stdin.resume();
  await new Promise((resolve) => process.stdin.once("data", resolve));

  await context.storageState({ path: STATE_FILE });
  console.log(`Saved auth state: ${STATE_FILE}`);
  await browser.close();
  process.exit(0);
})().catch((err) => {
  console.error("save_auth_state failed:", err);
  process.exit(1);
});
