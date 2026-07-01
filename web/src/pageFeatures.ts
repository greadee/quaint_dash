export type WidgetSize = "small" | "medium" | "large" | "wide" | "full";
export type WidgetGridFootprint = {
  columns: number;
  rows: number;
};

export type PageFeatureDefinition = {
  id: string;
  pageId: string;
  label: string;
  description?: string;
  category?: string;
  defaultEnabled: boolean;
  configurable: boolean;
  movable?: boolean;
  removable?: boolean;
  resizable?: boolean;
  defaultSize?: WidgetSize;
  supportedSizes?: WidgetSize[];
  footprints?: Partial<Record<WidgetSize, WidgetGridFootprint>>;
  defaultOrder?: number;
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
  layouts?: Record<string, PageLayoutPreference>;
};

export type WidgetLayoutItem = {
  widgetId: string;
  visible: boolean;
  size: WidgetSize;
  x: number;
  y: number;
  width: number;
  height: number;
};

export type PageLayoutPreference = {
  pageId: string;
  layoutVersion: number;
  updatedAt?: string;
  items: WidgetLayoutItem[];
};

export const PAGE_FEATURE_STORAGE_KEY = "quaint_dash_page_features";
export const PAGE_FEATURE_STORAGE_VERSION = 2;
export const PAGE_LAYOUT_VERSION = 1;
export const DASHBOARD_GRID_COLUMNS = 12;

export const defaultFootprints: Record<WidgetSize, WidgetGridFootprint> = {
  small: { columns: 3, rows: 2 },
  medium: { columns: 6, rows: 3 },
  large: { columns: 6, rows: 4 },
  wide: { columns: 8, rows: 4 },
  full: { columns: 12, rows: 4 },
};

const panelLayout = (defaultSize: WidgetSize, supportedSizes: WidgetSize[] = ["medium", "wide", "full"]) => ({
  movable: true,
  removable: true,
  resizable: supportedSizes.length > 1,
  defaultSize,
  supportedSizes,
});

