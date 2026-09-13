import type { DiscoverableProject, Project, ProjectAccessRequest, ProjectMember, User } from '@/types/domain';
import { axiosResponse } from '@/test/http';
import { createSettingsContextValue } from '@/test/settingsContext';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import React from 'react';

const apiMocks = vi.hoisted(() => ({
  getProjectFiles: vi.fn(),
  deleteProject: vi.fn(),
  getProjects: vi.fn(),
  updateProject: vi.fn(),
  completeProject: vi.fn(),
  getKnowledgeSources: vi.fn(),
  getDiscoverableProjects: vi.fn(),
  requestProjectAccess: vi.fn(),
  getProjectAccessRequests: vi.fn(),
  resolveProjectAccessRequest: vi.fn(),
  getProjectMembers: vi.fn(),
  getProjectMemberCandidates: vi.fn(),
  addProjectMember: vi.fn(),
  updateProjectMemberRole: vi.fn(),
  removeProjectMember: vi.fn(),
}));

vi.mock('@/app/services/api', () => ({ API_URL: 'http://api.test', api: apiMocks }));
vi.mock('@/lib/i18n/LanguageContext', () => ({
  useLanguage: () => ({
    t: (key: string, values?: Record<string, string | number>) =>
      values?.name !== undefined ? `${key}:${values.name}` : key,
  }),
}));

let settingsValue = createSettingsContextValue();
vi.mock('@/components/settings/SettingsContext', () => ({
  useSettings: () => settingsValue,
}));

import { ProjectsTab } from './ProjectsTab';

function axiosError(detail?: string) {
  return Object.assign(new Error('request failed'), {
    isAxiosError: true,
    response: { status: 400, data: detail ? { detail } : {} },
  });
}

const project = (overrides: Partial<Project> = {}): Project => ({
  id: 1, name: 'Projekt A', creator_id: 1, color: '#111111', ...overrides,
});
const member = (overrides: Partial<ProjectMember>): ProjectMember => ({
  id: 1, user_id: 1, user_name: 'Name', role: 'member', ...overrides,
});
const accessRequest = (overrides: Partial<ProjectAccessRequest>): ProjectAccessRequest => ({
  id: 1, user_id: 1, user_name: 'Anfragende:r', status: 'pending', ...overrides,
});
const candidate = (overrides: Partial<User>): User => ({
  id: 5, username: 'kim', name: 'Kim Miller', ...overrides,
});

/** Öffnet den Mitglieder-/Zugriffsanfragen-Bereich des (einzigen) Projekts. */
async function expandMembers() {
  fireEvent.click(screen.getByTitle('settings.projects.members.toggleTitle'));
  await waitFor(() => expect(apiMocks.getProjectMembers).toHaveBeenCalledOnce());
}

/** Wählt in einem gerade offenen Radix-Select-Dropdown den Eintrag mit diesem Text. */
function pickFromOpenListbox(text: string) {
  const listbox = screen.getByRole('listbox');
  fireEvent.click(within(listbox).getByText(text));
}

