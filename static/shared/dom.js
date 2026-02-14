// /static/shared/dom.js
(function (global) {
  "use strict";

  function escapeHtml(s) {
    return String(s ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function escapeHtmlAttr(s) {
    return String(s || "")
      .replaceAll("&", "&amp;")
      .replaceAll('"', "&quot;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;");
  }

  function cssEscapeAttr(s) {
    return String(s || "").replaceAll('"', "&quot;");
  }

  global.SharedDom = Object.assign(global.SharedDom || {}, {
    escapeHtml,
    escapeHtmlAttr,
    cssEscapeAttr,
  });

  if (!global.escapeHtml) global.escapeHtml = escapeHtml;
  if (!global.escapeHtmlAttr) global.escapeHtmlAttr = escapeHtmlAttr;
  if (!global.cssEscapeAttr) global.cssEscapeAttr = cssEscapeAttr;
})(window);
