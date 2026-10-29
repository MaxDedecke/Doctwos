import { describe, expect, it } from 'vitest';
import { contentFitZoom, JOURNEY_CONTENT_SPACING, journeyUpSteps } from './focusJourney';

describe('journeyUpSteps', () => {
  it('closes the deepest level first, one level per step, until nothing is expanded', () => {
    expect(journeyUpSteps(['c1', 'c1.2', 'c1.2.0', 't4', 'c3'])).toEqual([
      ['c1', 'c1.2', 't4', 'c3'],
      ['c1', 't4', 'c3'],
      [],
    ]);
    expect(journeyUpSteps([])).toEqual([]);
  });
});

describe('contentFitZoom', () => {
  it('stays far enough out that the expected contents fit into the view', () => {
    const k = contentFitZoom(133, 600);
    expect(2 * JOURNEY_CONTENT_SPACING * Math.sqrt(133) * k).toBeLessThanOrEqual(600);
    expect(contentFitZoom(400, 600)).toBeLessThan(k);
    expect(contentFitZoom(0, 600)).toBe(contentFitZoom(1, 600));
  });
});

