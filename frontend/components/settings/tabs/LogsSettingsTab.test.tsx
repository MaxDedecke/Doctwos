import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import React from 'react';

const { apiMocks, showToastMock, settingsState, defaultCurrentUser } = vi.hoisted(() => {
  const showToastMock = vi.fn();
  const defaultCurrentUser = { id: 1, username: 'admin', is_admin: true };
  const settingsState = {
    theme: 'dark' as const,
    backendStatus: 'connected' as const,
    currentUser: { ...defaultCurrentUser },
    connectedSources: [] as unknown[],
    // Echte Zuweisung statt no-op: refreshKnowledgeSources() im Tab ruft das hier
    // synchron auf, und die Quellenliste soll im nächsten Render sichtbar sein —
    // genau wie im echten SettingsContext.
    setConnectedSources: vi.fn((sources: unknown[]) => { settingsState.connectedSources = sources; }),
    showToast: showToastMock,
  };
  return { showToastMock, defaultCurrentUser, settingsState, apiMocks: {
    getKnowledgeSources: vi.fn().mockResolvedValue({ data: [] }),
    getMcpToolAuditLogs: vi.fn().mockResolvedValue({ data: { entries: [], retention_days: 90 } }),
    getNegativeChatFeedback: vi.fn().mockResolvedValue({ data: { entries: [] } }),
    getFeedbackDiagnosticSettings: vi.fn().mockResolvedValue({ data: null }),
    updateFeedbackDiagnosticSettings: vi.fn(),
    deleteFeedbackDiagnosticCases: vi.fn().mockResolvedValue({ data: { deleted: 3 } }),
    generateDiagnosticsBundle: vi.fn().mockResolvedValue({ data: {} }),
    getDiagnosticsRuns: vi.fn().mockResolvedValue({ data: [] }),
    syncKnowledgeSource: vi.fn().mockResolvedValue({ data: {} }),
  } };
});

vi.mock('@/app/services/api', () => ({ API_URL: 'http://api.test', api: apiMocks }));
vi.mock('@/components/settings/SettingsContext', () => ({ useSettings: () => settingsState }));
vi.mock('@/lib/i18n/LanguageContext', () => ({
  useLanguage: () => ({
    language: 'de',
    t: (key: string, values?: Record<string, string | number>) => {
      if (values?.count !== undefined) return `${key}:${values.count}`;
      if (values?.id !== undefined) return `${key}:${values.id}`;
      return key;
    },
  }),
}));

import { LogsSettingsTab } from './LogsSettingsTab';

const disabledSettings = { collection_enabled: false, support_export_enabled: false, retention_days: 90, updated_at: null };

afterEach(() => {
  vi.clearAllMocks();
  vi.unstubAllGlobals();
  settingsState.currentUser = { ...defaultCurrentUser };
  settingsState.connectedSources = [];
});

describe('LogsSettingsTab feedback diagnostics', () => {
  it('keeps export locked until collection and explicit export consent are enabled', async () => {
    apiMocks.getFeedbackDiagnosticSettings.mockResolvedValue({ data: disabledSettings });
    apiMocks.updateFeedbackDiagnosticSettings.mockImplementation(async (data) => ({ data: { ...data, updated_at: null } }));
    render(<LogsSettingsTab />);

    const [collect, allowExport] = await screen.findAllByRole('checkbox');
    expect((collect as HTMLInputElement).checked).toBe(false);
    expect((allowExport as HTMLInputElement).disabled).toBe(true);
    expect(screen.queryByText('settings.logsTab.feedbackDiagnosticsDownload')).toBeNull();

    fireEvent.click(collect);
    await waitFor(() => expect(apiMocks.updateFeedbackDiagnosticSettings).toHaveBeenCalledWith({ collection_enabled: true, support_export_enabled: false, retention_days: 90 }));
    await waitFor(() => expect((allowExport as HTMLInputElement).disabled).toBe(false));
    fireEvent.click(allowExport);
    await waitFor(() => expect(apiMocks.updateFeedbackDiagnosticSettings).toHaveBeenLastCalledWith({ collection_enabled: true, support_export_enabled: true, retention_days: 90 }));
  });

  it('offers the manual download only after both consents and confirms deletion', async () => {
    apiMocks.getFeedbackDiagnosticSettings.mockResolvedValue({ data: { ...disabledSettings, collection_enabled: true, support_export_enabled: true } });
    vi.stubGlobal('confirm', vi.fn(() => true));
    render(<LogsSettingsTab />);

    expect(await screen.findByText('settings.logsTab.feedbackDiagnosticsDownload')).toBeTruthy();
    fireEvent.click(screen.getByText('settings.logsTab.feedbackDiagnosticsDelete'));
    await waitFor(() => expect(apiMocks.deleteFeedbackDiagnosticCases).toHaveBeenCalledOnce());
  });

  it('shows the anonymized session label instead of any identifying session data (O-086)', async () => {
    apiMocks.getFeedbackDiagnosticSettings.mockResolvedValue({ data: disabledSettings });
    apiMocks.getNegativeChatFeedback.mockResolvedValue({
      data: {
        entries: [
          { message_id: 1, session_label: 1, question: 'Frage A', answer: 'Antwort A', sources_json: [], metadata_json: {}, created_at: null },
          { message_id: 2, session_label: 2, question: 'Frage B', answer: 'Antwort B', sources_json: [], metadata_json: {}, created_at: null },
        ],
        total: 2,
        limit: 100,
      },
    });
    render(<LogsSettingsTab />);

    expect(await screen.findByText('settings.logsTab.feedbackSession:1')).toBeTruthy();
    expect(screen.getByText('settings.logsTab.feedbackSession:2')).toBeTruthy();
    // Nirgends im gerenderten Auszug taucht ein Hinweis auf, wer die Sitzung
    // geführt hat — nur Frage/Antwort und das anonyme, laufende Label.
    expect(screen.queryByText(/session_id/i)).toBeNull();
  });
});

