import type { ShowToast } from '@/components/Toast';
import { api } from '@/app/services/api';
import { appendPanelHistory, type PanelHistoryEntry, type PanelSelection } from '@/lib/panelHistory';
import { resolvePanelNavigationTarget } from '@/lib/panelNavigation';
import { resolveReferenceTarget } from '@/lib/referenceTarget';
import { getSelectionViewType } from '@/lib/workspaceSelection';
import type { CodeEntity, FocusObject, KnowledgeSource, Project, WorkspaceDocument } from '@/types/domain';
import { isAxiosError } from 'axios';
import type { Dispatch, MutableRefObject, SetStateAction } from 'react';
import { useCallback } from 'react';
import type { PinnedCode } from './useWorkspaceLayout';

type Translator = (key: string, vars?: Record<string, string | number>) => string;
type Setter<T> = Dispatch<SetStateAction<T>>;
type FileNavEntry = {
  file: string | null;
  doc: WorkspaceDocument | null;
  tab: 'code' | 'doc' | 'weborigin' | 'graph';
};

interface PanelNavigationOptions {
  t: Translator;
  showToast: ShowToast;
  selectedProject: Project | null;
  selectedSource: KnowledgeSource | null;
  connectedSources: KnowledgeSource[];
  projectEntities: CodeEntity[];
  panelConfigs: string[];
  panelFrozen: boolean[];
  panelSelections: PanelSelection[];
  fileNavStack: FileNavEntry[];
  setPinnedCode: Setter<PinnedCode | null>;
  setPanelFocusObject: Setter<Array<FocusObject | null>>;
  setPanelSelections: Setter<PanelSelection[]>;
  setPanelHistory: Setter<PanelHistoryEntry[]>;
  setActiveMobileTab: Setter<'chat' | 'editor' | 'graph'>;
  setSelectedDoc: Setter<WorkspaceDocument | null>;
  setSelectedFile: Setter<string | null>;
  setSelectedEntity: Setter<CodeEntity | null>;
  setSelectedLine: Setter<number | null>;
  setFileNavStack: Setter<FileNavEntry[]>;
  setIsEditorMaximized: Setter<boolean>;
  isPanelHistoryNavRef: MutableRefObject<boolean>;
  isEditorNavigatingRef: MutableRefObject<boolean>;
  addPanel: (type: string, selectionOverride?: Partial<PanelSelection>, frozenOverride?: boolean) => boolean;
  ensurePanelType: (type: string, selectionOverride?: Partial<PanelSelection>, frozenOverride?: boolean) => boolean;
  ensureLivePanelType: (type: string, selectionOverride?: Partial<PanelSelection>, frozenOverride?: boolean) => boolean;
  updatePanelEntitySelection: (index: number, entity: CodeEntity) => void;
  handleFileSelect: (path: string | null, line?: number | null, sourceId?: number | string | null, projectOverride?: Project | null) => Promise<void>;
  loadFileReferences: (filePath: string, entityName?: string | null, projectOverride?: Project | null) => Promise<void>;
}

