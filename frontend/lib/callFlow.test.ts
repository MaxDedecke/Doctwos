import { describe, expect, it } from 'vitest';
import { extractCallFlowData } from './callFlow';
import type { ChatMessage } from '@/types/domain';

describe('extractCallFlowData', () => {
  it('returns null if message has no metadata or agent_steps', () => {
    const msg: ChatMessage = { role: 'assistant', content: 'Hello' };
    expect(extractCallFlowData(msg)).toBeNull();
  });

  it('returns null if agent_steps contains no trace_call_flow result', () => {
    const msg: ChatMessage = {
      role: 'assistant',
      content: 'Hello',
      metadata: {
        agent_steps: [
          { type: 'thought', content: 'Searching...' },
          { type: 'tool_call', name: 'search_repo_code', arguments: {} },
          { type: 'tool_result', name: 'search_repo_code', result: '{"matches":[]}' },
        ],
      },
    };
    expect(extractCallFlowData(msg)).toBeNull();
  });

  it('extracts valid CallFlowData from trace_call_flow step', () => {
    const flowPayload = {
      root: { id: 10, name: 'process_payment', type: 'function', file_path: 'src/pay.py', start_line: 5 },
      hops: 3,
      direction: 'outgoing',
      truncated: false,
      nodes: [
        { id: 10, name: 'process_payment', type: 'function', file_path: 'src/pay.py', start_line: 5 },
        { id: 11, name: 'charge_card', type: 'function', file_path: 'src/stripe.py', start_line: 12 },
      ],
      edges: [
        { id: 100, source: 10, target: 11, target_name: 'charge_card', type: 'CALL', resolution: 'resolved' },
      ],
      mermaid: 'flowchart TD\n  n10 --> n11',
    };

    const msg: ChatMessage = {
      role: 'assistant',
      content: 'Here is the flow',
      metadata: {
        agent_steps: [
          { type: 'tool_call', name: 'trace_call_flow', arguments: { entity_id: 10 } },
          { type: 'tool_result', name: 'trace_call_flow', result: JSON.stringify(flowPayload) },
        ],
      },
    };

    const extracted = extractCallFlowData(msg);
    expect(extracted).not.toBeNull();
    expect(extracted?.root.name).toBe('process_payment');
    expect(extracted?.hops).toBe(3);
    expect(extracted?.direction).toBe('outgoing');
    expect(extracted?.truncated).toBe(false);
    expect(extracted?.nodes).toHaveLength(2);
    expect(extracted?.edges).toHaveLength(1);
    expect(extracted?.mermaid).toBe('flowchart TD\n  n10 --> n11');
  });

  it('ignores trace_call_flow if it returned an error', () => {
    const msg: ChatMessage = {
      role: 'assistant',
      content: 'Error occurred',
      metadata: {
        agent_steps: [
          { type: 'tool_result', name: 'trace_call_flow', result: JSON.stringify({ error: 'Entity was not found' }) },
        ],
      },
    };
    expect(extractCallFlowData(msg)).toBeNull();
  });

  it('picks the most recent trace_call_flow step if multiple exist', () => {
    const flow1 = {
      root: { id: 1, name: 'first_root' },
      hops: 1,
      direction: 'outgoing',
      nodes: [{ id: 1, name: 'first_root' }],
      edges: [],
    };
    const flow2 = {
      root: { id: 2, name: 'second_root' },
      hops: 2,
      direction: 'incoming',
      nodes: [{ id: 2, name: 'second_root' }],
      edges: [],
    };

    const msg: ChatMessage = {
      role: 'assistant',
      content: 'Latest flow',
      metadata: {
        agent_steps: [
          { type: 'tool_result', name: 'trace_call_flow', result: JSON.stringify(flow1) },
          { type: 'tool_result', name: 'trace_call_flow', result: JSON.stringify(flow2) },
        ],
      },
    };

    const extracted = extractCallFlowData(msg);
    expect(extracted?.root.name).toBe('second_root');
    expect(extracted?.direction).toBe('incoming');
  });
});
