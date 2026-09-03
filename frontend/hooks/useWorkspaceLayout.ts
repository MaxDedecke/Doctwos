import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '@/app/services/api';
import {
  appendPanelHistory,
  EMPTY_PANEL_SELECTION,
  navigatePanelHistory,
  type PanelHistoryEntry,
  type PanelSelection,
} from '@/lib/panelHistory';
import { getSelectionViewType } from '@/lib/workspaceSelection';
import {
  clampPercentBetween,
  clampWorkspacePercent,
  MIN_THREE_COL_PANEL_PERCENT,
  pointerToPercent,
  pointerToWorkspacePercent,
} from '@/lib/workspaceResize';
import { cn } from '@/lib/utils';

type Translate = (key: string, values?: Record<string, unknown>) => string;

interface UseWorkspaceLayoutOptions {
  activeSessionId: number | null;
  selectedProject: any | null;
  selectedSource: any | null;
  t: Translate;
}

export interface PinnedCode {
  filepath: string;
  line: number;
  label?: string;
  context?: string;
  sourceId?: number | string | null;
  program?: string | null;
  section?: string | null;
  paragraph?: string | null;
}

type LayoutMode = '1-pane' | 'split' | '3-col' | '4-grid';

/**
 * Owns the global workspace situation: selection, panel slots, panel history,
 * responsive layout, and the debounced session snapshot. File loading itself
 * remains outside because it is an I/O concern with source-specific routing.
 */
