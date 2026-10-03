/** O-380: Quellenansicht zeigt Anzahl und Ursachen nicht strukturierter Dateien. */
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { LanguageProvider } from '@/lib/i18n/LanguageContext';
import { SourceScanSummary, type SourceScanSummaryData } from './SourceScanSummary';

function renderSummary(summary?: SourceScanSummaryData) {
  return render(
    <LanguageProvider>
      <SourceScanSummary summary={summary} theme="dark" />
    </LanguageProvider>
  );
}

describe('SourceScanSummary', () => {
  it('renders nothing without affected files or open edges', () => {
    const { container } = renderSummary({ total_files: 10, by_status: { complete: 10 }, by_reason: {} });
    expect(container.innerHTML).toBe('');
  });

  it('lists reasons sorted by size and the open edge count', () => {
    renderSummary({
      total_files: 100,
      by_status: {},
      by_reason: {
        parser_error: { total_files: 2, by_language: { java: 2 } },
        no_structure_parser: { total_files: 30, by_language: { properties: 30 } },
      },
      edges: { unresolved_external: 0, unresolved_open: 7 },
    });
    const root = screen.getByTestId('source-scan-summary');
    expect(root.textContent).toContain('32');
    expect(root.textContent).toContain('100');
    const items = Array.from(root.querySelectorAll('li')).map((li) => li.textContent ?? '');
    expect(items[0]).toContain('30');
    expect(items[1]).toContain('2');
    expect(items[2]).toContain('7');
  });
});
