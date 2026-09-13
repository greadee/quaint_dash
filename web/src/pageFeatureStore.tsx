import { Check, GripVertical, Plus, Redo2, RotateCcw, SlidersHorizontal, Undo2, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  PAGE_FEATURE_STORAGE_KEY,
  PAGE_FEATURE_STORAGE_VERSION,
  getConfigurableFeatures,
  getFeatureDefinition,
  getPageDefinition,
  isFeatureEnabled,
  normalizePageLayout,
  resolvePageFeaturePreferences,
  sanitizePageFeatureStore,
  widgetSupportedSizes,
  type PageLayoutPreference,
  type PageFeaturePreferenceStore,
  type WidgetSize,
} from "./pageFeatures";
import { PageFeatureContext, type PageFeatureContextValue } from "./pageFeatureContext";
import { usePageFeature, usePageFeatureControls, usePageLayoutControls } from "./pageFeatureHooks";

const defaultStore: PageFeaturePreferenceStore = { version: PAGE_FEATURE_STORAGE_VERSION, pages: {}, layouts: {} };
type LayoutHistory = Record<string, { past: PageLayoutPreference[]; future: PageLayoutPreference[] }>;
const MAX_LAYOUT_HISTORY = 30;

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
    layouts: store.layouts ?? {},
  };
}

