import { extractCallFlowData } from '@/lib/callFlow';
import type { AgentStep, AgentViewAction } from '@/types/domain';

/**
 * Passt eine vom Agenten angebotene Ansicht zu dem Werkzeugergebnis, auf das sie sich beruft? Nur dann darf die
 * Oberfläche sie anbieten; sonst gilt sie als abgelehnt (der Server prüft dasselbe, das hier ist die zweite Schicht).
 */
export function viewActionMatchesResult(data: AgentViewAction, accumulatedSteps: AgentStep[]): boolean {
  const matchingResult = [...accumulatedSteps].reverse().find(step =>
    step.type === 'tool_result' && step.id === data.tool_call_id && (
      (data.view === 'callgraph' && (step.name === 'trace_call_flow' || step.name === 'inspect_change_impact')) ||
      (data.view === 'graph' && step.name === 'show_graph_neighborhood') ||
      (data.view === 'code' && step.name === 'view_repo_file') ||
      (data.view === 'walkthrough' &&
        (step.name === 'offer_code_walkthrough' || step.name === 'offer_source_walkthrough'))
    )
  );
  const flow = data.view === 'callgraph' && matchingResult
    ? extractCallFlowData({ role: 'assistant', content: '', metadata: { agent_steps: [matchingResult] } })
    : null;
  let hasMatchingCodeLocation = false;
  let hasMatchingWalkthrough = false;
  let hasMatchingGraphNeighborhood = false;
  if (data.view === 'code' && matchingResult?.type === 'tool_result') {
    try {
      const result = JSON.parse(matchingResult.result) as Record<string, unknown>;
      hasMatchingCodeLocation = result.file_path === data.target.file_path &&
        result.start_line === data.target.start_line &&
        result.end_line === data.target.end_line;
    } catch {
      hasMatchingCodeLocation = false;
    }
  }
  if (data.view === 'walkthrough' && matchingResult?.type === 'tool_result') {
    try {
      const result = JSON.parse(matchingResult.result) as Record<string, unknown>;
      const canonicalize = (value: unknown) => JSON.stringify(
        value && typeof value === 'object' && !Array.isArray(value)
          ? Object.fromEntries(Object.entries(value as Record<string, unknown>).sort(([left], [right]) => left.localeCompare(right)))
          : value,
      );
      hasMatchingWalkthrough = result.status === 'ok' &&
        result.title === data.target.title &&
        Array.isArray(result.steps) && result.steps.length === data.target.steps.length &&
        result.steps.every((step, index) => canonicalize(step) === canonicalize(data.target.steps[index])) &&
        data.target.steps.every(step => {
          if (step.kind !== 'callgraph') return true;
          const traceResult = accumulatedSteps.find(candidate =>
            candidate.type === 'tool_result' && candidate.name === 'trace_call_flow' &&
            candidate.id === step.trace_tool_call_id,
          );
          if (traceResult?.type !== 'tool_result') return false;
          const flow = extractCallFlowData({ role: 'assistant', content: '', metadata: { agent_steps: [traceResult] } });
          if (!flow) return false;
          const edge = flow.edges.find(candidate => candidate.id === step.edge_id);
          const source = flow.nodes.find(candidate => candidate.id === step.source_entity_id);
          const target = flow.nodes.find(candidate => candidate.id === step.target_entity_id);
          return edge?.resolution === 'resolved' &&
            edge.source === step.source_entity_id && edge.target === step.target_entity_id &&
            source?.name === step.source_name && target?.name === step.target_name &&
            source?.file_path === (step.file_path || undefined) &&
            edge.start_line === step.start_line && edge.end_line === step.end_line;
        });
    } catch {
      hasMatchingWalkthrough = false;
    }
  }
  if (data.view === 'graph' && matchingResult?.type === 'tool_result') {
    try {
      const result = JSON.parse(matchingResult.result) as Record<string, unknown>;
      const nodes = Array.isArray(result.nodes) ? result.nodes : [];
      const edges = Array.isArray(result.edges) ? result.edges : [];
      hasMatchingGraphNeighborhood = result.status === 'ok' &&
        result.focus_id === data.target.focus_id &&
        result.focus_label === data.target.focus_label &&
        result.direction === data.target.direction &&
        result.hops === data.target.hops &&
        result.limit === data.target.limit &&
        JSON.stringify(result.relationships) === JSON.stringify(data.target.relationships) &&
        edges.length > 0 && edges.length <= data.target.limit &&
        nodes.some(node => node && typeof node === 'object' &&
          (node as Record<string, unknown>).id === data.target.focus_id);
    } catch {
      hasMatchingGraphNeighborhood = false;
    }
  }
  return !(
    (data.view === 'callgraph' && (!flow || flow.root.id !== data.target.entity_id)) ||
    (data.view === 'graph' && !hasMatchingGraphNeighborhood) ||
    (data.view === 'code' && !hasMatchingCodeLocation) ||
    (data.view === 'walkthrough' && !hasMatchingWalkthrough)
  );
}
