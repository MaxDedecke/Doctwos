import type { ChatMessage } from '@/types/domain';

export type ChatMode = 'normal' | 'evidence';

/**
 * Der Modus eines Chats wird mit der ersten Nutzernachricht festgelegt und bleibt
 * danach fest. Maßgeblich ist der `chat_mode` dieser ersten Nachricht; ohne Nachricht
 * (oder bei alten Nachrichten ohne Angabe) gibt es keinen festgelegten Modus.
 */
export function lockedChatMode(messages: ReadonlyArray<Pick<ChatMessage, 'role' | 'metadata'>>): ChatMode | null {
  const firstUser = messages.find(message => message.role === 'user');
  if (!firstUser) return null;
  const mode = firstUser.metadata?.chat_mode;
  return mode === 'normal' || mode === 'evidence' ? mode : null;
}
