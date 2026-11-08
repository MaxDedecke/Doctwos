import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { api } from '@/app/services/api';
import { LanguageProvider } from '@/lib/i18n/LanguageContext';
import { axiosResponse } from '@/test/http';
import type { InsightDetail } from '@/lib/insights';
import { InsightReviewView } from './InsightReviewView';

vi.mock('@/app/services/api', () => ({ api: {
  getInsightWorklist: vi.fn(), getInsight: vi.fn(), getInsightAssignees: vi.fn(), getInsightNotifications: vi.fn(),
  readInsightNotifications: vi.fn(), assignInsight: vi.fn(), getInsightEvidenceOptions: vi.fn(), batchApproveInsights: vi.fn(),
  getInsights: vi.fn(), getProjectMembers: vi.fn(), getLinkRecommendations: vi.fn(),
  getInsightCommitSources: vi.fn(), checkInsightCommit: vi.fn(), reviewInsight: vi.fn(), verifyInsight: vi.fn(), deleteInsight: vi.fn(),
} }));

const insight: Awaited<ReturnType<typeof api.getInsights>>['data'][number] = {
  id: 10, title: 'Zahlungsregel', content: 'Die Regel hat sich geändert.',
  origin_kind: 'code', evidence: [{ file: 'PAY.cbl' }], status: 'verified' as const,
  created_by_id: 1, created_at: null, verified_by_id: 2, verified_at: null,
  outdated_at: null, outdated_source_ids: [],
};

beforeEach(() => {
  vi.mocked(api.getInsightCommitSources).mockResolvedValue(axiosResponse([]));
  vi.mocked(api.getInsights).mockResolvedValue(axiosResponse([insight]));
  vi.mocked(api.getProjectMembers).mockResolvedValue(axiosResponse([]));
  vi.mocked(api.getLinkRecommendations).mockResolvedValue(axiosResponse({ counts: { pending: 0, approved: 0, rejected: 0 } }) as Awaited<ReturnType<typeof api.getLinkRecommendations>>);
  vi.mocked(api.deleteInsight).mockResolvedValue(axiosResponse(undefined));
  vi.mocked(api.getInsightNotifications).mockResolvedValue(axiosResponse({ unread_count: 0, has_more: false, items: [] }));
  vi.mocked(api.getInsightEvidenceOptions).mockResolvedValue(axiosResponse({ items: [], truncated: false }));
  vi.mocked(api.getInsightWorklist).mockImplementation(async () => {
    const rows = (await api.getInsights(3)).data;
    return axiosResponse({ items: rows.map(row => ({ ...row, revision: row.revision || 1,
      owner_id: null, reviewer_id: null, work_revision: 1, priority: 1, due_at: null,
      version_state: row.version_state || 'project', evidence_count: row.evidence.length, needs_review: true })),
      total: rows.length, offset: 0, limit: 25, has_more: false,
      counts: rows.reduce((counts, row) => ({ ...counts, [row.status]: (counts[row.status] || 0) + 1 }), {} as Record<string, number>),
    });
  });
  vi.mocked(api.getInsight).mockImplementation(async (_project, id) => {
    const row = (await api.getInsights(3)).data.find(row => row.id === id) || insight;
    return axiosResponse({ ...row, revision: row.revision || 1, version_state: row.version_state || 'project',
      owner_id: null, reviewer_id: null, priority: 1, work_revision: 1, due_at: null,
      current_versions: row.current_versions || [], review_history: row.review_history || [], workflow_history: [], needs_review: true, evidence_count: row.evidence.length, version_bindings: row.version_bindings || null,
    } as InsightDetail);
  });
  vi.spyOn(window, 'confirm').mockReturnValue(true);
});

afterEach(() => { vi.restoreAllMocks(); vi.clearAllMocks(); });

function renderView(isAdmin = true) {
  vi.mocked(api.getInsightAssignees).mockImplementation(async () => axiosResponse({ items: [], truncated: false,
    can_manage: isAdmin || (await api.getProjectMembers(3)).data.some((member: { user_id: number; role: string }) => member.user_id === 1 && member.role === 'admin'),
  }));
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
  fireEvent.click(await screen.findByRole('button', { name: 'Details öffnen' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Freigeben' }));
  await waitFor(() => expect(api.verifyInsight).toHaveBeenCalledWith(3, 10, 7, []));
});

it('edits the finding and submits a revision guarded draft', async () => {
  vi.mocked(api.getInsights).mockResolvedValue(axiosResponse([{ ...insight, revision: 7 }]));
  vi.mocked(api.reviewInsight).mockResolvedValue(axiosResponse({}));
  renderView();
  fireEvent.click(await screen.findByRole('button', { name: 'Details öffnen' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Überarbeiten' }));
  fireEvent.change(screen.getByLabelText('Erkenntnis'), { target: { value: 'Die neue Regel gilt.' } });
  fireEvent.click(screen.getByRole('button', { name: 'Entwurf sichern' }));
  await waitFor(() => expect(api.reviewInsight).toHaveBeenCalledWith(3, 10, expect.objectContaining({ action: 'revise', expected_revision: 7, content: 'Die neue Regel gilt.' })));
});

it('pages and filters on the server without loading all insight details', async () => {
  vi.mocked(api.getInsightWorklist).mockResolvedValue(axiosResponse({
    items: [{ ...insight, revision: 1, work_revision: 1, owner_id: null, reviewer_id: null,
      priority: 1, due_at: null, version_state: 'project', needs_review: true, evidence_count: 1 }],
    total: 70, offset: 0, limit: 25, has_more: true, counts: { verified: 70 },
  }));
  renderView();
  await screen.findByText('Zahlungsregel');
  expect(api.getInsight).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Weiter' }));
  await waitFor(() => expect(api.getInsightWorklist).toHaveBeenLastCalledWith(3, expect.objectContaining({ offset: 25, limit: 25 })));
  fireEvent.change(screen.getByRole('textbox', { name: 'Erkenntnisse im Projekt suchen' }), { target: { value: 'Zahlung' } });
  await waitFor(() => expect(api.getInsightWorklist).toHaveBeenLastCalledWith(3, expect.objectContaining({ q: 'Zahlung', offset: 0 })));
  fireEvent.change(screen.getByRole('combobox', { name: 'Aufgabenbereich' }), { target: { value: 'mine' } });
  await waitFor(() => expect(api.getInsightWorklist).toHaveBeenLastCalledWith(3, expect.objectContaining({ mine: true, offset: 0 })));
});

it('only offers batch approval after the displayed detail was reviewed', async () => {
  vi.mocked(api.getInsights).mockResolvedValue(axiosResponse([{ ...insight, status: 'outdated', revision: 9 }]));
  vi.mocked(api.batchApproveInsights).mockResolvedValue(axiosResponse({ items: [{ id: 10, status: 'verified' }] }));
  renderView();
  const checkbox = await screen.findByRole('checkbox', { name: 'Auswählen Zahlungsregel' });
  expect(checkbox.hasAttribute('disabled')).toBe(true);
  fireEvent.click(screen.getByRole('button', { name: 'Details öffnen' }));
  await screen.findByRole('button', { name: 'Freigeben' });
  expect(checkbox.hasAttribute('disabled')).toBe(false);
  fireEvent.click(checkbox);
  fireEvent.click(screen.getByRole('button', { name: '1 geprüfte Erkenntnisse freigeben' }));
  await waitFor(() => expect(api.batchApproveInsights).toHaveBeenCalledWith(3, [{ id: 10, expected_revision: 9, expected_versions: [] }]));
  expect(await screen.findByRole('status')).toBeTruthy();
});
