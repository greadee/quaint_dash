# Shared UI integration

The web application consumes version `0.1.0` of the canonical `@prool-ui/*` packages. Until a registry exists, npm `file:` dependencies point at the sibling `shared-ui` repository. The shared repository must be built first. `install-links=true` makes npm install the packed package shape instead of symlinking a second React runtime.

## Ownership

The shared repository owns design tokens, themes, generic React rendering, accessibility, tests, and component documentation. Quaint Dash owns API/query state, routing, finance DTOs and calculations, chart rendering, and the application theme adapter in `web/src/sharedUi.css`.

`RangeSelector` now adapts app-owned values to canonical `SegmentedControl`. `ChartFrame` keeps dashboard-specific eyebrow/tools/detail composition while delegating the semantic frame to the canonical component.

## Upgrade

1. Build and validate the target shared UI version.
2. Update the three exact dependency versions or temporary `file:` paths together.
3. Run `npm test`, `npm run lint`, and `npm run build`.
4. Verify `/api/v1/health`, refresh the Vite app, inspect console state, and review visual diffs.
5. Commit the app dependency update separately.

## Rollback and promotion

Restore the previous exact versions and lockfile, then rerun the compatibility checks. Revert the isolated migration commit if necessary. Never edit installed package files.

Generalizable app changes are proposed upstream with provenance, API/token/consumer impact, tests, and release type. Temporary app overrides are removed only after a new shared release is adopted.