describe('ProjectsTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    settingsValue = createSettingsContextValue({ projects: [project()] });
    apiMocks.getDiscoverableProjects.mockResolvedValue(axiosResponse([]));
    apiMocks.getProjectMembers.mockResolvedValue(axiosResponse([]));
    apiMocks.getProjectAccessRequests.mockResolvedValue(axiosResponse([]));
    apiMocks.getProjectMemberCandidates.mockResolvedValue(axiosResponse([]));
  });

  describe('Fokus setzen', () => {
    it('focuses the project and loads its files', async () => {
      apiMocks.getProjectFiles.mockResolvedValue(axiosResponse(['a.cbl']));
      render(<ProjectsTab onNewProject={vi.fn()} />);
      fireEvent.click(screen.getByText('settings.projects.select'));

      expect(settingsValue.setSelectedProject).toHaveBeenCalledWith(project());
      expect(settingsValue.showToast).toHaveBeenCalledWith('settings.toast.projectFocused:Projekt A', 'success');
      await waitFor(() => expect(settingsValue.setFiles).toHaveBeenCalledWith(['a.cbl']));
    });

    it('keeps the focus but reports a failure when the file list cannot be loaded', async () => {
      apiMocks.getProjectFiles.mockRejectedValue(new Error('boom'));
      render(<ProjectsTab onNewProject={vi.fn()} />);
      fireEvent.click(screen.getByText('settings.projects.select'));

      expect(settingsValue.setSelectedProject).toHaveBeenCalledWith(project());
      await waitFor(() => expect(settingsValue.showToast).toHaveBeenCalledWith('settings.toast.filesFetchFailed', 'error', expect.any(Error)));
    });
  });

  describe('Löschen mit Bestätigung', () => {
    it('aborts without calling the API when the confirmation is declined', () => {
      vi.stubGlobal('confirm', vi.fn(() => false));
      render(<ProjectsTab onNewProject={vi.fn()} />);
      fireEvent.click(screen.getByTitle('settings.projects.deleteTitle'));
      expect(apiMocks.deleteProject).not.toHaveBeenCalled();
      vi.unstubAllGlobals();
    });

    it('deletes the project, refreshes the list, and clears the focus if it was the active one', async () => {
      vi.stubGlobal('confirm', vi.fn(() => true));
      apiMocks.deleteProject.mockResolvedValue(axiosResponse({}));
      apiMocks.getProjects.mockResolvedValue(axiosResponse([]));
      settingsValue = createSettingsContextValue({ projects: [project()], selectedProject: project() });
      render(<ProjectsTab onNewProject={vi.fn()} />);

      fireEvent.click(screen.getByTitle('settings.projects.deleteTitle'));
      await waitFor(() => expect(apiMocks.deleteProject).toHaveBeenCalledWith(1));
      expect(settingsValue.showToast).toHaveBeenCalledWith('settings.toast.projectDeleted:Projekt A', 'success');
      await waitFor(() => expect(settingsValue.setProjects).toHaveBeenCalledWith([]));
      expect(settingsValue.setSelectedProject).toHaveBeenCalledWith(null);
      expect(settingsValue.setFiles).toHaveBeenCalledWith([]);
      vi.unstubAllGlobals();
    });

    it('does not clear the focus when a different project is deleted', async () => {
      vi.stubGlobal('confirm', vi.fn(() => true));
      apiMocks.deleteProject.mockResolvedValue(axiosResponse({}));
      apiMocks.getProjects.mockResolvedValue(axiosResponse([]));
      const other = project({ id: 2, name: 'Andere' });
      settingsValue = createSettingsContextValue({ projects: [other], selectedProject: project() });
      render(<ProjectsTab onNewProject={vi.fn()} />);

      fireEvent.click(screen.getByTitle('settings.projects.deleteTitle'));
      await waitFor(() => expect(apiMocks.deleteProject).toHaveBeenCalledWith(2));
      expect(settingsValue.setSelectedProject).not.toHaveBeenCalled();
      vi.unstubAllGlobals();
    });

    it('shows a toast and keeps the project on a failed deletion', async () => {
      vi.stubGlobal('confirm', vi.fn(() => true));
      apiMocks.deleteProject.mockRejectedValue(new Error('boom'));
      render(<ProjectsTab onNewProject={vi.fn()} />);

      fireEvent.click(screen.getByTitle('settings.projects.deleteTitle'));
      await waitFor(() => expect(settingsValue.showToast).toHaveBeenCalledWith('settings.toast.projectDeleteFailed', 'error', expect.any(Error)));
      expect(settingsValue.setProjects).not.toHaveBeenCalled();
      vi.unstubAllGlobals();
    });
  });

  describe('Bearbeiten', () => {
    it('updates the project list and the active focus on save', async () => {
      apiMocks.updateProject.mockResolvedValue({ data: { id: 1, name: 'Projekt A2' } });
      settingsValue = createSettingsContextValue({ projects: [project()], selectedProject: project() });
      render(<ProjectsTab onNewProject={vi.fn()} />);

      fireEvent.click(screen.getByTitle('settings.projects.editTitle'));
      fireEvent.change(screen.getByDisplayValue('Projekt A'), { target: { value: 'Projekt A2' } });
      fireEvent.click(screen.getByText('Speichern'));

      await waitFor(() => expect(apiMocks.updateProject).toHaveBeenCalledWith(1, {
        name: 'Projekt A2', description: undefined, color: '#111111', expose_code_analysis_globally: false,
      }));
      expect(settingsValue.setProjects).toHaveBeenCalledOnce();
      expect(settingsValue.setSelectedProject).toHaveBeenCalledOnce();
      expect(settingsValue.showToast).toHaveBeenCalledWith('Projekt aktualisiert', 'success');
    });

    it('shows an error and stays in edit mode when saving fails', async () => {
      apiMocks.updateProject.mockRejectedValue(new Error('boom'));
      render(<ProjectsTab onNewProject={vi.fn()} />);

      fireEvent.click(screen.getByTitle('settings.projects.editTitle'));
      fireEvent.click(screen.getByText('Speichern'));

      await waitFor(() => expect(settingsValue.showToast).toHaveBeenCalledWith('Fehler beim Aktualisieren', 'error', expect.any(Error)));
      expect(screen.getByText('Speichern')).toBeTruthy();
    });
  });

  describe('Sichtbarkeit der Verwaltungsaktionen', () => {
    it('never shows a role selector or remove button for the project creator, even to an admin', async () => {
      settingsValue = createSettingsContextValue({
        projects: [project({ creator_id: 99 })],
        currentUser: { id: 1, username: 'admin', is_admin: true },
      });
      apiMocks.getProjectMembers.mockResolvedValue(axiosResponse([member({ user_id: 99, user_name: 'Ersteller', role: 'admin' })]));
      render(<ProjectsTab onNewProject={vi.fn()} />);
      await expandMembers();

      await waitFor(() => expect(screen.getByText('Ersteller')).toBeTruthy());
      expect(screen.queryByRole('combobox')).toBeNull();
      expect(screen.queryByTitle('settings.projects.members.removeMemberTitle')).toBeNull();
    });

    it('shows no management actions to a regular, non-admin member', async () => {
      settingsValue = createSettingsContextValue({
        projects: [project({ creator_id: 99 })],
        currentUser: { id: 2, username: 'u', is_admin: false },
      });
      apiMocks.getProjectMembers.mockResolvedValue(axiosResponse([
        member({ user_id: 99, user_name: 'Ersteller', role: 'admin' }),
        member({ id: 2, user_id: 2, user_name: 'Ich', role: 'member' }),
      ]));
      render(<ProjectsTab onNewProject={vi.fn()} />);
      await expandMembers();

      await waitFor(() => expect(screen.getByText('Ich')).toBeTruthy());
      expect(screen.queryByRole('combobox')).toBeNull();
      expect(screen.queryByTitle('settings.projects.members.removeMemberTitle')).toBeNull();
      // Weder Hinzufügen-Zeile noch Zugriffsanfragen — beide sind admin-gated.
      expect(apiMocks.getProjectMemberCandidates).not.toHaveBeenCalled();
      expect(apiMocks.getProjectAccessRequests).not.toHaveBeenCalled();
      expect(screen.queryByTitle('settings.projects.editTitle')).toBeNull();
      expect(screen.queryByTitle('settings.projects.completeTitle')).toBeNull();
    });
  });

  describe('Rollenwechsel', () => {
    it('sends exactly the changed user/project combination and refreshes the list', async () => {
      apiMocks.getProjectMembers
        .mockResolvedValueOnce(axiosResponse([member({ id: 2, user_id: 2, user_name: 'Bob', role: 'member' })]))
        .mockResolvedValueOnce(axiosResponse([member({ id: 2, user_id: 2, user_name: 'Bob', role: 'admin' })]));
      apiMocks.updateProjectMemberRole.mockResolvedValue(axiosResponse({}));
      render(<ProjectsTab onNewProject={vi.fn()} />);
      await expandMembers();
      await waitFor(() => expect(screen.getByText('Bob')).toBeTruthy());

      fireEvent.click(screen.getByRole('combobox'));
      pickFromOpenListbox('settings.projects.members.roleAdmin');

      await waitFor(() => expect(apiMocks.updateProjectMemberRole).toHaveBeenCalledWith(1, 2, 'admin'));
      expect(settingsValue.showToast).toHaveBeenCalledWith('settings.projects.members.roleChanged', 'success');
      expect(apiMocks.getProjectMembers).toHaveBeenCalledTimes(2);
    });

    it('shows a toast without refreshing when the role change fails', async () => {
      apiMocks.getProjectMembers.mockResolvedValue(axiosResponse([member({ id: 2, user_id: 2, user_name: 'Bob', role: 'member' })]));
      apiMocks.updateProjectMemberRole.mockRejectedValue(axiosError('Nicht erlaubt'));
      render(<ProjectsTab onNewProject={vi.fn()} />);
      await expandMembers();
      await waitFor(() => expect(screen.getByText('Bob')).toBeTruthy());

      fireEvent.click(screen.getByRole('combobox'));
      pickFromOpenListbox('settings.projects.members.roleAdmin');

      await waitFor(() => expect(settingsValue.showToast).toHaveBeenCalledWith('Nicht erlaubt', 'error', expect.any(Error)));
      expect(apiMocks.getProjectMembers).toHaveBeenCalledOnce();
    });
  });

  describe('Mitglied entfernen', () => {
    it('removes exactly the targeted member and refreshes the list', async () => {
      apiMocks.getProjectMembers
        .mockResolvedValueOnce(axiosResponse([
          member({ id: 2, user_id: 2, user_name: 'Bob', role: 'member' }),
          member({ id: 3, user_id: 3, user_name: 'Carla', role: 'member' }),
        ]))
        .mockResolvedValueOnce(axiosResponse([member({ id: 3, user_id: 3, user_name: 'Carla', role: 'member' })]));
      apiMocks.removeProjectMember.mockResolvedValue(axiosResponse({}));
      render(<ProjectsTab onNewProject={vi.fn()} />);
      await expandMembers();
      await waitFor(() => expect(screen.getByText('Carla')).toBeTruthy());

      fireEvent.click(screen.getAllByTitle('settings.projects.members.removeMemberTitle')[1]);

      await waitFor(() => expect(apiMocks.removeProjectMember).toHaveBeenCalledWith(1, 3));
      expect(apiMocks.removeProjectMember).toHaveBeenCalledOnce();
      expect(settingsValue.showToast).toHaveBeenCalledWith('settings.toast.memberRemoved', 'success');
    });

    // Steht stellvertretend für die Backend-Regel "letzter Admin bleibt": die Oberfläche
    // muss die Ablehnung sichtbar machen statt sie zu verschlucken oder den Nutzer trotzdem
    // aus der Liste zu entfernen.
    it('surfaces a server-side rejection (e.g. the last remaining admin) without removing the member from the list', async () => {
      apiMocks.getProjectMembers.mockResolvedValue(axiosResponse([member({ id: 2, user_id: 2, user_name: 'Bob', role: 'member' })]));
      apiMocks.removeProjectMember.mockRejectedValue(axiosError('Der letzte Admin kann nicht entfernt werden'));
      render(<ProjectsTab onNewProject={vi.fn()} />);
      await expandMembers();
      await waitFor(() => expect(screen.getByText('Bob')).toBeTruthy());

      fireEvent.click(screen.getByTitle('settings.projects.members.removeMemberTitle'));

      await waitFor(() => expect(settingsValue.showToast).toHaveBeenCalledWith('Der letzte Admin kann nicht entfernt werden', 'error', expect.any(Error)));
      // Kein zweiter getProjectMembers-Aufruf (kein Refresh bei Fehlschlag) -- Bob bleibt sichtbar.
      expect(apiMocks.getProjectMembers).toHaveBeenCalledOnce();
      expect(screen.getByText('Bob')).toBeTruthy();
    });
  });

  describe('Mitglied hinzufügen', () => {
    it('filters candidates who are already members out of the picker', async () => {
      apiMocks.getProjectMembers.mockResolvedValue(axiosResponse([member({ user_id: 1, user_name: 'Ersteller', role: 'admin' })]));
      apiMocks.getProjectMemberCandidates.mockResolvedValue(axiosResponse([
        candidate({ id: 1, username: 'ersteller', name: 'Ersteller' }),
        candidate({ id: 5, username: 'kim', name: 'Kim Miller' }),
      ]));
      render(<ProjectsTab onNewProject={vi.fn()} />);
      await expandMembers();
      await waitFor(() => expect(apiMocks.getProjectMemberCandidates).toHaveBeenCalledOnce());

      const [userPicker] = screen.getAllByRole('combobox');
      fireEvent.click(userPicker);
      const listbox = screen.getByRole('listbox');
      expect(within(listbox).queryByText('Ersteller')).toBeNull();
      expect(within(listbox).getByText('Kim Miller')).toBeTruthy();
    });

    it('adds the selected candidate with the chosen role', async () => {
      apiMocks.getProjectMembers.mockResolvedValue(axiosResponse([member({ user_id: 1, user_name: 'Ersteller', role: 'admin' })]));
      apiMocks.getProjectMemberCandidates.mockResolvedValue(axiosResponse([candidate({ id: 5, name: 'Kim Miller' })]));
      apiMocks.addProjectMember.mockResolvedValue(axiosResponse({}));
      render(<ProjectsTab onNewProject={vi.fn()} />);
      await expandMembers();
      await waitFor(() => expect(apiMocks.getProjectMemberCandidates).toHaveBeenCalledOnce());

      const [userPicker, rolePicker] = screen.getAllByRole('combobox');
      fireEvent.click(userPicker);
      pickFromOpenListbox('Kim Miller');

      fireEvent.click(rolePicker);
      pickFromOpenListbox('settings.projects.members.roleAdmin');

      const addButton = screen.getAllByRole('button').find((b) => b.querySelector('.lucide-user-plus'))!;
      fireEvent.click(addButton);

      await waitFor(() => expect(apiMocks.addProjectMember).toHaveBeenCalledWith(1, 5, 'admin'));
      expect(settingsValue.showToast).toHaveBeenCalledWith('settings.toast.memberAdded', 'success');
    });

    it('disables the add button until a candidate is selected', async () => {
      apiMocks.getProjectMembers.mockResolvedValue(axiosResponse([member({ user_id: 1, user_name: 'Ersteller', role: 'admin' })]));
      apiMocks.getProjectMemberCandidates.mockResolvedValue(axiosResponse([candidate({ id: 5, name: 'Kim Miller' })]));
      render(<ProjectsTab onNewProject={vi.fn()} />);
      await expandMembers();
      await waitFor(() => expect(apiMocks.getProjectMemberCandidates).toHaveBeenCalledOnce());

      const addButton = screen.getAllByRole('button').find((b) => b.querySelector('.lucide-user-plus'))!;
      expect(addButton.hasAttribute('disabled')).toBe(true);
    });
  });

  describe('Zugriffsanfragen annehmen/ablehnen', () => {
    it('approves a request, refreshes both requests and members, with the approval-specific toast', async () => {
      apiMocks.getProjectMembers.mockResolvedValue(axiosResponse([]));
      apiMocks.getProjectAccessRequests.mockResolvedValue(axiosResponse([accessRequest({ id: 7, user_id: 8, user_name: 'Anna' })]));
      apiMocks.resolveProjectAccessRequest.mockResolvedValue(axiosResponse({}));
      render(<ProjectsTab onNewProject={vi.fn()} />);
      await expandMembers();
      await waitFor(() => expect(screen.getByText('Anna')).toBeTruthy());

      fireEvent.click(screen.getByTitle('settings.projects.members.approveTitle'));

      await waitFor(() => expect(apiMocks.resolveProjectAccessRequest).toHaveBeenCalledWith(1, 7, 'approved'));
      expect(settingsValue.showToast).toHaveBeenCalledWith('settings.toast.accessRequestApproved', 'success');
      // Annehmen zieht sowohl die Anfragenliste als auch die Mitgliederliste nach.
      expect(apiMocks.getProjectAccessRequests).toHaveBeenCalledTimes(2);
      expect(apiMocks.getProjectMembers).toHaveBeenCalledTimes(2);
    });

    it('rejects a request, refreshes only the requests list, with the rejection-specific toast', async () => {
      apiMocks.getProjectMembers.mockResolvedValue(axiosResponse([]));
      apiMocks.getProjectAccessRequests.mockResolvedValue(axiosResponse([accessRequest({ id: 7, user_id: 8, user_name: 'Anna' })]));
      apiMocks.resolveProjectAccessRequest.mockResolvedValue(axiosResponse({}));
      render(<ProjectsTab onNewProject={vi.fn()} />);
      await expandMembers();
      await waitFor(() => expect(screen.getByText('Anna')).toBeTruthy());

      fireEvent.click(screen.getByTitle('settings.projects.members.rejectTitle'));

      await waitFor(() => expect(apiMocks.resolveProjectAccessRequest).toHaveBeenCalledWith(1, 7, 'rejected'));
      expect(settingsValue.showToast).toHaveBeenCalledWith('settings.toast.accessRequestRejected', 'success');
      expect(apiMocks.getProjectAccessRequests).toHaveBeenCalledTimes(2);
      expect(apiMocks.getProjectMembers).toHaveBeenCalledOnce();
    });

    it('shows the server error detail when resolving a request fails', async () => {
      apiMocks.getProjectMembers.mockResolvedValue(axiosResponse([]));
      apiMocks.getProjectAccessRequests.mockResolvedValue(axiosResponse([accessRequest({ id: 7, user_id: 8, user_name: 'Anna' })]));
      apiMocks.resolveProjectAccessRequest.mockRejectedValue(axiosError('Anfrage bereits bearbeitet'));
      render(<ProjectsTab onNewProject={vi.fn()} />);
      await expandMembers();
      await waitFor(() => expect(screen.getByText('Anna')).toBeTruthy());

      fireEvent.click(screen.getByTitle('settings.projects.members.approveTitle'));

      await waitFor(() => expect(settingsValue.showToast).toHaveBeenCalledWith('Anfrage bereits bearbeitet', 'error', expect.any(Error)));
    });
  });

  describe('Entdeckbare Projekte / Zugriff anfragen', () => {
    const discoverable = (overrides: Partial<DiscoverableProject> = {}): DiscoverableProject => ({
      id: 42, name: 'Fremdes Projekt', creator_id: 9, ...overrides,
    });

    it('disables the button and shows a pending label when the request stays pending', async () => {
      apiMocks.getDiscoverableProjects.mockResolvedValue(axiosResponse([discoverable()]));
      apiMocks.requestProjectAccess.mockResolvedValue(axiosResponse({ status: 'pending', message: 'Angefragt' }));
      render(<ProjectsTab onNewProject={vi.fn()} />);

      await waitFor(() => expect(screen.getByText('Fremdes Projekt')).toBeTruthy());
      fireEvent.click(screen.getByText('settings.projects.discoverable.requestButton'));

      await waitFor(() => expect(apiMocks.requestProjectAccess).toHaveBeenCalledWith(42));
      expect(settingsValue.showToast).toHaveBeenCalledWith('Angefragt', 'success');
      await waitFor(() => expect(screen.getByText('settings.projects.discoverable.pending')).toBeTruthy());
      expect(screen.getByText('settings.projects.discoverable.pending').closest('button')!.hasAttribute('disabled')).toBe(true);
    });

    it('refreshes the discoverable list when access is granted immediately', async () => {
      apiMocks.getDiscoverableProjects
        .mockResolvedValueOnce(axiosResponse([discoverable()]))
        .mockResolvedValueOnce(axiosResponse([]));
      apiMocks.requestProjectAccess.mockResolvedValue(axiosResponse({ status: 'approved' }));
      render(<ProjectsTab onNewProject={vi.fn()} />);

      await waitFor(() => expect(screen.getByText('Fremdes Projekt')).toBeTruthy());
      fireEvent.click(screen.getByText('settings.projects.discoverable.requestButton'));

      await waitFor(() => expect(apiMocks.getDiscoverableProjects).toHaveBeenCalledTimes(2));
      await waitFor(() => expect(screen.queryByText('Fremdes Projekt')).toBeNull());
    });

    it('shows a toast on a failed access request', async () => {
      apiMocks.getDiscoverableProjects.mockResolvedValue(axiosResponse([discoverable()]));
      apiMocks.requestProjectAccess.mockRejectedValue(axiosError('Bereits Mitglied'));
      render(<ProjectsTab onNewProject={vi.fn()} />);

      await waitFor(() => expect(screen.getByText('Fremdes Projekt')).toBeTruthy());
      fireEvent.click(screen.getByText('settings.projects.discoverable.requestButton'));

      await waitFor(() => expect(settingsValue.showToast).toHaveBeenCalledWith('Bereits Mitglied', 'error', expect.any(Error)));
    });
  });

  describe('Projekt abschließen', () => {
    it('promotes exactly the checked sources and clears the focus if it was the active project', async () => {
      apiMocks.completeProject.mockResolvedValue(axiosResponse({}));
      apiMocks.getProjects.mockResolvedValue(axiosResponse([]));
      apiMocks.getKnowledgeSources.mockResolvedValue(axiosResponse([]));
      settingsValue = createSettingsContextValue({
        projects: [project()],
        selectedProject: project(),
        connectedSources: [
          { id: 10, name: 'Quelle A', type: 'git', project_id: 1 },
          { id: 11, name: 'Quelle B', type: 'git', project_id: 1 },
        ],
      });
      render(<ProjectsTab onNewProject={vi.fn()} />);

      fireEvent.click(screen.getByTitle('settings.projects.completeTitle'));
      // "Quelle A (git)" erscheint zweimal (Auswahl-Checkbox im Abschluss-Panel und
      // separat im "Verknüpfte Quellen"-Fußbereich der Karte) -- die Checkbox ist die erste.
      fireEvent.click(screen.getAllByText('Quelle A (git)')[0].closest('label')!.querySelector('input')!);
      fireEvent.click(screen.getByText('settings.projects.complete.confirm'));

      await waitFor(() => expect(apiMocks.completeProject).toHaveBeenCalledWith(1, { promote_source_ids: [10] }));
      expect(settingsValue.setSelectedProject).toHaveBeenCalledWith(null);
      expect(settingsValue.setFiles).toHaveBeenCalledWith([]);
      expect(settingsValue.showToast).toHaveBeenCalledWith('settings.toast.projectCompleted:Projekt A', 'success');
    });

    it('shows a toast and keeps the completion panel open on failure', async () => {
      apiMocks.completeProject.mockRejectedValue(axiosError('Noch offene Aufgaben'));
      render(<ProjectsTab onNewProject={vi.fn()} />);

      fireEvent.click(screen.getByTitle('settings.projects.completeTitle'));
      fireEvent.click(screen.getByText('settings.projects.complete.confirm'));

      await waitFor(() => expect(settingsValue.showToast).toHaveBeenCalledWith('Noch offene Aufgaben', 'error', expect.any(Error)));
      expect(screen.getByText('settings.projects.complete.confirm')).toBeTruthy();
      expect(settingsValue.setSelectedProject).not.toHaveBeenCalled();
    });
  });
});
