export async function apiFetch(url, options = {}) {
  const opts = Object.assign({ credentials: "same-origin" }, options || {});
  return fetch(url, opts);
}

export async function apiGetJson(url, options = {}) {
  const res = await apiFetch(url, options);
  if (!res.ok) {
    const err = new Error("HTTP " + res.status);
    err.status = res.status;
    err.response = res;
    throw err;
  }
  return res.json();
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
  return res.json();
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
  return res.json();
}