export function PageFeatureProvider({ children }: { children: ReactNode }) {
  const [store, setStore] = useState<PageFeaturePreferenceStore>(loadStore);
  const [editPageId, setEditPageId] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, PageLayoutPreference>>({});
  const [history, setHistory] = useState<LayoutHistory>({});
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
    setStore((current) => {
      const layout = normalizePageLayout(pageId, current.layouts?.[pageId]);
      const layouts = {
        ...(current.layouts ?? {}),
        [pageId]: { ...layout, items: layout.items.map((item) => item.widgetId === featureId ? { ...item, visible: enabled } : item), updatedAt: new Date().toISOString() },
      };
      return { ...withPagePreferences(current, pageId, (page) => ({ ...page, [featureId]: enabled })), layouts };
    });
  }, []);

  const enableAllFeatures = useCallback((pageId: string) => {
    setStore((current) => {
      const layout = normalizePageLayout(pageId, current.layouts?.[pageId]);
      const layouts = { ...(current.layouts ?? {}), [pageId]: { ...layout, items: layout.items.map((item) => ({ ...item, visible: true })), updatedAt: new Date().toISOString() } };
      return { ...withPagePreferences(current, pageId, () => Object.fromEntries(getConfigurableFeatures(pageId).map((feature) => [feature.id, true]))), layouts };
    });
  }, []);

  const disableAllFeatures = useCallback((pageId: string) => {
    setStore((current) => {
      const layout = normalizePageLayout(pageId, current.layouts?.[pageId]);
      const layouts = { ...(current.layouts ?? {}), [pageId]: { ...layout, items: layout.items.map((item) => ({ ...item, visible: false })), updatedAt: new Date().toISOString() } };
      return { ...withPagePreferences(current, pageId, () => Object.fromEntries(getConfigurableFeatures(pageId).map((feature) => [feature.id, false]))), layouts };
    });
  }, []);

  const resetPageFeatures = useCallback((pageId: string) => {
    setStore((current) => {
      const pages = { ...current.pages };
      delete pages[pageId];
      const layouts = { ...(current.layouts ?? {}) };
      delete layouts[pageId];
      return { version: PAGE_FEATURE_STORAGE_VERSION, pages, layouts };
    });
  }, []);

  const updateDraft = useCallback((pageId: string, updater: (layout: PageLayoutPreference) => PageLayoutPreference) => {
    setDrafts((current) => {
      const previous = normalizePageLayout(pageId, current[pageId] ?? normalizePageLayout(pageId, store.layouts?.[pageId]));
      const next = normalizePageLayout(pageId, updater(previous));
      if (JSON.stringify(previous.items) === JSON.stringify(next.items)) return current;
      setHistory((currentHistory) => {
        const pageHistory = currentHistory[pageId] ?? { past: [], future: [] };
        return {
          ...currentHistory,
          [pageId]: {
            past: [...pageHistory.past, previous].slice(-MAX_LAYOUT_HISTORY),
            future: [],
          },
        };
      });
      return { ...current, [pageId]: next };
    });
  }, [store.layouts]);

  const beginLayoutEdit = useCallback((pageId: string) => {
    setDrafts((current) => ({ ...current, [pageId]: normalizePageLayout(pageId, store.layouts?.[pageId]) }));
    setHistory((current) => ({ ...current, [pageId]: { past: [], future: [] } }));
    setEditPageId(pageId);
  }, [store.layouts]);

  const saveLayoutEdit = useCallback((pageId: string) => {
    const draft = normalizePageLayout(pageId, drafts[pageId]);
    setStore((current) => {
      const pages = { ...current.pages, [pageId]: Object.fromEntries(draft.items.map((item) => [item.widgetId, item.visible])) };
      return {
        version: PAGE_FEATURE_STORAGE_VERSION,
        pages,
        layouts: { ...(current.layouts ?? {}), [pageId]: { ...draft, updatedAt: new Date().toISOString() } },
      };
    });
    setEditPageId(null);
    setHistory((current) => {
      const next = { ...current };
      delete next[pageId];
      return next;
    });
  }, [drafts]);

  const cancelLayoutEdit = useCallback(() => {
    setHistory((current) => {
      if (!editPageId) return current;
      const next = { ...current };
      delete next[editPageId];
      return next;
    });
    setEditPageId(null);
  }, [editPageId]);

  const resetLayoutDraft = useCallback((pageId: string) => {
    updateDraft(pageId, () => normalizePageLayout(pageId, null));
  }, [updateDraft]);

  const undoLayoutEdit = useCallback((pageId: string) => {
    setHistory((currentHistory) => {
      const pageHistory = currentHistory[pageId];
      if (!pageHistory?.past.length) return currentHistory;
      const previous = pageHistory.past[pageHistory.past.length - 1];
      setDrafts((currentDrafts) => ({
        ...currentDrafts,
        [pageId]: previous,
      }));
      return {
        ...currentHistory,
        [pageId]: {
          past: pageHistory.past.slice(0, -1),
          future: [normalizePageLayout(pageId, drafts[pageId] ?? store.layouts?.[pageId]), ...pageHistory.future].slice(0, MAX_LAYOUT_HISTORY),
        },
      };
    });
  }, [drafts, store.layouts]);

  const redoLayoutEdit = useCallback((pageId: string) => {
    setHistory((currentHistory) => {
      const pageHistory = currentHistory[pageId];
      if (!pageHistory?.future.length) return currentHistory;
      const next = pageHistory.future[0];
      setDrafts((currentDrafts) => ({
        ...currentDrafts,
        [pageId]: next,
      }));
      return {
        ...currentHistory,
        [pageId]: {
          past: [...pageHistory.past, normalizePageLayout(pageId, drafts[pageId] ?? store.layouts?.[pageId])].slice(-MAX_LAYOUT_HISTORY),
          future: pageHistory.future.slice(1),
        },
      };
    });
  }, [drafts, store.layouts]);

  const moveWidgetBefore = useCallback((pageId: string, widgetId: string, beforeWidgetId: string) => {
    updateDraft(pageId, (layout) => {
      const moving = layout.items.find((item) => item.widgetId === widgetId);
      if (!moving || widgetId === beforeWidgetId) return layout;
      const rest = layout.items.filter((item) => item.widgetId !== widgetId);
      const index = Math.max(0, rest.findIndex((item) => item.widgetId === beforeWidgetId));
      return { ...layout, items: [...rest.slice(0, index), moving, ...rest.slice(index)] };
    });
  }, [updateDraft]);

  const moveWidget = useCallback((pageId: string, widgetId: string, direction: -1 | 1) => {
    updateDraft(pageId, (layout) => {
      const index = layout.items.findIndex((item) => item.widgetId === widgetId);
      const nextIndex = index + direction;
      if (index < 0 || nextIndex < 0 || nextIndex >= layout.items.length) return layout;
      const items = [...layout.items];
      [items[index], items[nextIndex]] = [items[nextIndex], items[index]];
      return { ...layout, items };
    });
  }, [updateDraft]);

  const removeWidget = useCallback((pageId: string, widgetId: string) => {
    updateDraft(pageId, (layout) => ({ ...layout, items: layout.items.map((item) => item.widgetId === widgetId ? { ...item, visible: false } : item) }));
  }, [updateDraft]);

  const addWidget = useCallback((pageId: string, widgetId: string) => {
    updateDraft(pageId, (layout) => ({ ...layout, items: layout.items.map((item) => item.widgetId === widgetId ? { ...item, visible: true } : item) }));
  }, [updateDraft]);

  const resizeWidget = useCallback((pageId: string, widgetId: string, size: WidgetSize) => {
    const definition = getFeatureDefinition(pageId, widgetId);
    if (!definition || !widgetSupportedSizes(definition).includes(size)) return;
    updateDraft(pageId, (layout) => ({ ...layout, items: layout.items.map((item) => item.widgetId === widgetId ? { ...item, size } : item) }));
  }, [updateDraft]);

  const getPageLayout = useCallback((pageId: string) => editPageId === pageId ? normalizePageLayout(pageId, drafts[pageId]) : normalizePageLayout(pageId, store.layouts?.[pageId]), [drafts, editPageId, store.layouts]);

  const value = useMemo<PageFeatureContextValue>(() => ({
    store,
    isEnabled: (pageId, featureId) => isFeatureEnabled(pageId, featureId, store),
    setFeatureEnabled,
    enableAllFeatures,
    disableAllFeatures,
    resetPageFeatures,
    getPageFeaturePreferences: (pageId) => resolvePageFeaturePreferences(pageId, store),
    editPageId,
    beginLayoutEdit,
    saveLayoutEdit,
    cancelLayoutEdit,
    resetLayoutDraft,
    undoLayoutEdit,
    redoLayoutEdit,
    moveWidget,
    moveWidgetBefore,
    removeWidget,
    addWidget,
    resizeWidget,
    getPageLayout,
    isLayoutEditing: (pageId) => editPageId === pageId,
    canUndoLayoutEdit: (pageId) => Boolean(history[pageId]?.past.length),
    canRedoLayoutEdit: (pageId) => Boolean(history[pageId]?.future.length),
  }), [addWidget, beginLayoutEdit, cancelLayoutEdit, disableAllFeatures, editPageId, enableAllFeatures, getPageLayout, history, moveWidget, moveWidgetBefore, redoLayoutEdit, removeWidget, resetLayoutDraft, resetPageFeatures, resizeWidget, saveLayoutEdit, setFeatureEnabled, store, undoLayoutEdit]);

  return <PageFeatureContext.Provider value={value}>{children}</PageFeatureContext.Provider>;
}

