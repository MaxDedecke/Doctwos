/**
 * Beispielfragen für den leeren Chat. Im Evidenz-Modus stammen die Namen aus
 * dem gewählten Projekt (`/chat/project-pulse`), im Normal-Modus bleiben die
 * Fragen allgemein — dort wird nicht im Projekt recherchiert, echte Objektnamen
 * würden also eine Belegbarkeit suggerieren, die dieser Modus nicht liefert.
 */

export const PULSE_ENTITY_TYPES = [
  'program', 'copybook', 'sql_table', 'jcl_job',
  'class', 'interface', 'method', 'maven_module',
] as const;
export type PulseEntityType = (typeof PULSE_ENTITY_TYPES)[number];

/** Technologie-Stack, auf den die Startansicht Karten und Fragen zuschneidet. */
export type Stack = 'cobol' | 'java';
const STACK_TYPES: Record<Stack, readonly PulseEntityType[]> = {
  cobol: ['program', 'copybook', 'sql_table', 'jcl_job'],
  java: ['class', 'interface', 'method', 'maven_module'],
};

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
  return !!pulse && PULSE_ENTITY_TYPES.some(type => (pulse.counts[type] ?? 0) > 0);
}

/** Im Projekt vorhandene Stacks, der stärkste zuerst. Ohne Pulse: COBOL (Produktstandard). */
export function detectStacks(pulse: ProjectPulse | null): Stack[] {
  if (!hasPulseContent(pulse)) return ['cobol'];
  const weight = (stack: Stack) => STACK_TYPES[stack].reduce((sum, type) => sum + (pulse.counts[type] ?? 0), 0);
  return (Object.keys(STACK_TYPES) as Stack[])
    .filter(stack => weight(stack) > 0)
    .sort((a, b) => weight(b) - weight(a));
}

/** Nur Typen der vorhandenen Stacks gehören in die Zählerzeile. */
export function pulseTypesToShow(pulse: ProjectPulse): PulseEntityType[] {
  const stacks = detectStacks(pulse);
  return PULSE_ENTITY_TYPES.filter(type => pulse.counts[type] > 0 && stacks.some(stack => STACK_TYPES[stack].includes(type)));
}

export function buildEvidenceQuestions(pulse: ProjectPulse, t: Translate): string[] {
  const key = (name: string) => `chatView.empty.questions.evidence.${name}`;
  const questions: string[] = [];
  const sample = (type: PulseEntityType) => pulse.samples[type] ?? [];
  for (const name of sample('program')) {
    questions.push(t(key('explainProgram'), { name }), t(key('callees'), { name }), t(key('callers'), { name }));
  }
  for (const name of sample('copybook')) questions.push(t(key('copybook'), { name }));
  for (const name of sample('sql_table')) questions.push(t(key('table'), { name }));
  for (const name of sample('jcl_job')) questions.push(t(key('job'), { name }));
  for (const name of sample('class')) questions.push(t(key('classExplain'), { name }), t(key('classUsers'), { name }));
  for (const name of sample('interface')) questions.push(t(key('interfaceImpls'), { name }));
  return questions;
}

export function buildNormalQuestions(pulse: ProjectPulse | null, t: Translate): string[] {
  const key = (name: string) => `chatView.empty.questions.normal.${name}`;
  const stacks = detectStacks(pulse);
  const known = hasPulseContent(pulse);
  const has = (type: PulseEntityType) => !known || pulse.counts[type] > 0;
  const questions: string[] = [];
  if (stacks.includes('cobol')) {
    questions.push(t(key('call')), t(key('paragraph')));
    if (has('copybook')) questions.push(t(key('copybook')));
    if (has('sql_table')) questions.push(t(key('sql')));
    if (has('jcl_job')) questions.push(t(key('jcl')));
  }
  if (stacks.includes('java')) {
    questions.push(t(key('javaInterface')), t(key('javaDi')));
    if (has('maven_module')) questions.push(t(key('javaMaven')));
  }
  return questions;
}
