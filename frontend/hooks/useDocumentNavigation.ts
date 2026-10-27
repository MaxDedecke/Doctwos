import { useCallback } from 'react';
import { resolveReferenceTarget } from '@/lib/referenceTarget';
import type { PanelSelection } from '@/lib/panelHistory';
import type { KnowledgeSource, WorkspaceDocument, CodeEntity } from '@/types/domain';
import type { ShowToast } from '@/components/Toast';
import type { Dispatch, SetStateAction } from 'react';

type Setter<T> = Dispatch<SetStateAction<T>>;
interface Options {
  connectedSources: KnowledgeSource[];
  panelConfigs: string[];
  panelFrozen: boolean[];
  panelSelections: PanelSelection[];
  addPanel: (type: string, selection?: Partial<PanelSelection>, frozen?: boolean) => boolean;
  ensureLivePanelType: (type: string, selection?: Partial<PanelSelection>) => boolean;
  pinFileFocus: (path: string | null, line?: number | null, sourceId?: number | string | null) => void;
  setSelectedDoc: Setter<WorkspaceDocument | null>;
  setSelectedFile: Setter<string | null>;
  setSelectedEntity: Setter<CodeEntity | null>;
  setSelectedLine: Setter<number | null>;
  showToast: ShowToast;
  t: (key: string, vars?: Record<string, string | number>) => string;
}

export function useDocumentNavigation({ connectedSources, panelConfigs, panelFrozen, panelSelections,
  addPanel, ensureLivePanelType, pinFileFocus, setSelectedDoc, setSelectedFile, setSelectedEntity,
  setSelectedLine, showToast, t }: Options) {
  const handleDocFocusRequest = useCallback((
    filePath: string,
    sourceId: number | string | null,
    locatorOrOpenIfMissing?: Partial<WorkspaceDocument> | boolean,
    openIfMissing = true,
    comparison = false,
  ) => {
    if (!sourceId) return;
    // Keep the old third-argument boolean accepted for existing callers while
    // reference navigation now supplies the locator as a document object.
    const locator = typeof locatorOrOpenIfMissing === 'object' ? locatorOrOpenIfMissing : undefined;
    const shouldOpen = typeof locatorOrOpenIfMissing === 'boolean' ? locatorOrOpenIfMissing : openIfMissing;
    const { isWebOrigin } = resolveReferenceTarget(filePath, sourceId, connectedSources);
    const source = connectedSources.find(candidate => Number(candidate.id) === Number(sourceId));
    const targetType = isWebOrigin ? 'webview' : 'doc';
    const baseUrl = locator?.url || (isWebOrigin ? filePath : null);
    const viewerUrl = baseUrl && locator?.urlAnchor && !baseUrl.includes('#')
      ? `${baseUrl}#${locator.urlAnchor}`
      : baseUrl;
    const selectedDocument: WorkspaceDocument = {
      ...locator,
      id: sourceId,
      name: filePath,
      isWebOrigin,
      url: viewerUrl,
      type: locator?.type || source?.type,
    };
    if (comparison) {
      const alreadyOpen = panelConfigs.some((config, index) => {
        const document = panelSelections[index]?.selectedDoc;
        return config === targetType && document && String(document.id) === String(sourceId)
          && document.name === filePath && (document.url || null) === (viewerUrl || null);
      });
      if (!alreadyOpen && !addPanel(targetType, {
        selectedFile: null, selectedDoc: selectedDocument, selectedEntity: null,
      }, true)) showToast(t('page.toast.noPanelSpace'), 'error');
      return;
    }
    const hasLiveTargetPanel = panelConfigs.some((config, index) => config === targetType && !panelFrozen[index]);
    if (!hasLiveTargetPanel && !shouldOpen) return;
    const selectionOverride = {
      selectedFile: null,
      selectedDoc: selectedDocument,
      selectedEntity: null,
    };
    if (!ensureLivePanelType(targetType, selectionOverride)) {
      showToast(t('page.toast.noPanelSpace'), 'error');
      return;
    }
    pinFileFocus(filePath, null, sourceId);
    setSelectedDoc(selectedDocument);
    setSelectedFile(null);
    setSelectedEntity(null);
    setSelectedLine(null);
  }, [addPanel, connectedSources, ensureLivePanelType, panelConfigs, panelFrozen, panelSelections, pinFileFocus, setSelectedDoc, setSelectedEntity, setSelectedFile, setSelectedLine, showToast, t]);

  return handleDocFocusRequest;
}
