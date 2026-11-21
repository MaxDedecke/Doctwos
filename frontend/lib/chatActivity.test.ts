import { describe, expect, it } from 'vitest';
import { currentActivity, toolLabel } from './chatActivity';

const labels: Record<string, string> = { 'agentSteps.toolLabels.view_repo_file': 'Datei lesen' };
const t = (key: string, vars?: Record<string, string | number>) => labels[key] ?? (vars ? `${key}:${JSON.stringify(vars)}` : key);

describe('current agent activity', () => {
  it('names the running tool with its target', () => {
    expect(currentActivity([{ type: 'tool_call', name: 'view_repo_file', arguments: { file_path: 'app/cbl/COSGN00C.cbl' }, id: 'c1' }], t))
      .toBe('agentSteps.live.toolWithHint:{"tool":"Datei lesen","hint":"app/cbl/COSGN00C.cbl"}');
  });

  it('prefers a running compaction and otherwise follows the last step', () => {
    expect(currentActivity([{ type: 'history_compacted', messages: 4, status: 'running' }], t)).toBe('agentSteps.live.compacting');
    expect(currentActivity([{ type: 'reasoning', turn: 0, content: 'x' }], t)).toBe('agentSteps.live.thinking');
    expect(currentActivity([
      { type: 'tool_call', name: 'x', arguments: {}, id: 'c1' },
      { type: 'tool_result', name: 'x', result: '{}', id: 'c1' },
    ], t)).toBe('agentSteps.live.evaluating');
  });

  it('keeps unknown tool names', () => {
    expect(toolLabel('jira_get_issue', t)).toBe('jira_get_issue');
  });
});
