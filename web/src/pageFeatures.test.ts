import { describe, expect, it } from "vitest";
import {
  PAGE_FEATURE_STORAGE_VERSION,
  buildDefaultPageLayout,
  getLayoutWidgets,
  getDefaultPagePreferences,
  isFeatureEnabled,
  normalizePageLayout,
  pageFeatureRegistry,
  resolvePageFeaturePreferences,
  sanitizePageFeatureStore,
  validatePageFeatureRegistry,
  type PageFeaturePreferenceStore,
} from "./pageFeatures";

describe("page feature registry", () => {
  it("has valid unique page and feature identifiers", () => {
    expect(validatePageFeatureRegistry()).toEqual([]);
  });

  it("keeps every configurable feature labeled with a deliberate default", () => {
    for (const page of pageFeatureRegistry) {
      for (const feature of page.features.filter((item) => item.configurable)) {
        expect(feature.label.trim()).not.toEqual("");
        expect(typeof feature.defaultEnabled).toBe("boolean");
      }
    }
  });

  it("does not register fixed primary navigation or page titles as optional features", () => {
    const ids = pageFeatureRegistry.flatMap((page) => page.features.map((feature) => feature.id));
    expect(ids).not.toContain("app.navigation");
    expect(ids).not.toContain("page.title");
    expect(ids).not.toContain("compare.controls");
    expect(ids).not.toContain("portfolio.detail.holdingsTable");
  });

  it("defines valid default layouts for layout-capable widgets", () => {
    for (const page of pageFeatureRegistry) {
      const widgets = getLayoutWidgets(page.id);
      const layout = buildDefaultPageLayout(page.id);
      expect(layout.items.map((item) => item.widgetId)).toEqual(widgets.map((widget) => widget.id));
      for (const item of layout.items) {
        expect(item.x).toBeGreaterThanOrEqual(0);
        expect(item.y).toBeGreaterThanOrEqual(0);
        expect(item.width).toBeGreaterThan(0);
        expect(item.height).toBeGreaterThan(0);
      }
    }
  });
});

describe("page feature preference resolution", () => {
  it("uses registry defaults when no preference exists", () => {
    const store: PageFeaturePreferenceStore = { version: PAGE_FEATURE_STORAGE_VERSION, pages: {} };
    expect(isFeatureEnabled("compare", "compare.valuation", store)).toBe(true);
    expect(isFeatureEnabled("compare", "compare.forwardScenarios", store)).toBe(false);
  });

  it("lets pages override features independently", () => {
    const store: PageFeaturePreferenceStore = {
      version: PAGE_FEATURE_STORAGE_VERSION,
      pages: {
        compare: { "compare.valuation": false },
        overview: { "overview.marketNews": false },
      },
    };
    expect(isFeatureEnabled("compare", "compare.valuation", store)).toBe(false);
    expect(isFeatureEnabled("overview", "overview.marketNews", store)).toBe(false);
    expect(isFeatureEnabled("portfolio.detail", "portfolio.detail.overviewRisk", store)).toBe(true);
  });

  it("ignores unknown pages, unknown feature ids, malformed values, and old versions", () => {
    const sanitized = sanitizePageFeatureStore({
      version: PAGE_FEATURE_STORAGE_VERSION,
      pages: {
        compare: { "compare.valuation": false, "compare.unknown": false, "compare.growth": "no" },
        unknown: { "unknown.feature": false },
      },
    });
    expect(sanitized.pages).toEqual({ compare: { "compare.valuation": false } });
    expect(sanitizePageFeatureStore({ version: 0, pages: { compare: { "compare.valuation": false } } })).toEqual({
      version: PAGE_FEATURE_STORAGE_VERSION,
      pages: {},
      layouts: {},
    });
  });

  it("keeps newly introduced features on defaults while preserving saved preferences", () => {
    const store: PageFeaturePreferenceStore = {
      version: PAGE_FEATURE_STORAGE_VERSION,
      pages: { compare: { "compare.valuation": false } },
    };
    const preferences = resolvePageFeaturePreferences("compare", store);
    expect(preferences["compare.valuation"]).toBe(false);
    expect(preferences["compare.growth"]).toBe(getDefaultPagePreferences("compare")["compare.growth"]);
  });

  it("normalizes invalid saved layouts without losing new widget defaults", () => {
    const layout = normalizePageLayout("compare", {
      pageId: "compare",
      layoutVersion: 99,
      items: [
        { widgetId: "compare.valuation", visible: false, size: "small", x: -10, y: -1, width: 99, height: 99 },
        { widgetId: "compare.valuation", visible: true, size: "full", x: 1, y: 1, width: 12, height: 4 },
        { widgetId: "compare.unknown", visible: true, size: "full", x: 0, y: 0, width: 12, height: 4 },
      ],
    });

    expect(layout.layoutVersion).toBe(1);
    expect(layout.items.filter((item) => item.widgetId === "compare.valuation")).toHaveLength(1);
    expect(layout.items.find((item) => item.widgetId === "compare.valuation")?.visible).toBe(false);
    expect(layout.items.find((item) => item.widgetId === "compare.valuation")?.size).toBe("full");
    expect(layout.items.some((item) => item.widgetId === "compare.growth")).toBe(true);
  });

  it("sanitizes versioned persisted layouts independently by page", () => {
    const sanitized = sanitizePageFeatureStore({
      version: PAGE_FEATURE_STORAGE_VERSION,
      pages: { compare: { "compare.valuation": false } },
      layouts: {
        compare: {
          pageId: "compare",
          layoutVersion: 1,
          items: [{ widgetId: "compare.valuation", visible: false, size: "full", x: 0, y: 0, width: 12, height: 4 }],
        },
        unknown: {
          pageId: "unknown",
          layoutVersion: 1,
          items: [],
        },
      },
    });

    expect(sanitized.layouts?.compare.items.find((item) => item.widgetId === "compare.valuation")?.visible).toBe(false);
    expect(sanitized.layouts?.unknown).toBeUndefined();
  });
});
