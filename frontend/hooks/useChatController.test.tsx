import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useState } from 'react';
import { api } from '@/app/services/api';
import { useChatController } from './useChatController';

const routerPush = vi.hoisted(() => vi.fn());

vi.mock('next/navigation', () => ({
  usePathname: () => '/workspace',
  useRouter: () => ({ push: routerPush }),
}));

type HarnessOverrides = {
  activeSessionId?: number | null;
  chatMessages?: any[];
  currentMessage?: string;
  isLoading?: boolean;
  selectedProject?: any | null;
  selectedSource?: any | null;
  pinnedCode?: any;
  handleProjectSelect?: any;
  restoreWorkspaceSnapshot?: any;
  resetChatSession?: any;
  showToast?: any;
  buildWorkspaceSnapshot?: any;
  sessions?: any[];
};

function useControllerHarness(overrides: HarnessOverrides = {}) {
  const [activeSessionId, setActiveSessionId] = useState<number | null>(overrides.activeSessionId ?? null);
  const [chatMessages, setChatMessages] = useState<any[]>(overrides.chatMessages ?? []);
  const [currentMessage, setCurrentMessage] = useState(overrides.currentMessage ?? '');
  const [isLoading, setIsLoading] = useState(overrides.isLoading ?? false);
  const [sessions, setSessions] = useState<any[]>(overrides.sessions ?? []);
  const [selectedSource, setSelectedSource] = useState<any | null>(overrides.selectedSource ?? null);
  const selectedProject = overrides.selectedProject ?? { id: 11, name: 'Demo' };
  // Lazy useState initializers (not a plain `overrides.X ?? vi.fn()`) so the
  // mock identity is stable across re-renders -- a handler under test here
  // can itself trigger a state update (e.g. setSessions), and asserting on
  // `result.current.showToast` after that re-render must still see the same
  // mock instance the callback actually closed over, not a freshly recreated one.
  const [handleProjectSelect] = useState(() => (overrides.handleProjectSelect ?? vi.fn()) as (project: any) => void | Promise<void>);
  const [restoreWorkspaceSnapshot] = useState(() => (overrides.restoreWorkspaceSnapshot ?? vi.fn()) as (snapshot: any) => void);
  const [resetChatSession] = useState(() => (overrides.resetChatSession ?? vi.fn()) as () => void);
  const [showToast] = useState(() => (overrides.showToast ?? vi.fn()) as (message: string, type?: string) => void);
  const [buildWorkspaceSnapshot] = useState(() => (overrides.buildWorkspaceSnapshot ?? vi.fn(() => ({ panelConfigs: ['chat', 'graph'] }))) as () => any);

  const controller = useChatController({
    t: (key, vars) => vars ? `${key}:${JSON.stringify(vars)}` : key,
    showToast,
    ignoreUrlSyncRef: { current: false },
    activeSessionId,
    setActiveSessionId,
    chatMessages,
    setChatMessages,
    currentMessage,
    setCurrentMessage,
    isLoading,
    setIsLoading,
    setSessions,
    selectedProject,
    selectedSource,
    setSelectedSource,
    pinnedCode: overrides.pinnedCode ?? null,
    branch: 'main',
    temperature: 0.7,
    systemPrompt: 'system',
    activeProfileId: 'ollama-default',
    llmProfiles: [{ id: 'ollama-default', name: 'Ollama', provider: 'ollama', model: 'qwen' }],
    projects: [selectedProject],
    connectedSources: [{ id: 8, name: 'Docs', type: 'local' }],
    handleProjectSelect,
    restoreWorkspaceSnapshot,
    resetChatSession,
    buildWorkspaceSnapshot,
  });

  return {
    controller,
    activeSessionId,
    chatMessages,
    currentMessage,
    isLoading,
    sessions,
    selectedSource,
    handleProjectSelect,
    restoreWorkspaceSnapshot,
    buildWorkspaceSnapshot,
    showToast,
  };
}

