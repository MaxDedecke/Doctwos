import { api, API_URL } from '@/app/services/api';

interface EntityEstimate {
  entities_to_scan: number;
  estimated_llm_reviews_max: number;
  estimated_embedding_calls_max: number;
  is_targeted?: boolean;
  chunk_count?: number;
}

interface Request {
  projectId: number;
  /** Quellen des Cross-Source-Laufs (Dokument ↔ Dokument); leer, wenn er nicht mitläuft. */
  knowledgeSourceIds: number[];
  /** Einschränkung des Entity-Laufs (`entity_types`/`doc_source_ids`), leer = keine. */
  runScopeQuery: string;
  limit: number;
  t: (key: string, values?: Record<string, string | number>) => string;
  isActive: () => boolean;
}

/** Aufwand schätzen und bestätigen lassen, bevor ein Link-Lauf startet. */
export async function confirmLinkRun({ projectId, knowledgeSourceIds, runScopeQuery, limit, t, isActive }: Request): Promise<'confirmed' | 'declined' | 'failed'> {
  let entityEstimate: EntityEstimate;
  let knowledgeEstimate: { chunk_count: number } | null = null;
  try {
    const entityResponse = await api.fetch(`${API_URL}/projects/${projectId}/link-recommendations/estimate${runScopeQuery ? `?${runScopeQuery}` : ''}`);
    if (!entityResponse.ok) throw new Error(`HTTP ${entityResponse.status}`);
    entityEstimate = await entityResponse.json();
    if (knowledgeSourceIds.length) {
      const scope = new URLSearchParams({ project_id: String(projectId) });
      knowledgeSourceIds.forEach(id => scope.append('source_ids', String(id)));
      const response = await api.fetch(`${API_URL}/knowledge-links/estimate?${scope}`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      knowledgeEstimate = await response.json();
    }
  } catch {
    return 'failed';
  }
  const knowledgeCount = knowledgeEstimate ? Math.min(limit, knowledgeEstimate.chunk_count) : 0;
  const message = t('linkManagerView.budget.confirm', {
    entityCount: Math.min(limit, entityEstimate.entities_to_scan),
    entityTotal: entityEstimate.entities_to_scan,
    embeddingCalls: Math.min(limit, entityEstimate.estimated_embedding_calls_max),
    llmCalls: Math.min(limit, entityEstimate.estimated_llm_reviews_max) + knowledgeCount * 5,
    knowledgeCount,
    limit,
  });
  const targeted = entityEstimate.is_targeted
    ? `${t('linkManagerView.runScope.confirm', { entities: entityEstimate.entities_to_scan, chunks: entityEstimate.chunk_count ?? 0 })}\n\n`
    : '';
  if (!isActive()) return 'declined';
  return window.confirm(targeted + message) ? 'confirmed' : 'declined';
}
