import { extractTraceId } from '@/lib/traceId';
import type { ShowToast } from '@/components/Toast';
import { api } from '@/app/services/api';
import { DEFAULT_EMBEDDING_MODEL, type LlmProfile } from '@/hooks/useAiSettings';
import type { ChatPinnedFocus } from '@/lib/chatFocus';
import {
  chatFocusRequestFields,
  createChatMetadata,
  createChatTurnFocus,
  getChatTurnFocus,
} from '@/lib/chatFocus';
import { fromStoredMessages, normalizeInitialUserMessage } from '@/lib/chatMessage';
import { parseChatStreamEvent } from '@/lib/chatStream';
import { withCompaction, withReasoningChunk } from '@/lib/chatSteps';
import { viewActionMatchesResult } from '@/lib/chatViewActionCheck';
import { extractCallFlowData } from '@/lib/callFlow';
import type { CallFlowData } from '@/lib/callFlow';
import { copyToClipboard } from '@/lib/utils';
import { lockedChatMode } from '@/lib/chatMode';
import type { AgentStep, AgentViewAction, AgentViewActionStatus, ChatMessage, ChatMetadata, ChatRequest, ChatSession, KnowledgeSource, Project, WorkspaceSnapshot } from '@/types/domain';
import { usePathname, useRouter } from 'next/navigation';
import type { Dispatch, MutableRefObject, SetStateAction } from 'react';
import { useCallback, useLayoutEffect, useRef, useState } from 'react';

/** Nachrichten je Seite beim Öffnen und Nachladen einer Sitzung. */
const MESSAGE_PAGE_SIZE = 40;

type Translator = (key: string, vars?: Record<string, string | number>) => string;
type Toast = ShowToast;
type ViewActionOutcome = Exclude<AgentViewActionStatus, 'requested'>;

interface ChatControllerOptions {
  t: Translator;
  showToast: Toast;
  ignoreUrlSyncRef: MutableRefObject<boolean>;
  activeSessionId: number | null;
  setActiveSessionId: Dispatch<SetStateAction<number | null>>;
  chatMessages: ChatMessage[];
  setChatMessages: Dispatch<SetStateAction<ChatMessage[]>>;
  currentMessage: string;
  setCurrentMessage: Dispatch<SetStateAction<string>>;
  isLoading: boolean;
  setIsLoading: Dispatch<SetStateAction<boolean>>;
  setSessions: Dispatch<SetStateAction<ChatSession[]>>;
  selectedProject: Project | null;
  selectedSource: KnowledgeSource | null;
  setSelectedSource: Dispatch<SetStateAction<KnowledgeSource | null>>;
  pinnedCode: ChatPinnedFocus | null;
  branch: string;
  temperature?: number;
  systemPrompt: string;
  chatMode?: 'normal' | 'evidence';
  activeProfileId: string;
  activeEmbeddingModel?: string;
  llmProfiles: LlmProfile[];
  projects: Project[];
  connectedSources: KnowledgeSource[];
  handleProjectSelect: (project: Project | null) => void | Promise<void>;
  restoreWorkspaceSnapshot: (snapshot: WorkspaceSnapshot) => void;
  resetChatSession: () => void;
  buildWorkspaceSnapshot: () => WorkspaceSnapshot;
}

