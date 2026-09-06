import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import React from 'react';

const apiMocks = vi.hoisted(() => ({
  getKnowledgeSources: vi.fn().mockResolvedValue({ data: [] }),
  getMcpToolAuditLogs: vi.fn().mockResolvedValue({ data: { entries: [], retention_days: 90 } }),
  getNegativeChatFeedback: vi.fn().mockResolvedValue({ data: { entries: [] } }),
  getFeedbackDiagnosticSettings: vi.fn(),
  updateFeedbackDiagnosticSettings: vi.fn(),
  deleteFeedbackDiagnosticCases: vi.fn().mockResolvedValue({ data: { deleted: 3 } }),
}));

vi.mock('@/app/services/api', () => ({ API_URL: 'http://api.test', api: apiMocks }));
vi.mock('@/components/settings/SettingsContext', () => ({
  useSettings: () => ({
    theme: 'dark', backendStatus: 'online', currentUser: { id: 1, username: 'admin', is_admin: true },
    connectedSources: [], setConnectedSources: vi.fn(), showToast: vi.fn(),
  }),
}));
vi.mock('@/lib/i18n/LanguageContext', () => ({ useLanguage: () => ({ language: 'de', t: (key: string, values?: Record<string, string | number>) => values?.count !== undefined ? `${key}:${values.count}` : key }) }));

import { LogsSettingsTab } from './LogsSettingsTab';

const disabledSettings = { collection_enabled: false, support_export_enabled: false, retention_days: 90, updated_at: null };

describe('LogsSettingsTab feedback diagnostics', () => {
  afterEach(() => {
    vi.clearAllMocks();
    vi.unstubAllGlobals();
  });

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
});
