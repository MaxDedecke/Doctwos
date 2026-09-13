import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { axiosResponse } from '@/test/http';
import { api } from '@/app/services/api';
import type { Project } from '@/types/domain';
import { useProjects } from './useProjects';

vi.mock('@/app/services/api', () => ({
  api: {
    getProjects: vi.fn(),
    getProjectStats: vi.fn(),
    getProjectFiles: vi.fn(),
    getProjectEntities: vi.fn(),
  },
}));

const mockedApi = vi.mocked(api);
const showToast = vi.fn();
const t = (key: string, values?: Record<string, string | number>) =>
  values ? `${key}:${JSON.stringify(values)}` : key;

function project(overrides: Partial<Project> = {}): Project {
  return { id: 1, name: 'Kontoführung', status: 'completed', ...overrides };
}

describe('useProjects', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockedApi.getProjects.mockResolvedValue(axiosResponse([]));
    mockedApi.getProjectFiles.mockResolvedValue(axiosResponse([]));
    mockedApi.getProjectEntities.mockResolvedValue(axiosResponse([]));
    mockedApi.getProjectStats.mockResolvedValue(axiosResponse({ total_files: 0, total_lines: 0, languages: [] }));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('does not load projects before login', () => {
    renderHook(() => useProjects({ isLoggedIn: false, isSettingsOpen: false, t, showToast }));
    expect(mockedApi.getProjects).not.toHaveBeenCalled();
  });

  it('loads projects once logged in and marks the backend connected', async () => {
    const projects = [project()];
    mockedApi.getProjects.mockResolvedValue(axiosResponse(projects));

    const { result } = renderHook(() => useProjects({ isLoggedIn: true, isSettingsOpen: false, t, showToast }));

    await waitFor(() => expect(result.current.projects).toEqual(projects));
    expect(result.current.backendStatus).toBe('connected');
  });

  it('marks the backend as errored and toasts when the initial load fails', async () => {
    const failure = new Error('network down');
    mockedApi.getProjects.mockRejectedValue(failure);

    const { result } = renderHook(() => useProjects({ isLoggedIn: true, isSettingsOpen: false, t, showToast }));

    await waitFor(() => expect(result.current.backendStatus).toBe('error'));
    expect(showToast).toHaveBeenCalledWith('page.toast.backendConnectionFailed', 'error', failure);
  });

  it('fetches stats for each project once the settings panel opens, and does not refetch on rerender', async () => {
    const projects = [project({ id: 1 }), project({ id: 2 })];
    mockedApi.getProjects.mockResolvedValue(axiosResponse(projects));
    mockedApi.getProjectStats.mockImplementation((id: number) =>
      Promise.resolve(axiosResponse({ total_files: id, total_lines: id * 10, languages: [] })));

    const { result, rerender } = renderHook(
      ({ isSettingsOpen }) => useProjects({ isLoggedIn: true, isSettingsOpen, t, showToast }),
      { initialProps: { isSettingsOpen: false } },
    );
    await waitFor(() => expect(result.current.projects).toEqual(projects));

    rerender({ isSettingsOpen: true });
    await waitFor(() => expect(Object.keys(result.current.projectStats)).toHaveLength(2));
    expect(result.current.projectStats[1]).toMatchObject({ total_files: 1 });
    expect(result.current.projectStats[2]).toMatchObject({ total_files: 2 });

    rerender({ isSettingsOpen: true });
    await Promise.resolve();
    expect(mockedApi.getProjectStats).toHaveBeenCalledTimes(2);
  });

  describe('polling while a project analysis is active', () => {
    beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));

    it('toasts success, refreshes stats, and reloads the selected project once it completes', async () => {
      const parsing = project({ id: 5, status: 'parsing', url: 'https://git.example/repo' });
      mockedApi.getProjects.mockResolvedValueOnce(axiosResponse([parsing]));
      const { result } = renderHook(() => useProjects({ isLoggedIn: true, isSettingsOpen: false, t, showToast }));
      await waitFor(() => expect(result.current.projects).toEqual([parsing]));

      await act(async () => {
        result.current.setSelectedProject(parsing);
      });

      const completed = { ...parsing, status: 'completed' };
      mockedApi.getProjects.mockResolvedValue(axiosResponse([completed]));
      mockedApi.getProjectFiles.mockResolvedValue(axiosResponse(['ACCOUNT.cbl']));
      mockedApi.getProjectEntities.mockResolvedValue(axiosResponse([{ id: 1, name: 'ACCOUNT', file_path: 'ACCOUNT.cbl', start_line: 1 }]));

      await act(async () => {
        await vi.advanceTimersByTimeAsync(2000);
      });

      expect(showToast).toHaveBeenCalledWith(`page.toast.projectAnalyzed:${JSON.stringify({ name: completed.name })}`, 'success');
      await waitFor(() => expect(result.current.projectStats[5]).toBeDefined());
      await waitFor(() => expect(result.current.selectedProject).toEqual(completed));
      expect(result.current.files).toEqual(['ACCOUNT.cbl']);
    });

    it('toasts an error for a project whose analysis fails, without touching the selection', async () => {
      const parsing = project({ id: 6, status: 'parsing' });
      mockedApi.getProjects.mockResolvedValueOnce(axiosResponse([parsing]));
      const { result } = renderHook(() => useProjects({ isLoggedIn: true, isSettingsOpen: false, t, showToast }));
      await waitFor(() => expect(result.current.projects).toEqual([parsing]));

      mockedApi.getProjects.mockResolvedValue(axiosResponse([{ ...parsing, status: 'error' }]));

      await act(async () => {
        await vi.advanceTimersByTimeAsync(2000);
      });

      expect(showToast).toHaveBeenCalledWith(`page.toast.projectAnalysisError:${JSON.stringify({ name: parsing.name })}`, 'error');
      expect(result.current.selectedProject).toBeNull();
    });

    it('stops polling once no project is still parsing or pending', async () => {
      const parsing = project({ id: 7, status: 'parsing' });
      mockedApi.getProjects.mockResolvedValueOnce(axiosResponse([parsing]));
      const { result } = renderHook(() => useProjects({ isLoggedIn: true, isSettingsOpen: false, t, showToast }));
      await waitFor(() => expect(result.current.projects).toEqual([parsing]));

      mockedApi.getProjects.mockResolvedValue(axiosResponse([{ ...parsing, status: 'completed' }]));
      await act(async () => {
        await vi.advanceTimersByTimeAsync(2000);
      });
      expect(mockedApi.getProjects).toHaveBeenCalledTimes(2);

      mockedApi.getProjects.mockClear();
      await act(async () => {
        await vi.advanceTimersByTimeAsync(6000);
      });
      expect(mockedApi.getProjects).not.toHaveBeenCalled();
    });
  });

  describe('selectProject', () => {
    it('clears every project-scoped field when selecting no project', async () => {
      const { result } = renderHook(() => useProjects({ isLoggedIn: false, isSettingsOpen: false, t, showToast }));
      await act(async () => {
        result.current.setSelectedProject(project());
        result.current.setFiles(['a.cbl']);
        result.current.setBranch('feature');
      });

      await act(async () => {
        await result.current.selectProject(null);
      });

      expect(result.current.selectedProject).toBeNull();
      expect(result.current.files).toEqual([]);
      expect(result.current.projectEntities).toEqual([]);
      expect(result.current.branch).toBe('main');
    });

    it('refuses to select a repository-backed project that is still analyzing', async () => {
      const stillParsing = project({ status: 'parsing', url: 'https://git.example/repo' });
      const { result } = renderHook(() => useProjects({ isLoggedIn: false, isSettingsOpen: false, t, showToast }));

      await act(async () => {
        await result.current.selectProject(stillParsing);
      });

      expect(showToast).toHaveBeenCalledWith(`page.toast.projectStillAnalyzing:${JSON.stringify({ name: stillParsing.name })}`, 'warning');
      expect(result.current.selectedProject).toBeNull();
      expect(mockedApi.getProjectFiles).not.toHaveBeenCalled();
    });

    it('allows a local project without a Git URL regardless of its status', async () => {
      const local = project({ status: null, url: null });
      mockedApi.getProjectFiles.mockResolvedValue(axiosResponse(['LOCAL.cbl']));
      const { result } = renderHook(() => useProjects({ isLoggedIn: false, isSettingsOpen: false, t, showToast }));

      await act(async () => {
        await result.current.selectProject(local);
      });

      expect(result.current.selectedProject).toEqual(local);
      expect(result.current.files).toEqual(['LOCAL.cbl']);
      expect(showToast).toHaveBeenCalledWith(`page.toast.projectSelected:${JSON.stringify({ name: local.name })}`, 'success');
    });

    it('shows an error toast when loading the newly selected project files fails', async () => {
      const failure = new Error('network down');
      mockedApi.getProjectFiles.mockRejectedValue(failure);
      const { result } = renderHook(() => useProjects({ isLoggedIn: false, isSettingsOpen: false, t, showToast }));

      await act(async () => {
        await result.current.selectProject(project());
      });

      expect(showToast).toHaveBeenCalledWith('page.toast.filesFetchFailed', 'error', failure);
      expect(result.current.selectedProject).toEqual(project());
    });

    it('replaces the previous project entities instead of carrying them over on project switch', async () => {
      const first = project({ id: 1 });
      const second = project({ id: 2, name: 'Zinsberechnung' });
      mockedApi.getProjectEntities.mockImplementation((id: number) =>
        Promise.resolve(axiosResponse([{ id, name: `Entity-${id}`, file_path: `${id}.cbl`, start_line: 1 }])));
      const { result } = renderHook(() => useProjects({ isLoggedIn: false, isSettingsOpen: false, t, showToast }));

      await act(async () => {
        await result.current.selectProject(first);
      });
      await waitFor(() => expect(result.current.projectEntities).toEqual([{ id: 1, name: 'Entity-1', file_path: '1.cbl', start_line: 1 }]));

      await act(async () => {
        await result.current.selectProject(second);
      });
      await waitFor(() => expect(result.current.projectEntities).toEqual([{ id: 2, name: 'Entity-2', file_path: '2.cbl', start_line: 1 }]));
    });
  });
});
