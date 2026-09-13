import { axiosResponse } from '@/test/http';
import { createSettingsContextValue } from '@/test/settingsContext';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import React from 'react';

const apiMocks = vi.hoisted(() => ({
  getUsers: vi.fn(),
  createUser: vi.fn(),
  updateUser: vi.fn(),
  resetUserPassword: vi.fn(),
  unlockUser: vi.fn(),
}));
const utilsMocks = vi.hoisted(() => ({ copyToClipboard: vi.fn() }));

vi.mock('@/app/services/api', () => ({ API_URL: 'http://api.test', api: apiMocks }));
vi.mock('@/lib/i18n/LanguageContext', () => ({
  useLanguage: () => ({
    t: (key: string, values?: Record<string, unknown>) => (values ? `${key}:${JSON.stringify(values)}` : key),
  }),
}));
vi.mock('@/lib/utils', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/utils')>();
  return { ...actual, copyToClipboard: utilsMocks.copyToClipboard };
});

let settingsValue = createSettingsContextValue();
vi.mock('@/components/settings/SettingsContext', () => ({
  useSettings: () => settingsValue,
}));

import { UsersSettingsTab } from './UsersSettingsTab';

function axiosError(detail?: string) {
  return Object.assign(new Error('request failed'), {
    isAxiosError: true,
    response: { status: 400, data: detail ? { detail } : {} },
  });
}

const managedUser = (overrides: Partial<{
  id: number; username: string; name: string | null; email: string | null;
  role: 'superuser' | 'user'; is_active: boolean; is_locked: boolean;
  must_change_password: boolean; failed_login_count: number; last_login_at: string | null;
}> = {}) => ({
  id: 2, username: 'bob', name: null, email: null, role: 'user' as const,
  is_active: true, is_locked: false, must_change_password: false,
  failed_login_count: 0, last_login_at: null, ...overrides,
});