describe('LogsSettingsTab diagnostics bundle (O-100)', () => {
  it('shows the waiting state right after starting a diagnostics bundle', async () => {
    apiMocks.getDiagnosticsRuns.mockResolvedValue({ data: [{ id: 7, status: 'running' }] });
    render(<LogsSettingsTab />);
    fireEvent.click(await screen.findByText('settings.logsTab.diagnosticsGenerate'));

    await waitFor(() => expect(apiMocks.generateDiagnosticsBundle).toHaveBeenCalledOnce());
    expect(await screen.findByText('settings.logsTab.diagnosticsGenerating')).toBeTruthy();
    expect(screen.queryByText('settings.logsTab.diagnosticsDownload')).toBeNull();
  });

  it('offers the download link once the polled run completes', async () => {
    apiMocks.getDiagnosticsRuns.mockResolvedValue({ data: [{ id: 7, status: 'completed' }] });
    render(<LogsSettingsTab />);
    fireEvent.click(await screen.findByText('settings.logsTab.diagnosticsGenerate'));
    await waitFor(() => expect(apiMocks.generateDiagnosticsBundle).toHaveBeenCalledOnce());

    // Das Polling wartet echte 3s (fixer Wert im Tab) — real, nicht gefaked:
    // Fake-Timer kollidieren mit React/testing-librarys eigener Async-Schleife.
    const downloadLink = await waitFor(() => screen.getByText('settings.logsTab.diagnosticsDownload'), { timeout: 4500 });
    expect(downloadLink.closest('a')!.getAttribute('href')).toBe('http://api.test/diagnostics/runs/7/download');
    expect(screen.getByText('settings.logsTab.diagnosticsGenerate')).toBeTruthy();
  }, 8000);

  it('surfaces a failed run as an error toast without offering a download link', async () => {
    apiMocks.getDiagnosticsRuns.mockResolvedValue({ data: [{ id: 8, status: 'failed' }] });
    render(<LogsSettingsTab />);
    fireEvent.click(await screen.findByText('settings.logsTab.diagnosticsGenerate'));
    await waitFor(() => expect(apiMocks.generateDiagnosticsBundle).toHaveBeenCalledOnce());

    await waitFor(() => expect(showToastMock).toHaveBeenCalledWith('settings.logsTab.diagnosticsFailedToast', 'error'), { timeout: 4500 });
    expect(screen.queryByText('settings.logsTab.diagnosticsDownload')).toBeNull();
    expect(screen.getByText('settings.logsTab.diagnosticsGenerate')).toBeTruthy();
  }, 8000);

  it('shows an error toast when the bundle cannot even be started', async () => {
    apiMocks.generateDiagnosticsBundle.mockRejectedValue(new Error('boom'));
    render(<LogsSettingsTab />);
    fireEvent.click(await screen.findByText('settings.logsTab.diagnosticsGenerate'));

    await waitFor(() => expect(showToastMock).toHaveBeenCalledWith('settings.logsTab.diagnosticsStartFailedToast', 'error', expect.any(Error)));
    expect(apiMocks.getDiagnosticsRuns).not.toHaveBeenCalled();
    expect(screen.getByText('settings.logsTab.diagnosticsGenerate')).toBeTruthy();
  });
});

