import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { LanguageProvider, useLanguage } from './LanguageContext';

function TestConsumer({ i18nKey, vars }: { i18nKey: string; vars?: Record<string, string | number> }) {
  const { t } = useLanguage();
  return <div data-testid="translated">{t(i18nKey, vars)}</div>;
}

describe('LanguageContext interpolation and translation', () => {
  it('interpolates double brace variables {{var}}', () => {
    render(
      <LanguageProvider>
        <TestConsumer i18nKey="chatView.walkthroughStep" vars={{ current: 1, count: 5 }} />
      </LanguageProvider>
    );
    expect(screen.getByTestId('translated').textContent).toBe('Schritt 1 von 5');
  });

  it('interpolates single brace variables {var} as a fallback', () => {
    render(
      <LanguageProvider>
        <TestConsumer i18nKey="chatView.walkthroughSummary" vars={{ count: 4 }} />
      </LanguageProvider>
    );
    expect(screen.getByTestId('translated').textContent).toBe('Soll ich dir das in 4 geführten Schritten zeigen?');
  });

  it('interpolates page variable properly', () => {
    render(
      <LanguageProvider>
        <TestConsumer i18nKey="chatView.walkthroughPage" vars={{ page: 42 }} />
      </LanguageProvider>
    );
    expect(screen.getByTestId('translated').textContent).toBe('Seite 42');
  });

  it('handles multiple occurrences of the same variable without leaving unreplaced placeholders', () => {
    render(
      <LanguageProvider>
        <TestConsumer i18nKey="chatView.walkthroughStep" vars={{ current: 3, count: 3 }} />
      </LanguageProvider>
    );
    expect(screen.getByTestId('translated').textContent).toBe('Schritt 3 von 3');
  });
});
