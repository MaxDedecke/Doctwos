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
  doc: any | null;
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
  const [selectedDoc, setSelectedDoc] = useState<any | null>(null);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [selectedEntity, setSelectedEntity] = useState<any | null>(null);
  const [selectedLine, setSelectedLine] = useState<number | null>(null);
  const [fileNavStack, setFileNavStack] = useState<FileNavEntry[]>([]);
  const [pinnedCode, setPinnedCode] = useState<PinnedCode | null>(null);
  const [activeMobileTab, setActiveMobileTab] = useState<'chat' | 'editor' | 'graph'>('chat');
  const isPanelHistoryNavRef = useRef(false);
  const isEditorNavigatingRef = useRef(false);
  const [addPanel] = useState(() => vi.fn());
  const [ensurePanelType] = useState(() => vi.fn());
  const [handleFileSelect] = useState(() => vi.fn().mockResolvedValue(undefined));
  const [loadFileReferences] = useState(() => vi.fn().mockResolvedValue(undefined));
  const [setPanelFocusObject] = useState(() => vi.fn());
  const [updatePanelEntitySelection] = useState(() => vi.fn());

  const navigation = usePanelNavigation({
    t: (key) => key,
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
    updatePanelEntitySelection,
    handleFileSelect,
    loadFileReferences,
  });

  return {
    navigation,
    addPanel,
    ensurePanelType,
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

  it('seeds the document focus when a graph requests opening a document view', () => {
    const { result } = renderHook(() => useNavigationHarness({ panelConfigs: ['graph'] }));

    act(() => {
      result.current.navigation.handleDocFocusRequest('manual.pdf', 8);
    });

    expect(result.current.ensurePanelType).toHaveBeenCalledWith('doc', {
      selectedFile: null,
      selectedDoc: { id: 8, name: 'manual.pdf' },
      selectedEntity: null,
    });
    expect(result.current.selectedDoc).toEqual({ id: 8, name: 'manual.pdf' });
  });
});
