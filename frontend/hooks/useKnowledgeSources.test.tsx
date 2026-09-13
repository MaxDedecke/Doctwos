import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { axiosResponse } from '@/test/http';
import { api } from '@/app/services/api';
import type { KnowledgeSource, Project } from '@/types/domain';
import { useKnowledgeSources } from './useKnowledgeSources';

vi.mock('@/app/services/api', () => ({
  api: {
    getKnowledgeSources: vi.fn(),
    getProjectReferences: vi.fn(),
  },
}));

const mockedApi = vi.mocked(api);
const showToast = vi.fn();
const t = (key: string, values?: Record<string, string | number>) =>
  values ? `${key}:${JSON.stringify(values)}` : key;

function source(overrides: Partial<KnowledgeSource> = {}): KnowledgeSource {
  return { id: 1, name: 'ENG Docs', type: 'Confluence', ...overrides };
}

function project(overrides: Partial<Project> = {}): Project {
  return { id: 1, name: 'Kontoführung', ...overrides };
}

describe('useKnowledgeSources', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    localStorage.clear();
    mockedApi.getKnowledgeSources.mockResolvedValue(axiosResponse([]));
  });

  it('does not load sources before login and keeps the built-in demo source', () => {
    const { result } = renderHook(() => useKnowledgeSources({ isLoggedIn: false, selectedProject: null, t, showToast }));
    expect(mockedApi.getKnowledgeSources).not.toHaveBeenCalled();
    expect(result.current.connectedSources).toHaveLength(1);
    expect(result.current.connectedSources[0]).toMatchObject({ id: 'conf-init', type: 'Confluence' });
  });

  it('loads sources once logged in, replacing the demo placeholder', async () => {
    const sources = [source({ id: 9 })];
    mockedApi.getKnowledgeSources.mockResolvedValue(axiosResponse(sources));

    const { result } = renderHook(() => useKnowledgeSources({ isLoggedIn: true, selectedProject: null, t, showToast }));

    await waitFor(() => expect(result.current.connectedSources).toEqual(sources));
  });

  it('leaves the previous sources in place when loading fails', async () => {
    mockedApi.getKnowledgeSources.mockRejectedValue(new Error('network down'));

    const { result } = renderHook(() => useKnowledgeSources({ isLoggedIn: true, selectedProject: null, t, showToast }));

    await act(async () => { await Promise.resolve(); });
    expect(result.current.connectedSources).toHaveLength(1);
    expect(result.current.connectedSources[0].id).toBe('conf-init');
  });

  it('drops pinned ids that no longer refer to a loaded source', async () => {
    localStorage.setItem('pinnedSourceIds', JSON.stringify([9, 41]));
    mockedApi.getKnowledgeSources.mockResolvedValue(axiosResponse([source({ id: 9 })]));

    const { result } = renderHook(() => useKnowledgeSources({ isLoggedIn: true, selectedProject: null, t, showToast }));

    await waitFor(() => expect(result.current.pinnedSourceIds).toEqual([9]));
    expect(JSON.parse(localStorage.getItem('pinnedSourceIds') as string)).toEqual([9]);
  });

  describe('togglePinSource', () => {
    it('pins and unpins a source, persisting the change', () => {
      const { result } = renderHook(() => useKnowledgeSources({ isLoggedIn: false, selectedProject: null, t, showToast }));

      act(() => result.current.togglePinSource(9));
      expect(result.current.pinnedSourceIds).toEqual([9]);
      expect(JSON.parse(localStorage.getItem('pinnedSourceIds') as string)).toEqual([9]);

      act(() => result.current.togglePinSource(9));
      expect(result.current.pinnedSourceIds).toEqual([]);
      expect(JSON.parse(localStorage.getItem('pinnedSourceIds') as string)).toEqual([]);
    });

    it('refuses a fifth pin and shows an error toast instead', () => {
      const { result } = renderHook(() => useKnowledgeSources({ isLoggedIn: false, selectedProject: null, t, showToast }));

      act(() => {
        [1, 2, 3, 4].forEach((id) => result.current.togglePinSource(id));
      });
      expect(result.current.pinnedSourceIds).toEqual([1, 2, 3, 4]);

      act(() => result.current.togglePinSource(5));
      expect(result.current.pinnedSourceIds).toEqual([1, 2, 3, 4]);
      expect(showToast).toHaveBeenCalledWith('settings.sourcesTab.maxPinsReached', 'error');
    });
  });

  describe('loadFileReferences', () => {
    it('does nothing without a selected project or override', async () => {
      const { result } = renderHook(() => useKnowledgeSources({ isLoggedIn: false, selectedProject: null, t, showToast }));

      await act(async () => { await result.current.loadFileReferences('ACCOUNT.cbl'); });

      expect(mockedApi.getProjectReferences).not.toHaveBeenCalled();
      expect(result.current.fileReferences).toEqual([]);
    });

    it('loads references for the currently selected project', async () => {
      const references = [{ file_path: 'ACCOUNT.cbl', line: 12 }];
      mockedApi.getProjectReferences.mockResolvedValue(axiosResponse(references));
      const { result } = renderHook(() =>
        useKnowledgeSources({ isLoggedIn: false, selectedProject: project({ id: 3 }), t, showToast }));

      await act(async () => { await result.current.loadFileReferences('ACCOUNT.cbl', 'BUCHEN'); });

      expect(mockedApi.getProjectReferences).toHaveBeenCalledWith(3, 'ACCOUNT.cbl', 'BUCHEN');
      expect(result.current.fileReferences).toEqual(references);
      expect(result.current.isLoadingReferences).toBe(false);
    });

    it('clears stale references instead of carrying them over when the lookup fails', async () => {
      mockedApi.getProjectReferences.mockResolvedValueOnce(axiosResponse([{ file_path: 'OLD.cbl' }]));
      const { result, rerender } = renderHook(
        ({ selectedProject }) => useKnowledgeSources({ isLoggedIn: false, selectedProject, t, showToast }),
        { initialProps: { selectedProject: project({ id: 1 }) } },
      );
      await act(async () => { await result.current.loadFileReferences('OLD.cbl'); });
      expect(result.current.fileReferences).toEqual([{ file_path: 'OLD.cbl' }]);

      mockedApi.getProjectReferences.mockRejectedValueOnce(new Error('network down'));
      rerender({ selectedProject: project({ id: 2 }) });
      await act(async () => { await result.current.loadFileReferences('NEW.cbl'); });

      expect(mockedApi.getProjectReferences).toHaveBeenLastCalledWith(2, 'NEW.cbl', undefined);
      expect(result.current.fileReferences).toEqual([]);
    });

    it('prefers an explicit project override over the currently selected project', async () => {
      mockedApi.getProjectReferences.mockResolvedValue(axiosResponse([]));
      const { result } = renderHook(() =>
        useKnowledgeSources({ isLoggedIn: false, selectedProject: project({ id: 1 }), t, showToast }));

      await act(async () => {
        await result.current.loadFileReferences('OTHER.cbl', null, project({ id: 42 }));
      });

      expect(mockedApi.getProjectReferences).toHaveBeenCalledWith(42, 'OTHER.cbl', undefined);
    });
  });
});
