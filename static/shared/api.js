// /static/shared/api.js
(function (global) {
  "use strict";

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

  function redirectToLogin() {
    const path = `${window.location.pathname || "/"}${window.location.search || ""}${window.location.hash || ""}`;
    const next = encodeURIComponent(path || "/");
    window.location.assign(`/login?next=${next}`);
  }

  function handleAuthFailure(res, options) {
    const opts = options || {};
    if (opts.skipAuthRedirect) return false;
    if (res && res.status === 401 && window.location.pathname !== "/login") {
      redirectToLogin();
      return true;
    }
    return false;
  }

  function getApiCacheKey(url) {
    return `${API_CACHE_PREFIX}${String(url || "")}`;
  }

  function isCacheDisabled(options) {
    const opts = options || {};
    return opts.cache === "no-store" || opts.cacheTTLms === 0;
  }

  function resolveCacheTtlMs(url, options) {
    const opts = options || {};
    if (Number.isFinite(Number(opts.cacheTTLms))) {
      return Math.max(0, Number(opts.cacheTTLms));
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
    } catch (_) {
      return null;
    }
  }

  function readCachedJson(url, ttlMs, allowStaleMs) {
    const key = getApiCacheKey(url);
    const now = Date.now();
    const stores = [sessionStorage, localStorage];

    for (const store of stores) {
      const parsed = readCacheEntry(store, key);
      if (!parsed) continue;
      const ts = Number((parsed && parsed.ts) || 0);
      if (!ts) continue;
      const age = now - ts;
      if (age <= ttlMs) return (parsed && parsed.data) || null;
      if (allowStaleMs > 0 && age <= allowStaleMs) return (parsed && parsed.data) || null;
    }

    return null;
  }

  function writeCacheEntry(store, key, payload) {
    try {
      store.setItem(key, JSON.stringify(payload));
    } catch (_) {
    }
  }

  function writeCachedJson(url, data) {
    const key = getApiCacheKey(url);
    const payload = { ts: Date.now(), data: data };
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
      } catch (_) {}
    };
    clearStore(sessionStorage);
    clearStore(localStorage);
  }

  function readCachedOrNull(url, options) {
    const ttlMs = resolveCacheTtlMs(url, options || {});
    if (isCacheDisabled(options) || ttlMs <= 0) return null;
    return readCachedJson(url, ttlMs, 0);
  }

  function getInflightKey(url, options) {
    const opts = options || {};
    const method = String(opts.method || "GET").toUpperCase();
    return `${method}:${String(url || "")}`;
  }

  async function fetchJsonAndCache(url, options) {
    const opts = options || {};
    const res = await apiFetch(url, opts);
    if (!res.ok) {
      const err = new Error("HTTP " + res.status);
      err.status = res.status;
      err.response = res;
      throw err;
    }
    const data = await res.json();
    const ttlMs = resolveCacheTtlMs(url, opts);
    if (!isCacheDisabled(opts) && ttlMs > 0) writeCachedJson(url, data);
    return data;
  }

  async function fetchWithStaleFallback(url, options) {
    try {
      return await fetchJsonAndCache(url, options || {});
    } catch (err) {
      if (!isCacheDisabled(options || {})) {
        const stale = readCachedJson(url, 0, API_CACHE_MAX_STALE_MS);
        if (stale !== null) return stale;
      }
      throw err;
    }
  }

  async function apiFetch(url, options) {
    const opts = Object.assign({ credentials: "same-origin" }, options || {});
    const res = await fetch(url, opts);
    handleAuthFailure(res, opts);
    return res;
  }

  async function apiGetJson(url, options) {
    const opts = options || {};
    const cached = readCachedOrNull(url, opts);
    if (cached !== null) return cached;

    const inflightKey = getInflightKey(url, opts);
    if (API_INFLIGHT.has(inflightKey)) {
      return API_INFLIGHT.get(inflightKey);
    }

    const p = (async () => {
      try {
        return await fetchWithStaleFallback(url, opts);
      } finally {
        API_INFLIGHT.delete(inflightKey);
      }
    })();

    API_INFLIGHT.set(inflightKey, p);
    return p;
  }

  async function apiPostJson(url, body, options) {
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

  async function apiPostForm(url, formData, options) {
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

  global.SharedApi = Object.assign(global.SharedApi || {}, {
    apiFetch,
    apiGetJson,
    apiPostJson,
    apiPostForm,
  });

  if (!global.apiFetch) global.apiFetch = apiFetch;
  if (!global.apiGetJson) global.apiGetJson = apiGetJson;
  if (!global.apiPostJson) global.apiPostJson = apiPostJson;
  if (!global.apiPostForm) global.apiPostForm = apiPostForm;
})(window);
