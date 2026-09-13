import { axiosResponse } from '@/test/http';
import { createSettingsContextValue } from '@/test/settingsContext';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import React from 'react';

const apiMocks = vi.hoisted(() => ({
  createProject: vi.fn(),
  getProjects: vi.fn(),
}));

vi.mock('@/app/services/api', () => ({ API_URL: 'http://api.test', api: apiMocks }));
vi.mock('@/lib/i18n/LanguageContext', () => ({
  useLanguage: () => ({ language: 'de', t: (key: string) => key }),
}));

let settingsValue = createSettingsContextValue();
vi.mock('@/components/settings/SettingsContext', () => ({
  useSettings: () => settingsValue,
}));

import { ProjectSetupTab } from './ProjectSetupTab';

const newProject = { id: 9, name: 'Neues Projekt' };

describe('ProjectSetupTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    settingsValue = createSettingsContextValue();
  });

  it('disables the submit button until a name is entered', () => {
    render(<ProjectSetupTab onDone={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'settings.projects.createButton' }).hasAttribute('disabled')).toBe(true);

    fireEvent.change(screen.getByPlaceholderText('settings.projects.namePlaceholder'), { target: { value: 'Neues Projekt' } });
    expect(screen.getByRole('button', { name: 'settings.projects.createButton' }).hasAttribute('disabled')).toBe(false);
  });

  it('creates the project, selects it, resets the form and reports success', async () => {
    apiMocks.createProject.mockResolvedValue(axiosResponse(newProject));
    apiMocks.getProjects.mockResolvedValue(axiosResponse([newProject]));
    const onDone = vi.fn();
    render(<ProjectSetupTab onDone={onDone} />);

    fireEvent.change(screen.getByPlaceholderText('settings.projects.namePlaceholder'), { target: { value: 'Neues Projekt' } });
    fireEvent.change(screen.getByPlaceholderText('settings.projects.descriptionPlaceholder'), { target: { value: 'Beschreibung' } });
    fireEvent.click(screen.getByRole('button', { name: 'settings.projects.createButton' }));

    await waitFor(() => expect(apiMocks.createProject).toHaveBeenCalledWith({
      name: 'Neues Projekt',
      description: 'Beschreibung',
      team_id: undefined,
      color: '#e4002b',
    }));
    await waitFor(() => expect(settingsValue.setSelectedProject).toHaveBeenCalledWith(newProject));
    expect(settingsValue.setProjects).toHaveBeenCalledWith([newProject]);
    expect(settingsValue.showToast).toHaveBeenCalledWith('settings.toast.projectCreated', 'success');
    expect(onDone).toHaveBeenCalledOnce();
    // Formular ist nach erfolgreicher Anlage zurückgesetzt.
    expect((screen.getByPlaceholderText('settings.projects.namePlaceholder') as HTMLInputElement).value).toBe('');
  });

  it('reports a failed creation without resetting the form or calling onDone', async () => {
    apiMocks.createProject.mockRejectedValue(new Error('boom'));
    const onDone = vi.fn();
    render(<ProjectSetupTab onDone={onDone} />);

    fireEvent.change(screen.getByPlaceholderText('settings.projects.namePlaceholder'), { target: { value: 'Kaputt' } });
    fireEvent.click(screen.getByRole('button', { name: 'settings.projects.createButton' }));

    await waitFor(() => expect(settingsValue.showToast).toHaveBeenCalledWith('settings.toast.projectCreateFailed', 'error', expect.any(Error)));
    expect(onDone).not.toHaveBeenCalled();
    expect((screen.getByPlaceholderText('settings.projects.namePlaceholder') as HTMLInputElement).value).toBe('Kaputt');
  });

  it('offers the team selector only for users in more than one team', () => {
    settingsValue = createSettingsContextValue({
      currentUser: { id: 1, username: 'admin', is_admin: true, teams: [{ id: 1, name: 'A' }, { id: 2, name: 'B' }] },
    });
    render(<ProjectSetupTab onDone={vi.fn()} />);
    expect(screen.getByText('settings.projects.teamLabel')).toBeTruthy();
  });

  it('hides the team selector for a user in a single team', () => {
    settingsValue = createSettingsContextValue({
      currentUser: { id: 1, username: 'admin', is_admin: true, teams: [{ id: 1, name: 'A' }] },
    });
    render(<ProjectSetupTab onDone={vi.fn()} />);
    expect(screen.queryByText('settings.projects.teamLabel')).toBeNull();
  });

  it('calls onDone when the back button is clicked', () => {
    const onDone = vi.fn();
    render(<ProjectSetupTab onDone={onDone} />);
    fireEvent.click(screen.getByText('settings.projects.backToList'));
    expect(onDone).toHaveBeenCalledOnce();
  });
});
