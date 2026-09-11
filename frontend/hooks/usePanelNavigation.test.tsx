import type { CodeEntity, WorkspaceDocument, KnowledgeSource } from '@/types/domain';
import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { useRef, useState } from 'react';
import { usePanelNavigation } from './usePanelNavigation';
import type { PanelHistoryEntry, PanelSelection } from '@/lib/panelHistory';
import type { PinnedCode } from './useWorkspaceLayout';

type HarnessOptions = {
  panelConfigs?: string[];
  panelFrozen?: boolean[];
  panelSelections?: PanelSelection[];
  panelHistory?: PanelHistoryEntry[];
};

type FileNavEntry = {
  file: string | null;
  doc: WorkspaceDocument | null;
  tab: 'code' | 'doc' | 'weborigin' | 'graph';
};

function useNavigationHarness(options: HarnessOptions = {}) {
  const [panelSelections, setPanelSelections] = useState<PanelSelection[]>(options.panelSelections ?? [{
    selectedFile: null,
    selectedDoc: null,
    selectedEntity: null,
    selectedLine: null,
  }]);
  const [panelHistory, setPanelHistory] = useState<PanelHistoryEntry[]>(options.panelHistory ?? [{ past: [], future: [] }]);
  const [selectedDoc, setSelectedDoc] = useState<WorkspaceDocument | null>(null);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [selectedEntity, setSelectedEntity] = useState<CodeEntity | null>(null);
  const [selectedLine, setSelectedLine] = useState<number | null>(null);
  const [fileNavStack, setFileNavStack] = useState<FileNavEntry[]>([]);
  const [pinnedCode, setPinnedCode] = useState<PinnedCode | null>(null);
  const [activeMobileTab, setActiveMobileTab] = useState<'chat' | 'editor' | 'graph'>('chat');
  const isPanelHistoryNavRef = useRef(false);
  const isEditorNavigatingRef = useRef(false);
  const [addPanel] = useState(() => vi.fn().mockReturnValue(true));
  const [ensurePanelType] = useState(() => vi.fn().mockReturnValue(true));
  const [ensureLivePanelType] = useState(() => vi.fn().mockReturnValue(true));
  const [showToast] = useState(() => vi.fn());
  const [handleFileSelect] = useState(() => vi.fn().mockResolvedValue(undefined));
  const [loadFileReferences] = useState(() => vi.fn().mockResolvedValue(undefined));
  const [setPanelFocusObject] = useState(() => vi.fn());
  const [updatePanelEntitySelection] = useState(() => vi.fn());

  const navigation = usePanelNavigation({
    t: (key) => key,
    showToast,
    selectedProject: { id: 11, name: 'Demo' },
    selectedSource: null,
    connectedSources: [{ id: 8, type: 'local', name: 'manual.pdf' }],
    projectEntities: [],
    panelConfigs: options.panelConfigs ?? ['chat'],
    panelFrozen: options.panelFrozen ?? [false],
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
    setIsEditorMaximized: vi.fn(),
    isPanelHistoryNavRef,
    isEditorNavigatingRef,
    addPanel,
    ensurePanelType,
    ensureLivePanelType,
    updatePanelEntitySelection,
    handleFileSelect,
    loadFileReferences,
  });

  return {
    navigation,
    addPanel,
    ensurePanelType,
    ensureLivePanelType,
    showToast,
    panelSelections,
    panelHistory,
    selectedDoc,
    pinnedCode,
    activeMobileTab,
    handleFileSelect,
  };
}