describe('UsersSettingsTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    settingsValue = createSettingsContextValue();
    apiMocks.getUsers.mockResolvedValue(axiosResponse([]));
  });

  describe('Anlegen', () => {
    it('disables the submit button until a username is entered', () => {
      render(<UsersSettingsTab />);
      expect(screen.getByText('settings.users.createButton').closest('button')!.hasAttribute('disabled')).toBe(true);
      fireEvent.change(screen.getByPlaceholderText('settings.users.usernamePlaceholder'), { target: { value: 'kim' } });
      expect(screen.getByText('settings.users.createButton').closest('button')!.hasAttribute('disabled')).toBe(false);
    });

    it('shows the initial password, resets the form, and refreshes the list on success', async () => {
      apiMocks.createUser.mockResolvedValue(axiosResponse({ username: 'kim', initial_password: 'S3cret!23' }));
      apiMocks.getUsers.mockResolvedValueOnce(axiosResponse([])).mockResolvedValueOnce(axiosResponse([managedUser({ id: 3, username: 'kim' })]));
      render(<UsersSettingsTab />);
      await waitFor(() => expect(apiMocks.getUsers).toHaveBeenCalledOnce());

      fireEvent.change(screen.getByPlaceholderText('settings.users.usernamePlaceholder'), { target: { value: 'kim' } });
      fireEvent.change(screen.getByPlaceholderText('settings.users.namePlaceholder'), { target: { value: 'Kim' } });
      fireEvent.click(screen.getByText('settings.users.createButton'));

      await waitFor(() => expect(apiMocks.createUser).toHaveBeenCalledWith({ username: 'kim', name: 'Kim', role: 'user' }));
      expect(screen.getByText('S3cret!23')).toBeTruthy();
      expect(settingsValue.showToast).toHaveBeenCalledWith('settings.toast.userCreated', 'success');
      expect((screen.getByPlaceholderText('settings.users.usernamePlaceholder') as HTMLInputElement).value).toBe('');
      await waitFor(() => expect(apiMocks.getUsers).toHaveBeenCalledTimes(2));
    });

    it('shows the server error detail on a failed creation, without an issued password', async () => {
      apiMocks.createUser.mockRejectedValue(axiosError('Nutzername bereits vergeben'));
      render(<UsersSettingsTab />);
      fireEvent.change(screen.getByPlaceholderText('settings.users.usernamePlaceholder'), { target: { value: 'kim' } });
      fireEvent.click(screen.getByText('settings.users.createButton'));

      await waitFor(() => expect(settingsValue.showToast).toHaveBeenCalledWith('Nutzername bereits vergeben', 'error', expect.any(Error)));
      expect(screen.queryByText('common.close')).toBeNull();
    });

    it('closing the issued-password banner clears it', async () => {
      apiMocks.createUser.mockResolvedValue(axiosResponse({ username: 'kim', initial_password: 'S3cret!23' }));
      render(<UsersSettingsTab />);
      fireEvent.change(screen.getByPlaceholderText('settings.users.usernamePlaceholder'), { target: { value: 'kim' } });
      fireEvent.click(screen.getByText('settings.users.createButton'));

      await waitFor(() => expect(screen.getByText('S3cret!23')).toBeTruthy());
      fireEvent.click(screen.getByText('common.close'));
      expect(screen.queryByText('S3cret!23')).toBeNull();
    });

    it('copies the issued password and reports success or failure', async () => {
      apiMocks.createUser.mockResolvedValue(axiosResponse({ username: 'kim', initial_password: 'S3cret!23' }));
      utilsMocks.copyToClipboard.mockResolvedValueOnce(true).mockResolvedValueOnce(false);
      render(<UsersSettingsTab />);
      fireEvent.change(screen.getByPlaceholderText('settings.users.usernamePlaceholder'), { target: { value: 'kim' } });
      fireEvent.click(screen.getByText('settings.users.createButton'));
      await waitFor(() => expect(screen.getByText('S3cret!23')).toBeTruthy());

      const copyButton = screen.getAllByRole('button').find((b) => b.querySelector('.lucide-copy'))!;
      fireEvent.click(copyButton);
      await waitFor(() => expect(utilsMocks.copyToClipboard).toHaveBeenCalledWith('S3cret!23'));
      await waitFor(() => expect(settingsValue.showToast).toHaveBeenCalledWith('settings.toast.passwordCopied', 'success'));

      fireEvent.click(copyButton);
      await waitFor(() => expect(settingsValue.showToast).toHaveBeenCalledWith('settings.toast.passwordCopyFailed', 'error'));
    });
  });

  describe('Passwort zurücksetzen', () => {
    it('aborts without calling the API when the confirmation is declined', async () => {
      vi.stubGlobal('confirm', vi.fn(() => false));
      apiMocks.getUsers.mockResolvedValue(axiosResponse([managedUser()]));
      render(<UsersSettingsTab />);
      await waitFor(() => expect(screen.getByTitle('settings.users.resetPasswordTitle')).toBeTruthy());

      fireEvent.click(screen.getByTitle('settings.users.resetPasswordTitle'));
      expect(apiMocks.resetUserPassword).not.toHaveBeenCalled();
    });

    it('resets exactly the targeted user, shows the new password, and refreshes', async () => {
      vi.stubGlobal('confirm', vi.fn(() => true));
      apiMocks.getUsers.mockResolvedValueOnce(axiosResponse([
        managedUser({ id: 2, username: 'bob' }),
        managedUser({ id: 3, username: 'carla' }),
      ])).mockResolvedValueOnce(axiosResponse([managedUser({ id: 2, username: 'bob' }), managedUser({ id: 3, username: 'carla' })]));
      apiMocks.resetUserPassword.mockResolvedValue(axiosResponse({ initial_password: 'NewPass1!' }));
      render(<UsersSettingsTab />);
      await waitFor(() => expect(screen.getByText('carla')).toBeTruthy());

      fireEvent.click(screen.getAllByTitle('settings.users.resetPasswordTitle')[1]);

      await waitFor(() => expect(apiMocks.resetUserPassword).toHaveBeenCalledWith(3));
      expect(apiMocks.resetUserPassword).toHaveBeenCalledOnce();
      expect(screen.getByText('NewPass1!')).toBeTruthy();
      expect(settingsValue.showToast).toHaveBeenCalledWith('settings.toast.passwordReset', 'success');
    });

    it('shows the server error detail on a failed reset', async () => {
      vi.stubGlobal('confirm', vi.fn(() => true));
      apiMocks.getUsers.mockResolvedValue(axiosResponse([managedUser()]));
      apiMocks.resetUserPassword.mockRejectedValue(axiosError('Nutzer gesperrt'));
      render(<UsersSettingsTab />);
      await waitFor(() => expect(screen.getByText('bob')).toBeTruthy());

      fireEvent.click(screen.getByTitle('settings.users.resetPasswordTitle'));
      await waitFor(() => expect(settingsValue.showToast).toHaveBeenCalledWith('Nutzer gesperrt', 'error', expect.any(Error)));
    });

    it('disables the reset button while the request is in flight', async () => {
      vi.stubGlobal('confirm', vi.fn(() => true));
      apiMocks.getUsers.mockResolvedValue(axiosResponse([managedUser()]));
      let resolveReset!: (v: unknown) => void;
      apiMocks.resetUserPassword.mockReturnValue(new Promise((resolve) => { resolveReset = resolve; }));
      render(<UsersSettingsTab />);
      await waitFor(() => expect(screen.getByText('bob')).toBeTruthy());

      const resetButton = screen.getByTitle('settings.users.resetPasswordTitle');
      fireEvent.click(resetButton);
      await waitFor(() => expect(resetButton.hasAttribute('disabled')).toBe(true));

      resolveReset(axiosResponse({ initial_password: 'x' }));
      // Der anschließende refresh() blendet kurz den Ladespinner ein und tauscht die
      // Listen-DOM-Knoten aus -- daher neu abfragen statt die alte Referenz weiterzuverwenden.
      await waitFor(() => expect(screen.getByTitle('settings.users.resetPasswordTitle').hasAttribute('disabled')).toBe(false));
    });
  });

  describe('Entsperren', () => {
    it('only shows the unlock button for a locked user', async () => {
      apiMocks.getUsers.mockResolvedValue(axiosResponse([
        managedUser({ id: 2, username: 'bob', is_locked: false }),
        managedUser({ id: 3, username: 'carla', is_locked: true }),
      ]));
      render(<UsersSettingsTab />);
      await waitFor(() => expect(screen.getByText('carla')).toBeTruthy());
      expect(screen.getAllByTitle('settings.users.unlockTitle').length).toBe(1);
    });

    it('unlocks exactly the targeted user and refreshes', async () => {
      apiMocks.getUsers.mockResolvedValueOnce(axiosResponse([
        managedUser({ id: 2, username: 'bob', is_locked: false }),
        managedUser({ id: 3, username: 'carla', is_locked: true }),
      ])).mockResolvedValueOnce(axiosResponse([
        managedUser({ id: 2, username: 'bob', is_locked: false }),
        managedUser({ id: 3, username: 'carla', is_locked: false }),
      ]));
      apiMocks.unlockUser.mockResolvedValue(axiosResponse({}));
      render(<UsersSettingsTab />);
      await waitFor(() => expect(screen.getByText('carla')).toBeTruthy());

      fireEvent.click(screen.getByTitle('settings.users.unlockTitle'));

      await waitFor(() => expect(apiMocks.unlockUser).toHaveBeenCalledWith(3));
      expect(settingsValue.showToast).toHaveBeenCalledWith('settings.toast.userUnlocked', 'success');
      await waitFor(() => expect(apiMocks.getUsers).toHaveBeenCalledTimes(2));
    });

    it('falls back to the generic update-failure toast when unlocking fails without a server detail', async () => {
      apiMocks.getUsers.mockResolvedValue(axiosResponse([managedUser({ id: 3, username: 'carla', is_locked: true })]));
      apiMocks.unlockUser.mockRejectedValue(axiosError());
      render(<UsersSettingsTab />);
      await waitFor(() => expect(screen.getByText('carla')).toBeTruthy());

      fireEvent.click(screen.getByTitle('settings.users.unlockTitle'));
      await waitFor(() => expect(settingsValue.showToast).toHaveBeenCalledWith('settings.toast.userUpdateFailed', 'error', expect.any(Error)));
    });
  });

  describe('Deaktivieren / Aktivieren', () => {
    it('asks for confirmation before deactivating an active user, and aborts if declined', async () => {
      vi.stubGlobal('confirm', vi.fn(() => false));
      apiMocks.getUsers.mockResolvedValue(axiosResponse([managedUser({ id: 2, username: 'bob', is_active: true })]));
      render(<UsersSettingsTab />);
      await waitFor(() => expect(screen.getByText('bob')).toBeTruthy());

      fireEvent.click(screen.getByTitle('settings.users.deactivateTitle'));
      expect(apiMocks.updateUser).not.toHaveBeenCalled();
    });

    it('deactivates exactly the targeted user once confirmed', async () => {
      vi.stubGlobal('confirm', vi.fn(() => true));
      apiMocks.getUsers.mockResolvedValueOnce(axiosResponse([
        managedUser({ id: 2, username: 'bob', is_active: true }),
        managedUser({ id: 3, username: 'carla', is_active: true }),
      ])).mockResolvedValueOnce(axiosResponse([]));
      apiMocks.updateUser.mockResolvedValue(axiosResponse({}));
      render(<UsersSettingsTab />);
      await waitFor(() => expect(screen.getByText('carla')).toBeTruthy());

      fireEvent.click(screen.getAllByTitle('settings.users.deactivateTitle')[1]);

      await waitFor(() => expect(apiMocks.updateUser).toHaveBeenCalledWith(3, { is_active: false }));
      expect(apiMocks.updateUser).toHaveBeenCalledOnce();
      expect(settingsValue.showToast).toHaveBeenCalledWith('settings.toast.userDeactivated', 'success');
    });

    it('reactivates an inactive user without asking for confirmation', async () => {
      vi.stubGlobal('confirm', vi.fn());
      apiMocks.getUsers.mockResolvedValue(axiosResponse([managedUser({ id: 2, username: 'bob', is_active: false })]));
      apiMocks.updateUser.mockResolvedValue(axiosResponse({}));
      render(<UsersSettingsTab />);
      await waitFor(() => expect(screen.getByText('bob')).toBeTruthy());

      fireEvent.click(screen.getByTitle('settings.users.activateTitle'));

      await waitFor(() => expect(apiMocks.updateUser).toHaveBeenCalledWith(2, { is_active: true }));
      expect(window.confirm).not.toHaveBeenCalled();
      expect(settingsValue.showToast).toHaveBeenCalledWith('settings.toast.userActivated', 'success');
    });

    it('shows the server error detail on a failed status change', async () => {
      vi.stubGlobal('confirm', vi.fn(() => true));
      apiMocks.getUsers.mockResolvedValue(axiosResponse([managedUser({ id: 2, username: 'bob', is_active: true })]));
      apiMocks.updateUser.mockRejectedValue(axiosError('Letzter Admin kann nicht deaktiviert werden'));
      render(<UsersSettingsTab />);
      await waitFor(() => expect(screen.getByText('bob')).toBeTruthy());

      fireEvent.click(screen.getByTitle('settings.users.deactivateTitle'));
      await waitFor(() => expect(settingsValue.showToast).toHaveBeenCalledWith('Letzter Admin kann nicht deaktiviert werden', 'error', expect.any(Error)));
    });

    it('disables the deactivate button for your own account', async () => {
      settingsValue = createSettingsContextValue({ currentUser: { id: 2, username: 'admin', is_admin: true } });
      apiMocks.getUsers.mockResolvedValue(axiosResponse([managedUser({ id: 2, username: 'admin', is_active: true })]));
      render(<UsersSettingsTab />);
      await waitFor(() => expect(screen.getByText('admin')).toBeTruthy());

      expect(screen.getByTitle('settings.users.deactivateTitle').hasAttribute('disabled')).toBe(true);
    });
  });

  describe('Rollenwechsel', () => {
    it("changes another user's role and refreshes the list", async () => {
      apiMocks.getUsers.mockResolvedValueOnce(axiosResponse([managedUser({ id: 2, username: 'bob', role: 'user' })]))
        .mockResolvedValueOnce(axiosResponse([managedUser({ id: 2, username: 'bob', role: 'superuser' })]));
      apiMocks.updateUser.mockResolvedValue(axiosResponse({}));
      render(<UsersSettingsTab />);
      await waitFor(() => expect(screen.getByText('bob')).toBeTruthy());

      // Zweite Combobox: die erste ist die Rollen-Auswahl im "Neu anlegen"-Formular oben.
      fireEvent.click(screen.getAllByRole('combobox')[1]);
      fireEvent.click(within(screen.getByRole('listbox')).getByText('settings.users.roleSuperuser'));

      await waitFor(() => expect(apiMocks.updateUser).toHaveBeenCalledWith(2, { role: 'superuser' }));
      expect(settingsValue.showToast).toHaveBeenCalledWith('settings.toast.userRoleChanged', 'success');
      await waitFor(() => expect(apiMocks.getUsers).toHaveBeenCalledTimes(2));
    });

    it('disables the role selector for your own account', async () => {
      settingsValue = createSettingsContextValue({ currentUser: { id: 2, username: 'admin', is_admin: true } });
      apiMocks.getUsers.mockResolvedValue(axiosResponse([managedUser({ id: 2, username: 'admin' })]));
      render(<UsersSettingsTab />);
      await waitFor(() => expect(screen.getByText('admin')).toBeTruthy());

      // Zweite Combobox: die erste ist die Rollen-Auswahl im "Neu anlegen"-Formular oben.
      expect(screen.getAllByRole('combobox')[1].getAttribute('data-disabled')).not.toBeNull();
    });
  });
});
