// Minimal shared state hub (incremental migration helper).
(function () {
  const listeners = new Map();
  const values = Object.create(null);

  function get(key) { return values[key]; }
  function set(key, value) {
    values[key] = value;
    const subs = listeners.get(key);
    if (!subs) return;
    for (const cb of subs) {
      try { cb(value); } catch (_) {}
    }
  }
  function subscribe(key, cb) {
    if (!listeners.has(key)) listeners.set(key, new Set());
    listeners.get(key).add(cb);
    return () => listeners.get(key)?.delete(cb);
  }

  window.AppState = { get, set, subscribe };
})();
