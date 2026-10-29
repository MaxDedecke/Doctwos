import { describe, expect, it } from 'vitest';
import { createRequestGate } from './requestGate';

describe('createRequestGate', () => {
  it('lets only the newest request apply and invalidates on demand', () => {
    const gate = createRequestGate();
    const first = gate.begin();
    const second = gate.begin();
    expect(first()).toBe(false);
    expect(second()).toBe(true);
    gate.invalidate();
    expect(second()).toBe(false);
  });
});
