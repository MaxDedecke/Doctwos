import { axiosResponse } from '@/test/http';
import { createSettingsContextValue } from '@/test/settingsContext';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import React from 'react';

const apiMocks = vi.hoisted(() => ({
  testConnector: vi.fn(),
  getConnectorRepos: vi.fn(),
  getConnectorBranches: vi.fn(),
  createGitSource: vi.fn(),
  getProjects: vi.fn(),
}));

vi.mock('@/app/services/api', () => ({ API_URL: 'http://api.test', api: apiMocks }));
vi.mock('@/lib/i18n/LanguageContext', () => ({ useLanguage: () => ({ t: (key: string) => key }) }));

let settingsValue = createSettingsContextValue();
vi.mock('@/components/settings/SettingsContext', () => ({
  useSettings: () => settingsValue,
}));

import { GitSetupTab } from './GitSetupTab';

/** Wie in JobCenter.test.tsx: ein axios-Fehler mit optionalem FastAPI-`detail`-Feld. */
function axiosError(detail?: string) {
  return Object.assign(new Error('request failed'), {
    isAxiosError: true,
    response: { status: 400, data: detail ? { detail } : {} },
  });
}

/** Schritt 1 → 2: repoType ist bereits 'public' vorbelegt, daher reicht "Weiter" ohne Auswahl. */
const advanceFromStep1 = (provider?: 'github' | 'gitlab' | 'bitbucket') => {
  if (provider) {
    const label = provider === 'github' ? 'GitHub' : provider === 'gitlab' ? 'GitLab' : 'BitBucket';
    fireEvent.click(screen.getByText(label));
  }
  fireEvent.click(screen.getByText('common.next'));
};

/**
 * Kürzester Weg zu Schritt 4 ohne Branch-Fetch-Mocks: eine URL, die keinem der
 * drei bekannten Hosts entspricht, wird von parsePublicGitUrl() nicht erkannt
 * und trotzdem als gültig akzeptiert (permissiver Fallback) — Branches bleiben
 * dabei leer, Schritt 4 zeigt dann das manuelle Branch-Textfeld.
 */
async function advancePublicToStep4(url = 'https://example.com/foo/bar.git') {
  advanceFromStep1();
  fireEvent.change(screen.getByPlaceholderText('https://github.com/facebook/react.git'), { target: { value: url } });
  fireEvent.click(screen.getByText('settings.gitSetup.step2.verify'));
  await waitFor(() => expect(screen.getByText('settings.gitSetup.step2.connectionSuccessHint')).toBeTruthy());
  fireEvent.click(screen.getByText('common.next'));
  await waitFor(() => expect(screen.getByText('settings.gitSetup.step4.addAndIndex')).toBeTruthy());
}

