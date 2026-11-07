import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { api } from '@/app/services/api';
import { LanguageProvider } from '@/lib/i18n/LanguageContext';
import { axiosResponse } from '@/test/http';
import { InsightReviewView } from './InsightReviewView';

vi.mock('@/app/services/api', () => ({ api: {
  getInsights: vi.fn(), getProjectMembers: vi.fn(), getLinkRecommendations: vi.fn(),
  reviewInsight: vi.fn(), verifyInsight: vi.fn(), deleteInsight: vi.fn(),
} }));

const insight = {
  id: 10, title: 'Zahlungsregel', content: 'Die Regel hat sich geändert.',
  origin_kind: 'code', evidence: [{ file: 'PAY.cbl' }], status: 'verified' as const,
  created_by_id: 1, created_at: null, verified_by_id: 2, verified_at: null,
  outdated_at: null, outdated_source_ids: [],
};

beforeEach(() => {
  vi.mocked(api.getInsights).mockResolvedValue(axiosResponse([insight]));
  vi.mocked(api.getProjectMembers).mockResolvedValue(axiosResponse([]));
  vi.mocked(api.getLinkRecommendations).mockResolvedValue(axiosResponse({ counts: { pending: 0, approved: 0, rejected: 0 } }) as Awaited<ReturnType<typeof api.getLinkRecommendations>>);
  vi.mocked(api.deleteInsight).mockResolvedValue(axiosResponse(undefined));
  vi.spyOn(window, 'confirm').mockReturnValue(true);
});

afterEach(() => { vi.restoreAllMocks(); vi.clearAllMocks(); });

function renderView(isAdmin = true) {
  return render(<LanguageProvider><InsightReviewView selectedProject={{ id: 3, name: 'Projekt' }} currentUser={{ id: 1, username: 'admin', is_admin: isAdmin }} theme="dark" /></LanguageProvider>);
}

it('deletes a verified insight after confirmation and removes it from the list', async () => {
  renderView();
  fireEvent.click(await screen.findByRole('button', { name: 'Löschen' }));
  expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining('Zahlungsregel'));
  await waitFor(() => expect(api.deleteInsight).toHaveBeenCalledWith(3, 10));
  await waitFor(() => expect(screen.queryByText('Zahlungsregel')).toBeNull());
  expect(screen.getByText('Keine Erkenntnisse in diesem Projekt.')).toBeTruthy();
});

it('leaves the insight intact when deletion is cancelled', async () => {
  vi.mocked(window.confirm).mockReturnValue(false);
  renderView();
  fireEvent.click(await screen.findByRole('button', { name: 'Löschen' }));
  expect(api.deleteInsight).not.toHaveBeenCalled();
  expect(screen.getByText('Zahlungsregel')).toBeTruthy();
});

it('keeps a failed deletion visible and shows the error', async () => {
  vi.mocked(api.deleteInsight).mockRejectedValueOnce(new Error('failed'));
  renderView();
  fireEvent.click(await screen.findByRole('button', { name: 'Löschen' }));
  expect(await screen.findByText('Die Erkenntnis konnte nicht gelöscht werden.')).toBeTruthy();
  expect(screen.getByText('Zahlungsregel')).toBeTruthy();
});

it('does not offer deletion to ordinary project members', async () => {
  renderView(false);
  await screen.findByText('Zahlungsregel');
  expect(screen.queryByRole('button', { name: 'Löschen' })).toBeNull();
});

it('also allows project admins to delete outdated insights', async () => {
  vi.mocked(api.getInsights).mockResolvedValue(axiosResponse([{ ...insight, status: 'outdated' }]));
  vi.mocked(api.getProjectMembers).mockResolvedValue(axiosResponse([{ id: 1, user_id: 1, user_name: 'admin', role: 'admin' }]));
  renderView(false);
  fireEvent.click(await screen.findByRole('button', { name: 'Löschen' }));
  await waitFor(() => expect(api.deleteInsight).toHaveBeenCalledWith(3, 10));
});

it('reapproves an outdated finding with its displayed revision', async () => {
  vi.mocked(api.getInsights).mockResolvedValue(axiosResponse([{ ...insight, status: 'outdated', revision: 7 }]));
  vi.mocked(api.verifyInsight).mockResolvedValue(axiosResponse({}));
  renderView();
  fireEvent.click(await screen.findByRole('button', { name: 'Freigeben' }));
  await waitFor(() => expect(api.verifyInsight).toHaveBeenCalledWith(3, 10, 7));
});

it('edits the finding and submits a revision guarded draft', async () => {
  vi.mocked(api.getInsights).mockResolvedValue(axiosResponse([{ ...insight, revision: 7 }]));
  vi.mocked(api.reviewInsight).mockResolvedValue(axiosResponse({}));
  renderView();
  fireEvent.click(await screen.findByRole('button', { name: 'Überarbeiten' }));
  fireEvent.change(screen.getByLabelText('Erkenntnis'), { target: { value: 'Die neue Regel gilt.' } });
  fireEvent.click(screen.getByRole('button', { name: 'Entwurf sichern' }));
  await waitFor(() => expect(api.reviewInsight).toHaveBeenCalledWith(3, 10, expect.objectContaining({ action: 'revise', expected_revision: 7, content: 'Die neue Regel gilt.' })));
});
