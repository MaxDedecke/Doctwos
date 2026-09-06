import type { AgentStep, ChatStreamEvent, ChatSource } from '@/types/domain';

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isAgentStep(value: unknown): value is AgentStep {
  if (!isRecord(value)) return false;
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
        ? { type: 'tool_result', name: value.name, result: value.result, id: value.id } : null;
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
        sources.push({ file: source.file, source_id: source.source_id, lines: source.lines });
      }
      return { type: 'sources', sources };
    }
    default:
      return null;
  }
}
