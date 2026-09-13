import type { Team, User } from '@/types/domain';
import { axiosResponse } from '@/test/http';
import { createSettingsContextValue } from '@/test/settingsContext';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import React from 'react';

const apiMocks = vi.hoisted(() => ({
  getTeams: vi.fn(),
  getUsers: vi.fn(),
  createTeam: vi.fn(),
  updateTeam: vi.fn(),
  deleteTeam: vi.fn(),
  getTeamMembers: vi.fn(),
  addTeamMember: vi.fn(),
  removeTeamMember: vi.fn(),
}));

vi.mock('@/app/services/api', () => ({ API_URL: 'http://api.test', api: apiMocks }));
vi.mock('@/lib/i18n/LanguageContext', () => ({
  useLanguage: () => ({
    t: (key: string, values?: Record<string, unknown>) =>
      values?.name !== undefined ? `${key}:${values.name}` : key,
  }),
}));

let settingsValue = createSettingsContextValue();
vi.mock('@/components/settings/SettingsContext', () => ({
  useSettings: () => settingsValue,
}));

import { TeamsSettingsTab } from './TeamsSettingsTab';

function axiosError(detail?: string) {
  return Object.assign(new Error('request failed'), {
    isAxiosError: true,
    response: { status: 400, data: detail ? { detail } : {} },
  });
}

const team = (overrides: Partial<Team> = {}): Team => ({ id: 1, name: 'Team Alpha', ...overrides });
const user = (overrides: Partial<User>): User => ({ id: 2, username: 'bob', ...overrides });

/** Öffnet den Mitglieder-Bereich des (einzigen) Teams. */
async function expandTeam() {
  await waitFor(() => expect(screen.getByText('Team Alpha')).toBeTruthy());
  fireEvent.click(screen.getByText('Team Alpha'));
  await waitFor(() => expect(apiMocks.getTeamMembers).toHaveBeenCalledOnce());
}

