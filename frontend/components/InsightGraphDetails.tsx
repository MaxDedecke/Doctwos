import { InsightEvidence } from './InsightEvidence';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import type { GraphNode } from '@/lib/knowledgeGraphTypes';

export function InsightGraphDetails({ node }: { node: GraphNode }) {
  const { t } = useLanguage();
  if (node.type !== 'insight') return null;
  return <div className="text-xs"><p>{t(`insightReview.status.${node.status}`)}</p><p className="mt-2 whitespace-pre-wrap">{node.content}</p><InsightEvidence evidence={node.evidence || []} /></div>;
}
