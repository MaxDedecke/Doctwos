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
  /** Guided walkthrough focus; omitted for a normal call-flow result. */
  focus_entity_id?: number;
  highlighted_edge_id?: number;
}

export interface ChangeImpactSummary {
  statically_resolved_edges: number;
  heuristic_links: number;
  unknown_dynamic_edges: number;
  truncated: boolean;
  limitations: string[];
}

export interface ChangeImpactData {
  toolCallId: string;
  targetLabel: string;
  flow: CallFlowData;
  summary: ChangeImpactSummary;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/**
 * Extracts the most recent successful trace_call_flow or inspect_change_impact
 * graph from an assistant message's agent_steps.
 */
export function extractCallFlowData(message: ChatMessage): CallFlowData | null {
  const steps = message.metadata?.agent_steps;
  if (!Array.isArray(steps) || steps.length === 0) return null;

  for (let i = steps.length - 1; i >= 0; i--) {
    const step = steps[i];
    if (step.type === 'tool_result' && (step.name === 'trace_call_flow' || step.name === 'inspect_change_impact') && step.result) {
      try {
        const parsed: unknown = typeof step.result === 'string' ? JSON.parse(step.result) : step.result;
        if (!isRecord(parsed) || parsed.error || (step.name === 'inspect_change_impact' && parsed.status !== 'ok')) continue;

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

/** Extracts the compact summary used by the impact-graph action card. */
export function extractChangeImpactData(message: ChatMessage): ChangeImpactData | null {
  const steps = message.metadata?.agent_steps;
  if (!Array.isArray(steps)) return null;
  for (let i = steps.length - 1; i >= 0; i--) {
    const step = steps[i];
    if (step.type !== 'tool_result' || step.name !== 'inspect_change_impact' || !step.result || !step.id) continue;
    try {
      const parsed: unknown = typeof step.result === 'string' ? JSON.parse(step.result) : step.result;
      if (!isRecord(parsed) || parsed.status !== 'ok' || !isRecord(parsed.impact_summary)) continue;
      const summary = parsed.impact_summary;
      const counts = [summary.statically_resolved_edges, summary.heuristic_links, summary.unknown_dynamic_edges];
      if (!counts.every(value => typeof value === 'number' && Number.isSafeInteger(value) && value >= 0)) continue;
      const flow = extractCallFlowData({ role: 'assistant', content: '', metadata: { agent_steps: [step] } });
      if (!flow) continue;
      const targetLabel = isRecord(parsed.target) && typeof parsed.target.file_path === 'string' && parsed.target.file_path
        ? parsed.target.file_path
        : flow.root.name;
      return {
        toolCallId: step.id,
        targetLabel,
        flow,
        summary: {
          statically_resolved_edges: summary.statically_resolved_edges as number,
          heuristic_links: summary.heuristic_links as number,
          unknown_dynamic_edges: summary.unknown_dynamic_edges as number,
          truncated: Boolean(summary.truncated),
          limitations: Array.isArray(summary.limitations)
            ? summary.limitations.filter((item): item is string => typeof item === 'string').slice(0, 4)
            : [],
        },
      };
    } catch {
      // Ignore malformed impact results and continue to older tool results.
    }
  }
  return null;
}
