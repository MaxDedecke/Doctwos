import type { ChatMessage, StoredChatMessage } from '@/types/domain';

/**
 * Removes the accidental numeric prefix that was shown on the first
 * "Wer bist du ?" message in a new chat. Keep this deliberately narrow so
 * that a user can still send messages that intentionally begin with a number.
 */
export function normalizeInitialUserMessage(content: string, isFirstUserMessage: boolean): string {
  if (!isFirstUserMessage) return content;

  return content.replace(/^0\s+(?=Wer bist du\s*\?$)/iu, "");
}

/** Gespeicherte Nachrichten in die Chat-Darstellung; nur eine Seite ab Gesprächsbeginn normalisiert die erste Frage. */
export function fromStoredMessages(messages: StoredChatMessage[], startsAtBeginning: boolean): ChatMessage[] {
  let firstUserSeen = !startsAtBeginning;
  return messages.map((message) => {
    const isFirstUserMessage = message.role === 'user' && !firstUserSeen;
    if (message.role === 'user') firstUserSeen = true;
    return {
      id: message.id,
      role: message.role,
      content: normalizeInitialUserMessage(message.content, isFirstUserMessage),
      sources: message.sources_json || undefined,
      metadata: message.metadata_json || undefined,
      feedback: message.feedback || undefined,
    };
  });
}