export function useChatController({
  t,
  showToast,
  ignoreUrlSyncRef,
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
  pinnedCode,
  branch,
  temperature,
  systemPrompt,
  chatMode = 'evidence',
  activeProfileId,
  activeEmbeddingModel,
  llmProfiles,
  projects,
  connectedSources,
  handleProjectSelect,
  restoreWorkspaceSnapshot,
  resetChatSession,
  buildWorkspaceSnapshot,
}: ChatControllerOptions) {
  const router = useRouter();
  const pathname = usePathname();
  const activeSessionIdRef = useRef(activeSessionId);
  const chatMessagesRef = useRef(chatMessages);
  const activeSessionEpochRef = useRef(0);
  const chatGenerationRef = useRef(0);
  const streamAbortRef = useRef<AbortController | null>(null);
  // Der Nutzer hat die laufende Antwort selbst gestoppt (Knopf oder Esc), sie ist also kein Fehler.
  const userStopRef = useRef(false);
  /** Entwertet und beendet einen laufenden Chat-Stream (neuer Chat, andere Sitzung, Projektwechsel). */
  const [olderPages, setOlderPages] = useState({ hasMore: false, loading: false });
  const invalidateChat = useCallback(() => {
    chatGenerationRef.current += 1;
    streamAbortRef.current?.abort();
    streamAbortRef.current = null;
    setIsLoading(false);
    setOlderPages({ hasMore: false, loading: false });
  }, [setIsLoading]);
  useLayoutEffect(() => {
    if (activeSessionIdRef.current !== activeSessionId) {
      activeSessionIdRef.current = activeSessionId;
      activeSessionEpochRef.current += 1;
    }
  }, [activeSessionId]);
  const handledViewActionIdsRef = useRef(new Set<string>());
  const viewActionOutcomesRef = useRef(new Map<string, ViewActionOutcome>());
  const persistedViewActionOutcomesRef = useRef(new Set<string>());

  const persistViewActionOutcome = useCallback((messageId: number, actionId: string, status: ViewActionOutcome) => {
    const key = `${messageId}:${actionId}:${status}`;
    if (persistedViewActionOutcomesRef.current.has(key)) return;
    persistedViewActionOutcomesRef.current.add(key);
    void api.updateChatMessageViewAction(messageId, actionId, status).catch((error) => {
      persistedViewActionOutcomesRef.current.delete(key);
      console.warn('Failed to persist agent view action outcome:', error);
    });
  }, []);

  useLayoutEffect(() => {
    chatMessagesRef.current = chatMessages;
    for (const message of chatMessages) {
      if (message.role !== 'assistant' || message.id == null || !message.metadata?.agent_steps) continue;
      for (const step of message.metadata.agent_steps) {
        if (step.type !== 'view_action') continue;
        const status = viewActionOutcomesRef.current.get(step.action_id);
        if (status) persistViewActionOutcome(message.id, step.action_id, status);
      }
    }
  }, [chatMessages, persistViewActionOutcome]);

  const recordAgentViewActionOutcome = useCallback((actionId: string, status: ViewActionOutcome) => {
    viewActionOutcomesRef.current.set(actionId, status);
    let messageId: number | undefined;
    setChatMessages(previous => previous.map(message => {
      if (message.role !== 'assistant' || !message.metadata?.agent_steps) return message;
      let found = false;
      const agentSteps = message.metadata.agent_steps.map(step => {
        if (step.type === 'view_action' && step.action_id === actionId) {
          found = true;
          return { ...step, status };
        }
        return step;
      });
      if (!found) return message;
      if (message.id != null) messageId = message.id;
      return { ...message, metadata: { ...message.metadata, agent_steps: agentSteps } };
    }));
    const storedMessage = chatMessagesRef.current.find(message =>
      message.role === 'assistant' && message.metadata?.agent_steps?.some(step =>
        step.type === 'view_action' && step.action_id === actionId,
      ),
    );
    if (messageId ?? storedMessage?.id) {
      persistViewActionOutcome(messageId ?? storedMessage!.id!, actionId, status);
    }
  }, [persistViewActionOutcome, setChatMessages]);

  const handleShareChat = useCallback(async () => {
    if (!activeSessionId) {
      showToast(t('chatView.startChatFirstToast'), 'error');
      return;
    }

    // Sitzung muss explizit freigegeben werden (is_public), bevor der Link für
    // andere Nutzer etwas nützt — der by-uuid-Zugriff prüft das serverseitig (O-032).
    try {
      await api.shareChatSession(activeSessionId);
    } catch (error) {
      console.error('Failed to mark chat session as shared:', error);
      showToast(t('chatView.copyFailedToast'), 'error', error);
      return;
    }

    const success = await copyToClipboard(window.location.href);
    showToast(
      success ? t('chatView.linkCopiedToast') : t('chatView.copyFailedToast'),
      success ? 'success' : 'error'
    );
  }, [activeSessionId, showToast, t]);

  // O-038: legt eine benannte Sitzung an, ohne dass je eine Chat-Nachricht
  // geschrieben wurde -- z.B. ein Befund, der nur über mehrere Views (Graph +
  // Code) entsteht. Der Snapshot wird hier sofort mitgespeichert (statt nur
  // auf den debounced Autosave in useWorkspaceLayout.ts zu warten): klickt der
  // Nutzer direkt danach dieselbe Sitzung in der Sidebar an, wäre sonst in dem
  // ~1,2s-Fenster noch kein Snapshot vorhanden und die Panels blieben leer.
  const handleSaveSessionWithoutChat = useCallback(async (title: string) => {
    const trimmedTitle = title.trim();
    if (!trimmedTitle) return;
    try {
      const res = await api.createChatSession({
        title: trimmedTitle,
        project_id: selectedProject?.id ?? null,
        source_id: selectedSource?.id ?? null,
      });
      const newSession = res.data;
      const snapshot = buildWorkspaceSnapshot();
      await api.updateChatSessionSnapshot(newSession.id, snapshot);
      setSessions(prev => [{ ...newSession, snapshot_json: snapshot }, ...prev]);
      ignoreUrlSyncRef.current = true;
      setActiveSessionId(newSession.id);
      if (newSession.uuid) {
        const params = new URLSearchParams(window.location.search);
        params.set('chat', newSession.uuid);
        router.push(`${pathname}?${params.toString()}`);
      }
      showToast(t('page.toast.sessionSaved', { title: trimmedTitle }), 'success');
    } catch (error) {
      console.error('Failed to save session without a chat message:', error);
      showToast(t('page.toast.sessionSaveFailed'), 'error', error);
    }
  }, [buildWorkspaceSnapshot, ignoreUrlSyncRef, pathname, router, selectedProject, selectedSource, setActiveSessionId, setSessions, showToast, t]);

  // O-038 Folgefix: ein zweites Mal auf das Speicher-Icon zu klicken, während
  // bereits eine chat-lose Sitzung aktiv ist (activeSessionId gesetzt,
  // chatMessages leer -- die einzige Bedingung, unter der der Button
  // überhaupt sichtbar ist), darf KEINE zweite Sitzung anlegen. Stattdessen
  // wird der aktuelle Stand sofort in die bestehende Sitzung geschrieben,
  // ohne erneut nach einem Namen zu fragen.
  const handleUpdateSessionSnapshot = useCallback(async () => {
    if (!activeSessionId) return;
    try {
      const snapshot = buildWorkspaceSnapshot();
      await api.updateChatSessionSnapshot(activeSessionId, snapshot);
      setSessions(prev => prev.map(session =>
        session.id === activeSessionId ? { ...session, snapshot_json: snapshot } : session
      ));
      showToast(t('page.toast.sessionUpdated'), 'success');
    } catch (error) {
      console.error('Failed to update session snapshot:', error);
      showToast(t('page.toast.sessionSaveFailed'), 'error', error);
    }
  }, [activeSessionId, buildWorkspaceSnapshot, setSessions, showToast, t]);

  // Shared SSE consumer for both a fresh send and a retry/regenerate. The
  // caller prepares the target assistant slot; this function only consumes the
  // stream and applies events to that slot. `previous` ist die Antwort, die eine Wiederholung ersetzen soll: Scheitert die Wiederholung, bleibt sie auf dem
  // Server stehen und kommt deshalb auch hier zurück.
  const runChatStream = useCallback(async (requestBody: ChatRequest, targetIndex: number, previous?: ChatMessage) => {
    let expectedSessionId = requestBody.session_id;
    let expectedSessionEpoch = activeSessionEpochRef.current;
    // Gehört dieser Stream noch zum aktuellen Chat? Ein neuer Chat, eine andere Sitzung oder ein
    // Projektwechsel entwertet ihn; danach schreibt er nichts mehr (die Antwortstelle `targetIndex`
    // gibt es im neuen Chat womöglich wieder).
    const generation = chatGenerationRef.current;
    const isCurrent = () => generation === chatGenerationRef.current;
    let accumulatedSteps: AgentStep[] = [];
    let saved = false;
    const updateTarget = (patch: (target: ChatMessage) => ChatMessage) => {
      if (!isCurrent()) return;
      setChatMessages(prev => {
        const target = prev[targetIndex];
        if (!target || target.role !== 'assistant') return prev;
        const next = [...prev];
        next[targetIndex] = patch(target);
        return next;
      });
    };
    const showSteps = (target: ChatMessage): ChatMessage => ({ ...target, metadata: { ...target.metadata, agent_steps: accumulatedSteps } });
    const failTurn = (text: string, cause: unknown, keepPartial = false) => {
      updateTarget(target => previous ?? { ...target, content: keepPartial && target.content ? `${target.content}\n\n${text}` : text });
      if (isCurrent()) showToast(t('page.toast.aiQueryFailed'), 'error', cause);
    };
    const markStopped = () => {
      const note = t('chatView.answerStopped');
      updateTarget(target => previous ?? { ...target, content: target.content ? `${target.content}\n\n_${note}_` : note });
    };
    const abort = new AbortController();
    streamAbortRef.current = abort;
    userStopRef.current = false;
    try {
      const response = await api.fetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody),
        signal: abort.signal,
      });

      if (!response.ok) {
        // O-073: die Trace-ID haengt an der Antwort, nicht am Error -- ohne
        // dieses Mitgeben waere sie hier verloren, und ausgerechnet der Chat
        // ist der Weg, ueber den Nutzer Fehler am ehesten melden.
        const httpError = new Error(t('page.error.httpError', { status: response.status })) as Error & { traceId?: string | null };
        httpError.traceId = extractTraceId(response);
        throw httpError;
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      if (!reader) {
        throw new Error(t('page.error.streamReaderInit'));
      }

      let buffer = '';
      let currentThought = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        let boundary = buffer.indexOf('\n\n');

        while (boundary !== -1) {
          const message = buffer.substring(0, boundary).trim();
          buffer = buffer.substring(boundary + 2);

          if (message.startsWith('data: ')) {
            const jsonStr = message.substring(6);
            try {
              const data = parseChatStreamEvent(jsonStr);
              if (!data) {
                boundary = buffer.indexOf('\n\n');
                continue;
              }

              if (data.type === 'session') {
                const userMessageId = data.user_message_id;
                if (userMessageId != null && isCurrent()) {
                  setChatMessages(prev => prev.map((message, index) => (
                    index === targetIndex - 1 && message.role === 'user' ? { ...message, id: userMessageId } : message
                  )));
                }
                const newSessionId = data.session_id;
                const newSessionUuid = data.session_uuid;

                if (requestBody.session_id == null && newSessionId) {
                  const shouldActivateSession = isCurrent() && activeSessionIdRef.current == null &&
                    activeSessionEpochRef.current === expectedSessionEpoch;
                  expectedSessionId = newSessionId;
                  if (shouldActivateSession) {
                    activeSessionIdRef.current = newSessionId;
                    activeSessionEpochRef.current += 1;
                    expectedSessionEpoch = activeSessionEpochRef.current;
                    ignoreUrlSyncRef.current = true;
                    setActiveSessionId(newSessionId);
                  }
                  const requestFocus = requestBody.metadata?.focus;
                  const newSession = {
                    id: newSessionId,
                    uuid: newSessionUuid,
                    title: data.session_title || (requestBody.message.length > 28 ? requestBody.message.substring(0, 25) + '...' : requestBody.message),
                    project_id: requestBody.project_id ?? null,
                    project: requestFocus?.project?.id != null ? { id: Number(requestFocus.project.id), name: requestFocus.project.name || '' } : selectedProject,
                    source_id: requestBody.source_id ?? null,
                    source: requestFocus?.source?.id != null ? { id: requestFocus.source.id, name: requestFocus.source.name || '' } : selectedSource,
                  };
                  setSessions(prev => prev.some(session => session.id === newSessionId) ? prev : [newSession, ...prev]);

                  if (shouldActivateSession && newSessionUuid) {
                    const params = new URLSearchParams(window.location.search);
                    params.set('chat', newSessionUuid);
                    router.push(`${pathname}?${params.toString()}`);
                  }
                }
              } else if (data.type === 'sources') {
                updateTarget(target => ({ ...target, sources: data.sources }));
              } else if (data.type === 'content_chunk') {
                currentThought += data.content;
                updateTarget(target => ({ ...target, content: target.content + data.content }));
              } else if (data.type === 'content_reset') {
                currentThought = '';
                updateTarget(target => ({ ...target, content: '' }));
              } else if (data.type === 'tool_call') {
                const newSteps = [...accumulatedSteps];
                if (currentThought.trim()) {
                  newSteps.push({ type: 'thought', content: currentThought });
                  currentThought = '';
                }
                newSteps.push({
                  type: 'tool_call',
                  name: data.name,
                  arguments: data.arguments,
                  id: data.id
                });
                accumulatedSteps = newSteps;
                updateTarget(target => ({ ...showSteps(target), content: '' }));
              } else if (data.type === 'tool_result' || data.type === 'context_trimmed') {
                accumulatedSteps = [...accumulatedSteps, data];
                updateTarget(showSteps);
              } else if (data.type === 'reasoning_chunk' || data.type === 'history_compacted') {
                accumulatedSteps = data.type === 'reasoning_chunk'
                  ? withReasoningChunk(accumulatedSteps, data.turn, data.content)
                  : withCompaction(accumulatedSteps, data);
                updateTarget(showSteps);
              } else if (data.type === 'view_action') {
                if (handledViewActionIdsRef.current.has(data.action_id)) {
                  boundary = buffer.indexOf('\n\n');
                  continue;
                }
                handledViewActionIdsRef.current.add(data.action_id);

                let status: ViewActionOutcome = 'rejected';
                const requestProjectId = requestBody.project_id == null ? null : Number(requestBody.project_id);
                const isCurrentTurn = activeSessionIdRef.current === data.session_id &&
                  expectedSessionId === data.session_id &&
                  activeSessionEpochRef.current === expectedSessionEpoch &&
                  requestProjectId === data.project_id;

                if (!isCurrentTurn) {
                  status = 'stale_context';
                } else if (!viewActionMatchesResult(data, accumulatedSteps)) {
                  status = 'rejected';
                } else {
                  // Agent views are proposals. Opening only happens after an explicit click in ChatView.
                  status = 'manual';
                }

                const recordedAction: AgentViewAction = { ...data, status };
                viewActionOutcomesRef.current.set(data.action_id, status);
                accumulatedSteps = [...accumulatedSteps, recordedAction];
                if (activeSessionIdRef.current === data.session_id) updateTarget(showSteps);
              } else if (data.type === 'turn_completed') {
                if (data.has_tool_calls) {
                  currentThought = '';
                }
              } else if (data.type === 'answer') {
                const finalSteps = [...(data.agent_steps || accumulatedSteps)];
                for (const action of accumulatedSteps.filter((step): step is AgentViewAction => step.type === 'view_action')) {
                  const existingIndex = finalSteps.findIndex(step => step.type === 'view_action' && step.action_id === action.action_id);
                  if (existingIndex === -1) finalSteps.push(action);
                  else finalSteps[existingIndex] = action;
                }
                accumulatedSteps = finalSteps;
                updateTarget(target => ({ ...showSteps(target), content: data.content }));
              } else if (data.type === 'message_saved') {
                saved = true;
                const actionsToPersist = accumulatedSteps.filter((step): step is AgentViewAction => step.type === 'view_action')
                  .map(action => ({
                    ...action,
                    status: viewActionOutcomesRef.current.get(action.action_id) ?? action.status,
                  }));
                updateTarget(target => {
                  const agentSteps = target.metadata?.agent_steps?.map(step => {
                    const action = actionsToPersist.find(candidate =>
                      candidate.action_id === (step.type === 'view_action' ? step.action_id : undefined),
                    );
                    return action ?? step;
                  });
                  return {
                    ...target,
                    id: data.message_id,
                    metadata: agentSteps ? { ...target.metadata, agent_steps: agentSteps } : target.metadata,
                  };
                });
                for (const action of actionsToPersist) {
                  if (action.status !== 'requested') {
                    persistViewActionOutcome(data.message_id, action.action_id, action.status);
                  }
                }
              } else if (data.type === 'telemetry' && data.event === 'completed' && data.metrics) {
                const telemetryMetrics = data.metrics;
                updateTarget(target => ({ ...target, metadata: { ...target.metadata, telemetry: { events: [], metrics: telemetryMetrics } } }));
              } else if (data.type === 'error') {
                // Serverseitiger Fehler mitten im Stream: die Antwort selbst
                // traegt die Trace-ID des Requests (O-073).
                failTurn(t('page.error.chatFetchFailedWithMessage', { message: data.error }), response);
                return;
              }
            } catch (error) {
              console.error('Failed to process stream chunk', error, jsonStr);
            }
          }
          boundary = buffer.indexOf('\n\n');
        }
      }
      // Ohne „message_saved“ ist die Runde nicht abgeschlossen (Verbindung weg, Server neu gestartet); stumm
      // stehen bleiben darf sie nicht.
      if (!saved && userStopRef.current) markStopped();
      else if (!saved) failTurn(t('page.error.streamInterrupted'), response, true);
    } catch (error) {
      // Abgebrochen, weil der Chat gewechselt hat: kein Fehler für den Nutzer.
      if (!isCurrent()) return;
      if (userStopRef.current) {
        markStopped();
        return;
      }
      console.error(error);
      failTurn(error instanceof Error && error.message
        ? t('page.error.chatFetchFailedWithMessage', { message: error.message })
        : t('page.error.chatFetchFailed'), error);
    } finally {
      if (streamAbortRef.current === abort) streamAbortRef.current = null;
      if (isCurrent()) setIsLoading(false);
    }
  }, [ignoreUrlSyncRef, pathname, persistViewActionOutcome, router, selectedProject, selectedSource, setActiveSessionId, setChatMessages, setIsLoading, setSessions, showToast, t]);

  const handleSendChat = useCallback(async (overrideMsg?: string, extraMetadata?: ChatMetadata) => {
    const isFirstUserMessage = !chatMessages.some((message) => message.role === 'user');
    // Ein laufender Chat behält den Modus seiner ersten Nachricht, auch wenn die Auswahl inzwischen anders steht.
    const sessionMode = lockedChatMode(chatMessages) ?? chatMode;
    const msgToSend = normalizeInitialUserMessage(
      (overrideMsg || currentMessage).trim(),
      isFirstUserMessage
    ).trim();
    if (!msgToSend || isLoading) return;

    const userMsgContent = msgToSend;
    const turnFocus = createChatTurnFocus(selectedProject, selectedSource, pinnedCode);
    const newUserMsg: ChatMessage = {
      role: 'user',
      content: userMsgContent,
      metadata: { ...createChatMetadata(turnFocus, extraMetadata), chat_mode: sessionMode },
    };

    const activeProfile = llmProfiles.find(p => p.id === activeProfileId);
    const assistantPlaceholder: ChatMessage = {
      role: 'assistant',
      content: '',
      sources: [],
      metadata: {
        model: activeProfile?.name || activeProfile?.model || t('page.defaultModelFallback'),
        provider: activeProfile?.provider,
        chat_mode: sessionMode,
        agent_steps: []
      }
    };

    const targetIndex = chatMessages.length + 1;
    setChatMessages(prev => [...prev, newUserMsg, assistantPlaceholder]);
    setCurrentMessage('');
    setIsLoading(true);
    const textareaEl = document.getElementById('chat-textarea') as HTMLTextAreaElement | null;
    if (textareaEl) textareaEl.style.height = 'auto';

    await runChatStream({
      message: userMsgContent,
      mode: sessionMode,
      session_id: activeSessionId,
      ...chatFocusRequestFields(turnFocus),
      branch,
      temperature,
      system_prompt: systemPrompt,
      llm_provider: activeProfile?.provider || 'ollama',
      llm_model: activeProfile?.model || undefined,
      llm_profile_id: activeProfile?.id ? Number(activeProfile.id) : undefined,
      embedding_model: activeEmbeddingModel || DEFAULT_EMBEDDING_MODEL,
      metadata: newUserMsg.metadata || {}
    }, targetIndex);
  }, [activeEmbeddingModel, activeProfileId, activeSessionId, branch, chatMessages, chatMode, currentMessage, isLoading, llmProfiles, pinnedCode, runChatStream, selectedProject, selectedSource, setChatMessages, setCurrentMessage, setIsLoading, systemPrompt, temperature, t]);

  // Neue Antwort auf eine vorhandene Frage: Wiederholen ersetzt die Antwort, Bearbeiten zusätzlich die Frage.
  const rerunTurn = useCallback(async (
    userIndex: number, userMsg: ChatMessage, extra: Pick<ChatRequest, 'retry_of_message_id' | 'edit_of_message_id'>,
    previous?: ChatMessage,
  ) => {
    const activeProfile = llmProfiles.find(p => p.id === activeProfileId);
    const mode = userMsg.metadata?.chat_mode === 'normal' ? 'normal' : 'evidence';
    const placeholder: ChatMessage = {
      role: 'assistant',
      content: '',
      sources: [],
      metadata: {
        model: activeProfile?.name || activeProfile?.model || t('page.defaultModelFallback'),
        provider: activeProfile?.provider,
        chat_mode: mode,
        agent_steps: []
      }
    };
    // Beim Bearbeiten fällt alles nach der Frage weg; beim Wiederholen bleibt der übrige Verlauf stehen.
    setChatMessages(prev => extra.edit_of_message_id
      ? [...prev.slice(0, userIndex), userMsg, placeholder]
      : prev.map((message, index) => (index === userIndex + 1 ? placeholder : message)));
    setIsLoading(true);
    const turnFocus = getChatTurnFocus(userMsg);
    await runChatStream({
      message: userMsg.content,
      mode,
      session_id: activeSessionId,
      ...chatFocusRequestFields(turnFocus),
      branch,
      temperature,
      system_prompt: systemPrompt,
      llm_provider: activeProfile?.provider || 'ollama',
      llm_model: activeProfile?.model || undefined,
      llm_profile_id: activeProfile?.id ? Number(activeProfile.id) : undefined,
      embedding_model: activeEmbeddingModel || DEFAULT_EMBEDDING_MODEL,
      metadata: createChatMetadata(turnFocus, userMsg.metadata),
      ...extra,
    }, userIndex + 1, previous);
  }, [activeEmbeddingModel, activeProfileId, activeSessionId, branch, llmProfiles, runChatStream, setChatMessages, setIsLoading, systemPrompt, t, temperature]);

  const handleRetryMessage = useCallback(async (index: number) => {
    if (isLoading) return;
    const assistantMsg = chatMessages[index];
    const userMsg = chatMessages[index - 1];
    if (!assistantMsg || assistantMsg.role !== 'assistant' || !assistantMsg.id) return;
    if (!userMsg || userMsg.role !== 'user') return;
    await rerunTurn(index - 1, userMsg, { retry_of_message_id: assistantMsg.id }, assistantMsg);
  }, [chatMessages, isLoading, rerunTurn]);

  /** Ersetzt den Text der letzten Frage und beantwortet sie neu; false, wenn das nicht geht. */
  const editLastQuestion = useCallback(async (text: string) => {
    const content = text.trim();
    const userIndex = chatMessages.map(message => message.role).lastIndexOf('user');
    const userMsg = chatMessages[userIndex];
    if (isLoading || !content || !userMsg?.id) return false;
    setCurrentMessage('');
    await rerunTurn(userIndex, { ...userMsg, content, metadata: { ...userMsg.metadata, edited: true } }, { edit_of_message_id: userMsg.id });
    return true;
  }, [chatMessages, isLoading, rerunTurn, setCurrentMessage]);

  const stopAnswer = useCallback(() => {
    if (!streamAbortRef.current) return;
    userStopRef.current = true;
    streamAbortRef.current.abort();
  }, []);

  const handleSessionSelect = useCallback(async (session: ChatSession) => {
    invalidateChat();
    ignoreUrlSyncRef.current = true;
    setActiveSessionId(session.id);

    if (session.uuid) {
      const params = new URLSearchParams(window.location.search);
      params.set('chat', session.uuid);
      router.push(`${pathname}?${params.toString()}`);
    }

    if (session.project) {
      const matchedProject = projects && projects.find((p) => p.id === session.project?.id);
      handleProjectSelect(matchedProject || session.project);
    } else if (session.project_id && projects && projects.length > 0) {
      const matchedProject = projects.find((p) => p.id === session.project_id);
      if (matchedProject) {
        handleProjectSelect(matchedProject);
      }
    }

    if (session.source) {
      setSelectedSource(session.source);
    } else if (session.source_id && connectedSources && connectedSources.length > 0) {
      const matchedSource = connectedSources.find((s) => s.id === session.source_id);
      if (matchedSource) {
        setSelectedSource(matchedSource);
      } else {
        setSelectedSource(null);
      }
    } else {
      setSelectedSource(null);
    }

    const snap = session.snapshot_json;
    if (snap) {
      if (!session.project && !session.project_id && snap.selectedProjectId && projects && projects.length > 0) {
        const matchedProject = projects.find((p) => p.id === snap.selectedProjectId);
        if (matchedProject) handleProjectSelect(matchedProject);
      }
      if (!session.source && !session.source_id && snap.selectedSourceId && connectedSources && connectedSources.length > 0) {
        const matchedSource = connectedSources.find((s) => s.id === snap.selectedSourceId);
        if (matchedSource) setSelectedSource(matchedSource);
      }

      restoreWorkspaceSnapshot(snap);
    }

    const generation = chatGenerationRef.current;
    try {
      const res = await api.getChatMessagesPage(session.id, { limit: MESSAGE_PAGE_SIZE });
      // Inzwischen eine andere Sitzung oder ein neuer Chat: diese Nachrichten nicht mehr zeigen.
      if (generation !== chatGenerationRef.current) return;
      setChatMessages(fromStoredMessages(res.data.messages, !res.data.has_more));
      setOlderPages({ hasMore: res.data.has_more, loading: false });
      showToast(t('page.toast.sessionLoaded', { title: session.title }), 'success');
    } catch (error) {
      console.error(error);
      showToast(t('page.toast.sessionLoadFailed'), 'error', error);
    }
  }, [connectedSources, handleProjectSelect, invalidateChat, ignoreUrlSyncRef, pathname, projects, restoreWorkspaceSnapshot, router, setActiveSessionId, setChatMessages, setSelectedSource, showToast, t]);

  // Ältere Seite vor die geladenen Nachrichten. Nicht während einer laufenden Antwort: Sie schreibt in ihre
  // Position im Verlauf, und das Voranstellen würde diese verschieben.
  const loadOlderMessages = useCallback(async () => {
    const sessionId = activeSessionIdRef.current;
    const oldestId = chatMessagesRef.current[0]?.id;
    if (sessionId == null || oldestId == null || isLoading || olderPages.loading) return;
    const generation = chatGenerationRef.current;
    setOlderPages(current => ({ ...current, loading: true }));
    try {
      const res = await api.getChatMessagesPage(sessionId, { limit: MESSAGE_PAGE_SIZE, before_id: oldestId });
      if (generation !== chatGenerationRef.current) return;
      setChatMessages(prev => [...fromStoredMessages(res.data.messages, !res.data.has_more), ...prev]);
      setOlderPages({ hasMore: res.data.has_more, loading: false });
    } catch (error) {
      if (generation === chatGenerationRef.current) setOlderPages(current => ({ ...current, loading: false }));
      showToast(t('page.toast.sessionLoadFailed'), 'error', error);
    }
  }, [isLoading, olderPages.loading, setChatMessages, showToast, t]);

  const handleRemoveSession = useCallback(async (id: number, event: React.MouseEvent) => {
    event.stopPropagation();
    try {
      await api.deleteChatSession(id);
      setSessions(prev => prev.filter(session => session.id !== id));
      if (activeSessionId === id) {
        resetChatSession();
      }
      showToast(t('page.toast.sessionRemoved'), 'success');
    } catch (error) {
      console.error(error);
      showToast(t('page.toast.sessionDeleteFailed'), 'error', error);
    }
  }, [activeSessionId, resetChatSession, setSessions, showToast, t]);

  return {
    handleShareChat,
    handleSaveSessionWithoutChat,
    handleUpdateSessionSnapshot,
    handleSendChat,
    handleRetryMessage,
    handleSessionSelect,
    handleRemoveSession,
    recordAgentViewActionOutcome,
    invalidateChat,
    chatControls: { olderMessages: { ...olderPages, load: loadOlderMessages }, stop: stopAnswer, editLast: editLastQuestion },
  };
}
