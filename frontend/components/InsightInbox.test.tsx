import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { api } from '@/app/services/api';
import { axiosResponse } from '@/test/http';
import { LanguageProvider } from '@/lib/i18n/LanguageContext';
import { InsightInbox } from './InsightInbox';

vi.mock('@/app/services/api', () => ({ api: { getInsight: vi.fn(), getInsightAssignees: vi.fn(), getInsightNotifications: vi.fn(), readInsightNotification: vi.fn(), readInsightNotifications: vi.fn() } }));

it('opens the targeted finding and acknowledges only that notification', async () => {
  vi.mocked(api.getInsightNotifications).mockResolvedValue(axiosResponse({ unread_count: 2, has_more: false, items: [
    { id: 7, insight_id: 10, title: 'Rule to review', kind: 'review_requested', created_at: '2026-11-08T12:00:00Z' },
  ] }));
  vi.mocked(api.readInsightNotification).mockResolvedValue(axiosResponse({ read: 1 }));
  const open = vi.fn();
  render(<LanguageProvider><InsightInbox projectId={3} currentUser={{ id: 1 }} onOpen={open} /></LanguageProvider>);
  fireEvent.click(screen.getByRole('button', { name: 'Meine Hinweise' }));
  fireEvent.click(await screen.findByRole('button', { name: /Prüfung angefordert: Rule to review/ }));
  expect(open).toHaveBeenCalledWith(10);
  await waitFor(() => expect(api.readInsightNotification).toHaveBeenCalledWith(3, 7));
  expect(api.readInsightNotifications).not.toHaveBeenCalled();
});


it('opens a focus-managed detail dialog from the sidebar and closes on Escape', async () => {
  vi.mocked(api.getInsightNotifications).mockResolvedValue(axiosResponse({ unread_count: 1, has_more: false, items: [
    { id: 8, insight_id: 11, title: 'Owned draft', kind: 'assigned', created_at: '2026-11-08T12:00:00Z' },
  ] }));
  vi.mocked(api.readInsightNotification).mockResolvedValue(axiosResponse({ read: 1 }));
  vi.mocked(api.getInsight).mockResolvedValue(axiosResponse({
    id: 11, title: 'Owned draft', content: 'A reviewed source is required.', status: 'draft',
    revision: 1, work_revision: 1, owner_id: 1, reviewer_id: null, priority: 1, due_at: null,
    created_by_id: 1, version_state: 'project', needs_review: true, evidence_count: 0,
    evidence: [], current_versions: [], version_bindings: null, review_history: [], workflow_history: [],
    outdated_source_ids: [],
  }));
  vi.mocked(api.getInsightAssignees).mockResolvedValue(axiosResponse({ items: [], can_manage: false, truncated: false }));
  render(<LanguageProvider><InsightInbox projectId={3} currentUser={{ id: 1 }} align="up" /></LanguageProvider>);
  fireEvent.click(screen.getByRole('button', { name: 'Meine Hinweise' }));
  fireEvent.click(await screen.findByRole('button', { name: /Neue Zuständigkeit: Owned draft/ }));
  const dialog = await screen.findByRole('dialog', { name: 'Erkenntnis im Detail' });
  expect(await screen.findByText('A reviewed source is required.')).toBeTruthy();
  fireEvent.keyDown(dialog, { key: 'Escape' });
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
});
