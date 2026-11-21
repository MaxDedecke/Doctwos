import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { AgentSteps } from './AgentSteps';

vi.mock('@/lib/i18n/LanguageContext', () => ({
  useLanguage: () => ({
    t: (key: string, vars?: Record<string, unknown>) => vars ? `${key}:${JSON.stringify(vars)}` : key,
    language: 'de',
  }),
}));

describe('AgentSteps', () => {
  it('uses the Doctus sans font for a thought instead of the browser serif fallback', () => {
    render(<AgentSteps steps={[{ type: 'thought', content: 'Ich prüfe den Ablauf.' }]} theme="dark" />);

    fireEvent.click(screen.getByRole('button', { name: /agentSteps\.showThoughts/ }));

    expect(screen.getByText('Ich prüfe den Ablauf.').parentElement?.className).toContain('font-sans');
    expect(screen.getByText('Ich prüfe den Ablauf.').parentElement?.className).not.toContain('font-serif');
  });

  it('marks a failed tool, shows its duration and counts it in the header', () => {
    render(<AgentSteps theme="dark" steps={[
      { type: 'tool_call', name: 'search_knowledge', arguments: {}, id: 'c1' },
      { type: 'tool_result', name: 'search_knowledge', result: '{"error":"x"}', id: 'c1', status: 'error', duration_ms: 1530 },
    ]} />);

    expect(screen.getByText('agentSteps.toolsFailed:{"count":1}')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /agentSteps\.showThoughts/ }));
    expect(screen.getByText('agentSteps.toolFailed')).toBeTruthy();
    expect(screen.getByText('1,5 s')).toBeTruthy();
  });

  it('shows a call without result as running while live and as aborted afterwards', () => {
    const steps = [{ type: 'tool_call' as const, name: 'trace_call_flow', arguments: {}, id: 'c1' }];
    const { unmount } = render(<AgentSteps theme="light" steps={steps} isLive />);
    fireEvent.click(screen.getByRole('button', { name: /agentSteps\.showThoughts/ }));
    expect(screen.getByText('agentSteps.toolRunning')).toBeTruthy();
    unmount();

    render(<AgentSteps theme="light" steps={steps} isLive={false} />);
    fireEvent.click(screen.getByRole('button', { name: /agentSteps\.showThoughts/ }));
    expect(screen.getByText('agentSteps.toolAborted')).toBeTruthy();
  });

  it('lists what the server trimmed to fit the context window', () => {
    render(<AgentSteps theme="dark" steps={[{ type: 'context_trimmed', turn: 1, parts: ['history', 'tool_results'] }]} />);

    expect(screen.getByText('agentSteps.contextTrimmed:{"count":1}')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /agentSteps\.showThoughts/ }));
    expect(screen.getByText(/agentSteps\.contextTrimmedStep/).textContent)
      .toContain('agentSteps.trimPart.history, agentSteps.trimPart.tool_results');
  });
});
