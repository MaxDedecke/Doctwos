import { describe, expect, it } from 'vitest';
import { applyMention, mentionAt } from './useEntityMentions';

describe('@ mentions', () => {
  it('finds the mention right before the caret only', () => {
    expect(mentionAt('Wer ruft @COSGN', 15)).toEqual({ query: 'COSGN', start: 9 });
    expect(mentionAt('mail@host', 9)).toBeNull();
    expect(mentionAt('@C', 2)).toBeNull();
  });

  it('replaces the mention with the backticked name and moves the caret behind it', () => {
    expect(applyMention('Wer ruft @COSG auf?', 14, 'COSGN00C')).toEqual({ text: 'Wer ruft `COSGN00C`  auf?', caret: 20 });
  });
});
