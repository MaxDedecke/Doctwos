import { useCallback } from 'react';
import type { Dispatch, MutableRefObject, SetStateAction } from 'react';
import { api } from '@/app/services/api';
import { appendPanelHistory, type PanelHistoryEntry, type PanelSelection } from '@/lib/panelHistory';
import { resolvePanelNavigationTarget } from '@/lib/panelNavigation';
import { resolveReferenceTarget } from '@/lib/referenceTarget';
import { getSelectionViewType } from '@/lib/workspaceSelection';
import type { PinnedCode } from './useWorkspaceLayout';

type Translator = (key: string, vars?: Record<string, string | number>) => string;
type Setter<T> = Dispatch<SetStateAction<T>>;
type FileNavEntry = {
  file: string | null;
  doc: any | null;
  tab: 'code' | 'doc' | 'weborigin' | 'graph';
};

interface PanelNavigationOptions {
  t: Translator;
  selectedProject: any | null;
  selectedSource: any | null;
  connectedSources: any[];
  projectEntities: any[];
  panelConfigs: string[];
  panelFrozen: boolean[];
  panelSelections: PanelSelection[];
  fileNavStack: FileNavEntry[];
  setPinnedCode: Setter<PinnedCode | null>;
  setPanelFocusObject: Setter<Array<any | null>>;
  setPanelSelections: Setter<PanelSelection[]>;
  setPanelHistory: Setter<PanelHistoryEntry[]>;
  setActiveMobileTab: Setter<'chat' | 'editor' | 'graph'>;
  setSelectedDoc: Setter<any | null>;
  setSelectedFile: Setter<string | null>;
  setSelectedEntity: Setter<any | null>;
  setSelectedLine: Setter<number | null>;
  setFileNavStack: Setter<FileNavEntry[]>;
  setIsEditorMaximized: Setter<boolean>;
  isPanelHistoryNavRef: MutableRefObject<boolean>;
  isEditorNavigatingRef: MutableRefObject<boolean>;
  addPanel: (type: string, selectionOverride?: Partial<PanelSelection>, frozenOverride?: boolean) => void;
  ensurePanelType: (type: string, selectionOverride?: Partial<PanelSelection>, frozenOverride?: boolean) => void;
  updatePanelEntitySelection: (index: number, entity: any) => void;
  handleFileSelect: (path: string | null, line?: number | null, sourceId?: number | string | null, projectOverride?: any | null) => Promise<void>;
  loadFileReferences: (filePath: string, entityName?: string | null, projectOverride?: any | null) => Promise<void>;
}