describe('usePanelNavigation', () => {
  it('opens a document reference in a new matching panel', async () => {
    const { result } = renderHook(() => useNavigationHarness({ panelConfigs: ['chat'] }));

    await act(async () => {
      await result.current.navigation.handlePanelFileSelect(0, 'manual.pdf', null, 8);
    });

    expect(result.current.addPanel).toHaveBeenCalledWith('doc', {
      selectedFile: 'manual.pdf',
      selectedDoc: { id: 8, name: 'manual.pdf' },
      selectedEntity: null,
      selectedLine: null,
    }, false);
    expect(result.current.pinnedCode).toMatchObject({
      filepath: 'manual.pdf',
      line: 0,
      sourceId: 8,
    });
    expect(result.current.activeMobileTab).toBe('editor');
  });

  it('keeps frozen-panel navigation local and appends its selection history', async () => {
    const previousSelection: PanelSelection = {
      selectedFile: 'old.cbl',
      selectedDoc: null,
      selectedEntity: null,
      selectedLine: 3,
    };
    const { result } = renderHook(() => useNavigationHarness({
      panelConfigs: ['code'],
      panelFrozen: [true],
      panelSelections: [previousSelection],
    }));

    await act(async () => {
      await result.current.navigation.handlePanelFileSelect(0, 'new.cbl', 12);
    });

    expect(result.current.panelSelections[0]).toMatchObject({
      selectedFile: 'new.cbl',
      selectedLine: 12,
    });
    expect(result.current.panelHistory[0].past).toEqual([previousSelection]);
    expect(result.current.pinnedCode).toMatchObject({ filepath: 'new.cbl', line: 12 });
  });

  it('replaces a live (non-frozen) panel\'s file directly instead of leaving the old one behind', async () => {
    // Regression: a chat citation opening into an already-open, non-frozen
    // code panel only patched selectedEntity/selectedLine into that panel's
    // own selection and left selectedFile/selectedDoc to a separate global-
    // state sync effect — the panel briefly still showed the previous file,
    // which looked like the first click on a source badge did nothing.
    const previousSelection: PanelSelection = {
      selectedFile: 'old.cbl',
      selectedDoc: null,
      selectedEntity: null,
      selectedLine: 5,
    };
    const { result } = renderHook(() => useNavigationHarness({
      panelConfigs: ['chat', 'code'],
      panelFrozen: [false, false],
      panelSelections: [{ selectedFile: null, selectedDoc: null, selectedEntity: null, selectedLine: null }, previousSelection],
    }));

    await act(async () => {
      await result.current.navigation.handlePanelFileSelect(0, 'new.cbl', 12);
    });

    expect(result.current.panelSelections[1]).toEqual({
      selectedFile: 'new.cbl',
      selectedDoc: null,
      selectedEntity: null,
      selectedLine: 12,
    });
  });

  it('seeds the document focus when a graph requests opening a document view', () => {
    const { result } = renderHook(() => useNavigationHarness({ panelConfigs: ['graph'] }));

    act(() => {
      result.current.navigation.handleDocFocusRequest('manual.pdf', 8);
    });

    expect(result.current.ensureLivePanelType).toHaveBeenCalledWith('doc', {
      selectedFile: null,
      selectedDoc: { id: 8, name: 'manual.pdf' },
      selectedEntity: null,
    });
    expect(result.current.selectedDoc).toEqual({ id: 8, name: 'manual.pdf' });
  });

  // O-090: an entity focus must carry its own end line, so the chat backend can
  // hand the LLM exactly this object's excerpt instead of the whole RAG chunk.
  it('pins an entity focus with its own end line', async () => {
    const { result } = renderHook(() => useNavigationHarness({ panelConfigs: ['code'] }));
    const entity: CodeEntity = {
      name: 'BER-ZINS',
      file_path: 'src/PROGRAM.cbl',
      start_line: 120,
      end_line: 145,
    };

    await act(async () => {
      await result.current.navigation.handlePanelEntitySelect(0, entity);
    });

    expect(result.current.pinnedCode).toMatchObject({
      filepath: 'src/PROGRAM.cbl',
      line: 120,
      endLine: 145,
      label: 'BER-ZINS',
    });
  });

  it('falls back to the start line as end line when an entity has none', async () => {
    const { result } = renderHook(() => useNavigationHarness({ panelConfigs: ['code'] }));
    const entity: CodeEntity = {
      name: 'BER-ZINS',
      file_path: 'src/PROGRAM.cbl',
      start_line: 120,
      end_line: null,
    };

    await act(async () => {
      await result.current.navigation.handlePanelEntitySelect(0, entity);
    });

    expect(result.current.pinnedCode).toMatchObject({ line: 120, endLine: 120 });
  });

  it('pins the same end-line contract via handleGutterAskEntity', () => {
    const { result } = renderHook(() => useNavigationHarness({ panelConfigs: ['code'] }));
    const entity: CodeEntity = {
      name: 'ZINS-SECTION',
      file_path: 'src/PROGRAM.cbl',
      start_line: 200,
      end_line: 260,
    };

    act(() => {
      result.current.navigation.handleGutterAskEntity(0, entity);
    });

    expect(result.current.pinnedCode).toMatchObject({ line: 200, endLine: 260 });
  });

  it('leaves end line unset for a bare gutter-line focus (no enclosing entity)', () => {
    const previousSelection: PanelSelection = {
      selectedFile: 'src/PROGRAM.cbl',
      selectedDoc: null,
      selectedEntity: null,
      selectedLine: null,
    };
    const { result } = renderHook(() => useNavigationHarness({
      panelConfigs: ['code'],
      panelSelections: [previousSelection],
    }));

    act(() => {
      result.current.navigation.handleGutterClick(0, 42, '           MOVE 0 TO WS-COUNTER');
    });

    expect(result.current.pinnedCode).toMatchObject({ filepath: 'src/PROGRAM.cbl', line: 42 });
    expect(result.current.pinnedCode?.endLine).toBeFalsy();
  });
});
