import { SlidersHorizontal } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  PAGE_FEATURE_STORAGE_KEY,
  PAGE_FEATURE_STORAGE_VERSION,
  getConfigurableFeatures,
  getFeatureDefinition,
  getPageDefinition,
  isFeatureEnabled,
  resolvePageFeaturePreferences,
  sanitizePageFeatureStore,
  type PageFeaturePreferenceStore,
} from "./pageFeatures";

type PageFeatureContextValue = {
  store: PageFeaturePreferenceStore;
  isEnabled: (pageId: string, featureId: string) => boolean;
  setFeatureEnabled: (pageId: string, featureId: string, enabled: boolean) => void;
  enableAllFeatures: (pageId: string) => void;
  disableAllFeatures: (pageId: string) => void;
  resetPageFeatures: (pageId: string) => void;
  getPageFeaturePreferences: (pageId: string) => Record<string, boolean>;
};

const defaultStore: PageFeaturePreferenceStore = { version: PAGE_FEATURE_STORAGE_VERSION, pages: {} };
const PageFeatureContext = createContext<PageFeatureContextValue | null>(null);

const defaultContext: PageFeatureContextValue = {
  store: defaultStore,
  isEnabled: (pageId, featureId) => isFeatureEnabled(pageId, featureId, defaultStore),
  setFeatureEnabled: () => undefined,
  enableAllFeatures: () => undefined,
  disableAllFeatures: () => undefined,
  resetPageFeatures: () => undefined,
  getPageFeaturePreferences: (pageId) => resolvePageFeaturePreferences(pageId, defaultStore),
};

function loadStore(): PageFeaturePreferenceStore {
  if (typeof window === "undefined") return defaultStore;
  try {
    const raw = window.localStorage.getItem(PAGE_FEATURE_STORAGE_KEY);
    if (!raw) return defaultStore;
    return sanitizePageFeatureStore(JSON.parse(raw));
  } catch {
    return defaultStore;
  }
}

function saveStore(store: PageFeaturePreferenceStore) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(PAGE_FEATURE_STORAGE_KEY, JSON.stringify(store));
  } catch {
    // Rendering must not depend on storage availability.
  }
}

function withPagePreferences(
  store: PageFeaturePreferenceStore,
  pageId: string,
  updater: (current: Record<string, boolean>) => Record<string, boolean>,
) {
  const page = getPageDefinition(pageId);
  if (!page) return store;
  const nextPage = updater(store.pages[pageId] ?? {});
  return {
    version: PAGE_FEATURE_STORAGE_VERSION,
    pages: {
      ...store.pages,
      [pageId]: nextPage,
    },
  };
}

export function PageFeatureProvider({ children }: { children: ReactNode }) {
  const [store, setStore] = useState<PageFeaturePreferenceStore>(loadStore);
  const hydrated = useRef(false);

  useEffect(() => {
    if (!hydrated.current) {
      hydrated.current = true;
      return;
    }
    saveStore(store);
  }, [store]);

  const setFeatureEnabled = useCallback((pageId: string, featureId: string, enabled: boolean) => {
    const definition = getFeatureDefinition(pageId, featureId);
    if (!definition?.configurable) return;
    setStore((current) => withPagePreferences(current, pageId, (page) => ({ ...page, [featureId]: enabled })));
  }, []);

  const enableAllFeatures = useCallback((pageId: string) => {
    setStore((current) => withPagePreferences(current, pageId, () => Object.fromEntries(getConfigurableFeatures(pageId).map((feature) => [feature.id, true]))));
  }, []);

  const disableAllFeatures = useCallback((pageId: string) => {
    setStore((current) => withPagePreferences(current, pageId, () => Object.fromEntries(getConfigurableFeatures(pageId).map((feature) => [feature.id, false]))));
  }, []);

  const resetPageFeatures = useCallback((pageId: string) => {
    setStore((current) => {
      const pages = { ...current.pages };
      delete pages[pageId];
      return { version: PAGE_FEATURE_STORAGE_VERSION, pages };
    });
  }, []);

  const value = useMemo<PageFeatureContextValue>(() => ({
    store,
    isEnabled: (pageId, featureId) => isFeatureEnabled(pageId, featureId, store),
    setFeatureEnabled,
    enableAllFeatures,
    disableAllFeatures,
    resetPageFeatures,
    getPageFeaturePreferences: (pageId) => resolvePageFeaturePreferences(pageId, store),
  }), [disableAllFeatures, enableAllFeatures, resetPageFeatures, setFeatureEnabled, store]);

  return <PageFeatureContext.Provider value={value}>{children}</PageFeatureContext.Provider>;
}

