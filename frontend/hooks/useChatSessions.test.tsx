import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { axiosResponse } from '@/test/http';
import { api } from '@/app/services/api';
import type { ChatMessage, ChatSession } from '@/types/domain';
import { useChatSessions } from './useChatSessions';

vi.mock('@/app/services/api', () => ({
  api: {
    getChatSessions: vi.fn(),
    updateChatMessageFeedback: vi.fn(),
  },
}));

const mockedApi = vi.mocked(api);
const showToast = vi.fn();
const t = (key: string, values?: Record<string, string | number>) =>
  values ? `${key}:${JSON.stringify(values)}` : key;

function message(overrides: Partial<ChatMessage> = {}): ChatMessage {
  return { id: 1, role: 'assistant', content: 'Antwort', sources: [], metadata: {}, ...overrides };
}

function feedbackResponse(linkFeedback: { signals_recorded: number; marked_for_review: Array<{ type: string; id: number }> }) {
  return axiosResponse({ id: 1, feedback: 'down' as const, link_feedback: linkFeedback });
}

describe('useChatSessions', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockedApi.getChatSessions.mockResolvedValue(axiosResponse([]));
  });

  it('does not load sessions before login', () => {
    renderHook(() => useChatSessions({ isLoggedIn: false, t, showToast }));
    expect(mockedApi.getChatSessions).not.toHaveBeenCalled();
  });

  it('loads sessions once logged in and marks them as loaded', async () => {
    const sessions: ChatSession[] = [{ id: 1, title: 'Erste Frage' }];
    mockedApi.getChatSessions.mockResolvedValue(axiosResponse(sessions));

    const { result } = renderHook(() => useChatSessions({ isLoggedIn: true, t, showToast }));

    await waitFor(() => expect(result.current.isSessionsLoaded).toBe(true));
    expect(result.current.sessions).toEqual(sessions);
  });

  it('still marks sessions as loaded when the request fails, leaving the list empty', async () => {
    mockedApi.getChatSessions.mockRejectedValue(new Error('network down'));

    const { result } = renderHook(() => useChatSessions({ isLoggedIn: true, t, showToast }));

    await waitFor(() => expect(result.current.isSessionsLoaded).toBe(true));
    expect(result.current.sessions).toEqual([]);
  });

  it('reloads sessions from scratch on a fresh login, without carrying over the previous list', async () => {
    const stale: ChatSession[] = [{ id: 1, title: 'Alte Sitzung' }];
    mockedApi.getChatSessions.mockResolvedValueOnce(axiosResponse(stale));
    const { result, rerender } = renderHook(
      ({ isLoggedIn }) => useChatSessions({ isLoggedIn, t, showToast }),
      { initialProps: { isLoggedIn: true } },
    );
    await waitFor(() => expect(result.current.sessions).toEqual(stale));

    const fresh: ChatSession[] = [{ id: 2, title: 'Neue Sitzung' }];
    mockedApi.getChatSessions.mockResolvedValueOnce(axiosResponse(fresh));
    rerender({ isLoggedIn: false });
    rerender({ isLoggedIn: true });

    await waitFor(() => expect(result.current.sessions).toEqual(fresh));
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
