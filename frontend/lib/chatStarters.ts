/**
 * Beispielfragen für den leeren Chat. Im Evidenz-Modus stammen die Namen aus
 * dem gewählten Projekt (`/chat/project-pulse`), im Normal-Modus bleiben die
 * Fragen allgemein — dort wird nicht im Projekt recherchiert, echte Objektnamen
 * würden also eine Belegbarkeit suggerieren, die dieser Modus nicht liefert.
 */

export const PULSE_ENTITY_TYPES = ['program', 'copybook', 'sql_table', 'jcl_job'] as const;
export type PulseEntityType = (typeof PULSE_ENTITY_TYPES)[number];

export interface ProjectPulse {
  counts: Record<PulseEntityType, number>;
  samples: Record<PulseEntityType, string[]>;
}

type Translate = (key: string, vars?: Record<string, string | number>) => string;

export function shuffle<T>(items: readonly T[], random: () => number = Math.random): T[] {
  const result = [...items];
  for (let i = result.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1));
    [result[i], result[j]] = [result[j], result[i]];
  }
  return result;
}

export function hasPulseContent(pulse: ProjectPulse | null): pulse is ProjectPulse {
  return !!pulse && PULSE_ENTITY_TYPES.some(type => pulse.counts[type] > 0);
}

export function buildEvidenceQuestions(pulse: ProjectPulse, t: Translate): string[] {
  const key = (name: string) => `chatView.empty.questions.evidence.${name}`;
  const questions: string[] = [];
  for (const name of pulse.samples.program) {
    questions.push(t(key('explainProgram'), { name }), t(key('callees'), { name }), t(key('callers'), { name }));
  }
  for (const name of pulse.samples.copybook) questions.push(t(key('copybook'), { name }));
  for (const name of pulse.samples.sql_table) questions.push(t(key('table'), { name }));
  for (const name of pulse.samples.jcl_job) questions.push(t(key('job'), { name }));
  return questions;
}

export function buildNormalQuestions(pulse: ProjectPulse | null, t: Translate): string[] {
  const key = (name: string) => `chatView.empty.questions.normal.${name}`;
  const has = (type: PulseEntityType) => !pulse || !hasPulseContent(pulse) || pulse.counts[type] > 0;
  const questions = [t(key('call')), t(key('paragraph'))];
  if (has('copybook')) questions.push(t(key('copybook')));
  if (has('sql_table')) questions.push(t(key('sql')));
  if (has('jcl_job')) questions.push(t(key('jcl')));
  return questions;
}
