export type PageFeatureDefinition = {
  id: string;
  pageId: string;
  label: string;
  description?: string;
  category?: string;
  defaultEnabled: boolean;
  configurable: boolean;
  order?: number;
};

export type ConfigurablePageDefinition = {
  id: string;
  label: string;
  description?: string;
  features: PageFeatureDefinition[];
};

export type PageFeaturePreferences = Record<string, boolean>;
export type PageFeaturePreferenceStore = {
  version: number;
  pages: Record<string, PageFeaturePreferences>;
};

export const PAGE_FEATURE_STORAGE_KEY = "quaint_dash_page_features";
export const PAGE_FEATURE_STORAGE_VERSION = 1;

export const pageFeatureRegistry: ConfigurablePageDefinition[] = [
  {
    id: "overview",
    label: "Overview",
    description: "Choose optional status panels on the overview page.",
    features: [
      { id: "overview.quickActions", pageId: "overview", label: "Next action panel", category: "Status", defaultEnabled: true, configurable: true, order: 10 },
      { id: "overview.marketNews", pageId: "overview", label: "Market notes", category: "News", defaultEnabled: true, configurable: true, order: 20 },
    ],
  },
  {
    id: "portfolio.workspace",
    label: "Portfolio workspace",
    description: "Choose optional aggregate portfolio panels.",
    features: [
      { id: "portfolio.workspace.allocation", pageId: "portfolio.workspace", label: "Aggregate allocation", category: "Exposure", defaultEnabled: true, configurable: true, order: 10 },
      { id: "portfolio.workspace.dataQuality", pageId: "portfolio.workspace", label: "Coverage panel", category: "Data quality", defaultEnabled: true, configurable: true, order: 20 },
      { id: "portfolio.workspace.fundamentals", pageId: "portfolio.workspace", label: "Fundamentals tab", category: "Analytics", defaultEnabled: false, configurable: true, order: 30 },
    ],
  },
  {
    id: "portfolio.detail",
    label: "Portfolio detail",
    description: "Choose optional analytics sections for an individual portfolio.",
    features: [
      { id: "portfolio.detail.overviewAllocation", pageId: "portfolio.detail", label: "Overview allocation", category: "Overview", defaultEnabled: true, configurable: true, order: 10 },
      { id: "portfolio.detail.overviewRisk", pageId: "portfolio.detail", label: "Overview risk panel", category: "Overview", defaultEnabled: true, configurable: true, order: 20 },
      { id: "portfolio.detail.overviewFundamentals", pageId: "portfolio.detail", label: "Overview fundamentals", category: "Overview", defaultEnabled: true, configurable: true, order: 30 },
      { id: "portfolio.detail.overviewLargestHoldings", pageId: "portfolio.detail", label: "Largest holdings", category: "Overview", defaultEnabled: true, configurable: true, order: 40 },
      { id: "portfolio.detail.holdingGrades", pageId: "portfolio.detail", label: "Holding grade charts", category: "Holdings", defaultEnabled: true, configurable: true, order: 50 },
      { id: "portfolio.detail.riskTab", pageId: "portfolio.detail", label: "Risk tab", category: "Tabs", defaultEnabled: true, configurable: true, order: 60 },
      { id: "portfolio.detail.optimizationTab", pageId: "portfolio.detail", label: "Optimization tab", category: "Tabs", defaultEnabled: false, configurable: true, order: 70 },
      { id: "portfolio.detail.fundamentalsTab", pageId: "portfolio.detail", label: "Fundamentals tab", category: "Tabs", defaultEnabled: true, configurable: true, order: 80 },
      { id: "portfolio.detail.activityTab", pageId: "portfolio.detail", label: "Activity tab", category: "Tabs", defaultEnabled: false, configurable: true, order: 90 },
    ],
  },
  {
    id: "asset",
    label: "Asset detail",
    description: "Choose optional asset detail tabs and supporting audit sections.",
    features: [
      { id: "asset.newsTab", pageId: "asset", label: "News and activity tab", category: "Tabs", defaultEnabled: true, configurable: true, order: 10 },
      { id: "asset.fundamentalsTab", pageId: "asset", label: "Fundamentals tab", category: "Tabs", defaultEnabled: true, configurable: true, order: 20 },
      { id: "asset.businessStrengthTab", pageId: "asset", label: "Business Strength tab", category: "Tabs", defaultEnabled: true, configurable: true, order: 30 },
      { id: "asset.businessStrengthDrivers", pageId: "asset", label: "Business Strength drivers", category: "Business Strength", defaultEnabled: true, configurable: true, order: 40 },
      { id: "asset.businessStrengthCategoryAudit", pageId: "asset", label: "Category metric audit", category: "Business Strength", defaultEnabled: false, configurable: true, order: 50 },
      { id: "asset.businessStrengthFullAudit", pageId: "asset", label: "Full calculation audit", category: "Business Strength", defaultEnabled: false, configurable: true, order: 60 },
    ],
  },
  {
    id: "compare",
    label: "Compare",
    description: "Choose optional comparison analytics while keeping asset controls fixed.",
    features: [
      { id: "compare.assetStrip", pageId: "compare", label: "Asset summary strip", category: "Summary", defaultEnabled: true, configurable: true, order: 10 },
      { id: "compare.chartTable", pageId: "compare", label: "Accessible chart data table", category: "Chart", defaultEnabled: false, configurable: true, order: 20 },
      { id: "compare.valuation", pageId: "compare", label: "Valuation metrics", category: "Metric groups", defaultEnabled: true, configurable: true, order: 30 },
      { id: "compare.growth", pageId: "compare", label: "Growth metrics", category: "Metric groups", defaultEnabled: true, configurable: true, order: 40 },
      { id: "compare.quality", pageId: "compare", label: "Quality metrics", category: "Metric groups", defaultEnabled: true, configurable: true, order: 50 },
      { id: "compare.balanceSheet", pageId: "compare", label: "Balance sheet metrics", category: "Metric groups", defaultEnabled: true, configurable: true, order: 60 },
      { id: "compare.capitalAllocation", pageId: "compare", label: "Capital allocation metrics", category: "Metric groups", defaultEnabled: false, configurable: true, order: 70 },
      { id: "compare.forwardScenarios", pageId: "compare", label: "Forward scenarios", category: "Scenarios", defaultEnabled: false, configurable: true, order: 80 },
      { id: "compare.methodology", pageId: "compare", label: "Methodology notes", category: "Data quality", defaultEnabled: false, configurable: true, order: 90 },
    ],
  },
  {
    id: "signals",
    label: "Signals",
    description: "Choose optional signal context panels.",
    features: [
      { id: "signals.summaryStrip", pageId: "signals", label: "Summary metric strip", category: "Summary", defaultEnabled: true, configurable: true, order: 10 },
      { id: "signals.priorityPanels", pageId: "signals", label: "Priority panels", category: "Priority", defaultEnabled: true, configurable: true, order: 20 },
      { id: "signals.methodology", pageId: "signals", label: "Methodology note", category: "Data quality", defaultEnabled: false, configurable: true, order: 30 },
    ],
  },
  {
    id: "benchmarks",
    label: "Benchmarks",
    description: "Choose optional benchmark comparison and diagnostic panels.",
    features: [
      { id: "benchmarks.snapshot", pageId: "benchmarks", label: "Market snapshot cards", category: "Summary", defaultEnabled: true, configurable: true, order: 10 },
      { id: "benchmarks.comparisonChart", pageId: "benchmarks", label: "Benchmark comparison chart", category: "Chart", defaultEnabled: true, configurable: true, order: 20 },
      { id: "benchmarks.leadership", pageId: "benchmarks", label: "Leadership and risk watch", category: "Rankings", defaultEnabled: true, configurable: true, order: 30 },
      { id: "benchmarks.status", pageId: "benchmarks", label: "Freshness diagnostics", category: "Data quality", defaultEnabled: false, configurable: true, order: 40 },
    ],
  },
  {
    id: "benchmark.detail",
    label: "Benchmark detail",
    description: "Choose optional benchmark detail panels.",
    features: [
      { id: "benchmark.detail.risk", pageId: "benchmark.detail", label: "Computed risk panel", category: "Risk", defaultEnabled: true, configurable: true, order: 10 },
      { id: "benchmark.detail.identity", pageId: "benchmark.detail", label: "Benchmark profile", category: "Metadata", defaultEnabled: true, configurable: true, order: 20 },
      { id: "benchmark.detail.quality", pageId: "benchmark.detail", label: "Freshness and disclosure", category: "Data quality", defaultEnabled: true, configurable: true, order: 30 },
      { id: "benchmark.detail.exposure", pageId: "benchmark.detail", label: "Exposure snapshot", category: "Composition", defaultEnabled: true, configurable: true, order: 40 },
      { id: "benchmark.detail.constituents", pageId: "benchmark.detail", label: "Top constituents", category: "Composition", defaultEnabled: true, configurable: true, order: 50 },
      { id: "benchmark.detail.actions", pageId: "benchmark.detail", label: "Manual refresh actions", category: "Operations", defaultEnabled: true, configurable: true, order: 60 },
    ],
  },
  {
    id: "brokers",
    label: "Brokers",
    description: "Choose optional broker summaries while preserving connection and import workflows.",
    features: [
      { id: "brokers.summaryCards", pageId: "brokers", label: "Broker summary cards", category: "Summary", defaultEnabled: true, configurable: true, order: 10 },
    ],
  },
  {
    id: "operations",
    label: "Operations",
    description: "Choose optional operations status cards.",
    features: [
      { id: "operations.routineWorker", pageId: "operations", label: "Routine ingestion worker", category: "Workers", defaultEnabled: true, configurable: true, order: 10 },
      { id: "operations.marketFreshness", pageId: "operations", label: "Market freshness worker", category: "Workers", defaultEnabled: true, configurable: true, order: 20 },
      { id: "operations.dataReadiness", pageId: "operations", label: "Portfolio data worker", category: "Workers", defaultEnabled: true, configurable: true, order: 30 },
      { id: "operations.projectionReadiness", pageId: "operations", label: "Projection readiness", category: "Readiness", defaultEnabled: true, configurable: true, order: 40 },
      { id: "operations.rankingReadiness", pageId: "operations", label: "Ranking readiness", category: "Readiness", defaultEnabled: true, configurable: true, order: 50 },
    ],
  },
];

