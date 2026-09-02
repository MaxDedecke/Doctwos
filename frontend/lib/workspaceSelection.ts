/**
 * File types that are rendered by the document/web-origin panels instead of
 * the code panel. The same classification is used by navigation callers and
 * by the workspace so a reference cannot open different panel types depending
 * on where the user clicked it.
 */
export const DOC_FILE_RE = /\.(pdf|docx?|png|jpe?g|md)$/i;

/**
 * Return the panel type that can render a selection, or null for no selection.
 * Web-origin documents are checked first because their URL may not have a
 * conventional document extension.
 */
export function getSelectionViewType(path: string | null, doc: any | null): string | null {
  if (doc?.isWebOrigin) return 'webview';
  const name = path || doc?.name || null;
  if (!name) return null;
  const cleanName = name.split('#')[0];
  if (DOC_FILE_RE.test(cleanName)) return 'doc';
  return 'code';
}