describe('LogsSettingsTab MCP audit trail (O-100, touches O-073)', () => {
  it('renders success/error entries including the trace id and lets an admin refresh them', async () => {
    apiMocks.getMcpToolAuditLogs
      .mockResolvedValueOnce({
        data: {
          entries: [
            { id: 1, tool_name: 'read_file', server_name: 'fs', status: 'success', user_name: 'max', duration_ms: 42, project_name: 'Doctus', trace_id: 'trace-abc', arguments: { path: 'x.cbl' }, created_at: null },
            { id: 2, tool_name: 'run_query', server_name: 'db', status: 'error', user_name: 'max', duration_ms: 10, trace_id: undefined, arguments: {}, error_message: 'timeout', created_at: null },
          ],
          retention_days: 30,
        },
      })
      .mockResolvedValueOnce({ data: { entries: [], retention_days: 30 } });

    render(<LogsSettingsTab />);

    expect(await screen.findByText('read_file')).toBeTruthy();
    expect(screen.getByText('settings.logsTab.mcpAuditSuccess')).toBeTruthy();
    expect(screen.getByText('settings.logsTab.mcpAuditError')).toBeTruthy();
    // O-073: die Trace-ID muss im Audit-Eintrag sichtbar sein, damit Support
    // damit gezielt in den Logs suchen kann — nur beim Eintrag, der eine hat.
    expect(screen.getByText('trace: trace-abc')).toBeTruthy();
    expect(screen.getByText('timeout')).toBeTruthy();

    fireEvent.click(screen.getByText('settings.logsTab.mcpAuditRefresh'));
    await waitFor(() => expect(apiMocks.getMcpToolAuditLogs).toHaveBeenCalledTimes(2));
    expect(await screen.findByText('settings.logsTab.mcpAuditEmpty')).toBeTruthy();
  });

  it('shows an empty-state placeholder when nothing has been audited yet', async () => {
    apiMocks.getMcpToolAuditLogs.mockResolvedValue({ data: { entries: [], retention_days: 30 } });
    render(<LogsSettingsTab />);
    expect(await screen.findByText('settings.logsTab.mcpAuditEmpty')).toBeTruthy();
  });
});

describe('LogsSettingsTab admin gating (O-100)', () => {
  it('hides every admin-only surface from a non-admin user and skips their admin-only requests', async () => {
    settingsState.currentUser = { id: 2, username: 'viewer', is_admin: false };
    apiMocks.getKnowledgeSources.mockResolvedValue({
      data: [{ id: 9, name: 'Mainframe SCM', type: 'git', sync_status: 'completed', last_synced_at: null }],
    });

    render(<LogsSettingsTab />);

    // Der nicht-admin-gebundene Teil (Quellen-Logs) lädt weiterhin normal.
    expect(await screen.findByText('Mainframe SCM')).toBeTruthy();

    expect(screen.queryByText('settings.logsTab.diagnosticsTitle')).toBeNull();
    expect(screen.queryByText('settings.logsTab.mcpAuditTitle')).toBeNull();
    expect(screen.queryByText('settings.logsTab.feedbackTitle')).toBeNull();
    expect(screen.queryByText('settings.logsTab.feedbackDiagnosticsTitle')).toBeNull();

    expect(apiMocks.getMcpToolAuditLogs).not.toHaveBeenCalled();
    expect(apiMocks.getNegativeChatFeedback).not.toHaveBeenCalled();
    expect(apiMocks.getFeedbackDiagnosticSettings).not.toHaveBeenCalled();
    expect(apiMocks.generateDiagnosticsBundle).not.toHaveBeenCalled();
  });
});

describe('LogsSettingsTab knowledge source sync (O-100)', () => {
  it('triggers a manual sync and reports the started toast', async () => {
    apiMocks.getKnowledgeSources.mockResolvedValue({
      data: [{ id: 5, name: 'Mainframe SCM', type: 'git', sync_status: 'completed', last_synced_at: null }],
    });

    render(<LogsSettingsTab />);
    const syncButton = await screen.findByTitle('settings.logsTab.syncNowTitle');
    fireEvent.click(syncButton);

    await waitFor(() => expect(apiMocks.syncKnowledgeSource).toHaveBeenCalledWith(5));
    await waitFor(() => expect(showToastMock).toHaveBeenCalledWith('settings.logsTab.syncStartedToast', 'success'));
  });

  it('shows an error toast when triggering a sync fails', async () => {
    apiMocks.getKnowledgeSources.mockResolvedValue({
      data: [{ id: 6, name: 'DB2 Katalog', type: 'db', sync_status: 'error', last_synced_at: null }],
    });
    apiMocks.syncKnowledgeSource.mockRejectedValue(new Error('down'));

    render(<LogsSettingsTab />);
    const syncButton = await screen.findByTitle('settings.logsTab.syncNowTitle');
    fireEvent.click(syncButton);

    await waitFor(() => expect(showToastMock).toHaveBeenCalledWith('settings.logsTab.syncStartFailedToast', 'error', expect.any(Error)));
  });
});
