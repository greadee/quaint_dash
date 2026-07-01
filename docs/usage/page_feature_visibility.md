# Page Feature Visibility And Layout

Quaint Dash uses a registry-driven page customization system for optional widgets. The same registry controls visibility, layout editing, add/remove behavior, and supported widget sizes. Major page identity, navigation, primary controls, core tables, error states, loading states, destructive/security controls, and customization controls must not be configurable or movable.

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

Layout-capable widgets add layout metadata:

```ts
{
  id: "compare.valuation",
  pageId: "compare",
  label: "Valuation metrics",
  category: "Metric groups",
  defaultEnabled: true,
  configurable: true,
  movable: true,
  removable: true,
  resizable: true,
  defaultSize: "full",
  supportedSizes: ["wide", "full"],
}
```

Only secondary and tertiary widgets should set `movable`, `removable`, or `resizable`. A tab may be visibility-configurable without being layout-capable. Repeated per-row or per-category details should normally remain visibility-only unless they are wrapped as one page-level widget.

## Layout Model

The layout model is page-scoped and versioned:

```ts
type WidgetLayoutItem = {
  widgetId: string;
  visible: boolean;
  size: WidgetSize;
  x: number;
  y: number;
  width: number;
  height: number;
};
```

`buildDefaultPageLayout(pageId)` derives official defaults from the registry. `normalizePageLayout(pageId, rawLayout)` validates and repairs stored layouts by:

- ignoring unknown widget IDs
- removing duplicate entries
- falling back to the widget default size when a saved size is unsupported
- recomputing footprint width and height from the registry
- compacting widgets into a 12-column canonical desktop grid
- appending newly introduced widgets with their default visibility

The initial implementation stores a canonical order and preset size. Tablet and mobile layouts are derived responsively by CSS: wide and full widgets span the available grid, and all layout widgets become single-column below tablet width.

## Edit Mode

Use `PageLayoutButton` in page header actions beside `PageFeatureMenu`.

```tsx
<div className="actions">
  <PageLayoutButton pageId="compare" />
  <PageFeatureMenu pageId="compare" />
</div>
<PageLayoutToolbar pageId="compare" />
```

Normal mode is protected: widgets are not draggable, drag handles are hidden, charts and tables keep their normal interactions, and widget content remains selectable. `Customize layout` enters an explicit edit mode. Edit mode shows a persistent toolbar with Add widgets, Undo, Redo, Reset layout, Cancel, and Done.

Wrap movable/removable/resizable widgets with `LayoutWidget`:

```tsx
<LayoutWidget pageId="compare" widgetId="compare.valuation">
  <ComparisonMetricSection title="Valuation" />
</LayoutWidget>
```

In edit mode, `LayoutWidget` adds a dedicated drag handle, keyboard move controls, a preset size selector when multiple sizes are supported, and Remove from page for removable widgets. The widget body is inert while editing to prevent chart drags, links, table scrolling, and text selection from conflicting with layout operations. Dragging over another widget highlights the snap target and displays the target footprint.

## Grid System

The canonical grid uses 12 logical columns with predefined sizes:

- `small`: 3 columns
- `medium`: 6 columns
- `large`: 6 columns
- `wide`: 8 columns
- `full`: 12 columns

Widgets snap by normalized order and footprint. Collision handling uses deterministic vertical compaction: widgets are walked in order, placed left to right, and wrapped to the next row when the footprint would exceed 12 columns. Widgets never overlap and hidden widgets do not mount.

Movement is intentionally constrained. The implementation supports drag-handle drop before another widget, visible drop targets, keyboard Up/Down controls, and session undo/redo. It does not expose freeform pixel placement or unrestricted resizing.

## Persistence

Preferences use local storage key `quaint_dash_page_features`.

Format:

```json
{
  "version": 2,
  "pages": {
    "compare": {
      "compare.valuation": false
    }
  },
  "layouts": {
    "compare": {
      "pageId": "compare",
      "layoutVersion": 1,
      "items": [
        {
          "widgetId": "compare.valuation",
          "visible": true,
          "size": "full",
          "x": 0,
          "y": 0,
          "width": 12,
          "height": 4
        }
      ]
    }
  }
}
```

The loader validates the version and known registry IDs. Invalid JSON, unknown pages, unknown features, malformed values, and invalid layouts are ignored or repaired per page. Version 1 visibility-only stores are migrated by keeping `pages` and deriving default layouts. New layout widgets are appended with their defaults instead of resetting existing pages.

Renamed widgets should be migrated by adding an alias step before removing the old ID. Removed widgets are safely dropped during normalization. If storage is corrupt or unavailable, the registry defaults are used.

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

Use `PageFeatureMenu` in the page header actions. Do not render it on pages with no configurable features. Use `PageLayoutButton` only on pages with layout-capable widgets.

```tsx
<div className="actions">
  <PageFeatureMenu pageId="compare" />
</div>
```

The menu supports individual toggles, enable all, disable all, reset to defaults, persisted state, partial-state checkbox display, Escape close, outside-click close, and mobile viewport constraints.

The Add widgets library in edit mode shows hidden layout-capable widgets for the current page only. Visibility-only features remain controlled by `Customize page`.

## Defaults

Defaults intentionally keep common supporting features visible and hide advanced, diagnostic, or visually heavy sections by default. Existing users can restore the fuller layout with `Enable all`.

Default layouts put high-value supporting widgets before advanced or diagnostic sections. Use larger defaults for dense charts and tables, compact defaults for metric summaries, and avoid making a widget resizable to a size it cannot render cleanly.

## Testing

Add or update:

- registry tests for unique IDs and defaults
- state tests for persistence, malformed storage, page isolation, new-feature defaults, layout normalization, size fallback, and collision compaction
- component tests for menu interactions, hidden rendering, edit mode, add/remove, resize presets, cancel, reset, and persisted Done
- page tests when a feature gate changes a route workflow or query enable condition

## Adding A Feature

1. Add a definition to `pageFeatureRegistry`.
2. Place `PageFeatureMenu` on the page if it is not already there.
3. Add layout metadata only if the feature is a true page-level widget.
4. Place `PageLayoutButton` and `PageLayoutToolbar` if the page has layout-capable widgets.
5. Wrap the optional widget in `LayoutWidget`, or conditionally render with `usePageFeature` for visibility-only sections.
6. Gate expensive queries/subscriptions when the data is used only by that widget.
7. Update registry, state, and component tests.

Never make page title, primary navigation, core selectors, destructive/security controls, primary workflow controls, or the customization menu itself configurable.

## Technology Decision

The app does not currently carry a drag-and-drop or grid dependency. The implemented approach uses browser drag events plus explicit keyboard controls and the existing React state layer. This keeps bundle size low and avoids adding a second layout state system. Collision behavior is intentionally order-based so widgets snap into the deterministic dashboard grid instead of becoming freeform windows.
