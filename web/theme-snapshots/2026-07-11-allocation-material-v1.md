# Allocation Material Rollback Snapshot

Saved before the matte/sharp-corner adjustment on 2026-07-11.

Rollback target files:

- `web/src/routes/portfolioRoute.tsx`
- `web/src/styles.css`

Snapshot intent:

- Premium metallic allocation pie with visible highlight sweep
- Rounded pie slice corners
- Light slice edge stroke
- Brighter legend swatch sheen

Snapshot identifiers:

- `piePalette` in `portfolioRoute.tsx`
- `AllocationPie()` SVG defs and `Pie` props in `portfolioRoute.tsx`
- `.allocation-pie-chart`
- `.allocation-swatch`
- `.allocation-center-value`
- `.allocation-center-label`

If we need to restore this exact look, use this snapshot as the reference version before the matte reduction pass.
