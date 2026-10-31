import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { axiosResponse } from '@/test/http';
import { api } from '@/app/services/api';
import { useOpenFileEntities } from './useOpenFileEntities';

vi.mock('@/app/services/api', () => ({ api: { getProjectEntities: vi.fn() } }));
const getEntities = vi.mocked(api.getProjectEntities);

describe('useOpenFileEntities', () => {
  beforeEach(() => {
    getEntities.mockReset();
    getEntities.mockImplementation(((projectId: number, file: string) =>
      Promise.resolve(axiosResponse([{ id: 1, name: `${projectId}:${file}`, file_path: file }]))) as never);
  });

  const names = (entities: { name?: string }[]) => entities.map((entity) => entity.name);

  it('stays idle while the full list is in use', () => {
    const { result } = renderHook(() => useOpenFileEntities(1, false, ['A.java']));
    expect(getEntities).not.toHaveBeenCalled();
    expect(result.current).toEqual([]);
  });

  it('loads every open file once and keeps a loaded file when another one opens', async () => {
    const { result, rerender } = renderHook(({ files }) => useOpenFileEntities(1, true, files), {
      initialProps: { files: ['A.java', 'A.java'] },
    });
    await waitFor(() => expect(names(result.current)).toEqual(['1:A.java']));

    rerender({ files: ['A.java', 'B.java'] });
    await waitFor(() => expect(names(result.current)).toEqual(['1:A.java', '1:B.java']));
    expect(getEntities).toHaveBeenCalledTimes(2);
  });

  it('drops closed files and does not show entities of the previous project', async () => {
    const { result, rerender } = renderHook(({ projectId, files }) => useOpenFileEntities(projectId, true, files), {
      initialProps: { projectId: 1, files: ['A.java', 'B.java'] },
    });
    await waitFor(() => expect(result.current).toHaveLength(2));

    rerender({ projectId: 1, files: ['B.java'] });
    expect(names(result.current)).toEqual(['1:B.java']);

    rerender({ projectId: 2, files: ['B.java'] });
    expect(result.current).toEqual([]);
    await waitFor(() => expect(names(result.current)).toEqual(['2:B.java']));
  });
});
