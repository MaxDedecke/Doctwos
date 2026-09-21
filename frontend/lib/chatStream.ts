import type { AgentStep, AgentViewAction, ChatStreamEvent, ChatSource } from '@/types/domain';

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isAgentViewAction(value: unknown): value is AgentViewAction {
  if (!isRecord(value) || !isRecord(value.target)) return false;
  const hasBaseFields = value.type === 'view_action' &&
    typeof value.action_id === 'string' &&
    Number.isSafeInteger(value.session_id) &&
    Number.isSafeInteger(value.turn_id) &&
    (value.project_id === null || Number.isSafeInteger(value.project_id)) &&
    typeof value.tool_call_id === 'string' &&
    ['requested', 'opened', 'updated', 'manual', 'declined', 'no_space', 'rejected', 'stale_context'].includes(String(value.status));
  if (!hasBaseFields) return false;
  if (value.view === 'callgraph') {
    const hasFocus = value.target.focus_entity_id !== undefined;
    const hasEdge = value.target.highlighted_edge_id !== undefined;
    return Number.isSafeInteger(value.target.entity_id) && hasFocus === hasEdge &&
      (!hasFocus || (
        Number.isSafeInteger(value.target.focus_entity_id) && Number(value.target.focus_entity_id) > 0 &&
        Number.isSafeInteger(value.target.highlighted_edge_id) && Number(value.target.highlighted_edge_id) > 0
      ));
  }
  const isDocumentTarget = (target: Record<string, unknown>) =>
    target.kind === 'document' &&
    Number.isSafeInteger(target.chunk_id) && Number(target.chunk_id) > 0 &&
    Number.isSafeInteger(target.source_id) && Number(target.source_id) > 0 &&
    typeof target.file_path === 'string' && target.file_path.length > 0 &&
    typeof target.excerpt === 'string' &&
    typeof target.explanation === 'string' && target.explanation.length > 0;
  const isCallGraphWalkthroughStep = (step: Record<string, unknown>) =>
    step.kind === 'callgraph' &&
    typeof step.trace_tool_call_id === 'string' && step.trace_tool_call_id.length > 0 &&
    Number.isSafeInteger(step.edge_id) && Number(step.edge_id) > 0 &&
    Number.isSafeInteger(step.source_entity_id) && Number(step.source_entity_id) > 0 &&
    Number.isSafeInteger(step.target_entity_id) && Number(step.target_entity_id) > 0 &&
    typeof step.source_name === 'string' && step.source_name.length > 0 &&
    typeof step.target_name === 'string' && step.target_name.length > 0 &&
    typeof step.file_path === 'string' &&
    typeof step.explanation === 'string' && step.explanation.length > 0;
  if (value.view === 'document') return isDocumentTarget(value.target);
  if (value.view === 'walkthrough') {
    return typeof value.target.title === 'string' && value.target.title.length > 0 &&
      Array.isArray(value.target.steps) && value.target.steps.length >= 1 && value.target.steps.length <= 6 &&
      value.target.steps.every(step => isRecord(step) && (
        isDocumentTarget(step) || isCallGraphWalkthroughStep(step) || (
          typeof step.file_path === 'string' && step.file_path.length > 0 &&
          Number.isSafeInteger(step.start_line) && Number(step.start_line) > 0 &&
          Number.isSafeInteger(step.end_line) && Number(step.end_line) >= Number(step.start_line) &&
          typeof step.explanation === 'string' && step.explanation.length > 0
        )
      ));
  }
  const startLine = value.target.start_line;
  const endLine = value.target.end_line;
  return value.view === 'code' &&
    typeof value.target.file_path === 'string' &&
    value.target.file_path.length > 0 &&
    typeof startLine === 'number' && Number.isSafeInteger(startLine) && startLine > 0 &&
    typeof endLine === 'number' && Number.isSafeInteger(endLine) && endLine >= startLine;
}

function isAgentStep(value: unknown): value is AgentStep {
  if (!isRecord(value)) return false;
  if (value.type === 'view_action') return isAgentViewAction(value);
  if (value.type === 'thought') return typeof value.content === 'string';
  if (typeof value.name !== 'string' || (value.id !== undefined && typeof value.id !== 'string')) return false;
  return value.type === 'tool_call' || (value.type === 'tool_result' && typeof value.result === 'string');
}

/** Ignore unknown/malformed events before they can corrupt the transient chat state. */
export function parseChatStreamEvent(json: string): ChatStreamEvent | null {
  const value: unknown = JSON.parse(json);
  if (!isRecord(value)) return null;
  switch (value.type) {
    case 'session':
      return typeof value.session_id === 'number' &&
        (value.session_uuid === undefined || typeof value.session_uuid === 'string') &&
        (value.session_title === undefined || typeof value.session_title === 'string')
        ? { type: 'session', session_id: value.session_id, session_uuid: value.session_uuid, session_title: value.session_title } : null;
    case 'content_chunk':
      return typeof value.content === 'string' ? { type: 'content_chunk', content: value.content } : null;
    case 'tool_call':
      return typeof value.name === 'string' && (value.id === undefined || typeof value.id === 'string')
        ? { type: 'tool_call', name: value.name, arguments: value.arguments, id: value.id } : null;
    case 'tool_result':
      return typeof value.name === 'string' && typeof value.result === 'string' && (value.id === undefined || typeof value.id === 'string')
        ? { type: 'tool_result', name: value.name, result: value.result, id: value.id, truncated: value.truncated === true } : null;
    case 'view_action':
      return isAgentViewAction(value) ? value : null;
    case 'turn_completed':
      return typeof value.has_tool_calls === 'boolean' ? { type: 'turn_completed', has_tool_calls: value.has_tool_calls } : null;
    case 'answer':
      return typeof value.content === 'string' && (value.agent_steps === undefined ||
        (Array.isArray(value.agent_steps) && value.agent_steps.every(isAgentStep)))
        ? { type: 'answer', content: value.content, agent_steps: value.agent_steps } : null;
    case 'message_saved':
      return typeof value.message_id === 'number' ? { type: 'message_saved', message_id: value.message_id } : null;
    case 'error':
      return typeof value.error === 'string' ? { type: 'error', error: value.error } : null;
    case 'sources': {
      if (!Array.isArray(value.sources)) return null;
      const sources: ChatSource[] = [];
      for (const source of value.sources) {
        if (!isRecord(source) || typeof source.file !== 'string' ||
          (source.source_id != null && typeof source.source_id !== 'string' && typeof source.source_id !== 'number') ||
          (source.lines !== undefined && (!Array.isArray(source.lines) || !source.lines.every((line: unknown) => line === null || typeof line === 'number')))) return null;
        const citation: ChatSource = {
          file: source.file,
          source_id: source.source_id,
          lines: source.lines,
        };
        if (isRecord(source.provenance)) citation.provenance = source.provenance;
        sources.push(citation);
      }
      return { type: 'sources', sources };
    }
    default:
      return null;
  }
}
