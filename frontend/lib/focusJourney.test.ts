import { describe, expect, it } from 'vitest';
import { journeyUpSteps } from './focusJourney';

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
