import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { api } from '@/app/services/api';
import { LanguageProvider } from '@/lib/i18n/LanguageContext';
import { axiosResponse } from '@/test/http';
import { InsightCommitCheck } from './InsightCommitCheck';

vi.mock('@/app/services/api', () => ({ api: {
  getInsightCommitSources: vi.fn(), checkInsightCommit: vi.fn(), verifyInsight: vi.fn(),
} }));

const report = {
  source_id: 8, branch: 'main', target_commit: 'b'.repeat(40), target_indexed: true, next_cursor: null,
  items: [{
    id: 10, title: 'Transaktion im Worker', content: 'Die Transaktion bleibt im Worker.',
    status: 'outdated', revision: 4, created_by_id: 2, result: 'needs_review', reason: 'files_changed',
    base_commit: 'a'.repeat(40), can_verify: true,
    evidence: [{ source_id: 8, file: 'Worker.java' }],
    version_bindings: [{ source_id: 8, commit: 'a'.repeat(40) }],
    current_versions: [{ source_id: 8, commit: 'b'.repeat(40) }],
    files: [{ file: 'Helper.java', change: 'M', kind: 'dependency', diff: { text: '-old\n+new', truncated: false } }],
  }],
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.getInsightCommitSources).mockResolvedValue(axiosResponse([{ id: 8, name: 'repo', branch: 'main', indexed_commit: 'b'.repeat(40) }]));
  vi.mocked(api.checkInsightCommit).mockResolvedValue(axiosResponse(report));
  vi.mocked(api.verifyInsight).mockResolvedValue(axiosResponse({}));
});

function view() {
  return render(<LanguageProvider><InsightCommitCheck projectId={3} canVerify reviewerId={1} theme="dark" onVerified={vi.fn()} /></LanguageProvider>);
}

async function submit() {
  await screen.findByRole('option', { name: 'repo · main' });
  fireEvent.change(screen.getByLabelText('Neuer Commit oder Git-Referenz'), { target: { value: 'HEAD' } });
  fireEvent.click(screen.getByRole('button', { name: 'Commit prüfen' }));
}

it('shows the evidence diff and submits approval with the displayed versions', async () => {
  vi.spyOn(window, 'confirm').mockReturnValue(true);
  view();
  await submit();
  expect(await screen.findByText('Transaktion im Worker')).toBeTruthy();
  expect(screen.getByText(/-old\s+\+new/)).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Für diesen Quellenstand freigeben' }));
  await waitFor(() => expect(api.verifyInsight).toHaveBeenCalledWith(3, 10, 4, report.items[0].current_versions));
});

it('disables approval for an unindexed commit', async () => {
  vi.mocked(api.checkInsightCommit).mockResolvedValue(axiosResponse({
    ...report, target_indexed: false, items: [{ ...report.items[0], can_verify: false }],
  }));
  view();
  await submit();
  expect(await screen.findByText(/noch nicht vollständig indiziert/)).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'Für diesen Quellenstand freigeben' })).toBeNull();
});

it('discards a late result after the requested commit changes', async () => {
  let complete: ((value: Awaited<ReturnType<typeof api.checkInsightCommit>>) => void) | undefined;
  vi.mocked(api.checkInsightCommit).mockReturnValue(new Promise(resolve => { complete = resolve; }));
  view();
  await submit();
  fireEvent.change(screen.getByLabelText('Neuer Commit oder Git-Referenz'), { target: { value: 'other' } });
  await act(async () => { complete?.(axiosResponse(report)); });
  await waitFor(() => expect(screen.queryByText('Transaktion im Worker')).toBeNull());
});

it('keeps self approval unavailable to a project admin', async () => {
  vi.mocked(api.checkInsightCommit).mockResolvedValue(axiosResponse({
    ...report, items: [{ ...report.items[0], created_by_id: 1 }],
  }));
  view();
  await submit();
  await screen.findByText('Transaktion im Worker');
  expect(screen.queryByRole('button', { name: 'Für diesen Quellenstand freigeben' })).toBeNull();
});
