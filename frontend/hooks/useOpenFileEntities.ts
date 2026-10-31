import { useEffect, useMemo, useState } from 'react';
import { api } from '@/app/services/api';
import type { CodeEntity } from '@/types/domain';

interface LoadedFiles {
  projectId: number | null;
  byFile: Record<string, CodeEntity[]>;
}

const EMPTY_ENTITIES: CodeEntity[] = [];

/**
 * Code-Elemente der geöffneten Dateien, für Projekte, deren vollständige Liste der Server ablehnt.
 * Bei `enabled = false` bleibt der Hook untätig; dann gilt die vollständige Liste aus `useProjects`.
 */
export function useOpenFileEntities(projectId: number | null, enabled: boolean, openFiles: string[]): CodeEntity[] {
  const [loaded, setLoaded] = useState<LoadedFiles>({ projectId, byFile: {} });
  const filesKey = enabled ? [...new Set(openFiles)].sort().join('\0') : '';
  const byFile = loaded.projectId === projectId ? loaded.byFile : null;

  useEffect(() => {
    if (!filesKey || projectId == null) return;
    let cancelled = false;
    for (const file of filesKey.split('\0')) {
      if (byFile?.[file]) continue;
      api.getProjectEntities(projectId, file)
        .then((res) => {
          if (cancelled) return;
          setLoaded((previous) => ({
            projectId,
            byFile: { ...(previous.projectId === projectId ? previous.byFile : {}), [file]: res.data },
          }));
        })
        .catch((error) => console.error('Failed to load file entities:', error));
    }
    return () => { cancelled = true; };
  // `byFile` nicht in den Abhängigkeiten: Jede Antwort würde sonst die offenen Anfragen verwerfen.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filesKey, projectId]);

  return useMemo(() => {
    if (!filesKey || !byFile) return EMPTY_ENTITIES;
    return filesKey.split('\0').flatMap((file) => byFile[file] ?? []);
  }, [filesKey, byFile]);
}