export function usePanelNavigation({
  t,
  showToast,
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
  ensureLivePanelType,
  updatePanelEntitySelection,
  handleFileSelect,
  loadFileReferences,
}: PanelNavigationOptions) {
  const pinFileFocus = useCallback((path: string | null, line: number | null = null, sourceId: number | string | null = null) => {
    if (!path) return;
    setPinnedCode({ filepath: path, line: line ?? 0, sourceId });
  }, [setPinnedCode]);

  const pinEntityFocus = useCallback((entity: CodeEntity) => {
    if (!entity) return;
    setPinnedCode({
      filepath: entity.file_path,
      line: entity.start_line ?? 0,
      // O-090: the object's own end line, so the chat backend can hand the LLM
      // exactly this object's excerpt instead of the whole chunk it sits in.
      endLine: entity.end_line ?? entity.start_line ?? null,
      label: entity.name,
      sourceId: entity.source_id ?? null,
      program: entity.program ?? null,
      section: entity.section ?? null,
      paragraph: entity.paragraph ?? null,
    });
  }, [setPinnedCode]);

  const handleObjectFocus = useCallback((object: FocusObject, panelIndex: number) => {
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

  const handlePanelEntitySelect = useCallback(async (index: number, entity: CodeEntity) => {
    pinEntityFocus(entity);
    updatePanelEntitySelection(index, entity);
  }, [pinEntityFocus, updatePanelEntitySelection]);

  const handlePanelFileSelect = useCallback(async (
    index: number,
    path: string | null,
    line: number | null = null,
    sourceId: number | string | null = null,
    openIfMissing = true,
  ) => {
    const { isDoc, isWebOrigin, resolvedSourceId } = resolveReferenceTarget(path, sourceId, connectedSources);
    const targetDoc = resolvedSourceId && (isDoc || isWebOrigin)
      ? { id: resolvedSourceId, name: path || '', ...(isWebOrigin ? { isWebOrigin: true, url: path || undefined } : {}) }
      : null;
    const targetType = getSelectionViewType(path, targetDoc);
    let focusedEntity = path && !targetDoc
      ? projectEntities.find((entity: CodeEntity) =>
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
      } catch (error) {
        if (!isAxiosError(error) || error.response?.status !== 404) console.error('Failed to resolve code focus:', error);
      }
    }

    let targetIndex = index;
    if (targetType && targetType !== panelConfigs[index]) {
      const resolution = resolvePanelNavigationTarget({
        targetType,
        panelConfigs,
        panelFrozen,
        openIfMissing,
      });
      if (resolution.shouldOpenNewPanel) {
        pinFileFocus(path, line, resolvedSourceId);
        addPanel(targetType, {
          selectedFile: path,
          selectedDoc: targetDoc,
          selectedEntity: focusedEntity,
          selectedLine: line,
        }, false);
        setActiveMobileTab(targetType === 'graph' ? 'graph' : targetType === 'chat' ? 'chat' : 'editor');
        return;
      }
      if (resolution.ignored || resolution.targetIndex === null) {
        // D-2: an der Panel-Obergrenze verpufft der Klick sonst kommentarlos.
        // Der "nur anstupsen"-Fall (openIfMissing=false) bleibt bewusst still.
        if (resolution.ignoreReason === 'no-space') showToast(t('page.toast.noPanelSpace'), 'error');
        return;
      }
      targetIndex = resolution.targetIndex;
      setActiveMobileTab(targetType === 'graph' ? 'graph' : targetType === 'chat' ? 'chat' : 'editor');
    }

    pinFileFocus(path, line, resolvedSourceId);

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
      // Reusing an existing live panel (targetIndex !== index, e.g. a chat
      // citation opening into an already-open code panel): the panel's own
      // selection must carry selectedFile/selectedDoc directly, not just
      // wait for the separate global-selection sync effect in
      // useWorkspaceLayout to notice the setSelectedFile/setSelectedDoc call
      // below on a later render. Without this, the panel's props briefly
      // still show the *previous* file, and clicking the very citation that
      // should have opened it appeared to require a second click.
      const nextSelection = {
        selectedFile: targetDoc ? null : path,
        selectedDoc: targetDoc,
        selectedEntity: focusedEntity,
        selectedLine: targetDoc ? null : line,
      };
      setSelectedDoc(nextSelection.selectedDoc);
      setSelectedFile(nextSelection.selectedFile);
      setSelectedEntity(nextSelection.selectedEntity);
      setSelectedLine(nextSelection.selectedLine);
      setPanelSelections(previous => {
        const next = [...previous];
        next[targetIndex] = nextSelection;
        return next;
      });
    }
  }, [addPanel, connectedSources, panelConfigs, panelFrozen, panelSelections, pinFileFocus, projectEntities, selectedProject, setActiveMobileTab, setPanelHistory, setPanelSelections, setSelectedDoc, setSelectedEntity, setSelectedFile, setSelectedLine, isPanelHistoryNavRef, showToast, t]);

  const handleDocFocusRequest = useCallback((filePath: string, sourceId: number | string | null, openIfMissing = true) => {
    if (!sourceId) return;
    const hasLiveDocPanel = panelConfigs.some((config, index) => config === 'doc' && !panelFrozen[index]);
    if (!hasLiveDocPanel && !openIfMissing) return;
    const selectionOverride = {
      selectedFile: null,
      selectedDoc: { id: sourceId, name: filePath },
      selectedEntity: null,
    };
    if (!ensureLivePanelType('doc', selectionOverride)) {
      showToast(t('page.toast.noPanelSpace'), 'error');
      return;
    }
    pinFileFocus(filePath, null, sourceId);
    setSelectedDoc({ id: sourceId, name: filePath });
    setSelectedFile(null);
    setSelectedLine(null);
  }, [ensureLivePanelType, panelConfigs, panelFrozen, pinFileFocus, setSelectedDoc, setSelectedFile, setSelectedLine, showToast, t]);

  const handleGutterClick = useCallback((panelIndex: number, lineNumber: number, lineContent: string) => {
    const selection = panelSelections[panelIndex];
    const filepath = selection?.selectedFile;
    if (!filepath) return;

    const enclosingEntities = projectEntities.filter((candidate) =>
      candidate.file_path === filepath &&
      candidate.start_line != null && candidate.start_line <= lineNumber &&
      (candidate.end_line ?? candidate.start_line) >= lineNumber
    );
    const entity = selection?.selectedEntity || enclosingEntities[0];
    const enclosingName = (type: string) => enclosingEntities
      .filter((candidate) => candidate.type === type)
      .sort((a, b) => ((a.end_line ?? a.start_line ?? 0) - (a.start_line ?? 0)) - ((b.end_line ?? b.start_line ?? 0) - (b.start_line ?? 0)))[0]?.name || null;
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
    if (!ensurePanelType('chat')) showToast(t('page.toast.noPanelSpace'), 'error');
    setActiveMobileTab('chat');
    setTimeout(() => {
      const textarea = document.getElementById('chat-textarea') as HTMLTextAreaElement;
      if (textarea) textarea.focus();
    }, 150);
  }, [ensurePanelType, panelSelections, projectEntities, selectedSource, setActiveMobileTab, setPinnedCode, showToast, t]);

  const handleGutterAskEntity = useCallback((panelIndex: number, entity: CodeEntity) => {
    if (!entity) return;
    setPinnedCode({
      filepath: entity.file_path,
      line: entity.start_line ?? 0,
      // O-090: see pinEntityFocus above — same entity-focus contract.
      endLine: entity.end_line ?? entity.start_line ?? null,
      label: entity.name,
      sourceId: entity.source_id ?? selectedSource?.id ?? null,
      program: entity.program ?? null,
      section: entity.section ?? null,
      paragraph: entity.paragraph ?? null,
    });
    if (!ensurePanelType('chat')) showToast(t('page.toast.noPanelSpace'), 'error');
    setActiveMobileTab('chat');
    setTimeout(() => {
      const textarea = document.getElementById('chat-textarea') as HTMLTextAreaElement;
      if (textarea) textarea.focus();
    }, 150);
  }, [ensurePanelType, selectedSource, setActiveMobileTab, setPinnedCode, showToast, t]);

  const handleEntitySelect = useCallback(async (entity: CodeEntity, projectOverride: Project | null = null) => {
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
