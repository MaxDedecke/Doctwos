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

  it('accepts a final answer with thought, call and result steps', () => {
    const event = { type: 'answer', content: 'Result', agent_steps: [
      { type: 'thought', content: 'Look up the caller' },
      { type: 'tool_call', name: 'search', arguments: '{}' },
      { type: 'tool_result', name: 'search', result: 'Found MAIN' },
    ] };
    expect(parseChatStreamEvent(JSON.stringify(event))).toEqual(event);
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
