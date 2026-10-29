import { describe, expect, it } from 'vitest';
import { chatScrollTarget, nextRevealLength, REVEAL_MAX_SECONDS } from './chatReveal';

describe('nextRevealLength', () => {
  it('reveals up to the end of a word, never mid-word', () => {
    const text = 'Das Programm ruft COBSWAIT auf.';
    const next = nextRevealLength(0, text, 10);
    expect(next).toBeGreaterThan(0);
    expect(next === text.length || /\s/.test(text[next])).toBe(true);
  });

  it('catches up with a long answer within the maximum time', () => {
    const text = 'wort '.repeat(4000);
    let shown = 0;
    let elapsed = 0;
    while (shown < text.length && elapsed < 10_000) {
      shown = nextRevealLength(shown, text, 16);
      elapsed += 16;
    }
    expect(shown).toBe(text.length);
    expect(elapsed).toBeLessThanOrEqual(REVEAL_MAX_SECONDS * 1000 + 100);
  });

  it('shows everything when nothing is outstanding', () => {
    expect(nextRevealLength(12, 'kurzer Text', 16)).toBe(11);
  });
});

describe('chatScrollTarget', () => {
  const view = { scrollTop: 0, scrollHeight: 3000, clientHeight: 600 };

  it('follows to the bottom but stops once the answer start reaches the top', () => {
    expect(chatScrollTarget({ ...view, anchorTop: 2000, following: true })).toBe(1988);
    expect(chatScrollTarget({ ...view, anchorTop: 200, following: true })).toBe(188);
    expect(chatScrollTarget({ ...view, scrollTop: 188, anchorTop: 200, following: true })).toBeNull();
  });

  it('stays put when the reader scrolled away or the target lies above', () => {
    expect(chatScrollTarget({ ...view, anchorTop: 2000, following: false })).toBeNull();
    expect(chatScrollTarget({ ...view, scrollTop: 2400, anchorTop: 2000, following: true })).toBeNull();
  });

  it('goes to the bottom without an anchor', () => {
    expect(chatScrollTarget({ ...view, anchorTop: null, following: true })).toBe(2400);
  });
});
