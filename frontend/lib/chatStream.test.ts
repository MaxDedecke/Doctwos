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

  it('keeps tool arguments as structured data without treating them as trusted fields', () => {
    const event = { type: 'tool_call', name: 'search', arguments: { query: 'CALL', filters: ['code'] }, id: 'call-1' };
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

  it.each([
    null,
    { type: 'future_event', content: 'ignored' },
    { type: 'content_chunk', content: { unexpected: true } },
    { type: 'sources', sources: [{ file: 7 }] },
    { type: 'sources', sources: [{ file: 'main.cbl', lines: ['wrong'] }] },
    { type: 'message_saved', message_id: '7' },
    { type: 'answer', content: 'ok', agent_steps: [{ type: 'tool_result', name: 'search', result: {} }] },
  ])('ignores an unsupported or malformed event: %j', event => {
    expect(parseChatStreamEvent(JSON.stringify(event))).toBeNull();
  });

  it('rejects broken JSON so the caller can report and skip that frame', () => {
    expect(() => parseChatStreamEvent('{')).toThrow(SyntaxError);
  });
});
