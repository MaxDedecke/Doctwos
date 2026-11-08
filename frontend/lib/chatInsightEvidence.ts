import type { ChatSource } from '@/types/domain';

export function chatInsightEvidence(sources: ChatSource[], messageId?: number) {
  return sources.map(source => {
    const origin = { chat_message_id: messageId };
    if (source.kind === 'insight') return { ...origin, insight_id: source.insight_id };
    if (source.kind === 'ci_build') return { ...origin, source_id: source.source_id, ci_build_id: source.ci_build_id, source_commit: source.build?.commit };
    return { ...origin, source_id: source.source_id, file: source.file, lines: source.lines };
  });
}
