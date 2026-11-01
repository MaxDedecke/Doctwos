/** Quellen, die Dateien liefern; alles andere ist ein Web-System. Gegenstück: backend/services/web_documents. */
const FILE_SOURCE_TYPES = new Set(['git', 'local', 'folderwatch', 'webdav']);

export const isWebSourceType = (sourceType: string | null | undefined): boolean =>
  !!sourceType && !FILE_SOURCE_TYPES.has(sourceType.toLowerCase());
