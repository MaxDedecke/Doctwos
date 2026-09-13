import { axiosResponse } from '@/test/http';
import { createSettingsContextValue } from '@/test/settingsContext';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import React from 'react';

const apiMocks = vi.hoisted(() => ({
  createKnowledgeSource: vi.fn(),
  createFolderWatchSource: vi.fn(),
  uploadLocalDocument: vi.fn(),
  testConnector: vi.fn(),
}));

vi.mock('@/app/services/api', () => ({ API_URL: 'http://api.test', api: apiMocks }));
vi.mock('@/lib/i18n/LanguageContext', () => ({
  useLanguage: () => ({
    t: (key: string, values?: Record<string, string | number>) =>
      values?.type !== undefined ? `${key}:${values.type}` : key,
  }),
}));

let settingsValue = createSettingsContextValue();
vi.mock('@/components/settings/SettingsContext', () => ({
  useSettings: () => settingsValue,
}));

// GitSetupTab ist selbst umfangreich und hat einen eigenen Punkt (O-095) -- hier reicht
// ein Stub, der die durchgereichten Props sichtbar macht, statt den echten Wizard mitzuziehen.
vi.mock('./GitSetupTab', () => ({
  GitSetupTab: ({ targetProjectId, onDone }: { targetProjectId: number | null; onDone: () => void }) => (
    <div>
      <span data-testid="git-target-project-id">{String(targetProjectId)}</span>
      <button onClick={onDone}>git-onDone</button>
    </div>
  ),
}));

import { SourcesSetupTab } from './SourcesSetupTab';

/** Wie in JobCenter.test.tsx: ein axios-Fehler mit optionalem FastAPI-`detail`-Feld. */
function axiosError(detail?: string) {
  return Object.assign(new Error('request failed'), {
    isAxiosError: true,
    response: { status: 400, data: detail ? { detail } : {} },
  });
}

const baseProps = {
  activeSourceType: 'Confluence',
  selectedSourceRepoId: 'all',
  onDone: vi.fn(),
};

