import { describe, expect, it } from 'vitest';
import { buildEvidenceQuestions, buildNormalQuestions, hasPulseContent, shuffle, type ProjectPulse } from './chatStarters';

const t = (key: string, vars?: Record<string, string | number>) =>
  vars ? `${key}|${Object.values(vars).join(',')}` : key;

const pulse = (overrides: Partial<ProjectPulse> = {}): ProjectPulse => ({
  counts: { program: 2, copybook: 1, sql_table: 0, jcl_job: 0 },
  samples: { program: ['PAYROLL', 'LEDGER'], copybook: ['ACCTREC'], sql_table: [], jcl_job: [] },
  ...overrides,
});

describe('chatStarters', () => {
  it('erkennt ein leeres Projekt daran, dass kein Typ Treffer hat', () => {
    expect(hasPulseContent(null)).toBe(false);
    expect(hasPulseContent(pulse({ counts: { program: 0, copybook: 0, sql_table: 0, jcl_job: 0 } }))).toBe(false);
    expect(hasPulseContent(pulse())).toBe(true);
  });

  it('bildet Evidenz-Fragen ausschließlich aus echten Objektnamen des Projekts', () => {
    const questions = buildEvidenceQuestions(pulse(), t);
    expect(questions).toHaveLength(2 * 3 + 1);
    expect(questions).toContain('chatView.empty.questions.evidence.callers|PAYROLL');
    expect(questions).toContain('chatView.empty.questions.evidence.copybook|ACCTREC');
    expect(questions.some(q => q.includes('.table|'))).toBe(false);
  });

  it('hält Normal-Fragen namenlos und lässt nicht vorhandene Themen weg', () => {
    const questions = buildNormalQuestions(pulse(), t);
    expect(questions).toContain('chatView.empty.questions.normal.copybook');
    expect(questions).not.toContain('chatView.empty.questions.normal.sql');
    expect(questions).not.toContain('chatView.empty.questions.normal.jcl');
    expect(questions.every(q => !q.includes('|'))).toBe(true);
  });

  it('bietet ohne Projekt alle allgemeinen Normal-Fragen an', () => {
    expect(buildNormalQuestions(null, t)).toHaveLength(5);
  });

  it('mischt, ohne Elemente zu verlieren oder die Eingabe zu verändern', () => {
    const input = [1, 2, 3, 4, 5];
    const shuffled = shuffle(input, () => 0.3);
    expect([...shuffled].sort()).toEqual(input);
    expect(input).toEqual([1, 2, 3, 4, 5]);
  });
});
