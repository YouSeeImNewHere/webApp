// /static/shared/api.js
(function (global) {
  "use strict";

  async function apiFetch(url, options) {
    const opts = Object.assign({ credentials: "same-origin" }, options || {});
    return fetch(url, opts);
  }

  async function apiGetJson(url, options) {
    const res = await apiFetch(url, options);
    if (!res.ok) {
      const err = new Error("HTTP " + res.status);
      err.status = res.status;
      err.response = res;
      throw err;
    }
    return res.json();
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
    return res.json();
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
    return res.json();
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
