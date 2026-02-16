// /static/shared/api.js
(function (global) {
  "use strict";

  const API_CACHE_PREFIX = "api:get:v1:";
  const API_CACHE_DEFAULT_TTL_MS = 3 * 60 * 1000;
  const API_CACHE_MAX_STALE_MS = 24 * 60 * 60 * 1000;
  const API_INFLIGHT = new Map();
  const API_MUTATION_INFLIGHT = new Map();
  const GLOBAL_FETCH_INFLIGHT = new Map();
  const GLOBAL_FETCH_TIMEOUT_MS = 25000;
  const GLOBAL_FETCH_MAX_RETRIES = 1;
  const DEFAULT_API_SLOW_MS = 500;
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

  function getMutationKey(url, options) {
    const opts = options || {};
    const method = String(opts.method || "POST").toUpperCase();
    const body = (typeof opts.body === "string") ? opts.body : "";
    return `${method}:${String(url || "")}:${body}`;
  }

  function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  function nowMs() {
    if (global && global.performance && typeof global.performance.now === "function") {
      return global.performance.now();
    }
    return Date.now();
  }

  function readStorageFlag(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      if (raw === null || raw === undefined || raw === "") return fallback;
      return raw;
    } catch (_) {
      return fallback;
    }
  }

  function isApiTimingEnabled() {
    const localFlag = String(readStorageFlag("debug_api_timing", "")).toLowerCase();
    if (localFlag === "1" || localFlag === "true" || localFlag === "yes") return true;
    return !!(global && global.__DEBUG_API_TIMING === true);
  }

  function getSlowThresholdMs() {
    const raw = Number(readStorageFlag("debug_api_slow_ms", DEFAULT_API_SLOW_MS));
    if (Number.isFinite(raw) && raw > 0) return raw;
    return DEFAULT_API_SLOW_MS;
  }

  function shouldLogTimedUrl(url) {
    const u = String(url || "");
    if (!u) return false;
    if (u.indexOf("/static/") === 0) return false;
    return true;
  }

  function maybeLogApiTiming(url, method, elapsedMs, status, attempts) {
    if (!isApiTimingEnabled()) return;
    if (!shouldLogTimedUrl(url)) return;
    const slowMs = getSlowThresholdMs();
    const level = elapsedMs >= slowMs ? "warn" : "info";
    const log = (console && typeof console[level] === "function") ? console[level].bind(console) : console.log.bind(console);
    log(
      `[api-timing] ${String(method || "GET")} ${String(url || "")} status=${status} ms=${Math.round(elapsedMs)} attempts=${attempts}`,
    );
  }

  function shouldRetryStatus(status) {
    return status === 408 || status === 429 || status === 502 || status === 503 || status === 504;
  }

  function resolveMethod(input, init) {
    if (init && init.method) return String(init.method).toUpperCase();
    if (input && typeof input === "object" && input.method) return String(input.method).toUpperCase();
    return "GET";
  }

  function resolveUrl(input) {
    if (typeof input === "string") return input;
    if (input && typeof input === "object" && typeof input.url === "string") return input.url;
    return "";
  }

  function resolveDedupeKey(input, init, method, url) {
    if (!url) return "";
    if (method === "GET" || method === "HEAD") return `${method}:${url}`;
    const mutation = (method === "POST" || method === "PUT" || method === "PATCH" || method === "DELETE");
    if (!mutation) return "";
    const body = init && init.body;
    if (typeof body === "string") return `${method}:${url}:${body}`;
    return "";
  }

  function withTimeoutOptions(init, timeoutMs) {
    const opts = Object.assign({}, init || {});
    if (!(timeoutMs > 0)) return { opts: opts, cleanup: null };
    if (opts.signal && opts.signal.aborted) return { opts: opts, cleanup: null };

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
    const cleanup = () => clearTimeout(timeoutId);

    if (opts.signal) {
      opts.signal.addEventListener("abort", () => controller.abort(), { once: true });
    }
    opts.signal = controller.signal;
    return { opts: opts, cleanup: cleanup };
  }

  async function rawFetchWithRetry(nativeFetch, input, init, method) {
    let attempt = 0;
    const url = resolveUrl(input);
    const startMs = nowMs();
    while (true) {
      const timeoutSetup = withTimeoutOptions(init, (method === "GET" || method === "HEAD") ? GLOBAL_FETCH_TIMEOUT_MS : 0);
      try {
        const res = await nativeFetch(input, timeoutSetup.opts);
        if (attempt < GLOBAL_FETCH_MAX_RETRIES && (method === "GET" || method === "HEAD") && shouldRetryStatus(res.status)) {
          attempt += 1;
          await sleep(200 * attempt);
          continue;
        }
        maybeLogApiTiming(url, method, nowMs() - startMs, res.status, attempt + 1);
        return res;
      } catch (err) {
        const retriable = (method === "GET" || method === "HEAD") && attempt < GLOBAL_FETCH_MAX_RETRIES;
        if (retriable) {
          attempt += 1;
          await sleep(200 * attempt);
          continue;
        }
        maybeLogApiTiming(url, method, nowMs() - startMs, "ERR", attempt + 1);
        throw err;
      } finally {
        if (typeof timeoutSetup.cleanup === "function") timeoutSetup.cleanup();
      }
    }
  }

  function installGlobalFetchOptimizations() {
    if (!global || typeof global.fetch !== "function") return;
    if (global.__sharedApiFetchOptimized) return;
    const nativeFetch = global.fetch.bind(global);

    global.fetch = function(input, init) {
      const method = resolveMethod(input, init);
      const url = resolveUrl(input);
      const dedupeKey = resolveDedupeKey(input, init, method, url);
      if (!dedupeKey) {
        return rawFetchWithRetry(nativeFetch, input, init, method);
      }

      if (GLOBAL_FETCH_INFLIGHT.has(dedupeKey)) {
        return GLOBAL_FETCH_INFLIGHT.get(dedupeKey).then(r => r.clone());
      }

      const p = rawFetchWithRetry(nativeFetch, input, init, method)
        .finally(() => {
          GLOBAL_FETCH_INFLIGHT.delete(dedupeKey);
        });
      GLOBAL_FETCH_INFLIGHT.set(dedupeKey, p);
      return p.then(r => r.clone());
    };

    global.__sharedApiFetchOptimized = true;
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
    const mutationKey = getMutationKey(url, opts);
    if (API_MUTATION_INFLIGHT.has(mutationKey)) {
      return API_MUTATION_INFLIGHT.get(mutationKey);
    }

    const p = (async () => {
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
    })()
      .finally(() => {
        API_MUTATION_INFLIGHT.delete(mutationKey);
      });

    API_MUTATION_INFLIGHT.set(mutationKey, p);
    return p;
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
  installGlobalFetchOptimizations();
})(window);
