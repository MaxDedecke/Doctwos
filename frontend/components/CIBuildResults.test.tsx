import { render, screen } from '@testing-library/react';
import { expect, it } from 'vitest';
import { LanguageProvider } from '@/lib/i18n/LanguageContext';
import { CIBuildResults } from './CIBuildResults';

it('shows commit-bound build and test outcomes separately', () => {
  render(<LanguageProvider><CIBuildResults data={{
    status: 'found', items: [{
      id: 1, provider: 'github', run_id: '12', job_name: 'verify', attempt: 2, variant: 'jdk21',
      commit: 'abc', branch: 'main', status: 'failed', pipeline_url: 'https://example.test/run/12',
      finished_at: '2026-11-07T18:00:00Z',
      summary: { test_status: 'failed', test_results: { tests: 3, failure: 1, error: 0, skipped: 0 },
        active_profiles: ['integration'], modules: [{ path: 'app', maven: { dependencies: [{ groupId: 'demo', artifactId: 'api', version: '2' }] } }] },
    }],
  }} /></LanguageProvider>);
  expect(screen.getByText(/Build fehlgeschlagen/)).toBeTruthy();
  expect(screen.getByText(/3 Tests · 1 fehlgeschlagen/)).toBeTruthy();
  expect(screen.getByText('demo:api:2 ·')).toBeTruthy();
  expect(screen.getByRole('link', { name: 'Pipeline öffnen' }).getAttribute('href')).toBe('https://example.test/run/12');
});

it('keeps missing results visible', () => {
  render(<LanguageProvider><CIBuildResults data={{ status: 'missing', items: [] }} /></LanguageProvider>);
  expect(screen.getByText(/noch keine CI-Ergebnisse/)).toBeTruthy();
});