export function FeatureGate({ pageId, featureId, children }: { pageId: string; featureId: string; children: ReactNode }) {
  return usePageFeature(pageId, featureId) ? <>{children}</> : null;
}

export function OptionalFeaturesEmpty({ pageId }: { pageId: string }) {
  const controls = usePageFeatureControls(pageId);
  if (controls.totalCount === 0 || !controls.noneEnabled) return null;
  return <div className="optional-empty" role="status">Optional widgets are hidden. Use Customize page to add them back.</div>;
}

export function PageLayoutButton({ pageId }: { pageId: string }) {
  const controls = usePageLayoutControls(pageId);
  if (!controls.widgets.length) return null;
  if (controls.editing) return null;
  return <button type="button" className="layout-edit-trigger" onClick={controls.begin}><GripVertical size={16} />Customize layout</button>;
}

export function PageLayoutToolbar({ pageId }: { pageId: string }) {
  const controls = usePageLayoutControls(pageId);
  const [libraryOpen, setLibraryOpen] = useState(false);
  if (!controls.editing) return null;
  const visibleIds = new Set(controls.layout.items.filter((item) => item.visible).map((item) => item.widgetId));
  const hidden = controls.widgets.filter((widget) => !visibleIds.has(widget.id));
  return <div className="layout-toolbar" role="region" aria-label={`${controls.page?.label ?? pageId} layout editor`}>
    <strong>Layout editing</strong>
    <span>{controls.layout.items.filter((item) => item.visible).length}/{controls.widgets.length} widgets visible</span>
    <button type="button" onClick={() => setLibraryOpen((value) => !value)}><Plus size={15} />Add widgets</button>
    <button type="button" onClick={controls.undo} disabled={!controls.canUndo}><Undo2 size={15} />Undo</button>
    <button type="button" onClick={controls.redo} disabled={!controls.canRedo}><Redo2 size={15} />Redo</button>
    <button type="button" onClick={controls.reset}><RotateCcw size={15} />Reset layout</button>
    <button type="button" onClick={controls.cancel}><X size={15} />Cancel</button>
    <button type="button" className="primary" onClick={controls.done}><Check size={15} />Done</button>
    {libraryOpen ? <div className="widget-library" role="dialog" aria-label="Add widgets">
      <div className="feature-menu-heading"><div><strong>Add widgets</strong><p>Removed widgets stay available here for this page.</p></div></div>
      {hidden.length ? hidden.map((widget) => <button type="button" key={widget.id} onClick={() => controls.add(widget.id)}><span><strong>{widget.label}</strong><em>{widget.category ?? "Widget"}</em></span><Plus size={15} /></button>) : <p className="muted-copy">Every optional widget is already on the page.</p>}
    </div> : null}
  </div>;
}

