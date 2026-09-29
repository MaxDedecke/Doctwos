import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { axiosResponse } from '@/test/http';
import { api } from '@/app/services/api';
import type { ChatMessage, ChatSession } from '@/types/domain';
import { useChatSessions } from './useChatSessions';

vi.mock('@/app/services/api', () => ({
  api: {
    getChatSessionsPage: vi.fn(),
    updateChatMessageFeedback: vi.fn(),
  },
}));

const mockedApi = vi.mocked(api);
const showToast = vi.fn();
const t = (key: string, values?: Record<string, string | number>) =>
  values ? `${key}:${JSON.stringify(values)}` : key;

function page(sessions: ChatSession[], hasMore = false) {
  return axiosResponse({ sessions, has_more: hasMore, limit: 30 });
}

function message(overrides: Partial<ChatMessage> = {}): ChatMessage {
  return { id: 1, role: 'assistant', content: 'Antwort', sources: [], metadata: {}, ...overrides };
}

function feedbackResponse(linkFeedback: { signals_recorded: number; marked_for_review: Array<{ type: string; id: number }> }) {
  return axiosResponse({ id: 1, feedback: 'down' as const, link_feedback: linkFeedback });
}

describe('useChatSessions', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockedApi.getChatSessionsPage.mockResolvedValue(page([]));
  });

  it('does not load sessions before login', () => {
    renderHook(() => useChatSessions({ isLoggedIn: false, t, showToast }));
    expect(mockedApi.getChatSessionsPage).not.toHaveBeenCalled();
  });

  it('loads sessions once logged in and marks them as loaded', async () => {
    const sessions: ChatSession[] = [{ id: 1, title: 'Erste Frage' }];
    mockedApi.getChatSessionsPage.mockResolvedValue(page(sessions));

    const { result } = renderHook(() => useChatSessions({ isLoggedIn: true, t, showToast }));

    await waitFor(() => expect(result.current.isSessionsLoaded).toBe(true));
    expect(result.current.sessions).toEqual(sessions);
  });

  it('still marks sessions as loaded when the request fails, leaving the list empty', async () => {
    mockedApi.getChatSessionsPage.mockRejectedValue(new Error('network down'));

    const { result } = renderHook(() => useChatSessions({ isLoggedIn: true, t, showToast }));

    await waitFor(() => expect(result.current.isSessionsLoaded).toBe(true));
    expect(result.current.sessions).toEqual([]);
  });

  it('reloads sessions from scratch on a fresh login, without carrying over the previous list', async () => {
    const stale: ChatSession[] = [{ id: 1, title: 'Alte Sitzung' }];
    mockedApi.getChatSessionsPage.mockResolvedValueOnce(page(stale));
    const { result, rerender } = renderHook(
      ({ isLoggedIn }) => useChatSessions({ isLoggedIn, t, showToast }),
      { initialProps: { isLoggedIn: true } },
    );
    await waitFor(() => expect(result.current.sessions).toEqual(stale));

    const fresh: ChatSession[] = [{ id: 2, title: 'Neue Sitzung' }];
    mockedApi.getChatSessionsPage.mockResolvedValueOnce(page(fresh));
    rerender({ isLoggedIn: false });
    rerender({ isLoggedIn: true });

    await waitFor(() => expect(result.current.sessions).toEqual(fresh));
  });

  describe('paged history', () => {
    const many = (from: number, count: number): ChatSession[] =>
      Array.from({ length: count }, (_, i) => ({ id: from - i, title: `Sitzung ${from - i}`, project_id: null }));

    it('requests the first page of the general context and exposes whether older sessions exist', async () => {
      mockedApi.getChatSessionsPage.mockResolvedValue(page(many(100, 30), true));

      const { result } = renderHook(() => useChatSessions({ isLoggedIn: true, t, showToast }));

      await waitFor(() => expect(result.current.isSessionsLoaded).toBe(true));
      expect(mockedApi.getChatSessionsPage).toHaveBeenCalledWith({ limit: 30, general: true });
      expect(result.current.sessions).toHaveLength(30);
      expect(result.current.hasMoreSessions).toBe(true);
    });

    it('loads the next page with the smallest loaded id as cursor and appends it without duplicates', async () => {
      mockedApi.getChatSessionsPage
        .mockResolvedValueOnce(page(many(100, 30), true))
        .mockResolvedValueOnce(page([{ id: 71, title: 'Sitzung 71', project_id: null }, ...many(70, 30)], false)); // 71 überlappt bewusst
      const { result } = renderHook(() => useChatSessions({ isLoggedIn: true, t, showToast }));
      await waitFor(() => expect(result.current.hasMoreSessions).toBe(true));

      act(() => result.current.loadMoreSessions());

      await waitFor(() => expect(result.current.sessions).toHaveLength(60));
      expect(mockedApi.getChatSessionsPage).toHaveBeenLastCalledWith({ limit: 30, before_id: 71, general: true });
      expect(new Set(result.current.sessions.map((session) => session.id)).size).toBe(60);
      expect(result.current.hasMoreSessions).toBe(false);
    });

    it('does not start a second request while one page is loading, nor when nothing is left', async () => {
      let resolveSecond: (value: unknown) => void = () => {};
      mockedApi.getChatSessionsPage
        .mockResolvedValueOnce(page(many(100, 30), true))
        .mockReturnValueOnce(new Promise((resolve) => { resolveSecond = resolve; }) as never);
      const { result } = renderHook(() => useChatSessions({ isLoggedIn: true, t, showToast }));
      await waitFor(() => expect(result.current.hasMoreSessions).toBe(true));

      act(() => { result.current.loadMoreSessions(); });
      act(() => { result.current.loadMoreSessions(); });
      expect(mockedApi.getChatSessionsPage).toHaveBeenCalledTimes(2);

      await act(async () => { resolveSecond(page(many(70, 5), false)); });
      await waitFor(() => expect(result.current.hasMoreSessions).toBe(false));
      act(() => result.current.loadMoreSessions());
      expect(mockedApi.getChatSessionsPage).toHaveBeenCalledTimes(2);
    });

    it('loads the first page of a project once when it becomes the context and keeps the general sessions', async () => {
      mockedApi.getChatSessionsPage
        .mockResolvedValueOnce(page([{ id: 9, title: 'Allgemein', project_id: null }], false))
        .mockResolvedValueOnce(page([{ id: 8, title: 'Projekt A', project_id: 5 }], false));
      const { result, rerender } = renderHook(
        ({ projectId }) => useChatSessions({ isLoggedIn: true, contextProjectId: projectId, t, showToast }),
        { initialProps: { projectId: null as number | null } },
      );
      await waitFor(() => expect(result.current.isSessionsLoaded).toBe(true));

      rerender({ projectId: 5 });
      await waitFor(() => expect(result.current.sessions).toHaveLength(2));
      expect(mockedApi.getChatSessionsPage).toHaveBeenLastCalledWith({ limit: 30, project_id: 5 });

      rerender({ projectId: null });
      rerender({ projectId: 5 });
      expect(mockedApi.getChatSessionsPage).toHaveBeenCalledTimes(2);
      expect(result.current.sessions.map((session) => session.id)).toEqual([9, 8]);
    });

    it('stops offering more sessions when a page fails', async () => {
      mockedApi.getChatSessionsPage
        .mockResolvedValueOnce(page(many(100, 30), true))
        .mockRejectedValueOnce(new Error('network down'));
      const { result } = renderHook(() => useChatSessions({ isLoggedIn: true, t, showToast }));
      await waitFor(() => expect(result.current.hasMoreSessions).toBe(true));

      act(() => result.current.loadMoreSessions());

      await waitFor(() => expect(result.current.hasMoreSessions).toBe(false));
      expect(result.current.sessions).toHaveLength(30);
    });
  });

  describe('handleFeedback', () => {
    it('applies the feedback optimistically and toggles it off on a repeated click', async () => {
      mockedApi.updateChatMessageFeedback.mockResolvedValue(
        feedbackResponse({ signals_recorded: 0, marked_for_review: [] }));
      const { result } = renderHook(() => useChatSessions({ isLoggedIn: false, t, showToast }));
      act(() => result.current.setChatMessages([message({ id: 1 })]));

      await act(async () => { await result.current.handleFeedback(1, 'up'); });
      expect(result.current.chatMessages[0].feedback).toBe('up');
      expect(mockedApi.updateChatMessageFeedback).toHaveBeenLastCalledWith(1, 'up');

      await act(async () => { await result.current.handleFeedback(1, 'up'); });
      expect(result.current.chatMessages[0].feedback).toBeNull();
      expect(mockedApi.updateChatMessageFeedback).toHaveBeenLastCalledWith(1, null);
    });

    it('rolls back the optimistic update and toasts an error when persistence fails', async () => {
      const failure = new Error('network down');
      mockedApi.updateChatMessageFeedback.mockRejectedValue(failure);
      const { result } = renderHook(() => useChatSessions({ isLoggedIn: false, t, showToast }));
      act(() => result.current.setChatMessages([message({ id: 1, feedback: undefined })]));

      await act(async () => { await result.current.handleFeedback(1, 'down'); });

      expect(result.current.chatMessages[0].feedback).toBeNull();
      expect(showToast).toHaveBeenCalledWith('page.toast.feedbackFailed', 'error', failure);
    });

    it('toasts that links were marked for review when the negative signal produces one', async () => {
      mockedApi.updateChatMessageFeedback.mockResolvedValue(
        feedbackResponse({ signals_recorded: 1, marked_for_review: [{ type: 'entity_doc', id: 5 }] }));
      const { result } = renderHook(() => useChatSessions({ isLoggedIn: false, t, showToast }));
      act(() => result.current.setChatMessages([message({ id: 1 })]));

      await act(async () => { await result.current.handleFeedback(1, 'down'); });

      expect(showToast).toHaveBeenCalledWith('page.toast.feedbackLinksMarkedForReview', 'success');
    });

    it('toasts that a signal was recorded when no link needed review', async () => {
      mockedApi.updateChatMessageFeedback.mockResolvedValue(
        feedbackResponse({ signals_recorded: 1, marked_for_review: [] }));
      const { result } = renderHook(() => useChatSessions({ isLoggedIn: false, t, showToast }));
      act(() => result.current.setChatMessages([message({ id: 1 })]));

      await act(async () => { await result.current.handleFeedback(1, 'down'); });

      expect(showToast).toHaveBeenCalledWith('page.toast.feedbackLinkSignalRecorded', 'success');
    });

    it('says nothing when no link signal was recorded', async () => {
      mockedApi.updateChatMessageFeedback.mockResolvedValue(
        feedbackResponse({ signals_recorded: 0, marked_for_review: [] }));
      const { result } = renderHook(() => useChatSessions({ isLoggedIn: false, t, showToast }));
      act(() => result.current.setChatMessages([message({ id: 1 })]));

      await act(async () => { await result.current.handleFeedback(1, 'up'); });

      expect(showToast).not.toHaveBeenCalled();
    });
  });

  it('addAssistantHint appends a plain assistant note without touching earlier messages', () => {
    const { result } = renderHook(() => useChatSessions({ isLoggedIn: false, t, showToast }));
    act(() => result.current.setChatMessages([message({ id: 1, content: 'Erste' })]));

    act(() => result.current.addAssistantHint('Hinweis'));

    expect(result.current.chatMessages).toEqual([
      message({ id: 1, content: 'Erste' }),
      { role: 'assistant', content: 'Hinweis', sources: [], metadata: {} },
    ]);
  });
});
