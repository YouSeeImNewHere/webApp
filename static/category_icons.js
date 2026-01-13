// static/category_icons.js

function normalizeCategoryKey(cat) {
  return String(cat || "")
    .trim()
    .toLowerCase(); // IMPORTANT: assumes your SVG filenames are lowercase
}

const DEFAULT_CATEGORY_ICON = "/static/icons/categories/default.svg";

/**
 * Assumes icon filenames match the normalized category key:
 *   "Self Care"  -> "self care.svg"
 *   "Card Payment" -> "card payment.svg"
 *
 * (Spaces are fine; the browser will request %20 in the URL.)
 */
function categoryIconUrl(category) {
  const key = normalizeCategoryKey(category);
  return key
    ? `/static/icons/categories/${encodeURIComponent(key)}.svg`
    : DEFAULT_CATEGORY_ICON;
}

/**
 * Returns ONLY the <img>. The surrounding .tx-icon-wrap is provided by the page renderer.
 */
function categoryIconHTML(category, extraTitle = "") {
  const title = extraTitle || (category ? String(category) : "Uncategorized");
  const src = categoryIconUrl(category);

  return `
    <img class="tx-icon" src="${src}" alt="" title="${title}"
         onerror="this.onerror=null;this.src='${DEFAULT_CATEGORY_ICON}'">
  `;
}

// Optional: if other files import these
window.categoryIconUrl = categoryIconUrl;
window.categoryIconHTML = categoryIconHTML;
window.normalizeCategoryKey = normalizeCategoryKey;
