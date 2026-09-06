export type PanelNavigationIgnoreReason = 'no-space' | 'no-matching-panel';

export type PanelNavigationResolution = {
  targetIndex: number | null;
  shouldOpenNewPanel: boolean;
  ignored: boolean;
  /**
   * Why nothing happened. 'no-space' means the four-panel cap blocked a panel
   * the caller wanted to open -- that one deserves user feedback (D-2).
   * 'no-matching-panel' is the deliberate "only nudge an existing view" case
   * (openIfMissing=false) and stays silent.
   */
  ignoreReason: PanelNavigationIgnoreReason | null;
};

/**
 * Resolves where a cross-view navigation event may write its selection.
 *
 * A frozen panel is never a target: freezing protects a panel from every
 * navigation except a click inside that panel itself (decision D-1 in
 * docs/PANEL_SYNCHRONISATION.md). Callers that clicked inside the panel never
 * reach this function -- their target type equals their own panel type.
 */
export function resolvePanelNavigationTarget({
  targetType,
  panelConfigs,
  panelFrozen,
  openIfMissing = true,
  maxPanels = 4,
}: {
  targetType: string;
  panelConfigs: string[];
  panelFrozen: boolean[];
  openIfMissing?: boolean;
  maxPanels?: number;
}): PanelNavigationResolution {
  const liveIndex = panelConfigs.findIndex(
    (config, index) => config === targetType && !panelFrozen[index]
  );
  if (liveIndex !== -1) {
    return { targetIndex: liveIndex, shouldOpenNewPanel: false, ignored: false, ignoreReason: null };
  }

  if (!openIfMissing) {
    return { targetIndex: null, shouldOpenNewPanel: false, ignored: true, ignoreReason: 'no-matching-panel' };
  }

  if (panelConfigs.length < maxPanels) {
    return { targetIndex: null, shouldOpenNewPanel: true, ignored: false, ignoreReason: null };
  }

  return { targetIndex: null, shouldOpenNewPanel: false, ignored: true, ignoreReason: 'no-space' };
}
