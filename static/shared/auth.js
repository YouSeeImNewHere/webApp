// Minimal auth helper for the new shared layer.
(function () {
  function isLoggedIn() {
    try {
      return Boolean(localStorage.getItem("token"));
    } catch (_) {
      return false;
    }
  }

  window.Auth = { isLoggedIn };
})();