function streamResponse(events: Array<Record<string, any>>) {
  const encoder = new TextEncoder();
  const payload = `${events.map(event => `data: ${JSON.stringify(event)}`).join('\n\n')}\n\n`;
  const chunks: Uint8Array[] = [encoder.encode(payload)];

  return {
    ok: true,
    body: {
      getReader: () => ({
        read: vi.fn(async () => chunks.length > 0
          ? { value: chunks.shift(), done: false }
          : { value: undefined, done: true }),
      }),
    },
  };
}

describe('useChatController', () => {
  beforeEach(() => {
    routerPush.mockReset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('sends a new message and applies the streamed session and answer', async () => {
    const fetchMock = vi.fn().mockResolvedValue(streamResponse([
      { type: 'session', session_id: 42, session_uuid: 'chat-42', session_title: 'Neue Frage' },
      { type: 'content_chunk', content: 'Hallo' },
      { type: 'answer', content: 'Hallo Welt', agent_steps: [] },
      { type: 'message_saved', message_id: 99 },
    ]));
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() => useControllerHarness({ currentMessage: 'Wie geht es weiter?' }));

    await act(async () => {
      await result.current.controller.handleSendChat();
    });

    const request = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(request).toMatchObject({
      message: 'Wie geht es weiter?',
      session_id: null,
      project_id: 11,
      llm_model: 'qwen',
    });
    expect(result.current.activeSessionId).toBe(42);
    expect(result.current.chatMessages).toHaveLength(2);
    expect(result.current.chatMessages[1]).toMatchObject({
      id: 99,
      role: 'assistant',
      content: 'Hallo Welt',
    });
    expect(routerPush).toHaveBeenCalledWith('/workspace?chat=chat-42');
  });

  it('sends the currently focused code object with the chat turn', async () => {
    const fetchMock = vi.fn().mockResolvedValue(streamResponse([
      { type: 'answer', content: 'Erklärung', agent_steps: [] },
    ]));
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() => useControllerHarness({
      currentMessage: 'Was macht das?',
      pinnedCode: {
        filepath: 'copy/BUCHUNGS-REC.cpy',
        line: 23,
        label: 'BUCH-ZINS-LAST',
        sourceId: 1154,
      },
    }));

    await act(async () => {
      await result.current.controller.handleSendChat();
    });

    const request = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(request).toMatchObject({
      pinned_file: 'copy/BUCHUNGS-REC.cpy',
      pinned_line: 23,
      pinned_label: 'BUCH-ZINS-LAST',
      pinned_source_id: 1154,
    });
    expect(request.metadata.refs[0]).toMatchObject({
      file: 'copy/BUCHUNGS-REC.cpy',
      line: 23,
      label: 'BUCH-ZINS-LAST',
    });
  });

  it('retries an existing assistant message with its original user metadata', async () => {
    const fetchMock = vi.fn().mockResolvedValue(streamResponse([
      { type: 'answer', content: 'Neue Antwort', agent_steps: [] },
      { type: 'message_saved', message_id: 101 },
    ]));
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() => useControllerHarness({
      activeSessionId: 7,
      selectedProject: { id: 99, name: 'Current project' },
      selectedSource: { id: 77, name: 'Current source' },
      pinnedCode: { filepath: 'current.cbl', line: 4, context: 'Current focus', sourceId: 77 },
      chatMessages: [
        {
          id: 10,
          role: 'user',
          content: 'Erkläre das',
          metadata: {
            project: { id: 11, name: 'Original project' },
            source: { id: 8, name: 'Original source' },
            focus: {
              project: { id: 11, name: 'Original project' },
              source: { id: 8, name: 'Original source' },
              pinned: {
                filepath: 'main.cbl',
                line: 42,
                context: 'Original focus',
                sourceId: 8,
              },
            },
            refs: [{ file: 'main.cbl', line: 42 }],
          },
        },
        { id: 20, role: 'assistant', content: 'Alte Antwort' },
      ],
    }));

    await act(async () => {
      await result.current.controller.handleRetryMessage(1);
    });

    const request = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(request).toMatchObject({
      message: 'Erkläre das',
      session_id: 7,
      project_id: 11,
      source_id: 8,
      pinned_file: 'main.cbl',
      pinned_line: 42,
      pinned_context: 'Original focus',
      metadata: { refs: [{ file: 'main.cbl' }] },
      retry_of_message_id: 20,
    });
    expect(result.current.chatMessages[1]).toMatchObject({
      id: 101,
      content: 'Neue Antwort',
    });
  });

  it('loads a session, restores its workspace and normalizes its first message', async () => {
    vi.spyOn(api, 'getChatMessages').mockResolvedValue({
      data: [
        { id: 1, role: 'user', content: '0 Wer bist du ?', metadata_json: { refs: [] } },
        { id: 2, role: 'assistant', content: 'Ich bin Doctus.', sources_json: [] },
      ],
    } as any);
    const handleProjectSelect = vi.fn();
    const restoreWorkspaceSnapshot = vi.fn();
    const { result } = renderHook(() => useControllerHarness({
      handleProjectSelect,
      restoreWorkspaceSnapshot,
    }));
    const session = {
      id: 7,
      uuid: 'chat-7',
      title: 'Historie',
      project_id: 11,
      source_id: 8,
      snapshot_json: { selectedProjectId: 11, selectedSourceId: 8 },
    };

    await act(async () => {
      await result.current.controller.handleSessionSelect(session);
    });

    expect(result.current.activeSessionId).toBe(7);
    expect(result.current.chatMessages[0].content).toBe('Wer bist du ?');
    expect(result.current.chatMessages[1].content).toBe('Ich bin Doctus.');
    expect(result.current.selectedSource).toMatchObject({ id: 8, name: 'Docs' });
    expect(restoreWorkspaceSnapshot).toHaveBeenCalledWith(session.snapshot_json);
    expect(routerPush).toHaveBeenCalledWith('/workspace?chat=chat-7');
  });

  // O-038: eine Sitzung ohne Chat-Nachricht anlegen (Speicher-Icon in der
  // Header-Bar, sichtbar bei leerem Chat + zweiter offener View).
  describe('handleSaveSessionWithoutChat', () => {
    it('creates a session via the API, saves its snapshot immediately, activates it, and lists it', async () => {
      const newSession = { id: 55, uuid: 'chat-55', title: 'Graph-Befund', project_id: 11, source_id: null };
      vi.spyOn(api, 'createChatSession').mockResolvedValue({ data: newSession } as any);
      const updateSnapshotSpy = vi.spyOn(api, 'updateChatSessionSnapshot').mockResolvedValue({} as any);
      const { result } = renderHook(() => useControllerHarness());

      await act(async () => {
        await result.current.controller.handleSaveSessionWithoutChat('  Graph-Befund  ');
      });

      expect(api.createChatSession).toHaveBeenCalledWith({
        title: 'Graph-Befund',
        project_id: 11,
        source_id: null,
      });
      // The snapshot is saved right away instead of waiting for the debounced
      // autosave (useWorkspaceLayout.ts) -- clicking straight back into this
      // session in the sidebar must not find an empty snapshot_json.
      expect(updateSnapshotSpy).toHaveBeenCalledWith(55, { panelConfigs: ['chat', 'graph'] });
      expect(result.current.activeSessionId).toBe(55);
      expect(result.current.sessions).toEqual([{ ...newSession, snapshot_json: { panelConfigs: ['chat', 'graph'] } }]);
      expect(routerPush).toHaveBeenCalledWith('/workspace?chat=chat-55');
    });

    it('does nothing for a blank title -- no API call, no session created', async () => {
      const createSpy = vi.spyOn(api, 'createChatSession');
      const { result } = renderHook(() => useControllerHarness());

      await act(async () => {
        await result.current.controller.handleSaveSessionWithoutChat('   ');
      });

      expect(createSpy).not.toHaveBeenCalled();
      expect(result.current.activeSessionId).toBeNull();
      expect(result.current.sessions).toEqual([]);
    });

    it('shows an error toast and leaves state untouched when the API call fails', async () => {
      vi.spyOn(api, 'createChatSession').mockRejectedValue(new Error('network down'));
      const { result } = renderHook(() => useControllerHarness());

      await act(async () => {
        await result.current.controller.handleSaveSessionWithoutChat('Graph-Befund');
      });

      expect(result.current.showToast).toHaveBeenCalledWith('page.toast.sessionSaveFailed', 'error');
      expect(result.current.activeSessionId).toBeNull();
      expect(result.current.sessions).toEqual([]);
    });
  });

  // O-038 Folgefix: erneutes Klicken auf das Speicher-Icon, während schon eine
  // chat-lose Sitzung aktiv ist, darf keine zweite Sitzung anlegen -- nur die
  // bestehende updaten.
  describe('handleUpdateSessionSnapshot', () => {
    it('saves the current snapshot into the already-active session, without creating a new one', async () => {
      const createSpy = vi.spyOn(api, 'createChatSession');
      const updateSnapshotSpy = vi.spyOn(api, 'updateChatSessionSnapshot').mockResolvedValue({} as any);
      const { result } = renderHook(() => useControllerHarness({
        activeSessionId: 55,
        buildWorkspaceSnapshot: () => ({ panelConfigs: ['chat', 'graph', 'code'] }),
      }));

      await act(async () => {
        await result.current.controller.handleUpdateSessionSnapshot();
      });

      expect(createSpy).not.toHaveBeenCalled();
      expect(updateSnapshotSpy).toHaveBeenCalledWith(55, { panelConfigs: ['chat', 'graph', 'code'] });
      expect(result.current.showToast).toHaveBeenCalledWith('page.toast.sessionUpdated', 'success');
    });

    it('updates the matching cached session entry with the newly saved snapshot', async () => {
      vi.spyOn(api, 'updateChatSessionSnapshot').mockResolvedValue({} as any);
      const { result } = renderHook(() => useControllerHarness({
        activeSessionId: 55,
        sessions: [{ id: 55, title: 'Graph-Befund', snapshot_json: { panelConfigs: ['chat', 'graph'] } }, { id: 9, title: 'Andere Sitzung' }],
        buildWorkspaceSnapshot: () => ({ panelConfigs: ['graph', 'code'] }),
      }));

      await act(async () => {
        await result.current.controller.handleUpdateSessionSnapshot();
      });

      expect(result.current.sessions).toEqual([
        { id: 55, title: 'Graph-Befund', snapshot_json: { panelConfigs: ['graph', 'code'] } },
        { id: 9, title: 'Andere Sitzung' },
      ]);
    });

    it('does nothing when there is no active session', async () => {
      const updateSnapshotSpy = vi.spyOn(api, 'updateChatSessionSnapshot');
      const { result } = renderHook(() => useControllerHarness({ activeSessionId: null }));

      await act(async () => {
        await result.current.controller.handleUpdateSessionSnapshot();
      });

      expect(updateSnapshotSpy).not.toHaveBeenCalled();
    });

    it('shows an error toast when the update fails', async () => {
      vi.spyOn(api, 'updateChatSessionSnapshot').mockRejectedValue(new Error('network down'));
      const { result } = renderHook(() => useControllerHarness({ activeSessionId: 55 }));

      await act(async () => {
        await result.current.controller.handleUpdateSessionSnapshot();
      });

      expect(result.current.showToast).toHaveBeenCalledWith('page.toast.sessionSaveFailed', 'error');
    });
  });
});
