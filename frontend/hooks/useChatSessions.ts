import type { ShowToast } from '@/components/Toast';
import { api } from '@/app/services/api';
import type { ChatMessage, ChatSession } from '@/types/domain';
import { useCallback, useEffect, useRef, useState } from 'react';

/** Größe einer Seite des Verlaufs; kleiner als das serverseitige Maximum von 100. */
export const SESSION_PAGE_SIZE = 30;

/** Ladezustand des Verlaufs je Kontext ("general" oder Projekt). `cursor` ist die kleinste vom Server gelieferte ID. */
interface SessionPaging {
  cursor: number | null;
  hasMore: boolean;
  loading: boolean;
}

interface UseChatSessionsOptions {
  isLoggedIn: boolean;
  /** Projekt, dessen Verlauf die Seitenleiste zeigt (null = allgemeiner Kontext). */
  contextProjectId?: number | null;
  t: (key: string, values?: Record<string, string | number>) => string;
  showToast: ShowToast;
}

/**
 * Owns the persisted chat-session collection and the transient conversation
 * state. Request orchestration remains in the page for now because it crosses
 * project, source, model, and workspace domains; all chat consumers still use
 * this single state owner.
 */
export function useChatSessions({ isLoggedIn, contextProjectId = null, t, showToast }: UseChatSessionsOptions) {
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [currentMessage, setCurrentMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [isSessionsLoaded, setIsSessionsLoaded] = useState(false);
  const [activeSessionId, setActiveSessionId] = useState<number | null>(null);

  const contextKey = contextProjectId === null ? 'general' : `project:${contextProjectId}`;
  const [paging, setPaging] = useState<Record<string, SessionPaging>>({});
  // Verhindert doppelte Anfragen, solange der Zustand noch nicht neu gerendert wurde.
  const inFlightRef = useRef<Set<string>>(new Set());

  /**
   * Lädt die nächste Seite des Verlaufs für einen Kontext. Ältere Seiten werden ans Ende
   * der bereits geladenen Sitzungen gehängt (schon bekannte IDs bleiben unverändert),
   * damit lokal angelegte oder per Link geöffnete Sitzungen oben stehen bleiben.
   */
  const loadSessionPage = useCallback(async (key: string, projectId: number | null, cursor: number | null) => {
    if (inFlightRef.current.has(key)) return;
    inFlightRef.current.add(key);
    setPaging((previous) => ({ ...previous, [key]: { cursor, hasMore: previous[key]?.hasMore ?? true, loading: true } }));
    try {
      const res = await api.getChatSessionsPage({
        limit: SESSION_PAGE_SIZE,
        ...(cursor !== null ? { before_id: cursor } : {}),
        ...(projectId !== null ? { project_id: projectId } : { general: true }),
      });
      const incoming = res.data.sessions;
      setSessions((previous) => {
        const known = new Set(previous.map((session) => session.id));
        return [...previous, ...incoming.filter((session) => !known.has(session.id))];
      });
      setPaging((previous) => ({
        ...previous,
        [key]: {
          cursor: incoming.length > 0 ? Math.min(...incoming.map((session) => session.id)) : cursor,
          hasMore: res.data.has_more,
          loading: false,
        },
      }));
    } catch (error) {
      console.error('Failed to load chat sessions:', error);
      setPaging((previous) => ({ ...previous, [key]: { cursor, hasMore: false, loading: false } }));
    } finally {
      inFlightRef.current.delete(key);
    }
  }, []);

  // Nach dem Login den Verlauf (erste Seite des allgemeinen Kontexts) laden; beim Logout
  // wird alles verworfen, damit ein neuer Login von vorn beginnt.
  useEffect(() => {
    if (!isLoggedIn) return;
    let cancelled = false;
    (async () => {
      await loadSessionPage('general', null, null);
      if (!cancelled) setIsSessionsLoaded(true);
    })();
    return () => {
      cancelled = true;
      inFlightRef.current.clear();
      setSessions([]);
      setPaging({});
      setIsSessionsLoaded(false);
    };
  }, [isLoggedIn, loadSessionPage]);

  // Beim Wechsel in ein Projekt dessen erste Seite laden (einmal je Kontext).
  const contextLoaded = paging[contextKey] !== undefined;
  useEffect(() => {
    if (!isLoggedIn || contextProjectId === null || contextLoaded) return;
    (async () => {
      await loadSessionPage(contextKey, contextProjectId, null);
    })();
  }, [isLoggedIn, contextProjectId, contextKey, contextLoaded, loadSessionPage]);

  const contextPaging = paging[contextKey];
  const hasMoreSessions = Boolean(contextPaging?.hasMore);
  const isLoadingMoreSessions = Boolean(contextPaging?.loading);
  const loadMoreSessions = useCallback(() => {
    const state = paging[contextKey];
    if (!state || state.loading || !state.hasMore) return;
    void loadSessionPage(contextKey, contextProjectId, state.cursor);
  }, [contextKey, contextProjectId, loadSessionPage, paging]);

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
      const response = await api.updateChatMessageFeedback(messageId, nextValue);
      if (nextValue === 'down' && response.data.link_feedback.signals_recorded > 0) {
        showToast(
          response.data.link_feedback.marked_for_review.length > 0
            ? t('page.toast.feedbackLinksMarkedForReview')
            : t('page.toast.feedbackLinkSignalRecorded'),
          'success',
        );
      }
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
    hasMoreSessions,
    isLoadingMoreSessions,
    loadMoreSessions,
    activeSessionId,
    setActiveSessionId,
    handleFeedback,
    addAssistantHint,
  };
}
