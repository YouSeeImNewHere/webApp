function normalizeCategoryKey(cat) {
  return String(cat || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")   // spaces & symbols → hyphen
    .replace(/^-+|-+$/g, "");     // trim leading/trailing hyphens
}

const DEFAULT_CATEGORY_ICON = "/static/icons/categories/default.svg";

/**
 * Assumes icon filenames use kebab-case:
 *   "Self Care"    -> "self-care.svg"
 *   "Card Payment" -> "card-payment.svg"
 */
function categoryIconUrl(category) {
  const key = normalizeCategoryKey(category);
  return key
    ? `/static/icons/categories/${key}.svg`
    : DEFAULT_CATEGORY_ICON;
}

/**
 * Returns ONLY the <img>. The surrounding .tx-icon-wrap is provided by the page renderer.
 */
function categoryIconHTML(category, extraTitle = "") {
  const title = extraTitle || (category ? String(category) : "Uncategorized");
  const src = categoryIconUrl(category);

  return `
    <img class="tx-icon"
         src="${src}"
         alt=""
         title="${title}"
         onerror="this.onerror=null;this.src='${DEFAULT_CATEGORY_ICON}'">
  `;
}

// Optional: global exports
window.categoryIconUrl = categoryIconUrl;
window.categoryIconHTML = categoryIconHTML;
window.normalizeCategoryKey = normalizeCategoryKey;
