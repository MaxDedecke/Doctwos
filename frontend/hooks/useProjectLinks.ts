import { useCallback, useEffect, useRef, useState } from 'react';
import { api, API_URL } from '@/app/services/api';
import type { EntityDocLink, KnowledgeLink, LinkCounts } from '@/lib/linkManagerTypes';

const emptyCounts = (): LinkCounts => ({ pending: 0, approved: 0, rejected: 0 });

export function useProjectLinks(projectId: number | undefined, tab: string, minScore: number, enabled: boolean) {
  const [entityLinks, setEntityLinks] = useState<EntityDocLink[]>([]);
  const [entityCounts, setEntityCounts] = useState<LinkCounts>(emptyCounts);
  const [knowledgeLinks, setKnowledgeLinks] = useState<KnowledgeLink[]>([]);
  const [knowledgeCounts, setKnowledgeCounts] = useState<LinkCounts>(emptyCounts);
  const [isLoading, setIsLoading] = useState(false);
  const alive = useRef(true);
  const sequences = useRef({ entity: 0, knowledge: 0 });
  const isActive = useCallback(() => alive.current, []);

  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; };
  }, []);

  const fetchEntityLinks = useCallback(async (silent = false) => {
    if (!projectId || !alive.current) return null;
    const sequence = ++sequences.current.entity;
    if (!silent) setIsLoading(true);
    try {
      const params = new URLSearchParams({ status: tab });
      if (minScore > 0) params.set('min_score', String(minScore / 100));
      const response = await api.fetch(`${API_URL}/projects/${projectId}/link-recommendations?${params}`);
      if (!response.ok) return null;
      const data = await response.json();
      if (!alive.current || sequence !== sequences.current.entity) return null;
      setEntityLinks(data.links || []);
      setEntityCounts(data.counts || emptyCounts());
      return data;
    } catch { return null; }
    finally { if (!silent && alive.current && sequence === sequences.current.entity) setIsLoading(false); }
  }, [projectId, tab, minScore]);

  const fetchKnowledgeLinks = useCallback(async (silent = false) => {
    if (!projectId || !alive.current) return null;
    const sequence = ++sequences.current.knowledge;
    if (!silent) setIsLoading(true);
    try {
      const filters = new URLSearchParams({ project_id: String(projectId) });
      if (minScore > 0) filters.set('min_score', String(minScore / 100));
      const [listRes, countsRes] = await Promise.all([
        api.fetch(`${API_URL}/knowledge-links?status=${tab}&${filters}`),
        api.fetch(`${API_URL}/knowledge-links/counts?${filters}`),
      ]);
      if (!listRes.ok || !countsRes.ok) return null;
      const [links, counts] = await Promise.all([listRes.json(), countsRes.json()]);
      if (!alive.current || sequence !== sequences.current.knowledge) return null;
      const safeCounts: LinkCounts = {
        pending: counts?.pending ?? 0, approved: counts?.approved ?? 0, rejected: counts?.rejected ?? 0,
      };
      setKnowledgeLinks(Array.isArray(links) ? links : []);
      setKnowledgeCounts(safeCounts);
      return { links, counts: safeCounts };
    } catch { return null; }
    finally { if (!silent && alive.current && sequence === sequences.current.knowledge) setIsLoading(false); }
  }, [projectId, tab, minScore]);

  useEffect(() => {
    const requests = sequences.current;
    (async () => {
      if (enabled) await Promise.all([fetchEntityLinks(), fetchKnowledgeLinks()]);
    })();
    return () => { requests.entity++; requests.knowledge++; };
  }, [enabled, fetchEntityLinks, fetchKnowledgeLinks]);

  return {
    entityLinks, entityCounts, setEntityLinks, setEntityCounts,
    knowledgeLinks, knowledgeCounts, setKnowledgeLinks, setKnowledgeCounts,
    isLoading, fetchEntityLinks, fetchKnowledgeLinks, isActive,
  };
}
