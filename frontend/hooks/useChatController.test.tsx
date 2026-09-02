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
};

function useControllerHarness(overrides: HarnessOverrides = {}) {
  const [activeSessionId, setActiveSessionId] = useState<number | null>(overrides.activeSessionId ?? null);
  const [chatMessages, setChatMessages] = useState<any[]>(overrides.chatMessages ?? []);
  const [currentMessage, setCurrentMessage] = useState(overrides.currentMessage ?? '');
  const [isLoading, setIsLoading] = useState(overrides.isLoading ?? false);
  const [sessions, setSessions] = useState<any[]>([]);
  const [selectedSource, setSelectedSource] = useState<any | null>(overrides.selectedSource ?? null);
  const selectedProject = overrides.selectedProject ?? { id: 11, name: 'Demo' };
  const handleProjectSelect = (overrides.handleProjectSelect ?? vi.fn()) as (project: any) => void | Promise<void>;
  const restoreWorkspaceSnapshot = (overrides.restoreWorkspaceSnapshot ?? vi.fn()) as (snapshot: any) => void;
  const resetChatSession = (overrides.resetChatSession ?? vi.fn()) as () => void;

  const controller = useChatController({
    t: (key, vars) => vars ? `${key}:${JSON.stringify(vars)}` : key,
    showToast: vi.fn(),
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
});