export function usePageFeatureControls(pageId: string) {
  const context = useContext(PageFeatureContext) ?? defaultContext;
  const features = getConfigurableFeatures(pageId);
  const preferences = context.getPageFeaturePreferences(pageId);
  const enabledCount = features.filter((feature) => preferences[feature.id]).length;
  return {
    page: getPageDefinition(pageId),
    features,
    preferences,
    enabledCount,
    totalCount: features.length,
    allEnabled: features.length > 0 && enabledCount === features.length,
    noneEnabled: features.length > 0 && enabledCount === 0,
    partiallyEnabled: enabledCount > 0 && enabledCount < features.length,
    isEnabled: (featureId: string) => context.isEnabled(pageId, featureId),
    setFeatureEnabled: (featureId: string, enabled: boolean) => context.setFeatureEnabled(pageId, featureId, enabled),
    enableAll: () => context.enableAllFeatures(pageId),
    disableAll: () => context.disableAllFeatures(pageId),
    reset: () => context.resetPageFeatures(pageId),
  };
}

export function usePageFeature(pageId: string, featureId: string) {
  return usePageFeatureControls(pageId).isEnabled(featureId);
}

export function FeatureGate({ pageId, featureId, children }: { pageId: string; featureId: string; children: ReactNode }) {
  return usePageFeature(pageId, featureId) ? <>{children}</> : null;
}

export function OptionalFeaturesEmpty({ pageId }: { pageId: string }) {
  const controls = usePageFeatureControls(pageId);
  if (controls.totalCount === 0 || !controls.noneEnabled) return null;
  return <div className="optional-empty" role="status">Optional widgets are hidden. Use Customize page to add them back.</div>;
}

export function PageFeatureMenu({ pageId }: { pageId: string }) {
  const controls = usePageFeatureControls(pageId);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return undefined;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        triggerRef.current?.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open]);

  useEffect(() => {
    if (!open) return undefined;
    const onPointerDown = (event: MouseEvent) => {
      if (!panelRef.current?.contains(event.target as Node) && !triggerRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [open]);

  if (!controls.page || controls.features.length === 0) return null;
  const filtered = controls.features.filter((feature) => `${feature.label} ${feature.category ?? ""} ${feature.description ?? ""}`.toLowerCase().includes(query.trim().toLowerCase()));
  const grouped = filtered.reduce<Record<string, typeof filtered>>((groups, feature) => {
    const key = feature.category ?? "Features";
    groups[key] = [...(groups[key] ?? []), feature];
    return groups;
  }, {});

  return <div className="feature-menu">
    <button
      ref={triggerRef}
      type="button"
      className="feature-menu-trigger"
      aria-haspopup="dialog"
      aria-expanded={open}
      onClick={() => setOpen((value) => !value)}
    >
      <SlidersHorizontal size={16} />Customize page
      <span>{controls.enabledCount}/{controls.totalCount}</span>
    </button>
    {open ? <div className="feature-menu-panel" ref={panelRef} role="dialog" aria-label={`${controls.page.label} optional features`}>
      <div className="feature-menu-heading">
        <div>
          <strong>{controls.page.label}</strong>
          <p>{controls.page.description ?? "Choose which optional sections appear on this page."}</p>
        </div>
        <span aria-live="polite">{controls.allEnabled ? "All enabled" : controls.noneEnabled ? "None enabled" : "Partially enabled"}</span>
      </div>
      {controls.features.length > 6 ? <label className="feature-search">Search<input value={query} onChange={(event) => setQuery(event.target.value)} /></label> : null}
      <label className="feature-master-toggle">
        <input
          type="checkbox"
          checked={controls.allEnabled}
          ref={(element) => {
            if (element) element.indeterminate = controls.partiallyEnabled;
          }}
          aria-checked={controls.partiallyEnabled ? "mixed" : controls.allEnabled}
          onChange={(event) => event.target.checked ? controls.enableAll() : controls.disableAll()}
        />
        <span>All optional widgets</span>
      </label>
      <div className="feature-menu-actions">
        <button type="button" onClick={controls.enableAll}>Enable all</button>
        <button type="button" onClick={controls.disableAll}>Disable all</button>
        <button type="button" onClick={controls.reset}>Reset to defaults</button>
      </div>
      <div className="feature-list">
        {Object.entries(grouped).map(([category, features]) => <div className="feature-group" key={category}>
          <p>{category}</p>
          {features.map((feature) => <label key={feature.id} className="feature-toggle-row">
            <input type="checkbox" checked={controls.preferences[feature.id] ?? feature.defaultEnabled} onChange={(event) => controls.setFeatureEnabled(feature.id, event.target.checked)} />
            <span><strong>{feature.label}</strong>{feature.description ? <em>{feature.description}</em> : null}</span>
          </label>)}
        </div>)}
      </div>
    </div> : null}
  </div>;
}
