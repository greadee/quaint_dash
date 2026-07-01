import { describe, expect, it } from "vitest";
import {
  PAGE_FEATURE_STORAGE_VERSION,
  getDefaultPagePreferences,
  isFeatureEnabled,
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
});
