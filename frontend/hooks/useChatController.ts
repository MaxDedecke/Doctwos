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
import { normalizeInitialUserMessage } from '@/lib/chatMessage';
import { parseChatStreamEvent } from '@/lib/chatStream';
import { extractCallFlowData } from '@/lib/callFlow';
import type { CallFlowData } from '@/lib/callFlow';
import { copyToClipboard } from '@/lib/utils';
import type { AgentStep, AgentViewAction, AgentViewActionStatus, ChatMessage, ChatMetadata, ChatRequest, ChatSession, KnowledgeSource, Project, WorkspaceSnapshot } from '@/types/domain';
import { usePathname, useRouter } from 'next/navigation';
import type { Dispatch, MutableRefObject, SetStateAction } from 'react';
import { useCallback, useLayoutEffect, useRef } from 'react';

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
  temperature: number;
  systemPrompt: string;
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
  // stream and applies events to that slot.
  const runChatStream = useCallback(async (requestBody: ChatRequest, targetIndex: number) => {
    let expectedSessionId = requestBody.session_id;
    let expectedSessionEpoch = activeSessionEpochRef.current;
    try {
      const response = await api.fetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody)
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
      let accumulatedSteps: AgentStep[] = [];
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
                const newSessionId = data.session_id;
                const newSessionUuid = data.session_uuid;

                if (requestBody.session_id == null && newSessionId) {
                  const shouldActivateSession = activeSessionIdRef.current == null &&
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
                setChatMessages(prev => {
                  const next = [...prev];
                  const target = next[targetIndex];
                  if (target && target.role === 'assistant') {
                    next[targetIndex] = { ...target, sources: data.sources };
                  }
                  return next;
                });
              } else if (data.type === 'content_chunk') {
                currentThought += data.content;
                setChatMessages(prev => {
                  const next = [...prev];
                  const target = next[targetIndex];
                  if (target && target.role === 'assistant') {
                    next[targetIndex] = { ...target, content: target.content + data.content };
                  }
                  return next;
                });
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

                setChatMessages(prev => {
                  const next = [...prev];
                  const target = next[targetIndex];
                  if (target && target.role === 'assistant') {
                    next[targetIndex] = {
                      ...target,
                      content: '',
                      metadata: {
                        ...target.metadata,
                        agent_steps: accumulatedSteps
                      }
                    };
                  }
                  return next;
                });
              } else if (data.type === 'tool_result') {
                const newSteps = [...accumulatedSteps];
                newSteps.push({
                  type: 'tool_result',
                  name: data.name,
                  result: data.result,
                  id: data.id,
                  truncated: data.truncated
                });
                accumulatedSteps = newSteps;

                setChatMessages(prev => {
                  const next = [...prev];
                  const target = next[targetIndex];
                  if (target && target.role === 'assistant') {
                    next[targetIndex] = {
                      ...target,
                      metadata: {
                        ...target.metadata,
                        agent_steps: accumulatedSteps
                      }
                    };
                  }
                  return next;
                });
              } else if (data.type === 'view_action') {
                if (handledViewActionIdsRef.current.has(data.action_id)) {
                  boundary = buffer.indexOf('\n\n');
                  continue;
                }
                handledViewActionIdsRef.current.add(data.action_id);

                const matchingResult = [...accumulatedSteps].reverse().find(step =>
                  step.type === 'tool_result' && step.id === data.tool_call_id && (
                    (data.view === 'callgraph' && (step.name === 'trace_call_flow' || step.name === 'inspect_change_impact')) ||
                    (data.view === 'code' && step.name === 'view_repo_file') ||
                    (data.view === 'walkthrough' &&
                      (step.name === 'offer_code_walkthrough' || step.name === 'offer_source_walkthrough'))
                  )
                );
                const flow = data.view === 'callgraph' && matchingResult
                  ? extractCallFlowData({ role: 'assistant', content: '', metadata: { agent_steps: [matchingResult] } })
                  : null;
                let hasMatchingCodeLocation = false;
                let hasMatchingWalkthrough = false;
                if (data.view === 'code' && matchingResult?.type === 'tool_result') {
                  try {
                    const result = JSON.parse(matchingResult.result) as Record<string, unknown>;
                    hasMatchingCodeLocation = result.file_path === data.target.file_path &&
                      result.start_line === data.target.start_line &&
                      result.end_line === data.target.end_line;
                  } catch {
                    hasMatchingCodeLocation = false;
                  }
                }
                if (data.view === 'walkthrough' && matchingResult?.type === 'tool_result') {
                  try {
                    const result = JSON.parse(matchingResult.result) as Record<string, unknown>;
                    const canonicalize = (value: unknown) => JSON.stringify(
                      value && typeof value === 'object' && !Array.isArray(value)
                        ? Object.fromEntries(Object.entries(value as Record<string, unknown>).sort(([left], [right]) => left.localeCompare(right)))
                        : value,
                    );
                    hasMatchingWalkthrough = result.status === 'ok' &&
                      result.title === data.target.title &&
                      Array.isArray(result.steps) && result.steps.length === data.target.steps.length &&
                      result.steps.every((step, index) => canonicalize(step) === canonicalize(data.target.steps[index])) &&
                      data.target.steps.every(step => {
                        if (step.kind !== 'callgraph') return true;
                        const traceResult = accumulatedSteps.find(candidate =>
                          candidate.type === 'tool_result' && candidate.name === 'trace_call_flow' &&
                          candidate.id === step.trace_tool_call_id,
                        );
                        if (traceResult?.type !== 'tool_result') return false;
                        const flow = extractCallFlowData({ role: 'assistant', content: '', metadata: { agent_steps: [traceResult] } });
                        if (!flow) return false;
                        const edge = flow.edges.find(candidate => candidate.id === step.edge_id);
                        const source = flow.nodes.find(candidate => candidate.id === step.source_entity_id);
                        const target = flow.nodes.find(candidate => candidate.id === step.target_entity_id);
                        return edge?.resolution === 'resolved' &&
                          edge.source === step.source_entity_id && edge.target === step.target_entity_id &&
                          source?.name === step.source_name && target?.name === step.target_name &&
                          source?.file_path === (step.file_path || undefined) &&
                          edge.start_line === step.start_line && edge.end_line === step.end_line;
                      });
                  } catch {
                    hasMatchingWalkthrough = false;
                  }
                }
                let status: ViewActionOutcome = 'rejected';
                const requestProjectId = requestBody.project_id == null ? null : Number(requestBody.project_id);
                const isCurrentTurn = activeSessionIdRef.current === data.session_id &&
                  expectedSessionId === data.session_id &&
                  activeSessionEpochRef.current === expectedSessionEpoch &&
                  requestProjectId === data.project_id;

                if (!isCurrentTurn) {
                  status = 'stale_context';
                } else if (
                  (data.view === 'callgraph' && (!flow || flow.root.id !== data.target.entity_id)) ||
                  (data.view === 'code' && !hasMatchingCodeLocation) ||
                  (data.view === 'walkthrough' && !hasMatchingWalkthrough)
                ) {
                  status = 'rejected';
                } else {
                  // Agent views are proposals. Opening only happens after an explicit click in ChatView.
                  status = 'manual';
                }

                const recordedAction: AgentViewAction = { ...data, status };
                viewActionOutcomesRef.current.set(data.action_id, status);
                accumulatedSteps = [...accumulatedSteps, recordedAction];
                if (activeSessionIdRef.current === data.session_id) {
                  setChatMessages(prev => {
                    const next = [...prev];
                    const target = next[targetIndex];
                    if (target && target.role === 'assistant') {
                      next[targetIndex] = {
                        ...target,
                        metadata: { ...target.metadata, agent_steps: accumulatedSteps },
                      };
                    }
                    return next;
                  });
                }
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
                setChatMessages(prev => {
                  const next = [...prev];
                  const target = next[targetIndex];
                  if (target && target.role === 'assistant') {
                    next[targetIndex] = {
                      ...target,
                      content: data.content,
                      metadata: {
                        ...target.metadata,
                        agent_steps: finalSteps
                      }
                    };
                  }
                  return next;
                });
              } else if (data.type === 'message_saved') {
                const actionsToPersist = accumulatedSteps.filter((step): step is AgentViewAction => step.type === 'view_action')
                  .map(action => ({
                    ...action,
                    status: viewActionOutcomesRef.current.get(action.action_id) ?? action.status,
                  }));
                setChatMessages(prev => {
                  const next = [...prev];
                  const target = next[targetIndex];
                  if (target && target.role === 'assistant') {
                    const agentSteps = target.metadata?.agent_steps?.map(step => {
                      const action = actionsToPersist.find(candidate =>
                        candidate.action_id === (step.type === 'view_action' ? step.action_id : undefined),
                      );
                      return action ?? step;
                    });
                    next[targetIndex] = {
                      ...target,
                      id: data.message_id,
                      metadata: agentSteps ? { ...target.metadata, agent_steps: agentSteps } : target.metadata,
                    };
                  }
                  return next;
                });
                for (const action of actionsToPersist) {
                  if (action.status !== 'requested') {
                    persistViewActionOutcome(data.message_id, action.action_id, action.status);
                  }
                }
              } else if (data.type === 'error') {
                const errMsgText = t('page.error.chatFetchFailedWithMessage', { message: data.error });
                setChatMessages(prev => {
                  const next = [...prev];
                  const target = next[targetIndex];
                  if (target && target.role === 'assistant') {
                    next[targetIndex] = { ...target, content: errMsgText };
                  }
                  return next;
                });
                // Serverseitiger Fehler mitten im Stream: die Antwort selbst
                // traegt die Trace-ID des Requests (O-073).
                showToast(t('page.toast.aiQueryFailed'), 'error', response);
                return;
              }
            } catch (error) {
              console.error('Failed to process stream chunk', error, jsonStr);
            }
          }
          boundary = buffer.indexOf('\n\n');
        }
      }
    } catch (error) {
      console.error(error);
      let errMsgText = t('page.error.chatFetchFailed');
      if (error instanceof Error && error.message) {
        errMsgText = t('page.error.chatFetchFailedWithMessage', { message: error.message });
      }
      setChatMessages(prev => {
        const next = [...prev];
        const target = next[targetIndex];
        if (target && target.role === 'assistant') {
          next[targetIndex] = { ...target, content: errMsgText };
        }
        return next;
      });
      showToast(t('page.toast.aiQueryFailed'), 'error', error);
    } finally {
      setIsLoading(false);
    }
  }, [ignoreUrlSyncRef, pathname, router, selectedProject, selectedSource, setActiveSessionId, setChatMessages, setIsLoading, setSessions, showToast, t]);

  const handleSendChat = useCallback(async (overrideMsg?: string, extraMetadata?: ChatMetadata) => {
    const isFirstUserMessage = !chatMessages.some((message) => message.role === 'user');
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
      metadata: createChatMetadata(turnFocus, extraMetadata),
    };

    const activeProfile = llmProfiles.find(p => p.id === activeProfileId);
    const assistantPlaceholder: ChatMessage = {
      role: 'assistant',
      content: '',
      sources: [],
      metadata: {
        model: activeProfile?.name || activeProfile?.model || t('page.defaultModelFallback'),
        provider: activeProfile?.provider,
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
  }, [activeEmbeddingModel, activeProfileId, activeSessionId, branch, chatMessages, currentMessage, isLoading, llmProfiles, pinnedCode, runChatStream, selectedProject, selectedSource, setChatMessages, setCurrentMessage, setIsLoading, systemPrompt, temperature, t]);

  const handleRetryMessage = useCallback(async (index: number) => {
    if (isLoading) return;
    const assistantMsg = chatMessages[index];
    const userMsg = chatMessages[index - 1];
    if (!assistantMsg || assistantMsg.role !== 'assistant' || !assistantMsg.id) return;
    if (!userMsg || userMsg.role !== 'user') return;

    const activeProfile = llmProfiles.find(p => p.id === activeProfileId);
    const retryPlaceholder: ChatMessage = {
      role: 'assistant',
      content: '',
      sources: [],
      metadata: {
        model: activeProfile?.name || activeProfile?.model || t('page.defaultModelFallback'),
        provider: activeProfile?.provider,
        agent_steps: []
      }
    };

    setChatMessages(prev => {
      const next = [...prev];
      next[index] = retryPlaceholder;
      return next;
    });
    setIsLoading(true);

    const turnFocus = getChatTurnFocus(userMsg);

    await runChatStream({
      message: userMsg.content,
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
      retry_of_message_id: assistantMsg.id
    }, index);
  }, [activeEmbeddingModel, activeProfileId, activeSessionId, branch, chatMessages, isLoading, llmProfiles, runChatStream, setChatMessages, setIsLoading, systemPrompt, t, temperature]);

  const handleSessionSelect = useCallback(async (session: ChatSession) => {
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

    try {
      const res = await api.getChatMessages(session.id);
      let hasUserMessage = false;
      const formatted = res.data.map((message) => {
        const isFirstUserMessage = message.role === 'user' && !hasUserMessage;
        if (message.role === 'user') hasUserMessage = true;

        return {
          id: message.id,
          role: message.role,
          content: normalizeInitialUserMessage(message.content, isFirstUserMessage),
          sources: message.sources_json || undefined,
          metadata: message.metadata_json || undefined,
          feedback: message.feedback || undefined
        };
      });
      setChatMessages(formatted);
      showToast(t('page.toast.sessionLoaded', { title: session.title }), 'success');
    } catch (error) {
      console.error(error);
      showToast(t('page.toast.sessionLoadFailed'), 'error', error);
    }
  }, [connectedSources, handleProjectSelect, ignoreUrlSyncRef, pathname, projects, restoreWorkspaceSnapshot, router, setActiveSessionId, setChatMessages, setSelectedSource, showToast, t]);

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
  };
}
