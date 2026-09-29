import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { LanguageProvider } from '@/lib/i18n/LanguageContext';
import { InsightDraftAction } from './InsightDraftAction';

vi.mock('@/app/services/api', () => ({ api: { createInsight: vi.fn() } }));

const renderAction = (props: Partial<React.ComponentProps<typeof InsightDraftAction>> = {}) =>
  render(
    <LanguageProvider>
      <InsightDraftAction projectId={1} origin="code" evidence={[{ file: 'A.cbl' }]} defaultTitle="A.cbl" theme="dark" {...props} />
    </LanguageProvider>
  );

describe('InsightDraftAction', () => {
  it('shows a compact hover-expanding button and opens the draft dialog on click', () => {
    renderAction();
    const button = screen.getByRole('button', { name: 'Erkenntnis sichern' });

    expect(button.className).toContain('w-7');
    expect(button.className).toContain('hover:w-[var(--expand-w)]');
    fireEvent.click(button);

    expect(screen.getByRole('dialog')).toBeTruthy();
  });

  it('is disabled without a project or evidence', () => {
    renderAction({ evidence: [] });
    expect((screen.getByRole('button', { name: 'Erkenntnis sichern' }) as HTMLButtonElement).disabled).toBe(true);
  });
});
