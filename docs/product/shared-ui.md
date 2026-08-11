# Shared UI integration

The web application consumes version `0.1.0` of the canonical `@prool-ui/*` packages from immutable release tarballs committed under `web/vendor/prool-ui`. Installation and builds do not read the shared UI working repository, so later upstream changes cannot alter this application.

## Ownership

The shared repository owns design tokens, themes, generic React rendering, accessibility, tests, and component documentation. Quaint Dash owns API/query state, routing, finance DTOs and calculations, chart rendering, and the application theme adapter in `web/src/sharedUi.css`.

`RangeSelector` now adapts app-owned values to canonical `SegmentedControl`. `ChartFrame` keeps dashboard-specific eyebrow/tools/detail composition while delegating the semantic frame to the canonical component.

## Upgrade

1. Build and validate the target shared UI version.
2. Pack the three packages and copy the versioned tarballs into `web/vendor/prool-ui`.
3. Update all three exact tarball paths together and regenerate `package-lock.json`.
4. Run `npm ci`, `npm test`, `npm run lint`, and `npm run build`.
5. Verify `/api/v1/health`, refresh the Vite app, inspect console state, and review visual diffs.
6. Commit the app dependency update separately.

## Rollback and promotion

Restore the previous exact versions and lockfile, then rerun the compatibility checks. Revert the isolated migration commit if necessary. Never edit installed package files.

Generalizable app changes are proposed upstream with provenance, API/token/consumer impact, tests, and release type. Temporary app overrides are removed only after a new shared release is adopted.
