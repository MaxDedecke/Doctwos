import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

const { apiMocks, settingsState } = vi.hoisted(() => ({
  apiMocks: {
    getNegativeChatFeedback: vi.fn(),
    getFeedbackDiagnosticSettings: vi.fn().mockResolvedValue({ data: null }),
    updateFeedbackDiagnosticSettings: vi.fn(),
    deleteFeedbackDiagnosticCases: vi.fn(),
  },
  settingsState: {
    theme: 'dark' as const,
    currentUser: { id: 1, username: 'admin', is_admin: true } as { id: number; username: string; is_admin: boolean },
    showToast: vi.fn(),
  },
}));

vi.mock('@/app/services/api', () => ({ API_URL: 'http://api.test', api: apiMocks }));
vi.mock('@/components/settings/SettingsContext', () => ({ useSettings: () => settingsState }));
vi.mock('@/lib/i18n/LanguageContext', () => ({
  useLanguage: () => ({
    language: 'de',
    t: (key: string, values?: Record<string, string | number>) =>
      values ? `${key}:${Object.values(values).join('/')}` : key,
  }),
}));

import { EvaluationSettingsTab, FEEDBACK_PAGE_SIZE } from './EvaluationSettingsTab';

const entry = (id: number) => ({
  message_id: id, session_label: 1, question: `Frage ${id}`, answer: `Antwort ${id}`,
  sources_json: [], metadata_json: {}, created_at: null,
});
const page = (ids: number[], total: number, extra: Record<string, unknown> = {}) => ({
  data: { entries: ids.map(entry), total, limit: FEEDBACK_PAGE_SIZE, ...extra },
});
const range = (start: number, count: number) => Array.from({ length: count }, (_, i) => start - i);

afterEach(() => {
  vi.clearAllMocks();
  settingsState.currentUser = { id: 1, username: 'admin', is_admin: true };
  apiMocks.getFeedbackDiagnosticSettings.mockResolvedValue({ data: null });
});

describe('EvaluationSettingsTab negative feedback list paging', () => {
  it('loads and renders only one page of 20 entries', async () => {
    apiMocks.getNegativeChatFeedback.mockResolvedValue(page(range(400, 20), 400));
    render(<EvaluationSettingsTab />);

    await waitFor(() => expect(document.querySelectorAll('details.group')).toHaveLength(20));
    expect(apiMocks.getNegativeChatFeedback).toHaveBeenCalledWith({ limit: 20, offset: 0 });
    expect(screen.getByTestId('list-pager-range').textContent).toBe('settings.pager.range:1/20/400');
  });

  it('pages with server-side offsets and replaces the previous page', async () => {
    apiMocks.getNegativeChatFeedback
      .mockResolvedValueOnce(page(range(45, 20), 45))
      .mockResolvedValueOnce(page(range(25, 20), 45))
      .mockResolvedValueOnce(page(range(5, 5), 45));
    render(<EvaluationSettingsTab />);
    await waitFor(() => expect(document.querySelectorAll('details.group')).toHaveLength(20));

    fireEvent.click(screen.getByLabelText('settings.pager.nextPage'));
    await waitFor(() => expect(apiMocks.getNegativeChatFeedback).toHaveBeenLastCalledWith({ limit: 20, offset: 20 }));
    await waitFor(() => expect(screen.queryByText('Frage 45')).toBeNull());
    expect(await screen.findByText('Frage 25', { selector: 'span' })).toBeTruthy();

    fireEvent.click(screen.getByLabelText('settings.pager.nextPage'));
    await waitFor(() => expect(apiMocks.getNegativeChatFeedback).toHaveBeenLastCalledWith({ limit: 20, offset: 40 }));
    await waitFor(() => expect(document.querySelectorAll('details.group')).toHaveLength(5));
    expect((screen.getByLabelText('settings.pager.nextPage') as HTMLButtonElement).disabled).toBe(true);
  });

  it('searches on the server (debounced), resets to page 1 and shows the no-match state', async () => {
    apiMocks.getNegativeChatFeedback.mockResolvedValueOnce(page(range(45, 20), 45));
    render(<EvaluationSettingsTab />);
    await waitFor(() => expect(document.querySelectorAll('details.group')).toHaveLength(20));

    apiMocks.getNegativeChatFeedback.mockResolvedValue({ data: { entries: [], total: 0, limit: 20 } });
    fireEvent.change(screen.getByPlaceholderText('settings.evaluationTab.feedbackSearch'), { target: { value: 'zebra' } });
    expect(apiMocks.getNegativeChatFeedback).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(apiMocks.getNegativeChatFeedback).toHaveBeenLastCalledWith({ limit: 20, offset: 0, q: 'zebra' }));
    expect(await screen.findByText('settings.evaluationTab.feedbackNoMatches')).toBeTruthy();
    expect(screen.queryByTestId('list-pager-range')).toBeNull();
  });

  it('tells the admin when the search only covered the newest ratings', async () => {
    apiMocks.getNegativeChatFeedback.mockResolvedValueOnce(page([3, 2, 1], 3));
    render(<EvaluationSettingsTab />);
    await waitFor(() => expect(document.querySelectorAll('details.group')).toHaveLength(3));

    apiMocks.getNegativeChatFeedback.mockResolvedValue(page([2], 1, { search_truncated: true }));
    fireEvent.change(screen.getByPlaceholderText('settings.evaluationTab.feedbackSearch'), { target: { value: 'Antwort' } });
    expect(await screen.findByText('settings.evaluationTab.feedbackSearchTruncated')).toBeTruthy();
  });

  it('shows the empty state without a pager when nothing was downvoted', async () => {
    apiMocks.getNegativeChatFeedback.mockResolvedValue({ data: { entries: [], total: 0, limit: 20 } });
    render(<EvaluationSettingsTab />);
    expect(await screen.findByText('settings.evaluationTab.feedbackEmpty')).toBeTruthy();
    expect(screen.queryByTestId('list-pager-range')).toBeNull();
  });

  it('renders nothing and requests nothing for non-admins', () => {
    settingsState.currentUser = { id: 2, username: 'viewer', is_admin: false };
    const { container } = render(<EvaluationSettingsTab />);
    expect(container.innerHTML).toBe('');
    expect(apiMocks.getNegativeChatFeedback).not.toHaveBeenCalled();
  });
});
