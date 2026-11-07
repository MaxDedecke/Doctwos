import { axiosResponse } from '@/test/http';
import { api } from '@/app/services/api';
import { LanguageProvider } from '@/lib/i18n/LanguageContext';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { SourceProfileDialog } from './SourceProfileDialog';

vi.mock('@/app/services/api', () => ({
  api: { getPreflight: vi.fn(), getBuildProfile: vi.fn(), putBuildProfile: vi.fn() },
}));

const report = {
  source_id: 4,
  files: { total: 3, by_language: { cobol: { complete: 2, partial: 1 } }, encodings: { cp273: 3 } },
  parser_gaps: [{ pattern: "mismatched input 'GENERATE'", occurrences: 5, files: 1, example: 'app/A.cbl:18' }],
  copybooks: { ambiguous: [], missing: [{ name: 'DFHAID', references: 2, example_file: 'app/A.cbl' }], duplicate_copybook_names: 0 },
  hints: [{ code: 'ENCODING_EBCDIC', message: '3 Quelldatei(en) wurden als EBCDIC erkannt.' }],
};
const profile = { source_id: 4, build_profile: { source: { encoding: 'CCSID-1141' }, paths: {} }, language_paths: null };

function open(canEdit: boolean) {
  vi.mocked(api.getPreflight).mockResolvedValue(axiosResponse(report));
  vi.mocked(api.getBuildProfile).mockResolvedValue(axiosResponse(profile));
  render(<LanguageProvider><SourceProfileDialog source={{ id: 4, name: 'Kernbank' }} canEdit={canEdit} onClose={vi.fn()} /></LanguageProvider>);
}

describe('SourceProfileDialog', () => {
  afterEach(() => vi.clearAllMocks());

  it('zeigt Hinweise, Status je Sprache, Grammatiklücken und offene COPY-Namen', async () => {
    open(false);
    expect(await screen.findByText('3 Quelldatei(en) wurden als EBCDIC erkannt.')).toBeTruthy();
    expect(screen.getByText("mismatched input 'GENERATE'")).toBeTruthy();
    expect(screen.getByText('DFHAID')).toBeTruthy();
    expect(screen.getByText(/cp273 3/)).toBeTruthy();
  });

  it('speichert ein geändertes Profil und meldet unlesbare Zeilen vor dem Senden', async () => {
    vi.mocked(api.putBuildProfile).mockResolvedValue(axiosResponse({ ...profile, build_profile: { source: { encoding: 'CCSID-1141', copy_search_order: ['copy/team'] }, paths: {} } }));
    open(true);
    fireEvent.click(await screen.findByRole('tab', { name: 'Buildprofil' }));
    expect((screen.getByPlaceholderText('CCSID-1141') as HTMLInputElement).value).toBe('CCSID-1141');

    fireEvent.change(screen.getByPlaceholderText('ENV=PROD'), { target: { value: 'ENV' } });
    fireEvent.click(screen.getByRole('button', { name: 'Speichern' }));
    expect(screen.getByRole('alert').textContent).toContain('„ENV“');
    expect(api.putBuildProfile).not.toHaveBeenCalled();

    fireEvent.change(screen.getByPlaceholderText('ENV=PROD'), { target: { value: '' } });
    fireEvent.change(screen.getByLabelText(/COPY-Suchreihenfolge/), { target: { value: 'copy/team' } });
    fireEvent.click(screen.getByRole('button', { name: 'Speichern' }));
    await waitFor(() => expect(api.putBuildProfile).toHaveBeenCalledWith(4, {
      build_profile: { source: { encoding: 'CCSID-1141', copy_search_order: ['copy/team'] }, paths: {} },
      language_paths: null,
    }));
    expect(await screen.findByText('Gespeichert, gilt ab dem nächsten Sync.')).toBeTruthy();
  });

  it('lässt Nicht-Administratoren nur lesen', async () => {
    open(false);
    fireEvent.click(await screen.findByRole('tab', { name: 'Buildprofil' }));
    expect((screen.getByPlaceholderText('CCSID-1141') as HTMLInputElement).disabled).toBe(true);
    expect((screen.getByRole('button', { name: 'Speichern' }) as HTMLButtonElement).disabled).toBe(true);
  });
});
