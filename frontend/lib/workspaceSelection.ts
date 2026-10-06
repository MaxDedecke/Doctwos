import type { WorkspaceDocument } from '@/types/domain';
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
export function getSelectionViewType(path: string | null, doc: Partial<Pick<WorkspaceDocument, 'name' | 'isWebOrigin'>> | null): string | null {
  if (doc?.isWebOrigin) return 'webview';
  const name = path || doc?.name || null;
  if (!name) return null;
  const cleanName = name.split('#')[0];
  if (DOC_FILE_RE.test(cleanName)) return 'doc';
  return 'code';
}

/**
 * Was eine neu geöffnete Ansicht aus der aktuellen Auswahl übernehmen darf. Ein Code-Objekt im Fokus soll die
 * Dokument- oder Web-Ansicht nicht mit einer Codedatei öffnen (und umgekehrt der Code-Viewer kein Dokument):
 * Jede Ansicht bekommt nur, was sie darstellen kann. Chat, Graph und Prozessansichten spiegeln den Fokus.
 */
export function seedSelectionForPanelType<F extends string | null, D extends Partial<Pick<WorkspaceDocument, 'name' | 'isWebOrigin'>> | null, E>(
  type: string,
  current: { selectedFile: F; selectedDoc: D; selectedEntity: E },
): { selectedFile: F | null; selectedDoc: D | null; selectedEntity: E | null } {
  const fileType = getSelectionViewType(current.selectedFile, null);
  const docType = getSelectionViewType(null, current.selectedDoc);
  if (type === 'code') {
    return { selectedFile: fileType === 'code' ? current.selectedFile : null, selectedDoc: null, selectedEntity: fileType === 'code' ? current.selectedEntity : null };
  }
  if (type === 'doc') {
    return {
      selectedFile: fileType === 'doc' ? current.selectedFile : null,
      selectedDoc: docType === 'doc' ? current.selectedDoc : null,
      selectedEntity: null,
    };
  }
  if (type === 'webview') {
    return { selectedFile: null, selectedDoc: docType === 'webview' ? current.selectedDoc : null, selectedEntity: null };
  }
  return current;
}