export function usePanelNavigation({
  t,
  selectedProject,
  selectedSource,
  connectedSources,
  projectEntities,
  panelConfigs,
  panelFrozen,
  panelSelections,
  fileNavStack,
  setPinnedCode,
  setPanelFocusObject,
  setPanelSelections,
  setPanelHistory,
  setActiveMobileTab,
  setSelectedDoc,
  setSelectedFile,
  setSelectedEntity,
  setSelectedLine,
  setFileNavStack,
  setIsEditorMaximized,
  isPanelHistoryNavRef,
  isEditorNavigatingRef,
  addPanel,
  ensurePanelType,
  updatePanelEntitySelection,
  handleFileSelect,
  loadFileReferences,
}: PanelNavigationOptions) {
  const pinFileFocus = useCallback((path: string | null, line: number | null = null) => {
    if (!path) return;
    setPinnedCode({ filepath: path, line: line || 0 });
  }, [setPinnedCode]);

  const pinEntityFocus = useCallback((entity: any) => {
    if (!entity) return;
    setPinnedCode({ filepath: entity.file_path, line: entity.start_line, label: entity.name });
  }, [setPinnedCode]);

  const handleObjectFocus = useCallback((object: any, panelIndex: number) => {
    if (!object) return;
    setPanelFocusObject(previous => {
      const next = [...previous];
      next[panelIndex] = object;
      return next;
    });
    const selection = panelSelections[panelIndex];
    const filepath = selection?.selectedFile || selection?.selectedDoc?.name || t('page.objectFileFallback');
    const context =
      `${t('page.focusedObjectLabel')}: ${object.name}\n` +
      `Typ: ${object.type}\n` +
      `Material: ${object.material}\n` +
      `Volumen: ${object.volume}\n` +
      `Feuerwiderstand: ${object.fireRating}`;
    setPinnedCode({ filepath, line: 0, label: object.name, context });
    const textarea = document.getElementById('chat-textarea') as HTMLTextAreaElement;
    if (textarea) textarea.focus();
  }, [panelSelections, setPanelFocusObject, setPinnedCode, t]);

  const handlePanelEntitySelect = useCallback(async (index: number, entity: any) => {
    pinEntityFocus(entity);
    updatePanelEntitySelection(index, entity);
  }, [pinEntityFocus, updatePanelEntitySelection]);

  const handlePanelFileSelect = useCallback(async (
    index: number,
    path: string | null,
    line: number | null = null,
    sourceId: number | string | null = null,
    openIfMissing = true,
    preserveFrozenTarget = false,
  ) => {
    const { isDoc, isWebOrigin, resolvedSourceId } = resolveReferenceTarget(path, sourceId, connectedSources);
    const targetDoc = resolvedSourceId && (isDoc || isWebOrigin)
      ? { id: resolvedSourceId, name: path, ...(isWebOrigin ? { isWebOrigin: true, url: path } : {}) }
      : null;
    const targetType = getSelectionViewType(path, targetDoc);
    let focusedEntity = path && !targetDoc
      ? projectEntities.find((entity: any) =>
          entity.file_path === path &&
          (!resolvedSourceId || Number(entity.source_id) === Number(resolvedSourceId)) &&
          (entity.type === 'program' || entity.type === 'copybook')) || null
      : null;

    // Resolve code entities before any state-changing await. Graph "open in
    // view" can fire this handler next to onDocFocus; keeping the routing
    // decision synchronous prevents a duplicate panel from being opened.
    if (path && resolvedSourceId && !isWebOrigin && !targetDoc) {
      try {
        focusedEntity = (await api.resolveEntity(Number(resolvedSourceId), path, selectedProject?.id)).data;
      } catch (error: any) {
        if (error?.response?.status !== 404) console.error('Failed to resolve code focus:', error);
      }
    }

    let targetIndex = index;
    if (targetType && targetType !== panelConfigs[index]) {
      const resolution = resolvePanelNavigationTarget({
        targetType,
        panelConfigs,
        panelFrozen,
        openIfMissing,
        preserveFrozenTarget,
      });
      if (resolution.shouldOpenNewPanel) {
        addPanel(targetType, {
          selectedFile: path,
          selectedDoc: targetDoc,
          selectedEntity: focusedEntity,
          selectedLine: line,
        }, false);
        setActiveMobileTab(targetType === 'graph' ? 'graph' : targetType === 'chat' ? 'chat' : 'editor');
        return;
      }
      if (resolution.ignored || resolution.targetIndex === null) return;
      targetIndex = resolution.targetIndex;
      setActiveMobileTab(targetType === 'graph' ? 'graph' : targetType === 'chat' ? 'chat' : 'editor');
    }

    // A Call-Graph click must not rewrite the graph's own frozen selection.
    if (preserveFrozenTarget && panelFrozen[targetIndex]) return;

    pinFileFocus(path, line);

    if (panelFrozen[targetIndex]) {
      const previousSelection = panelSelections[targetIndex];
      const nextSelection = {
        selectedFile: path,
        selectedDoc: targetDoc,
        selectedEntity: focusedEntity,
        selectedLine: line,
      };
      setPanelSelections(previous => {
        const next = [...previous];
        next[targetIndex] = nextSelection;
        return next;
      });
      if (!isPanelHistoryNavRef.current && previousSelection && (previousSelection.selectedFile || previousSelection.selectedDoc) && (
        previousSelection.selectedFile !== nextSelection.selectedFile ||
        previousSelection.selectedDoc !== nextSelection.selectedDoc ||
        previousSelection.selectedEntity !== nextSelection.selectedEntity ||
        previousSelection.selectedLine !== nextSelection.selectedLine
      )) {
        setPanelHistory(previousHistory => {
          const next = [...previousHistory];
          const entry = next[targetIndex] || { past: [], future: [] };
          next[targetIndex] = appendPanelHistory(entry, previousSelection, nextSelection);
          return next;
        });
      }
    } else {
      setSelectedDoc(targetDoc);
      setSelectedFile(targetDoc ? null : path);
      setSelectedEntity(focusedEntity);
      setSelectedLine(targetDoc ? null : line);
      setPanelSelections(previous => {
        const next = [...previous];
        next[targetIndex] = {
          ...next[targetIndex],
          selectedEntity: focusedEntity,
          selectedLine: line,
        };
        return next;
      });
    }
  }, [addPanel, connectedSources, panelConfigs, panelFrozen, panelSelections, pinFileFocus, projectEntities, selectedProject, setActiveMobileTab, setPanelHistory, setPanelSelections, setSelectedDoc, setSelectedEntity, setSelectedFile, setSelectedLine, isPanelHistoryNavRef]);

  const handleDocFocusRequest = useCallback((filePath: string, sourceId: number | string | null, openIfMissing = true) => {
    if (!sourceId) return;
    if (!panelConfigs.includes('doc') && !openIfMissing) return;
    const selectionOverride = {
      selectedFile: null,
      selectedDoc: { id: sourceId, name: filePath },
      selectedEntity: null,
    };
    ensurePanelType('doc', selectionOverride);
    setSelectedDoc({ id: sourceId, name: filePath });
    setSelectedFile(null);
    setSelectedLine(null);
  }, [ensurePanelType, panelConfigs, setSelectedDoc, setSelectedFile, setSelectedLine]);

  const handleGutterClick = useCallback((panelIndex: number, lineNumber: number, lineContent: string) => {
    const selection = panelSelections[panelIndex];
    const filepath = selection?.selectedFile;
    if (!filepath) return;

    const enclosingEntities = projectEntities.filter((candidate: any) =>
      candidate.file_path === filepath &&
      candidate.start_line <= lineNumber &&
      candidate.end_line >= lineNumber
    );
    const entity = selection?.selectedEntity || enclosingEntities[0];
    const enclosingName = (type: string) => enclosingEntities
      .filter((candidate: any) => candidate.type === type)
      .sort((a: any, b: any) => (a.end_line - a.start_line) - (b.end_line - b.start_line))[0]?.name || null;
    setPinnedCode({
      filepath,
      line: lineNumber,
      label: `${filepath.split('/').pop()}:${lineNumber}`,
      context: lineContent,
      sourceId: entity?.source_id || selectedSource?.id || null,
      program: enclosingName('program'),
      section: enclosingName('section'),
      paragraph: enclosingName('paragraph'),
    });
    ensurePanelType('chat');
    setActiveMobileTab('chat');
    setTimeout(() => {
      const textarea = document.getElementById('chat-textarea') as HTMLTextAreaElement;
      if (textarea) textarea.focus();
    }, 150);
  }, [ensurePanelType, panelSelections, projectEntities, selectedSource, setActiveMobileTab, setPinnedCode]);

  const handleGutterAskEntity = useCallback((panelIndex: number, entity: any) => {
    if (!entity) return;
    setPinnedCode({
      filepath: entity.file_path,
      line: entity.start_line,
      label: entity.name,
      sourceId: entity.source_id || selectedSource?.id || null,
    });
    ensurePanelType('chat');
    setActiveMobileTab('chat');
    setTimeout(() => {
      const textarea = document.getElementById('chat-textarea') as HTMLTextAreaElement;
      if (textarea) textarea.focus();
    }, 150);
  }, [ensurePanelType, selectedSource, setActiveMobileTab, setPinnedCode]);

  const handleEntitySelect = useCallback(async (entity: any, projectOverride: any = null) => {
    setSelectedEntity(entity);
    pinEntityFocus(entity);
    loadFileReferences(entity.file_path, entity.name, projectOverride);
    await handleFileSelect(entity.file_path, entity.start_line, entity.source_id ?? null, projectOverride);
  }, [handleFileSelect, loadFileReferences, pinEntityFocus, setSelectedEntity]);

  const handleNavigateBack = useCallback(async () => {
    if (fileNavStack.length === 0) return;
    const newStack = fileNavStack.slice(0, -1);
    const previous = fileNavStack[fileNavStack.length - 1];
    setFileNavStack(newStack);
    if (newStack.length === 0) setIsEditorMaximized(false);
    isEditorNavigatingRef.current = true;
    if (previous.file) {
      await handleFileSelect(previous.file, null, null);
    } else if (previous.doc) {
      await handleFileSelect(previous.doc.name, null, previous.doc.id);
    }
  }, [fileNavStack, handleFileSelect, isEditorNavigatingRef, setFileNavStack, setIsEditorMaximized]);

  return {
    pinFileFocus,
    pinEntityFocus,
    handleObjectFocus,
    handlePanelEntitySelect,
    handlePanelFileSelect,
    handleDocFocusRequest,
    handleGutterClick,
    handleGutterAskEntity,
    handleEntitySelect,
    handleNavigateBack,
  };
}
