import { describe, expect, it } from 'vitest';
import { buildEvidenceQuestions, buildNormalQuestions, detectStacks, hasPulseContent, pulseTypesToShow, shuffle, type ProjectPulse } from './chatStarters';

const t = (key: string, vars?: Record<string, string | number>) =>
  vars ? `${key}|${Object.values(vars).join(',')}` : key;

const ZERO = { program: 0, copybook: 0, sql_table: 0, jcl_job: 0, class: 0, interface: 0, method: 0, maven_module: 0 };
const NONE = { program: [], copybook: [], sql_table: [], jcl_job: [], class: [], interface: [], method: [], maven_module: [] };

const javaPulse = (): ProjectPulse => ({
  counts: { ...ZERO, class: 40, interface: 5, method: 300 },
  samples: { ...NONE, class: ['UserLogic'], interface: ['UserService'] },
});

const pulse = (overrides: Partial<ProjectPulse> = {}): ProjectPulse => ({
  counts: { ...ZERO, program: 2, copybook: 1 },
  samples: { ...NONE, program: ['PAYROLL', 'LEDGER'], copybook: ['ACCTREC'] },
  ...overrides,
});

describe('chatStarters', () => {
  it('erkennt ein leeres Projekt daran, dass kein Typ Treffer hat', () => {
    expect(hasPulseContent(null)).toBe(false);
    expect(hasPulseContent(pulse({ counts: ZERO }))).toBe(false);
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

  it('erkennt Java-Projekte und ordnet den stärksten Stack zuerst ein', () => {
    expect(detectStacks(null)).toEqual(['cobol']);
    expect(detectStacks(pulse())).toEqual(['cobol']);
    expect(detectStacks(javaPulse())).toEqual(['java']);
    expect(detectStacks({ ...javaPulse(), counts: { ...javaPulse().counts, program: 500 } })[0]).toBe('cobol');
  });

  it('zeigt bei Java-Projekten Java-Zähler und stellt Java-Fragen', () => {
    expect(pulseTypesToShow(javaPulse())).toEqual(['class', 'interface', 'method']);
    const evidence = buildEvidenceQuestions(javaPulse(), t);
    expect(evidence).toContain('chatView.empty.questions.evidence.classExplain|UserLogic');
    expect(evidence).toContain('chatView.empty.questions.evidence.interfaceImpls|UserService');
    const normal = buildNormalQuestions(javaPulse(), t);
    expect(normal).toContain('chatView.empty.questions.normal.javaDi');
    expect(normal).not.toContain('chatView.empty.questions.normal.call');
  });

  it('mischt, ohne Elemente zu verlieren oder die Eingabe zu verändern', () => {
    const input = [1, 2, 3, 4, 5];
    const shuffled = shuffle(input, () => 0.3);
    expect([...shuffled].sort()).toEqual(input);
    expect(input).toEqual([1, 2, 3, 4, 5]);
  });
});
