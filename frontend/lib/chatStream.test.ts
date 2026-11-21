import { describe, expect, it } from 'vitest';
import { parseChatStreamEvent } from './chatStream';

describe('chat stream boundary', () => {
  it('keeps numeric source IDs and nullable document lines from the backend', () => {
    const event = { type: 'sources', sources: [
      { file: 'main.cbl', source_id: 7, lines: [1, 12] },
      { file: 'manual.pdf', source_id: '8', lines: [null, null] },
    ] };
    expect(parseChatStreamEvent(JSON.stringify(event))).toEqual(event);
  });

  it('preserves source provenance on streamed citations', () => {
    const event = { type: 'sources', sources: [
      { file: 'src/main.cbl', source_id: 7, lines: [12, 16], provenance: {
        kind: 'code_fact', verification_status: 'indexed_unreviewed', source_revision: 'rev-123',
      } },
    ] };
    expect(parseChatStreamEvent(JSON.stringify(event))).toEqual(event);
  });

  it('keeps tool arguments as structured data without treating them as trusted fields', () => {
    const event = { type: 'tool_call', name: 'search', arguments: { query: 'CALL', filters: ['code'] }, id: 'call-1' };
    expect(parseChatStreamEvent(JSON.stringify(event))).toEqual(event);
  });

  it('carries the O-168 truncation flag on a tool_result event', () => {
    const event = { type: 'tool_result', name: 'jira_get_issue', result: 'Found MAIN', id: 'call-1', truncated: true };
    expect(parseChatStreamEvent(JSON.stringify(event))).toEqual(event);
  });

  it('defaults a tool_result without a truncated field to false', () => {
    const event = { type: 'tool_result', name: 'search', result: 'Found MAIN' };
    expect(parseChatStreamEvent(JSON.stringify(event))).toEqual({
      type: 'tool_result', name: 'search', result: 'Found MAIN', truncated: false,
    });
  });

  it('carries tool status and duration, and drops malformed ones', () => {
    const event = { type: 'tool_result', name: 'search', result: '{"error":"x"}', id: 'call-1', truncated: false, status: 'error', duration_ms: 812 };
    expect(parseChatStreamEvent(JSON.stringify(event))).toEqual(event);
    expect(parseChatStreamEvent(JSON.stringify({ ...event, status: 'kaputt', duration_ms: -3 }))).toEqual({
      type: 'tool_result', name: 'search', result: '{"error":"x"}', id: 'call-1', truncated: false,
    });
  });

  it('parses the live-text reset and context trims, keeping only known trimmed parts', () => {
    expect(parseChatStreamEvent(JSON.stringify({ type: 'content_reset' }))).toEqual({ type: 'content_reset' });
    expect(parseChatStreamEvent(JSON.stringify({ type: 'context_trimmed', turn: 2, parts: ['history', 'unbekannt'] })))
      .toEqual({ type: 'context_trimmed', turn: 2, parts: ['history'] });
  });

  it('parses live reasoning and compaction progress', () => {
    expect(parseChatStreamEvent(JSON.stringify({ type: 'reasoning_chunk', turn: 1, content: 'denke' })))
      .toEqual({ type: 'reasoning_chunk', turn: 1, content: 'denke' });
    expect(parseChatStreamEvent(JSON.stringify({ type: 'history_compacted', messages: 6, status: 'running' })))
      .toEqual({ type: 'history_compacted', messages: 6, status: 'running' });
    expect(parseChatStreamEvent(JSON.stringify({ type: 'history_compacted', messages: 6, status: 'kaputt' }))).toBeNull();
  });

  it('keeps the answer when its steps carry reasoning and a compaction', () => {
    const event = { type: 'answer', content: 'Result', agent_steps: [
      { type: 'history_compacted', messages: 6, status: 'ok' },
      { type: 'reasoning', turn: 0, content: 'Ich prüfe' },
    ] };
    expect(parseChatStreamEvent(JSON.stringify(event))).toEqual(event);
  });

  it('keeps the answer when its steps include a context trim', () => {
    const event = { type: 'answer', content: 'Result', agent_steps: [
      { type: 'context_trimmed', turn: 0, parts: ['history'] },
      { type: 'tool_result', name: 'search', result: 'Found MAIN', status: 'ok', duration_ms: 5 },
    ] };
    expect(parseChatStreamEvent(JSON.stringify(event))).toEqual(event);
  });

  it('accepts a final answer with thought, call and result steps', () => {
    const event = { type: 'answer', content: 'Result', agent_steps: [
      { type: 'thought', content: 'Look up the caller' },
      { type: 'tool_call', name: 'search', arguments: '{}' },
      { type: 'tool_result', name: 'search', result: 'Found MAIN' },
    ] };
    expect(parseChatStreamEvent(JSON.stringify(event))).toEqual(event);
  });

  it('keeps the answer when agent_steps carry the server-side mcp_preflight step', () => {
    const preflight = { type: 'mcp_preflight', status: 'not_configured', servers: [], tool_count: 0 };
    const toolCall = { type: 'tool_call', name: 'search', arguments: '{}' };
    const event = { type: 'answer', content: 'Result', agent_steps: [preflight, toolCall] };
    expect(parseChatStreamEvent(JSON.stringify(event))).toEqual({
      type: 'answer', content: 'Result', agent_steps: [toolCall],
    });
  });

  it('accepts monotonic milestones and the final O-323 eval metrics', () => {
    const milestone = { type: 'telemetry', event: 'first_token', monotonic_ms: 42 } as const;
    const completed = {
      type: 'telemetry', event: 'completed', metrics: {
        response_time_ms: 93,
        first_token_ms: 42,
        tool_count: 2,
        retrieval_wait_ms: 17,
        first_tool_call_ms: 31,
        model_end_ms: 78,
      },
    } as const;
    expect(parseChatStreamEvent(JSON.stringify(milestone))).toEqual(milestone);
    expect(parseChatStreamEvent(JSON.stringify(completed))).toEqual(completed);
  });

  it.each([
    null,
    { type: 'future_event', content: 'ignored' },
    { type: 'content_chunk', content: { unexpected: true } },
    { type: 'sources', sources: [{ file: 7 }] },
    { type: 'sources', sources: [{ file: 'main.cbl', lines: ['wrong'] }] },
    { type: 'message_saved', message_id: '7' },
    { type: 'telemetry', event: 'completed', metrics: { tool_count: -1 } },
    { type: 'answer', content: 'ok', agent_steps: [{ type: 'tool_result', name: 'search', result: {} }] },
  ])('ignores an unsupported or malformed event: %j', event => {
    expect(parseChatStreamEvent(JSON.stringify(event))).toBeNull();
  });

  it('rejects broken JSON so the caller can report and skip that frame', () => {
    expect(() => parseChatStreamEvent('{')).toThrow(SyntaxError);
  });
});