export function LayoutWidget({ pageId, widgetId, children }: { pageId: string; widgetId: string; children: ReactNode }) {
  const controls = usePageLayoutControls(pageId);
  const definition = getFeatureDefinition(pageId, widgetId);
  const item = controls.layout.items.find((candidate) => candidate.widgetId === widgetId);
  const visible = item?.visible ?? definition?.defaultEnabled ?? true;
  const [dropTarget, setDropTarget] = useState(false);
  if (!definition || !visible) return null;
  const supportedSizes = widgetSupportedSizes(definition);
  const editing = controls.editing;
  const style = item ? {
    order: item.y * 100 + item.x,
  } : undefined;
  return <div
    className={`layout-widget ${editing ? "editing" : ""} ${dropTarget ? "drop-target" : ""} size-${item?.size ?? "medium"}`}
    style={style}
    data-widget-id={widgetId}
    data-drop-label={`Drop before ${definition.label}`}
    data-footprint={item ? `${item.width} x ${item.height}` : undefined}
    aria-roledescription={editing ? "draggable dashboard widget" : undefined}
    onDragOver={(event) => {
      if (editing) event.preventDefault();
    }}
    onDragEnter={(event) => {
      if (!editing) return;
      const source = event.dataTransfer.getData("text/plain");
      if (source !== widgetId) setDropTarget(true);
    }}
    onDragLeave={(event) => {
      if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDropTarget(false);
    }}
    onDrop={(event) => {
      const source = event.dataTransfer.getData("text/plain");
      setDropTarget(false);
      if (source && source !== widgetId) controls.moveBefore(source, widgetId);
    }}
  >
    {editing ? <div className="layout-widget-controls">
      <button
        type="button"
        className="drag-handle"
        draggable
        aria-label={`Move ${definition.label}`}
        onDragStart={(event) => {
          event.dataTransfer.setData("text/plain", widgetId);
          event.dataTransfer.effectAllowed = "move";
        }}
        onKeyDown={(event) => {
          if (event.key === "ArrowUp" || event.key === "ArrowLeft") {
            event.preventDefault();
            controls.move(widgetId, -1);
          }
          if (event.key === "ArrowDown" || event.key === "ArrowRight") {
            event.preventDefault();
            controls.move(widgetId, 1);
          }
        }}
      ><GripVertical size={16} /></button>
      <span>{definition.label}</span>
      <button type="button" aria-label={`Move ${definition.label} earlier`} onClick={() => controls.move(widgetId, -1)}>Up</button>
      <button type="button" aria-label={`Move ${definition.label} later`} onClick={() => controls.move(widgetId, 1)}>Down</button>
      {definition.resizable && supportedSizes.length > 1 ? <label>Size<select value={item?.size ?? definition.defaultSize ?? supportedSizes[0]} onChange={(event) => controls.resize(widgetId, event.target.value as WidgetSize)}>{supportedSizes.map((size) => <option key={size} value={size}>{size}</option>)}</select></label> : null}
      {definition.removable ? <button type="button" aria-label={`Remove ${definition.label} from page`} onClick={() => controls.remove(widgetId)}><X size={14} />Remove</button> : null}
    </div> : null}
    <div className={editing ? "layout-widget-content inert" : "layout-widget-content"}>{children}</div>
  </div>;
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
