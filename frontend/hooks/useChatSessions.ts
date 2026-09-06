import type { ShowToast } from '@/components/Toast';
import { api } from '@/app/services/api';
import type { ChatMessage, ChatSession } from '@/types/domain';
import { useCallback, useEffect, useState } from 'react';

interface UseChatSessionsOptions {
  isLoggedIn: boolean;
  t: (key: string, values?: Record<string, string | number>) => string;
  showToast: ShowToast;
}

/**
 * Owns the persisted chat-session collection and the transient conversation
 * state. Request orchestration remains in the page for now because it crosses
 * project, source, model, and workspace domains; all chat consumers still use
 * this single state owner.
 */
export function useChatSessions({ isLoggedIn, t, showToast }: UseChatSessionsOptions) {
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [currentMessage, setCurrentMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [isSessionsLoaded, setIsSessionsLoaded] = useState(false);
  const [activeSessionId, setActiveSessionId] = useState<number | null>(null);

  useEffect(() => {
    if (!isLoggedIn) return;

    api.getChatSessions()
      .then((res) => setSessions(res.data))
      .catch((error) => console.error('Failed to load chat sessions:', error))
      .finally(() => setIsSessionsLoaded(true));
  }, [isLoggedIn]);

  /**
   * Keep feedback optimistic so the chat remains responsive, but roll it back
   * if persistence fails. This is a chat-session concern rather than page UI.
   */
  const handleFeedback = useCallback(async (messageId: number, feedback: 'up' | 'down') => {
    const current = chatMessages.find((message) => message.id === messageId)?.feedback ?? null;
    const nextValue = current === feedback ? null : feedback;
    setChatMessages((previous) => previous.map((message) =>
      message.id === messageId ? { ...message, feedback: nextValue } : message
    ));

    try {
      await api.updateChatMessageFeedback(messageId, nextValue);
    } catch (error) {
      console.error(error);
      setChatMessages((previous) => previous.map((message) =>
        message.id === messageId ? { ...message, feedback: current } : message
      ));
      showToast(t('page.toast.feedbackFailed'), 'error', error);
    }
  }, [chatMessages, showToast, t]);

  const addAssistantHint = useCallback((text: string) => {
    setChatMessages((previous) => [...previous, { role: 'assistant', content: text, sources: [], metadata: {} }]);
  }, []);

  return {
    chatMessages,
    setChatMessages,
    currentMessage,
    setCurrentMessage,
    isLoading,
    setIsLoading,
    sessions,
    setSessions,
    isSessionsLoaded,
    activeSessionId,
    setActiveSessionId,
    handleFeedback,
    addAssistantHint,
  };
}
