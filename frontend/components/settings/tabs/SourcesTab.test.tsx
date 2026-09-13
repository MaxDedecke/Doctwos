import type { KnowledgeSource } from '@/types/domain';
import { axiosResponse } from '@/test/http';
import { createSettingsContextValue } from '@/test/settingsContext';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import React from 'react';

const apiMocks = vi.hoisted(() => ({
  syncKnowledgeSource: vi.fn(),
  reindexKnowledgeSource: vi.fn(),
  deleteKnowledgeSource: vi.fn(),
  updateKnowledgeSourceInterval: vi.fn(),
  updateKnowledgeSourceContextNote: vi.fn(),
}));

vi.mock('@/app/services/api', () => ({ API_URL: 'http://api.test', api: apiMocks }));
vi.mock('@/lib/i18n/LanguageContext', () => ({
  useLanguage: () => ({
    language: 'de',
    t: (key: string, values?: Record<string, string | number>) => {
      if (values?.count !== undefined) return `${key}:${values.count}`;
      if (values?.name !== undefined) return `${key}:${values.name}`;
      return key;
    },
  }),
}));
vi.mock('@/lib/FeaturesContext', () => ({
  useFeatures: () => ({ connectors: { confluence: true, jira: true, local: true, folderwatch: true, webdav: false } }),
}));

let settingsValue = createSettingsContextValue();
vi.mock('@/components/settings/SettingsContext', () => ({
  useSettings: () => settingsValue,
}));

import { SourcesTab } from './SourcesTab';

const gitSource = (overrides: Partial<KnowledgeSource> = {}): KnowledgeSource => ({
  id: 1,
  name: 'Mein Repo',
  type: 'git',
  project_id: null,
  sync_status: null,
  sync_interval_minutes: 60,
  ...overrides,
});

const baseProps = {
  selectedSourceRepoId: 'all',
  setSelectedSourceRepoId: vi.fn(),
  onSetupSource: vi.fn(),
  onAttachGit: vi.fn(),
};