describe('GitSetupTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    settingsValue = createSettingsContextValue();
  });

  describe('Schritt 2 / öffentliche URL', () => {
    it('shows only an inline error, no toast, when verifying with an empty URL', () => {
      render(<GitSetupTab targetProjectId={null} onDone={vi.fn()} />);
      advanceFromStep1();
      fireEvent.click(screen.getByText('settings.gitSetup.step2.verify'));

      expect(screen.getByText('settings.toast.invalidGitUrl')).toBeTruthy();
      expect(settingsValue.showToast).not.toHaveBeenCalled();
      expect(screen.getByText('common.next').closest('button')!.hasAttribute('disabled')).toBe(true);
    });

    it('fetches branches for a parseable GitHub URL and lets you proceed straight to step 4', async () => {
      apiMocks.getConnectorBranches.mockResolvedValue(axiosResponse(['main', 'develop']));
      render(<GitSetupTab targetProjectId={null} onDone={vi.fn()} />);
      advanceFromStep1();
      fireEvent.change(screen.getByPlaceholderText('https://github.com/facebook/react.git'), { target: { value: 'https://github.com/acme/widgets.git' } });
      fireEvent.click(screen.getByText('settings.gitSetup.step2.verify'));

      await waitFor(() => expect(apiMocks.getConnectorBranches).toHaveBeenCalledWith({ type: 'github', repo_name: 'acme/widgets' }));
      expect(settingsValue.showToast).toHaveBeenCalledWith('settings.toast.repoUrlVerified', 'success');
      await waitFor(() => expect(screen.getByText('common.next').closest('button')!.hasAttribute('disabled')).toBe(false));

      fireEvent.click(screen.getByText('common.next'));
      await waitFor(() => expect(screen.getByText('settings.gitSetup.step4.addAndIndex')).toBeTruthy());
    });

    it('still accepts the URL when the branch lookup for a parsed host fails', async () => {
      apiMocks.getConnectorBranches.mockRejectedValue(new Error('boom'));
      render(<GitSetupTab targetProjectId={null} onDone={vi.fn()} />);
      advanceFromStep1();
      fireEvent.change(screen.getByPlaceholderText('https://github.com/facebook/react.git'), { target: { value: 'https://github.com/acme/widgets.git' } });
      fireEvent.click(screen.getByText('settings.gitSetup.step2.verify'));

      await waitFor(() => expect(settingsValue.showToast).toHaveBeenCalledWith('settings.toast.gitUrlAcceptedNoBranches', 'success'));
    });

    it('accepts a URL from an unrecognized host as a permissive fallback', async () => {
      render(<GitSetupTab targetProjectId={null} onDone={vi.fn()} />);
      advanceFromStep1();
      fireEvent.change(screen.getByPlaceholderText('https://github.com/facebook/react.git'), { target: { value: 'https://example.com/foo/bar.git' } });
      fireEvent.click(screen.getByText('settings.gitSetup.step2.verify'));

      await waitFor(() => expect(settingsValue.showToast).toHaveBeenCalledWith('settings.toast.gitUrlAccepted', 'success'));
      expect(apiMocks.getConnectorBranches).not.toHaveBeenCalled();
    });

    it('creates the source end-to-end for a public repo, forcing username/token to null', async () => {
      apiMocks.getConnectorBranches.mockResolvedValue(axiosResponse(['main', 'develop']));
      apiMocks.createGitSource.mockResolvedValue(axiosResponse({ id: 10, name: 'widgets' }));
      apiMocks.getProjects.mockResolvedValue(axiosResponse([]));
      const onDone = vi.fn();
      render(<GitSetupTab targetProjectId={null} onDone={onDone} />);
      advanceFromStep1();
      fireEvent.change(screen.getByPlaceholderText('https://github.com/facebook/react.git'), { target: { value: 'https://github.com/acme/widgets.git' } });
      fireEvent.click(screen.getByText('settings.gitSetup.step2.verify'));
      await waitFor(() => expect(screen.getByText('settings.gitSetup.step2.connectionSuccessHint')).toBeTruthy());
      fireEvent.click(screen.getByText('common.next'));
      await waitFor(() => expect(screen.getByText('settings.gitSetup.step4.addAndIndex')).toBeTruthy());

      fireEvent.click(screen.getByText('settings.gitSetup.step4.addAndIndex'));

      await waitFor(() => expect(apiMocks.createGitSource).toHaveBeenCalledWith({
        name: 'widgets', url: 'https://github.com/acme/widgets.git', branch: 'main',
        username: null, token: null, project_id: null, team_id: undefined,
      }));
      expect(settingsValue.setConnectedSources).toHaveBeenCalledOnce();
      expect(settingsValue.setProjects).toHaveBeenCalledOnce();
      expect(settingsValue.showToast).toHaveBeenCalledWith('settings.toast.repoAdded', 'success');
      await waitFor(() => expect(screen.getByText('settings.gitSetup.step5.finishAndClose')).toBeTruthy());

      fireEvent.click(screen.getByText('settings.gitSetup.step5.finishAndClose'));
      expect(onDone).toHaveBeenCalledOnce();
    });
  });

  describe('Schritt 2 / private Anbindung', () => {
    const fillGithubCreds = () => {
      fireEvent.change(screen.getByPlaceholderText('settings.gitSetup.step2.usernamePlaceholderGithub'), { target: { value: 'acme' } });
      fireEvent.change(screen.getByPlaceholderText('ghp_...'), { target: { value: 'ghp_secret' } });
    };

    it('tests the connection, loads the repo list on success, and enables the next step', async () => {
      apiMocks.testConnector.mockResolvedValue(axiosResponse({ success: true, message: 'Verbunden' }));
      apiMocks.getConnectorRepos.mockResolvedValue(axiosResponse([
        { full_name: 'acme/repo-a', name: 'repo-a', clone_url: 'https://github.com/acme/repo-a.git' },
      ]));
      render(<GitSetupTab targetProjectId={null} onDone={vi.fn()} />);
      advanceFromStep1('github');
      fillGithubCreds();
      fireEvent.click(screen.getByText('settings.gitSetup.step2.testConnection'));

      await waitFor(() => expect(apiMocks.testConnector).toHaveBeenCalledWith({ type: 'github', username: 'acme', token: 'ghp_secret', url: undefined }));
      await waitFor(() => expect(apiMocks.getConnectorRepos).toHaveBeenCalledWith({ type: 'github', username: 'acme', token: 'ghp_secret', url: undefined }));
      expect(settingsValue.showToast).toHaveBeenCalledWith('Verbunden', 'success');
      expect(screen.getByText('common.next').closest('button')!.hasAttribute('disabled')).toBe(false);
    });

    it('shows a toast when the repo list fails to load, but still lets you proceed to an empty list', async () => {
      apiMocks.testConnector.mockResolvedValue(axiosResponse({ success: true }));
      apiMocks.getConnectorRepos.mockRejectedValue(new Error('boom'));
      render(<GitSetupTab targetProjectId={null} onDone={vi.fn()} />);
      advanceFromStep1('github');
      fillGithubCreds();
      fireEvent.click(screen.getByText('settings.gitSetup.step2.testConnection'));

      await waitFor(() => expect(settingsValue.showToast).toHaveBeenCalledWith('settings.toast.repoListFetchFailed', 'error', expect.any(Error)));
      await waitFor(() => expect(screen.getByText('settings.gitSetup.step2.connectionSuccessHint')).toBeTruthy());

      fireEvent.click(screen.getByText('common.next'));
      expect(screen.getByText('settings.gitSetup.step3.noReposFound')).toBeTruthy();
    });

    it('shows the server message inline and a generic toast when the server reports failure', async () => {
      apiMocks.testConnector.mockResolvedValue(axiosResponse({ success: false, message: 'Ungültiges Token' }));
      render(<GitSetupTab targetProjectId={null} onDone={vi.fn()} />);
      advanceFromStep1('github');
      fillGithubCreds();
      fireEvent.click(screen.getByText('settings.gitSetup.step2.testConnection'));

      await waitFor(() => expect(screen.getByText('Ungültiges Token')).toBeTruthy());
      expect(settingsValue.showToast).toHaveBeenCalledWith('settings.toast.connectionFailed', 'error');
      expect(screen.getByText('common.next').closest('button')!.hasAttribute('disabled')).toBe(true);
    });

    it('surfaces the server error detail inline on a network failure', async () => {
      apiMocks.testConnector.mockRejectedValue(axiosError('Zeitüberschreitung beim Verbindungsaufbau'));
      render(<GitSetupTab targetProjectId={null} onDone={vi.fn()} />);
      advanceFromStep1('github');
      fillGithubCreds();
      fireEvent.click(screen.getByText('settings.gitSetup.step2.testConnection'));

      await waitFor(() => expect(screen.getByText('Zeitüberschreitung beim Verbindungsaufbau')).toBeTruthy());
    });

    it('passes the Bitbucket server URL and PAT-flavored fields to the connection test', async () => {
      apiMocks.testConnector.mockResolvedValue(axiosResponse({ success: true }));
      apiMocks.getConnectorRepos.mockResolvedValue(axiosResponse([]));
      render(<GitSetupTab targetProjectId={null} onDone={vi.fn()} />);
      advanceFromStep1('bitbucket');
      fireEvent.change(screen.getByPlaceholderText('https://bitbucket.example.com'), { target: { value: 'https://bb.acme.com' } });
      fireEvent.change(screen.getByPlaceholderText('settings.gitSetup.step2.usernamePlaceholderPat'), { target: { value: 'x-token-auth' } });
      fireEvent.change(screen.getByPlaceholderText('settings.gitSetup.step2.tokenPlaceholderPatEnter'), { target: { value: 'pat-secret' } });
      fireEvent.click(screen.getByText('settings.gitSetup.step2.testConnection'));

      await waitFor(() => expect(apiMocks.testConnector).toHaveBeenCalledWith({
        type: 'bitbucket', username: 'x-token-auth', token: 'pat-secret', url: 'https://bb.acme.com',
      }));
    });
  });

  describe('Schritt 3 / Repository-Auswahl inkl. Nachladen bei Wechsel', () => {
    const repos = [
      { full_name: 'acme/repo-a', name: 'repo-a', clone_url: 'https://github.com/acme/repo-a.git' },
      { full_name: 'acme/repo-b', name: 'repo-b', clone_url: 'https://github.com/acme/repo-b.git' },
    ];

    async function toStep3WithRepos() {
      apiMocks.testConnector.mockResolvedValue(axiosResponse({ success: true }));
      apiMocks.getConnectorRepos.mockResolvedValue(axiosResponse(repos));
      render(<GitSetupTab targetProjectId={null} onDone={vi.fn()} />);
      advanceFromStep1('github');
      fireEvent.change(screen.getByPlaceholderText('settings.gitSetup.step2.usernamePlaceholderGithub'), { target: { value: 'acme' } });
      fireEvent.change(screen.getByPlaceholderText('ghp_...'), { target: { value: 'ghp_secret' } });
      fireEvent.click(screen.getByText('settings.gitSetup.step2.testConnection'));
      // "Weiter" hängt nur an connectionStatus, nicht am (parallel laufenden) Repo-Fetch.
      await waitFor(() => expect(screen.getByText('common.next').closest('button')!.hasAttribute('disabled')).toBe(false));
      fireEvent.click(screen.getByText('common.next'));
      await waitFor(() => expect(screen.getByText('repo-a')).toBeTruthy());
    }

    it('filters the repo list by name', async () => {
      await toStep3WithRepos();
      fireEvent.change(screen.getByPlaceholderText('settings.gitSetup.step3.filterPlaceholder'), { target: { value: 'repo-b' } });
      expect(screen.queryByText('repo-a')).toBeNull();
      expect(screen.getByText('repo-b')).toBeTruthy();
    });

    it('reloads branches for the newly selected repo instead of keeping the previous selection', async () => {
      apiMocks.getConnectorBranches
        .mockResolvedValueOnce(axiosResponse(['main', 'dev']))
        .mockResolvedValueOnce(axiosResponse(['release', 'main']));
      apiMocks.createGitSource.mockResolvedValue(axiosResponse({ id: 1 }));
      apiMocks.getProjects.mockResolvedValue(axiosResponse([]));
      await toStep3WithRepos();

      fireEvent.click(screen.getByText('repo-a'));
      await waitFor(() => expect(apiMocks.getConnectorBranches).toHaveBeenCalledWith({
        type: 'github', username: 'acme', token: 'ghp_secret', repo_name: 'acme/repo-a', url: undefined,
      }));

      fireEvent.click(screen.getByText('repo-b'));
      await waitFor(() => expect(apiMocks.getConnectorBranches).toHaveBeenCalledWith({
        type: 'github', username: 'acme', token: 'ghp_secret', repo_name: 'acme/repo-b', url: undefined,
      }));
      expect(apiMocks.getConnectorBranches).toHaveBeenCalledTimes(2);

      // Weiter zu Schritt 4 und anlegen: die abgesetzte Anfrage muss repo-b (nicht repo-a) und dessen
      // ersten Branch "release" (nicht das erste Ergebnis "main" von repo-a) tragen.
      await waitFor(() => expect(screen.getByText('common.next').closest('button')!.hasAttribute('disabled')).toBe(false));
      fireEvent.click(screen.getByText('common.next'));
      fireEvent.click(screen.getByText('settings.gitSetup.step4.addAndIndex'));

      await waitFor(() => expect(apiMocks.createGitSource).toHaveBeenCalledWith(expect.objectContaining({
        name: 'repo-b', url: 'https://github.com/acme/repo-b.git', branch: 'release',
      })));
    });

    it('shows a toast and clears the branch selection when the branch lookup for a repo fails', async () => {
      apiMocks.getConnectorBranches.mockRejectedValue(new Error('boom'));
      await toStep3WithRepos();

      fireEvent.click(screen.getByText('repo-a'));
      await waitFor(() => expect(settingsValue.showToast).toHaveBeenCalledWith('settings.toast.branchesFetchFailed', 'error', expect.any(Error)));

      // Trotz fehlgeschlagenem Branch-Fetch bleibt die Repo-Auswahl gültig (Next bleibt nutzbar).
      fireEvent.click(screen.getByText('common.next'));
      // Ohne Branches greift in Schritt 4 das manuelle Textfeld statt der Auswahlliste.
      expect(screen.getByPlaceholderText('main')).toBeTruthy();
    });
  });

  describe('Schritt 4 / Team-Sperre (F-041) und Anlegen', () => {
    it('blocks submission and shows a warning for a non-admin without a project and without a team', async () => {
      settingsValue = createSettingsContextValue({ currentUser: { id: 2, username: 'u', is_admin: false, teams: [] } });
      render(<GitSetupTab targetProjectId={null} onDone={vi.fn()} />);
      await advancePublicToStep4();

      expect(screen.getByText('settings.gitSetup.step4.noTeamTitle')).toBeTruthy();
      expect(screen.getByText('settings.gitSetup.step4.addAndIndex').closest('button')!.hasAttribute('disabled')).toBe(true);
    });

    it('blocks submission until a team is picked when the user belongs to more than one team', async () => {
      settingsValue = createSettingsContextValue({
        currentUser: { id: 2, username: 'u', is_admin: false, teams: [{ id: 1, name: 'A' }, { id: 2, name: 'B' }] },
      });
      render(<GitSetupTab targetProjectId={null} onDone={vi.fn()} />);
      await advancePublicToStep4();

      expect(screen.getByText('settings.gitSetup.step4.teamLabel')).toBeTruthy();
      expect(screen.getByText('settings.gitSetup.step4.addAndIndex').closest('button')!.hasAttribute('disabled')).toBe(true);
    });

    it('does not show a team picker, nor blocks submission, for a user with exactly one team', async () => {
      settingsValue = createSettingsContextValue({
        currentUser: { id: 2, username: 'u', is_admin: false, teams: [{ id: 1, name: 'A' }] },
      });
      render(<GitSetupTab targetProjectId={null} onDone={vi.fn()} />);
      await advancePublicToStep4();

      expect(screen.queryByText('settings.gitSetup.step4.teamLabel')).toBeNull();
      expect(screen.getByText('settings.gitSetup.step4.addAndIndex').closest('button')!.hasAttribute('disabled')).toBe(false);
    });

    it('does not gate submission when the source is attached to a project, even without a team', async () => {
      settingsValue = createSettingsContextValue({ currentUser: { id: 2, username: 'u', is_admin: false, teams: [] } });
      render(<GitSetupTab targetProjectId={5} onDone={vi.fn()} />);
      await advancePublicToStep4();

      expect(screen.queryByText('settings.gitSetup.step4.noTeamTitle')).toBeNull();
      expect(screen.getByText('settings.gitSetup.step4.addAndIndex').closest('button')!.hasAttribute('disabled')).toBe(false);
    });

    it('does not gate submission for admins, even without a team', async () => {
      settingsValue = createSettingsContextValue({ currentUser: { id: 2, username: 'admin', is_admin: true, teams: [] } });
      render(<GitSetupTab targetProjectId={null} onDone={vi.fn()} />);
      await advancePublicToStep4();

      expect(screen.getByText('settings.gitSetup.step4.addAndIndex').closest('button')!.hasAttribute('disabled')).toBe(false);
    });

    it('shows the server error detail on a failed submit and stays on the branch step', async () => {
      apiMocks.createGitSource.mockRejectedValue(axiosError('Name bereits vergeben'));
      render(<GitSetupTab targetProjectId={null} onDone={vi.fn()} />);
      await advancePublicToStep4();

      fireEvent.click(screen.getByText('settings.gitSetup.step4.addAndIndex'));

      await waitFor(() => expect(settingsValue.showToast).toHaveBeenCalledWith('Name bereits vergeben', 'error', expect.any(Error)));
      expect(screen.getByText('settings.gitSetup.step4.addAndIndex')).toBeTruthy();
      expect(settingsValue.setConnectedSources).not.toHaveBeenCalled();
    });
  });
});
