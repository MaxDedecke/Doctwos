import type { AnalysisStatus } from '@/lib/analysisStatus';
import type { ChatMessage } from '@/types/domain';

export interface CallFlowNode {
  id: number;
  name: string;
  qualified_name?: string | null;
  type?: string | null;
  file_path?: string | null;
  start_line?: number | null;
  end_line?: number | null;
  source_id?: number | string | null;
  analysis_status?: AnalysisStatus;
  analysis_reasons?: string[];
}

export interface CallFlowEdge {
  id: number;
  source: number;
  target: number | null;
  target_name: string;
  type: string;
  resolution: string;
  meta?: { resolution_reason?: string; source_file_path?: string };
  start_line?: number | null;
  end_line?: number | null;
}

export interface CallFlowData {
  root: CallFlowNode;
  hops: number;
  direction: 'outgoing' | 'incoming' | 'both';
  truncated: boolean;
  nodes: CallFlowNode[];
  edges: CallFlowEdge[];
  mermaid?: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/**
 * Extracts and validates the most recent successful trace_call_flow result
 * from an assistant message's agent_steps.
 */
export function extractCallFlowData(message: ChatMessage): CallFlowData | null {
  const steps = message.metadata?.agent_steps;
  if (!Array.isArray(steps) || steps.length === 0) return null;

  for (let i = steps.length - 1; i >= 0; i--) {
    const step = steps[i];
    if (step.type === 'tool_result' && step.name === 'trace_call_flow' && step.result) {
      try {
        const parsed: unknown = typeof step.result === 'string' ? JSON.parse(step.result) : step.result;
        if (!isRecord(parsed) || parsed.error) continue;

        if (
          isRecord(parsed.root) &&
          typeof parsed.root.id === 'number' &&
          typeof parsed.root.name === 'string' &&
          Array.isArray(parsed.nodes) &&
          Array.isArray(parsed.edges)
        ) {
          return {
            root: parsed.root as unknown as CallFlowNode,
            hops: typeof parsed.hops === 'number' ? parsed.hops : 1,
            direction: (parsed.direction === 'incoming' || parsed.direction === 'both') ? parsed.direction : 'outgoing',
            truncated: Boolean(parsed.truncated),
            nodes: parsed.nodes as unknown as CallFlowNode[],
            edges: parsed.edges as unknown as CallFlowEdge[],
            mermaid: typeof parsed.mermaid === 'string' ? parsed.mermaid : undefined,
          };
        }
      } catch {
        // Continue searching if this particular step had malformed JSON
      }
    }
  }

  return null;
}
