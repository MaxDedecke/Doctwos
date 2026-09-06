import type { ShowToast } from '@/components/Toast';
import { api } from '@/app/services/api';
import type { FileReference, KnowledgeSource, Project } from '@/types/domain';
import { useCallback, useEffect, useState } from 'react';

type Translate = (key: string, values?: Record<string, string | number>) => string;
type Toast = ShowToast;

interface UseKnowledgeSourcesOptions {
  isLoggedIn: boolean;
  selectedProject: Project | null;
  t: Translate;
  showToast: Toast;
}

/**
 * Owns source selection, source filters, source references, and the persisted
 * source-pin preference. File navigation consumes this hook through the
 * `loadFileReferences` command without needing to know how source state loads.
 */
export function useKnowledgeSources({
  isLoggedIn,
  selectedProject,
  t,
  showToast,
}: UseKnowledgeSourcesOptions) {
  const [selectedSource, setSelectedSource] = useState<KnowledgeSource | null>(null);
  const [selectedSourceRepoId, setSelectedSourceRepoId] = useState('all');
  const [fileReferences, setFileReferences] = useState<FileReference[]>([]);
  const [isLoadingReferences, setIsLoadingReferences] = useState(false);
  const [isReferencesDropdownOpen, setIsReferencesDropdownOpen] = useState(false);
  const [referencesTab, setReferencesTab] = useState<'code' | 'docs'>('code');
  const [activeSourceType, setActiveSourceType] = useState<string | null>(null);
  const [connectedSources, setConnectedSources] = useState<KnowledgeSource[]>([
    { id: 'conf-init', type: 'Confluence', name: t('page.demoSourceName'), repoId: 'all', spaces: ['ENG', 'PROD'] },
  ]);
  const [pinnedSourceIds, setPinnedSourceIds] = useState<number[]>(() => {
    if (typeof window === 'undefined') return [];
    const saved = localStorage.getItem('pinnedSourceIds');
    if (!saved) return [];
    try {
      return JSON.parse(saved);
    } catch (error) {
      console.error('Failed to restore pinned sources:', error);
      return [];
    }
  });

  useEffect(() => {
    if (!isLoggedIn) return;

    api.getKnowledgeSources()
      .then((res) => {
        setConnectedSources(res.data);
        // A source may have been deleted or the database may have been
        // reseeded since the preference was written. Remove stale pins so the
        // four-source limit reflects actual sources.
        setPinnedSourceIds((previous) => {
          const valid = previous.filter((id) => res.data.some((source: KnowledgeSource) => source.id === id));
          if (valid.length !== previous.length) {
            localStorage.setItem('pinnedSourceIds', JSON.stringify(valid));
          }
          return valid;
        });
      })
      .catch((error) => console.error('Failed to load knowledge sources:', error));
  }, [isLoggedIn]);

  const togglePinSource = useCallback((sourceId: number) => {
    setPinnedSourceIds((previous) => {
      if (previous.includes(sourceId)) {
        const next = previous.filter((id) => id !== sourceId);
        localStorage.setItem('pinnedSourceIds', JSON.stringify(next));
        return next;
      }
      if (previous.length >= 4) {
        showToast(t('settings.sourcesTab.maxPinsReached'), 'error');
        return previous;
      }
      const next = [...previous, sourceId];
      localStorage.setItem('pinnedSourceIds', JSON.stringify(next));
      return next;
    });
  }, [showToast, t]);

  const loadFileReferences = useCallback(async (filePath: string, entityName: string | null = null, projectOverride: Project | null = null) => {
    const project = projectOverride || selectedProject;
    if (!project) return;
    setIsLoadingReferences(true);
    try {
      const res = await api.getProjectReferences(project.id, filePath, entityName || undefined);
      setFileReferences(res.data);
    } catch (error) {
      console.error('Failed to load file references:', error);
      setFileReferences([]);
    } finally {
      setIsLoadingReferences(false);
    }
  }, [selectedProject]);

  return {
    selectedSource,
    setSelectedSource,
    selectedSourceRepoId,
    setSelectedSourceRepoId,
    fileReferences,
    setFileReferences,
    isLoadingReferences,
    isReferencesDropdownOpen,
    setIsReferencesDropdownOpen,
    referencesTab,
    setReferencesTab,
    activeSourceType,
    setActiveSourceType,
    connectedSources,
    setConnectedSources,
    pinnedSourceIds,
    setPinnedSourceIds,
    togglePinSource,
    loadFileReferences,
  };
}