describe('SourcesTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    settingsValue = createSettingsContextValue({ connectedSources: [gitSource()] });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('shows the syncing status for a source that is currently syncing', () => {
    settingsValue = createSettingsContextValue({ connectedSources: [gitSource({ sync_status: 'syncing' })] });
    render(<SourcesTab {...baseProps} />);
    expect(screen.getByText('settings.logsTab.statusSyncingDefault')).toBeTruthy();
  });

  it('shows the error status for a source that failed to sync', () => {
    settingsValue = createSettingsContextValue({ connectedSources: [gitSource({ sync_status: 'error' })] });
    render(<SourcesTab {...baseProps} />);
    expect(screen.getByText('settings.logsTab.statusErrorLabel')).toBeTruthy();
  });

  it('shows the success status for a source with a last sync timestamp', () => {
    settingsValue = createSettingsContextValue({ connectedSources: [gitSource({ last_synced_at: '2026-09-01T10:00:00Z' })] });
    render(<SourcesTab {...baseProps} />);
    expect(screen.getByText('settings.logsTab.statusSuccess')).toBeTruthy();
  });

  it('shows the ready status for a source that has never synced', () => {
    render(<SourcesTab {...baseProps} />);
    expect(screen.getByText('settings.logsTab.statusReady')).toBeTruthy();
  });

  it('triggers a sync for exactly the clicked source', async () => {
    apiMocks.syncKnowledgeSource.mockResolvedValue(axiosResponse({}));
    settingsValue = createSettingsContextValue({
      connectedSources: [gitSource({ id: 1, name: 'Repo A' }), gitSource({ id: 2, name: 'Repo B' })],
    });
    render(<SourcesTab {...baseProps} />);

    fireEvent.click(screen.getAllByTitle('settings.sourcesTab.syncSourceTitle')[1]);
    await waitFor(() => expect(apiMocks.syncKnowledgeSource).toHaveBeenCalledWith(2));
    expect(apiMocks.syncKnowledgeSource).toHaveBeenCalledOnce();
  });

  it('refuses to sync a mock Confluence source and never calls the API', () => {
    settingsValue = createSettingsContextValue({
      connectedSources: [gitSource({ id: 'conf-init-1', type: 'confluence' })],
    });
    render(<SourcesTab {...baseProps} />);
    fireEvent.click(screen.getByTitle('settings.sourcesTab.syncSourceTitle'));
    expect(apiMocks.syncKnowledgeSource).not.toHaveBeenCalled();
    expect(settingsValue.showToast).toHaveBeenCalledWith('settings.toast.mockSyncNotAllowed', 'error');
  });

  it('only offers full reindex to admins, and only for git sources', () => {
    settingsValue = createSettingsContextValue({
      connectedSources: [gitSource()],
      currentUser: { id: 1, username: 'user', is_admin: false },
    });
    render(<SourcesTab {...baseProps} />);
    expect(screen.queryByTitle('settings.sourcesTab.fullReindexTitle')).toBeNull();
  });

  it('asks for confirmation before a full reindex, and aborts if declined', () => {
    vi.stubGlobal('confirm', vi.fn(() => false));
    render(<SourcesTab {...baseProps} />);
    fireEvent.click(screen.getByTitle('settings.sourcesTab.fullReindexTitle'));
    expect(apiMocks.reindexKnowledgeSource).not.toHaveBeenCalled();
  });

  it('triggers a full reindex for exactly the clicked source once confirmed', async () => {
    vi.stubGlobal('confirm', vi.fn(() => true));
    apiMocks.reindexKnowledgeSource.mockResolvedValue(axiosResponse({}));
    settingsValue = createSettingsContextValue({
      connectedSources: [gitSource({ id: 1, name: 'Repo A' }), gitSource({ id: 2, name: 'Repo B' })],
    });
    render(<SourcesTab {...baseProps} />);

    fireEvent.click(screen.getAllByTitle('settings.sourcesTab.fullReindexTitle')[1]);
    await waitFor(() => expect(apiMocks.reindexKnowledgeSource).toHaveBeenCalledWith(2));
    expect(apiMocks.reindexKnowledgeSource).toHaveBeenCalledOnce();
  });

  it('asks for confirmation before deleting a source, and aborts if declined', () => {
    vi.stubGlobal('confirm', vi.fn(() => false));
    render(<SourcesTab {...baseProps} />);
    fireEvent.click(screen.getByTitle('settings.sourcesTab.deleteInstanceTitle'));
    expect(apiMocks.deleteKnowledgeSource).not.toHaveBeenCalled();
  });

  it('deletes exactly the clicked source once confirmed', async () => {
    vi.stubGlobal('confirm', vi.fn(() => true));
    apiMocks.deleteKnowledgeSource.mockResolvedValue(axiosResponse({}));
    settingsValue = createSettingsContextValue({
      connectedSources: [gitSource({ id: 1, name: 'Repo A' }), gitSource({ id: 2, name: 'Repo B' })],
    });
    render(<SourcesTab {...baseProps} />);

    fireEvent.click(screen.getAllByTitle('settings.sourcesTab.deleteInstanceTitle')[1]);
    await waitFor(() => expect(apiMocks.deleteKnowledgeSource).toHaveBeenCalledWith(2));
    expect(apiMocks.deleteKnowledgeSource).toHaveBeenCalledOnce();
    expect(settingsValue.setConnectedSources).toHaveBeenCalledOnce();
  });

  it('reports a failed deletion without removing the source from the list', async () => {
    vi.stubGlobal('confirm', vi.fn(() => true));
    apiMocks.deleteKnowledgeSource.mockRejectedValue(new Error('boom'));
    render(<SourcesTab {...baseProps} />);

    fireEvent.click(screen.getByTitle('settings.sourcesTab.deleteInstanceTitle'));
    await waitFor(() => expect(settingsValue.showToast).toHaveBeenCalledWith('settings.toast.sourceDeleteFailed', 'error', expect.any(Error)));
    expect(settingsValue.setConnectedSources).not.toHaveBeenCalled();
  });

  it('updates the sync interval for exactly the changed source', async () => {
    apiMocks.updateKnowledgeSourceInterval.mockResolvedValue(axiosResponse({}));
    render(<SourcesTab {...baseProps} />);

    fireEvent.change(screen.getByTitle('settings.sourcesTab.syncIntervalTitle'), { target: { value: '1440' } });
    await waitFor(() => expect(apiMocks.updateKnowledgeSourceInterval).toHaveBeenCalledWith(1, 1440));
  });

  it('rolls the interval back to the previous value if the update fails', async () => {
    apiMocks.updateKnowledgeSourceInterval.mockRejectedValue(new Error('boom'));
    render(<SourcesTab {...baseProps} />);

    fireEvent.change(screen.getByTitle('settings.sourcesTab.syncIntervalTitle'), { target: { value: '1440' } });
    await waitFor(() => expect(settingsValue.showToast).toHaveBeenCalledWith('settings.toast.intervalUpdateFailed', 'error', expect.any(Error)));
    // Optimistisches Update, dann Rollback: der letzte setConnectedSources-Aufruf muss die ursprüngliche Liste sein.
    const calls = (settingsValue.setConnectedSources as ReturnType<typeof vi.fn>).mock.calls;
    expect(calls[calls.length - 1][0]).toEqual([gitSource()]);
  });

  it('saves a changed context note on blur, but skips the request when unchanged', async () => {
    apiMocks.updateKnowledgeSourceContextNote.mockResolvedValue(axiosResponse({}));
    render(<SourcesTab {...baseProps} />);
    const textarea = screen.getByPlaceholderText('settings.sourcesTab.contextNotePlaceholder');

    fireEvent.blur(textarea, { target: { value: '' } });
    expect(apiMocks.updateKnowledgeSourceContextNote).not.toHaveBeenCalled();

    fireEvent.change(textarea, { target: { value: 'Fachjargon' } });
    fireEvent.blur(textarea);
    await waitFor(() => expect(apiMocks.updateKnowledgeSourceContextNote).toHaveBeenCalledWith(1, 'Fachjargon'));
  });

  it('never offers a delete-allowlist rejection silently: a failed context note update shows a toast', async () => {
    apiMocks.updateKnowledgeSourceContextNote.mockRejectedValue(new Error('boom'));
    render(<SourcesTab {...baseProps} />);
    const textarea = screen.getByPlaceholderText('settings.sourcesTab.contextNotePlaceholder');

    fireEvent.change(textarea, { target: { value: 'Fachjargon' } });
    fireEvent.blur(textarea);
    await waitFor(() => expect(settingsValue.showToast).toHaveBeenCalledWith('settings.toast.contextNoteUpdateFailed', 'error', expect.any(Error)));
  });

  it('filters connected sources to the selected project', () => {
    settingsValue = createSettingsContextValue({
      projects: [{ id: 5, name: 'Projekt 5' }],
      connectedSources: [
        gitSource({ id: 1, name: 'Allgemeine Quelle', project_id: null }),
        gitSource({ id: 2, name: 'Projekt-Quelle', project_id: 5 }),
      ],
    });
    render(<SourcesTab {...baseProps} selectedSourceRepoId="5" />);
    // Erscheint doppelt: einmal als Netzwerk-Graph-Knoten, einmal als Karte.
    expect(screen.getAllByText('Projekt-Quelle').length).toBeGreaterThan(0);
    expect(screen.queryByText('Allgemeine Quelle')).toBeNull();
  });
});