describe('TeamsSettingsTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    settingsValue = createSettingsContextValue();
    apiMocks.getTeams.mockResolvedValue(axiosResponse([team()]));
    apiMocks.getUsers.mockResolvedValue(axiosResponse([]));
    apiMocks.getTeamMembers.mockResolvedValue(axiosResponse([]));
  });

  describe('Anlegen', () => {
    it('disables the submit button until a name is entered', async () => {
      apiMocks.getTeams.mockResolvedValue(axiosResponse([]));
      render(<TeamsSettingsTab />);
      expect(screen.getByText('settings.teams.createButton').closest('button')!.hasAttribute('disabled')).toBe(true);
      fireEvent.change(screen.getByPlaceholderText('settings.teams.newTeamPlaceholder'), { target: { value: 'Neu' } });
      expect(screen.getByText('settings.teams.createButton').closest('button')!.hasAttribute('disabled')).toBe(false);
    });

    it('creates the team, resets the input, and refreshes the list', async () => {
      apiMocks.getTeams.mockResolvedValueOnce(axiosResponse([])).mockResolvedValueOnce(axiosResponse([team({ name: 'Neues Team' })]));
      apiMocks.createTeam.mockResolvedValue(axiosResponse({}));
      render(<TeamsSettingsTab />);
      await waitFor(() => expect(apiMocks.getTeams).toHaveBeenCalledOnce());

      fireEvent.change(screen.getByPlaceholderText('settings.teams.newTeamPlaceholder'), { target: { value: '  Neues Team  ' } });
      fireEvent.click(screen.getByText('settings.teams.createButton'));

      await waitFor(() => expect(apiMocks.createTeam).toHaveBeenCalledWith('Neues Team'));
      expect(settingsValue.showToast).toHaveBeenCalledWith('settings.toast.teamCreated', 'success');
      expect((screen.getByPlaceholderText('settings.teams.newTeamPlaceholder') as HTMLInputElement).value).toBe('');
      await waitFor(() => expect(apiMocks.getTeams).toHaveBeenCalledTimes(2));
    });

    it('shows the server error detail on a failed creation and keeps the entered name', async () => {
      apiMocks.getTeams.mockResolvedValue(axiosResponse([]));
      apiMocks.createTeam.mockRejectedValue(axiosError('Name bereits vergeben'));
      render(<TeamsSettingsTab />);

      fireEvent.change(screen.getByPlaceholderText('settings.teams.newTeamPlaceholder'), { target: { value: 'Doppelt' } });
      fireEvent.click(screen.getByText('settings.teams.createButton'));

      await waitFor(() => expect(settingsValue.showToast).toHaveBeenCalledWith('Name bereits vergeben', 'error', expect.any(Error)));
      expect((screen.getByPlaceholderText('settings.teams.newTeamPlaceholder') as HTMLInputElement).value).toBe('Doppelt');
    });
  });

  describe('Umbenennen', () => {
    it('prefills the rename input with the current name and cancels on Escape', async () => {
      render(<TeamsSettingsTab />);
      await waitFor(() => expect(screen.getByText('Team Alpha')).toBeTruthy());

      fireEvent.click(screen.getByTitle('settings.teams.renameTitle'));
      const input = screen.getByDisplayValue('Team Alpha');
      fireEvent.change(input, { target: { value: 'Geändert' } });
      fireEvent.keyDown(input, { key: 'Escape' });

      expect(screen.getByText('Team Alpha')).toBeTruthy();
      expect(screen.queryByDisplayValue('Geändert')).toBeNull();
    });

    it('renames the team on Enter and refreshes', async () => {
      apiMocks.getTeams.mockResolvedValueOnce(axiosResponse([team()])).mockResolvedValueOnce(axiosResponse([team({ name: 'Team Beta' })]));
      apiMocks.updateTeam.mockResolvedValue(axiosResponse({}));
      render(<TeamsSettingsTab />);
      await waitFor(() => expect(screen.getByText('Team Alpha')).toBeTruthy());

      fireEvent.click(screen.getByTitle('settings.teams.renameTitle'));
      const input = screen.getByDisplayValue('Team Alpha');
      fireEvent.change(input, { target: { value: 'Team Beta' } });
      fireEvent.keyDown(input, { key: 'Enter' });

      await waitFor(() => expect(apiMocks.updateTeam).toHaveBeenCalledWith(1, 'Team Beta'));
      expect(settingsValue.showToast).toHaveBeenCalledWith('settings.toast.teamRenamed', 'success');
      await waitFor(() => expect(apiMocks.getTeams).toHaveBeenCalledTimes(2));
    });

    it('does nothing when confirming an empty name', async () => {
      render(<TeamsSettingsTab />);
      await waitFor(() => expect(screen.getByText('Team Alpha')).toBeTruthy());

      fireEvent.click(screen.getByTitle('settings.teams.renameTitle'));
      const input = screen.getByDisplayValue('Team Alpha');
      fireEvent.change(input, { target: { value: '   ' } });
      fireEvent.keyDown(input, { key: 'Enter' });

      expect(apiMocks.updateTeam).not.toHaveBeenCalled();
    });

    it('shows the server error detail on a failed rename and stays in edit mode', async () => {
      apiMocks.updateTeam.mockRejectedValue(axiosError('Name ungültig'));
      render(<TeamsSettingsTab />);
      await waitFor(() => expect(screen.getByText('Team Alpha')).toBeTruthy());

      fireEvent.click(screen.getByTitle('settings.teams.renameTitle'));
      fireEvent.change(screen.getByDisplayValue('Team Alpha'), { target: { value: 'Team Beta' } });
      fireEvent.keyDown(screen.getByDisplayValue('Team Beta'), { key: 'Enter' });

      await waitFor(() => expect(settingsValue.showToast).toHaveBeenCalledWith('Name ungültig', 'error', expect.any(Error)));
      expect(screen.getByDisplayValue('Team Beta')).toBeTruthy();
    });
  });

  describe('Löschen', () => {
    it('aborts without calling the API when the confirmation is declined', async () => {
      vi.stubGlobal('confirm', vi.fn(() => false));
      render(<TeamsSettingsTab />);
      await waitFor(() => expect(screen.getByText('Team Alpha')).toBeTruthy());

      fireEvent.click(screen.getByTitle('settings.teams.deleteTitle'));
      expect(apiMocks.deleteTeam).not.toHaveBeenCalled();
      vi.unstubAllGlobals();
    });

    it('deletes exactly the targeted team and refreshes the list', async () => {
      vi.stubGlobal('confirm', vi.fn(() => true));
      apiMocks.getTeams.mockResolvedValueOnce(axiosResponse([team({ id: 1, name: 'Team Alpha' }), team({ id: 2, name: 'Team Beta' })]))
        .mockResolvedValueOnce(axiosResponse([team({ id: 1, name: 'Team Alpha' })]));
      apiMocks.deleteTeam.mockResolvedValue(axiosResponse({}));
      render(<TeamsSettingsTab />);
      await waitFor(() => expect(screen.getByText('Team Beta')).toBeTruthy());

      fireEvent.click(screen.getAllByTitle('settings.teams.deleteTitle')[1]);

      await waitFor(() => expect(apiMocks.deleteTeam).toHaveBeenCalledWith(2));
      expect(apiMocks.deleteTeam).toHaveBeenCalledOnce();
      expect(settingsValue.showToast).toHaveBeenCalledWith('settings.toast.teamDeleted:Team Beta', 'success');
      vi.unstubAllGlobals();
    });

    it('shows the server error detail on a failed deletion', async () => {
      vi.stubGlobal('confirm', vi.fn(() => true));
      apiMocks.deleteTeam.mockRejectedValue(axiosError('Team hat noch Projekte'));
      render(<TeamsSettingsTab />);
      await waitFor(() => expect(screen.getByText('Team Alpha')).toBeTruthy());

      fireEvent.click(screen.getByTitle('settings.teams.deleteTitle'));
      await waitFor(() => expect(settingsValue.showToast).toHaveBeenCalledWith('Team hat noch Projekte', 'error', expect.any(Error)));
      vi.unstubAllGlobals();
    });
  });

  describe('Mitglieder', () => {
    it('loads members on first expand only, not again on collapse and re-expand', async () => {
      apiMocks.getTeamMembers.mockResolvedValue(axiosResponse([user({ id: 2, username: 'bob', name: 'Bob' })]));
      render(<TeamsSettingsTab />);
      await waitFor(() => expect(screen.getByText('Team Alpha')).toBeTruthy());

      fireEvent.click(screen.getByText('Team Alpha')); // expand
      await waitFor(() => expect(screen.getByText('Bob')).toBeTruthy());
      fireEvent.click(screen.getByText('Team Alpha')); // collapse
      fireEvent.click(screen.getByText('Team Alpha')); // re-expand

      expect(apiMocks.getTeamMembers).toHaveBeenCalledOnce();
    });

    it('filters existing members out of the add-member candidate list', async () => {
      apiMocks.getUsers.mockResolvedValue(axiosResponse([
        user({ id: 2, username: 'bob', name: 'Bob' }),
        user({ id: 3, username: 'carla', name: 'Carla' }),
      ]));
      apiMocks.getTeamMembers.mockResolvedValue(axiosResponse([user({ id: 2, username: 'bob', name: 'Bob' })]));
      render(<TeamsSettingsTab />);
      await expandTeam();
      await waitFor(() => expect(screen.getByText('Bob')).toBeTruthy());

      fireEvent.click(screen.getByRole('combobox'));
      const listbox = screen.getByRole('listbox');
      expect(within(listbox).queryByText('Bob')).toBeNull();
      expect(within(listbox).getByText('Carla')).toBeTruthy();
    });

    it('hides the add-member row entirely once every user is already a member', async () => {
      apiMocks.getUsers.mockResolvedValue(axiosResponse([user({ id: 2, username: 'bob', name: 'Bob' })]));
      apiMocks.getTeamMembers.mockResolvedValue(axiosResponse([user({ id: 2, username: 'bob', name: 'Bob' })]));
      render(<TeamsSettingsTab />);
      await expandTeam();
      await waitFor(() => expect(screen.getByText('Bob')).toBeTruthy());

      expect(screen.queryByRole('combobox')).toBeNull();
    });

    it('disables the add button until a candidate is selected', async () => {
      apiMocks.getUsers.mockResolvedValue(axiosResponse([user({ id: 3, username: 'carla', name: 'Carla' })]));
      render(<TeamsSettingsTab />);
      await expandTeam();
      await waitFor(() => expect(screen.getByRole('combobox')).toBeTruthy());

      const addButton = screen.getAllByRole('button').find((b) => b.querySelector('.lucide-user-plus'))!;
      expect(addButton.hasAttribute('disabled')).toBe(true);
    });

    it('adds the selected candidate to exactly this team', async () => {
      apiMocks.getUsers.mockResolvedValue(axiosResponse([user({ id: 3, username: 'carla', name: 'Carla' })]));
      apiMocks.addTeamMember.mockResolvedValue(axiosResponse({}));
      render(<TeamsSettingsTab />);
      await expandTeam();
      await waitFor(() => expect(screen.getByRole('combobox')).toBeTruthy());

      fireEvent.click(screen.getByRole('combobox'));
      fireEvent.click(within(screen.getByRole('listbox')).getByText('Carla'));
      const addButton = screen.getAllByRole('button').find((b) => b.querySelector('.lucide-user-plus'))!;
      fireEvent.click(addButton);

      await waitFor(() => expect(apiMocks.addTeamMember).toHaveBeenCalledWith(1, 3));
      expect(settingsValue.showToast).toHaveBeenCalledWith('settings.toast.memberAdded', 'success');
      // Nur die Mitgliederliste dieses Teams wird nachgezogen, nicht die ganze Teamliste.
      expect(apiMocks.getTeamMembers).toHaveBeenCalledTimes(2);
      expect(apiMocks.getTeams).toHaveBeenCalledOnce();
    });

    it('shows the server error detail when adding a member fails', async () => {
      apiMocks.getUsers.mockResolvedValue(axiosResponse([user({ id: 3, username: 'carla', name: 'Carla' })]));
      apiMocks.addTeamMember.mockRejectedValue(axiosError('Nutzer bereits in anderem Team'));
      render(<TeamsSettingsTab />);
      await expandTeam();
      await waitFor(() => expect(screen.getByRole('combobox')).toBeTruthy());

      fireEvent.click(screen.getByRole('combobox'));
      fireEvent.click(within(screen.getByRole('listbox')).getByText('Carla'));
      const addButton = screen.getAllByRole('button').find((b) => b.querySelector('.lucide-user-plus'))!;
      fireEvent.click(addButton);

      await waitFor(() => expect(settingsValue.showToast).toHaveBeenCalledWith('Nutzer bereits in anderem Team', 'error', expect.any(Error)));
    });

    it('removes exactly the targeted member and refreshes only this team', async () => {
      apiMocks.getTeamMembers.mockResolvedValueOnce(axiosResponse([
        user({ id: 2, username: 'bob', name: 'Bob' }),
        user({ id: 3, username: 'carla', name: 'Carla' }),
      ])).mockResolvedValueOnce(axiosResponse([user({ id: 3, username: 'carla', name: 'Carla' })]));
      apiMocks.removeTeamMember.mockResolvedValue(axiosResponse({}));
      render(<TeamsSettingsTab />);
      await expandTeam();
      await waitFor(() => expect(screen.getByText('Carla')).toBeTruthy());

      fireEvent.click(screen.getAllByTitle('settings.teams.removeMemberTitle')[0]);

      await waitFor(() => expect(apiMocks.removeTeamMember).toHaveBeenCalledWith(1, 2));
      expect(apiMocks.removeTeamMember).toHaveBeenCalledOnce();
      expect(settingsValue.showToast).toHaveBeenCalledWith('settings.toast.memberRemoved', 'success');
    });

    it('shows the server error detail when removing a member fails', async () => {
      apiMocks.getTeamMembers.mockResolvedValue(axiosResponse([user({ id: 2, username: 'bob', name: 'Bob' })]));
      apiMocks.removeTeamMember.mockRejectedValue(axiosError('Letztes Teammitglied'));
      render(<TeamsSettingsTab />);
      await expandTeam();
      await waitFor(() => expect(screen.getByText('Bob')).toBeTruthy());

      fireEvent.click(screen.getByTitle('settings.teams.removeMemberTitle'));
      await waitFor(() => expect(settingsValue.showToast).toHaveBeenCalledWith('Letztes Teammitglied', 'error', expect.any(Error)));
    });
  });
});
