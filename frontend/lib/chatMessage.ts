/**
 * Removes the accidental numeric prefix that was shown on the first
 * "Wer bist du ?" message in a new chat. Keep this deliberately narrow so
 * that a user can still send messages that intentionally begin with a number.
 */
export function normalizeInitialUserMessage(content: string, isFirstUserMessage: boolean): string {
  if (!isFirstUserMessage) return content;

  return content.replace(/^0\s+(?=Wer bist du\s*\?$)/iu, "");
}
