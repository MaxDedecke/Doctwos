import { describe, expect, it } from 'vitest';
import { withCompaction, withReasoningChunk } from './chatSteps';

describe('chat steps during streaming', () => {
  it('joins reasoning chunks of one model turn and starts a new step for the next turn', () => {
    let steps = withReasoningChunk([], 0, 'Ich ');
    steps = withReasoningChunk(steps, 0, 'prüfe');
    steps = withReasoningChunk([...steps, { type: 'tool_call', name: 'search', arguments: {} }], 1, 'Weiter');
    expect(steps).toEqual([
      { type: 'reasoning', turn: 0, content: 'Ich prüfe' },
      { type: 'tool_call', name: 'search', arguments: {} },
      { type: 'reasoning', turn: 1, content: 'Weiter' },
    ]);
  });

  it('replaces the running compaction step with its result', () => {
    const running = withCompaction([], { type: 'history_compacted', messages: 8, status: 'running' });
    expect(withCompaction(running, { type: 'history_compacted', messages: 8, status: 'ok' }))
      .toEqual([{ type: 'history_compacted', messages: 8, status: 'ok' }]);
  });
});
