import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { useState } from 'react';
import { LanguageProvider } from '@/lib/i18n/LanguageContext';
import { api } from '@/app/services/api';
import { axiosResponse } from '@/test/http';
import { InsightEvidenceEditor } from './InsightEvidenceEditor';
import { InsightAssignmentForm } from './InsightAssignmentForm';
import type { Evidence, InsightDetail } from '@/lib/insights';

vi.mock('@/app/services/api', () => ({ api: { getInsightEvidenceOptions: vi.fn() } }));

it('searches within the project and edits evidence locators without raw JSON', async () => {
  vi.mocked(api.getInsightEvidenceOptions).mockResolvedValue(axiosResponse({ items: [
    { label: 'Worker.run · Worker.java', evidence: { entity_id: 7, source_id: 4, file: 'Worker.java', start_line: 3 } },
  ], truncated: false }));
  function Editor() {
    const [value, setValue] = useState<Evidence>([{ file: 'Old.java', source_id: 4, start_line: 1 }]);
    return <LanguageProvider><InsightEvidenceEditor projectId={2} value={value} onChange={setValue} /><output>{JSON.stringify(value)}</output></LanguageProvider>;
  }
  render(<Editor />);
  fireEvent.click(screen.getByRole('button', { name: 'Beleg entfernen' }));
  fireEvent.change(screen.getByRole('textbox', { name: 'Beleg im Projekt suchen' }), { target: { value: 'Worker' } });
  fireEvent.click(await screen.findByRole('button', { name: /Beleg hinzufügen · Worker.run/ }));
  await waitFor(() => expect(api.getInsightEvidenceOptions).toHaveBeenCalledWith(2, 'Worker', 'code'));
  expect(screen.getByRole('spinbutton', { name: 'Von Zeile 1' }).getAttribute('value')).toBe('3');
  fireEvent.change(screen.getByRole('spinbutton', { name: 'Bis Zeile 1' }), { target: { value: '6' } });
  expect(screen.getByRole('status').textContent).toContain('"end_line":6');
});

it('saves assignment against a separate workflow revision', () => {
  const save = vi.fn();
  const insight = { revision: 5, work_revision: 2, owner_id: null, reviewer_id: null, priority: 1, due_at: null } as InsightDetail;
  render(<LanguageProvider><InsightAssignmentForm insight={insight} assignees={{ items: [
    { id: 2, name: 'Owner', can_review: false }, { id: 3, name: 'Reviewer', can_review: true },
  ], can_manage: true, truncated: false }} save={save} busy={false} /></LanguageProvider>);
  fireEvent.change(screen.getByLabelText('Verantwortlich'), { target: { value: '2' } });
  fireEvent.change(screen.getByLabelText('Prüfer'), { target: { value: '3' } });
  fireEvent.change(screen.getByLabelText('Priorität'), { target: { value: '3' } });
  fireEvent.click(screen.getByRole('button', { name: 'Zuständigkeit speichern' }));
  expect(save).toHaveBeenCalledWith({ expected_revision: 5, expected_work_revision: 2, owner_id: 2, reviewer_id: 3, priority: 3, due_at: null });
});
