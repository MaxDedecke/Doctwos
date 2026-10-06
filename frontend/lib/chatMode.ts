import type { ChatMessage } from '@/types/domain';

export type ChatMode = 'normal' | 'evidence';

/**
 * Der Modus eines Chats wird mit der ersten Nutzernachricht festgelegt und bleibt
 * danach fest. Maßgeblich ist der `chat_mode` dieser ersten Nachricht; ohne Nachricht
 * Fehlt sie (ältere Chats), gilt der Modus der ersten Antwort; ohne beides gibt es keinen
 * festgelegten Modus.
 */
export function lockedChatMode(messages: ReadonlyArray<Pick<ChatMessage, 'role' | 'metadata'>>): ChatMode | null {
  const firstUser = messages.find(message => message.role === 'user');
  if (!firstUser) return null;
  const isMode = (mode: unknown): mode is ChatMode => mode === 'normal' || mode === 'evidence';
  if (isMode(firstUser.metadata?.chat_mode)) return firstUser.metadata.chat_mode;
  const firstAssistant = messages.find(message => message.role === 'assistant' && isMode(message.metadata?.chat_mode));
  return isMode(firstAssistant?.metadata?.chat_mode) ? firstAssistant.metadata.chat_mode : null;
}
