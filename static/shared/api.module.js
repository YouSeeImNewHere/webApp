function redirectToLogin() {
  const path = `${window.location.pathname || "/"}${window.location.search || ""}${window.location.hash || ""}`;
  const next = encodeURIComponent(path || "/");
  window.location.assign(`/login?next=${next}`);
}

const API_CACHE_PREFIX = "api:get:v1:";
const API_CACHE_DEFAULT_TTL_MS = 3 * 60 * 1000;
const API_CACHE_MAX_STALE_MS = 24 * 60 * 60 * 1000;
const API_INFLIGHT = new Map();

const API_CACHE_RULES = [
  { prefix: "/notifications/unread", ttlMs: 15 * 1000 },
  { prefix: "/transactions", ttlMs: 2 * 60 * 1000 },
  { prefix: "/unassigned", ttlMs: 2 * 60 * 1000 },
  { prefix: "/bank-totals", ttlMs: 3 * 60 * 1000 },
  { prefix: "/category-totals-month", ttlMs: 3 * 60 * 1000 },
  { prefix: "/month-budget", ttlMs: 3 * 60 * 1000 },
  { prefix: "/page/home", ttlMs: 2 * 60 * 1000 },
  { prefix: "/net-worth", ttlMs: 5 * 60 * 1000 },
  { prefix: "/savings", ttlMs: 5 * 60 * 1000 },
  { prefix: "/investments", ttlMs: 5 * 60 * 1000 },
  { prefix: "/spending", ttlMs: 5 * 60 * 1000 },
];

function handleAuthFailure(res, options = {}) {
  if (options && options.skipAuthRedirect) return false;
  if (res && res.status === 401 && window.location.pathname !== "/login") {
    redirectToLogin();
    return true;
  }
  return false;
}

function getApiCacheKey(url) {
  return `${API_CACHE_PREFIX}${String(url || "")}`;
}

function isCacheDisabled(options = {}) {
  return options.cache === "no-store" || options.cacheTTLms === 0;
}

function resolveCacheTtlMs(url, options = {}) {
  if (Number.isFinite(Number(options.cacheTTLms))) {
    return Math.max(0, Number(options.cacheTTLms));
  }
  const u = String(url || "");
  const hit = API_CACHE_RULES.find(r => u.indexOf(r.prefix) === 0);
  return hit ? hit.ttlMs : API_CACHE_DEFAULT_TTL_MS;
}

function readCacheEntry(store, key) {
  try {
    const raw = store.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return null;
    return parsed;
  } catch {
    return null;
  }
}

function readCachedJson(url, ttlMs, allowStaleMs = 0) {
  const key = getApiCacheKey(url);
  const now = Date.now();
  const stores = [sessionStorage, localStorage];

  for (const store of stores) {
    const parsed = readCacheEntry(store, key);
    if (!parsed) continue;
    const ts = Number(parsed.ts || 0);
    if (!ts) continue;
    const age = now - ts;
    if (age <= ttlMs) return parsed.data ?? null;
    if (allowStaleMs > 0 && age <= allowStaleMs) return parsed.data ?? null;
  }

  return null;
}

function writeCacheEntry(store, key, payload) {
  try {
    store.setItem(key, JSON.stringify(payload));
  } catch {}
}

function writeCachedJson(url, data) {
  const key = getApiCacheKey(url);
  const payload = { ts: Date.now(), data };
  writeCacheEntry(sessionStorage, key, payload);
  writeCacheEntry(localStorage, key, payload);
}

function clearApiGetCache() {
  const clearStore = (store) => {
    try {
      const keys = [];
      for (let i = 0; i < store.length; i += 1) {
        const k = store.key(i);
        if (k && k.indexOf(API_CACHE_PREFIX) === 0) keys.push(k);
      }
      keys.forEach(k => store.removeItem(k));
    } catch {}
  };
  clearStore(sessionStorage);
  clearStore(localStorage);
}

function readCachedOrNull(url, options = {}) {
  const ttlMs = resolveCacheTtlMs(url, options);
  if (isCacheDisabled(options) || ttlMs <= 0) return null;
  return readCachedJson(url, ttlMs);
}

function getInflightKey(url, options = {}) {
  const method = String(options.method || "GET").toUpperCase();
  return `${method}:${String(url || "")}`;
}

async function fetchJsonAndCache(url, options = {}) {
  const res = await apiFetch(url, options);
  if (!res.ok) {
    const err = new Error("HTTP " + res.status);
    err.status = res.status;
    err.response = res;
    throw err;
  }
  const data = await res.json();
  const ttlMs = resolveCacheTtlMs(url, options);
  if (!isCacheDisabled(options) && ttlMs > 0) writeCachedJson(url, data);
  return data;
}

async function fetchWithStaleFallback(url, options = {}) {
  try {
    return await fetchJsonAndCache(url, options);
  } catch (err) {
    if (!isCacheDisabled(options)) {
      const stale = readCachedJson(url, 0, API_CACHE_MAX_STALE_MS);
      if (stale !== null) return stale;
    }
    throw err;
  }
}

export async function apiFetch(url, options = {}) {
  const opts = Object.assign({ credentials: "same-origin" }, options || {});
  const res = await fetch(url, opts);
  handleAuthFailure(res, opts);
  return res;
}

export async function apiGetJson(url, options = {}) {
  const cached = readCachedOrNull(url, options);
  if (cached !== null) return cached;

  const inflightKey = getInflightKey(url, options);
  if (API_INFLIGHT.has(inflightKey)) {
    return API_INFLIGHT.get(inflightKey);
  }

  const p = (async () => {
    try {
      return await fetchWithStaleFallback(url, options);
    } finally {
      API_INFLIGHT.delete(inflightKey);
    }
  })();

  API_INFLIGHT.set(inflightKey, p);
  return p;
}

export async function apiPostJson(url, body, options = {}) {
  const opts = Object.assign(
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    },
    options || {},
  );
  const res = await apiFetch(url, opts);
  if (!res.ok) {
    const err = new Error("HTTP " + res.status);
    err.status = res.status;
    err.response = res;
    throw err;
  }
  const data = await res.json();
  clearApiGetCache();
  return data;
}

export async function apiPostForm(url, formData, options = {}) {
  const opts = Object.assign(
    {
      method: "POST",
      body: formData,
    },
    options || {},
  );
  const res = await apiFetch(url, opts);
  if (!res.ok) {
    const err = new Error("HTTP " + res.status);
    err.status = res.status;
    err.response = res;
    throw err;
  }
  const data = await res.json();
  clearApiGetCache();
  return data;
}
