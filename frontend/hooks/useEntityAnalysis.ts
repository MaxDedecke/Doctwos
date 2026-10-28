import { useEffect, useState } from 'react';
import { api } from '@/app/services/api';
import type { CodeEntity, EntityNeighbor } from '@/types/domain';

interface Analysis {
  key: string;
  entity: CodeEntity | null;
  file: CodeEntity | null;
  neighbors: EntityNeighbor[];
  linksTruncated: boolean;
  failed: boolean;
}

/** Fetch full metadata only for an expanded inspector; discard obsolete replies. */
export function useEntityAnalysis(open: boolean, entityId: number | undefined, fileId: number | undefined, projectId: number | null | undefined) {
  const key = `${projectId}:${entityId}:${fileId}`;
  const [result, setResult] = useState<Analysis | null>(null);
  useEffect(() => {
    if (!open || entityId == null) return;
    let cancelled = false;
    const load = async () => {
      const ids = [...new Set([entityId, fileId].filter((id): id is number => id != null))];
      const [replies, links] = await Promise.all([
        Promise.allSettled(ids.map(id => api.getEntity(id, projectId))),
        Promise.allSettled([api.getEntityNeighbors(entityId, { projectId, types: ['INJECTS', 'DISPATCHES_TO', 'EXPOSES'], direction: 'both', limit: 15 })]),
      ]);
      if (cancelled) return;
      const entities = replies.flatMap(reply => reply.status === 'fulfilled' ? [reply.value.data] : []);
      const linkReply = links[0];
      setResult({ key, entity: entities.find(entity => entity.id === entityId) || null,
        file: entities.find(entity => entity.id === fileId) || null,
        neighbors: linkReply.status === 'fulfilled' ? Object.values(linkReply.value.data.groups).flat() : [],
        linksTruncated: linkReply.status === 'fulfilled' && Object.values(linkReply.value.data.page || {}).some(page => page.has_more),
        failed: replies.some(reply => reply.status === 'rejected') || linkReply.status === 'rejected' });
    };
    void load();
    return () => { cancelled = true; };
  }, [open, entityId, fileId, projectId, key]);
  return { analysis: result?.key === key ? result : null, loading: open && entityId != null && result?.key !== key };
}
