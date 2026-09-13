import type { KnowledgeSource } from '@/types/domain';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import React from 'react';

vi.mock('@/lib/i18n/LanguageContext', () => ({
  useLanguage: () => ({
    t: (key: string, values?: Record<string, string | number>) =>
      values?.count !== undefined ? `${key}:${values.count}` : key,
  }),
}));

import { SourceNetworkGraph } from './SourceNetworkGraph';

const source = (overrides: Partial<KnowledgeSource>): KnowledgeSource => ({
  id: 1,
  name: 'Quelle',
  type: 'git',
  ...overrides,
});

describe('SourceNetworkGraph', () => {
  it('shows the empty state when there are no sources', () => {
    render(<SourceNetworkGraph sources={[]} theme="dark" scopeLabel="Allgemein" />);
    expect(screen.getByText('sourceNetworkGraph.empty')).toBeTruthy();
  });

  it('renders one node per source, titled by name', () => {
    const sources = [
      source({ id: 1, name: 'Repo A' }),
      source({ id: 2, name: 'Repo B' }),
    ];
    render(<SourceNetworkGraph sources={sources} theme="dark" scopeLabel="Allgemein" />);
    expect(screen.getByTitle('Repo A')).toBeTruthy();
    expect(screen.getByTitle('Repo B')).toBeTruthy();
  });

  it('collapses sources beyond the visible limit into a single overflow node', () => {
    // MAX_VISIBLE_NODES ist 6 — der siebte Knoten muss zum "+1 weitere"-Knoten zusammenfallen.
    const sources = Array.from({ length: 7 }, (_, i) => source({ id: i + 1, name: `Quelle ${i + 1}` }));
    render(<SourceNetworkGraph sources={sources} theme="dark" scopeLabel="Allgemein" />);
    for (let i = 1; i <= 6; i++) {
      expect(screen.getByTitle(`Quelle ${i}`)).toBeTruthy();
    }
    expect(screen.queryByTitle('Quelle 7')).toBeNull();
    expect(screen.getByText('sourceNetworkGraph.overflowLabel:1')).toBeTruthy();
  });

  it('shows the scope label as given', () => {
    render(<SourceNetworkGraph sources={[]} theme="dark" scopeLabel="Projekt X" />);
    expect(screen.getByText('Projekt X')).toBeTruthy();
  });
});
