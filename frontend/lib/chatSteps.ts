import type { AgentStep } from '@/types/domain';

/** Hängt ein live gestreamtes Stück Denken an den Denkschritt desselben Modellzugs an. */
export function withReasoningChunk(steps: AgentStep[], turn: number, content: string): AgentStep[] {
  const last = steps[steps.length - 1];
  if (last?.type === 'reasoning' && (last.turn ?? 0) === turn) {
    return [...steps.slice(0, -1), { ...last, content: last.content + content }];
  }
  return [...steps, { type: 'reasoning', turn, content }];
}

/** Ersetzt den laufenden Compacting-Schritt durch sein Ergebnis, statt einen zweiten anzuhängen. */
export function withCompaction(steps: AgentStep[], step: Extract<AgentStep, { type: 'history_compacted' }>): AgentStep[] {
  const index = steps.findIndex(candidate => candidate.type === 'history_compacted');
  if (index === -1) return [...steps, step];
  return steps.map((candidate, position) => (position === index ? step : candidate));
}
