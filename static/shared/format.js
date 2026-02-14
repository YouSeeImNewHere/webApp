// /static/shared/format.js
(function (global) {
  "use strict";

  function money(n) {
    const num = Number(n || 0);
    return num.toLocaleString("en-US", { style: "currency", currency: "USD" });
  }

  function moneyOrDash(v) {
    if (v === null || v === undefined) return "—";
    const n = Number(v);
    if (Number.isNaN(n)) return String(v);
    return money(n);
  }

  global.SharedFormat = Object.assign(global.SharedFormat || {}, {
    money,
    moneyOrDash,
  });

  if (!global.money) global.money = money;
  if (!global.moneyOrDash) global.moneyOrDash = moneyOrDash;
})(window);
