import type { NewsArticle } from "../api";

export type NewsPreset = "all" | "breaking" | "earnings" | "corporate" | "macro" | "press";

const corporateCategories = new Set(["merger_acquisition", "buyback", "dividend", "stock_split", "capital_raise"]);
const macroCategories = new Set(["macro", "central_bank", "economic_data", "government_policy"]);

export function categoryMatchesPreset(article: NewsArticle, preset: NewsPreset) {
  const codes = new Set(article.categories.map((item) => item.category_code));
  if (preset === "corporate") return [...codes].some((code) => corporateCategories.has(code));
  if (preset === "macro") return [...codes].some((code) => macroCategories.has(code));
  return true;
}