describe('SourcesSetupTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    settingsValue = createSettingsContextValue();
  });

  describe('Konnektorauswahl', () => {
    it('renders the Git wizard for the Git connector, passing through the target project', () => {
      render(<SourcesSetupTab {...baseProps} activeSourceType="Git" selectedSourceRepoId="5" />);
      expect(screen.getByTestId('git-target-project-id').textContent).toBe('5');
    });

    it('passes null as the target project for Git when no project is selected', () => {
      render(<SourcesSetupTab {...baseProps} activeSourceType="Git" selectedSourceRepoId="all" />);
      expect(screen.getByTestId('git-target-project-id').textContent).toBe('null');
    });

    it('shows the integration form for Confluence', () => {
      render(<SourcesSetupTab {...baseProps} activeSourceType="Confluence" />);
      expect(screen.getByText('settings.sourcesSetup.serverUrlLabel')).toBeTruthy();
      expect(screen.getByText('settings.sourcesSetup.apiTokenPasswordLabel')).toBeTruthy();
    });

    it('shows the folder-watch form for the folder-watch connector', () => {
      render(<SourcesSetupTab {...baseProps} activeSourceType="settings.sourcesTab.types.folderwatch.name" />);
      expect(screen.getByText('settings.sourcesSetup.folderNameLabel')).toBeTruthy();
      expect(screen.getByText('settings.sourcesSetup.folderPathLabel')).toBeTruthy();
    });

    it('shows the upload dropzone for the local-documents connector', () => {
      render(<SourcesSetupTab {...baseProps} activeSourceType="settings.sourcesTab.types.local.name" />);
      expect(screen.getByText('settings.sourcesSetup.dropzoneText')).toBeTruthy();
    });
  });

  describe('Pflichtfeldvalidierung (Confluence/Jira)', () => {
    it('requires a name before connecting', () => {
      render(<SourcesSetupTab {...baseProps} />);
      fireEvent.click(screen.getByText('settings.sourcesSetup.connect'));
      expect(settingsValue.showToast).toHaveBeenCalledWith('settings.toast.nameRequired', 'error');
      expect(apiMocks.createKnowledgeSource).not.toHaveBeenCalled();
    });

    it('requires a server URL before connecting', () => {
      render(<SourcesSetupTab {...baseProps} />);
      fireEvent.change(screen.getByPlaceholderText('settings.sourcesSetup.integrationNamePlaceholder:Confluence'), { target: { value: 'Mein Confluence' } });
      fireEvent.click(screen.getByText('settings.sourcesSetup.connect'));
      expect(settingsValue.showToast).toHaveBeenCalledWith('settings.toast.serverUrlRequired', 'error');
      expect(apiMocks.createKnowledgeSource).not.toHaveBeenCalled();
    });

    it('requires an API token before connecting', () => {
      render(<SourcesSetupTab {...baseProps} />);
      fireEvent.change(screen.getByPlaceholderText('settings.sourcesSetup.integrationNamePlaceholder:Confluence'), { target: { value: 'Mein Confluence' } });
      fireEvent.change(screen.getByText('settings.sourcesSetup.serverUrlLabel').closest('div')!.querySelector('input')!, { target: { value: 'https://x.atlassian.net' } });
      fireEvent.click(screen.getByText('settings.sourcesSetup.connect'));
      expect(settingsValue.showToast).toHaveBeenCalledWith('settings.toast.apiTokenRequired', 'error');
      expect(apiMocks.createKnowledgeSource).not.toHaveBeenCalled();
    });

    it('requires a server URL and API token before testing the connection too', () => {
      render(<SourcesSetupTab {...baseProps} />);
      fireEvent.click(screen.getByText('settings.sourcesSetup.testConnection'));
      expect(settingsValue.showToast).toHaveBeenCalledWith('settings.toast.serverUrlRequired', 'error');
      expect(apiMocks.testConnector).not.toHaveBeenCalled();
    });
  });

  describe('Verbindung testen', () => {
    const fillUrlAndToken = () => {
      fireEvent.change(screen.getByText('settings.sourcesSetup.serverUrlLabel').closest('div')!.querySelector('input')!, { target: { value: 'https://x.atlassian.net' } });
      fireEvent.change(screen.getByPlaceholderText('settings.sourcesSetup.tokenPlaceholder'), { target: { value: 'secret-token' } });
    };

    it('shows success and the server message when the test succeeds', async () => {
      apiMocks.testConnector.mockResolvedValue(axiosResponse({ success: true, message: 'Verbunden!' }));
      render(<SourcesSetupTab {...baseProps} />);
      fillUrlAndToken();
      fireEvent.click(screen.getByText('settings.sourcesSetup.testConnection'));

      await waitFor(() => expect(apiMocks.testConnector).toHaveBeenCalledWith({
        type: 'confluence', url: 'https://x.atlassian.net', username: undefined, token: 'secret-token',
      }));
      await waitFor(() => expect(screen.getByText('settings.sourcesSetup.connectionSuccess')).toBeTruthy());
      expect(settingsValue.showToast).toHaveBeenCalledWith('Verbunden!', 'success');
    });

    it('shows the inline error and toast when the server reports failure', async () => {
      apiMocks.testConnector.mockResolvedValue(axiosResponse({ success: false, message: 'Falscher Token' }));
      render(<SourcesSetupTab {...baseProps} />);
      fillUrlAndToken();
      fireEvent.click(screen.getByText('settings.sourcesSetup.testConnection'));

      await waitFor(() => expect(screen.getByText('Falscher Token')).toBeTruthy());
      expect(settingsValue.showToast).toHaveBeenCalledWith('Falscher Token', 'error');
    });

    it('surfaces the server error detail, not a generic message, on a network failure', async () => {
      apiMocks.testConnector.mockRejectedValue(axiosError('Zeitüberschreitung beim Verbindungsaufbau'));
      render(<SourcesSetupTab {...baseProps} />);
      fillUrlAndToken();
      fireEvent.click(screen.getByText('settings.sourcesSetup.testConnection'));

      await waitFor(() => expect(screen.getByText('Zeitüberschreitung beim Verbindungsaufbau')).toBeTruthy());
    });
  });

  describe('Verbinden (Confluence/Jira)', () => {
    const fillRequiredFields = () => {
      fireEvent.change(screen.getByPlaceholderText('settings.sourcesSetup.integrationNamePlaceholder:Confluence'), { target: { value: 'Mein Confluence' } });
      fireEvent.change(screen.getByText('settings.sourcesSetup.serverUrlLabel').closest('div')!.querySelector('input')!, { target: { value: 'https://x.atlassian.net' } });
      fireEvent.change(screen.getByPlaceholderText('settings.sourcesSetup.tokenPlaceholder'), { target: { value: 'secret-token' } });
    };

    it('creates the source with a fallback space of ALL when none is given, and reports success', async () => {
      const created = { id: 42, name: 'Mein Confluence', type: 'confluence' };
      apiMocks.createKnowledgeSource.mockResolvedValue(axiosResponse(created));
      const onDone = vi.fn();
      render(<SourcesSetupTab {...baseProps} onDone={onDone} selectedSourceRepoId="7" />);
      fillRequiredFields();
      fireEvent.click(screen.getByText('settings.sourcesSetup.connect'));

      await waitFor(() => expect(apiMocks.createKnowledgeSource).toHaveBeenCalledWith({
        name: 'Mein Confluence',
        type: 'confluence',
        url: 'https://x.atlassian.net',
        username: null,
        token: 'secret-token',
        project_id: 7,
        spaces: ['ALL'],
      }));
      expect(settingsValue.setConnectedSources).toHaveBeenCalledOnce();
      expect(settingsValue.showToast).toHaveBeenCalledWith('settings.toast.sourceConnected:Confluence', 'success');
      expect(onDone).toHaveBeenCalledOnce();
    });

    it('splits comma-separated spaces into a trimmed list', async () => {
      apiMocks.createKnowledgeSource.mockResolvedValue(axiosResponse({ id: 1 }));
      render(<SourcesSetupTab {...baseProps} />);
      fillRequiredFields();
      fireEvent.change(screen.getByPlaceholderText('settings.sourcesSetup.spacesProjectKeysPlaceholder'), { target: { value: ' ENG , OPS ,ENG' } });
      fireEvent.click(screen.getByText('settings.sourcesSetup.connect'));

      await waitFor(() => expect(apiMocks.createKnowledgeSource).toHaveBeenCalledWith(
        expect.objectContaining({ spaces: ['ENG', 'OPS', 'ENG'] })
      ));
    });

    it('reports a failed connection without calling onDone', async () => {
      apiMocks.createKnowledgeSource.mockRejectedValue(axiosError('Name bereits vergeben'));
      const onDone = vi.fn();
      render(<SourcesSetupTab {...baseProps} onDone={onDone} />);
      fillRequiredFields();
      fireEvent.click(screen.getByText('settings.sourcesSetup.connect'));

      await waitFor(() => expect(settingsValue.showToast).toHaveBeenCalledWith('Name bereits vergeben', 'error', expect.any(Error)));
      expect(onDone).not.toHaveBeenCalled();
      expect(settingsValue.setConnectedSources).not.toHaveBeenCalled();
    });
  });

  describe('Ordner-Überwachung', () => {
    const folderProps = { ...baseProps, activeSourceType: 'settings.sourcesTab.types.folderwatch.name' };

    it('disables the connect button until both name and path are filled', () => {
      render(<SourcesSetupTab {...folderProps} />);
      const connectButton = screen.getByText('settings.sourcesSetup.folderConnect').closest('button')!;
      // folderPath ist vorbelegt ("/watched"), nur der Name fehlt.
      expect(connectButton.hasAttribute('disabled')).toBe(true);
      fireEvent.change(screen.getByPlaceholderText('settings.sourcesSetup.folderNamePlaceholder'), { target: { value: 'Docs' } });
      expect(connectButton.hasAttribute('disabled')).toBe(false);
    });

    it('creates the folder-watch source, resets the form and reports success', async () => {
      apiMocks.createFolderWatchSource.mockResolvedValue(axiosResponse({ id: 3, name: 'Docs' }));
      const onDone = vi.fn();
      render(<SourcesSetupTab {...folderProps} onDone={onDone} selectedSourceRepoId="9" />);

      fireEvent.change(screen.getByPlaceholderText('settings.sourcesSetup.folderNamePlaceholder'), { target: { value: 'Docs' } });
      fireEvent.change(screen.getByPlaceholderText('settings.sourcesSetup.folderPathPlaceholder'), { target: { value: '/data/docs' } });
      fireEvent.click(screen.getByText('settings.sourcesSetup.folderConnect'));

      await waitFor(() => expect(apiMocks.createFolderWatchSource).toHaveBeenCalledWith({
        name: 'Docs', folder_path: '/data/docs', project_id: 9,
      }));
      expect(settingsValue.setConnectedSources).toHaveBeenCalledOnce();
      expect(onDone).toHaveBeenCalledOnce();
      expect((screen.getByPlaceholderText('settings.sourcesSetup.folderNamePlaceholder') as HTMLInputElement).value).toBe('');
    });

    it('reports a failed folder-watch connection without calling onDone', async () => {
      apiMocks.createFolderWatchSource.mockRejectedValue(axiosError('Pfad nicht erreichbar'));
      const onDone = vi.fn();
      render(<SourcesSetupTab {...folderProps} onDone={onDone} />);

      fireEvent.change(screen.getByPlaceholderText('settings.sourcesSetup.folderNamePlaceholder'), { target: { value: 'Docs' } });
      fireEvent.click(screen.getByText('settings.sourcesSetup.folderConnect'));

      await waitFor(() => expect(settingsValue.showToast).toHaveBeenCalledWith('Pfad nicht erreichbar', 'error', expect.any(Error)));
      expect(onDone).not.toHaveBeenCalled();
    });
  });

  describe('Lokaler Upload', () => {
    const localProps = { ...baseProps, activeSourceType: 'settings.sourcesTab.types.local.name' };

    const selectFile = (file: File) => {
      const input = document.querySelector('input[type="file"]') as HTMLInputElement;
      fireEvent.change(input, { target: { files: [file] } });
    };

    it('disables the upload button until a file is selected', () => {
      render(<SourcesSetupTab {...localProps} />);
      expect(screen.getByText('settings.sourcesSetup.uploadAndIndex').closest('button')!.hasAttribute('disabled')).toBe(true);
      selectFile(new File(['x'], 'doc.pdf', { type: 'application/pdf' }));
      expect(screen.getByText('settings.sourcesSetup.uploadAndIndex').closest('button')!.hasAttribute('disabled')).toBe(false);
    });

    it('uploads the file with its name and the selected project, then reports success', async () => {
      apiMocks.uploadLocalDocument.mockResolvedValue(axiosResponse({ id: 5, name: 'doc.pdf' }));
      const onDone = vi.fn();
      render(<SourcesSetupTab {...localProps} onDone={onDone} selectedSourceRepoId="3" />);

      selectFile(new File(['x'], 'doc.pdf', { type: 'application/pdf' }));
      fireEvent.click(screen.getByText('settings.sourcesSetup.uploadAndIndex'));

      await waitFor(() => expect(apiMocks.uploadLocalDocument).toHaveBeenCalledOnce());
      const formData = apiMocks.uploadLocalDocument.mock.calls[0][0] as FormData;
      expect((formData.get('file') as File).name).toBe('doc.pdf');
      expect(formData.get('name')).toBe('doc.pdf');
      expect(formData.get('project_id')).toBe('3');
      expect(settingsValue.setConnectedSources).toHaveBeenCalledOnce();
      expect(onDone).toHaveBeenCalledOnce();
    });

    it('omits project_id from the upload when no project is selected', async () => {
      apiMocks.uploadLocalDocument.mockResolvedValue(axiosResponse({ id: 5, name: 'doc.pdf' }));
      render(<SourcesSetupTab {...localProps} selectedSourceRepoId="all" />);

      selectFile(new File(['x'], 'doc.pdf', { type: 'application/pdf' }));
      fireEvent.click(screen.getByText('settings.sourcesSetup.uploadAndIndex'));

      await waitFor(() => expect(apiMocks.uploadLocalDocument).toHaveBeenCalledOnce());
      const formData = apiMocks.uploadLocalDocument.mock.calls[0][0] as FormData;
      expect(formData.get('project_id')).toBeNull();
    });

    // O-044: das Backend lehnt nicht unterstützte Dateiendungen serverseitig ab
    // (`_ALLOWED_UPLOAD_EXTENSIONS`); dieser Fehler darf nicht verschluckt werden,
    // und die Oberfläche darf den Upload nicht fälschlich als Erfolg behandeln.
    it('shows the server-provided rejection reason for an unsupported file type instead of a generic error', async () => {
      apiMocks.uploadLocalDocument.mockRejectedValue(axiosError('Nicht unterstützter Dateityp: .exe'));
      const onDone = vi.fn();
      render(<SourcesSetupTab {...localProps} onDone={onDone} />);

      selectFile(new File(['x'], 'malware.exe', { type: 'application/octet-stream' }));
      fireEvent.click(screen.getByText('settings.sourcesSetup.uploadAndIndex'));

      await waitFor(() => expect(settingsValue.showToast).toHaveBeenCalledWith('Nicht unterstützter Dateityp: .exe', 'error', expect.any(Error)));
      expect(onDone).not.toHaveBeenCalled();
      expect(settingsValue.setConnectedSources).not.toHaveBeenCalled();
      // Kein Hängenbleiben im Ladezustand nach dem Fehlschlag.
      expect(screen.getByText('settings.sourcesSetup.uploadAndIndex')).toBeTruthy();
    });

    it('falls back to a generic error message when the server gives no detail', async () => {
      apiMocks.uploadLocalDocument.mockRejectedValue(axiosError());
      render(<SourcesSetupTab {...localProps} />);

      selectFile(new File(['x'], 'doc.pdf', { type: 'application/pdf' }));
      fireEvent.click(screen.getByText('settings.sourcesSetup.uploadAndIndex'));

      await waitFor(() => expect(settingsValue.showToast).toHaveBeenCalledWith('settings.toast.documentUploadFailed', 'error', expect.any(Error)));
    });
  });
});
