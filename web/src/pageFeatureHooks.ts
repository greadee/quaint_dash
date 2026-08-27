import { useContext } from "react";
import {
  getConfigurableFeatures,
  getLayoutWidgets,
  getPageDefinition,
  type WidgetSize,
} from "./pageFeatures";
import { defaultPageFeatureContext, PageFeatureContext } from "./pageFeatureContext";

export function usePageFeatureControls(pageId: string) {
  const context = useContext(PageFeatureContext) ?? defaultPageFeatureContext;
  const features = getConfigurableFeatures(pageId);
  const layout = context.getPageLayout(pageId);
  const layoutPreferences = Object.fromEntries(layout.items.map((item) => [item.widgetId, item.visible]));
  const preferences = Object.fromEntries(features.map((feature) => [
    feature.id,
    context.isLayoutEditing(pageId) && feature.id in layoutPreferences ? layoutPreferences[feature.id] : context.isEnabled(pageId, feature.id),
  ]));
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

export function usePageLayoutControls(pageId: string) {
  const context = useContext(PageFeatureContext) ?? defaultPageFeatureContext;
  const layout = context.getPageLayout(pageId);
  const widgets = getLayoutWidgets(pageId);
  return {
    page: getPageDefinition(pageId),
    widgets,
    layout,
    editing: context.isLayoutEditing(pageId),
    begin: () => context.beginLayoutEdit(pageId),
    done: () => context.saveLayoutEdit(pageId),
    cancel: () => context.cancelLayoutEdit(),
    reset: () => context.resetLayoutDraft(pageId),
    undo: () => context.undoLayoutEdit(pageId),
    redo: () => context.redoLayoutEdit(pageId),
    canUndo: context.canUndoLayoutEdit(pageId),
    canRedo: context.canRedoLayoutEdit(pageId),
    move: (widgetId: string, direction: -1 | 1) => context.moveWidget(pageId, widgetId, direction),
    moveBefore: (widgetId: string, beforeWidgetId: string) => context.moveWidgetBefore(pageId, widgetId, beforeWidgetId),
    remove: (widgetId: string) => context.removeWidget(pageId, widgetId),
    add: (widgetId: string) => context.addWidget(pageId, widgetId),
    resize: (widgetId: string, size: WidgetSize) => context.resizeWidget(pageId, widgetId, size),
  };
}

export function usePageFeature(pageId: string, featureId: string) {
  return usePageFeatureControls(pageId).isEnabled(featureId);
}
