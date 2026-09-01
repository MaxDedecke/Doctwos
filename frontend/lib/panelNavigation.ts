export type PanelNavigationResolution = {
  targetIndex: number | null;
  shouldOpenNewPanel: boolean;
  ignored: boolean;
};

/**
 * Resolves where a cross-view navigation event may write its selection.
 *
 * A normal navigation may fall back to a matching frozen panel because the
 * click happened inside that panel. Call-Graph navigation opts out of that
 * fallback so a fixed code view cannot be changed by a graph click.
 */
export function resolvePanelNavigationTarget({
  targetType,
  panelConfigs,
  panelFrozen,
  openIfMissing = true,
  preserveFrozenTarget = false,
  maxPanels = 4,
}: {
  targetType: string;
  panelConfigs: string[];
  panelFrozen: boolean[];
  openIfMissing?: boolean;
  preserveFrozenTarget?: boolean;
  maxPanels?: number;
}): PanelNavigationResolution {
  const liveIndex = panelConfigs.findIndex(
    (config, index) => config === targetType && !panelFrozen[index]
  );
  if (liveIndex !== -1) {
    return { targetIndex: liveIndex, shouldOpenNewPanel: false, ignored: false };
  }

  const matchingIndex = panelConfigs.indexOf(targetType);
  if (matchingIndex !== -1 && !preserveFrozenTarget) {
    return { targetIndex: matchingIndex, shouldOpenNewPanel: false, ignored: false };
  }

  if (openIfMissing && panelConfigs.length < maxPanels) {
    return { targetIndex: null, shouldOpenNewPanel: true, ignored: false };
  }

  return { targetIndex: null, shouldOpenNewPanel: false, ignored: true };
}
