import { render, screen } from '@testing-library/react';
import { expect, it } from 'vitest';
import { LanguageProvider } from '@/lib/i18n/LanguageContext';
import { ChatReviewedSource } from './ChatReviewedSource';
import { chatInsightEvidence } from '@/lib/chatInsightEvidence';
import type { ChatSource } from '@/types/domain';

it('renders the cited CI snapshot with the shared build and test view', () => {
  const source: ChatSource = { kind: 'ci_build', file: 'ci-build:7', ci_build_id: 7, source_id: 8, build: {
    id: 7, provider: 'gitlab', job_name: 'verify', variant: 'jdk21', run_id: '12', attempt: 2,
    commit: 'abc', branch: 'main', status: 'failed', pipeline_url: 'https://ci.example/run/12',
    summary: { test_status: 'failed', test_results: { tests: 3, failure: 1 }, active_profiles: ['integration'], modules: [] },
  }};
  render(<LanguageProvider><ChatReviewedSource source={source} onOpenFile={() => {}} /></LanguageProvider>);
  expect(screen.getByText(/Build fehlgeschlagen/)).toBeTruthy();
  expect(screen.getByText(/3 Tests · 1 fehlgeschlagen/)).toBeTruthy();
  expect(screen.getByText(/main · abc/)).toBeTruthy();
  expect(screen.getByText(/gespeicherten Stand/)).toBeTruthy();
  expect(screen.getByRole('link', { name: 'Pipeline öffnen' }).getAttribute('href')).toBe('https://ci.example/run/12');
  expect(chatInsightEvidence([source], 3)).toEqual([{ chat_message_id: 3, source_id: 8, ci_build_id: 7, source_commit: 'abc' }]);
});

it('retains insight references when synthesizing another finding', () => {
  const source: ChatSource = { kind: 'insight', file: 'insight:4', insight_id: 4, title: 'Reviewed claim', content: 'A claim', evidence: [] };
  render(<LanguageProvider><ChatReviewedSource source={source} onOpenFile={() => {}} /></LanguageProvider>);
  expect(screen.getByText('A claim')).toBeTruthy();
  expect(chatInsightEvidence([source], 2)).toEqual([{ chat_message_id: 2, insight_id: 4 }]);
});
