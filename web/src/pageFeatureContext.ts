import { createContext } from "react";
import {
  PAGE_FEATURE_STORAGE_VERSION,
  isFeatureEnabled,
  normalizePageLayout,
  resolvePageFeaturePreferences,
  type PageFeaturePreferenceStore,
  type PageLayoutPreference,
  type WidgetSize,
} from "./pageFeatures";

export type PageFeatureContextValue = {
  store: PageFeaturePreferenceStore;
  isEnabled: (pageId: string, featureId: string) => boolean;
  setFeatureEnabled: (pageId: string, featureId: string, enabled: boolean) => void;
  enableAllFeatures: (pageId: string) => void;
  disableAllFeatures: (pageId: string) => void;
  resetPageFeatures: (pageId: string) => void;
  getPageFeaturePreferences: (pageId: string) => Record<string, boolean>;
  editPageId: string | null;
  beginLayoutEdit: (pageId: string) => void;
  saveLayoutEdit: (pageId: string) => void;
  cancelLayoutEdit: () => void;
  resetLayoutDraft: (pageId: string) => void;
  undoLayoutEdit: (pageId: string) => void;
  redoLayoutEdit: (pageId: string) => void;
  moveWidget: (pageId: string, widgetId: string, direction: -1 | 1) => void;
  moveWidgetBefore: (pageId: string, widgetId: string, beforeWidgetId: string) => void;
  removeWidget: (pageId: string, widgetId: string) => void;
  addWidget: (pageId: string, widgetId: string) => void;
  resizeWidget: (pageId: string, widgetId: string, size: WidgetSize) => void;
  getPageLayout: (pageId: string) => PageLayoutPreference;
  isLayoutEditing: (pageId: string) => boolean;
  canUndoLayoutEdit: (pageId: string) => boolean;
  canRedoLayoutEdit: (pageId: string) => boolean;
};

const defaultStore: PageFeaturePreferenceStore = {
  version: PAGE_FEATURE_STORAGE_VERSION,
  pages: {},
  layouts: {},
};

export const PageFeatureContext = createContext<PageFeatureContextValue | null>(null);

export const defaultPageFeatureContext: PageFeatureContextValue = {
  store: defaultStore,
  isEnabled: (pageId, featureId) => isFeatureEnabled(pageId, featureId, defaultStore),
  setFeatureEnabled: () => undefined,
  enableAllFeatures: () => undefined,
  disableAllFeatures: () => undefined,
  resetPageFeatures: () => undefined,
  getPageFeaturePreferences: (pageId) => resolvePageFeaturePreferences(pageId, defaultStore),
  editPageId: null,
  beginLayoutEdit: () => undefined,
  saveLayoutEdit: () => undefined,
  cancelLayoutEdit: () => undefined,
  resetLayoutDraft: () => undefined,
  undoLayoutEdit: () => undefined,
  redoLayoutEdit: () => undefined,
  moveWidget: () => undefined,
  moveWidgetBefore: () => undefined,
  removeWidget: () => undefined,
  addWidget: () => undefined,
  resizeWidget: () => undefined,
  getPageLayout: (pageId) => normalizePageLayout(pageId),
  isLayoutEditing: () => false,
  canUndoLayoutEdit: () => false,
  canRedoLayoutEdit: () => false,
};