export const pageFeatureRegistry: ConfigurablePageDefinition[] = [
  {
    id: "overview",
    label: "Overview",
    description: "Choose optional status panels on the overview page.",
    features: [
      { id: "overview.quickActions", pageId: "overview", label: "Next action panel", category: "Status", defaultEnabled: true, configurable: true, order: 10, ...panelLayout("medium", ["medium", "wide"]) },
      { id: "overview.marketNews", pageId: "overview", label: "Market notes", category: "News", defaultEnabled: true, configurable: true, order: 20, ...panelLayout("medium", ["medium", "wide"]) },
    ],
  },
  {
    id: "portfolio.workspace",
    label: "Portfolio workspace",
    description: "Choose optional aggregate portfolio panels.",
    features: [
      { id: "portfolio.workspace.allocation", pageId: "portfolio.workspace", label: "Aggregate allocation", category: "Exposure", defaultEnabled: true, configurable: true, order: 10, ...panelLayout("wide", ["medium", "wide", "full"]) },
      { id: "portfolio.workspace.dataQuality", pageId: "portfolio.workspace", label: "Coverage panel", category: "Data quality", defaultEnabled: true, configurable: true, order: 20, ...panelLayout("medium", ["medium", "wide"]) },
      { id: "portfolio.workspace.fundamentals", pageId: "portfolio.workspace", label: "Fundamentals tab", category: "Analytics", defaultEnabled: false, configurable: true, order: 30 },
    ],
  },
  {
    id: "portfolio.detail",
    label: "Portfolio detail",
    description: "Choose optional analytics sections for an individual portfolio.",
    features: [
      { id: "portfolio.detail.overviewAllocation", pageId: "portfolio.detail", label: "Overview allocation", category: "Overview", defaultEnabled: true, configurable: true, order: 10, ...panelLayout("wide", ["medium", "wide", "full"]) },
      { id: "portfolio.detail.overviewRisk", pageId: "portfolio.detail", label: "Overview risk panel", category: "Overview", defaultEnabled: true, configurable: true, order: 20, ...panelLayout("medium", ["medium", "wide"]) },
      { id: "portfolio.detail.overviewFundamentals", pageId: "portfolio.detail", label: "Overview fundamentals", category: "Overview", defaultEnabled: true, configurable: true, order: 30, ...panelLayout("medium", ["medium", "wide"]) },
      { id: "portfolio.detail.overviewLargestHoldings", pageId: "portfolio.detail", label: "Largest holdings", category: "Overview", defaultEnabled: true, configurable: true, order: 40, ...panelLayout("medium", ["small", "medium"]) },
      { id: "portfolio.detail.holdingGrades", pageId: "portfolio.detail", label: "Holding grade charts", category: "Holdings", defaultEnabled: true, configurable: true, order: 50, ...panelLayout("full", ["wide", "full"]) },
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
      { id: "asset.businessStrengthDrivers", pageId: "asset", label: "Business Strength drivers", category: "Business Strength", defaultEnabled: true, configurable: true, order: 40, ...panelLayout("full", ["wide", "full"]) },
      { id: "asset.businessStrengthCategoryAudit", pageId: "asset", label: "Category metric audit", category: "Business Strength", defaultEnabled: false, configurable: true, order: 50 },
      { id: "asset.businessStrengthFullAudit", pageId: "asset", label: "Full calculation audit", category: "Business Strength", defaultEnabled: false, configurable: true, order: 60, ...panelLayout("full", ["full"]) },
    ],
  },
  {
    id: "compare",
    label: "Compare",
    description: "Choose optional comparison analytics while keeping asset controls fixed.",
    features: [
      { id: "compare.assetStrip", pageId: "compare", label: "Asset summary strip", category: "Summary", defaultEnabled: true, configurable: true, order: 10, ...panelLayout("full", ["wide", "full"]) },
      { id: "compare.chartTable", pageId: "compare", label: "Accessible chart data table", category: "Chart", defaultEnabled: false, configurable: true, order: 20, ...panelLayout("full", ["full"]) },
      { id: "compare.valuation", pageId: "compare", label: "Valuation metrics", category: "Metric groups", defaultEnabled: true, configurable: true, order: 30, ...panelLayout("full", ["wide", "full"]) },
      { id: "compare.growth", pageId: "compare", label: "Growth metrics", category: "Metric groups", defaultEnabled: true, configurable: true, order: 40, ...panelLayout("full", ["wide", "full"]) },
      { id: "compare.quality", pageId: "compare", label: "Quality metrics", category: "Metric groups", defaultEnabled: true, configurable: true, order: 50, ...panelLayout("full", ["wide", "full"]) },
      { id: "compare.balanceSheet", pageId: "compare", label: "Balance sheet metrics", category: "Metric groups", defaultEnabled: true, configurable: true, order: 60, ...panelLayout("full", ["wide", "full"]) },
      { id: "compare.capitalAllocation", pageId: "compare", label: "Capital allocation metrics", category: "Metric groups", defaultEnabled: false, configurable: true, order: 70, ...panelLayout("full", ["wide", "full"]) },
      { id: "compare.forwardScenarios", pageId: "compare", label: "Forward scenarios", category: "Scenarios", defaultEnabled: false, configurable: true, order: 80, ...panelLayout("full", ["wide", "full"]) },
      { id: "compare.methodology", pageId: "compare", label: "Methodology notes", category: "Data quality", defaultEnabled: false, configurable: true, order: 90, ...panelLayout("full", ["full"]) },
    ],
  },
  {
    id: "signals",
    label: "Signals",
    description: "Choose optional signal context panels.",
    features: [
      { id: "signals.summaryStrip", pageId: "signals", label: "Summary metric strip", category: "Summary", defaultEnabled: true, configurable: true, order: 10, ...panelLayout("full", ["wide", "full"]) },
      { id: "signals.priorityPanels", pageId: "signals", label: "Priority panels", category: "Priority", defaultEnabled: true, configurable: true, order: 20, ...panelLayout("full", ["wide", "full"]) },
      { id: "signals.methodology", pageId: "signals", label: "Methodology note", category: "Data quality", defaultEnabled: false, configurable: true, order: 30, ...panelLayout("full", ["full"]) },
    ],
  },
  {
    id: "benchmarks",
    label: "Benchmarks",
    description: "Choose optional benchmark comparison and diagnostic panels.",
    features: [
      { id: "benchmarks.snapshot", pageId: "benchmarks", label: "Market snapshot cards", category: "Summary", defaultEnabled: true, configurable: true, order: 10, ...panelLayout("full", ["wide", "full"]) },
      { id: "benchmarks.comparisonChart", pageId: "benchmarks", label: "Benchmark comparison chart", category: "Chart", defaultEnabled: true, configurable: true, order: 20, ...panelLayout("full", ["wide", "full"]) },
      { id: "benchmarks.leadership", pageId: "benchmarks", label: "Leadership and risk watch", category: "Rankings", defaultEnabled: true, configurable: true, order: 30, ...panelLayout("full", ["wide", "full"]) },
      { id: "benchmarks.status", pageId: "benchmarks", label: "Freshness diagnostics", category: "Data quality", defaultEnabled: false, configurable: true, order: 40, ...panelLayout("wide", ["wide", "full"]) },
    ],
  },
  {
    id: "benchmark.detail",
    label: "Benchmark detail",
    description: "Choose optional benchmark detail panels.",
    features: [
      { id: "benchmark.detail.risk", pageId: "benchmark.detail", label: "Computed risk panel", category: "Risk", defaultEnabled: true, configurable: true, order: 10, ...panelLayout("medium", ["medium", "wide"]) },
      { id: "benchmark.detail.identity", pageId: "benchmark.detail", label: "Benchmark profile", category: "Metadata", defaultEnabled: true, configurable: true, order: 20, ...panelLayout("medium", ["medium", "wide"]) },
      { id: "benchmark.detail.quality", pageId: "benchmark.detail", label: "Freshness and disclosure", category: "Data quality", defaultEnabled: true, configurable: true, order: 30, ...panelLayout("medium", ["medium", "wide"]) },
      { id: "benchmark.detail.exposure", pageId: "benchmark.detail", label: "Exposure snapshot", category: "Composition", defaultEnabled: true, configurable: true, order: 40, ...panelLayout("medium", ["medium", "wide"]) },
      { id: "benchmark.detail.constituents", pageId: "benchmark.detail", label: "Top constituents", category: "Composition", defaultEnabled: true, configurable: true, order: 50, ...panelLayout("medium", ["medium", "wide"]) },
      { id: "benchmark.detail.actions", pageId: "benchmark.detail", label: "Manual refresh actions", category: "Operations", defaultEnabled: true, configurable: true, order: 60, ...panelLayout("full", ["wide", "full"]) },
    ],
  },
  {
    id: "brokers",
    label: "Brokers",
    description: "Choose optional broker summaries while preserving connection and import workflows.",
    features: [
      { id: "brokers.summaryCards", pageId: "brokers", label: "Broker summary cards", category: "Summary", defaultEnabled: true, configurable: true, order: 10, ...panelLayout("full", ["wide", "full"]) },
    ],
  },
  {
    id: "operations",
    label: "Operations",
    description: "Choose optional operations status cards.",
    features: [
      { id: "operations.routineWorker", pageId: "operations", label: "Routine ingestion worker", category: "Workers", defaultEnabled: true, configurable: true, order: 10, ...panelLayout("full", ["wide", "full"]) },
      { id: "operations.marketFreshness", pageId: "operations", label: "Market freshness worker", category: "Workers", defaultEnabled: true, configurable: true, order: 20, ...panelLayout("full", ["wide", "full"]) },
      { id: "operations.dataReadiness", pageId: "operations", label: "Portfolio data worker", category: "Workers", defaultEnabled: true, configurable: true, order: 30, ...panelLayout("full", ["wide", "full"]) },
      { id: "operations.projectionReadiness", pageId: "operations", label: "Projection readiness", category: "Readiness", defaultEnabled: true, configurable: true, order: 40, ...panelLayout("full", ["wide", "full"]) },
      { id: "operations.rankingReadiness", pageId: "operations", label: "Ranking readiness", category: "Readiness", defaultEnabled: true, configurable: true, order: 50, ...panelLayout("full", ["wide", "full"]) },
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

export function getLayoutWidgets(pageId: string) {
  return getConfigurableFeatures(pageId).filter((feature) => feature.movable || feature.removable || feature.resizable);
}

export function widgetDefaultSize(feature: PageFeatureDefinition): WidgetSize {
  return feature.defaultSize ?? "medium";
}

export function widgetSupportedSizes(feature: PageFeatureDefinition): WidgetSize[] {
  return feature.supportedSizes?.length ? feature.supportedSizes : [widgetDefaultSize(feature)];
}

export function widgetFootprint(feature: PageFeatureDefinition, size: WidgetSize): WidgetGridFootprint {
  return feature.footprints?.[size] ?? defaultFootprints[size] ?? defaultFootprints.medium;
}

export function getFeatureDefinition(pageId: string, featureId: string) {
  return getPageDefinition(pageId)?.features.find((feature) => feature.id === featureId) ?? null;
}

function compactLayout(items: WidgetLayoutItem[], definitions: Map<string, PageFeatureDefinition>): WidgetLayoutItem[] {
  let cursorX = 0;
  let cursorY = 0;
  let rowHeight = 1;
  return items.map((item) => {
    const definition = definitions.get(item.widgetId);
    const footprint = definition ? widgetFootprint(definition, item.size) : { columns: item.width, rows: item.height };
    const width = Math.min(DASHBOARD_GRID_COLUMNS, Math.max(1, footprint.columns));
    const height = Math.max(1, footprint.rows);
    if (cursorX + width > DASHBOARD_GRID_COLUMNS) {
      cursorX = 0;
      cursorY += rowHeight;
      rowHeight = 1;
    }
    const next = { ...item, x: cursorX, y: cursorY, width, height };
    cursorX += width;
    rowHeight = Math.max(rowHeight, height);
    return next;
  });
}

export function buildDefaultPageLayout(pageId: string): PageLayoutPreference {
  const definitions = getLayoutWidgets(pageId);
  const byId = new Map(definitions.map((feature) => [feature.id, feature]));
  const items = definitions.map((feature) => {
    const size = widgetDefaultSize(feature);
    const footprint = widgetFootprint(feature, size);
    return {
      widgetId: feature.id,
      visible: feature.defaultEnabled,
      size,
      x: 0,
      y: 0,
      width: footprint.columns,
      height: footprint.rows,
    };
  });
  return {
    pageId,
    layoutVersion: PAGE_LAYOUT_VERSION,
    items: compactLayout(items, byId),
  };
}

export function normalizePageLayout(pageId: string, rawLayout?: PageLayoutPreference | null): PageLayoutPreference {
  const definitions = getLayoutWidgets(pageId);
  const byId = new Map(definitions.map((feature) => [feature.id, feature]));
  const seen = new Set<string>();
  const rawItems = Array.isArray(rawLayout?.items) ? rawLayout.items : [];
  const normalized: WidgetLayoutItem[] = [];

  rawItems.forEach((item) => {
    const definition = byId.get(item.widgetId);
    if (!definition || seen.has(item.widgetId)) return;
    seen.add(item.widgetId);
    const supported = widgetSupportedSizes(definition);
    const size = supported.includes(item.size) ? item.size : widgetDefaultSize(definition);
    const footprint = widgetFootprint(definition, size);
    normalized.push({
      widgetId: item.widgetId,
      visible: typeof item.visible === "boolean" ? item.visible : definition.defaultEnabled,
      size,
      x: Number.isFinite(item.x) ? Math.max(0, item.x) : 0,
      y: Number.isFinite(item.y) ? Math.max(0, item.y) : 0,
      width: footprint.columns,
      height: footprint.rows,
    });
  });

  definitions.forEach((definition) => {
    if (seen.has(definition.id)) return;
    const size = widgetDefaultSize(definition);
    const footprint = widgetFootprint(definition, size);
    normalized.push({
      widgetId: definition.id,
      visible: definition.defaultEnabled,
      size,
      x: 0,
      y: 0,
      width: footprint.columns,
      height: footprint.rows,
    });
  });

  return {
    pageId,
    layoutVersion: PAGE_LAYOUT_VERSION,
    updatedAt: rawLayout?.updatedAt,
    items: compactLayout(normalized, byId),
  };
}

export function getDefaultPagePreferences(pageId: string): PageFeaturePreferences {
  return Object.fromEntries(getConfigurableFeatures(pageId).map((feature) => [feature.id, feature.defaultEnabled]));
}

export function sanitizePageFeatureStore(value: unknown): PageFeaturePreferenceStore {
  if (!value || typeof value !== "object") return { version: PAGE_FEATURE_STORAGE_VERSION, pages: {}, layouts: {} };
  const source = value as { version?: unknown; pages?: unknown };
  if (![1, PAGE_FEATURE_STORAGE_VERSION].includes(Number(source.version)) || !source.pages || typeof source.pages !== "object") {
    return { version: PAGE_FEATURE_STORAGE_VERSION, pages: {}, layouts: {} };
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
  const layouts: Record<string, PageLayoutPreference> = {};
  if (source.version === PAGE_FEATURE_STORAGE_VERSION && "layouts" in source && source.layouts && typeof source.layouts === "object") {
    Object.entries(source.layouts as Record<string, PageLayoutPreference>).forEach(([pageId, layout]) => {
      if (getPageDefinition(pageId)) layouts[pageId] = normalizePageLayout(pageId, layout);
    });
  }
  return { version: PAGE_FEATURE_STORAGE_VERSION, pages, layouts };
}

export function resolvePageFeaturePreferences(pageId: string, store: PageFeaturePreferenceStore): PageFeaturePreferences {
  return { ...getDefaultPagePreferences(pageId), ...(store.pages[pageId] ?? {}) };
}

export function isFeatureEnabled(pageId: string, featureId: string, store: PageFeaturePreferenceStore) {
  const definition = getFeatureDefinition(pageId, featureId);
  if (!definition) return true;
  if (!definition.configurable) return true;
  if (store.layouts?.[pageId]) {
    const layoutItem = normalizePageLayout(pageId, store.layouts[pageId]).items.find((item) => item.widgetId === featureId);
    if (layoutItem) return layoutItem.visible;
  }
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
      if (feature.defaultSize && !widgetSupportedSizes(feature).includes(feature.defaultSize)) errors.push(`${feature.id} default size is unsupported.`);
      widgetSupportedSizes(feature).forEach((size) => {
        const footprint = widgetFootprint(feature, size);
        if (footprint.columns < 1 || footprint.columns > DASHBOARD_GRID_COLUMNS || footprint.rows < 1) errors.push(`${feature.id} has invalid ${size} footprint.`);
      });
      if (featureIds.has(feature.id)) errors.push(`Duplicate feature id: ${feature.id}`);
      featureIds.add(feature.id);
    });
  });
  return errors;
}