export const configurablePageIds = new Set(pageFeatureRegistry.map((page) => page.id));

export function getPageDefinition(pageId: string) {
  return pageFeatureRegistry.find((page) => page.id === pageId) ?? null;
}

export function getConfigurableFeatures(pageId: string) {
  return (getPageDefinition(pageId)?.features ?? [])
    .filter((feature) => feature.configurable)
    .sort((left, right) => (left.order ?? 0) - (right.order ?? 0) || left.label.localeCompare(right.label));
}

export function getFeatureDefinition(pageId: string, featureId: string) {
  return getPageDefinition(pageId)?.features.find((feature) => feature.id === featureId) ?? null;
}

export function getDefaultPagePreferences(pageId: string): PageFeaturePreferences {
  return Object.fromEntries(getConfigurableFeatures(pageId).map((feature) => [feature.id, feature.defaultEnabled]));
}

export function sanitizePageFeatureStore(value: unknown): PageFeaturePreferenceStore {
  if (!value || typeof value !== "object") return { version: PAGE_FEATURE_STORAGE_VERSION, pages: {} };
  const source = value as { version?: unknown; pages?: unknown };
  if (source.version !== PAGE_FEATURE_STORAGE_VERSION || !source.pages || typeof source.pages !== "object") {
    return { version: PAGE_FEATURE_STORAGE_VERSION, pages: {} };
  }
  const pages: Record<string, PageFeaturePreferences> = {};
  Object.entries(source.pages as Record<string, unknown>).forEach(([pageId, rawPreferences]) => {
    const page = getPageDefinition(pageId);
    if (!page || !rawPreferences || typeof rawPreferences !== "object") return;
    const validIds = new Set(page.features.map((feature) => feature.id));
    const preferences: PageFeaturePreferences = {};
    Object.entries(rawPreferences as Record<string, unknown>).forEach(([featureId, enabled]) => {
      if (validIds.has(featureId) && typeof enabled === "boolean") preferences[featureId] = enabled;
    });
    if (Object.keys(preferences).length) pages[pageId] = preferences;
  });
  return { version: PAGE_FEATURE_STORAGE_VERSION, pages };
}

