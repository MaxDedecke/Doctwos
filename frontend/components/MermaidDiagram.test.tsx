import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { getMermaidRenderConfig, MermaidDiagram } from './MermaidDiagram';

vi.mock('mermaid', () => ({
  default: {
    initialize: vi.fn(),
    render: vi.fn().mockResolvedValue({ svg: '<svg viewBox="0 0 100 50"><foreignObject><div xmlns="http://www.w3.org/1999/xhtml">Flow</div></foreignObject></svg>' }),
  },
}));

describe('MermaidDiagram', () => {
  afterEach(() => vi.clearAllMocks());

  it('opens the compact chat diagram in an almost full-window dialog and closes it with Escape', () => {
    render(<MermaidDiagram code="flowchart TD\nA --> B" theme="dark" />);

    fireEvent.click(screen.getByRole('button', { name: 'Diagramm maximieren' }));

    const dialog = screen.getByRole('dialog', { name: 'Ablaufdiagramm in Großansicht' });
    expect(dialog).toBeTruthy();
    expect(dialog.parentElement).toBe(document.body);
    expect(dialog.className).toContain('z-[3000]');
    expect(screen.getByText('Ablaufdiagramm')).toBeTruthy();

    fireEvent.keyDown(window, { key: 'Escape' });

    expect(screen.queryByRole('dialog', { name: 'Ablaufdiagramm in Großansicht' })).toBeNull();
  });

  it('disables Mermaid HTML labels globally so flowchart labels use native SVG text', () => {
    expect(getMermaidRenderConfig('dark')).toMatchObject({
      theme: 'dark',
      securityLevel: 'strict',
      htmlLabels: false,
    });
  });
});
