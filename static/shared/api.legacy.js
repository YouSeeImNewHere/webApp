import { startLoading, stopLoading, signalError } from "./loading.js";

export async function apiFetch(url, options = {}) {
  startLoading();

  try {
    const res = await fetch(url, options);

    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }

    return res;
  } catch (err) {
    console.error("API error:", err);
    signalError();
    throw err;
  } finally {
    stopLoading();
  }
}
