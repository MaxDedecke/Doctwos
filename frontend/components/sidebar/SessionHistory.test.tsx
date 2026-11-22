import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { api } from '@/app/services/api';
import { axiosResponse } from '@/test/http';
import type { ChatSession } from '@/types/domain';
import { SessionHistory } from './SessionHistory';

vi.mock('@/lib/i18n/LanguageContext', () => ({ useLanguage: () => ({ t: (key: string) => key, language: 'de' }) }));
vi.mock('@tanstack/react-virtual', () => ({
  useVirtualizer: ({ count }: { count: number }) => ({
    getVirtualItems: () => Array.from({ length: count }, (_, index) => ({ index, start: index * 40 })),
    getTotalSize: () => count * 40,
    measureElement: () => undefined,
  }),
}));

const sessions: ChatSession[] = [{ id: 1, title: 'Login-Ablauf' }, { id: 2, title: 'Zinsen' }];

function renderHistory() {
  const onSelect = vi.fn();
  render(<SessionHistory sessions={sessions} selectedProject={null} hasMore={false} isLoadingMore={false}
    activeSessionId={null} theme="dark" onSelect={onSelect} onRemove={vi.fn()} />);
  return { onSelect };
}

describe('SessionHistory', () => {
  afterEach(() => vi.restoreAllMocks());

  it('pins a session to the top and renames it in place', async () => {
    const page = vi.spyOn(api, 'getChatSessionsPage').mockResolvedValue(axiosResponse({ sessions: [], has_more: false, limit: 50 }) as never);
    const update = vi.spyOn(api, 'updateChatSession')
      .mockResolvedValueOnce(axiosResponse({ id: 2, title: 'Zinsen', is_pinned: true }) as never)
      .mockResolvedValueOnce(axiosResponse({ id: 2, title: 'Zinslauf', is_pinned: true }) as never);
    renderHistory();
    await waitFor(() => expect(page).toHaveBeenCalledWith({ general: true, pinned: true, limit: 50 }));

    fireEvent.click(screen.getAllByRole('button', { name: 'sidebar.pinSession' })[1]);
    await waitFor(() => expect(screen.getAllByText(/Zinsen|Login-Ablauf/).map(node => node.textContent)).toEqual(['Zinsen', 'Login-Ablauf']));

    fireEvent.click(screen.getAllByRole('button', { name: 'sidebar.renameSession' })[0]);
    const input = screen.getByRole('textbox', { name: 'sidebar.renameSession' });
    fireEvent.change(input, { target: { value: 'Zinslauf' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    await waitFor(() => expect(screen.getByText('Zinslauf')).toBeTruthy());
    expect(update).toHaveBeenLastCalledWith(2, { title: 'Zinslauf' });
  });

  it('searches titles on the server and shows only the matches', async () => {
    vi.useFakeTimers();
    const page = vi.spyOn(api, 'getChatSessionsPage').mockImplementation(async (params) => axiosResponse({
      sessions: params?.q ? [{ id: 9, title: 'Zinsen 2025' }] : [], has_more: false, limit: 50,
    }) as never);
    renderHistory();

    fireEvent.change(screen.getByRole('textbox', { name: 'sidebar.searchSessions' }), { target: { value: 'zins' } });
    await act(async () => { await vi.advanceTimersByTimeAsync(300); });
    vi.useRealTimers();

    await waitFor(() => expect(screen.getByText('Zinsen 2025')).toBeTruthy());
    expect(screen.queryByText('Login-Ablauf')).toBeNull();
    expect(page).toHaveBeenCalledWith({ general: true, q: 'zins', limit: 50 });
  });
});
