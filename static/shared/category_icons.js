function normalizeCategoryKey(cat) {
  return String(cat || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")   // spaces & symbols → hyphen
    .replace(/^-+|-+$/g, "");     // trim leading/trailing hyphens
}

const DEFAULT_CATEGORY_ICON = "/static/icons/categories/default.svg";
const AVAILABLE_CATEGORY_ICONS = new Set([
  "bills",
  "cash-withdrawal",
  "default",
  "food",
  "games",
  "parking",
  "shopping",
  "snack",
  "transportation",
  "travel",
]);

/**
 * Assumes icon filenames use kebab-case:
 *   "Self Care"    -> "self-care.svg"
 *   "Card Payment" -> "card-payment.svg"
 */
function categoryIconUrl(category) {
  const key = normalizeCategoryKey(category);
  if (!key) return DEFAULT_CATEGORY_ICON;
  if (!AVAILABLE_CATEGORY_ICONS.has(key)) return DEFAULT_CATEGORY_ICON;
  return `/static/icons/categories/${key}.svg`;
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