export function useWorkspaceLayout({
  activeSessionId,
  selectedProject,
  selectedSource,
  t,
}: UseWorkspaceLayoutOptions) {
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [isMobile, setIsMobile] = useState(false);
  const [activeMobileTab, setActiveMobileTab] = useState<'chat' | 'editor' | 'graph'>('chat');
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [selectedDoc, setSelectedDoc] = useState<any | null>(null);
  const [selectedLine, setSelectedLine] = useState<number | null>(null);
  const [activeRightTab, setActiveRightTab] = useState<'code' | 'doc' | 'weborigin' | 'graph'>('code');
  const [fileContent, setFileContent] = useState('');
  const [fileContentFormat, setFileContentFormat] = useState('text');
  const [isLoadingFile, setIsLoadingFile] = useState(false);
  const [isEditorMaximized, setIsEditorMaximized] = useState(false);
  const [workspaceSplit, setWorkspaceSplit] = useState('45/55');
  const [splitPercent, setSplitPercent] = useState(45);
  const [gridColumnPercent, setGridColumnPercent] = useState(50);
  const [gridRowPercent, setGridRowPercent] = useState(50);
  // Boundaries (as % of container width) between the 3-col layout's three
  // panels: panel 0 spans [0, threeColLeftPercent], panel 1 spans
  // [threeColLeftPercent, threeColRightPercent], panel 2 gets the rest.
  const [threeColLeftPercent, setThreeColLeftPercent] = useState(100 / 3);
  const [threeColRightPercent, setThreeColRightPercent] = useState((100 / 3) * 2);
  const [isDragging, setIsDragging] = useState(false);
  const [panelConfigs, setPanelConfigs] = useState<string[]>(['chat']);
  const [fileNavStack, setFileNavStack] = useState<Array<{
    file: string | null;
    doc: any | null;
    tab: 'code' | 'doc' | 'weborigin' | 'graph';
  }>>([]);
  const [selectedEntity, setSelectedEntity] = useState<any | null>(null);
  const [pinnedCode, setPinnedCode] = useState<PinnedCode | null>(null);
  const [panelFrozen, setPanelFrozen] = useState<boolean[]>([false]);
  const [panelFocusObject, setPanelFocusObject] = useState<Array<any | null>>([null]);
  const [panelSelections, setPanelSelections] = useState<PanelSelection[]>([EMPTY_PANEL_SELECTION]);
  const [panelHistory, setPanelHistory] = useState<PanelHistoryEntry[]>([{ past: [], future: [] }]);
  const [activePanelIndex, setActivePanelIndex] = useState(0);

  const isDraggingRef = useRef(false);
  const resizeModeRef = useRef<'split' | 'grid' | 'three-col' | null>(null);
  const resizeContainerRef = useRef<HTMLElement | null>(null);
  const dragStartXRef = useRef(0);
  const dragStartPercentRef = useRef(45);
  // Which 3-col divider is being dragged, and the *other* divider's position
  // at drag start -- it doesn't move during this drag, so it's the fixed
  // bound the dragged divider must not cross (kept in a ref, not state, to
  // avoid the pointermove handler closing over a stale value).
  const threeColDividerRef = useRef<'left' | 'right' | null>(null);
  const threeColOtherBoundaryRef = useRef(100 / 3);
  const splitContainerRef = useRef<HTMLDivElement>(null);
  const isPanelHistoryNavRef = useRef(false);
  const activePanelIndexRef = useRef(0);
  const pendingPanelTypesRef = useRef<Set<string>>(new Set());
  const pendingPanelCountRef = useRef(0);
  const isRestoringSnapshotRef = useRef(false);
  const snapshotDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (typeof window !== 'undefined') {
      // This is a deliberate DOM-to-state initialization. It runs once after
      // mount to avoid a server/client hydration mismatch on mobile.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setIsSidebarOpen(window.innerWidth >= 768);
    }
  }, []);

  useEffect(() => {
    const handleResize = () => setIsMobile(window.innerWidth < 768);
    handleResize();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // Keep the mobile tab aligned with the content that is actually available.
  // These guards preserve the mobile navigation rules while keeping that
  // cross-panel state out of the page component.
  const [previousMobileReset, setPreviousMobileReset] = useState({ selectedFile, selectedDoc, activeRightTab });
  if (
    previousMobileReset.selectedFile !== selectedFile ||
    previousMobileReset.selectedDoc !== selectedDoc ||
    previousMobileReset.activeRightTab !== activeRightTab
  ) {
    setPreviousMobileReset({ selectedFile, selectedDoc, activeRightTab });
    if (!selectedFile && !selectedDoc && activeRightTab !== 'graph') setActiveMobileTab('chat');
  }

  const [previousGraphSync, setPreviousGraphSync] = useState({ activeRightTab, isMobile });
  if (previousGraphSync.activeRightTab !== activeRightTab || previousGraphSync.isMobile !== isMobile) {
    setPreviousGraphSync({ activeRightTab, isMobile });
    if (activeRightTab === 'graph' && isMobile) setActiveMobileTab('graph');
  }

  // Synchronize live panels during render so a global selection is reflected
  // before a child panel renders. The dependency snapshot prevents a render
  // loop while keeping the existing history semantics intact.
  const [previousPanelSync, setPreviousPanelSync] = useState({
    selectedFile,
    selectedDoc,
    selectedEntity,
    selectedLine,
    panelFrozen,
    panelConfigs,
  });
  /* eslint-disable react-hooks/refs, react-hooks/immutability */
  if (
    previousPanelSync.selectedFile !== selectedFile ||
    previousPanelSync.selectedDoc !== selectedDoc ||
    previousPanelSync.selectedEntity !== selectedEntity ||
    previousPanelSync.selectedLine !== selectedLine ||
    previousPanelSync.panelFrozen !== panelFrozen ||
    previousPanelSync.panelConfigs !== panelConfigs
  ) {
    setPreviousPanelSync({ selectedFile, selectedDoc, selectedEntity, selectedLine, panelFrozen, panelConfigs });
    const incomingType = getSelectionViewType(selectedFile, selectedDoc);
    let changed = false;
    const historyPushIndexes: number[] = [];
    const nextSelections = panelSelections.map((selection, index) => {
      if (panelFrozen[index]) return selection;
      const panelType = panelConfigs[index];
      const shouldSync = panelType === 'chat' || panelType === 'graph' || panelType === 'callgraph'
        || incomingType === null || incomingType === panelType;
      if (!shouldSync) return selection;
      if (
        selection.selectedFile !== selectedFile ||
        selection.selectedDoc !== selectedDoc ||
        selection.selectedEntity !== selectedEntity ||
        selection.selectedLine !== selectedLine
      ) {
        changed = true;
        if (!isPanelHistoryNavRef.current && !isRestoringSnapshotRef.current && (selection.selectedFile || selection.selectedDoc)) {
          historyPushIndexes.push(index);
        }
        return { selectedFile, selectedDoc, selectedEntity, selectedLine };
      }
      return selection;
    });
    if (changed) {
      const previousSelections = panelSelections;
      setPanelSelections(nextSelections);
      if (historyPushIndexes.length > 0) {
        setPanelHistory((previousHistory) => {
          const nextHistory = [...previousHistory];
          historyPushIndexes.forEach((index) => {
            const entry = nextHistory[index] || { past: [], future: [] };
            nextHistory[index] = appendPanelHistory(entry, previousSelections[index], nextSelections[index]);
          });
          return nextHistory;
        });
      }
    }
  }
  /* eslint-enable react-hooks/refs, react-hooks/immutability */

  const togglePanelFreeze = useCallback((index: number) => {
    const willUnfreeze = panelFrozen[index];
    setPanelFrozen((previous) => {
      const next = [...previous];
      next[index] = !next[index];
      return next;
    });

    if (willUnfreeze) {
      const previousSelection = panelSelections[index] || EMPTY_PANEL_SELECTION;
      const liveSelection: PanelSelection = { selectedFile, selectedDoc, selectedEntity, selectedLine: null };
      setPanelHistory((previousHistory) => {
        const nextHistory = [...previousHistory];
        const entry = nextHistory[index] || { past: [], future: [] };
        nextHistory[index] = appendPanelHistory(entry, previousSelection, liveSelection);
        return nextHistory;
      });
      setPanelSelections((previousSelections) => {
        const next = [...previousSelections];
        next[index] = liveSelection;
        return next;
      });
    }
  }, [panelFrozen, panelSelections, selectedDoc, selectedEntity, selectedFile]);

  const closePanel = useCallback((index: number) => {
    if (panelConfigs.length <= 1) return;
    setPanelConfigs((previous) => previous.filter((_, itemIndex) => itemIndex !== index));
    setPanelFrozen((previous) => previous.filter((_, itemIndex) => itemIndex !== index));
    setPanelSelections((previous) => previous.filter((_, itemIndex) => itemIndex !== index));
    setPanelHistory((previous) => previous.filter((_, itemIndex) => itemIndex !== index));
    setPanelFocusObject((previous) => previous.filter((_, itemIndex) => itemIndex !== index));
    activePanelIndexRef.current = Math.max(0, index - 1);
  }, [panelConfigs.length]);

  const addPanel = useCallback((type: string, selectionOverride?: Partial<PanelSelection>, frozenOverride?: boolean) => {
    // React state from the current render is stale during same-tick bursts.
    // This counter makes the four-panel cap atomic until the next commit.
    if (panelConfigs.length + pendingPanelCountRef.current >= 4) return;
    pendingPanelCountRef.current += 1;
    setPanelFrozen((previous) => [...previous, frozenOverride ?? false]);
    setPanelFocusObject((previous) => [...previous, null]);
    setPanelSelections((previous) => [...previous, {
      selectedFile: selectionOverride?.selectedFile ?? selectedFile,
      selectedDoc: selectionOverride?.selectedDoc ?? selectedDoc,
      selectedEntity: selectionOverride?.selectedEntity ?? selectedEntity,
      selectedLine: selectionOverride?.selectedLine ?? null,
    }]);
    setPanelHistory((previous) => [...previous, { past: [], future: [] }]);
    setPanelConfigs((previous) => [...previous, type]);
  }, [panelConfigs.length, selectedDoc, selectedEntity, selectedFile]);

  useEffect(() => {
    pendingPanelTypesRef.current.clear();
    pendingPanelCountRef.current = 0;
  }, [panelConfigs]);

  const ensurePanelType = useCallback((type: string, selectionOverride?: Partial<PanelSelection>, frozenOverride?: boolean) => {
    if (panelConfigs.includes(type) || pendingPanelTypesRef.current.has(type)) return;
    pendingPanelTypesRef.current.add(type);
    addPanel(type, selectionOverride, frozenOverride);
  }, [addPanel, panelConfigs]);

  const cellCls = (expanded: string) => cn('h-full min-w-0 min-h-0', expanded);

  const handlePanelEntitySelect = useCallback((index: number, entity: any) => {
    const previousSelection = panelSelections[index];
    setPanelSelections((previous) => {
      const next = [...previous];
      next[index] = { ...next[index], selectedEntity: entity };
      return next;
    });
    if (panelFrozen[index] && !isPanelHistoryNavRef.current && previousSelection &&
        (previousSelection.selectedFile || previousSelection.selectedDoc) && previousSelection.selectedEntity !== entity) {
      setPanelHistory((previousHistory) => {
        const nextHistory = [...previousHistory];
        const entry = nextHistory[index] || { past: [], future: [] };
        nextHistory[index] = appendPanelHistory(entry, previousSelection, { ...previousSelection, selectedEntity: entity });
        return nextHistory;
      });
    }
    if (!panelFrozen[index]) setSelectedEntity(entity);
  }, [panelFrozen, panelSelections]);

  const goBackPanel = useCallback((index: number) => {
    const entry = panelHistory[index];
    if (!entry) return;
    const transition = navigatePanelHistory(entry, panelSelections[index] || EMPTY_PANEL_SELECTION, 'back');
    if (!transition) return;
    isPanelHistoryNavRef.current = true;
    setPanelHistory((previous) => {
      const next = [...previous];
      next[index] = transition.entry;
      return next;
    });
    setPanelSelections((previous) => {
      const next = [...previous];
      next[index] = transition.selection;
      return next;
    });
    if (!panelFrozen[index]) {
      setSelectedFile(transition.selection.selectedFile);
      setSelectedDoc(transition.selection.selectedDoc);
      setSelectedEntity(transition.selection.selectedEntity);
      setSelectedLine(transition.selection.selectedLine);
    }
    setTimeout(() => { isPanelHistoryNavRef.current = false; }, 0);
  }, [panelHistory, panelSelections, panelFrozen]);

  const goForwardPanel = useCallback((index: number) => {
    const entry = panelHistory[index];
    if (!entry) return;
    const transition = navigatePanelHistory(entry, panelSelections[index] || EMPTY_PANEL_SELECTION, 'forward');
    if (!transition) return;
    isPanelHistoryNavRef.current = true;
    setPanelHistory((previous) => {
      const next = [...previous];
      next[index] = transition.entry;
      return next;
    });
    setPanelSelections((previous) => {
      const next = [...previous];
      next[index] = transition.selection;
      return next;
    });
    if (!panelFrozen[index]) {
      setSelectedFile(transition.selection.selectedFile);
      setSelectedDoc(transition.selection.selectedDoc);
      setSelectedEntity(transition.selection.selectedEntity);
      setSelectedLine(transition.selection.selectedLine);
    }
    setTimeout(() => { isPanelHistoryNavRef.current = false; }, 0);
  }, [panelHistory, panelSelections, panelFrozen]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (!event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
      if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
      const index = isMobile
        ? (activeMobileTab === 'chat' ? panelConfigs.indexOf('chat')
          : activeMobileTab === 'graph' ? panelConfigs.indexOf('graph')
          : panelConfigs.findIndex((type) => type !== 'chat' && type !== 'graph'))
        : activePanelIndex;
      if (index < 0 || index >= panelConfigs.length) return;
      event.preventDefault();
      if (event.key === 'ArrowLeft') goBackPanel(index);
      else goForwardPanel(index);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [activeMobileTab, activePanelIndex, isMobile, panelConfigs, panelHistory, panelSelections, panelFrozen, goBackPanel, goForwardPanel]);

  const buildWorkspaceSnapshot = () => ({
    panelConfigs,
    panelSelections,
    panelFocusObject,
    panelFrozen,
    activeRightTab,
    splitPercent,
    gridColumnPercent,
    gridRowPercent,
    threeColLeftPercent,
    threeColRightPercent,
    fileNavStack,
    pinnedCode,
    selectedProjectId: selectedProject?.id ?? null,
    selectedSourceId: selectedSource?.id ?? null,
  });

  useEffect(() => {
    if (!activeSessionId || isRestoringSnapshotRef.current) return;
    if (snapshotDebounceRef.current) clearTimeout(snapshotDebounceRef.current);
    snapshotDebounceRef.current = setTimeout(() => {
      api.updateChatSessionSnapshot(activeSessionId, buildWorkspaceSnapshot())
        .catch((error) => console.error('Failed to save workspace snapshot:', error));
    }, 1200);
    return () => {
      if (snapshotDebounceRef.current) clearTimeout(snapshotDebounceRef.current);
    };
  // Snapshot contents, not the callback identity, define the save boundary.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeSessionId, panelConfigs, panelSelections, panelFocusObject, panelFrozen, activeRightTab, splitPercent, gridColumnPercent, gridRowPercent, threeColLeftPercent, threeColRightPercent, fileNavStack, pinnedCode, selectedProject, selectedSource]);

  // Presets are a second representation of the same split value. The guarded
  // render update keeps a drag-selected percentage intact until a preset
  // actually changes, matching the original workspace behavior.
  const [previousWorkspaceSplit, setPreviousWorkspaceSplit] = useState(workspaceSplit);
  if (workspaceSplit !== previousWorkspaceSplit) {
    setPreviousWorkspaceSplit(workspaceSplit);
    const presetMap: Record<string, number> = { '50/50': 50, '40/60': 40, '60/40': 60, '45/55': 45 };
    setSplitPercent(presetMap[workspaceSplit] ?? 45);
  }

  useEffect(() => {
    const handlePointerMove = (event: PointerEvent) => {
      if (!isDraggingRef.current || !resizeContainerRef.current) return;
      const containerRect = resizeContainerRef.current.getBoundingClientRect();
      if (resizeModeRef.current === 'grid') {
        setGridColumnPercent(pointerToWorkspacePercent(event.clientX, containerRect.left, containerRect.width));
        setGridRowPercent(pointerToWorkspacePercent(event.clientY, containerRect.top, containerRect.height));
        return;
      }
      if (resizeModeRef.current === 'three-col') {
        const rawPercent = pointerToPercent(event.clientX, containerRect.left, containerRect.width);
        if (threeColDividerRef.current === 'left') {
          setThreeColLeftPercent(clampPercentBetween(
            rawPercent,
            MIN_THREE_COL_PANEL_PERCENT,
            threeColOtherBoundaryRef.current - MIN_THREE_COL_PANEL_PERCENT,
          ));
        } else {
          setThreeColRightPercent(clampPercentBetween(
            rawPercent,
            threeColOtherBoundaryRef.current + MIN_THREE_COL_PANEL_PERCENT,
            100 - MIN_THREE_COL_PANEL_PERCENT,
          ));
        }
        return;
      }
      const deltaPercent = ((event.clientX - dragStartXRef.current) / containerRect.width) * 100;
      setSplitPercent(clampWorkspacePercent(dragStartPercentRef.current + deltaPercent));
    };
    const handlePointerUp = () => {
      if (!isDraggingRef.current) return;
      isDraggingRef.current = false;
      resizeModeRef.current = null;
      resizeContainerRef.current = null;
      threeColDividerRef.current = null;
      setIsDragging(false);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
    window.addEventListener('pointermove', handlePointerMove);
    window.addEventListener('pointerup', handlePointerUp);
    return () => {
      window.removeEventListener('pointermove', handlePointerMove);
      window.removeEventListener('pointerup', handlePointerUp);
    };
  }, []);

  const handleDividerMouseDown = useCallback((event: React.PointerEvent) => {
    event.preventDefault();
    isDraggingRef.current = true;
    resizeModeRef.current = 'split';
    resizeContainerRef.current = splitContainerRef.current;
    setIsDragging(true);
    dragStartXRef.current = event.clientX;
    dragStartPercentRef.current = splitPercent;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  }, [splitPercent]);

  const handleGridResizePointerDown = useCallback((event: React.PointerEvent) => {
    event.preventDefault();
    isDraggingRef.current = true;
    resizeModeRef.current = 'grid';
    resizeContainerRef.current = event.currentTarget.parentElement;
    setIsDragging(true);
    document.body.style.cursor = 'move';
    document.body.style.userSelect = 'none';
  }, []);

  const handleThreeColLeftDividerPointerDown = useCallback((event: React.PointerEvent) => {
    event.preventDefault();
    isDraggingRef.current = true;
    resizeModeRef.current = 'three-col';
    threeColDividerRef.current = 'left';
    threeColOtherBoundaryRef.current = threeColRightPercent;
    resizeContainerRef.current = splitContainerRef.current;
    setIsDragging(true);
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  }, [threeColRightPercent]);

  const handleThreeColRightDividerPointerDown = useCallback((event: React.PointerEvent) => {
    event.preventDefault();
    isDraggingRef.current = true;
    resizeModeRef.current = 'three-col';
    threeColDividerRef.current = 'right';
    threeColOtherBoundaryRef.current = threeColLeftPercent;
    resizeContainerRef.current = splitContainerRef.current;
    setIsDragging(true);
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  }, [threeColLeftPercent]);

  const restoreWorkspaceSnapshot = useCallback((snapshot: any) => {
    isRestoringSnapshotRef.current = true;
    const restoredSelections = Array.isArray(snapshot.panelSelections) && snapshot.panelSelections.length > 0
      ? snapshot.panelSelections
      : [EMPTY_PANEL_SELECTION];
    const primary = restoredSelections[0];
    setSelectedFile(primary.selectedFile ?? null);
    setSelectedDoc(primary.selectedDoc ?? null);
    setSelectedEntity(primary.selectedEntity ?? null);
    setSelectedLine(primary.selectedLine ?? null);
    setPanelConfigs(Array.isArray(snapshot.panelConfigs) && snapshot.panelConfigs.length > 0 ? snapshot.panelConfigs : ['chat']);
    setPanelFrozen(Array.isArray(snapshot.panelFrozen) ? snapshot.panelFrozen : restoredSelections.map(() => false));
    setPanelSelections(restoredSelections);
    setPanelHistory(restoredSelections.map(() => ({ past: [], future: [] })));
    setPanelFocusObject(Array.isArray(snapshot.panelFocusObject) ? snapshot.panelFocusObject : restoredSelections.map(() => null));
    setFileNavStack(Array.isArray(snapshot.fileNavStack) ? snapshot.fileNavStack : []);
    setPinnedCode(snapshot.pinnedCode ?? null);
    if (typeof snapshot.activeRightTab === 'string') setActiveRightTab(snapshot.activeRightTab);
    if (typeof snapshot.splitPercent === 'number') setSplitPercent(snapshot.splitPercent);
    if (typeof snapshot.gridColumnPercent === 'number') setGridColumnPercent(clampWorkspacePercent(snapshot.gridColumnPercent));
    if (typeof snapshot.gridRowPercent === 'number') setGridRowPercent(clampWorkspacePercent(snapshot.gridRowPercent));
    if (typeof snapshot.threeColLeftPercent === 'number' && typeof snapshot.threeColRightPercent === 'number') {
      // Restore only if the pair is still a valid, ordered boundary -- a
      // corrupted or hand-edited snapshot must not collapse a column to
      // negative width.
      const left = clampPercentBetween(snapshot.threeColLeftPercent, MIN_THREE_COL_PANEL_PERCENT, 100 - 2 * MIN_THREE_COL_PANEL_PERCENT);
      const right = clampPercentBetween(snapshot.threeColRightPercent, left + MIN_THREE_COL_PANEL_PERCENT, 100 - MIN_THREE_COL_PANEL_PERCENT);
      setThreeColLeftPercent(left);
      setThreeColRightPercent(right);
    }
    setTimeout(() => { isRestoringSnapshotRef.current = false; }, 0);
  }, []);

  const resetWorkspace = useCallback(() => {
    setSelectedDoc(null);
    setSelectedFile(null);
    setSelectedEntity(null);
    setSelectedLine(null);
    setActiveRightTab('code');
    setFileContent('');
    setFileContentFormat('text');
    setPinnedCode(null);
    setFileNavStack([]);
    setPanelConfigs(['chat']);
    setPanelSelections([EMPTY_PANEL_SELECTION]);
    setPanelHistory([{ past: [], future: [] }]);
    setPanelFrozen([false]);
    setPanelFocusObject([null]);
    setSplitPercent(45);
    setGridColumnPercent(50);
    setGridRowPercent(50);
    setThreeColLeftPercent(100 / 3);
    setThreeColRightPercent((100 / 3) * 2);
    setWorkspaceSplit('45/55');
  }, []);

  return {
    isSidebarOpen,
    setIsSidebarOpen,
    isMobile,
    activeMobileTab,
    setActiveMobileTab,
    selectedFile,
    setSelectedFile,
    selectedDoc,
    setSelectedDoc,
    selectedLine,
    setSelectedLine,
    activeRightTab,
    setActiveRightTab,
    fileContent,
    setFileContent,
    fileContentFormat,
    setFileContentFormat,
    isLoadingFile,
    setIsLoadingFile,
    isEditorMaximized,
    setIsEditorMaximized,
    workspaceSplit,
    setWorkspaceSplit,
    splitPercent,
    gridColumnPercent,
    gridRowPercent,
    threeColLeftPercent,
    threeColRightPercent,
    setSplitPercent,
    isDragging,
    panelConfigs,
    setPanelConfigs,
    layoutMode: (panelConfigs.length === 1 ? '1-pane' : panelConfigs.length === 2 ? 'split' : panelConfigs.length === 3 ? '3-col' : '4-grid') as LayoutMode,
    fileNavStack,
    setFileNavStack,
    selectedEntity,
    setSelectedEntity,
    pinnedCode,
    setPinnedCode,
    panelFrozen,
    setPanelFrozen,
    panelFocusObject,
    setPanelFocusObject,
    panelSelections,
    setPanelSelections,
    panelHistory,
    setPanelHistory,
    splitContainerRef,
    activePanelIndex,
    setActivePanelIndex,
    isRestoringSnapshotRef,
    isPanelHistoryNavRef,
    togglePanelFreeze,
    closePanel,
    addPanel,
    ensurePanelType,
    cellCls,
    handlePanelEntitySelect,
    goBackPanel,
    goForwardPanel,
    handleDividerMouseDown,
    handleGridResizePointerDown,
    handleThreeColLeftDividerPointerDown,
    handleThreeColRightDividerPointerDown,
    restoreWorkspaceSnapshot,
    resetWorkspace,
  };
}
