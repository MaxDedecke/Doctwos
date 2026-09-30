import { describe, expect, it } from 'vitest';
import { lockedChatMode } from './chatMode';

describe('lockedChatMode', () => {
  it('hat ohne Nachricht keinen festgelegten Modus', () => {
    expect(lockedChatMode([])).toBeNull();
    expect(lockedChatMode([{ role: 'assistant', metadata: { chat_mode: 'evidence' } }])).toBeNull();
  });

  it('nimmt den Modus der ersten Nutzernachricht', () => {
    expect(lockedChatMode([
      { role: 'user', metadata: { chat_mode: 'normal' } },
      { role: 'assistant', metadata: { chat_mode: 'normal' } },
      { role: 'user', metadata: { chat_mode: 'evidence' } },
    ])).toBe('normal');
  });

  it('ignoriert alte Nachrichten ohne oder mit unbekanntem Modus', () => {
    expect(lockedChatMode([{ role: 'user' }])).toBeNull();
    expect(lockedChatMode([{ role: 'user', metadata: { chat_mode: 'foo' as never } }])).toBeNull();
  });
});
