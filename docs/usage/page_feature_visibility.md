# Page Feature Visibility

Quaint Dash uses a registry-driven page visibility system for optional widgets. Major page identity, navigation, primary controls, core tables, error states, loading states, and the `Customize page` control must not be configurable.

## Registry

Definitions live in `web/src/pageFeatures.ts`.

Feature IDs are stable strings with the naming convention:

```text
page.section
page.group.section
```

Examples:

```ts
{
  id: "portfolio.detail.holdingGrades",
  pageId: "portfolio.detail",
  label: "Holding grade charts",
  category: "Holdings",
  defaultEnabled: false,
  configurable: true,
}
```

The page registry exports `ConfigurablePageDefinition` entries. Each configurable feature has a label, boolean default, stable ID, page ID, and optional category/order.

## Persistence

Preferences use local storage key `quaint_dash_page_features`.

Format:

```json
{
  "version": 1,
  "pages": {
    "compare": {
      "compare.valuation": false
    }
  }
}
```

The loader validates the version and known registry IDs. Invalid JSON, unknown pages, unknown features, and malformed values are ignored. New features fall back to registry defaults without resetting existing user choices. Renamed features should be handled by a future versioned migration before changing the storage version.

## Rendering

Wrap optional sections with `FeatureGate` or read `usePageFeature(pageId, featureId)`.

```tsx
<FeatureGate pageId="compare" featureId="compare.forwardScenarios">
  <ComparisonForwardScenarios />
</FeatureGate>
```

For hidden expensive widgets, also gate the related query with the same visibility flag:

```tsx
const showConstituents = usePageFeature("benchmark.detail", "benchmark.detail.constituents");
const constituents = useQuery({
  queryKey: ["benchmark-detail-constituents", id],
  queryFn: () => api.benchmarkConstituents(id),
  enabled: Boolean(id) && showConstituents,
});
```

## Menu

Use `PageFeatureMenu` in the page header actions. Do not render it on pages with no configurable features.

```tsx
<div className="actions">
  <PageFeatureMenu pageId="compare" />
</div>
```

The menu supports individual toggles, enable all, disable all, reset to defaults, persisted state, partial-state checkbox display, Escape close, outside-click close, and mobile viewport constraints.

## Defaults

Defaults intentionally keep common supporting features visible and hide advanced, diagnostic, or visually heavy sections by default. Existing users can restore the fuller layout with `Enable all`.

## Testing

Add or update:

- registry tests for unique IDs and defaults
- state tests for persistence, malformed storage, page isolation, and new-feature defaults
- component tests for menu interactions and hidden rendering
- page tests when a feature gate changes a route workflow or query enable condition

## Adding A Feature

1. Add a definition to `pageFeatureRegistry`.
2. Place `PageFeatureMenu` on the page if it is not already there.
3. Wrap the optional widget or conditionally render with `usePageFeature`.
4. Gate expensive queries/subscriptions when the data is used only by that widget.
5. Update tests.

Never make page title, primary navigation, core selectors, destructive/security controls, primary workflow controls, or the customization menu itself configurable.
