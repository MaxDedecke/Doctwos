import type { ChatAttachment } from '@/types/domain';

/** Grenzen wie im Backend (services/chat_attachments.py). */
export const MAX_ATTACHMENTS = 5;
export const MAX_ATTACHMENT_CHARS = 200_000;
export const ATTACHMENT_ACCEPT = [
  '.cbl', '.cob', '.cpy', '.jcl', '.proc', '.bms', '.java', '.xml', '.xsl', '.sql', '.txt', '.log', '.md', '.json',
  '.yaml', '.yml', '.csv', '.properties', '.sh', '.py', '.ts', '.js', 'text/*',
].join(',');

/** Liest Textdateien als Anhänge; Binärdateien, zu große und überzählige werden mit Namen abgewiesen. */
export async function readAttachments(files: File[], already: number): Promise<{ accepted: ChatAttachment[]; rejected: string[] }> {
  const accepted: ChatAttachment[] = [];
  const rejected: string[] = [];
  for (const file of files) {
    if (already + accepted.length >= MAX_ATTACHMENTS) {
      rejected.push(file.name);
      continue;
    }
    const content = await file.text().catch(() => null);
    if (content == null || content.includes('\u0000') || !content.trim() || content.length > MAX_ATTACHMENT_CHARS) {
      rejected.push(file.name);
      continue;
    }
    accepted.push({ name: file.name, content });
  }
  return { accepted, rejected };
}
