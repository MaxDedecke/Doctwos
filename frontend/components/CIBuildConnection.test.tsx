import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { api } from '@/app/services/api';
import { LanguageProvider } from '@/lib/i18n/LanguageContext';
import { axiosResponse } from '@/test/http';
import { CIBuildConnection } from './CIBuildConnection';

vi.mock('@/app/services/api', () => ({ api: {
  getCITokens: vi.fn(), createCIToken: vi.fn(), revokeCIToken: vi.fn(),
} }));

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.getCITokens).mockResolvedValue(axiosResponse({
    can_manage: true, sources: [{ id: 8, name: 'repo', branch: 'main' }], tokens: [],
  }));
  vi.mocked(api.createCIToken).mockResolvedValue(axiosResponse({ token: 'dct_ci_secret_once' }));
});

it('issues a source-bound credential and clears the displayed secret on close', async () => {
  render(<LanguageProvider><CIBuildConnection projectId={3} theme="dark" /></LanguageProvider>);
  fireEvent.click(screen.getByText('CI-Anbindung verwalten'));
  const name = await screen.findByLabelText('Name des CI-Zugangs');
  fireEvent.change(name, { target: { value: 'GitHub main' } });
  fireEvent.click(screen.getByRole('button', { name: 'CI-Token erstellen' }));
  expect(await screen.findByDisplayValue('dct_ci_secret_once')).toBeTruthy();
  expect(api.createCIToken).toHaveBeenCalledWith(3, { source_id: 8, name: 'GitHub main' });
  fireEvent.click(screen.getByText('CI-Anbindung verwalten'));
  await waitFor(() => expect(screen.queryByDisplayValue('dct_ci_secret_once')).toBeNull());
});

it('explains management permissions to a project member', async () => {
  vi.mocked(api.getCITokens).mockResolvedValue(axiosResponse({ can_manage: false, sources: [], tokens: [] }));
  render(<LanguageProvider><CIBuildConnection projectId={3} theme="light" /></LanguageProvider>);
  fireEvent.click(screen.getByText('CI-Anbindung verwalten'));
  expect(await screen.findByText(/von Projekt-Admins verwaltet/)).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'CI-Token erstellen' })).toBeNull();
});