export function resolvePageFeaturePreferences(pageId: string, store: PageFeaturePreferenceStore): PageFeaturePreferences {
  return { ...getDefaultPagePreferences(pageId), ...(store.pages[pageId] ?? {}) };
}

export function isFeatureEnabled(pageId: string, featureId: string, store: PageFeaturePreferenceStore) {
  const definition = getFeatureDefinition(pageId, featureId);
  if (!definition) return true;
  if (!definition.configurable) return true;
  return resolvePageFeaturePreferences(pageId, store)[featureId] ?? definition.defaultEnabled;
}

export function validatePageFeatureRegistry(registry = pageFeatureRegistry) {
  const pageIds = new Set<string>();
  const featureIds = new Set<string>();
  const errors: string[] = [];
  registry.forEach((page) => {
    if (!page.id || !page.label) errors.push("Every page needs an id and label.");
    if (pageIds.has(page.id)) errors.push(`Duplicate page id: ${page.id}`);
    pageIds.add(page.id);
    page.features.forEach((feature) => {
      if (feature.pageId !== page.id) errors.push(`${feature.id} has mismatched pageId ${feature.pageId}.`);
      if (!feature.id.startsWith(`${page.id}.`) && page.id !== "asset") errors.push(`${feature.id} should start with its page id.`);
      if (!feature.label.trim()) errors.push(`${feature.id} is missing a label.`);
      if (typeof feature.defaultEnabled !== "boolean") errors.push(`${feature.id} is missing a boolean default.`);
      if (featureIds.has(feature.id)) errors.push(`Duplicate feature id: ${feature.id}`);
      featureIds.add(feature.id);
    });
  });
  return errors;
}
