import type { AppSettings, MoverDefault } from "./routeTypes";

export function SettingsPage({ settings, onChange }: { settings: AppSettings; onChange: (next: Partial<AppSettings>) => void }) {
  return <div className="page">
    <div className="page-title">
      <div><p className="eyebrow">Workspace preferences</p><h1>Settings</h1><p className="page-subtitle">Control visual tone, default list behavior, and compactness for repeated dashboard work.</p></div>
    </div>
    <section className="settings-grid">
      <article className="card settings-card">
        <div><p className="eyebrow">Appearance</p><h2>Theme</h2></div>
        <div className="segmented-control" role="group" aria-label="Theme">
          <button className={settings.theme === "light" ? "selected" : ""} onClick={() => onChange({ theme: "light" })}>Light</button>
          <button className={settings.theme === "dark" ? "selected" : ""} onClick={() => onChange({ theme: "dark" })}>Dark</button>
        </div>
        <p>The dark theme uses a charcoal-black dashboard shell with saturated allocation accents. The light theme keeps the same layout and materials on an off-white surface.</p>
      </article>
      <article className="card settings-card">
        <div><p className="eyebrow">Overview</p><h2>Movers list</h2></div>
        <label className="setting-row"><span>Default holdings shown</span><select value={settings.moverDefault} onChange={(event) => onChange({ moverDefault: event.target.value as MoverDefault })}><option value="8">8 holdings</option><option value="all">All holdings</option></select></label>
        <p>The Overview page always allows switching between the compact eight-row view and the full mover list.</p>
      </article>
      <article className="card settings-card">
        <div><p className="eyebrow">Data surfaces</p><h2>Density</h2></div>
        <div className="segmented-control" role="group" aria-label="Density">
          <button className={settings.density === "comfortable" ? "selected" : ""} onClick={() => onChange({ density: "comfortable" })}>Comfortable</button>
          <button className={settings.density === "compact" ? "selected" : ""} onClick={() => onChange({ density: "compact" })}>Compact</button>
        </div>
        <p>Compact mode trims repeated table and card spacing without changing the information shown.</p>
      </article>
      <article className="card settings-card">
        <div><p className="eyebrow">Feature color</p><h2>Accents</h2></div>
        <label className="toggle-row"><input type="checkbox" checked={settings.featureColor} onChange={(event) => onChange({ featureColor: event.target.checked })} /><span>Use color for feature icons and semantic states</span></label>
        <p>Leave this on to keep the allocation-material accent system visible across charts, summaries, and action states.</p>
      </article>
    </section>
  </div>;
}
