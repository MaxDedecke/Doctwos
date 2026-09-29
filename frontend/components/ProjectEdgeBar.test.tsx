import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ProjectEdgeBar } from './ProjectEdgeBar';

describe('ProjectEdgeBar', () => {
  it('uses the brand gradient without a project color', () => {
    render(<ProjectEdgeBar />);
    const bar = screen.getByTestId('project-edge-bar');
    expect(bar.className).toContain('doctus-brand-gradient');
    expect(bar.getAttribute('style') ?? '').not.toContain('background-color');
  });

  it('treats an empty color like no color', () => {
    render(<ProjectEdgeBar color="" />);
    expect(screen.getByTestId('project-edge-bar').className).toContain('doctus-brand-gradient');
  });

  it('is filled with the project color instead of the gradient when a color is set', () => {
    render(<ProjectEdgeBar color="#2f9e6b" />);
    const bar = screen.getByTestId('project-edge-bar');
    expect(bar.className).not.toContain('doctus-brand-gradient');
    expect(bar.style.backgroundColor).toBe('rgb(47, 158, 107)');
  });

  it('stays a decorative, non-interactive vertical edge on the far left', () => {
    render(<ProjectEdgeBar color="#2f9e6b" />);
    const bar = screen.getByTestId('project-edge-bar');
    expect(bar.getAttribute('aria-hidden')).toBe('true');
    expect(bar.className).toContain('pointer-events-none');
    expect(bar.className).toContain('left-0');
    expect(bar.className).toContain('w-1');
  });
});
