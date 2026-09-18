import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { MermaidDiagram } from './MermaidDiagram';

vi.mock('mermaid', () => ({
  default: {
    initialize: vi.fn(),
    render: vi.fn().mockResolvedValue({ svg: '<svg viewBox="0 0 100 50"><text>Flow</text></svg>' }),
  },
}));

describe('MermaidDiagram', () => {
  afterEach(() => vi.clearAllMocks());

  it('opens the compact chat diagram in an almost full-window dialog and closes it with Escape', () => {
    render(<MermaidDiagram code="flowchart TD\nA --> B" theme="dark" />);

    fireEvent.click(screen.getByRole('button', { name: 'Diagramm maximieren' }));

    expect(screen.getByRole('dialog', { name: 'Ablaufdiagramm in Großansicht' })).toBeTruthy();
    expect(screen.getByText('Ablaufdiagramm')).toBeTruthy();

    fireEvent.keyDown(window, { key: 'Escape' });

    expect(screen.queryByRole('dialog', { name: 'Ablaufdiagramm in Großansicht' })).toBeNull();
  });
});
