import type { AgentStep } from '@/types/domain';

type Translate = (key: string, vars?: Record<string, string | number>) => string;

/** Lesbarer Name eines Werkzeugs; unbekannte (z. B. MCP-Werkzeuge) behalten ihren Namen. */
export function toolLabel(name: string, t: Translate): string {
  const key = `agentSteps.toolLabels.${name}`;
  const label = t(key);
  return label === key ? name : label;
}

function argumentHint(args: unknown): string | null {
  if (!args || typeof args !== 'object') return null;
  const record = args as Record<string, unknown>;
  const value = record.file_path ?? record.path ?? record.query ?? record.topic
    ?? (Array.isArray(record.symbols) ? record.symbols.join(', ') : null)
    ?? (Array.isArray(record.entity_names) ? record.entity_names.join(', ') : null);
  return typeof value === 'string' && value.trim() ? value.trim().slice(0, 60) : null;
}

/** Was der Agent gerade tut, als eine Zeile für die Live-Anzeige („Liest COSGN00C.cbl …“). */
export function currentActivity(steps: AgentStep[], t: Translate): string {
  if (steps.some(step => step.type === 'history_compacted' && step.status === 'running')) {
    return t('agentSteps.live.compacting');
  }
  const answered = new Set(steps.flatMap(step => (step.type === 'tool_result' && step.id ? [step.id] : [])));
  const last = steps[steps.length - 1];
  const pending = [...steps].reverse().find(step => step.type === 'tool_call' && (!step.id || !answered.has(step.id)));
  if (pending?.type === 'tool_call' && last?.type !== 'tool_result') {
    const hint = argumentHint(pending.arguments);
    const tool = toolLabel(pending.name, t);
    return hint ? t('agentSteps.live.toolWithHint', { tool, hint }) : t('agentSteps.live.tool', { tool });
  }
  if (last?.type === 'reasoning') return t('agentSteps.live.thinking');
  if (last?.type === 'tool_result') return t('agentSteps.live.evaluating');
  return t('agentSteps.live.working');
}
