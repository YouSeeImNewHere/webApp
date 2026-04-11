function redirectToLogin() {
  const path = `${window.location.pathname || "/"}${window.location.search || ""}${window.location.hash || ""}`;
  const next = encodeURIComponent(path || "/");
  window.location.assign(`/login?next=${next}`);
}

const API_CACHE_PREFIX = "api:get:v1:";
const API_CACHE_DEFAULT_TTL_MS = 3 * 60 * 1000;
const API_CACHE_MAX_STALE_MS = 24 * 60 * 60 * 1000;
const API_INFLIGHT = new Map();
const API_MUTATION_INFLIGHT = new Map();
const GLOBAL_FETCH_INFLIGHT = new Map();
const GLOBAL_FETCH_TIMEOUT_MS = 25000;
const GLOBAL_FETCH_MAX_RETRIES = 1;
const DEFAULT_API_SLOW_MS = 500;
const CLIENT_ERROR_ENDPOINT = "/admin/error-notifications/client";
const CLIENT_ERROR_MAX_EVENTS = 25;
const CLIENT_ERROR_DEDUPE_MS = 20000;
const CLIENT_ERROR_RECENT = new Map();
let CLIENT_ERROR_SENT_COUNT = 0;

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

function getMutationKey(url, options = {}) {
  const method = String(options.method || "POST").toUpperCase();
  const body = (typeof options.body === "string") ? options.body : "";
  return `${method}:${String(url || "")}:${body}`;
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function nowMs() {
  if (typeof window !== "undefined" && window.performance && typeof window.performance.now === "function") {
    return window.performance.now();
  }
  return Date.now();
}

function readStorageFlag(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    if (raw === null || raw === undefined || raw === "") return fallback;
    return raw;
  } catch {
    return fallback;
  }
}

function isApiTimingEnabled() {
  const localFlag = String(readStorageFlag("debug_api_timing", "")).toLowerCase();
  if (localFlag === "1" || localFlag === "true" || localFlag === "yes") return true;
  return !!(typeof window !== "undefined" && window.__DEBUG_API_TIMING === true);
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
  const log = (typeof console[level] === "function") ? console[level].bind(console) : console.log.bind(console);
  log(
    `[api-timing] ${String(method || "GET")} ${String(url || "")} status=${status} ms=${Math.round(elapsedMs)} attempts=${attempts}`,
  );
}

function shouldRetryStatus(status) {
  return status === 408 || status === 429 || status === 502 || status === 503 || status === 504;
}

function normalizeClientErrorKey(input) {
  return String(input || "").slice(0, 300);
}

function shouldSendClientError(key) {
  if (!key) return false;
  if (CLIENT_ERROR_SENT_COUNT >= CLIENT_ERROR_MAX_EVENTS) return false;
  const now = Date.now();
  const prev = Number(CLIENT_ERROR_RECENT.get(key) || 0);
  if (prev > 0 && now - prev < CLIENT_ERROR_DEDUPE_MS) return false;
  CLIENT_ERROR_RECENT.set(key, now);
  CLIENT_ERROR_SENT_COUNT += 1;
  if (CLIENT_ERROR_RECENT.size > 120) {
    const cutoff = now - (CLIENT_ERROR_DEDUPE_MS * 2);
    for (const [k, ts] of CLIENT_ERROR_RECENT.entries()) {
      if (Number(ts) < cutoff) CLIENT_ERROR_RECENT.delete(k);
    }
  }
  return true;
}

function sendClientErrorReport(payload, dedupeKey = "") {
  if (typeof window === "undefined") return;
  const key = normalizeClientErrorKey(dedupeKey || payload?.message || payload?.source || "client-error");
  if (!shouldSendClientError(key)) return;

  let body = "{}";
  try {
    body = JSON.stringify(payload || {});
  } catch {
    body = JSON.stringify({ source: "client_report_json_error", message: "Failed to serialize payload" });
  }

  try {
    if (navigator && typeof navigator.sendBeacon === "function") {
      const blob = new Blob([body], { type: "application/json" });
      navigator.sendBeacon(CLIENT_ERROR_ENDPOINT, blob);
      return;
    }
  } catch {}

  try {
    fetch(CLIENT_ERROR_ENDPOINT, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body,
      keepalive: true,
    }).catch(() => {});
  } catch {}
}

