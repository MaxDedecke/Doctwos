import { useCallback } from 'react';
import type { Dispatch, MutableRefObject, SetStateAction } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { api } from '@/app/services/api';
import { copyToClipboard } from '@/lib/utils';
import { normalizeInitialUserMessage } from '@/lib/chatMessage';
import {
  chatFocusRequestFields,
  createChatMetadata,
  createChatTurnFocus,
  getChatTurnFocus,
} from '@/lib/chatFocus';

type Translator = (key: string, vars?: Record<string, string | number>) => string;
type Toast = (message: string, type?: string) => void;

interface ChatControllerOptions {
  t: Translator;
  showToast: Toast;
  ignoreUrlSyncRef: MutableRefObject<boolean>;
  activeSessionId: number | null;
  setActiveSessionId: Dispatch<SetStateAction<number | null>>;
  chatMessages: any[];
  setChatMessages: Dispatch<SetStateAction<any[]>>;
  currentMessage: string;
  setCurrentMessage: Dispatch<SetStateAction<string>>;
  isLoading: boolean;
  setIsLoading: Dispatch<SetStateAction<boolean>>;
  setSessions: Dispatch<SetStateAction<any[]>>;
  selectedProject: any | null;
  selectedSource: any | null;
  setSelectedSource: Dispatch<SetStateAction<any | null>>;
  pinnedCode: any;
  branch: string;
  temperature: number;
  systemPrompt: string;
  activeProfileId: string;
  llmProfiles: any[];
  projects: any[];
  connectedSources: any[];
  handleProjectSelect: (project: any | null) => void | Promise<void>;
  restoreWorkspaceSnapshot: (snapshot: any) => void;
  resetChatSession: () => void;
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
  llmProfiles,
  projects,
  connectedSources,
  handleProjectSelect,
  restoreWorkspaceSnapshot,
  resetChatSession,
}: ChatControllerOptions) {
  const router = useRouter();
  const pathname = usePathname();

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
      showToast(t('chatView.copyFailedToast'), 'error');
      return;
    }

    const success = await copyToClipboard(window.location.href);
    showToast(
      success ? t('chatView.linkCopiedToast') : t('chatView.copyFailedToast'),
      success ? 'success' : 'error'
    );
  }, [activeSessionId, showToast, t]);

  // Shared SSE consumer for both a fresh send and a retry/regenerate. The
  // caller prepares the target assistant slot; this function only consumes the
  // stream and applies events to that slot.
  const runChatStream = useCallback(async (requestBody: any, targetIndex: number) => {
    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody)
      });

      if (!response.ok) {
        throw new Error(t('page.error.httpError', { status: response.status }));
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      if (!reader) {
        throw new Error(t('page.error.streamReaderInit'));
      }

      let buffer = '';
      let accumulatedSteps: any[] = [];
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
              const data = JSON.parse(jsonStr);

              if (data.type === 'session') {
                const newSessionId = data.session_id;
                const newSessionUuid = data.session_uuid;

                if (!activeSessionId && newSessionId) {
                  ignoreUrlSyncRef.current = true;
                  setActiveSessionId(newSessionId);
                  const requestFocus = requestBody.metadata?.focus;
                  const newSession = {
                    id: newSessionId,
                    uuid: newSessionUuid,
                    title: data.session_title || (requestBody.message.length > 28 ? requestBody.message.substring(0, 25) + '...' : requestBody.message),
                    project_id: requestBody.project_id ?? null,
                    project: requestFocus?.project ?? selectedProject,
                    source_id: requestBody.source_id ?? null,
                    source: requestFocus?.source ?? selectedSource,
                  };
                  setSessions(prev => [newSession, ...prev]);

                  if (newSessionUuid) {
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
                  id: data.id
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
              } else if (data.type === 'turn_completed') {
                if (data.has_tool_calls) {
                  currentThought = '';
                }
              } else if (data.type === 'answer') {
                setChatMessages(prev => {
                  const next = [...prev];
                  const target = next[targetIndex];
                  if (target && target.role === 'assistant') {
                    next[targetIndex] = {
                      ...target,
                      content: data.content,
                      metadata: {
                        ...target.metadata,
                        agent_steps: data.agent_steps || accumulatedSteps
                      }
                    };
                  }
                  return next;
                });
              } else if (data.type === 'message_saved') {
                setChatMessages(prev => {
                  const next = [...prev];
                  const target = next[targetIndex];
                  if (target && target.role === 'assistant') {
                    next[targetIndex] = { ...target, id: data.message_id };
                  }
                  return next;
                });
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
                showToast(t('page.toast.aiQueryFailed'), 'error');
                return;
              }
            } catch (error) {
              console.error('Failed to process stream chunk', error, jsonStr);
            }
          }
          boundary = buffer.indexOf('\n\n');
        }
      }
    } catch (error: any) {
      console.error(error);
      let errMsgText = t('page.error.chatFetchFailed');
      if (error?.message) {
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
      showToast(t('page.toast.aiQueryFailed'), 'error');
    } finally {
      setIsLoading(false);
    }
  }, [activeSessionId, ignoreUrlSyncRef, pathname, router, selectedProject, selectedSource, setActiveSessionId, setChatMessages, setIsLoading, setSessions, showToast, t]);

  const handleSendChat = useCallback(async (overrideMsg?: string, extraMetadata?: Record<string, any>) => {
    const isFirstUserMessage = !chatMessages.some((message: any) => message.role === 'user');
    const msgToSend = normalizeInitialUserMessage(
      (overrideMsg || currentMessage).trim(),
      isFirstUserMessage
    ).trim();
    if (!msgToSend || isLoading) return;

    const userMsgContent = msgToSend;
    const turnFocus = createChatTurnFocus(selectedProject, selectedSource, pinnedCode);
    const newUserMsg = {
      role: 'user',
      content: userMsgContent,
      metadata: createChatMetadata(turnFocus, extraMetadata),
    };

    const activeProfile = llmProfiles.find(p => p.id === activeProfileId);
    const assistantPlaceholder = {
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
      llm_api_key: activeProfile?.apiKey || undefined,
      llm_base_url: activeProfile?.baseUrl || undefined,
      metadata: newUserMsg.metadata
    }, targetIndex);
  }, [activeProfileId, activeSessionId, branch, chatMessages, currentMessage, isLoading, llmProfiles, pinnedCode, runChatStream, selectedProject, selectedSource, setChatMessages, setCurrentMessage, setIsLoading, systemPrompt, temperature, t]);

  const handleRetryMessage = useCallback(async (index: number) => {
    if (isLoading) return;
    const assistantMsg: any = chatMessages[index];
    const userMsg: any = chatMessages[index - 1];
    if (!assistantMsg || assistantMsg.role !== 'assistant' || !assistantMsg.id) return;
    if (!userMsg || userMsg.role !== 'user') return;

    const activeProfile = llmProfiles.find(p => p.id === activeProfileId);
    const retryPlaceholder = {
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
      llm_api_key: activeProfile?.apiKey || undefined,
      llm_base_url: activeProfile?.baseUrl || undefined,
      metadata: createChatMetadata(turnFocus, userMsg.metadata),
      retry_of_message_id: assistantMsg.id
    }, index);
  }, [activeProfileId, activeSessionId, branch, chatMessages, isLoading, llmProfiles, runChatStream, setChatMessages, setIsLoading, systemPrompt, t, temperature]);

  const handleSessionSelect = useCallback(async (session: any) => {
    ignoreUrlSyncRef.current = true;
    setActiveSessionId(session.id);

    if (session.uuid) {
      const params = new URLSearchParams(window.location.search);
      params.set('chat', session.uuid);
      router.push(`${pathname}?${params.toString()}`);
    }

    if (session.project) {
      const matchedProject = projects && projects.find((p: any) => p.id === session.project.id);
      handleProjectSelect(matchedProject || session.project);
    } else if (session.project_id && projects && projects.length > 0) {
      const matchedProject = projects.find((p: any) => p.id === session.project_id);
      if (matchedProject) {
        handleProjectSelect(matchedProject);
      }
    }

    if (session.source) {
      setSelectedSource(session.source);
    } else if (session.source_id && connectedSources && connectedSources.length > 0) {
      const matchedSource = connectedSources.find((s: any) => s.id === session.source_id);
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
        const matchedProject = projects.find((p: any) => p.id === snap.selectedProjectId);
        if (matchedProject) handleProjectSelect(matchedProject);
      }
      if (!session.source && !session.source_id && snap.selectedSourceId && connectedSources && connectedSources.length > 0) {
        const matchedSource = connectedSources.find((s: any) => s.id === snap.selectedSourceId);
        if (matchedSource) setSelectedSource(matchedSource);
      }

      restoreWorkspaceSnapshot(snap);
    }

    try {
      const res = await api.getChatMessages(session.id);
      let hasUserMessage = false;
      const formatted = res.data.map((message: any) => {
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
      showToast(t('page.toast.sessionLoadFailed'), 'error');
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
      showToast(t('page.toast.sessionDeleteFailed'), 'error');
    }
  }, [activeSessionId, resetChatSession, setSessions, showToast, t]);

  return {
    handleShareChat,
    handleSendChat,
    handleRetryMessage,
    handleSessionSelect,
    handleRemoveSession,
  };
}