function installClientErrorTracking() {
  if (typeof window === "undefined") return;
  if (window.__clientErrorTrackingInstalled) return;
  window.__clientErrorTrackingInstalled = true;

  window.addEventListener("error", (evt) => {
    try {
      const target = evt && evt.target;
      const isResourceError = !!(target && target !== window);
      const message = isResourceError
        ? `resource_load_failed: ${String(target?.tagName || "unknown")}`
        : String(evt?.message || "window_error");
      const stack = String(evt?.error?.stack || "").slice(0, 3000);
      const source = isResourceError ? "resource_error" : "window_error";
      const requestUrl = String(evt?.filename || target?.src || target?.href || "").slice(0, 1000);
      sendClientErrorReport(
        {
          source,
          message,
          stack,
          page_url: String(window.location.href || "").slice(0, 1000),
          route: `${window.location.pathname || "/"}${window.location.search || ""}`,
          request_url: requestUrl || null,
          request_method: "CLIENT",
          status_code: 0,
          user_agent: String(navigator?.userAgent || "").slice(0, 500),
        },
        `${source}:${message}:${requestUrl}`,
      );
    } catch {}
  }, true);

  window.addEventListener("unhandledrejection", (evt) => {
    try {
      const reason = evt?.reason;
      const msg = (reason && (reason.message || String(reason))) || "unhandled_rejection";
      const stack = String(reason?.stack || "").slice(0, 3000);
      sendClientErrorReport(
        {
          source: "unhandled_rejection",
          message: String(msg).slice(0, 1000),
          stack,
          page_url: String(window.location.href || "").slice(0, 1000),
          route: `${window.location.pathname || "/"}${window.location.search || ""}`,
          request_method: "CLIENT",
          status_code: 0,
          user_agent: String(navigator?.userAgent || "").slice(0, 500),
        },
        `unhandled_rejection:${String(msg).slice(0, 200)}`,
      );
    } catch {}
  });
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
  if (!(timeoutMs > 0)) return { opts, cleanup: null };
  if (opts.signal && opts.signal.aborted) return { opts, cleanup: null };

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  const cleanup = () => clearTimeout(timeoutId);

  if (opts.signal) {
    opts.signal.addEventListener("abort", () => controller.abort(), { once: true });
  }
  opts.signal = controller.signal;
  return { opts, cleanup };
}

async function rawFetchWithRetry(nativeFetch, input, init, method) {
  let attempt = 0;
  const url = resolveUrl(input);
  const startMs = nowMs();
  while (true) {
    const timeoutSetup = withTimeoutOptions(init, (method === "GET" || method === "HEAD") ? GLOBAL_FETCH_TIMEOUT_MS : 0);
    const reqOpts = timeoutSetup.opts || {};
    try {
      if (typeof window !== "undefined" && String(url || "").startsWith("/")) {
        const headers = new Headers(reqOpts.headers || {});
        const href = String(window.location.href || "");
        if (href) headers.set("X-Client-Page-Url", href.slice(0, 1000));
        const route = `${window.location.pathname || "/"}${window.location.search || ""}`;
        if (route) headers.set("X-Client-Page-Route", route.slice(0, 500));
        let preview = "";
        try {
          preview = String(localStorage.getItem("settings_view_non_admin_preview") || "").trim();
        } catch {}
        if (preview === "1") headers.set("X-Non-Admin-Preview", "1");
        reqOpts.headers = headers;
      }
    } catch {}
    try {
      const res = await nativeFetch(input, reqOpts);
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

export function installGlobalFetchOptimizations() {
  if (typeof window === "undefined" || typeof window.fetch !== "function") return;
  if (window.__sharedApiFetchOptimized) return;
  const nativeFetch = window.fetch.bind(window);

  window.fetch = function(input, init) {
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

  window.__sharedApiFetchOptimized = true;
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
  try {
    const res = await fetch(url, opts);
    handleAuthFailure(res, opts);
    const status = Number(res.status || 0);
    const urlStr = String(url || "");
    const isClientErrorEndpoint = urlStr.indexOf(CLIENT_ERROR_ENDPOINT) === 0;
    if (!isClientErrorEndpoint && status >= 400 && !opts.skipClientErrorReport) {
      const method = String(opts.method || "GET").toUpperCase();
      let detailText = "";
      try {
        const clone = res.clone();
        const ct = String(clone.headers.get("content-type") || "").toLowerCase();
        if (ct.includes("application/json")) {
          const data = await clone.json().catch(() => null);
          if (data && typeof data === "object") {
            if (typeof data.detail === "string") detailText = data.detail;
            else detailText = JSON.stringify(data);
          }
        } else {
          detailText = String(await clone.text().catch(() => "") || "");
        }
      } catch {}
      const msg = `HTTP ${status} ${method} ${urlStr}${detailText ? ` | ${detailText}` : ""}`.slice(0, 1800);
      sendClientErrorReport(
        {
          source: "api_response",
          message: msg,
          page_url: String(window.location.href || "").slice(0, 1000),
          route: `${window.location.pathname || "/"}${window.location.search || ""}`,
          request_url: urlStr.slice(0, 1000),
          request_method: method,
          status_code: status,
          user_agent: String(navigator?.userAgent || "").slice(0, 500),
        },
        `api_response:${status}:${method}:${urlStr}`,
      );
    }
    return res;
  } catch (err) {
    if (!opts.skipClientErrorReport) {
      const method = String(opts.method || "GET").toUpperCase();
      const urlStr = String(url || "");
      sendClientErrorReport(
        {
          source: "api_fetch_exception",
          message: String(err?.message || err || "fetch_failed").slice(0, 1000),
          stack: String(err?.stack || "").slice(0, 3000),
          page_url: String(window.location.href || "").slice(0, 1000),
          route: `${window.location.pathname || "/"}${window.location.search || ""}`,
          request_url: urlStr.slice(0, 1000),
          request_method: method,
          status_code: 0,
          user_agent: String(navigator?.userAgent || "").slice(0, 500),
        },
        `api_fetch_exception:${method}:${urlStr}:${String(err?.message || "").slice(0, 200)}`,
      );
    }
    throw err;
  }
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

installGlobalFetchOptimizations();
installClientErrorTracking();
